"""Reranker — re-scores search results for improved relevance ordering."""

from __future__ import annotations

from evidentia.core.logging import get_logger
from evidentia.retrieval.hybrid_search import SearchResult

logger = get_logger(__name__)


class Reranker:
    """Re-scores search results using a cross-encoder or heuristic model.

    In production this would use a cross-encoder model (e.g. ms-marco).
    This implementation provides a simple heuristic reranker as a baseline.
    """

    def __init__(self, title_boost: float = 1.5, recency_boost: float = 1.2) -> None:
        self._title_boost = title_boost
        self._recency_boost = recency_boost

    def rerank(self, query: str, results: list[SearchResult], top_k: int = 10) -> list[SearchResult]:
        """Re-score and reorder search results."""
        query_lower = query.lower()
        scored: list[SearchResult] = []

        for result in results:
            boost = 1.0

            # Boost if query terms appear in title
            title_lower = result.source.title.lower()
            query_terms = query_lower.split()
            title_matches = sum(1 for t in query_terms if t in title_lower)
            if title_matches > 0:
                boost *= self._title_boost * (title_matches / len(query_terms))

            new_score = result.score * boost
            scored.append(
                SearchResult(
                    source=result.source,
                    score=new_score,
                    match_type=result.match_type,
                )
            )

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]
