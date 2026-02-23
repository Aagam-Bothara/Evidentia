"""PRISMA 2020 flow diagram export endpoints — SVG and PNG downloads."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger
from evidentia.core.prisma_diagram import PRISMAData, generate_prisma_png_bytes, generate_prisma_svg

logger = get_logger(__name__)

router = APIRouter()


async def _load_prisma_data(review_id: str, user: AuthenticatedUser) -> PRISMAData:
    """Load review data and build a :class:`PRISMAData` instance.

    Tries the database first, then falls back to the in-memory store used by
    the reviews route.
    """
    # ── Try DB ──────────────────────────────────────────────────────
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.review_repository import ReviewRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ReviewRepository(db)
            review = await repo.get(uuid.UUID(review_id))
            if review is None or review.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Review not found")

            # Compute full-text assessed: screened minus excluded at screening
            full_text_assessed = max(review.total_screened - review.total_excluded_screening, 0)
            # Full-text excluded: assessed minus included minus uncertain
            full_text_excluded = max(full_text_assessed - review.total_included - review.total_uncertain, 0)

            return PRISMAData(
                databases_searched=review.databases or [],
                total_identified=review.total_identified,
                other_sources=0,
                duplicates_removed=review.total_duplicates,
                records_screened=review.total_screened,
                records_excluded=review.total_excluded_screening,
                full_text_assessed=full_text_assessed,
                full_text_excluded=full_text_excluded,
                exclusion_reasons=None,
                studies_included=review.total_included,
                uncertain_count=review.total_uncertain,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("prisma_db_fallback", error=str(exc))

    # ── Fallback: in-memory store ───────────────────────────────────
    try:
        from evidentia.api.routes.reviews import _review_store
    except ImportError:
        raise HTTPException(status_code=404, detail="Review not found")  # noqa: B904

    review_data = _review_store.get(review_id)
    if review_data is None or review_data.get("user_id") != str(user.user_id):
        raise HTTPException(status_code=404, detail="Review not found")

    prisma = review_data.get("prisma", {})
    total_identified = prisma.get("total_identified", 0)
    duplicates_removed = prisma.get("duplicates_removed", 0)
    records_screened = prisma.get("records_screened", 0)
    records_excluded = prisma.get("excluded_at_screening", 0)
    included = prisma.get("included_count", 0)
    uncertain = prisma.get("uncertain_count", 0)
    full_text_assessed = max(records_screened - records_excluded, 0)
    full_text_excluded = max(full_text_assessed - included - uncertain, 0)

    return PRISMAData(
        databases_searched=prisma.get("databases_searched", review_data.get("databases", [])),
        total_identified=total_identified,
        other_sources=0,
        duplicates_removed=duplicates_removed,
        records_screened=records_screened,
        records_excluded=records_excluded,
        full_text_assessed=full_text_assessed,
        full_text_excluded=full_text_excluded,
        exclusion_reasons=prisma.get("exclusion_reasons"),
        studies_included=included,
        uncertain_count=uncertain,
    )


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/reviews/{review_id}/prisma/svg")
async def get_prisma_svg(
    review_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> Response:
    """Download the PRISMA 2020 flow diagram as an SVG file."""
    data = await _load_prisma_data(review_id, user)
    svg_content = generate_prisma_svg(data)
    logger.info("prisma_svg_exported", review_id=review_id)
    return Response(
        content=svg_content,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": f'attachment; filename="prisma-{review_id}.svg"',
        },
    )


@router.get("/reviews/{review_id}/prisma/png")
async def get_prisma_png(
    review_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> Response:
    """Download the PRISMA 2020 flow diagram as a PNG file.

    Requires *cairosvg* to be installed.  Returns HTTP 501 if unavailable.
    """
    data = await _load_prisma_data(review_id, user)
    png_bytes = generate_prisma_png_bytes(data)
    if png_bytes is None:
        raise HTTPException(
            status_code=501,
            detail=("PNG export requires the 'cairosvg' package. Install it with: pip install cairosvg"),
        )
    logger.info("prisma_png_exported", review_id=review_id)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="prisma-{review_id}.png"',
        },
    )
