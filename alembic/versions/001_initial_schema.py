"""Initial schema — users, runs, claims, citations, evidence, documents, PDFs.

Revision ID: 001
Revises:
Create Date: 2026-02-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("api_key", sa.String(64), unique=True, nullable=True, index=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("plan_json", JSON, nullable=True),
        sa.Column("evidence_summary_json", JSON, nullable=True),
        sa.Column("total_tool_calls", sa.Integer, server_default="0"),
        sa.Column("total_iterations", sa.Integer, server_default="0"),
        sa.Column("elapsed_seconds", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "claims",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False, index=True),
        sa.Column("statement", sa.Text, nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("position", sa.Integer, server_default="0"),
    )

    op.create_table(
        "citations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", UUID(as_uuid=True), sa.ForeignKey("claims.id"), nullable=False, index=True),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("authors_json", JSON, nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("doi", sa.String(255), nullable=True),
        sa.Column("published_date", sa.String(50), nullable=True),
    )

    op.create_table(
        "evidence_spans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", UUID(as_uuid=True), sa.ForeignKey("claims.id"), nullable=False, index=True),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("start_offset", sa.Integer, nullable=True),
        sa.Column("end_offset", sa.Integer, nullable=True),
        sa.Column("is_conflicting", sa.Boolean, server_default="false"),
    )

    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("content", sa.Text, server_default=""),
        sa.Column("content_hash", sa.String(64), unique=True, nullable=True, index=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("doi", sa.String(255), nullable=True),
        sa.Column("metadata_json", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "pdf_uploads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("page_count", sa.Integer, server_default="0"),
        sa.Column("chunk_count", sa.Integer, server_default="0"),
        sa.Column("text", sa.Text, server_default=""),
        sa.Column("metadata_json", JSON, nullable=True),
        sa.Column("file_path", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "pdf_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pdf_id", UUID(as_uuid=True), sa.ForeignKey("pdf_uploads.id"), nullable=False, index=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        # pgvector column for embeddings
        # sa.Column("embedding", Vector(384), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("pdf_chunks")
    op.drop_table("pdf_uploads")
    op.drop_table("documents")
    op.drop_table("evidence_spans")
    op.drop_table("citations")
    op.drop_table("claims")
    op.drop_table("runs")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
