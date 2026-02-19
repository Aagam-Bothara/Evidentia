"""Query endpoint — submit research queries to the agent."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger
from evidentia.schemas.api import QueryRequest, QueryResponse

logger = get_logger(__name__)

router = APIRouter()

# In-memory run store for background results (production: DB-backed)
_pending_runs: dict[str, dict] = {}


@router.post("/query", response_model=QueryResponse)
async def submit_query(
    request: QueryRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> QueryResponse:
    """Submit a research query — runs agent in background, returns run_id immediately."""
    run_id = uuid.uuid4().hex

    # Start agent in background
    asyncio.create_task(_run_agent(run_id, request.query, user.user_id))

    return QueryResponse(
        run_id=run_id,
        status="pending",
        query=request.query,
    )


@router.get("/runs/{run_id}", response_model=QueryResponse)
async def get_run(
    run_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> QueryResponse:
    """Retrieve results of a previous run by ID."""
    # Check in-memory pending runs
    if run_id in _pending_runs:
        return QueryResponse(**_pending_runs[run_id])

    # Check database
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import RunRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = RunRepository(db)
            run = await repo.get_run(uuid.UUID(run_id))
            if run and run.user_id == user.user_id:
                claims = repo.run_to_claims(run)
                return QueryResponse(
                    run_id=str(run.id),
                    status=run.status,
                    query=run.query,
                    claims=claims,
                    elapsed_seconds=run.elapsed_seconds,
                )
    except Exception as exc:
        logger.warning("run_fetch_failed", error=str(exc))

    raise HTTPException(status_code=404, detail="Run not found")


async def _run_agent(run_id: str, query: str, user_id: uuid.UUID) -> None:
    """Background task: run the agent and store results."""
    _pending_runs[run_id] = {
        "run_id": run_id,
        "status": "executing",
        "query": query,
    }

    try:
        from evidentia.agent.factory import build_agent

        agent = build_agent()
        result = await agent.run(query)

        _pending_runs[run_id] = {
            "run_id": run_id,
            "status": "completed" if result.success else "failed",
            "query": query,
            "claims": result.claims,
            "elapsed_seconds": result.elapsed_seconds,
        }

        # Persist to DB
        try:
            from evidentia.db.engine import _get_session_factory
            from evidentia.db.repositories import RunRepository

            factory = _get_session_factory()
            async with factory() as db:
                repo = RunRepository(db)
                await repo.save_run(
                    user_id=user_id,
                    query=query,
                    summary=result.summary,
                    claims=result.claims,
                    plan_json=result.plan.model_dump() if result.plan else None,
                    evidence_summary=result.evidence_summary,
                    total_tool_calls=result.total_tool_calls,
                    total_iterations=result.total_iterations,
                    elapsed_seconds=result.elapsed_seconds,
                    success=result.success,
                )
                await db.commit()
        except Exception as exc:
            logger.warning("run_persist_failed", run_id=run_id, error=str(exc))

    except Exception as exc:
        logger.error("agent_run_failed", run_id=run_id, error=str(exc))
        _pending_runs[run_id] = {
            "run_id": run_id,
            "status": "failed",
            "query": query,
        }
