"""SQLAlchemy ORM models — the persistent data layer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# ── Users ───────────────────────────────────────────────────────────


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    runs: Mapped[list[RunRow]] = relationship(back_populates="user", lazy="selectin")


# ── Projects ─────────────────────────────────────────────────────────


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    team_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    runs: Mapped[list[RunRow]] = relationship(back_populates="project", lazy="selectin")


# ── Runs ────────────────────────────────────────────────────────────


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("projects.id"),
        nullable=True,
        index=True,
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    total_tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    total_iterations: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[UserRow] = relationship(back_populates="runs")
    project: Mapped[ProjectRow | None] = relationship(back_populates="runs")
    claims: Mapped[list[ClaimRow]] = relationship(back_populates="run", lazy="selectin", cascade="all, delete-orphan")


# ── Claims ──────────────────────────────────────────────────────────


class ClaimRow(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("runs.id"), nullable=False, index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    position: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped[RunRow] = relationship(back_populates="claims")
    citations: Mapped[list[CitationRow]] = relationship(
        back_populates="claim",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    evidence_spans: Mapped[list[EvidenceSpanRow]] = relationship(
        back_populates="claim",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


# ── Citations ───────────────────────────────────────────────────────


class CitationRow(Base):
    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("claims.id"), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    claim: Mapped[ClaimRow] = relationship(back_populates="citations")


# ── Evidence Spans ──────────────────────────────────────────────────


class EvidenceSpanRow(Base):
    __tablename__ = "evidence_spans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("claims.id"), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_conflicting: Mapped[bool] = mapped_column(Boolean, default=False)

    claim: Mapped[ClaimRow] = relationship(back_populates="evidence_spans")


# ── Documents ───────────────────────────────────────────────────────


class DocumentRow(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        nullable=True,
        index=True,
    )
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── PDF Uploads ─────────────────────────────────────────────────────


class PDFUploadRow(Base):
    __tablename__ = "pdf_uploads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    chunks: Mapped[list[PDFChunkRow]] = relationship(
        back_populates="pdf",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


# ── PDF Chunks ──────────────────────────────────────────────────────


class PDFChunkRow(Base):
    __tablename__ = "pdf_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    pdf_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("pdf_uploads.id"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # embedding column added by pgvector migration:
    # embedding: Mapped[...] = mapped_column(Vector(384), nullable=True)

    pdf: Mapped[PDFUploadRow] = relationship(back_populates="chunks")


# ── Annotations ────────────────────────────────────────────────────


class AnnotationRow(Base):
    __tablename__ = "annotations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("runs.id"),
        nullable=True,
        index=True,
    )
    claim_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    annotation_type: Mapped[str] = mapped_column(String(20), default="note")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Research Memory ────────────────────────────────────────────────


class ResearchMemoryRow(Base):
    __tablename__ = "research_memory"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    topic_summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    query_count: Mapped[int] = mapped_column(Integer, default=1)
    last_accessed: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Teams ──────────────────────────────────────────────────────────


class TeamRow(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    members: Mapped[list[TeamMemberRow]] = relationship(
        back_populates="team",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class TeamMemberRow(Base):
    __tablename__ = "team_members"

    team_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("teams.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    team: Mapped[TeamRow] = relationship(back_populates="members")


# ── User Credentials (BYO-API vault) ─────────────────────────────


class UserCredentialRow(Base):
    __tablename__ = "user_credentials"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (UniqueConstraint("user_id", "service", name="uq_user_service"),)
