"""Query endpoint — submit research queries to the agent."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger
from evidentia.core.reproducibility import (
    RunFingerprint,
    build_fingerprint,
    verify_fingerprint,
)
from evidentia.core.reproducibility import (
    compare_runs as compare_fingerprints,
)
from evidentia.schemas.api import QueryRequest, QueryResponse

logger = get_logger(__name__)

router = APIRouter()

# In-memory run store for background results (production: DB-backed)
_pending_runs: dict[str, dict] = {}

# In-memory fingerprint store (fallback when DB is unavailable)
_run_fingerprints: dict[str, dict] = {}

# In-memory claims store keyed by run_id for verification/comparison
_run_claims: dict[str, list[dict]] = {}
_run_queries: dict[str, str] = {}


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


class RunSummary(BaseModel):
    """Lightweight run summary for listing — no full claims data."""

    run_id: str
    query: str
    status: str
    claim_count: int = 0
    elapsed_seconds: float | None = None
    created_at: str = ""


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(
    user: AuthenticatedUser = Depends(require_auth),
) -> list[RunSummary]:
    """List recent runs for the current user (lightweight, no full claims)."""
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import RunRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = RunRepository(db)
            rows = await repo.list_runs(user.user_id, limit=50)
            return [
                RunSummary(
                    run_id=str(r.id),
                    query=r.query,
                    status=r.status,
                    claim_count=len(r.claims) if r.claims else 0,
                    elapsed_seconds=r.elapsed_seconds,
                    created_at=r.created_at.isoformat() if r.created_at else "",
                )
                for r in rows
            ]
    except Exception as exc:
        logger.warning("list_runs_failed", error=str(exc))

    return []


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
        from evidentia.agent.factory import build_agent_for_user

        agent = await build_agent_for_user(str(user_id))
        result = await agent.run(query)

        # Build reproducibility fingerprint
        claims_dicts = [c.model_dump() for c in result.claims]
        fp = build_fingerprint(run_id=run_id, query=query, claims=claims_dicts)
        fp_dict = fp.to_dict()

        # Store fingerprint and run data in memory for API access
        _run_fingerprints[run_id] = fp_dict
        _run_claims[run_id] = claims_dicts
        _run_queries[run_id] = query

        _pending_runs[run_id] = {
            "run_id": run_id,
            "status": "completed" if result.success else "failed",
            "query": query,
            "claims": result.claims,
            "elapsed_seconds": result.elapsed_seconds,
            "fingerprint": fp_dict,
        }

        # Persist to DB (include fingerprint in evidence_summary)
        try:
            from evidentia.db.engine import _get_session_factory
            from evidentia.db.repositories import RunRepository

            ev_summary = result.evidence_summary or {}
            ev_summary["fingerprint"] = fp_dict

            factory = _get_session_factory()
            async with factory() as db:
                repo = RunRepository(db)
                await repo.save_run(
                    user_id=user_id,
                    query=query,
                    summary=result.summary,
                    claims=result.claims,
                    plan_json=result.plan.model_dump() if result.plan else None,
                    evidence_summary=ev_summary,
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


# ── Reproducibility Endpoints ────────────────────────────────────


class FingerprintResponse(BaseModel):
    fingerprint: dict


class VerifyResponse(BaseModel):
    passed: bool
    run_id: str
    expected_composite: str
    actual_composite: str
    mismatches: list[str]
    details: dict


class CompareRequest(BaseModel):
    run_id_a: str
    run_id_b: str


class CompareResponse(BaseModel):
    comparison: dict


@router.get("/runs/{run_id}/fingerprint", response_model=FingerprintResponse)
async def get_fingerprint(
    run_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> FingerprintResponse:
    """Return the reproducibility fingerprint for a run."""
    # Check in-memory store
    if run_id in _run_fingerprints:
        return FingerprintResponse(fingerprint=_run_fingerprints[run_id])

    # Check database (fingerprint stored in evidence_summary_json)
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import RunRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = RunRepository(db)
            run = await repo.get_run(uuid.UUID(run_id))
            if run and run.user_id == user.user_id:
                ev_summary = run.evidence_summary_json or {}
                if "fingerprint" in ev_summary:
                    return FingerprintResponse(fingerprint=ev_summary["fingerprint"])

                # Build fingerprint from stored data if not already present
                claims = repo.run_to_claims(run)
                claims_dicts = [c.model_dump() for c in claims]
                fp = build_fingerprint(
                    run_id=str(run.id),
                    query=run.query,
                    claims=claims_dicts,
                )
                fp_dict = fp.to_dict()
                _run_fingerprints[run_id] = fp_dict
                return FingerprintResponse(fingerprint=fp_dict)
    except Exception as exc:
        logger.warning("fingerprint_fetch_failed", error=str(exc))

    raise HTTPException(status_code=404, detail="Fingerprint not found")


@router.post("/runs/{run_id}/verify", response_model=VerifyResponse)
async def verify_run(
    run_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> VerifyResponse:
    """Re-verify the fingerprint against stored data."""
    # Get fingerprint
    fp_dict = _run_fingerprints.get(run_id)
    query = _run_queries.get(run_id)
    claims = _run_claims.get(run_id)

    # Try DB fallback
    if fp_dict is None:
        try:
            from evidentia.db.engine import _get_session_factory
            from evidentia.db.repositories import RunRepository

            factory = _get_session_factory()
            async with factory() as db:
                repo = RunRepository(db)
                run = await repo.get_run(uuid.UUID(run_id))
                if run and run.user_id == user.user_id:
                    query = run.query
                    claims_objs = repo.run_to_claims(run)
                    claims = [c.model_dump() for c in claims_objs]
                    ev_summary = run.evidence_summary_json or {}
                    fp_dict = ev_summary.get("fingerprint")
                    if fp_dict is None:
                        # Build it on the fly
                        fp = build_fingerprint(run_id=str(run.id), query=query, claims=claims)
                        fp_dict = fp.to_dict()
        except Exception as exc:
            logger.warning("verify_fetch_failed", error=str(exc))

    if fp_dict is None or query is None or claims is None:
        raise HTTPException(status_code=404, detail="Run data not found for verification")

    fingerprint = RunFingerprint.from_dict(fp_dict)
    result = verify_fingerprint(
        fingerprint=fingerprint,
        query=query,
        claims=claims,
        tool_calls=fingerprint.tool_call_log,
    )
    return VerifyResponse(**result.to_dict())


@router.post("/runs/compare", response_model=CompareResponse)
async def compare_runs_endpoint(
    body: CompareRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> CompareResponse:
    """Compare two research runs."""

    async def _load_run_data(rid: str) -> tuple[dict | None, list[dict] | None]:
        """Load fingerprint and claims for a run."""
        fp = _run_fingerprints.get(rid)
        cl = _run_claims.get(rid)
        if fp and cl is not None:
            return fp, cl
        try:
            from evidentia.db.engine import _get_session_factory
            from evidentia.db.repositories import RunRepository

            factory = _get_session_factory()
            async with factory() as db:
                repo = RunRepository(db)
                run = await repo.get_run(uuid.UUID(rid))
                if run and run.user_id == user.user_id:
                    claims_objs = repo.run_to_claims(run)
                    cl = [c.model_dump() for c in claims_objs]
                    ev_summary = run.evidence_summary_json or {}
                    fp = ev_summary.get("fingerprint")
                    if fp is None:
                        fp_obj = build_fingerprint(run_id=str(run.id), query=run.query, claims=cl)
                        fp = fp_obj.to_dict()
                    return fp, cl
        except Exception as exc:
            logger.warning("compare_fetch_failed", run_id=rid, error=str(exc))
        return None, None

    fp_a, claims_a = await _load_run_data(body.run_id_a)
    fp_b, claims_b = await _load_run_data(body.run_id_b)

    if fp_a is None or fp_b is None:
        raise HTTPException(status_code=404, detail="One or both runs not found")

    fp1 = RunFingerprint.from_dict(fp_a)
    fp2 = RunFingerprint.from_dict(fp_b)

    result = compare_fingerprints(fp1, fp2, claims_a, claims_b)
    return CompareResponse(comparison=result.to_dict())


# ── Data Extraction Table ────────────────────────────────────────


class ExtractTableRequest(BaseModel):
    claims: list[dict] = Field(..., description="Claims from a research run")


class ExtractedRow(BaseModel):
    source: str
    authors: str
    year: str
    method: str
    sample_size: str
    key_finding: str
    outcome: str
    confidence: str


class ExtractTableResponse(BaseModel):
    rows: list[ExtractedRow]


@router.post("/extract-table", response_model=ExtractTableResponse)
async def extract_table(
    body: ExtractTableRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> ExtractTableResponse:
    """Extract structured data from research claims into a table."""
    from evidentia.core.config import get_settings
    from evidentia.core.llm import create_llm

    settings = get_settings()
    llm = create_llm(settings)

    # Build context from claims
    claims_text = ""
    for i, claim in enumerate(body.claims, 1):
        citations = claim.get("citations", [])
        evidence = claim.get("evidence_spans", [])
        cit_text = "; ".join(c.get("title", "Unknown") + " by " + ", ".join(c.get("authors", [])) for c in citations)
        ev_text = " | ".join(e.get("text", "") for e in evidence)
        claims_text += (
            f"\nClaim {i}: {claim.get('statement', '')}\n"
            f"Confidence: {claim.get('confidence', 'unknown')}\n"
            f"Sources: {cit_text}\n"
            f"Evidence: {ev_text}\n"
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a research data extractor. Given research claims with "
                "citations and evidence, extract structured data into rows. Each "
                "row represents one study/source.\n\n"
                "Return ONLY a JSON array of objects with these fields:\n"
                "- source: paper title (short)\n"
                "- authors: first author et al.\n"
                "- year: publication year or 'N/A'\n"
                "- method: study methodology (e.g., 'RCT', 'Meta-analysis', "
                "'Survey', 'Review')\n"
                "- sample_size: sample size or 'N/A'\n"
                "- key_finding: main finding in 1-2 sentences\n"
                "- outcome: primary outcome measure\n"
                "- confidence: 'high', 'medium', or 'low'\n\n"
                "Respond with ONLY the JSON array, no markdown fencing."
            ),
        },
        {
            "role": "user",
            "content": (f"Extract structured data from these research findings:\n{claims_text}"),
        },
    ]

    response = await llm.chat(messages, temperature=0.0, max_tokens=3000)

    # Parse JSON response
    import json as _json

    try:
        content = response.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        rows_data = _json.loads(content)
        rows = [ExtractedRow(**row) for row in rows_data]
    except Exception:
        rows = []

    return ExtractTableResponse(rows=rows)


# ── Statistical Synthesis ────────────────────────────────────────


class SynthesizeRequest(BaseModel):
    studies: list[dict] = Field(..., description="Study data rows from the extraction table")


@router.post("/synthesize")
async def synthesize(
    body: SynthesizeRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict:
    """Perform cross-study statistical synthesis (meta-analysis).

    Takes an array of study objects from the extraction table and returns
    pooled effect sizes, heterogeneity measures, and forest plot data.
    This is pure statistical computation — no LLM involved.
    """
    from evidentia.core.statistics import StatisticalSynthesis

    engine = StatisticalSynthesis()

    try:
        result = engine.auto_synthesize(body.studies)
        return engine.result_to_dict(result)
    except Exception as exc:
        logger.error("synthesis_failed", error=str(exc))
        raise HTTPException(
            status_code=422,
            detail=f"Statistical synthesis failed: {str(exc)}",
        ) from exc


# ── Provenance Chain ─────────────────────────────────────────────


@router.get("/runs/{run_id}/provenance")
async def get_run_provenance(
    run_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict:
    """Return the full provenance chain for a run.

    Returns JSON with all provenance links, coverage score, and ungrounded claims.
    """
    from evidentia.core.provenance import get_provenance

    chain = get_provenance(run_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="Provenance chain not found for this run")

    return chain.to_dict()
