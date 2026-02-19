"""Planner — generates structured execution plans from user queries via LLM."""

from __future__ import annotations

from typing import Any

from evidentia.core.exceptions import PlanningError
from evidentia.core.logging import get_logger
from evidentia.core.models import ExecutionPlan
from evidentia.schemas.api import QueryRequest

logger = get_logger(__name__)

# System prompt instructing the LLM to produce a structured plan.
PLANNER_SYSTEM_PROMPT = """\
You are the planning module of Evidentia, a research agent.
Given a user's research query and a list of available tools, produce a structured execution plan.

Rules:
1. Break the query into discrete, atomic steps.
2. Each step must specify exactly ONE tool to call.
3. Steps may declare dependencies on prior steps via depends_on.
4. Independent steps should NOT depend on each other (they can run in parallel).
5. Always include a validation / synthesis step at the end.
6. Output valid JSON matching the ExecutionPlan schema.
"""


class Planner:
    """Generates an ExecutionPlan from a user query using an LLM."""

    def __init__(self, llm_client: Any, available_tools: list[str]) -> None:
        self._llm = llm_client
        self._available_tools = available_tools

    async def generate_plan(self, request: QueryRequest) -> ExecutionPlan:
        """Ask the LLM to produce a structured plan for the query.

        Returns:
            A validated ExecutionPlan ready for the ToolRouter.

        Raises:
            PlanningError: If the LLM output cannot be parsed into a valid plan.
        """
        logger.info("generating_plan", query=request.query)

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Query: {request.query}\n\n"
                    f"Available tools: {', '.join(self._available_tools)}\n"
                    f"Max steps: {request.max_steps}"
                ),
            },
        ]

        try:
            raw = await self._llm.chat(messages, response_format="json")
            plan = ExecutionPlan.model_validate_json(raw)
        except Exception as exc:
            raise PlanningError(f"Failed to generate valid plan: {exc}") from exc

        self._validate_plan(plan, request)
        logger.info("plan_generated", step_count=len(plan.steps))
        return plan

    def _validate_plan(self, plan: ExecutionPlan, request: QueryRequest) -> None:
        """Sanity-check the plan before execution."""
        if not plan.steps:
            raise PlanningError("Plan has zero steps")
        if len(plan.steps) > request.max_steps:
            raise PlanningError(f"Plan has {len(plan.steps)} steps, exceeding max of {request.max_steps}")
        step_ids = {s.id for s in plan.steps}
        for step in plan.steps:
            if step.tool_name not in self._available_tools:
                raise PlanningError(f"Unknown tool '{step.tool_name}' in plan step {step.id}")
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise PlanningError(f"Step {step.id} depends on unknown step {dep}")
