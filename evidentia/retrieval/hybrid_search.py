"""Hybrid search — combines BM25 keyword search with vector similarity."""

from __future__ import annotations

import math
from collections import Counter
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from evidentia.core.logging import get_logger
from evidentia.core.models import Source

if TYPE_CHECKING:
    from evidentia.retrieval.vector_store import VectorStore

logger = get_logger(__name__)


class SearchResult(BaseModel):
    """A single search result with relevance score."""

    source: Source
    score: float
    match_type: str  # "bm25", "vector", "hybrid"


class HybridSearchEngine:
    """Combines BM25 keyword scoring with vector similarity for retrieval.

    In production, BM25 runs against PostgreSQL full-text search and
    vector search runs against pgvector. This implementation provides
    the BM25 component in-memory.
    """

    def __init__(
        self,
        bm25_weight: float = 0.4,
        vector_weight: float = 0.6,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self._bm25_weight = bm25_weight
        self._vector_weight = vector_weight
        self._k1 = k1
        self._b = b
        self._documents: list[Source] = []
        self._doc_freqs: Counter[str] = Counter()
        self._avg_doc_len: float = 0.0

    def index(self, documents: list[Source]) -> None:
        """Build the BM25 index over the given documents."""
        self._documents = documents
        total_len = 0
        self._doc_freqs = Counter()

        for doc in documents:
            tokens = self._tokenize(doc.content)
            total_len += len(tokens)
            unique_tokens = set(tokens)
            for token in unique_tokens:
                self._doc_freqs[token] += 1

        self._avg_doc_len = total_len / len(documents) if documents else 0.0

    def search_bm25(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Pure BM25 keyword search."""
        query_tokens = self._tokenize(query)
        n = len(self._documents)
        scores: list[tuple[int, float]] = []

        for idx, doc in enumerate(self._documents):
            doc_tokens = self._tokenize(doc.content)
            doc_len = len(doc_tokens)
            tf_map = Counter(doc_tokens)
            score = 0.0

            for qt in query_tokens:
                if qt not in tf_map:
                    continue
                tf = tf_map[qt]
                df = self._doc_freqs.get(qt, 0)
                idf = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
                numerator = tf * (self._k1 + 1)
                denominator = tf + self._k1 * (1 - self._b + self._b * doc_len / max(self._avg_doc_len, 1))
                score += idf * numerator / denominator

            scores.append((idx, score))

        scores.sort(key=lambda x: x[1], reverse=True)

        return [
            SearchResult(
                source=self._documents[idx],
                score=score,
                match_type="bm25",
            )
            for idx, score in scores[:top_k]
            if score > 0
        ]

    async def search_hybrid(
        self,
        query: str,
        vector_store: VectorStore,
        top_k: int = 10,
        bm25_weight: float | None = None,
        vector_weight: float | None = None,
        rrf_k: int = 60,
    ) -> list[SearchResult]:
        """Hybrid search combining BM25 keyword scores with vector similarity.

        Uses Reciprocal Rank Fusion (RRF) to merge the two ranked result
        lists into a single ordering.  RRF is robust to differences in
        score scale between the two systems.

        Args:
            query: Natural-language search query.
            vector_store: A :class:`VectorStore` instance to run semantic search against.
            top_k: Maximum number of results to return.
            bm25_weight: Override for the BM25 weight (defaults to instance setting).
            vector_weight: Override for the vector weight (defaults to instance setting).
            rrf_k: The *k* constant in RRF (default 60, per the original paper).

        Returns:
            List of :class:`SearchResult` sorted by descending hybrid score.
        """
        w_bm25 = bm25_weight if bm25_weight is not None else self._bm25_weight
        w_vec = vector_weight if vector_weight is not None else self._vector_weight

        # Fetch both result lists — BM25 is synchronous, vector is async.
        bm25_results = self.search_bm25(query, top_k=top_k)
        vector_results = await vector_store.search(query, top_k=top_k)

        # Build RRF score maps keyed by doc id.
        rrf_scores: dict[str, float] = {}
        source_map: dict[str, Source] = {}

        # BM25 contribution (results already ranked by score descending).
        for rank, result in enumerate(bm25_results, start=1):
            doc_id = result.source.id
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + w_bm25 / (rrf_k + rank)
            source_map[doc_id] = result.source

        # Vector contribution.
        for rank, vr in enumerate(vector_results, start=1):
            doc_id = vr.doc_id
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + w_vec / (rrf_k + rank)
            # If the doc wasn't already in source_map, reconstruct a minimal Source.
            if doc_id not in source_map:
                source_map[doc_id] = self._source_from_vector_result(vr)

        # Sort by fused score and return top_k.
        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        results: list[SearchResult] = []
        for doc_id, score in ranked[:top_k]:
            results.append(
                SearchResult(
                    source=source_map[doc_id],
                    score=score,
                    match_type="hybrid",
                )
            )

        logger.info(
            "hybrid_search_complete",
            bm25_hits=len(bm25_results),
            vector_hits=len(vector_results),
            fused_hits=len(results),
        )
        return results

    @staticmethod
    def _source_from_vector_result(vr: Any) -> Source:
        """Build a minimal Source from a VectorSearchResult.

        This is used when a document appears in the vector results but
        not in the BM25 results (e.g. it was added as a chunk only).
        """
        from evidentia.core.models import SourceType

        return Source(
            id=vr.doc_id,
            title=vr.title,
            content=vr.text,
            source_type=SourceType.DOCUMENT,
            metadata=vr.metadata,
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + lowercase tokenizer."""
        return text.lower().split()
