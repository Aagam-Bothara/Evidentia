"""Vector store — in-memory semantic search with cosine similarity."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field

from evidentia.core.logging import get_logger
from evidentia.core.models import Source
from evidentia.retrieval.embeddings import EmbeddingService

logger = get_logger(__name__)


class VectorSearchResult(BaseModel):
    """A single vector search result with similarity score."""

    doc_id: str
    title: str
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class _StoredVector(BaseModel):
    """Internal record pairing a document with its embedding."""

    doc_id: str
    title: str
    text: str
    vector: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorStore:
    """In-memory vector store with cosine similarity search.

    Uses sentence-transformers to generate embeddings and stores them
    in-memory for development and testing.  The interface is designed so
    that a future pgvector-backed implementation can be swapped in with
    minimal changes.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._embedder = EmbeddingService(model_name=model_name)
        self._vectors: list[_StoredVector] = []
        self._id_index: dict[str, int] = {}  # doc_id -> position in _vectors
        logger.info("vector_store_init", model_name=model_name)

    # ── Public API ────────────────────────────────────────────────────

    async def add_documents(self, documents: list[Source]) -> None:
        """Embed and store full Source documents.

        Each document's ``content`` field is embedded.  If a document with
        the same ``id`` already exists it is silently replaced.

        Args:
            documents: Source documents to embed and store.
        """
        if not documents:
            return

        texts = [doc.content for doc in documents]
        vectors = self._embedder.embed_batch(texts)

        for doc, vec in zip(documents, vectors, strict=False):
            stored = _StoredVector(
                doc_id=doc.id,
                title=doc.title,
                text=doc.content,
                vector=vec,
                metadata=doc.metadata,
            )
            self._upsert(stored)

        logger.info("documents_embedded", count=len(documents))

    async def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Add pre-chunked text (e.g. from PDF ingestion).

        Each chunk dict must contain at minimum ``doc_id`` and ``text``.
        Optional keys: ``title``, ``metadata``.

        Args:
            chunks: List of chunk dictionaries.
        """
        if not chunks:
            return

        texts = [c["text"] for c in chunks]
        vectors = self._embedder.embed_batch(texts)

        for chunk, vec in zip(chunks, vectors, strict=False):
            stored = _StoredVector(
                doc_id=chunk["doc_id"],
                title=chunk.get("title", ""),
                text=chunk["text"],
                vector=vec,
                metadata=chunk.get("metadata", {}),
            )
            self._upsert(stored)

        logger.info("chunks_embedded", count=len(chunks))

    async def search(self, query: str, top_k: int = 10) -> list[VectorSearchResult]:
        """Semantic search by natural-language query.

        The query is embedded using the same model and then compared
        against all stored vectors via cosine similarity.

        Args:
            query: Natural-language search query.
            top_k: Maximum number of results to return.

        Returns:
            List of :class:`VectorSearchResult` sorted by descending score.
        """
        if not self._vectors:
            return []

        query_vector = self._embedder.embed(query)
        return await self.search_by_vector(query_vector, top_k=top_k)

    async def search_by_vector(self, vector: list[float], top_k: int = 10) -> list[VectorSearchResult]:
        """Search by a raw embedding vector.

        This is useful when the caller already has an embedding (e.g.
        from an external model or a cached query).

        Args:
            vector: Query embedding vector.
            top_k: Maximum number of results to return.

        Returns:
            List of :class:`VectorSearchResult` sorted by descending score.
        """
        if not self._vectors:
            return []

        scored: list[tuple[int, float]] = []
        for idx, stored in enumerate(self._vectors):
            sim = self._cosine_similarity(vector, stored.vector)
            scored.append((idx, sim))

        scored.sort(key=lambda x: x[1], reverse=True)

        results: list[VectorSearchResult] = []
        for idx, sim in scored[:top_k]:
            stored = self._vectors[idx]
            results.append(
                VectorSearchResult(
                    doc_id=stored.doc_id,
                    title=stored.title,
                    text=stored.text,
                    score=sim,
                    metadata=stored.metadata,
                )
            )

        logger.debug("vector_search_complete", results=len(results))
        return results

    @property
    def count(self) -> int:
        """Number of stored vectors."""
        return len(self._vectors)

    @property
    def dimension(self) -> int:
        """Dimensionality of the embedding model."""
        return self._embedder.dimension

    # ── Internal helpers ──────────────────────────────────────────────

    def _upsert(self, stored: _StoredVector) -> None:
        """Insert or replace a stored vector by doc_id."""
        if stored.doc_id in self._id_index:
            pos = self._id_index[stored.doc_id]
            self._vectors[pos] = stored
        else:
            self._id_index[stored.doc_id] = len(self._vectors)
            self._vectors.append(stored)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        When both vectors are unit-normalised (as sentence-transformers
        produces with ``normalize_embeddings=True``) this reduces to a
        simple dot product.  The full formula is kept for safety when
        non-normalised vectors are supplied.
        """
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)
