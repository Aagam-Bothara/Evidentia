"""Add systematic_reviews and review_papers tables.

Revision ID: 005
Revises: 004
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "systematic_reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("research_question", sa.Text, nullable=False),
        sa.Column("search_query", sa.Text, server_default=""),
        sa.Column("inclusion_criteria", JSON, server_default="[]"),
        sa.Column("exclusion_criteria", JSON, server_default="[]"),
        sa.Column("databases", JSON, server_default="[]"),
        sa.Column("total_identified", sa.Integer, server_default="0"),
        sa.Column("total_duplicates", sa.Integer, server_default="0"),
        sa.Column("total_screened", sa.Integer, server_default="0"),
        sa.Column("total_excluded_screening", sa.Integer, server_default="0"),
        sa.Column("total_included", sa.Integer, server_default="0"),
        sa.Column("total_uncertain", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elapsed_seconds", sa.Float, nullable=True),
    )
    op.create_index("idx_reviews_user_id", "systematic_reviews", ["user_id"])

    op.create_table(
        "review_papers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "review_id",
            UUID(as_uuid=True),
            sa.ForeignKey("systematic_reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("authors_json", JSON, nullable=True),
        sa.Column("abstract", sa.Text, nullable=True),
        sa.Column("doi", sa.String(255), nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("published_date", sa.String(50), nullable=True),
        sa.Column("journal", sa.String(500), nullable=True),
        sa.Column("citation_count", sa.Integer, nullable=True),
        sa.Column("source_database", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("is_duplicate", sa.Boolean, server_default="false"),
        sa.Column("duplicate_of_id", UUID(as_uuid=True), nullable=True),
        sa.Column("screening_decision", sa.String(20), nullable=True),
        sa.Column("exclusion_reason", sa.Text, nullable=True),
        sa.Column("screening_confidence", sa.Float, nullable=True),
        sa.Column("manually_reviewed", sa.Boolean, server_default="false"),
        sa.Column("manual_decision", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_review_papers_review_id", "review_papers", ["review_id"])
    op.create_index("idx_review_papers_doi", "review_papers", ["doi"])
    op.create_index("idx_review_papers_decision", "review_papers", ["screening_decision"])


def downgrade() -> None:
    op.drop_index("idx_review_papers_decision", "review_papers")
    op.drop_index("idx_review_papers_doi", "review_papers")
    op.drop_index("idx_review_papers_review_id", "review_papers")
    op.drop_table("review_papers")
    op.drop_index("idx_reviews_user_id", "systematic_reviews")
    op.drop_table("systematic_reviews")
