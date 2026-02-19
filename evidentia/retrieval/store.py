"""Document store — persists and retrieves source documents."""

from __future__ import annotations

import hashlib
from typing import Any

from evidentia.core.logging import get_logger
from evidentia.core.models import Source, SourceType

logger = get_logger(__name__)


class DocumentStore:
    """Stores and deduplicates source documents.

    In production this backs onto PostgreSQL. This in-memory implementation
    serves as the interface contract and is used during development/testing.
    """

    def __init__(self) -> None:
        self._documents: dict[str, Source] = {}
        self._hash_index: dict[str, str] = {}  # content_hash -> doc_id

    async def add(self, source: Source) -> Source:
        """Add a document, deduplicating by content hash."""
        content_hash = hashlib.sha256(source.content.encode()).hexdigest()

        # Deduplicate
        if content_hash in self._hash_index:
            existing_id = self._hash_index[content_hash]
            logger.info("document_deduplicated", existing_id=existing_id)
            return self._documents[existing_id]

        source.content_hash = content_hash
        self._documents[source.id] = source
        self._hash_index[content_hash] = source.id
        logger.info("document_stored", doc_id=source.id, source_type=source.source_type)
        return source

    async def get(self, doc_id: str) -> Source | None:
        return self._documents.get(doc_id)

    async def list_all(self) -> list[Source]:
        return list(self._documents.values())

    async def delete(self, doc_id: str) -> bool:
        if doc := self._documents.pop(doc_id, None):
            if doc.content_hash:
                self._hash_index.pop(doc.content_hash, None)
            return True
        return False
