"""Domain models for systematic literature reviews."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ── Review Mode (Tiered) ────────────────────────────────────────────


class ReviewMode(str, Enum):
    """Tiered review modes with different rigor levels."""

    FAST = "fast"  # 1 screening pass, no quality scoring, no contradictions
    RIGOROUS = "rigorous"  # 2 screening passes, quality scoring, contradictions
    PUBLICATION = "publication"  # 3 screening passes, quality scoring, contradictions, full audit


# Default parameters per mode
REVIEW_MODE_PARAMS: dict[ReviewMode, dict[str, Any]] = {
    ReviewMode.FAST: {
        "screening_passes": 1,
        "quality_scoring": False,
        "contradiction_detection": False,
        "screening_temperature": 0.0,
    },
    ReviewMode.RIGOROUS: {
        "screening_passes": 2,
        "quality_scoring": True,
        "contradiction_detection": True,
        "screening_temperature": 0.0,
    },
    ReviewMode.PUBLICATION: {
        "screening_passes": 3,
        "quality_scoring": True,
        "contradiction_detection": True,
        "screening_temperature": 0.0,
    },
}


class ReviewConfig(BaseModel):
    """User-provided configuration for a systematic review."""

    research_question: str
    inclusion_criteria: list[str]
    exclusion_criteria: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=lambda: ["pubmed_search", "openalex_search", "semantic_scholar"])
    max_results_per_db: int = 100
    mode: ReviewMode = ReviewMode.RIGOROUS


class PaperRecord(BaseModel):
    """Unified representation of an academic paper across all databases."""

    title: str = ""
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    doi: str | None = None
    url: str | None = None
    published_date: str | None = None
    journal: str | None = None
    citation_count: int | None = None
    source_database: str = ""
    source_id: str | None = None

    # Populated during deduplication
    is_duplicate: bool = False
    duplicate_of: str | None = None

    # Populated during screening
    screening_decision: str | None = None  # include, exclude, uncertain
    exclusion_reason: str | None = None
    screening_confidence: float | None = None

    # Explainability: per-criteria screening rationale
    criteria_evaluations: list[CriterionEvaluation] | None = None
    evidence_spans: list[str] | None = None  # Text spans from abstract supporting decision

    # Confidence calibration: multi-pass agreement
    screening_agreement: float | None = None  # 0.0-1.0 inter-pass agreement
    screening_votes: list[str] | None = None  # e.g. ["include", "include", "exclude"]

    # Populated during quality scoring
    quality_score: float | None = None  # 0.0-1.0 composite score
    quality_grade: str | None = None  # A, B, C, D, F
    quality_dimensions: dict[str, Any] | None = None  # Full breakdown


class CriterionEvaluation(BaseModel):
    """Evaluation of a single inclusion/exclusion criterion for a paper."""

    criterion: str  # The original criterion text
    criterion_type: str = "inclusion"  # "inclusion" or "exclusion"
    met: bool | None = None  # True=met, False=not met, None=uncertain
    rationale: str = ""
    evidence_span: str = ""  # Text from abstract supporting this evaluation


class ScreeningDecision(BaseModel):
    """LLM screening result for a single paper."""

    paper_index: int
    decision: str  # include, exclude, uncertain
    reason: str = ""
    confidence: float = 0.0

    # Per-decision explainability
    criteria_evaluations: list[CriterionEvaluation] = Field(default_factory=list)
    evidence_spans: list[str] = Field(default_factory=list)


class PRISMAFlowData(BaseModel):
    """PRISMA flow diagram counts."""

    databases_searched: list[str] = Field(default_factory=list)
    records_per_database: dict[str, int] = Field(default_factory=dict)
    total_identified: int = 0
    duplicates_removed: int = 0
    records_screened: int = 0
    excluded_at_screening: int = 0
    exclusion_reasons: dict[str, int] = Field(default_factory=dict)
    uncertain_count: int = 0
    included_count: int = 0


class ReviewEvent(BaseModel):
    """Event emitted during review execution (mirrors AgentEvent)."""

    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


# ── Reproducibility ─────────────────────────────────────────────────


class ReviewRunManifest(BaseModel):
    """Reproducibility manifest — captures all inputs that determine a review's output.

    The run_hash is a SHA-256 digest of the deterministic inputs.
    Two runs with the same manifest hash should produce identical results
    (assuming API responses are cached/stable).
    """

    config: ReviewConfig
    model_id: str = ""
    screening_temperature: float = 0.0
    screening_passes: int = 1
    quality_scoring_enabled: bool = True
    contradiction_detection_enabled: bool = True
    scoring_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "methodology_rigor": 0.30,
            "sample_adequacy": 0.20,
            "bias_risk": 0.20,
            "reproducibility": 0.15,
            "statistical_rigor": 0.15,
        }
    )
    engine_version: str = "1.0.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def compute_hash(self) -> str:
        """SHA-256 hash of deterministic run inputs."""
        # Only hash the inputs that affect output (not timestamps)
        deterministic = {
            "research_question": self.config.research_question,
            "inclusion_criteria": sorted(self.config.inclusion_criteria),
            "exclusion_criteria": sorted(self.config.exclusion_criteria),
            "databases": sorted(self.config.databases),
            "max_results_per_db": self.config.max_results_per_db,
            "mode": self.config.mode.value,
            "model_id": self.model_id,
            "screening_temperature": self.screening_temperature,
            "screening_passes": self.screening_passes,
            "quality_scoring": self.quality_scoring_enabled,
            "contradiction_detection": self.contradiction_detection_enabled,
            "scoring_weights": self.scoring_weights,
            "engine_version": self.engine_version,
        }
        payload = json.dumps(deterministic, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()
