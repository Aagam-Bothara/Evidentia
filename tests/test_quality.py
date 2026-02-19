"""Tests for the Evidence Quality Scoring module."""

import json

import pytest

from evidentia.core.llm import BaseLLM, LLMResponse
from evidentia.review.models import PaperRecord
from evidentia.review.quality import (
    DESIGN_STRENGTH,
    EvidenceQualityScore,
    QualityScorer,
    StudyDesign,
    detect_heuristic_signals,
    detect_study_design,
    extract_sample_size,
    extract_study_count,
)


# ── Mock LLM ─────────────────────────────────────────────────────────


class MockQualityLLM(BaseLLM):
    """Returns pre-configured quality assessment responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_index = 0

    async def chat(self, messages, temperature=0.0, max_tokens=4096, response_format=None):
        if self._call_index < len(self._responses):
            content = self._responses[self._call_index]
            self._call_index += 1
            return LLMResponse(content=content, usage={"total_tokens": 100})
        return LLMResponse(
            content='{"assessments": []}',
            usage={"total_tokens": 10},
        )

    async def chat_with_tools(self, messages, tools, temperature=0.0, max_tokens=4096):
        return await self.chat(messages, temperature, max_tokens)


class FailingLLM(BaseLLM):
    """LLM that always raises an exception."""

    async def chat(self, messages, temperature=0.0, max_tokens=4096, response_format=None):
        raise RuntimeError("LLM service unavailable")

    async def chat_with_tools(self, messages, tools, temperature=0.0, max_tokens=4096):
        raise RuntimeError("LLM service unavailable")


# ── Helpers ──────────────────────────────────────────────────────────


def _make_paper(
    title: str = "A Study",
    abstract: str | None = None,
    citation_count: int | None = None,
    **kwargs,
) -> PaperRecord:
    return PaperRecord(
        title=title,
        authors=kwargs.get("authors", ["Author A"]),
        abstract=abstract,
        source_database=kwargs.get("source_database", "pubmed_search"),
        source_id=kwargs.get("source_id", "pm1"),
        citation_count=citation_count,
        doi=kwargs.get("doi"),
        journal=kwargs.get("journal"),
        published_date=kwargs.get("published_date"),
    )


def _quality_response(assessments: list[dict]) -> str:
    return json.dumps({"assessments": assessments})


def _full_assessment(paper_index: int = 0, **overrides) -> dict:
    """Build a complete LLM assessment dict with sensible defaults."""
    base = {
        "paper_index": paper_index,
        "methodology_rigor": {"score": 0.8, "rationale": "Well-designed study"},
        "sample_adequacy": {"score": 0.7, "rationale": "Adequate sample"},
        "bias_risk": {"score": 0.6, "rationale": "Moderate bias control"},
        "reproducibility": {"score": 0.7, "rationale": "Methods described"},
        "statistical_rigor": {"score": 0.65, "rationale": "Appropriate stats"},
        "study_design_detected": "rct",
        "key_strengths": ["Pre-registered", "Large sample"],
        "key_limitations": ["Single-blind", "Short follow-up"],
    }
    base.update(overrides)
    return base


# ── Study design detection ───────────────────────────────────────────


class TestDetectStudyDesign:
    """Tests for detect_study_design function."""

    def test_meta_analysis(self):
        assert detect_study_design("A meta-analysis of RCTs") == StudyDesign.META_ANALYSIS

    def test_meta_analysis_no_hyphen(self):
        assert detect_study_design("A metaanalysis of drug efficacy") == StudyDesign.META_ANALYSIS

    def test_systematic_review(self):
        text = "Systematic review of dietary interventions"
        assert detect_study_design(text) == StudyDesign.SYSTEMATIC_REVIEW

    def test_rct_full_phrase(self):
        text = "A randomized controlled trial of aspirin"
        assert detect_study_design(text) == StudyDesign.RCT

    def test_rct_abbreviation(self):
        assert detect_study_design("An RCT comparing two drugs") == StudyDesign.RCT

    def test_rct_british_spelling(self):
        text = "A randomised controlled trial of statins"
        assert detect_study_design(text) == StudyDesign.RCT

    def test_cohort_study(self):
        text = "A prospective cohort study of 10,000 adults"
        assert detect_study_design(text) == StudyDesign.COHORT

    def test_longitudinal_study(self):
        text = "A longitudinal study of child development"
        assert detect_study_design(text) == StudyDesign.COHORT

    def test_retrospective_analysis(self):
        text = "Retrospective analysis of hospital records"
        assert detect_study_design(text) == StudyDesign.COHORT

    def test_case_control(self):
        text = "A case-control study of lung cancer risk factors"
        assert detect_study_design(text) == StudyDesign.CASE_CONTROL

    def test_case_control_no_hyphen(self):
        text = "Case control investigation of diabetes risk"
        assert detect_study_design(text) == StudyDesign.CASE_CONTROL

    def test_cross_sectional(self):
        text = "A cross-sectional survey of mental health"
        assert detect_study_design(text) == StudyDesign.CROSS_SECTIONAL

    def test_cross_sectional_no_hyphen(self):
        text = "Cross sectional study among healthcare workers"
        assert detect_study_design(text) == StudyDesign.CROSS_SECTIONAL

    def test_case_report(self):
        text = "Case report of rare cardiac event"
        assert detect_study_design(text) == StudyDesign.CASE_REPORT

    def test_case_series(self):
        text = "Case series of unusual infections"
        assert detect_study_design(text) == StudyDesign.CASE_REPORT

    def test_expert_opinion_editorial(self):
        text = "Editorial: The future of precision medicine"
        assert detect_study_design(text) == StudyDesign.EXPERT_OPINION

    def test_expert_opinion_commentary(self):
        text = "Commentary on recent vaccine developments"
        assert detect_study_design(text) == StudyDesign.EXPERT_OPINION

    def test_expert_opinion_letter(self):
        text = "Letter to the editor regarding trial results"
        assert detect_study_design(text) == StudyDesign.EXPERT_OPINION

    def test_unknown_design(self):
        text = "Exploring the molecular basis of cancer"
        assert detect_study_design(text) == StudyDesign.UNKNOWN

    def test_empty_string(self):
        assert detect_study_design("") == StudyDesign.UNKNOWN

    def test_priority_meta_analysis_over_rct(self):
        """Meta-analysis pattern should match first even if RCT is mentioned."""
        text = "A meta-analysis of randomized controlled trials"
        assert detect_study_design(text) == StudyDesign.META_ANALYSIS

    def test_case_insensitive(self):
        text = "A RANDOMIZED CONTROLLED TRIAL OF ASPIRIN"
        assert detect_study_design(text) == StudyDesign.RCT


# ── Sample size extraction ───────────────────────────────────────────


class TestExtractSampleSize:
    """Tests for extract_sample_size function."""

    def test_n_equals_format(self):
        assert extract_sample_size("We enrolled patients (n=200) from the clinic.") == 200

    def test_n_equals_with_spaces(self):
        assert extract_sample_size("The study had N = 350 patients.") == 350

    def test_participants(self):
        assert extract_sample_size("A total of 500 participants were enrolled.") == 500

    def test_patients(self):
        assert extract_sample_size("We recruited 120 patients from three hospitals.") == 120

    def test_subjects(self):
        assert extract_sample_size("The 85 subjects completed all visits.") == 85

    def test_sample_of(self):
        assert extract_sample_size("A sample of 450 was randomly selected.") == 450

    def test_sample_size_of(self):
        assert extract_sample_size("The sample size of 300 was sufficient.") == 300

    def test_individuals(self):
        assert extract_sample_size("We studied 1200 individuals over 5 years.") == 1200

    def test_enrolled_format(self):
        assert extract_sample_size("We enrolled 250 from primary care.") == 250

    def test_women(self):
        assert extract_sample_size("Data from 800 women were analyzed.") == 800

    def test_commas_in_number(self):
        assert extract_sample_size("Included 12,345 participants in the analysis.") == 12345

    def test_multiple_sizes_returns_first_participant_match(self):
        text = "From 1000 participants, 200 patients completed follow-up."
        assert extract_sample_size(text) == 1000

    def test_n_equals_prioritized_over_larger_screening_count(self):
        """N= is prioritized even when a larger screening number appears first."""
        text = "Of 5000 patients screened, we enrolled those eligible (n=200)."
        assert extract_sample_size(text) == 200

    def test_enrolled_prioritized_over_screening(self):
        """'Enrolled' matches are preferred over generic 'participants' matches."""
        text = "After screening 3000 participants, we enrolled 450 into the trial."
        assert extract_sample_size(text) == 450

    def test_no_sample_size(self):
        text = "This paper reviews current literature."
        assert extract_sample_size(text) is None

    def test_empty_string(self):
        assert extract_sample_size("") is None

    def test_number_too_small(self):
        """Numbers below 2 are excluded as implausible sample sizes."""
        assert extract_sample_size("n=1 case was identified.") is None

    def test_number_at_lower_boundary(self):
        """n=2 is the minimum accepted sample size."""
        assert extract_sample_size("n=2 twins were studied.") == 2

    def test_very_large_sample(self):
        """Large but plausible sample sizes should be extracted."""
        assert extract_sample_size("Data from 5,000,000 participants.") == 5000000

    def test_number_above_ten_million_excluded(self):
        """Numbers > 10,000,000 are excluded as implausible."""
        assert extract_sample_size("n=20000000 records in the database.") is None


# ── Study count extraction (meta-analyses) ─────────────────────────


class TestExtractStudyCount:
    """Tests for extract_study_count function."""

    def test_included_studies(self):
        assert extract_study_count("We included 15 studies in the meta-analysis.") == 15

    def test_k_equals_format(self):
        assert extract_study_count("A total of k=23 trials were pooled.") == 23

    def test_studies_were_included(self):
        assert extract_study_count("42 studies were included after screening.") == 42

    def test_across_studies(self):
        assert extract_study_count("Data from across 8 studies were combined.") == 8

    def test_trials_met_criteria(self):
        assert extract_study_count("12 trials met the inclusion criteria.") == 12

    def test_no_study_count(self):
        assert extract_study_count("A randomized trial of 500 participants.") is None

    def test_empty_string(self):
        assert extract_study_count("") is None


# ── Heuristic signals ────────────────────────────────────────────────


class TestDetectHeuristicSignals:
    """Tests for detect_heuristic_signals function."""

    def test_detects_study_design(self):
        paper = _make_paper(
            title="A randomized controlled trial of vitamin D",
            abstract="We conducted an RCT with 200 participants.",
        )
        signals = detect_heuristic_signals(paper)
        assert signals["study_design"] == StudyDesign.RCT
        assert signals["design_strength"] == DESIGN_STRENGTH[StudyDesign.RCT]

    def test_detects_sample_size(self):
        paper = _make_paper(abstract="We enrolled 500 participants in the study.")
        signals = detect_heuristic_signals(paper)
        assert signals["sample_size"] == 500

    def test_detects_preregistration_prospero(self):
        paper = _make_paper(abstract="Registered on PROSPERO (CRD42021...).")
        signals = detect_heuristic_signals(paper)
        assert signals["is_preregistered"] is True

    def test_detects_preregistration_clinicaltrials(self):
        paper = _make_paper(abstract="Trial registered at ClinicalTrials.gov NCT0001.")
        signals = detect_heuristic_signals(paper)
        assert signals["is_preregistered"] is True

    def test_detects_preregistration_osf(self):
        paper = _make_paper(abstract="Pre-registered protocol available on OSF.")
        signals = detect_heuristic_signals(paper)
        assert signals["is_preregistered"] is True

    def test_no_preregistration(self):
        paper = _make_paper(abstract="We studied the effect of exercise.")
        signals = detect_heuristic_signals(paper)
        assert signals["is_preregistered"] is False

    def test_detects_open_data_github(self):
        paper = _make_paper(abstract="Code is available at github.com/repo.")
        signals = detect_heuristic_signals(paper)
        assert signals["has_open_data"] is True

    def test_detects_open_data_zenodo(self):
        paper = _make_paper(abstract="Data deposited on Zenodo.")
        signals = detect_heuristic_signals(paper)
        assert signals["has_open_data"] is True

    def test_detects_data_availability(self):
        paper = _make_paper(abstract="Open data deposited in the public repository.")
        signals = detect_heuristic_signals(paper)
        assert signals["has_open_data"] is True

    def test_no_open_data(self):
        paper = _make_paper(abstract="A study of 100 patients.")
        signals = detect_heuristic_signals(paper)
        assert signals["has_open_data"] is False

    def test_detects_control_group(self):
        paper = _make_paper(abstract="Compared to a control group receiving placebo.")
        signals = detect_heuristic_signals(paper)
        assert signals["has_control_group"] is True

    def test_detects_placebo(self):
        paper = _make_paper(abstract="Patients were randomized to drug or placebo.")
        signals = detect_heuristic_signals(paper)
        assert signals["has_control_group"] is True

    def test_no_control_group(self):
        paper = _make_paper(abstract="An observational study of outcomes.")
        signals = detect_heuristic_signals(paper)
        assert signals["has_control_group"] is False

    def test_funding_bias_high(self):
        """Industry-funded with no conflict disclosure = high bias."""
        paper = _make_paper(
            abstract="This study was funded by the pharma company for efficacy evaluation."
        )
        signals = detect_heuristic_signals(paper)
        assert signals["funding_bias_risk"] == "high"

    def test_funding_bias_moderate(self):
        """Industry-funded with conflict disclosure = moderate bias."""
        paper = _make_paper(
            abstract=(
                "Supported by a grant from the pharma industry. "
                "The authors report no conflict of interest."
            )
        )
        signals = detect_heuristic_signals(paper)
        assert signals["funding_bias_risk"] == "moderate"

    def test_funding_bias_low(self):
        """Conflict disclosure without industry funding = low bias."""
        paper = _make_paper(
            abstract="The authors report no conflict of interest."
        )
        signals = detect_heuristic_signals(paper)
        assert signals["funding_bias_risk"] == "low"

    def test_funding_bias_unknown(self):
        """No funding or conflict signals = unknown bias."""
        paper = _make_paper(abstract="A study of outcomes in healthy adults.")
        signals = detect_heuristic_signals(paper)
        assert signals["funding_bias_risk"] == "unknown"

    def test_citation_signal_high_impact(self):
        paper = _make_paper(abstract="A study.", citation_count=150)
        signals = detect_heuristic_signals(paper)
        assert signals["citation_signal"] == "high_impact"

    def test_citation_signal_moderate_impact(self):
        paper = _make_paper(abstract="A study.", citation_count=50)
        signals = detect_heuristic_signals(paper)
        assert signals["citation_signal"] == "moderate_impact"

    def test_citation_signal_low_impact(self):
        paper = _make_paper(abstract="A study.", citation_count=10)
        signals = detect_heuristic_signals(paper)
        assert signals["citation_signal"] == "low_impact"

    def test_citation_signal_minimal_impact(self):
        paper = _make_paper(abstract="A study.", citation_count=2)
        signals = detect_heuristic_signals(paper)
        assert signals["citation_signal"] == "minimal_impact"

    def test_citation_signal_unknown_when_none(self):
        paper = _make_paper(abstract="A study.", citation_count=None)
        signals = detect_heuristic_signals(paper)
        assert signals["citation_signal"] == "unknown"

    def test_none_abstract_handled(self):
        """Paper with no abstract should not crash."""
        paper = _make_paper(title="Some RCT title", abstract=None)
        signals = detect_heuristic_signals(paper)
        assert signals["study_design"] == StudyDesign.RCT


# ── QualityScorer: _score_to_grade ───────────────────────────────────


class TestScoreToGrade:
    """Tests for the grade assignment boundaries."""

    def test_grade_a(self):
        assert QualityScorer._score_to_grade(0.85) == "A"

    def test_grade_a_boundary(self):
        assert QualityScorer._score_to_grade(0.8) == "A"

    def test_grade_b(self):
        assert QualityScorer._score_to_grade(0.72) == "B"

    def test_grade_b_boundary(self):
        assert QualityScorer._score_to_grade(0.65) == "B"

    def test_grade_c(self):
        assert QualityScorer._score_to_grade(0.55) == "C"

    def test_grade_c_boundary(self):
        assert QualityScorer._score_to_grade(0.5) == "C"

    def test_grade_d(self):
        assert QualityScorer._score_to_grade(0.42) == "D"

    def test_grade_d_boundary(self):
        assert QualityScorer._score_to_grade(0.35) == "D"

    def test_grade_f(self):
        assert QualityScorer._score_to_grade(0.2) == "F"

    def test_grade_f_zero(self):
        assert QualityScorer._score_to_grade(0.0) == "F"

    def test_grade_a_perfect(self):
        assert QualityScorer._score_to_grade(1.0) == "A"

    def test_grade_just_below_a(self):
        assert QualityScorer._score_to_grade(0.799) == "B"

    def test_grade_just_below_b(self):
        assert QualityScorer._score_to_grade(0.649) == "C"


# ── QualityScorer: _blend_scores ─────────────────────────────────────


class TestBlendScores:
    """Tests for score blending logic."""

    def test_blend_with_llm_score(self):
        """Blends heuristic and LLM using specified weights."""
        result = QualityScorer._blend_scores(heuristic=0.6, llm=0.8, heuristic_weight=0.4)
        # 0.6 * 0.4 + 0.8 * 0.6 = 0.24 + 0.48 = 0.72
        assert result == 0.72

    def test_blend_without_llm_falls_back_to_heuristic(self):
        """No LLM score should fall back to pure heuristic."""
        result = QualityScorer._blend_scores(heuristic=0.7, llm=None, heuristic_weight=0.3)
        assert result == 0.7

    def test_blend_llm_clamped_above_one(self):
        """LLM score > 1.0 should be clamped to 1.0 before blending."""
        result = QualityScorer._blend_scores(heuristic=0.5, llm=1.5, heuristic_weight=0.3)
        # 0.5 * 0.3 + 1.0 * 0.7 = 0.15 + 0.70 = 0.85
        assert result == 0.85

    def test_blend_llm_clamped_below_zero(self):
        """LLM score < 0.0 should be clamped to 0.0 before blending."""
        result = QualityScorer._blend_scores(heuristic=0.5, llm=-0.5, heuristic_weight=0.3)
        # 0.5 * 0.3 + 0.0 * 0.7 = 0.15
        assert result == 0.15

    def test_blend_invalid_llm_type_falls_back(self):
        """Non-numeric LLM value should fall back to heuristic."""
        result = QualityScorer._blend_scores(heuristic=0.6, llm="bad", heuristic_weight=0.3)
        assert result == 0.6

    def test_blend_heuristic_weight_zero(self):
        """With heuristic_weight=0, result should be pure LLM score."""
        result = QualityScorer._blend_scores(heuristic=0.3, llm=0.9, heuristic_weight=0.0)
        assert result == 0.9

    def test_blend_heuristic_weight_one(self):
        """With heuristic_weight=1, result should be pure heuristic score."""
        result = QualityScorer._blend_scores(heuristic=0.3, llm=0.9, heuristic_weight=1.0)
        assert result == 0.3


# ── QualityScorer: _sample_size_score ────────────────────────────────


class TestSampleSizeScore:
    """Tests for _sample_size_score across study designs."""

    def test_none_sample_size(self):
        assert QualityScorer._sample_size_score(None, StudyDesign.RCT) == 0.4

    # Meta-analysis / Systematic review thresholds (with study_count)
    def test_meta_analysis_large_study_count(self):
        assert QualityScorer._sample_size_score(None, StudyDesign.META_ANALYSIS, study_count=25) == 0.95

    def test_meta_analysis_medium_study_count(self):
        assert QualityScorer._sample_size_score(None, StudyDesign.META_ANALYSIS, study_count=15) == 0.8

    def test_meta_analysis_small_study_count(self):
        assert QualityScorer._sample_size_score(None, StudyDesign.META_ANALYSIS, study_count=5) == 0.6

    def test_meta_analysis_very_small_study_count(self):
        assert QualityScorer._sample_size_score(None, StudyDesign.META_ANALYSIS, study_count=3) == 0.4

    def test_systematic_review_large_study_count(self):
        assert QualityScorer._sample_size_score(None, StudyDesign.SYSTEMATIC_REVIEW, study_count=30) == 0.95

    # Meta-analysis fallback to participant count (no study_count)
    def test_meta_analysis_large_participants(self):
        assert QualityScorer._sample_size_score(6000, StudyDesign.META_ANALYSIS) == 0.9

    def test_meta_analysis_moderate_participants(self):
        assert QualityScorer._sample_size_score(1500, StudyDesign.META_ANALYSIS) == 0.75

    def test_meta_analysis_small_participants(self):
        assert QualityScorer._sample_size_score(300, StudyDesign.META_ANALYSIS) == 0.6

    def test_meta_analysis_no_size_info(self):
        assert QualityScorer._sample_size_score(None, StudyDesign.META_ANALYSIS) == 0.4

    # RCT thresholds
    def test_rct_very_large(self):
        assert QualityScorer._sample_size_score(1000, StudyDesign.RCT) == 0.95

    def test_rct_large(self):
        assert QualityScorer._sample_size_score(200, StudyDesign.RCT) == 0.8

    def test_rct_moderate(self):
        assert QualityScorer._sample_size_score(50, StudyDesign.RCT) == 0.6

    def test_rct_small(self):
        assert QualityScorer._sample_size_score(15, StudyDesign.RCT) == 0.35

    # Cohort / Case-control / Cross-sectional thresholds
    def test_cohort_very_large(self):
        assert QualityScorer._sample_size_score(2000, StudyDesign.COHORT) == 0.9

    def test_cohort_large(self):
        assert QualityScorer._sample_size_score(500, StudyDesign.COHORT) == 0.75

    def test_cohort_moderate(self):
        assert QualityScorer._sample_size_score(100, StudyDesign.COHORT) == 0.55

    def test_cohort_small(self):
        assert QualityScorer._sample_size_score(20, StudyDesign.COHORT) == 0.3

    def test_case_control_large(self):
        assert QualityScorer._sample_size_score(1500, StudyDesign.CASE_CONTROL) == 0.9

    def test_cross_sectional_moderate(self):
        assert QualityScorer._sample_size_score(300, StudyDesign.CROSS_SECTIONAL) == 0.75

    # Case report is always low
    def test_case_report_always_low(self):
        assert QualityScorer._sample_size_score(5, StudyDesign.CASE_REPORT) == 0.2

    def test_case_report_even_large_n(self):
        assert QualityScorer._sample_size_score(1000, StudyDesign.CASE_REPORT) == 0.2

    # Unknown / Expert opinion fall through to default
    def test_expert_opinion_default(self):
        assert QualityScorer._sample_size_score(100, StudyDesign.EXPERT_OPINION) == 0.4

    def test_unknown_design_default(self):
        assert QualityScorer._sample_size_score(100, StudyDesign.UNKNOWN) == 0.4


# ── QualityScorer: _bias_heuristic_score ─────────────────────────────


class TestBiasHeuristicScore:
    """Tests for _bias_heuristic_score."""

    def test_baseline_score(self):
        """Minimal heuristics yield baseline 0.4."""
        h = {
            "is_preregistered": False,
            "has_control_group": False,
            "funding_bias_risk": "unknown",
            "study_design": StudyDesign.CROSS_SECTIONAL,
        }
        assert QualityScorer._bias_heuristic_score(h) == 0.4

    def test_preregistered_boost(self):
        h = {
            "is_preregistered": True,
            "has_control_group": False,
            "funding_bias_risk": "unknown",
            "study_design": StudyDesign.COHORT,
        }
        assert QualityScorer._bias_heuristic_score(h) == pytest.approx(0.6)

    def test_control_group_boost(self):
        h = {
            "is_preregistered": False,
            "has_control_group": True,
            "funding_bias_risk": "unknown",
            "study_design": StudyDesign.COHORT,
        }
        assert QualityScorer._bias_heuristic_score(h) == pytest.approx(0.55)

    def test_low_funding_bias_boost(self):
        h = {
            "is_preregistered": False,
            "has_control_group": False,
            "funding_bias_risk": "low",
            "study_design": StudyDesign.COHORT,
        }
        # 0.4 + 0.15 (low funding) = 0.55
        assert QualityScorer._bias_heuristic_score(h) == pytest.approx(0.55)

    def test_moderate_funding_bias_penalty(self):
        h = {
            "is_preregistered": False,
            "has_control_group": False,
            "funding_bias_risk": "moderate",
            "study_design": StudyDesign.COHORT,
        }
        # 0.4 - 0.05 = 0.35
        assert QualityScorer._bias_heuristic_score(h) == pytest.approx(0.35)

    def test_high_funding_bias_penalty(self):
        h = {
            "is_preregistered": False,
            "has_control_group": False,
            "funding_bias_risk": "high",
            "study_design": StudyDesign.COHORT,
        }
        assert QualityScorer._bias_heuristic_score(h) == pytest.approx(0.25)

    def test_rct_design_bonus(self):
        """RCTs get a +0.1 design bonus for inherent bias control."""
        h = {
            "is_preregistered": False,
            "has_control_group": False,
            "funding_bias_risk": "unknown",
            "study_design": StudyDesign.RCT,
        }
        # 0.4 + 0.1 (RCT design bonus) = 0.5
        assert QualityScorer._bias_heuristic_score(h) == pytest.approx(0.5)

    def test_all_positive_signals_rct(self):
        h = {
            "is_preregistered": True,
            "has_control_group": True,
            "funding_bias_risk": "low",
            "study_design": StudyDesign.RCT,
        }
        result = QualityScorer._bias_heuristic_score(h)
        assert result <= 1.0
        # 0.4 + 0.2 + 0.15 + 0.15 + 0.1 (RCT) = 1.0
        assert result == pytest.approx(1.0)


# ── QualityScorer: _reproducibility_heuristic ────────────────────────


class TestReproducibilityHeuristic:
    """Tests for _reproducibility_heuristic."""

    def test_baseline(self):
        h = {"has_open_data": False, "is_preregistered": False}
        assert QualityScorer._reproducibility_heuristic(h) == 0.35

    def test_open_data_boost(self):
        h = {"has_open_data": True, "is_preregistered": False}
        assert QualityScorer._reproducibility_heuristic(h) == pytest.approx(0.65)

    def test_preregistered_boost(self):
        h = {"has_open_data": False, "is_preregistered": True}
        assert QualityScorer._reproducibility_heuristic(h) == pytest.approx(0.55)

    def test_both_signals_capped_at_one(self):
        h = {"has_open_data": True, "is_preregistered": True}
        # 0.35 + 0.3 + 0.2 = 0.85
        result = QualityScorer._reproducibility_heuristic(h)
        assert result == pytest.approx(0.85)
        assert result <= 1.0


# ── QualityScorer: _sample_rationale ─────────────────────────────────


class TestSampleRationale:
    """Tests for _sample_rationale text generation."""

    def test_none_sample(self):
        assert "not reported" in QualityScorer._sample_rationale(None)

    def test_large_sample(self):
        r = QualityScorer._sample_rationale(600)
        assert "Large" in r
        assert "600" in r

    def test_moderate_sample(self):
        r = QualityScorer._sample_rationale(150)
        assert "Moderate" in r

    def test_small_sample(self):
        r = QualityScorer._sample_rationale(40)
        assert "Small" in r

    def test_very_small_sample(self):
        r = QualityScorer._sample_rationale(10)
        assert "Very small" in r


# ── QualityScorer: _build_composite_score ────────────────────────────


class TestBuildCompositeScore:
    """Tests for _build_composite_score merging heuristics + LLM data."""

    def _make_scorer(self) -> QualityScorer:
        return QualityScorer(MockQualityLLM([]))

    def _base_heuristics(self, **overrides) -> dict:
        h = {
            "study_design": StudyDesign.RCT,
            "design_strength": DESIGN_STRENGTH[StudyDesign.RCT],
            "sample_size": 200,
            "study_count": None,
            "has_control_group": True,
            "is_preregistered": True,
            "has_open_data": True,
            "funding_bias_risk": "low",
            "citation_signal": "moderate_impact",
        }
        h.update(overrides)
        return h

    def test_full_llm_data_produces_score(self):
        scorer = self._make_scorer()
        paper = _make_paper(title="A Randomized Controlled Trial", abstract="n=200 participants")
        llm_data = _full_assessment()
        heuristics = self._base_heuristics()

        result = scorer._build_composite_score(paper, heuristics, llm_data)

        assert isinstance(result, EvidenceQualityScore)
        assert 0.0 <= result.overall_score <= 1.0
        assert result.grade in ("A", "B", "C", "D", "F")
        assert result.study_design == StudyDesign.RCT
        assert result.sample_size == 200
        assert result.has_control_group is True
        assert result.is_preregistered is True
        assert result.has_open_data is True
        assert result.funding_bias_risk == "low"
        assert len(result.dimensions) == 5

    def test_no_llm_data_heuristic_fallback(self):
        """Empty LLM data should still produce a valid score from heuristics only."""
        scorer = self._make_scorer()
        paper = _make_paper(title="A Cohort Study", abstract="200 participants")
        heuristics = self._base_heuristics(study_design=StudyDesign.COHORT,
                                            design_strength=DESIGN_STRENGTH[StudyDesign.COHORT])

        result = scorer._build_composite_score(paper, heuristics, {})

        assert isinstance(result, EvidenceQualityScore)
        assert 0.0 <= result.overall_score <= 1.0
        assert result.grade in ("A", "B", "C", "D", "F")
        assert len(result.dimensions) == 5

    def test_five_dimensions_present(self):
        scorer = self._make_scorer()
        paper = _make_paper()
        heuristics = self._base_heuristics()
        result = scorer._build_composite_score(paper, heuristics, _full_assessment())

        dim_names = [d.name for d in result.dimensions]
        assert "methodology_rigor" in dim_names
        assert "sample_adequacy" in dim_names
        assert "bias_risk" in dim_names
        assert "reproducibility" in dim_names
        assert "statistical_rigor" in dim_names

    def test_dimension_scores_in_range(self):
        scorer = self._make_scorer()
        paper = _make_paper()
        heuristics = self._base_heuristics()
        result = scorer._build_composite_score(paper, heuristics, _full_assessment())

        for dim in result.dimensions:
            assert 0.0 <= dim.score <= 1.0, f"{dim.name} score out of range: {dim.score}"

    def test_summary_with_llm_strengths_and_limitations(self):
        scorer = self._make_scorer()
        paper = _make_paper()
        heuristics = self._base_heuristics()
        llm_data = _full_assessment(
            key_strengths=["Large sample", "Blinded"],
            key_limitations=["Short follow-up"],
        )
        result = scorer._build_composite_score(paper, heuristics, llm_data)

        assert "Strengths:" in result.summary
        assert "Large sample" in result.summary
        assert "Limitations:" in result.summary
        assert "Short follow-up" in result.summary

    def test_summary_without_llm_uses_default(self):
        scorer = self._make_scorer()
        paper = _make_paper()
        heuristics = self._base_heuristics()
        result = scorer._build_composite_score(paper, heuristics, {})

        assert "Grade" in result.summary
        assert result.grade in result.summary

    def test_control_group_signal_in_methodology(self):
        scorer = self._make_scorer()
        paper = _make_paper()
        heuristics = self._base_heuristics(has_control_group=True)
        result = scorer._build_composite_score(paper, heuristics, {})

        method_dim = [d for d in result.dimensions if d.name == "methodology_rigor"][0]
        assert "Control group present" in method_dim.signals

    def test_preregistered_signal_in_bias(self):
        scorer = self._make_scorer()
        paper = _make_paper()
        heuristics = self._base_heuristics(is_preregistered=True)
        result = scorer._build_composite_score(paper, heuristics, {})

        bias_dim = [d for d in result.dimensions if d.name == "bias_risk"][0]
        assert "Pre-registered" in bias_dim.signals

    def test_open_data_signal_in_reproducibility(self):
        scorer = self._make_scorer()
        paper = _make_paper()
        heuristics = self._base_heuristics(has_open_data=True)
        result = scorer._build_composite_score(paper, heuristics, {})

        repro_dim = [d for d in result.dimensions if d.name == "reproducibility"][0]
        assert "Open data/code available" in repro_dim.signals

    def test_high_quality_rct_gets_high_score(self):
        """Well-powered RCT with all positive signals should score well."""
        scorer = self._make_scorer()
        paper = _make_paper()
        heuristics = self._base_heuristics(
            study_design=StudyDesign.RCT,
            design_strength=DESIGN_STRENGTH[StudyDesign.RCT],
            sample_size=500,
        )
        llm_data = _full_assessment(
            methodology_rigor={"score": 0.9, "rationale": "Excellent RCT"},
            sample_adequacy={"score": 0.9, "rationale": "Large sample"},
            bias_risk={"score": 0.85, "rationale": "Well controlled"},
            reproducibility={"score": 0.85, "rationale": "Open and registered"},
            statistical_rigor={"score": 0.8, "rationale": "Rigorous stats"},
        )
        result = scorer._build_composite_score(paper, heuristics, llm_data)
        assert result.grade in ("A", "B")
        assert result.overall_score >= 0.65

    def test_case_report_low_score(self):
        """Case report with minimal signals should score low."""
        scorer = self._make_scorer()
        paper = _make_paper()
        heuristics = self._base_heuristics(
            study_design=StudyDesign.CASE_REPORT,
            design_strength=DESIGN_STRENGTH[StudyDesign.CASE_REPORT],
            sample_size=3,
            has_control_group=False,
            is_preregistered=False,
            has_open_data=False,
            funding_bias_risk="unknown",
        )
        # Low LLM scores for a weak study
        llm_data = _full_assessment(
            methodology_rigor={"score": 0.2, "rationale": "Case report only"},
            sample_adequacy={"score": 0.15, "rationale": "N=3"},
            bias_risk={"score": 0.25, "rationale": "No controls"},
            reproducibility={"score": 0.2, "rationale": "No protocol"},
            statistical_rigor={"score": 0.1, "rationale": "Descriptive only"},
        )
        result = scorer._build_composite_score(paper, heuristics, llm_data)
        assert result.grade in ("D", "F")
        assert result.overall_score < 0.5


# ── QualityScorer: score_papers (async integration) ──────────────────


class TestScorePapers:
    """Async tests for the full score_papers pipeline with mock LLM."""

    @pytest.mark.asyncio
    async def test_score_single_paper(self):
        response = _quality_response([_full_assessment(paper_index=0)])
        llm = MockQualityLLM([response])
        scorer = QualityScorer(llm)

        papers = [_make_paper(
            title="Randomized controlled trial of aspirin",
            abstract="We enrolled 200 participants in this RCT. Registered at ClinicalTrials.gov.",
        )]
        results = await scorer.score_papers(papers)

        assert len(results) == 1
        assert isinstance(results[0], EvidenceQualityScore)
        assert 0.0 <= results[0].overall_score <= 1.0
        assert results[0].grade in ("A", "B", "C", "D", "F")

    @pytest.mark.asyncio
    async def test_score_multiple_papers(self):
        response = _quality_response([
            _full_assessment(paper_index=0),
            _full_assessment(paper_index=1),
            _full_assessment(paper_index=2),
        ])
        llm = MockQualityLLM([response])
        scorer = QualityScorer(llm)

        papers = [
            _make_paper(title=f"Study {i}", abstract=f"{i*100} participants")
            for i in range(3)
        ]
        results = await scorer.score_papers(papers)

        assert len(results) == 3
        for r in results:
            assert isinstance(r, EvidenceQualityScore)

    @pytest.mark.asyncio
    async def test_score_papers_batching(self):
        """Papers exceeding BATCH_SIZE should result in multiple LLM calls."""
        batch1 = _quality_response([_full_assessment(paper_index=i) for i in range(5)])
        batch2 = _quality_response([_full_assessment(paper_index=i) for i in range(3)])
        llm = MockQualityLLM([batch1, batch2])
        scorer = QualityScorer(llm)

        papers = [
            _make_paper(title=f"Study {i}", abstract=f"{100 + i} participants")
            for i in range(8)
        ]
        results = await scorer.score_papers(papers)

        assert len(results) == 8
        assert llm._call_index == 2  # Two LLM calls

    @pytest.mark.asyncio
    async def test_llm_failure_produces_heuristic_only_scores(self):
        """When LLM fails, scores should still be generated from heuristics."""
        llm = FailingLLM()
        scorer = QualityScorer(llm)

        papers = [_make_paper(
            title="A meta-analysis of treatment outcomes",
            abstract="We included 25 studies with 5000 participants total.",
        )]
        results = await scorer.score_papers(papers)

        assert len(results) == 1
        assert isinstance(results[0], EvidenceQualityScore)
        assert 0.0 <= results[0].overall_score <= 1.0
        assert results[0].study_design == StudyDesign.META_ANALYSIS

    @pytest.mark.asyncio
    async def test_invalid_json_produces_heuristic_only_scores(self):
        """Malformed JSON from LLM should fall back to heuristic-only scoring."""
        llm = MockQualityLLM(["not valid json at all {{{"])
        scorer = QualityScorer(llm)

        papers = [_make_paper(
            title="Cohort study of diabetes",
            abstract="A prospective cohort study with 300 patients.",
        )]
        results = await scorer.score_papers(papers)

        assert len(results) == 1
        assert isinstance(results[0], EvidenceQualityScore)
        assert results[0].study_design == StudyDesign.COHORT

    @pytest.mark.asyncio
    async def test_empty_papers_list(self):
        """Scoring an empty list should return empty results."""
        llm = MockQualityLLM([])
        scorer = QualityScorer(llm)

        results = await scorer.score_papers([])
        assert results == []

    @pytest.mark.asyncio
    async def test_heuristic_signals_reflected_in_result(self):
        """Heuristic signals from the paper text should appear in the score."""
        response = _quality_response([_full_assessment(paper_index=0)])
        llm = MockQualityLLM([response])
        scorer = QualityScorer(llm)

        papers = [_make_paper(
            title="Cross-sectional survey",
            abstract=(
                "A cross-sectional study of 800 women. "
                "Pre-registered on OSF. Data available on Zenodo. "
                "Compared with a control group. "
                "The authors declare no conflict of interest."
            ),
        )]
        results = await scorer.score_papers(papers)
        r = results[0]

        assert r.study_design == StudyDesign.CROSS_SECTIONAL
        assert r.sample_size == 800
        assert r.is_preregistered is True
        assert r.has_open_data is True
        assert r.has_control_group is True
        assert r.funding_bias_risk == "low"


# ── QualityScorer: _format_papers ────────────────────────────────────


class TestFormatPapers:
    """Tests for _format_papers static method."""

    def test_basic_formatting(self):
        papers = [_make_paper(
            title="Test Paper Title",
            abstract="A short abstract.",
            authors=["Alice", "Bob"],
            published_date="2024-06-01",
            journal="Nature",
            citation_count=42,
        )]
        text = QualityScorer._format_papers(papers)

        assert "[0] Title: Test Paper Title" in text
        assert "Alice, Bob" in text
        assert "2024-06-01" in text
        assert "Nature" in text
        assert "42" in text

    def test_abstract_truncated_at_800(self):
        papers = [_make_paper(abstract="A" * 1000)]
        text = QualityScorer._format_papers(papers)
        # The abstract portion should not exceed 800 chars
        assert "A" * 800 in text
        assert "A" * 801 not in text

    def test_multiple_papers_indexed(self):
        papers = [_make_paper(title=f"Paper {i}") for i in range(3)]
        text = QualityScorer._format_papers(papers)
        assert "[0] Title: Paper 0" in text
        assert "[1] Title: Paper 1" in text
        assert "[2] Title: Paper 2" in text

    def test_missing_optional_fields(self):
        """Papers with no abstract, date, journal, citations should not crash."""
        papers = [_make_paper(title="Minimal Paper")]
        text = QualityScorer._format_papers(papers)
        assert "[0] Title: Minimal Paper" in text
        assert "Abstract" not in text


# ── StudyDesign enum ─────────────────────────────────────────────────


class TestStudyDesignEnum:
    """Tests for StudyDesign enum values and DESIGN_STRENGTH mapping."""

    def test_all_designs_have_strength(self):
        for design in StudyDesign:
            assert design in DESIGN_STRENGTH

    def test_strengths_ordered(self):
        """META_ANALYSIS should be strongest, EXPERT_OPINION weakest."""
        assert DESIGN_STRENGTH[StudyDesign.META_ANALYSIS] > DESIGN_STRENGTH[StudyDesign.EXPERT_OPINION]
        assert DESIGN_STRENGTH[StudyDesign.RCT] > DESIGN_STRENGTH[StudyDesign.COHORT]
        assert DESIGN_STRENGTH[StudyDesign.COHORT] > DESIGN_STRENGTH[StudyDesign.CASE_REPORT]

    def test_strengths_in_zero_one_range(self):
        for design, strength in DESIGN_STRENGTH.items():
            assert 0.0 <= strength <= 1.0, f"{design} strength out of range: {strength}"

    def test_enum_values_are_strings(self):
        assert StudyDesign.META_ANALYSIS.value == "meta_analysis"
        assert StudyDesign.RCT.value == "rct"
        assert StudyDesign.UNKNOWN.value == "unknown"
