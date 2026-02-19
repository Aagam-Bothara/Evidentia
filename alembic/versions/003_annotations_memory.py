"""Add annotations and research_memory tables.

Revision ID: 003
Revises: 002
Create Date: 2026-02-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "annotations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("claim_id", sa.String(255), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("annotation_type", sa.String(20), server_default="note"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_annotations_run_id", "annotations", ["run_id"])

    op.create_table(
        "research_memory",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("topic_summary", sa.Text, nullable=False),
        sa.Column("source_ids_json", JSON, server_default="[]"),
        sa.Column("query_count", sa.Integer, server_default="1"),
        sa.Column("last_accessed", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_memory_user_id", "research_memory", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_memory_user_id", "research_memory")
    op.drop_table("research_memory")
    op.drop_index("idx_annotations_run_id", "annotations")
    op.drop_table("annotations")
