"""Deduplication engine for systematic reviews.

Two-stage approach:
1. Exact DOI match (strongest signal)
2. Fuzzy title match via Jaccard token-overlap (threshold 0.85)
"""

from __future__ import annotations

import re

from evidentia.review.models import PaperRecord


class Deduplicator:
    """Remove duplicate papers found across multiple databases."""

    def __init__(self, title_threshold: float = 0.85) -> None:
        self._title_threshold = title_threshold

    def deduplicate(self, papers: list[PaperRecord]) -> tuple[list[PaperRecord], list[PaperRecord]]:
        """Partition papers into unique and duplicate sets.

        Returns:
            (unique_papers, duplicate_papers)
        """
        unique: list[PaperRecord] = []
        duplicates: list[PaperRecord] = []
        seen_dois: dict[str, int] = {}
        seen_titles: list[tuple[set[str], int]] = []  # (word_set, index_in_unique)

        for paper in papers:
            # Stage 1: Exact DOI match
            if paper.doi:
                doi_key = paper.doi.lower().strip()
                if doi_key in seen_dois:
                    paper.is_duplicate = True
                    paper.duplicate_of = unique[seen_dois[doi_key]].source_id
                    duplicates.append(paper)
                    continue
                seen_dois[doi_key] = len(unique)

            # Stage 2: Fuzzy title match
            words = self._tokenize(paper.title)
            is_dup = False
            for existing_words, existing_idx in seen_titles:
                sim = self._jaccard(words, existing_words)
                if sim >= self._title_threshold:
                    paper.is_duplicate = True
                    paper.duplicate_of = unique[existing_idx].source_id
                    duplicates.append(paper)
                    is_dup = True
                    break

            if not is_dup:
                seen_titles.append((words, len(unique)))
                unique.append(paper)

        return unique, duplicates

    @staticmethod
    def _tokenize(title: str) -> set[str]:
        """Lowercase, strip punctuation, split into word set."""
        cleaned = re.sub(r"[^\w\s]", "", title.lower())
        return set(cleaned.split())

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        """Jaccard similarity between two word sets."""
        if not a or not b:
            return 0.0
        intersection = a & b
        union = a | b
        return len(intersection) / len(union)
