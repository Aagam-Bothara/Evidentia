"""Add chat_messages table for project-scoped collaboration.

Revision ID: 006
Revises: 005
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("user_email", sa.String(255), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("ref_type", sa.String(20), nullable=True),
        sa.Column("ref_id", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_chat_project", "chat_messages", ["project_id"])
    op.create_index(
        "idx_chat_project_time",
        "chat_messages",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_chat_project_time")
    op.drop_index("idx_chat_project")
    op.drop_table("chat_messages")
