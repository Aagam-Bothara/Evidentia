"""Repository for systematic review persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from evidentia.db.review_models import ReviewPaperRow, SystematicReviewRow
from evidentia.review.models import PaperRecord, PRISMAFlowData


class ReviewRepository:
    """Async repository for systematic reviews."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: uuid.UUID,
        research_question: str,
        inclusion_criteria: list[str],
        exclusion_criteria: list[str],
        databases: list[str],
        project_id: uuid.UUID | None = None,
    ) -> SystematicReviewRow:
        row = SystematicReviewRow(
            user_id=user_id,
            project_id=project_id,
            research_question=research_question,
            search_query=research_question,
            inclusion_criteria=inclusion_criteria,
            exclusion_criteria=exclusion_criteria,
            databases=databases,
            status="pending",
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, review_id: uuid.UUID) -> SystematicReviewRow | None:
        return await self._session.get(SystematicReviewRow, review_id)

    async def list_by_user(self, user_id: uuid.UUID) -> list[SystematicReviewRow]:
        result = await self._session.execute(
            select(SystematicReviewRow)
            .where(SystematicReviewRow.user_id == user_id)
            .order_by(SystematicReviewRow.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, review_id: uuid.UUID) -> bool:
        row = await self.get(review_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def save_papers(
        self, review_id: uuid.UUID, papers: list[PaperRecord]
    ) -> None:
        """Bulk-save papers from a completed review."""
        for paper in papers:
            row = ReviewPaperRow(
                review_id=review_id,
                title=paper.title,
                authors_json=paper.authors,
                abstract=paper.abstract,
                doi=paper.doi,
                url=paper.url,
                published_date=paper.published_date,
                journal=paper.journal,
                citation_count=paper.citation_count,
                source_database=paper.source_database,
                source_id=paper.source_id,
                is_duplicate=paper.is_duplicate,
                screening_decision=paper.screening_decision,
                exclusion_reason=paper.exclusion_reason,
                screening_confidence=paper.screening_confidence,
            )
            self._session.add(row)
        await self._session.flush()

    async def get_papers(
        self,
        review_id: uuid.UUID,
        decision: str | None = None,
        include_duplicates: bool = False,
    ) -> list[ReviewPaperRow]:
        """Get papers with optional filtering."""
        stmt = select(ReviewPaperRow).where(ReviewPaperRow.review_id == review_id)

        if decision:
            stmt = stmt.where(ReviewPaperRow.screening_decision == decision)
        if not include_duplicates:
            stmt = stmt.where(ReviewPaperRow.is_duplicate == False)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_paper_decision(
        self,
        paper_id: uuid.UUID,
        decision: str,
        reason: str | None = None,
    ) -> ReviewPaperRow | None:
        """Manual screening override."""
        row = await self._session.get(ReviewPaperRow, paper_id)
        if row is None:
            return None
        row.manual_decision = decision
        row.manually_reviewed = True
        row.screening_decision = decision
        if reason:
            row.exclusion_reason = reason
        await self._session.flush()
        return row

    async def update_review_status(
        self,
        review_id: uuid.UUID,
        status: str,
        prisma: PRISMAFlowData | None = None,
        elapsed_seconds: float | None = None,
    ) -> None:
        """Update review status and PRISMA counts."""
        row = await self.get(review_id)
        if row is None:
            return
        row.status = status
        if prisma:
            row.total_identified = prisma.total_identified
            row.total_duplicates = prisma.duplicates_removed
            row.total_screened = prisma.records_screened
            row.total_excluded_screening = prisma.excluded_at_screening
            row.total_included = prisma.included_count
            row.total_uncertain = prisma.uncertain_count
        if elapsed_seconds is not None:
            row.elapsed_seconds = elapsed_seconds
        if status == "completed":
            row.completed_at = datetime.now(timezone.utc)
        await self._session.flush()
