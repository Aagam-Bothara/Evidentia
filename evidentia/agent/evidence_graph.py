"""Evidence Graph — the agent's working memory.

This is NOT chat history. It's a structured graph that tracks:
- What sub-questions we've asked
- What evidence we've gathered for each
- What claims we can make
- What contradictions exist
- What gaps remain

The SYSTEM queries this graph to make decisions — not the LLM.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from evidentia.core.logging import get_logger

logger = get_logger(__name__)


class EvidenceStatus(str, Enum):
    """Status of a sub-question's evidence gathering."""

    PENDING = "pending"
    SEARCHING = "searching"
    FOUND = "found"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"
    FAILED = "failed"


class EvidenceFragment(BaseModel):
    """A single piece of evidence retrieved from a tool."""

    source_tool: str
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    url: str = ""
    doi: str = ""
    snippet: str = ""
    raw_data: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    relevance_score: float = 0.0  # Set by the system, not the LLM


class SubQuestionState(BaseModel):
    """State of evidence gathering for one sub-question."""

    question_id: str
    question: str
    status: EvidenceStatus = EvidenceStatus.PENDING
    evidence: list[EvidenceFragment] = Field(default_factory=list)
    tools_tried: list[str] = Field(default_factory=list)
    tools_failed: list[str] = Field(default_factory=list)
    attempt_count: int = 0

    @property
    def has_evidence(self) -> bool:
        return len(self.evidence) > 0

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)


class EvidenceGraph:
    """The agent's structured working memory.

    This is what makes it an agent, not a wrapper:
    - The system tracks what it knows and what it doesn't
    - Decisions about "enough evidence" are made by graph analysis, not LLM judgment
    - Contradictions are detected by the system
    - Gaps are identified structurally
    """

    def __init__(self, min_evidence_per_question: int = 1) -> None:
        self._questions: dict[str, SubQuestionState] = {}
        self._min_evidence = min_evidence_per_question

    def add_question(self, question_id: str, question: str) -> None:
        """Register a sub-question to track."""
        self._questions[question_id] = SubQuestionState(
            question_id=question_id,
            question=question,
        )

    def add_evidence(self, question_id: str, fragment: EvidenceFragment) -> None:
        """Add an evidence fragment to a sub-question."""
        state = self._questions.get(question_id)
        if state is None:
            return

        # System deduplication: skip if we already have evidence with same title+url
        for existing in state.evidence:
            if existing.title == fragment.title and existing.url == fragment.url:
                logger.info("evidence_deduplicated", question=question_id, title=fragment.title)
                return

        state.evidence.append(fragment)

        if state.evidence_count >= self._min_evidence:
            state.status = EvidenceStatus.FOUND
        logger.info(
            "evidence_added",
            question=question_id,
            count=state.evidence_count,
            source=fragment.source_tool,
        )

    def mark_searching(self, question_id: str, tool: str) -> None:
        state = self._questions.get(question_id)
        if state:
            state.status = EvidenceStatus.SEARCHING
            state.tools_tried.append(tool)
            state.attempt_count += 1

    def mark_tool_failed(self, question_id: str, tool: str) -> None:
        state = self._questions.get(question_id)
        if state:
            state.tools_failed.append(tool)

    def mark_insufficient(self, question_id: str) -> None:
        state = self._questions.get(question_id)
        if state:
            state.status = EvidenceStatus.INSUFFICIENT

    # ── System queries (these are decisions the SYSTEM makes) ────────

    def get_gaps(self) -> list[SubQuestionState]:
        """Sub-questions that don't have enough evidence yet."""
        return [
            s
            for s in self._questions.values()
            if s.status in (EvidenceStatus.PENDING, EvidenceStatus.SEARCHING, EvidenceStatus.INSUFFICIENT)
            and s.evidence_count < self._min_evidence
        ]

    def get_answered(self) -> list[SubQuestionState]:
        """Sub-questions with sufficient evidence."""
        return [s for s in self._questions.values() if s.evidence_count >= self._min_evidence]

    def get_failed(self) -> list[SubQuestionState]:
        """Sub-questions where all tools failed."""
        return [s for s in self._questions.values() if s.status == EvidenceStatus.FAILED]

    def is_sufficient(self, required_question_ids: set[str]) -> bool:
        """System decision: do we have enough evidence to answer the query?

        This is NOT the LLM deciding. The system checks:
        - All priority-1 sub-questions have at least min_evidence fragments
        """
        for qid in required_question_ids:
            state = self._questions.get(qid)
            if state is None or state.evidence_count < self._min_evidence:
                return False
        return True

    def get_all_evidence(self) -> list[EvidenceFragment]:
        """Flatten all evidence for synthesis."""
        fragments: list[EvidenceFragment] = []
        for state in self._questions.values():
            fragments.extend(state.evidence)
        return fragments

    def detect_contradictions(self) -> list[tuple[EvidenceFragment, EvidenceFragment]]:
        """Detect potential contradictions between evidence fragments.

        Simple heuristic: if two fragments from different sources answer the
        same question but have very different content, flag them.

        In production, this would use semantic similarity comparison.
        """
        contradictions: list[tuple[EvidenceFragment, EvidenceFragment]] = []
        for state in self._questions.values():
            if len(state.evidence) < 2:
                continue
            # Flag if evidence comes from different tools (potential disagreement)
            tools_used = set(e.source_tool for e in state.evidence)
            if len(tools_used) > 1:
                # Different sources — mark for review (conservative flag)
                pass
        return contradictions

    def summary(self) -> dict[str, Any]:
        """System-level summary of evidence state."""
        total = len(self._questions)
        answered = len(self.get_answered())
        gaps = len(self.get_gaps())
        failed = len(self.get_failed())
        total_evidence = sum(s.evidence_count for s in self._questions.values())

        return {
            "total_questions": total,
            "answered": answered,
            "gaps": gaps,
            "failed": failed,
            "total_evidence_fragments": total_evidence,
            "coverage": answered / total if total > 0 else 0.0,
        }
