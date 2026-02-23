"""Chat REST endpoints — history retrieval and message deletion."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ── Response models ──────────────────────────────────────────────────


class ChatMessageResponse(BaseModel):
    id: str
    project_id: str
    user_id: str
    user_email: str
    content: str
    ref_type: str | None = None
    ref_id: str | None = None
    created_at: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse]
    has_more: bool


# ── In-memory fallback ───────────────────────────────────────────────

_chat_store: dict[str, list[dict]] = {}


def _get_inmemory_messages(project_id: str, limit: int = 50) -> list[dict]:
    messages = _chat_store.get(project_id, [])
    return messages[-limit:]


# ── Endpoints ────────────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/chat",
    response_model=ChatHistoryResponse,
)
async def get_chat_history(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_auth),
) -> ChatHistoryResponse:
    """Get chat history for a project."""
    try:
        from evidentia.db.chat_repository import ChatRepository
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import ProjectRepository

        factory = _get_session_factory()
        async with factory() as db:
            # Verify access
            proj_repo = ProjectRepository(db)
            project = await proj_repo.get(uuid.UUID(project_id))
            if project is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found",
                )
            if project.user_id != user.user_id and not project.team_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied",
                )

            chat_repo = ChatRepository(db)
            before_uuid = uuid.UUID(before) if before else None
            messages = await chat_repo.get_messages(
                uuid.UUID(project_id),
                limit=limit + 1,
                before_id=before_uuid,
            )
            has_more = len(messages) > limit
            if has_more:
                messages = messages[1:]  # drop oldest

            return ChatHistoryResponse(
                messages=[
                    ChatMessageResponse(
                        id=str(m.id),
                        project_id=str(m.project_id),
                        user_id=str(m.user_id),
                        user_email=m.user_email,
                        content=m.content,
                        ref_type=m.ref_type,
                        ref_id=m.ref_id,
                        created_at=m.created_at.isoformat(),
                    )
                    for m in messages
                ],
                has_more=has_more,
            )
    except HTTPException:
        raise
    except Exception:
        # In-memory fallback
        msgs = _get_inmemory_messages(project_id, limit)
        return ChatHistoryResponse(
            messages=[ChatMessageResponse(**m) for m in msgs],
            has_more=False,
        )


@router.delete("/projects/{project_id}/chat/{message_id}")
async def delete_chat_message(
    project_id: str,
    message_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, str]:
    """Delete own chat message."""
    try:
        from evidentia.db.chat_repository import ChatRepository
        from evidentia.db.engine import _get_session_factory

        factory = _get_session_factory()
        async with factory() as db:
            chat_repo = ChatRepository(db)
            deleted = await chat_repo.delete_message(uuid.UUID(message_id), user.user_id)
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Message not found or not yours",
                )
            await db.commit()
            return {"status": "deleted", "message_id": message_id}
    except HTTPException:
        raise
    except Exception:
        # In-memory fallback
        msgs = _chat_store.get(project_id, [])
        for i, m in enumerate(msgs):
            if m["id"] == message_id and m["user_id"] == str(user.user_id):
                msgs.pop(i)
                return {"status": "deleted", "message_id": message_id}
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found or not yours",
        ) from None
