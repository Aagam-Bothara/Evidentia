"""Annotations endpoints — notes on runs and claims."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# In-memory fallback
_annotation_store: dict[str, list[dict[str, Any]]] = {}


class AnnotationCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    claim_id: str | None = None
    annotation_type: str = "note"


class AnnotationResponse(BaseModel):
    id: str
    text: str
    claim_id: str | None = None
    annotation_type: str = "note"
    created_at: str


class AnnotationListResponse(BaseModel):
    annotations: list[AnnotationResponse]


@router.post("/runs/{run_id}/annotations", response_model=AnnotationResponse)
async def create_annotation(
    run_id: str,
    body: AnnotationCreate,
    user: AuthenticatedUser = Depends(require_auth),
) -> AnnotationResponse:
    """Add an annotation (note, question, highlight) to a run or claim."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import AnnotationRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = AnnotationRepository(db)
            annotation = await repo.create(
                user_id=user.user_id,
                run_id=uuid.UUID(run_id),
                text=body.text,
                claim_id=body.claim_id,
                annotation_type=body.annotation_type,
            )
            await db.commit()
            return AnnotationResponse(
                id=str(annotation.id),
                text=annotation.text,
                claim_id=annotation.claim_id,
                annotation_type=annotation.annotation_type,
                created_at=annotation.created_at.isoformat(),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("annotation_db_create_failed", error=str(exc))

    # Fallback to in-memory
    ann_id = uuid.uuid4().hex[:12]
    now = datetime.now(UTC).isoformat()
    ann = {
        "id": ann_id,
        "text": body.text,
        "claim_id": body.claim_id,
        "annotation_type": body.annotation_type,
        "created_at": now,
    }
    _annotation_store.setdefault(run_id, []).append(ann)

    return AnnotationResponse(**ann)


@router.get("/runs/{run_id}/annotations", response_model=AnnotationListResponse)
async def list_annotations(
    run_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> AnnotationListResponse:
    """List annotations for a run."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import AnnotationRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = AnnotationRepository(db)
            annotations = await repo.list_by_run(uuid.UUID(run_id))
            return AnnotationListResponse(
                annotations=[
                    AnnotationResponse(
                        id=str(a.id),
                        text=a.text,
                        claim_id=a.claim_id,
                        annotation_type=a.annotation_type,
                        created_at=a.created_at.isoformat(),
                    )
                    for a in annotations
                ]
            )
    except Exception:
        pass

    # Fallback to in-memory
    return AnnotationListResponse(annotations=[AnnotationResponse(**a) for a in _annotation_store.get(run_id, [])])


@router.delete("/annotations/{annotation_id}")
async def delete_annotation(
    annotation_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, str]:
    """Delete an annotation."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import AnnotationRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = AnnotationRepository(db)
            deleted = await repo.delete(uuid.UUID(annotation_id))
            if deleted:
                await db.commit()
                return {"status": "deleted", "id": annotation_id}
    except Exception:
        pass

    # Fallback to in-memory
    for _run_id, ann_list in _annotation_store.items():
        for i, a in enumerate(ann_list):
            if a["id"] == annotation_id:
                ann_list.pop(i)
                return {"status": "deleted", "id": annotation_id}

    raise HTTPException(status_code=404, detail="Annotation not found")
