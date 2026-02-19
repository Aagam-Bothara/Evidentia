"""Tool Router — dispatches plan steps to the correct tools, handling parallelism."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from evidentia.core.exceptions import BudgetExhaustedError, ToolExecutionError
from evidentia.core.logging import get_logger
from evidentia.core.models import ExecutionPlan, PlanStep, StepResult, StepStatus
from evidentia.tools.base import BaseTool

logger = get_logger(__name__)


class ToolRouter:
    """Executes plan steps by routing them to registered tools."""

    def __init__(
        self,
        tools: dict[str, BaseTool],
        max_retries: int = 3,
        max_total_calls: int = 50,
    ) -> None:
        self._tools = tools
        self._max_retries = max_retries
        self._max_total_calls = max_total_calls
        self._total_calls = 0

    async def execute_plan(self, plan: ExecutionPlan) -> list[StepResult]:
        """Execute all steps in the plan, respecting dependency ordering.

        Independent steps run concurrently; dependent steps wait for their parents.
        """
        results: dict[str, StepResult] = {}
        completed: set[str] = set()

        # Build dependency graph
        dependents: dict[str, list[str]] = {s.id: [] for s in plan.steps}
        for step in plan.steps:
            for dep in step.depends_on:
                dependents[dep].append(step.id)

        # Find initially ready steps (no dependencies)
        ready = [s for s in plan.steps if not s.depends_on]
        pending = {s.id: s for s in plan.steps if s.depends_on}

        while ready:
            # Run all ready steps concurrently
            tasks = [self._execute_step(step) for step in ready]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            next_ready: list[PlanStep] = []
            for step, result in zip(ready, batch_results):
                if isinstance(result, Exception):
                    sr = StepResult(
                        step_id=step.id,
                        tool_name=step.tool_name,
                        status=StepStatus.FAILED,
                        error=str(result),
                    )
                else:
                    sr = result

                results[step.id] = sr
                completed.add(step.id)

                # Check if any pending steps are now unblocked
                for dep_id in dependents.get(step.id, []):
                    if dep_id in pending:
                        dep_step = pending[dep_id]
                        if all(d in completed for d in dep_step.depends_on):
                            next_ready.append(dep_step)
                            del pending[dep_id]

            ready = next_ready

        # Mark any remaining pending steps as skipped
        for step_id, step in pending.items():
            results[step_id] = StepResult(
                step_id=step_id,
                tool_name=step.tool_name,
                status=StepStatus.SKIPPED,
                error="Dependencies did not complete",
            )

        return [results[s.id] for s in plan.steps]

    async def _execute_step(self, step: PlanStep) -> StepResult:
        """Execute a single step with retry logic."""
        tool = self._tools.get(step.tool_name)
        if tool is None:
            return StepResult(
                step_id=step.id,
                tool_name=step.tool_name,
                status=StepStatus.FAILED,
                error=f"Tool '{step.tool_name}' not registered",
            )

        last_error: str | None = None
        for attempt in range(self._max_retries + 1):
            if self._total_calls >= self._max_total_calls:
                raise BudgetExhaustedError(
                    f"Exceeded max tool calls ({self._max_total_calls})"
                )

            self._total_calls += 1
            started = datetime.now(timezone.utc)

            try:
                logger.info(
                    "executing_step",
                    step_id=step.id,
                    tool=step.tool_name,
                    attempt=attempt + 1,
                )
                output = await tool.execute(step.tool_input)
                return StepResult(
                    step_id=step.id,
                    tool_name=step.tool_name,
                    status=StepStatus.SUCCESS,
                    output=output,
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                    retries=attempt,
                )
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "step_failed",
                    step_id=step.id,
                    tool=step.tool_name,
                    attempt=attempt + 1,
                    error=last_error,
                )

        return StepResult(
            step_id=step.id,
            tool_name=step.tool_name,
            status=StepStatus.FAILED,
            error=f"All {self._max_retries + 1} attempts failed. Last error: {last_error}",
            retries=self._max_retries,
        )
