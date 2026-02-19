"""API request / response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from evidentia.core.models import Claim, ExecutionPlan, RunStatus, StepResult

# ── Query ────────────────────────────────────────────────────────────


class QueryRequest(BaseModel):
    """Incoming research query from user."""

    query: str = Field(..., min_length=1, max_length=5000)
    tools: list[str] | None = Field(default=None, description="Restrict to specific tool names. None = auto-select.")
    max_steps: int = Field(default=20, ge=1, le=100)
    project_id: str | None = None


class QueryResponse(BaseModel):
    """Structured response returned to the user."""

    run_id: str
    status: RunStatus
    query: str
    plan: ExecutionPlan | None = None
    claims: list[Claim] = Field(default_factory=list)
    steps: list[StepResult] = Field(default_factory=list)
    elapsed_seconds: float | None = None


# ── Run trace ────────────────────────────────────────────────────────


class RunTraceResponse(BaseModel):
    """Full trace of a past run for replay/inspection."""

    run_id: str
    query: str
    status: RunStatus
    plan: ExecutionPlan | None = None
    steps: list[StepResult] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Tools ────────────────────────────────────────────────────────────


class ToolListItem(BaseModel):
    """Summary of an available tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    category: str


class ToolListResponse(BaseModel):
    tools: list[ToolListItem]


# ── Auth ─────────────────────────────────────────────────────────────


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ── Health ───────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    environment: str
