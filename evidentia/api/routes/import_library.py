"""Bibliography import endpoints — BibTeX / RIS file upload and parsing."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.bibliography import ImportedPaper, detect_format, parse_bibliography
from evidentia.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Maximum upload size: 10 MB (bibliography files are text, should be small)
_MAX_FILE_SIZE = 10 * 1024 * 1024
_ALLOWED_EXTENSIONS = {".bib", ".ris", ".txt", ".enw", ".nbib"}


# ── Response models ─────────────────────────────────────────────────


class ImportedPaperResponse(BaseModel):
    """Single paper as returned by the import endpoint."""

    title: str
    authors: list[str] = Field(default_factory=list)
    year: str | None = None
    doi: str | None = None
    url: str | None = None
    journal: str | None = None
    abstract: str | None = None
    volume: str | None = None
    pages: str | None = None
    source_format: str = ""


class BibliographyImportResponse(BaseModel):
    """Response from the bibliography import endpoint."""

    papers: list[ImportedPaperResponse]
    total: int = 0
    duplicates_skipped: int = 0
    added_to_review: int = 0
    format: str = ""
    review_id: str | None = None


# ── Helpers ─────────────────────────────────────────────────────────


def _paper_to_response(paper: ImportedPaper) -> ImportedPaperResponse:
    return ImportedPaperResponse(
        title=paper.title,
        authors=paper.authors,
        year=paper.year,
        doi=paper.doi,
        url=paper.url,
        journal=paper.journal,
        abstract=paper.abstract,
        volume=paper.volume,
        pages=paper.pages,
        source_format=paper.source_format,
    )


def _paper_to_review_dict(paper: ImportedPaper) -> dict[str, Any]:
    """Convert an ImportedPaper to the dict format used in _review_papers_store."""
    source_db = f"{paper.source_format}_import"
    return {
        "id": uuid.uuid4().hex[:12],
        "title": paper.title,
        "authors": paper.authors,
        "authors_json": paper.authors,
        "abstract": paper.abstract,
        "doi": paper.doi,
        "url": paper.url,
        "published_date": paper.year,
        "journal": paper.journal,
        "citation_count": None,
        "source_database": source_db,
        "source_id": None,
        "is_duplicate": False,
        "screening_decision": None,
        "exclusion_reason": None,
        "screening_confidence": None,
        "manually_reviewed": False,
        "manual_decision": None,
    }


def _find_duplicates(
    existing: list[dict[str, Any]],
    incoming: list[ImportedPaper],
) -> tuple[list[ImportedPaper], int]:
    """Filter out papers that already exist in the review (by DOI or title).

    Returns:
        Tuple of (non-duplicate papers, count of duplicates skipped).
    """
    existing_dois: set[str] = set()
    existing_titles: set[str] = set()
    for p in existing:
        doi = p.get("doi")
        if doi:
            existing_dois.add(doi.strip().lower())
        title = p.get("title", "")
        if title:
            existing_titles.add(title.strip().lower())

    unique: list[ImportedPaper] = []
    skipped = 0
    for paper in incoming:
        is_dup = (
            paper.doi is not None and paper.doi.strip().lower() in existing_dois
        ) or paper.title.strip().lower() in existing_titles

        if is_dup:
            skipped += 1
        else:
            unique.append(paper)
            # Add to sets so we also dedup within the incoming batch
            if paper.doi:
                existing_dois.add(paper.doi.strip().lower())
            existing_titles.add(paper.title.strip().lower())

    return unique, skipped


# ── Endpoint ────────────────────────────────────────────────────────


@router.post("/import/bibliography", response_model=BibliographyImportResponse)
async def import_bibliography(
    file: UploadFile = File(...),
    review_id: str | None = Query(None, description="Optional review ID to add papers to"),
    user: AuthenticatedUser = Depends(require_auth),
) -> BibliographyImportResponse:
    """Upload a .bib or .ris file, parse it, and return parsed papers.

    If ``review_id`` is provided, the papers are also added to that
    systematic review (with duplicate detection).
    """
    # ── Validate file ───────────────────────────────────────────
    filename = (file.filename or "").lower()
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1]
    if ext and ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(f"Unsupported file extension '{ext}'. Accepted: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"),
        )

    content_bytes = await file.read()
    if len(content_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum {_MAX_FILE_SIZE // (1024 * 1024)}MB.",
        )

    # ── Decode text ─────────────────────────────────────────────
    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content_bytes.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail="Unable to decode file. Please use UTF-8 or Latin-1 encoding.",
            ) from exc

    if not text.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # ── Detect format and parse ─────────────────────────────────
    try:
        fmt = detect_format(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        papers = parse_bibliography(text)
    except Exception as exc:
        logger.error("bibliography_parse_failed", error=str(exc), filename=file.filename)
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse bibliography file: {exc}",
        ) from exc

    if not papers:
        raise HTTPException(
            status_code=422,
            detail="No papers found in the uploaded file. Check the file format.",
        )

    logger.info(
        "bibliography_uploaded",
        filename=file.filename,
        format=fmt,
        papers_parsed=len(papers),
        review_id=review_id,
        user_id=str(user.user_id),
    )

    # ── Optionally add to a review ──────────────────────────────
    duplicates_skipped = 0
    added_to_review = 0

    if review_id is not None:
        added_to_review, duplicates_skipped = await _add_papers_to_review(
            review_id=review_id,
            user=user,
            papers=papers,
        )

    return BibliographyImportResponse(
        papers=[_paper_to_response(p) for p in papers],
        total=len(papers),
        duplicates_skipped=duplicates_skipped,
        added_to_review=added_to_review,
        format=fmt,
        review_id=review_id,
    )


async def _add_papers_to_review(
    review_id: str,
    user: AuthenticatedUser,
    papers: list[ImportedPaper],
) -> tuple[int, int]:
    """Add parsed papers to a review, returning (added_count, duplicates_skipped).

    Tries the DB path first, then falls back to in-memory storage.
    """
    # ── Try DB ──────────────────────────────────────────────────
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.review_models import ReviewPaperRow
        from evidentia.db.review_repository import ReviewRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ReviewRepository(db)
            review = await repo.get(uuid.UUID(review_id))
            if review is None or review.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Review not found")

            # Fetch existing papers for duplicate detection
            existing_rows = await repo.get_papers(uuid.UUID(review_id), include_duplicates=True)
            existing_dicts = [{"doi": r.doi, "title": r.title} for r in existing_rows]
            unique_papers, skipped = _find_duplicates(existing_dicts, papers)

            # Bulk insert unique papers
            for paper in unique_papers:
                source_db = f"{paper.source_format}_import"
                row = ReviewPaperRow(
                    review_id=uuid.UUID(review_id),
                    title=paper.title,
                    authors_json=paper.authors,
                    abstract=paper.abstract,
                    doi=paper.doi,
                    url=paper.url,
                    published_date=paper.year,
                    journal=paper.journal,
                    source_database=source_db,
                    is_duplicate=False,
                )
                db.add(row)

            await db.flush()
            await db.commit()

            logger.info(
                "bibliography_added_to_review_db",
                review_id=review_id,
                added=len(unique_papers),
                duplicates_skipped=skipped,
            )
            return len(unique_papers), skipped

    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("bibliography_db_save_failed", error=str(exc))

    # ── Fallback: in-memory store ───────────────────────────────
    from evidentia.api.routes.reviews import _review_papers_store, _review_store

    review = _review_store.get(review_id)
    if review is None or review.get("user_id") != str(user.user_id):
        raise HTTPException(status_code=404, detail="Review not found")

    existing = _review_papers_store.get(review_id, [])
    unique_papers, skipped = _find_duplicates(existing, papers)

    new_dicts = [_paper_to_review_dict(p) for p in unique_papers]
    _review_papers_store.setdefault(review_id, []).extend(new_dicts)

    logger.info(
        "bibliography_added_to_review_memory",
        review_id=review_id,
        added=len(new_dicts),
        duplicates_skipped=skipped,
    )
    return len(new_dicts), skipped
