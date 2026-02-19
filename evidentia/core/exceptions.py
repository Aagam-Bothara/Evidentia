"""Structured exception hierarchy for Evidentia."""

from __future__ import annotations


class EvidentiaCoreError(Exception):
    """Base exception for all Evidentia errors."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        self.code = code or self.__class__.__name__
        super().__init__(message)


# ── Orchestrator errors ──────────────────────────────────────────────

class PlanningError(EvidentiaCoreError):
    """LLM planner failed to produce a valid structured plan."""


class BudgetExhaustedError(EvidentiaCoreError):
    """Run exceeded its tool-call or token budget."""


class OrchestrationError(EvidentiaCoreError):
    """Generic control-plane failure."""


# ── Tool errors ──────────────────────────────────────────────────────

class ToolExecutionError(EvidentiaCoreError):
    """A tool call failed after all retries."""

    def __init__(
        self,
        message: str,
        *,
        tool_name: str,
        status_code: int | None = None,
        retry_after: float | None = None,
        **kwargs,
    ) -> None:
        self.tool_name = tool_name
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


class ToolTimeoutError(ToolExecutionError):
    """Tool call exceeded its timeout."""


class ToolSchemaError(EvidentiaCoreError):
    """Tool input or output did not match its declared schema."""


# ── Validation errors ────────────────────────────────────────────────

class ValidationError(EvidentiaCoreError):
    """Generic validation failure."""


class CitationValidationError(ValidationError):
    """A claim was missing a required citation or evidence span."""


class EvidenceConflictError(ValidationError):
    """Sources disagree — flagged for user review."""


# ── Connector errors ─────────────────────────────────────────────────

class ConnectorAuthError(EvidentiaCoreError):
    """BYO-API credentials are missing or invalid."""


class ConnectorRuntimeError(EvidentiaCoreError):
    """The user-owned connector runtime is unreachable."""


# ── Retrieval errors ─────────────────────────────────────────────────

class RetrievalError(EvidentiaCoreError):
    """Failed to search or retrieve documents."""


# ── Review errors ──────────────────────────────────────────────────

class ReviewError(EvidentiaCoreError):
    """Systematic review pipeline failure."""


class ScreeningError(ReviewError):
    """LLM screening failed for a batch of papers."""
