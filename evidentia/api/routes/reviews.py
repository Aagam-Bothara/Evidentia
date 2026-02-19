"""Systematic Review endpoints — PRISMA-compliant literature reviews."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger
from evidentia.review.exporter import ReviewExporter
from evidentia.review.feedback import FeedbackStore
from evidentia.review.models import PaperRecord
from evidentia.schemas.review import (
    BulkDecisionRequest,
    ContradictionReportResponse,
    PaperDecisionRequest,
    PaperListResponse,
    PaperResponse,
    PRISMAFlowResponse,
    QualityScoreResponse,
    ReviewCreateRequest,
    ReviewExportRequest,
    ReviewListResponse,
    ReviewResponse,
)

logger = get_logger(__name__)

router = APIRouter()

# In-memory fallback
_review_store: dict[str, dict[str, Any]] = {}
_review_papers_store: dict[str, list[dict[str, Any]]] = {}
_feedback_store = FeedbackStore()


def _paper_to_response(p: dict[str, Any]) -> PaperResponse:
    # Parse criteria evaluations from dict form
    raw_evals = p.get("criteria_evaluations")
    criteria_evals = None
    if raw_evals and isinstance(raw_evals, list):
        from evidentia.schemas.review import CriterionEvaluationResponse
        criteria_evals = [
            CriterionEvaluationResponse(
                criterion=e.get("criterion", "") if isinstance(e, dict) else getattr(e, "criterion", ""),
                criterion_type=e.get("criterion_type", "inclusion") if isinstance(e, dict) else getattr(e, "criterion_type", "inclusion"),
                met=e.get("met") if isinstance(e, dict) else getattr(e, "met", None),
                rationale=e.get("rationale", "") if isinstance(e, dict) else getattr(e, "rationale", ""),
                evidence_span=e.get("evidence_span", "") if isinstance(e, dict) else getattr(e, "evidence_span", ""),
            )
            for e in raw_evals
        ]

    return PaperResponse(
        id=p.get("id", ""),
        title=p.get("title", ""),
        authors=p.get("authors") or p.get("authors_json") or [],
        abstract=p.get("abstract"),
        doi=p.get("doi"),
        url=p.get("url"),
        published_date=p.get("published_date"),
        journal=p.get("journal"),
        citation_count=p.get("citation_count"),
        source_database=p.get("source_database", ""),
        is_duplicate=p.get("is_duplicate", False),
        screening_decision=p.get("screening_decision"),
        exclusion_reason=p.get("exclusion_reason"),
        manually_reviewed=p.get("manually_reviewed", False),
        quality_score=p.get("quality_score"),
        quality_grade=p.get("quality_grade"),
        quality_dimensions=p.get("quality_dimensions"),
        criteria_evaluations=criteria_evals,
        evidence_spans=p.get("evidence_spans"),
        screening_agreement=p.get("screening_agreement"),
        screening_votes=p.get("screening_votes"),
    )


@router.post("/reviews", response_model=ReviewResponse)
async def create_review(
    body: ReviewCreateRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> ReviewResponse:
    """Create a new systematic review."""
    # Try DB
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.review_repository import ReviewRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ReviewRepository(db)
            proj_id = None
            if body.project_id:
                try:
                    proj_id = uuid.UUID(body.project_id)
                except ValueError:
                    pass
            review = await repo.create(
                user_id=user.user_id,
                research_question=body.research_question,
                inclusion_criteria=body.inclusion_criteria,
                exclusion_criteria=body.exclusion_criteria,
                databases=body.databases,
                project_id=proj_id,
            )
            await db.commit()
            return ReviewResponse(
                id=str(review.id),
                research_question=review.research_question,
                status=review.status,
                created_at=review.created_at.isoformat(),
            )
    except Exception as exc:
        logger.warning("review_db_create_failed", error=str(exc))

    # Fallback
    review_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    _review_store[review_id] = {
        "id": review_id,
        "user_id": str(user.user_id),
        "research_question": body.research_question,
        "inclusion_criteria": body.inclusion_criteria,
        "exclusion_criteria": body.exclusion_criteria,
        "databases": body.databases,
        "mode": body.mode,
        "status": "pending",
        "created_at": now,
        "elapsed_seconds": None,
        "prisma": {},
    }
    _review_papers_store[review_id] = []

    return ReviewResponse(
        id=review_id,
        research_question=body.research_question,
        status="pending",
        mode=body.mode,
        created_at=now,
    )


@router.get("/reviews", response_model=ReviewListResponse)
async def list_reviews(
    user: AuthenticatedUser = Depends(require_auth),
) -> ReviewListResponse:
    """List user's systematic reviews."""
    # Try DB
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.review_repository import ReviewRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ReviewRepository(db)
            reviews = await repo.list_by_user(user.user_id)
            return ReviewListResponse(
                reviews=[
                    ReviewResponse(
                        id=str(r.id),
                        research_question=r.research_question,
                        status=r.status,
                        prisma=PRISMAFlowResponse(
                            total_identified=r.total_identified,
                            duplicates_removed=r.total_duplicates,
                            records_screened=r.total_screened,
                            excluded_at_screening=r.total_excluded_screening,
                            included_count=r.total_included,
                            uncertain_count=r.total_uncertain,
                        ),
                        created_at=r.created_at.isoformat(),
                        elapsed_seconds=r.elapsed_seconds,
                    )
                    for r in reviews
                ]
            )
    except Exception:
        pass

    # Fallback
    user_reviews = [
        ReviewResponse(
            id=r["id"],
            research_question=r["research_question"],
            status=r["status"],
            created_at=r["created_at"],
            elapsed_seconds=r.get("elapsed_seconds"),
        )
        for r in _review_store.values()
        if r["user_id"] == str(user.user_id)
    ]
    return ReviewListResponse(reviews=user_reviews)


@router.get("/reviews/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> ReviewResponse:
    """Get a systematic review with PRISMA data."""
    # Try DB
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.review_repository import ReviewRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ReviewRepository(db)
            review = await repo.get(uuid.UUID(review_id))
            if review is None or review.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Review not found")
            return ReviewResponse(
                id=str(review.id),
                research_question=review.research_question,
                status=review.status,
                prisma=PRISMAFlowResponse(
                    databases_searched=review.databases or [],
                    total_identified=review.total_identified,
                    duplicates_removed=review.total_duplicates,
                    records_screened=review.total_screened,
                    excluded_at_screening=review.total_excluded_screening,
                    included_count=review.total_included,
                    uncertain_count=review.total_uncertain,
                ),
                created_at=review.created_at.isoformat(),
                elapsed_seconds=review.elapsed_seconds,
            )
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback
    review = _review_store.get(review_id)
    if review is None or review["user_id"] != str(user.user_id):
        raise HTTPException(status_code=404, detail="Review not found")
    return ReviewResponse(
        id=review["id"],
        research_question=review["research_question"],
        status=review["status"],
        created_at=review["created_at"],
        elapsed_seconds=review.get("elapsed_seconds"),
    )


@router.delete("/reviews/{review_id}")
async def delete_review(
    review_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, str]:
    """Delete a systematic review."""
    # Try DB
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.review_repository import ReviewRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ReviewRepository(db)
            review = await repo.get(uuid.UUID(review_id))
            if review is None or review.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Review not found")
            await repo.delete(uuid.UUID(review_id))
            await db.commit()
            return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback
    review = _review_store.get(review_id)
    if review is None or review["user_id"] != str(user.user_id):
        raise HTTPException(status_code=404, detail="Review not found")
    del _review_store[review_id]
    _review_papers_store.pop(review_id, None)
    return {"status": "deleted"}


@router.get("/reviews/{review_id}/papers", response_model=PaperListResponse)
async def list_papers(
    review_id: str,
    decision: str | None = None,
    user: AuthenticatedUser = Depends(require_auth),
) -> PaperListResponse:
    """List papers in a review with optional filtering."""
    # Try DB
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.review_repository import ReviewRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ReviewRepository(db)
            review = await repo.get(uuid.UUID(review_id))
            if review is None or review.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Review not found")

            rows = await repo.get_papers(uuid.UUID(review_id), decision=decision)
            papers = [
                PaperResponse(
                    id=str(r.id),
                    title=r.title,
                    authors=r.authors_json or [],
                    abstract=r.abstract,
                    doi=r.doi,
                    url=r.url,
                    published_date=r.published_date,
                    journal=r.journal,
                    citation_count=r.citation_count,
                    source_database=r.source_database,
                    is_duplicate=r.is_duplicate,
                    screening_decision=r.screening_decision,
                    exclusion_reason=r.exclusion_reason,
                    manually_reviewed=r.manually_reviewed,
                )
                for r in rows
            ]
            return PaperListResponse(papers=papers, total=len(papers))
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback
    review = _review_store.get(review_id)
    if review is None or review["user_id"] != str(user.user_id):
        raise HTTPException(status_code=404, detail="Review not found")

    all_papers = _review_papers_store.get(review_id, [])
    if decision:
        all_papers = [p for p in all_papers if p.get("screening_decision") == decision]
    papers = [_paper_to_response(p) for p in all_papers if not p.get("is_duplicate")]
    return PaperListResponse(papers=papers, total=len(papers))


@router.patch("/reviews/{review_id}/papers/{paper_id}", response_model=PaperResponse)
async def update_paper_decision(
    review_id: str,
    paper_id: str,
    body: PaperDecisionRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> PaperResponse:
    """Manual screening override for a paper."""
    # Try DB
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.review_repository import ReviewRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ReviewRepository(db)
            review = await repo.get(uuid.UUID(review_id))
            if review is None or review.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Review not found")

            row = await repo.update_paper_decision(
                uuid.UUID(paper_id), body.decision, body.reason
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Paper not found")
            await db.commit()
            return PaperResponse(
                id=str(row.id),
                title=row.title,
                authors=row.authors_json or [],
                abstract=row.abstract,
                doi=row.doi,
                url=row.url,
                published_date=row.published_date,
                journal=row.journal,
                citation_count=row.citation_count,
                source_database=row.source_database,
                is_duplicate=row.is_duplicate,
                screening_decision=row.screening_decision,
                exclusion_reason=row.exclusion_reason,
                manually_reviewed=row.manually_reviewed,
            )
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback
    review_data = _review_store.get(review_id)
    papers = _review_papers_store.get(review_id, [])
    for p in papers:
        if p.get("id") == paper_id:
            original_decision = p.get("screening_decision", "uncertain")
            original_confidence = p.get("screening_confidence", 0.0)
            p["screening_decision"] = body.decision
            p["manually_reviewed"] = True
            if body.reason:
                p["exclusion_reason"] = body.reason

            # Record feedback for the learning loop
            _feedback_store.record_override(
                user_id=str(user.user_id),
                review_id=review_id,
                paper_title=p.get("title", ""),
                paper_abstract=p.get("abstract", ""),
                original_decision=original_decision,
                original_confidence=original_confidence,
                user_decision=body.decision,
                user_reason=body.reason,
                research_question=review_data.get("research_question", "") if review_data else "",
                inclusion_criteria=review_data.get("inclusion_criteria", []) if review_data else [],
                exclusion_criteria=review_data.get("exclusion_criteria", []) if review_data else [],
                paper_doi=p.get("doi"),
            )

            return _paper_to_response(p)
    raise HTTPException(status_code=404, detail="Paper not found")


@router.post("/reviews/{review_id}/papers/bulk-decide")
async def bulk_decide(
    review_id: str,
    body: BulkDecisionRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, int]:
    """Bulk manual decisions for papers."""
    updated = 0
    for item in body.decisions:
        paper_id = item.get("paper_id", "")
        decision = item.get("decision", "")
        reason = item.get("reason")
        if decision not in ("include", "exclude"):
            continue

        # Try DB
        try:
            from evidentia.db.engine import _get_session_factory
            from evidentia.db.review_repository import ReviewRepository

            factory = _get_session_factory()
            async with factory() as db:
                repo = ReviewRepository(db)
                row = await repo.update_paper_decision(
                    uuid.UUID(paper_id), decision, reason
                )
                if row:
                    await db.commit()
                    updated += 1
                continue
        except Exception:
            pass

        # Fallback
        papers = _review_papers_store.get(review_id, [])
        for p in papers:
            if p.get("id") == paper_id:
                p["screening_decision"] = decision
                p["manually_reviewed"] = True
                if reason:
                    p["exclusion_reason"] = reason
                updated += 1
                break

    return {"updated": updated}


@router.post("/reviews/{review_id}/export")
async def export_review(
    review_id: str,
    body: ReviewExportRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> PlainTextResponse:
    """Export review results."""
    papers: list[PaperRecord] = []

    # Try DB
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.review_repository import ReviewRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ReviewRepository(db)
            review = await repo.get(uuid.UUID(review_id))
            if review is None or review.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Review not found")
            rows = await repo.get_papers(
                uuid.UUID(review_id), include_duplicates=False
            )
            papers = [
                PaperRecord(
                    title=r.title,
                    authors=r.authors_json or [],
                    abstract=r.abstract,
                    doi=r.doi,
                    url=r.url,
                    published_date=r.published_date,
                    journal=r.journal,
                    citation_count=r.citation_count,
                    source_database=r.source_database,
                    source_id=r.source_id,
                    is_duplicate=r.is_duplicate,
                    screening_decision=r.screening_decision,
                    exclusion_reason=r.exclusion_reason,
                    screening_confidence=r.screening_confidence,
                )
                for r in rows
            ]
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback
    if not papers:
        review = _review_store.get(review_id)
        if review is None or review["user_id"] != str(user.user_id):
            raise HTTPException(status_code=404, detail="Review not found")
        raw_papers = _review_papers_store.get(review_id, [])
        papers = [
            PaperRecord(
                title=p.get("title", ""),
                authors=p.get("authors") or [],
                abstract=p.get("abstract"),
                doi=p.get("doi"),
                url=p.get("url"),
                published_date=p.get("published_date"),
                source_database=p.get("source_database", ""),
                is_duplicate=p.get("is_duplicate", False),
                screening_decision=p.get("screening_decision"),
                exclusion_reason=p.get("exclusion_reason"),
            )
            for p in raw_papers
        ]

    exporter = ReviewExporter()
    content_type = "text/plain"
    if body.format == "csv":
        content = exporter.to_csv(papers, include_excluded=body.include_excluded)
        content_type = "text/csv"
    elif body.format == "bibtex":
        content = exporter.to_bibtex(papers)
    elif body.format == "ris":
        content = exporter.to_ris(papers)
    else:
        content = exporter.to_csv(papers, include_excluded=body.include_excluded)

    return PlainTextResponse(content=content, media_type=content_type)


@router.get("/reviews/{review_id}/prisma", response_model=PRISMAFlowResponse)
async def get_prisma_data(
    review_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> PRISMAFlowResponse:
    """Get PRISMA flow diagram data."""
    # Try DB
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.review_repository import ReviewRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ReviewRepository(db)
            review = await repo.get(uuid.UUID(review_id))
            if review is None or review.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Review not found")
            return PRISMAFlowResponse(
                databases_searched=review.databases or [],
                total_identified=review.total_identified,
                duplicates_removed=review.total_duplicates,
                records_screened=review.total_screened,
                excluded_at_screening=review.total_excluded_screening,
                included_count=review.total_included,
                uncertain_count=review.total_uncertain,
            )
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback
    review = _review_store.get(review_id)
    if review is None or review["user_id"] != str(user.user_id):
        raise HTTPException(status_code=404, detail="Review not found")
    prisma = review.get("prisma", {})
    return PRISMAFlowResponse(**prisma) if prisma else PRISMAFlowResponse()


@router.get("/feedback/stats")
async def get_feedback_stats(
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, Any]:
    """Get aggregate feedback statistics — measures screening accuracy."""
    stats = _feedback_store.get_stats()
    return stats.model_dump()


@router.get("/feedback/training-pairs")
async def get_training_pairs(
    limit: int = 1000,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, Any]:
    """Export feedback as training pairs for model fine-tuning."""
    pairs = _feedback_store.get_training_pairs(limit=limit)
    return {"pairs": pairs, "total": len(pairs)}
