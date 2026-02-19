"""Decision Engine — evaluates step results and decides next action."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from evidentia.core.logging import get_logger
from evidentia.core.models import Run, StepResult, StepStatus

logger = get_logger(__name__)


class Decision(str, Enum):
    """Possible decisions after evaluating step results."""

    CONTINUE = "continue"
    RETRY_STEP = "retry_step"
    REPLAN = "replan"
    FALLBACK = "fallback"
    COMPLETE = "complete"
    FAIL = "fail"


class DecisionContext(BaseModel):
    """Information the decision engine uses to choose next action."""

    run: Run
    latest_results: list[StepResult]
    remaining_budget: int
    validation_passed: bool


class DecisionEngine:
    """Evaluates execution state and decides: continue, retry, replan, or stop."""

    def __init__(self, *, failure_threshold: float = 0.5) -> None:
        self._failure_threshold = failure_threshold

    def evaluate(self, ctx: DecisionContext) -> Decision:
        """Determine the next action based on current execution state."""
        total = len(ctx.latest_results)
        if total == 0:
            return Decision.COMPLETE

        failed = sum(1 for r in ctx.latest_results if r.status == StepStatus.FAILED)
        failure_rate = failed / total

        # All steps succeeded and validation passed
        if failed == 0 and ctx.validation_passed:
            logger.info("decision_complete", reason="all_steps_passed")
            return Decision.COMPLETE

        # No budget left — fail or complete with partial results
        if ctx.remaining_budget <= 0:
            logger.warning("decision_fail", reason="budget_exhausted")
            return Decision.FAIL

        # Minor failures — retry individual steps
        if failure_rate <= self._failure_threshold:
            logger.info("decision_retry", failure_rate=failure_rate)
            return Decision.RETRY_STEP

        # Major failures — replan from scratch
        logger.warning("decision_replan", failure_rate=failure_rate)
        return Decision.REPLAN
