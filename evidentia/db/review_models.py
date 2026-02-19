"""SQLAlchemy ORM models for systematic literature reviews."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidentia.db.models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class SystematicReviewRow(Base):
    __tablename__ = "systematic_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)

    # Configuration
    research_question: Mapped[str] = mapped_column(Text, nullable=False)
    search_query: Mapped[str] = mapped_column(Text, default="")
    inclusion_criteria: Mapped[list] = mapped_column(JSON, default=list)
    exclusion_criteria: Mapped[list] = mapped_column(JSON, default=list)
    databases: Mapped[list] = mapped_column(JSON, default=list)

    # PRISMA flow counts
    total_identified: Mapped[int] = mapped_column(Integer, default=0)
    total_duplicates: Mapped[int] = mapped_column(Integer, default=0)
    total_screened: Mapped[int] = mapped_column(Integer, default=0)
    total_excluded_screening: Mapped[int] = mapped_column(Integer, default=0)
    total_included: Mapped[int] = mapped_column(Integer, default=0)
    total_uncertain: Mapped[int] = mapped_column(Integer, default=0)

    # State
    status: Mapped[str] = mapped_column(String(20), default="pending")

    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    elapsed_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    papers: Mapped[list[ReviewPaperRow]] = relationship(
        back_populates="review", lazy="selectin", cascade="all, delete-orphan"
    )


class ReviewPaperRow(Base):
    __tablename__ = "review_papers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("systematic_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Paper metadata
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    journal: Mapped[str | None] = mapped_column(String(500), nullable=True)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Source tracking
    source_database: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Deduplication
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Screening
    screening_decision: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    screening_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    manually_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    review: Mapped[SystematicReviewRow] = relationship(back_populates="papers")
