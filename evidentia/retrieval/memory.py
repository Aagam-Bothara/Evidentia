"""Research Memory — learns from past sessions to improve future queries.

Stores topic summaries and source IDs after each completed run.
Before decomposition, checks for related past research to inject context.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from evidentia.core.logging import get_logger

logger = get_logger(__name__)

# In-memory fallback for when DB is unavailable
_memory_store: list[dict[str, Any]] = []


class ResearchMemoryService:
    """Manages research memory — records past research and finds related topics."""

    async def record_run(
        self,
        user_id: uuid.UUID,
        query: str,
        source_ids: list[str],
    ) -> None:
        """Save a completed run to research memory."""
        # Try DB first
        try:
            from evidentia.db.engine import _get_session_factory
            from evidentia.db.repositories import ResearchMemoryRepository

            factory = _get_session_factory()
            async with factory() as db:
                repo = ResearchMemoryRepository(db)
                await repo.record(
                    user_id=user_id,
                    topic_summary=query,
                    source_ids=source_ids,
                )
                await db.commit()
                logger.info("memory_recorded", user_id=str(user_id))
                return
        except Exception as exc:
            logger.warning("memory_db_record_failed", error=str(exc))

        # Fallback to in-memory
        _memory_store.append(
            {
                "user_id": str(user_id),
                "topic_summary": query,
                "source_ids": source_ids,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )

    async def find_related(
        self,
        user_id: uuid.UUID,
        query: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Find related past research for context injection.

        Returns list of {topic_summary, source_ids} dicts.
        """
        # Try DB first
        try:
            from evidentia.db.engine import _get_session_factory
            from evidentia.db.repositories import ResearchMemoryRepository

            factory = _get_session_factory()
            async with factory() as db:
                repo = ResearchMemoryRepository(db)
                memories = await repo.find_related(user_id, query, top_k)
                return [
                    {
                        "topic_summary": m.topic_summary,
                        "source_ids": m.source_ids_json or [],
                    }
                    for m in memories
                ]
        except Exception as exc:
            logger.warning("memory_db_find_failed", error=str(exc))

        # Fallback to in-memory keyword matching
        query_words = set(query.lower().split())
        scored = []
        for mem in _memory_store:
            if mem["user_id"] != str(user_id):
                continue
            summary_words = set(mem["topic_summary"].lower().split())
            overlap = len(query_words & summary_words)
            if overlap > 0:
                scored.append((overlap, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "topic_summary": m["topic_summary"],
                "source_ids": m["source_ids"],
            }
            for _, m in scored[:top_k]
        ]
