"""Tests for cross-study contradiction detection."""

import json

import pytest

from evidentia.core.llm import BaseLLM, LLMResponse
from evidentia.review.contradictions import (
    ContradictionDetector,
    ContradictionPair,
    ContradictionReport,
)
from evidentia.review.models import PaperRecord


# -- Mock LLM ----------------------------------------------------------------


class MockContradictionLLM(BaseLLM):
    """Returns pre-configured contradiction analysis responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_index = 0

    async def chat(self, messages, temperature=0.0, max_tokens=4096, response_format=None):
        if self._call_index < len(self._responses):
            content = self._responses[self._call_index]
            self._call_index += 1
            return LLMResponse(content=content, usage={"total_tokens": 80})
        return LLMResponse(
            content='{"contradictions": [], "consensus_areas": [], "summary": ""}',
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


# -- Helpers ------------------------------------------------------------------


def _make_papers(n: int) -> list[PaperRecord]:
    return [
        PaperRecord(
            title=f"Paper {i}: Study on Effect {i}",
            authors=[f"Author {i}A", f"Author {i}B"],
            abstract=f"This study investigates effect {i} in a randomised controlled trial.",
            source_database="pubmed_search",
            source_id=f"pm{i}",
            published_date=f"2024-0{min(i + 1, 9)}-01",
        )
        for i in range(n)
    ]


def _contradiction_response(
    contradictions: list[dict],
    consensus_areas: list[str] | None = None,
    summary: str = "",
) -> str:
    return json.dumps({
        "contradictions": contradictions,
        "consensus_areas": consensus_areas or [],
        "summary": summary,
    })


# -- detect() with fewer than 2 papers ---------------------------------------


@pytest.mark.asyncio
async def test_detect_zero_papers_returns_empty_report():
    """detect() with no papers returns a report with zero papers and no contradictions."""
    llm = MockContradictionLLM([])
    detector = ContradictionDetector(llm)

    report = await detector.detect([])

    assert isinstance(report, ContradictionReport)
    assert report.total_papers_analyzed == 0
    assert report.contradictions == []
    assert report.consensus_areas == []
    assert "Insufficient papers" in report.summary


@pytest.mark.asyncio
async def test_detect_one_paper_returns_empty_report():
    """detect() with a single paper returns early without calling LLM."""
    llm = MockContradictionLLM([])
    detector = ContradictionDetector(llm)

    papers = _make_papers(1)
    report = await detector.detect(papers)

    assert report.total_papers_analyzed == 1
    assert report.contradictions == []
    assert "Insufficient papers" in report.summary
    assert "need at least 2" in report.summary
    assert llm._call_index == 0  # LLM should never be called


# -- detect() with 2+ papers and mocked LLM returning contradictions ---------


@pytest.mark.asyncio
async def test_detect_two_papers_with_contradiction():
    """detect() with two papers should return a contradiction when LLM finds one."""
    response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "effect_size",
                "description": "Paper 0 reports d=0.8, Paper 1 reports d=0.1",
                "severity": "strong",
                "confidence": 0.90,
            }
        ],
        consensus_areas=["Both studies agree on safety profile"],
        summary="1 contradiction found.",
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(2)
    report = await detector.detect(papers)

    assert report.total_papers_analyzed == 2
    assert len(report.contradictions) == 1

    c = report.contradictions[0]
    assert c.paper_a_index == 0
    assert c.paper_b_index == 1
    assert c.dimension == "effect_size"
    assert c.severity == "strong"
    assert c.confidence == 0.90
    assert c.paper_a_title == papers[0].title
    assert c.paper_b_title == papers[1].title


@pytest.mark.asyncio
async def test_detect_multiple_contradictions():
    """detect() correctly parses multiple contradictions from LLM output."""
    response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "conclusion",
                "description": "Opposite conclusions about treatment efficacy",
                "severity": "strong",
                "confidence": 0.92,
            },
            {
                "paper_a_index": 1,
                "paper_b_index": 2,
                "dimension": "methodology",
                "description": "Conflicting methodological approaches yielding different results",
                "severity": "moderate",
                "confidence": 0.75,
            },
        ],
        consensus_areas=["All agree on safety"],
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(3)
    report = await detector.detect(papers)

    assert len(report.contradictions) == 2
    # Should be sorted: strong before moderate
    assert report.contradictions[0].severity == "strong"
    assert report.contradictions[1].severity == "moderate"


# -- Low confidence contradictions filtered out (< 0.6) ----------------------


@pytest.mark.asyncio
async def test_low_confidence_contradictions_filtered():
    """Contradictions with confidence < 0.6 should be excluded from the report."""
    response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "effect_size",
                "description": "Slight difference in effect sizes",
                "severity": "mild",
                "confidence": 0.55,
            },
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "conclusion",
                "description": "Opposite conclusions",
                "severity": "strong",
                "confidence": 0.85,
            },
        ],
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(2)
    report = await detector.detect(papers)

    assert len(report.contradictions) == 1
    assert report.contradictions[0].dimension == "conclusion"
    assert report.contradictions[0].confidence == 0.85


@pytest.mark.asyncio
async def test_confidence_exactly_at_threshold_filtered():
    """A contradiction with confidence == 0.6 should NOT be filtered (boundary is strictly < 0.6)."""
    response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "outcome_measure",
                "description": "Borderline disagreement on outcome",
                "severity": "mild",
                "confidence": 0.6,
            },
        ],
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(2)
    report = await detector.detect(papers)

    assert len(report.contradictions) == 1
    assert report.contradictions[0].confidence == 0.6


@pytest.mark.asyncio
async def test_all_contradictions_below_threshold_yields_empty():
    """When every contradiction is below 0.6, the report should have none."""
    response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "effect_size",
                "description": "Vague difference",
                "severity": "mild",
                "confidence": 0.3,
            },
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "conclusion",
                "description": "Barely different",
                "severity": "mild",
                "confidence": 0.59,
            },
        ],
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(2)
    report = await detector.detect(papers)

    assert len(report.contradictions) == 0


# -- Severity levels ---------------------------------------------------------


@pytest.mark.asyncio
async def test_severity_sorting_order():
    """Contradictions should be sorted: strong first, then moderate, then mild."""
    response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "a",
                "description": "Mild",
                "severity": "mild",
                "confidence": 0.90,
            },
            {
                "paper_a_index": 0,
                "paper_b_index": 2,
                "dimension": "b",
                "description": "Strong",
                "severity": "strong",
                "confidence": 0.80,
            },
            {
                "paper_a_index": 1,
                "paper_b_index": 2,
                "dimension": "c",
                "description": "Moderate",
                "severity": "moderate",
                "confidence": 0.85,
            },
        ],
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(3)
    report = await detector.detect(papers)

    assert [c.severity for c in report.contradictions] == ["strong", "moderate", "mild"]


@pytest.mark.asyncio
async def test_invalid_severity_defaults_to_moderate():
    """An unknown severity value from LLM should be normalized to 'moderate'."""
    response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "conclusion",
                "description": "Some disagreement",
                "severity": "extreme",  # Invalid
                "confidence": 0.80,
            },
        ],
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(2)
    report = await detector.detect(papers)

    assert len(report.contradictions) == 1
    assert report.contradictions[0].severity == "moderate"


# -- Index validation ---------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_indices_skipped():
    """Contradictions referencing paper indices entirely outside the batch should be skipped."""
    response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 50,
                "paper_b_index": 99,
                "dimension": "effect_size",
                "description": "Ghost contradiction",
                "severity": "strong",
                "confidence": 0.95,
            },
        ],
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(3)
    report = await detector.detect(papers)

    assert len(report.contradictions) == 0


@pytest.mark.asyncio
async def test_local_indices_treated_as_offsets():
    """When LLM returns local (0-based) indices instead of offset indices, they should be adjusted."""
    response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "conclusion",
                "description": "Different conclusions",
                "severity": "moderate",
                "confidence": 0.80,
            },
        ],
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(2)
    report = await detector.detect(papers)

    assert len(report.contradictions) == 1
    # With offset=0, local indices 0 and 1 are valid directly
    assert report.contradictions[0].paper_a_index == 0
    assert report.contradictions[0].paper_b_index == 1


# -- Consensus areas ---------------------------------------------------------


@pytest.mark.asyncio
async def test_consensus_areas_parsed():
    """Consensus areas from LLM response should be included in the report."""
    response = _contradiction_response(
        contradictions=[],
        consensus_areas=[
            "All studies agree intervention is safe",
            "Consistent finding of dose-response relationship",
            "Uniform reporting of minimal side effects",
        ],
        summary="No contradictions found. Strong consensus across papers.",
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(3)
    report = await detector.detect(papers)

    assert len(report.consensus_areas) == 3
    assert "intervention is safe" in report.consensus_areas[0]


@pytest.mark.asyncio
async def test_consensus_areas_deduplicated():
    """Duplicate consensus areas across batches should be deduplicated."""
    # This requires more than BATCH_SIZE papers to trigger multiple batches.
    # We temporarily shrink BATCH_SIZE via monkeypatching.
    shared_consensus = "All studies agree on safety profile"
    response1 = _contradiction_response(
        contradictions=[],
        consensus_areas=[shared_consensus, "Consensus A"],
    )
    response2 = _contradiction_response(
        contradictions=[],
        consensus_areas=[shared_consensus, "Consensus B"],
    )
    llm = MockContradictionLLM([response1, response2])
    detector = ContradictionDetector(llm)
    detector.BATCH_SIZE = 2  # Force multiple batches

    papers = _make_papers(4)
    report = await detector.detect(papers)

    # shared_consensus should appear only once
    assert report.consensus_areas.count(shared_consensus) == 1
    assert "Consensus A" in report.consensus_areas
    assert "Consensus B" in report.consensus_areas


@pytest.mark.asyncio
async def test_consensus_areas_capped_at_ten():
    """At most 10 consensus areas should be kept in the report."""
    areas = [f"Consensus point {i}" for i in range(15)]
    response = _contradiction_response(contradictions=[], consensus_areas=areas)
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(2)
    report = await detector.detect(papers)

    assert len(report.consensus_areas) == 10


@pytest.mark.asyncio
async def test_consensus_areas_non_list_ignored():
    """If consensus_areas is not a list (e.g., a string), it should be replaced with empty list."""
    raw = json.dumps({
        "contradictions": [],
        "consensus_areas": "This is a string, not a list",
        "summary": "",
    })
    llm = MockContradictionLLM([raw])
    detector = ContradictionDetector(llm)

    papers = _make_papers(2)
    report = await detector.detect(papers)

    assert report.consensus_areas == []


# -- Deduplication of contradictions ------------------------------------------


def test_dedupe_identical_pairs():
    """Exact duplicate contradiction pairs (same indices and dimension) should be deduped."""
    detector = ContradictionDetector.__new__(ContradictionDetector)

    contradictions = [
        ContradictionPair(
            paper_a_index=0, paper_b_index=1, dimension="effect_size",
            description="First", severity="strong", confidence=0.9,
        ),
        ContradictionPair(
            paper_a_index=0, paper_b_index=1, dimension="effect_size",
            description="Second (duplicate)", severity="moderate", confidence=0.8,
        ),
    ]
    result = detector._dedupe_contradictions(contradictions)

    assert len(result) == 1
    assert result[0].description == "First"


def test_dedupe_reversed_indices():
    """Contradiction pair (A, B) should be treated as duplicate of (B, A) for the same dimension."""
    detector = ContradictionDetector.__new__(ContradictionDetector)

    contradictions = [
        ContradictionPair(
            paper_a_index=2, paper_b_index=5, dimension="conclusion",
            description="From batch 1", severity="strong", confidence=0.9,
        ),
        ContradictionPair(
            paper_a_index=5, paper_b_index=2, dimension="conclusion",
            description="From batch 2", severity="strong", confidence=0.85,
        ),
    ]
    result = detector._dedupe_contradictions(contradictions)

    assert len(result) == 1
    assert result[0].description == "From batch 1"  # First one kept


def test_dedupe_different_dimensions_not_deduped():
    """Same paper pair but different dimensions should NOT be deduped."""
    detector = ContradictionDetector.__new__(ContradictionDetector)

    contradictions = [
        ContradictionPair(
            paper_a_index=0, paper_b_index=1, dimension="effect_size",
            description="Effect size disagreement", severity="strong", confidence=0.9,
        ),
        ContradictionPair(
            paper_a_index=0, paper_b_index=1, dimension="methodology",
            description="Methodological disagreement", severity="moderate", confidence=0.8,
        ),
    ]
    result = detector._dedupe_contradictions(contradictions)

    assert len(result) == 2


# -- Summary generation ------------------------------------------------------


def test_summary_no_contradictions_no_consensus():
    """Summary with no contradictions and no consensus areas."""
    summary = ContradictionDetector._build_summary([], [], 5)
    assert "No contradictions" in summary
    assert "5 papers" in summary
    assert "consensus" not in summary.lower()


def test_summary_no_contradictions_with_consensus():
    """Summary with no contradictions but consensus areas present."""
    summary = ContradictionDetector._build_summary([], ["Safety is confirmed"], 4)
    assert "No contradictions" in summary
    assert "consensus" in summary.lower()
    assert "1 area" in summary


def test_summary_with_mixed_severities():
    """Summary should break down severity counts."""
    contradictions = [
        ContradictionPair(
            paper_a_index=0, paper_b_index=1, dimension="a",
            severity="strong", confidence=0.9,
        ),
        ContradictionPair(
            paper_a_index=0, paper_b_index=2, dimension="b",
            severity="strong", confidence=0.85,
        ),
        ContradictionPair(
            paper_a_index=1, paper_b_index=2, dimension="c",
            severity="moderate", confidence=0.8,
        ),
        ContradictionPair(
            paper_a_index=2, paper_b_index=3, dimension="d",
            severity="mild", confidence=0.7,
        ),
    ]
    summary = ContradictionDetector._build_summary(contradictions, [], 4)
    assert "4 contradiction(s)" in summary
    assert "2 strong" in summary
    assert "1 moderate" in summary
    assert "1 mild" in summary


def test_summary_with_contradictions_and_consensus():
    """Summary should mention both contradictions and consensus."""
    contradictions = [
        ContradictionPair(
            paper_a_index=0, paper_b_index=1, dimension="a",
            severity="moderate", confidence=0.8,
        ),
    ]
    consensus = ["Safety agreed", "Dosing agreed"]
    summary = ContradictionDetector._build_summary(contradictions, consensus, 3)
    assert "1 contradiction(s)" in summary
    assert "Consensus on 2 area(s)" in summary


# -- LLM failure graceful handling --------------------------------------------


@pytest.mark.asyncio
async def test_llm_failure_returns_report_with_failure_message():
    """If the LLM call fails, detect() should return a valid report with no contradictions.

    The failure is logged but the final report is still well-formed.
    The per-batch failure summary is replaced by the aggregated summary from _build_summary.
    """
    llm = FailingLLM()
    detector = ContradictionDetector(llm)

    papers = _make_papers(3)
    report = await detector.detect(papers)

    assert isinstance(report, ContradictionReport)
    assert report.total_papers_analyzed == 3
    assert report.contradictions == []
    # The report gracefully degrades: no crash, just zero contradictions
    assert "No contradictions" in report.summary


@pytest.mark.asyncio
async def test_invalid_json_returns_failure_report():
    """If the LLM returns malformed JSON, the batch should fail gracefully.

    The error is caught in _analyze_batch and the final report has no contradictions.
    """
    llm = MockContradictionLLM(["this is not json {{{"])
    detector = ContradictionDetector(llm)

    papers = _make_papers(2)
    report = await detector.detect(papers)

    assert report.contradictions == []
    assert report.total_papers_analyzed == 2
    assert "No contradictions" in report.summary


# -- Empty contradictions response --------------------------------------------


@pytest.mark.asyncio
async def test_empty_contradictions_from_llm():
    """LLM returns a valid response with an empty contradictions list."""
    response = _contradiction_response(
        contradictions=[],
        consensus_areas=["All papers agree on intervention safety"],
        summary="No contradictions found.",
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(3)
    report = await detector.detect(papers)

    assert report.total_papers_analyzed == 3
    assert len(report.contradictions) == 0
    assert len(report.consensus_areas) == 1
    assert "No contradictions" in report.summary


# -- Batch processing for larger paper sets -----------------------------------


@pytest.mark.asyncio
async def test_batch_processing_multiple_batches():
    """Papers exceeding BATCH_SIZE should be processed in multiple LLM calls."""
    batch1_response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "effect_size",
                "description": "Batch 1 contradiction",
                "severity": "strong",
                "confidence": 0.9,
            },
        ],
        consensus_areas=["Batch 1 consensus"],
    )
    batch2_response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "conclusion",
                "description": "Batch 2 contradiction",
                "severity": "moderate",
                "confidence": 0.8,
            },
        ],
        consensus_areas=["Batch 2 consensus"],
    )
    llm = MockContradictionLLM([batch1_response, batch2_response])
    detector = ContradictionDetector(llm)
    detector.BATCH_SIZE = 3  # Force smaller batches

    papers = _make_papers(5)
    report = await detector.detect(papers)

    assert llm._call_index == 2  # Two LLM calls
    assert report.total_papers_analyzed == 5
    assert len(report.contradictions) == 2
    assert "Batch 1 consensus" in report.consensus_areas
    assert "Batch 2 consensus" in report.consensus_areas


@pytest.mark.asyncio
async def test_batch_trailing_single_paper_skipped():
    """A trailing batch with only 1 paper should be skipped (need >= 2 for comparison)."""
    batch1_response = _contradiction_response(
        contradictions=[],
        consensus_areas=["All agree"],
    )
    llm = MockContradictionLLM([batch1_response])
    detector = ContradictionDetector(llm)
    detector.BATCH_SIZE = 2

    papers = _make_papers(3)
    report = await detector.detect(papers)

    # Only one LLM call (the first batch of 2); trailing paper is skipped
    assert llm._call_index == 1


@pytest.mark.asyncio
async def test_partial_llm_failure_in_batch():
    """If one batch fails and another succeeds, contradictions from the successful batch are kept."""
    good_response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "effect_size",
                "description": "Valid contradiction",
                "severity": "moderate",
                "confidence": 0.85,
            },
        ],
    )

    call_count = 0

    class PartialFailLLM(BaseLLM):
        """First call succeeds, second call fails."""

        async def chat(self, messages, temperature=0.0, max_tokens=4096, response_format=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(content=good_response, usage={"total_tokens": 50})
            raise RuntimeError("Second batch failed")

        async def chat_with_tools(self, messages, tools, temperature=0.0, max_tokens=4096):
            return await self.chat(messages, temperature, max_tokens)

    detector = ContradictionDetector(PartialFailLLM())
    detector.BATCH_SIZE = 2

    papers = _make_papers(4)
    report = await detector.detect(papers)

    # Should have the contradiction from the successful first batch
    assert len(report.contradictions) == 1
    assert report.contradictions[0].description == "Valid contradiction"


# -- Confidence clamping ------------------------------------------------------


@pytest.mark.asyncio
async def test_confidence_clamped_to_0_1():
    """Confidence values above 1.0 should be clamped to 1.0."""
    response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "effect_size",
                "description": "Overcorrected confidence",
                "severity": "strong",
                "confidence": 1.5,
            },
        ],
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(2)
    report = await detector.detect(papers)

    assert len(report.contradictions) == 1
    assert report.contradictions[0].confidence == 1.0


# -- Paper title population ---------------------------------------------------


@pytest.mark.asyncio
async def test_paper_titles_populated_on_contradictions():
    """Contradiction pairs should have paper_a_title and paper_b_title populated from the input papers."""
    response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                "dimension": "conclusion",
                "description": "Different conclusions",
                "severity": "moderate",
                "confidence": 0.80,
            },
        ],
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(2)
    report = await detector.detect(papers)

    c = report.contradictions[0]
    assert c.paper_a_title == papers[0].title
    assert c.paper_b_title == papers[1].title


# -- Format papers helper -----------------------------------------------------


def test_format_papers_includes_all_fields():
    """_format_papers should include title, abstract, authors, and date."""
    papers = [
        PaperRecord(
            title="Test Formatting Paper",
            authors=["Alice", "Bob", "Charlie"],
            abstract="A brief abstract about the study results.",
            published_date="2024-06-15",
        ),
    ]
    text = ContradictionDetector._format_papers(papers, offset=0)
    assert "[0] Title: Test Formatting Paper" in text
    assert "Alice, Bob, Charlie" in text
    assert "A brief abstract" in text
    assert "2024-06-15" in text


def test_format_papers_with_offset():
    """_format_papers with offset should number papers starting from the offset."""
    papers = _make_papers(2)
    text = ContradictionDetector._format_papers(papers, offset=5)
    assert "[5] Title:" in text
    assert "[6] Title:" in text
    assert "[0] Title:" not in text


def test_format_papers_truncates_long_abstract():
    """Abstracts longer than 800 characters should be truncated."""
    papers = [
        PaperRecord(
            title="Long Abstract Paper",
            abstract="X" * 1200,
        ),
    ]
    text = ContradictionDetector._format_papers(papers, offset=0)
    # The abstract portion in the formatted text should be at most 800 characters
    assert "X" * 800 in text
    assert "X" * 801 not in text


# -- Model defaults -----------------------------------------------------------


def test_contradiction_pair_defaults():
    """ContradictionPair should have sensible defaults."""
    pair = ContradictionPair(paper_a_index=0, paper_b_index=1)
    assert pair.dimension == ""
    assert pair.description == ""
    assert pair.severity == "moderate"
    assert pair.confidence == 0.0
    assert pair.paper_a_title == ""
    assert pair.paper_b_title == ""


def test_contradiction_report_defaults():
    """ContradictionReport should have sensible defaults."""
    report = ContradictionReport()
    assert report.total_papers_analyzed == 0
    assert report.contradictions == []
    assert report.consensus_areas == []
    assert report.summary == ""


# -- Missing dimension defaults to "unspecified" ------------------------------


@pytest.mark.asyncio
async def test_missing_dimension_defaults_to_unspecified():
    """If a contradiction has no 'dimension' field, it should default to 'unspecified'."""
    response = _contradiction_response(
        contradictions=[
            {
                "paper_a_index": 0,
                "paper_b_index": 1,
                # "dimension" omitted
                "description": "Some disagreement",
                "severity": "moderate",
                "confidence": 0.80,
            },
        ],
    )
    llm = MockContradictionLLM([response])
    detector = ContradictionDetector(llm)

    papers = _make_papers(2)
    report = await detector.detect(papers)

    assert len(report.contradictions) == 1
    assert report.contradictions[0].dimension == "unspecified"
