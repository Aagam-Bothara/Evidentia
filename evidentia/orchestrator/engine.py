"""Orchestration Engine — the main control loop tying planner, router, validator, and decision."""

from __future__ import annotations

from datetime import UTC, datetime

from evidentia.core.config import Settings
from evidentia.core.exceptions import BudgetExhaustedError
from evidentia.core.logging import get_logger
from evidentia.core.models import Run, RunStatus, StepStatus
from evidentia.orchestrator.decision import Decision, DecisionContext, DecisionEngine
from evidentia.orchestrator.planner import Planner
from evidentia.orchestrator.router import ToolRouter
from evidentia.schemas.api import QueryRequest, QueryResponse
from evidentia.validator.engine import ValidationEngine

logger = get_logger(__name__)


class OrchestrationEngine:
    """Top-level control loop: Plan → Call → Validate → Decide."""

    def __init__(
        self,
        planner: Planner,
        router: ToolRouter,
        validator: ValidationEngine,
        decision_engine: DecisionEngine,
        settings: Settings,
    ) -> None:
        self._planner = planner
        self._router = router
        self._validator = validator
        self._decision = decision_engine
        self._settings = settings

    async def run_query(self, request: QueryRequest) -> QueryResponse:
        """Execute the full research pipeline for a query."""
        run = Run(query=request.query, status=RunStatus.PLANNING)
        logger.info("run_started", run_id=run.id, query=request.query)

        try:
            # Phase 1: Plan
            run.plan = await self._planner.generate_plan(request)
            run.status = RunStatus.EXECUTING

            remaining_budget = self._settings.max_tool_calls_per_run
            max_iterations = 3  # Prevent infinite replan loops

            for iteration in range(max_iterations):
                # Phase 2: Execute
                results = await self._router.execute_plan(run.plan)
                run.steps.extend(results)
                remaining_budget -= len(results)

                # Phase 3: Validate
                validation_passed = await self._validator.validate_results(results)

                # Phase 4: Decide
                ctx = DecisionContext(
                    run=run,
                    latest_results=results,
                    remaining_budget=remaining_budget,
                    validation_passed=validation_passed,
                )
                decision = self._decision.evaluate(ctx)

                if decision == Decision.COMPLETE:
                    run.status = RunStatus.COMPLETED
                    break
                elif decision == Decision.FAIL:
                    run.status = RunStatus.FAILED
                    break
                elif decision == Decision.REPLAN:
                    logger.info("replanning", iteration=iteration + 1)
                    run.plan = await self._planner.generate_plan(request)
                elif decision == Decision.RETRY_STEP:
                    failed_steps = [r for r in results if r.status == StepStatus.FAILED]
                    logger.info("retrying_steps", count=len(failed_steps))
                    # Re-execution happens on next loop iteration with same plan
            else:
                run.status = RunStatus.FAILED

            run.completed_at = datetime.now(UTC)

        except BudgetExhaustedError:
            run.status = RunStatus.FAILED
            run.completed_at = datetime.now(UTC)
            logger.error("budget_exhausted", run_id=run.id)

        except Exception as exc:
            run.status = RunStatus.FAILED
            run.completed_at = datetime.now(UTC)
            logger.error("run_failed", run_id=run.id, error=str(exc))

        logger.info(
            "run_finished",
            run_id=run.id,
            status=run.status,
            steps=len(run.steps),
            elapsed=run.elapsed_seconds,
        )

        return QueryResponse(
            run_id=run.id,
            status=run.status,
            query=run.query,
            plan=run.plan,
            claims=run.claims,
            steps=run.steps,
            elapsed_seconds=run.elapsed_seconds,
        )
