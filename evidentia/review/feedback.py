"""User feedback learning loop — stores screening overrides as training signal.

Every time a researcher overrides Evidentia's automated screening decision,
that override becomes a labeled training example. Over time, this data
improves screening accuracy — a compounding data moat.

Storage: JSON-lines file (one entry per feedback event). No external DB needed.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from evidentia.core.logging import get_logger

logger = get_logger(__name__)


class FeedbackEntry(BaseModel):
    """A single user feedback event (screening override)."""

    timestamp: float = Field(default_factory=time.time)
    user_id: str = ""
    review_id: str = ""
    paper_title: str = ""
    paper_abstract: str = ""
    paper_doi: str | None = None
    original_decision: str = ""  # What Evidentia decided
    original_confidence: float = 0.0
    user_decision: str = ""  # What the user chose
    user_reason: str | None = None
    research_question: str = ""
    inclusion_criteria: list[str] = Field(default_factory=list)
    exclusion_criteria: list[str] = Field(default_factory=list)


class FeedbackStats(BaseModel):
    """Aggregate stats about collected feedback."""

    total_overrides: int = 0
    overrides_to_include: int = 0
    overrides_to_exclude: int = 0
    avg_original_confidence_on_overrides: float = 0.0
    most_common_override_reasons: list[str] = Field(default_factory=list)
    accuracy_estimate: float | None = None  # % of decisions users agreed with


class FeedbackStore:
    """Append-only store for screening override feedback.

    Data moat: every override makes future screening more accurate.
    File-based to avoid DB dependency; scales to millions of entries.
    """

    def __init__(self, data_dir: str | Path | None = None) -> None:
        if data_dir is None:
            data_dir = Path.home() / ".evidentia" / "feedback"
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._feedback_file = self._data_dir / "screening_overrides.jsonl"

    def record_override(
        self,
        user_id: str,
        review_id: str,
        paper_title: str,
        paper_abstract: str,
        original_decision: str,
        original_confidence: float,
        user_decision: str,
        user_reason: str | None = None,
        research_question: str = "",
        inclusion_criteria: list[str] | None = None,
        exclusion_criteria: list[str] | None = None,
        paper_doi: str | None = None,
    ) -> FeedbackEntry:
        """Record a screening override as feedback."""
        entry = FeedbackEntry(
            user_id=user_id,
            review_id=review_id,
            paper_title=paper_title,
            paper_abstract=paper_abstract or "",
            paper_doi=paper_doi,
            original_decision=original_decision,
            original_confidence=original_confidence,
            user_decision=user_decision,
            user_reason=user_reason,
            research_question=research_question,
            inclusion_criteria=inclusion_criteria or [],
            exclusion_criteria=exclusion_criteria or [],
        )

        try:
            with open(self._feedback_file, "a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
            logger.info(
                "feedback_recorded",
                user_id=user_id,
                review_id=review_id,
                original=original_decision,
                override=user_decision,
            )
        except OSError as exc:
            logger.warning("feedback_write_failed", error=str(exc))

        return entry

    def get_stats(self) -> FeedbackStats:
        """Compute aggregate feedback statistics."""
        entries = self._load_all()

        if not entries:
            return FeedbackStats()

        overrides = [e for e in entries if e.original_decision != e.user_decision]
        agreements = [e for e in entries if e.original_decision == e.user_decision]

        to_include = sum(1 for e in overrides if e.user_decision == "include")
        to_exclude = sum(1 for e in overrides if e.user_decision == "exclude")

        avg_conf = 0.0
        if overrides:
            avg_conf = sum(e.original_confidence for e in overrides) / len(overrides)

        # Most common override reasons
        reason_counts: dict[str, int] = {}
        for e in overrides:
            if e.user_reason:
                reason_counts[e.user_reason] = reason_counts.get(e.user_reason, 0) + 1
        top_reasons = sorted(reason_counts.keys(), key=lambda r: -reason_counts[r])[:5]

        # Accuracy estimate (what % did users agree with)
        accuracy = None
        total = len(entries)
        if total > 0:
            accuracy = round(len(agreements) / total, 3)

        return FeedbackStats(
            total_overrides=len(overrides),
            overrides_to_include=to_include,
            overrides_to_exclude=to_exclude,
            avg_original_confidence_on_overrides=round(avg_conf, 3),
            most_common_override_reasons=top_reasons,
            accuracy_estimate=accuracy,
        )

    def get_training_pairs(
        self, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Export feedback as training pairs for fine-tuning.

        Each pair contains the paper context + the human-corrected decision.
        This is the raw material for building a fine-tuned screening model.
        """
        entries = self._load_all()
        overrides = [e for e in entries if e.original_decision != e.user_decision]

        pairs: list[dict[str, Any]] = []
        for entry in overrides[:limit]:
            pairs.append({
                "input": {
                    "title": entry.paper_title,
                    "abstract": entry.paper_abstract,
                    "research_question": entry.research_question,
                    "inclusion_criteria": entry.inclusion_criteria,
                    "exclusion_criteria": entry.exclusion_criteria,
                },
                "label": entry.user_decision,
                "reason": entry.user_reason or "",
                "original_prediction": entry.original_decision,
                "original_confidence": entry.original_confidence,
            })

        return pairs

    def _load_all(self) -> list[FeedbackEntry]:
        """Load all feedback entries from disk."""
        if not self._feedback_file.exists():
            return []

        entries: list[FeedbackEntry] = []
        try:
            with open(self._feedback_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(FeedbackEntry.model_validate_json(line))
                        except Exception:
                            continue  # Skip malformed entries
        except OSError:
            pass

        return entries
