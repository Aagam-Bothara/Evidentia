"""Validation endpoints — compare Evidentia reviews against gold-standard reviews."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger
from evidentia.core.validation import (
    GoldPaper,
    GoldStandardReview,
    ValidationEngine,
    get_sample_gold_standard,
)

logger = get_logger(__name__)

router = APIRouter()

# ── Request / response schemas ───────────────────────────────────────


class GoldPaperRequest(BaseModel):
    title: str
    doi: str | None = None
    decision: str = "include"
    reason: str | None = None


class CustomGoldRequest(BaseModel):
    title: str
    research_question: str
    included_papers: list[GoldPaperRequest]
    excluded_papers: list[GoldPaperRequest] = Field(default_factory=list)
    total_identified: int | None = None
    total_screened: int | None = None
    total_included: int | None = None


class ValidateRequest(BaseModel):
    gold_standard: str = Field(
        default="sample",
        description="Which gold standard to use: 'sample' for built-in, 'custom' for user-provided.",
        pattern=r"^(sample|custom)$",
    )
    custom_gold: CustomGoldRequest | None = None


class GoldStandardSummary(BaseModel):
    id: str
    title: str
    source: str
    included_count: int
    excluded_count: int


class GoldStandardListResponse(BaseModel):
    gold_standards: list[GoldStandardSummary]


# ── Helpers ──────────────────────────────────────────────────────────


def _get_review_papers(
    review_id: str,
    user: AuthenticatedUser,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Synchronously try to load Evidentia review papers.

    Returns (papers_list, prisma_dict | None).
    This is a helper that encapsulates the DB-try / in-memory-fallback
    pattern used throughout the routes layer.
    """
    # We cannot use async DB access here directly; callers should use
    # the async version below.  This exists only as a signature reference.
    raise NotImplementedError("Use _get_review_papers_async")


async def _get_review_papers_async(
    review_id: str,
    user: AuthenticatedUser,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Load review papers from DB or in-memory fallback.

    Returns (papers_list, prisma_dict | None).
    """
    # ── Try DB ───────────────────────────────────────────────────
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.review_repository import ReviewRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ReviewRepository(db)
            review = await repo.get(uuid.UUID(review_id))
            if review is None or review.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Review not found")

            rows = await repo.get_papers(uuid.UUID(review_id))
            papers: list[dict[str, Any]] = [
                {
                    "id": str(r.id),
                    "title": r.title,
                    "doi": r.doi,
                    "screening_decision": r.screening_decision,
                    "exclusion_reason": r.exclusion_reason,
                }
                for r in rows
            ]

            prisma: dict[str, Any] = {
                "total_identified": review.total_identified,
                "records_screened": review.total_screened,
                "included_count": review.total_included,
                "duplicates_removed": review.total_duplicates,
                "excluded_at_screening": review.total_excluded_screening,
            }

            return papers, prisma
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("validation_db_fallback", error=str(exc))

    # ── Fallback: in-memory store from reviews route ─────────────
    try:
        from evidentia.api.routes.reviews import _review_papers_store, _review_store

        review_data = _review_store.get(review_id)
        if review_data is None or review_data.get("user_id") != str(user.user_id):
            raise HTTPException(status_code=404, detail="Review not found")

        raw_papers = _review_papers_store.get(review_id, [])
        papers = [
            {
                "id": p.get("id", ""),
                "title": p.get("title", ""),
                "doi": p.get("doi"),
                "screening_decision": p.get("screening_decision"),
                "exclusion_reason": p.get("exclusion_reason"),
            }
            for p in raw_papers
        ]

        prisma_raw = review_data.get("prisma", {})
        prisma = prisma_raw if prisma_raw else None

        return papers, prisma
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Review not found") from exc


def _build_gold_standard(body: ValidateRequest) -> GoldStandardReview:
    """Build a GoldStandardReview from the request body."""
    if body.gold_standard == "sample":
        return get_sample_gold_standard()

    if body.custom_gold is None:
        raise HTTPException(
            status_code=400,
            detail="custom_gold is required when gold_standard='custom'",
        )

    cg = body.custom_gold
    included = [GoldPaper(title=p.title, doi=p.doi, decision="include") for p in cg.included_papers]
    excluded = [GoldPaper(title=p.title, doi=p.doi, decision="exclude", reason=p.reason) for p in cg.excluded_papers]

    return GoldStandardReview(
        title=cg.title,
        research_question=cg.research_question,
        included_papers=included,
        excluded_papers=excluded,
        total_identified=cg.total_identified or (len(included) + len(excluded)),
        total_screened=cg.total_screened or (len(included) + len(excluded)),
        total_included=cg.total_included or len(included),
        source="custom",
    )


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/validate/review/{review_id}")
async def validate_review(
    review_id: str,
    body: ValidateRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, Any]:
    """Validate a systematic review against a gold standard.

    Body:
    {
        "gold_standard": "sample" | "custom",
        "custom_gold": {
            "title": "...",
            "research_question": "...",
            "included_papers": [{"title": "...", "doi": "..."}],
            "excluded_papers": [{"title": "...", "doi": "...", "reason": "..."}]
        }
    }

    Returns the full ValidationResult with confusion matrix, metrics,
    and paper-level matching details.
    """
    gold = _build_gold_standard(body)
    papers, prisma = await _get_review_papers_async(review_id, user)

    if not papers:
        raise HTTPException(
            status_code=400,
            detail="Review has no papers to validate. Run the review first.",
        )

    engine = ValidationEngine()
    result = engine.validate_review(
        gold=gold,
        evidentia_papers=papers,
        evidentia_prisma=prisma,
        review_id=review_id,
    )

    logger.info(
        "review_validated",
        review_id=review_id,
        gold_title=gold.title,
        f1=round(result.f1_score, 4),
    )

    return result.to_dict()


@router.get("/validate/gold-standards")
async def list_gold_standards(
    user: AuthenticatedUser = Depends(require_auth),
) -> GoldStandardListResponse:
    """List available built-in gold standard reviews."""
    sample = get_sample_gold_standard()
    return GoldStandardListResponse(
        gold_standards=[
            GoldStandardSummary(
                id="sample_vitamin_d",
                title=sample.title,
                source=sample.source,
                included_count=len(sample.included_papers),
                excluded_count=len(sample.excluded_papers),
            ),
        ]
    )


@router.post("/validate/upload-gold")
async def upload_gold_standard(
    file: UploadFile = File(...),
    title: str = Query(..., min_length=5, max_length=500),
    research_question: str = Query(..., min_length=10, max_length=2000),
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, Any]:
    """Upload a BibTeX file as a custom gold standard.

    The uploaded BibTeX is parsed and returned as a gold standard summary
    that can be passed to the validate endpoint.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    if not file.filename.lower().endswith((".bib", ".bibtex", ".txt")):
        raise HTTPException(
            status_code=400,
            detail="Only BibTeX files (.bib, .bibtex, .txt) are accepted.",
        )

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:  # 5 MB limit
        raise HTTPException(status_code=413, detail="File too large. Maximum 5MB.")

    try:
        bibtex_text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            bibtex_text = content.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail="Unable to decode file. Ensure it is UTF-8 or Latin-1 encoded.",
            ) from exc

    try:
        from evidentia.core.validation import create_gold_from_bibtex

        gold = create_gold_from_bibtex(
            title=title,
            research_question=research_question,
            included_bibtex=bibtex_text,
        )
    except Exception as exc:
        logger.warning("gold_bibtex_parse_failed", error=str(exc))
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse BibTeX file: {exc}",
        ) from exc

    logger.info(
        "gold_standard_uploaded",
        title=title,
        included=len(gold.included_papers),
    )

    return {
        "title": gold.title,
        "research_question": gold.research_question,
        "source": gold.source,
        "included_count": len(gold.included_papers),
        "excluded_count": len(gold.excluded_papers),
        "included_papers": [{"title": p.title, "doi": p.doi} for p in gold.included_papers],
    }
