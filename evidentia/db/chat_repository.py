"""Chat repository — persist and query chat messages."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from evidentia.db.chat_models import ChatMessageRow


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_message(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        user_email: str,
        content: str,
        ref_type: str | None = None,
        ref_id: str | None = None,
    ) -> ChatMessageRow:
        msg = ChatMessageRow(
            project_id=project_id,
            user_id=user_id,
            user_email=user_email,
            content=content,
            ref_type=ref_type,
            ref_id=ref_id,
        )
        self._session.add(msg)
        await self._session.flush()
        return msg

    async def get_messages(
        self,
        project_id: uuid.UUID,
        limit: int = 100,
        before_id: uuid.UUID | None = None,
    ) -> list[ChatMessageRow]:
        stmt = (
            select(ChatMessageRow)
            .where(ChatMessageRow.project_id == project_id)
            .order_by(ChatMessageRow.created_at.desc())
            .limit(limit)
        )
        if before_id is not None:
            sub = select(ChatMessageRow.created_at).where(ChatMessageRow.id == before_id)
            stmt = stmt.where(ChatMessageRow.created_at < sub.scalar_subquery())
        result = await self._session.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()  # oldest first
        return messages

    async def delete_message(self, message_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(ChatMessageRow).where(
                ChatMessageRow.id == message_id,
                ChatMessageRow.user_id == user_id,
            )
        )
        return result.rowcount > 0  # type: ignore[return-value]
