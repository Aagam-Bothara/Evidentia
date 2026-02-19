"""Evidence Quality Scoring — proprietary methodology assessment.

Analyzes papers on multiple quality dimensions using LLM-based assessment
combined with heuristic signals extracted from metadata and abstracts.

This is Evidentia's core differentiator: no public API provides this.
"""

from __future__ import annotations

import asyncio
import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from evidentia.core.llm import BaseLLM
from evidentia.core.logging import get_logger
from evidentia.review.models import PaperRecord

logger = get_logger(__name__)


# ── Domain models ─────────────────────────────────────────────────────


class StudyDesign(str, Enum):
    """Hierarchy of study designs (strongest → weakest evidence)."""

    META_ANALYSIS = "meta_analysis"
    SYSTEMATIC_REVIEW = "systematic_review"
    RCT = "rct"
    COHORT = "cohort"
    CASE_CONTROL = "case_control"
    CROSS_SECTIONAL = "cross_sectional"
    CASE_REPORT = "case_report"
    EXPERT_OPINION = "expert_opinion"
    UNKNOWN = "unknown"


# Evidence strength by design (0.0-1.0 scale)
DESIGN_STRENGTH: dict[StudyDesign, float] = {
    StudyDesign.META_ANALYSIS: 1.0,
    StudyDesign.SYSTEMATIC_REVIEW: 0.95,
    StudyDesign.RCT: 0.85,
    StudyDesign.COHORT: 0.65,
    StudyDesign.CASE_CONTROL: 0.55,
    StudyDesign.CROSS_SECTIONAL: 0.45,
    StudyDesign.CASE_REPORT: 0.25,
    StudyDesign.EXPERT_OPINION: 0.15,
    StudyDesign.UNKNOWN: 0.2,
}


class QualityDimension(BaseModel):
    """Score for a single quality dimension."""

    name: str
    score: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    signals: list[str] = Field(default_factory=list)


class EvidenceQualityScore(BaseModel):
    """Composite evidence quality assessment for a paper."""

    overall_score: float = Field(ge=0.0, le=1.0, default=0.0)
    grade: str = ""  # A, B, C, D, F
    study_design: StudyDesign = StudyDesign.UNKNOWN
    dimensions: list[QualityDimension] = Field(default_factory=list)
    sample_size: int | None = None
    has_control_group: bool | None = None
    is_preregistered: bool | None = None
    has_open_data: bool | None = None
    funding_bias_risk: str = "unknown"  # low, moderate, high, unknown
    summary: str = ""


# ── Heuristic signals (fast, no LLM needed) ──────────────────────────


# Study design detection patterns (applied to title + abstract)
_DESIGN_PATTERNS: list[tuple[StudyDesign, re.Pattern]] = [
    (StudyDesign.META_ANALYSIS, re.compile(
        r"\bmeta[\s-]?analy", re.IGNORECASE
    )),
    (StudyDesign.SYSTEMATIC_REVIEW, re.compile(
        r"\bsystematic\s+review\b", re.IGNORECASE
    )),
    (StudyDesign.RCT, re.compile(
        r"\b(randomi[sz]ed\s+(controlled?\s+)?trial|RCT)\b", re.IGNORECASE
    )),
    (StudyDesign.COHORT, re.compile(
        r"\b(cohort|longitudinal|prospective|retrospective)\s+(study|analysis)\b",
        re.IGNORECASE,
    )),
    (StudyDesign.CASE_CONTROL, re.compile(
        r"\bcase[\s-]?control\b", re.IGNORECASE
    )),
    (StudyDesign.CROSS_SECTIONAL, re.compile(
        r"\bcross[\s-]?sectional\b", re.IGNORECASE
    )),
    (StudyDesign.CASE_REPORT, re.compile(
        r"\bcase\s+(report|series)\b", re.IGNORECASE
    )),
    (StudyDesign.EXPERT_OPINION, re.compile(
        r"\b(editorial|commentary|opinion|letter\s+to\s+the\s+editor)\b",
        re.IGNORECASE,
    )),
]

# Sample size extraction patterns
_SAMPLE_SIZE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bn\s*=\s*(\d[\d,]*)", re.IGNORECASE),
    re.compile(r"(\d[\d,]*)\s+participants", re.IGNORECASE),
    re.compile(r"(\d[\d,]*)\s+patients", re.IGNORECASE),
    re.compile(r"(\d[\d,]*)\s+subjects", re.IGNORECASE),
    re.compile(r"sample\s+(?:size\s+)?(?:of\s+)?(\d[\d,]*)", re.IGNORECASE),
    re.compile(r"(\d[\d,]*)\s+(?:individuals|adults|children|people|women|men)", re.IGNORECASE),
    re.compile(r"enrolled\s+(\d[\d,]*)", re.IGNORECASE),
]

# Study count extraction for meta-analyses / systematic reviews
_STUDY_COUNT_PATTERNS: list[re.Pattern] = [
    re.compile(r"(\d[\d,]*)\s+(?:studies|trials|articles|publications)\s+(?:were\s+)?(?:included|selected|identified|met)", re.IGNORECASE),
    re.compile(r"included\s+(\d[\d,]*)\s+(?:studies|trials|articles)", re.IGNORECASE),
    re.compile(r"(\d[\d,]*)\s+(?:studies|trials)\s+(?:in|for|with)", re.IGNORECASE),
    re.compile(r"(?:comprising|totaling|across|from)\s+(\d[\d,]*)\s+(?:studies|trials)", re.IGNORECASE),
    re.compile(r"k\s*=\s*(\d[\d,]*)", re.IGNORECASE),
]


def extract_study_count(text: str) -> int | None:
    """Extract the number of included studies (for meta-analyses/systematic reviews)."""
    for pattern in _STUDY_COUNT_PATTERNS:
        for match in pattern.finditer(text):
            try:
                k = int(match.group(1).replace(",", ""))
                if 2 <= k <= 5000:  # Reasonable range for study counts
                    return k
            except (ValueError, IndexError):
                continue
    return None


# Bias / reproducibility signal patterns
_PREREGISTRATION_PATTERN = re.compile(
    r"\b(pre[\s-]?register|PROSPERO|ClinicalTrials\.gov|OSF|ISRCTN)\b",
    re.IGNORECASE,
)
_OPEN_DATA_PATTERN = re.compile(
    r"\b(open\s+data|data\s+availab|code\s+availab|github\.com|zenodo|figshare|dryad)\b",
    re.IGNORECASE,
)
_CONTROL_GROUP_PATTERN = re.compile(
    r"\b(control\s+group|placebo|sham|wait[\s-]?list|compared\s+(?:to|with)\s+(?:a\s+)?control)\b",
    re.IGNORECASE,
)
_FUNDING_INDUSTRY_PATTERN = re.compile(
    r"\b(funded\s+by|supported\s+by|grant\s+from).{0,80}(pharma|inc\.|corp|ltd|company|industry)\b",
    re.IGNORECASE,
)
_CONFLICT_PATTERN = re.compile(
    r"\b(conflict.{0,10}interest|competing\s+interest|no\s+conflict|declare.{0,10}conflict)\b",
    re.IGNORECASE,
)


def detect_study_design(text: str) -> StudyDesign:
    """Detect study design from title + abstract text."""
    for design, pattern in _DESIGN_PATTERNS:
        if pattern.search(text):
            return design
    return StudyDesign.UNKNOWN


def extract_sample_size(text: str) -> int | None:
    """Extract the most likely sample size from abstract text.

    Uses priority-based selection: "N=" statements are most definitive,
    "enrolled" is next, then first plausible mention from other patterns.
    Avoids returning screening/assessed counts that overstate sample size.
    """
    # Priority 1: "N = X" — almost always the definitive sample size
    n_eq_pattern = _SAMPLE_SIZE_PATTERNS[0]  # r"\bn\s*=\s*(\d[\d,]*)"
    n_eq_matches = []
    for match in n_eq_pattern.finditer(text):
        try:
            n = int(match.group(1).replace(",", ""))
            if 2 <= n <= 10_000_000:
                n_eq_matches.append(n)
        except (ValueError, IndexError):
            continue
    if n_eq_matches:
        return n_eq_matches[0]  # First N= statement is typically primary

    # Priority 2: "enrolled X" — definitive enrollment count
    enrolled_pattern = _SAMPLE_SIZE_PATTERNS[6]  # r"enrolled\s+(\d[\d,]*)"
    for match in enrolled_pattern.finditer(text):
        try:
            n = int(match.group(1).replace(",", ""))
            if 2 <= n <= 10_000_000:
                return n
        except (ValueError, IndexError):
            continue

    # Priority 3: First plausible match from remaining patterns
    for pattern in _SAMPLE_SIZE_PATTERNS[1:6]:
        for match in pattern.finditer(text):
            try:
                n = int(match.group(1).replace(",", ""))
                if 2 <= n <= 10_000_000:
                    return n  # First match, not max
            except (ValueError, IndexError):
                continue

    return None


def detect_heuristic_signals(paper: PaperRecord) -> dict[str, Any]:
    """Extract quality signals from paper metadata without LLM."""
    text = f"{paper.title} {paper.abstract or ''}"

    design = detect_study_design(text)
    sample_size = extract_sample_size(text)
    study_count = extract_study_count(text) if design in (
        StudyDesign.META_ANALYSIS, StudyDesign.SYSTEMATIC_REVIEW
    ) else None
    has_control = bool(_CONTROL_GROUP_PATTERN.search(text))
    is_preregistered = bool(_PREREGISTRATION_PATTERN.search(text))
    has_open_data = bool(_OPEN_DATA_PATTERN.search(text))

    # Funding bias assessment
    has_industry = bool(_FUNDING_INDUSTRY_PATTERN.search(text))
    has_conflict_disclosure = bool(_CONFLICT_PATTERN.search(text))

    if has_industry and not has_conflict_disclosure:
        funding_bias = "high"
    elif has_industry and has_conflict_disclosure:
        funding_bias = "moderate"
    elif has_conflict_disclosure:
        funding_bias = "low"
    else:
        funding_bias = "unknown"

    # Citation signal
    citation_signal = "unknown"
    if paper.citation_count is not None:
        if paper.citation_count >= 100:
            citation_signal = "high_impact"
        elif paper.citation_count >= 20:
            citation_signal = "moderate_impact"
        elif paper.citation_count >= 5:
            citation_signal = "low_impact"
        else:
            citation_signal = "minimal_impact"

    return {
        "study_design": design,
        "design_strength": DESIGN_STRENGTH[design],
        "sample_size": sample_size,
        "study_count": study_count,
        "has_control_group": has_control,
        "is_preregistered": is_preregistered,
        "has_open_data": has_open_data,
        "funding_bias_risk": funding_bias,
        "citation_signal": citation_signal,
    }


# ── LLM-based deep quality assessment ────────────────────────────────

QUALITY_SYSTEM_PROMPT = """\
You are a research methodology expert. Assess the quality of academic papers \
based on their title, abstract, and metadata.

For each paper, evaluate these dimensions (score 0.0 to 1.0):

1. **methodology_rigor**: How sound is the study design? (RCTs > observational > case reports)
2. **sample_adequacy**: Is the sample size sufficient for the claims made?
3. **bias_risk**: How well are biases controlled? (inverse: high score = low bias risk)
4. **reproducibility**: Are methods described clearly enough to replicate?
5. **statistical_rigor**: Are appropriate statistical methods mentioned?

Output JSON:
{
  "assessments": [
    {
      "paper_index": 0,
      "methodology_rigor": {"score": 0.8, "rationale": "Well-designed RCT with clear protocol"},
      "sample_adequacy": {"score": 0.7, "rationale": "N=200, adequate for primary outcome"},
      "bias_risk": {"score": 0.6, "rationale": "Single-blind only, allocation unclear"},
      "reproducibility": {"score": 0.8, "rationale": "Detailed methods, registered protocol"},
      "statistical_rigor": {"score": 0.7, "rationale": "ITT analysis, confidence intervals reported"},
      "study_design_detected": "rct",
      "key_strengths": ["Pre-registered", "Large sample"],
      "key_limitations": ["Single-blind", "Short follow-up"]
    }
  ]
}

Rules:
- Score 0.0-1.0 for each dimension
- Always provide specific rationale referencing the paper content
- If information is insufficient, score 0.3-0.5 and note the limitation
"""


class QualityScorer:
    """Proprietary evidence quality assessment engine.

    Combines fast heuristic signals (regex-based) with deep LLM assessment
    to produce composite quality scores for academic papers.
    """

    BATCH_SIZE = 5

    def __init__(self, llm: BaseLLM) -> None:
        self._llm = llm

    async def score_papers(
        self, papers: list[PaperRecord]
    ) -> list[EvidenceQualityScore]:
        """Score all papers, returning quality assessments in order."""
        scores: list[EvidenceQualityScore] = []

        for batch_start in range(0, len(papers), self.BATCH_SIZE):
            batch = papers[batch_start: batch_start + self.BATCH_SIZE]
            batch_scores = await self._score_batch(batch)
            scores.extend(batch_scores)

            if batch_start + self.BATCH_SIZE < len(papers):
                await asyncio.sleep(0.5)

        return scores

    async def _score_batch(
        self, papers: list[PaperRecord]
    ) -> list[EvidenceQualityScore]:
        """Score a batch of papers combining heuristics + LLM."""
        # Step 1: Fast heuristic signals for each paper
        heuristics = [detect_heuristic_signals(p) for p in papers]

        # Step 2: LLM deep assessment
        llm_assessments = await self._llm_assess(papers)

        # Step 3: Combine heuristics + LLM into composite scores
        results: list[EvidenceQualityScore] = []
        for i, paper in enumerate(papers):
            h = heuristics[i]
            llm_data = llm_assessments.get(i, {})
            score = self._build_composite_score(paper, h, llm_data)
            results.append(score)

        return results

    async def _llm_assess(
        self, papers: list[PaperRecord]
    ) -> dict[int, dict[str, Any]]:
        """Run LLM quality assessment on a batch."""
        papers_text = self._format_papers(papers)

        try:
            response = await self._llm.chat(
                messages=[
                    {"role": "system", "content": QUALITY_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Assess these papers:\n\n{papers_text}"},
                ],
                temperature=0.0,
                response_format="json",
            )
            data = response.as_json()
            assessments = data.get("assessments", [])
            return {
                a.get("paper_index", i): a
                for i, a in enumerate(assessments)
            }
        except Exception as exc:
            logger.warning("quality_llm_failed", error=str(exc))
            return {}

    def _build_composite_score(
        self,
        paper: PaperRecord,
        heuristics: dict[str, Any],
        llm_data: dict[str, Any],
    ) -> EvidenceQualityScore:
        """Merge heuristic + LLM signals into a final quality score."""
        dimensions: list[QualityDimension] = []
        design = heuristics["study_design"]

        # Dimension 1: Methodology Rigor
        llm_methodology = llm_data.get("methodology_rigor", {})
        methodology_score = self._blend_scores(
            heuristic=heuristics["design_strength"],
            llm=llm_methodology.get("score"),
            heuristic_weight=0.4,
        )
        signals = [f"Design: {design.value}"]
        if heuristics["has_control_group"]:
            signals.append("Control group present")
        dimensions.append(QualityDimension(
            name="methodology_rigor",
            score=methodology_score,
            rationale=llm_methodology.get("rationale", f"Study design: {design.value}"),
            signals=signals,
        ))

        # Dimension 2: Sample Adequacy
        llm_sample = llm_data.get("sample_adequacy", {})
        sample_heuristic = self._sample_size_score(
            heuristics["sample_size"], design, heuristics.get("study_count"),
        )
        sample_score = self._blend_scores(
            heuristic=sample_heuristic,
            llm=llm_sample.get("score"),
            heuristic_weight=0.3,
        )
        sample_signals = []
        if heuristics["sample_size"]:
            sample_signals.append(f"N={heuristics['sample_size']}")
        dimensions.append(QualityDimension(
            name="sample_adequacy",
            score=sample_score,
            rationale=llm_sample.get("rationale", self._sample_rationale(heuristics["sample_size"])),
            signals=sample_signals,
        ))

        # Dimension 3: Bias Risk (inverse — high score = low bias)
        llm_bias = llm_data.get("bias_risk", {})
        bias_heuristic = self._bias_heuristic_score(heuristics)
        bias_score = self._blend_scores(
            heuristic=bias_heuristic,
            llm=llm_bias.get("score"),
            heuristic_weight=0.3,
        )
        bias_signals = []
        if heuristics["is_preregistered"]:
            bias_signals.append("Pre-registered")
        if heuristics["funding_bias_risk"] != "unknown":
            bias_signals.append(f"Funding bias: {heuristics['funding_bias_risk']}")
        dimensions.append(QualityDimension(
            name="bias_risk",
            score=bias_score,
            rationale=llm_bias.get("rationale", f"Funding bias risk: {heuristics['funding_bias_risk']}"),
            signals=bias_signals,
        ))

        # Dimension 4: Reproducibility
        llm_repro = llm_data.get("reproducibility", {})
        repro_heuristic = self._reproducibility_heuristic(heuristics)
        repro_score = self._blend_scores(
            heuristic=repro_heuristic,
            llm=llm_repro.get("score"),
            heuristic_weight=0.3,
        )
        repro_signals = []
        if heuristics["has_open_data"]:
            repro_signals.append("Open data/code available")
        if heuristics["is_preregistered"]:
            repro_signals.append("Pre-registered protocol")
        dimensions.append(QualityDimension(
            name="reproducibility",
            score=repro_score,
            rationale=llm_repro.get("rationale", "Based on data availability and protocol registration"),
            signals=repro_signals,
        ))

        # Dimension 5: Statistical Rigor
        llm_stats = llm_data.get("statistical_rigor", {})
        stats_heuristic = self._stats_rigor_baseline(design)
        stats_score = self._blend_scores(
            heuristic=stats_heuristic,
            llm=llm_stats.get("score"),
            heuristic_weight=0.25,
        )
        dimensions.append(QualityDimension(
            name="statistical_rigor",
            score=stats_score,
            rationale=llm_stats.get("rationale", "Statistical methods assessment"),
            signals=[],
        ))

        # ── Composite overall score ──
        weights = {
            "methodology_rigor": 0.30,
            "sample_adequacy": 0.20,
            "bias_risk": 0.20,
            "reproducibility": 0.15,
            "statistical_rigor": 0.15,
        }
        overall = sum(
            d.score * weights.get(d.name, 0.2)
            for d in dimensions
        )
        overall = round(min(1.0, max(0.0, overall)), 3)

        grade = self._score_to_grade(overall)

        # Build summary
        strengths = llm_data.get("key_strengths", [])
        limitations = llm_data.get("key_limitations", [])
        summary_parts = []
        if strengths:
            summary_parts.append(f"Strengths: {', '.join(strengths[:3])}")
        if limitations:
            summary_parts.append(f"Limitations: {', '.join(limitations[:3])}")

        return EvidenceQualityScore(
            overall_score=overall,
            grade=grade,
            study_design=design,
            dimensions=dimensions,
            sample_size=heuristics["sample_size"],
            has_control_group=heuristics["has_control_group"],
            is_preregistered=heuristics["is_preregistered"],
            has_open_data=heuristics["has_open_data"],
            funding_bias_risk=heuristics["funding_bias_risk"],
            summary=". ".join(summary_parts) if summary_parts else f"Grade {grade} evidence ({design.value})",
        )

    @staticmethod
    def _blend_scores(
        heuristic: float,
        llm: float | None,
        heuristic_weight: float = 0.3,
    ) -> float:
        """Blend heuristic and LLM scores. Falls back to heuristic if no LLM."""
        if llm is not None:
            try:
                llm_val = max(0.0, min(1.0, float(llm)))
                return round(
                    heuristic * heuristic_weight + llm_val * (1 - heuristic_weight),
                    3,
                )
            except (TypeError, ValueError):
                pass
        return round(heuristic, 3)

    @staticmethod
    def _sample_size_score(
        n: int | None,
        design: StudyDesign,
        study_count: int | None = None,
    ) -> float:
        """Heuristic sample size adequacy score.

        For meta-analyses/systematic reviews, uses study_count (k) as the
        primary metric since pooled participant count N can be misleading.
        Falls back to participant count N with adjusted thresholds.
        """
        if design in (StudyDesign.META_ANALYSIS, StudyDesign.SYSTEMATIC_REVIEW):
            # Prefer study count (k) over participant count (N)
            if study_count is not None:
                if study_count >= 20:
                    return 0.95
                elif study_count >= 10:
                    return 0.8
                elif study_count >= 5:
                    return 0.6
                return 0.4
            # Fallback: use participant count with MA-appropriate thresholds
            if n is not None:
                if n >= 5000:
                    return 0.9
                elif n >= 1000:
                    return 0.75
                elif n >= 200:
                    return 0.6
                return 0.45
            return 0.4  # No size info at all

        if n is None:
            return 0.4  # Unknown — moderate penalty

        if design == StudyDesign.RCT:
            if n >= 500:
                return 0.95
            elif n >= 100:
                return 0.8
            elif n >= 30:
                return 0.6
            return 0.35
        elif design in (StudyDesign.COHORT, StudyDesign.CASE_CONTROL, StudyDesign.CROSS_SECTIONAL):
            if n >= 1000:
                return 0.9
            elif n >= 200:
                return 0.75
            elif n >= 50:
                return 0.55
            return 0.3
        elif design == StudyDesign.CASE_REPORT:
            return 0.2  # Always low for case reports
        return 0.4

    @staticmethod
    def _bias_heuristic_score(heuristics: dict[str, Any]) -> float:
        """Heuristic bias risk score (high = low bias risk)."""
        score = 0.4  # Baseline
        if heuristics["is_preregistered"]:
            score += 0.2
        if heuristics["has_control_group"]:
            score += 0.15
        if heuristics["funding_bias_risk"] == "low":
            score += 0.15  # Raised from 0.1 — proper disclosure is meaningful
        elif heuristics["funding_bias_risk"] == "moderate":
            score -= 0.05  # Industry + disclosure — slight penalty
        elif heuristics["funding_bias_risk"] == "high":
            score -= 0.15
        # Study design bonus: higher-evidence designs inherently control more bias
        design = heuristics.get("study_design", StudyDesign.UNKNOWN)
        if design in (StudyDesign.RCT, StudyDesign.META_ANALYSIS, StudyDesign.SYSTEMATIC_REVIEW):
            score += 0.1
        return min(1.0, max(0.0, score))

    @staticmethod
    def _reproducibility_heuristic(heuristics: dict[str, Any]) -> float:
        """Heuristic reproducibility score."""
        score = 0.35  # Baseline
        if heuristics["has_open_data"]:
            score += 0.3
        if heuristics["is_preregistered"]:
            score += 0.2
        return min(1.0, score)

    @staticmethod
    def _stats_rigor_baseline(design: StudyDesign) -> float:
        """Design-based baseline for statistical rigor.

        Higher-evidence study types inherently require more rigorous
        statistical methods, so the prior is higher.
        """
        baselines = {
            StudyDesign.META_ANALYSIS: 0.7,      # Requires pooling methods, heterogeneity tests
            StudyDesign.SYSTEMATIC_REVIEW: 0.6,   # Often narrative synthesis, less formal stats
            StudyDesign.RCT: 0.65,                # Requires ITT, power analysis, CI
            StudyDesign.COHORT: 0.55,             # Regression, survival analysis common
            StudyDesign.CASE_CONTROL: 0.5,        # Odds ratios, matching methods
            StudyDesign.CROSS_SECTIONAL: 0.45,    # Descriptive stats, correlations
            StudyDesign.CASE_REPORT: 0.2,         # Rarely has formal statistics
            StudyDesign.EXPERT_OPINION: 0.15,     # No statistical methods expected
            StudyDesign.UNKNOWN: 0.35,
        }
        return baselines.get(design, 0.35)

    @staticmethod
    def _sample_rationale(n: int | None) -> str:
        if n is None:
            return "Sample size not reported in abstract"
        if n >= 500:
            return f"Large sample (N={n})"
        if n >= 100:
            return f"Moderate sample (N={n})"
        if n >= 30:
            return f"Small sample (N={n})"
        return f"Very small sample (N={n})"

    @staticmethod
    def _score_to_grade(score: float) -> str:
        if score >= 0.8:
            return "A"
        if score >= 0.65:
            return "B"
        if score >= 0.5:
            return "C"
        if score >= 0.35:
            return "D"
        return "F"

    @staticmethod
    def _format_papers(papers: list[PaperRecord]) -> str:
        parts: list[str] = []
        for i, p in enumerate(papers):
            lines = [f"[{i}] Title: {p.title}"]
            if p.abstract:
                lines.append(f"    Abstract: {p.abstract[:800]}")
            if p.authors:
                lines.append(f"    Authors: {', '.join(p.authors[:5])}")
            if p.published_date:
                lines.append(f"    Date: {p.published_date}")
            if p.journal:
                lines.append(f"    Journal: {p.journal}")
            if p.citation_count is not None:
                lines.append(f"    Citations: {p.citation_count}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)
