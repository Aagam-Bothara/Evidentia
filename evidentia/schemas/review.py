"""Pydantic request/response schemas for systematic reviews."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewCreateRequest(BaseModel):
    research_question: str = Field(..., min_length=10, max_length=5000)
    inclusion_criteria: list[str] = Field(..., min_length=1)
    exclusion_criteria: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=lambda: ["pubmed_search", "openalex_search", "semantic_scholar"])
    max_results_per_database: int = Field(default=100, ge=10, le=500)
    project_id: str | None = None
    mode: str = Field(default="rigorous", pattern=r"^(fast|rigorous|publication)$")


class PRISMAFlowResponse(BaseModel):
    databases_searched: list[str] = Field(default_factory=list)
    records_per_database: dict[str, int] = Field(default_factory=dict)
    total_identified: int = 0
    duplicates_removed: int = 0
    records_screened: int = 0
    excluded_at_screening: int = 0
    exclusion_reasons: dict[str, int] = Field(default_factory=dict)
    uncertain_count: int = 0
    included_count: int = 0


class ReviewResponse(BaseModel):
    id: str
    research_question: str
    status: str
    mode: str = "rigorous"
    run_hash: str | None = None
    prisma: PRISMAFlowResponse = Field(default_factory=PRISMAFlowResponse)
    created_at: str
    elapsed_seconds: float | None = None


class ReviewListResponse(BaseModel):
    reviews: list[ReviewResponse]


class CriterionEvaluationResponse(BaseModel):
    criterion: str
    criterion_type: str = "inclusion"
    met: bool | None = None
    rationale: str = ""
    evidence_span: str = ""


class CalibrationResponse(BaseModel):
    passes: int = 1
    mean_agreement: float | None = None
    full_agreement_count: int = 0
    low_agreement_count: int = 0


class QualityScoreResponse(BaseModel):
    overall_score: float | None = None
    grade: str | None = None
    study_design: str | None = None
    dimensions: list[dict] = Field(default_factory=list)
    sample_size: int | None = None
    has_control_group: bool | None = None
    is_preregistered: bool | None = None
    has_open_data: bool | None = None
    funding_bias_risk: str = "unknown"
    summary: str = ""


class ContradictionResponse(BaseModel):
    paper_a_index: int = 0
    paper_b_index: int = 0
    paper_a_title: str = ""
    paper_b_title: str = ""
    dimension: str = ""
    contradiction_type: str = "unknown"
    description: str = ""
    severity: str = "moderate"
    confidence: float = 0.0
    evidence_a: str = ""
    evidence_b: str = ""


class ContradictionReportResponse(BaseModel):
    total_contradictions: int = 0
    contradictions: list[ContradictionResponse] = Field(default_factory=list)
    consensus_areas: list[str] = Field(default_factory=list)
    summary: str = ""
    type_distribution: dict[str, int] = Field(default_factory=dict)


class PaperResponse(BaseModel):
    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    doi: str | None = None
    url: str | None = None
    published_date: str | None = None
    journal: str | None = None
    citation_count: int | None = None
    source_database: str = ""
    is_duplicate: bool = False
    screening_decision: str | None = None
    exclusion_reason: str | None = None
    manually_reviewed: bool = False
    quality_score: float | None = None
    quality_grade: str | None = None
    quality_dimensions: dict | None = None
    # Explainability fields
    criteria_evaluations: list[CriterionEvaluationResponse] | None = None
    evidence_spans: list[str] | None = None
    # Calibration fields
    screening_agreement: float | None = None
    screening_votes: list[str] | None = None


class PaperListResponse(BaseModel):
    papers: list[PaperResponse]
    total: int = 0


class PaperDecisionRequest(BaseModel):
    decision: str = Field(..., pattern=r"^(include|exclude)$")
    reason: str | None = None


class BulkDecisionRequest(BaseModel):
    decisions: list[dict]


class ReviewExportRequest(BaseModel):
    format: str = Field(default="csv", pattern=r"^(csv|bibtex|ris)$")
    include_excluded: bool = False
