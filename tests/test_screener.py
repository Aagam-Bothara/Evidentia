"""Tests for the LLM-based systematic review screener."""

import json

import pytest

from evidentia.core.llm import BaseLLM, LLMResponse
from evidentia.review.models import PaperRecord
from evidentia.review.screener import Screener

# ── Mock LLM ─────────────────────────────────────────────────────────


class MockScreeningLLM(BaseLLM):
    """Returns pre-configured screening responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_index = 0

    async def chat(self, messages, temperature=0.0, max_tokens=4096, response_format=None):
        if self._call_index < len(self._responses):
            content = self._responses[self._call_index]
            self._call_index += 1
            return LLMResponse(content=content, usage={"total_tokens": 50})
        return LLMResponse(
            content='{"decisions": []}',
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


def _make_papers(n: int) -> list[PaperRecord]:
    return [
        PaperRecord(
            title=f"Paper {i}: A Study on Topic {i}",
            authors=[f"Author {i}"],
            abstract=f"This paper examines topic {i} in detail.",
            source_database="pubmed_search",
            source_id=f"pm{i}",
        )
        for i in range(n)
    ]


def _screening_response(decisions: list[dict]) -> str:
    return json.dumps({"decisions": decisions})


# ── Basic batch screening ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_screen_single_batch():
    """Screen a small batch of papers (under BATCH_SIZE)."""
    response = _screening_response(
        [
            {"paper_index": 0, "decision": "include", "reason": "Meets criteria", "confidence": 0.95},
            {"paper_index": 1, "decision": "exclude", "reason": "Wrong population", "confidence": 0.88},
            {"paper_index": 2, "decision": "uncertain", "reason": "Need full text", "confidence": 0.55},
        ]
    )
    llm = MockScreeningLLM([response])
    screener = Screener(llm)

    papers = _make_papers(3)
    result = await screener.screen_all(
        papers,
        inclusion_criteria=["RCT design", "Adult participants"],
        exclusion_criteria=["Animal studies"],
    )

    assert len(result) == 3
    assert result[0].screening_decision == "include"
    assert result[0].screening_confidence == 0.95
    assert result[1].screening_decision == "exclude"
    assert result[1].exclusion_reason == "Wrong population"
    assert result[2].screening_decision == "uncertain"


@pytest.mark.asyncio
async def test_screen_multiple_batches():
    """Papers exceeding BATCH_SIZE should be split across multiple LLM calls."""
    batch1 = _screening_response(
        [{"paper_index": i, "decision": "include", "reason": "OK", "confidence": 0.9} for i in range(5)]
    )
    batch2 = _screening_response(
        [{"paper_index": i, "decision": "include", "reason": "OK", "confidence": 0.9} for i in range(3)]
    )
    llm = MockScreeningLLM([batch1, batch2])
    screener = Screener(llm)

    papers = _make_papers(8)
    result = await screener.screen_all(papers, ["Criteria A"], [])

    assert len(result) == 8
    assert all(p.screening_decision == "include" for p in result)
    assert llm._call_index == 2  # Two LLM calls


# ── Low confidence handling ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_low_confidence_forced_uncertain():
    """Papers with confidence < 0.7 should be forced to 'uncertain'."""
    response = _screening_response(
        [
            {"paper_index": 0, "decision": "include", "reason": "Maybe meets criteria", "confidence": 0.55},
            {"paper_index": 1, "decision": "exclude", "reason": "Probably wrong", "confidence": 0.65},
        ]
    )
    llm = MockScreeningLLM([response])
    screener = Screener(llm)

    papers = _make_papers(2)
    result = await screener.screen_all(papers, ["Criteria"], [])

    assert result[0].screening_decision == "uncertain"
    assert "Low confidence" in result[0].exclusion_reason
    assert result[1].screening_decision == "uncertain"
    assert "Low confidence" in result[1].exclusion_reason


@pytest.mark.asyncio
async def test_low_confidence_uncertain_stays_uncertain():
    """If LLM says 'uncertain' with low confidence, it stays uncertain (not double-flagged)."""
    response = _screening_response(
        [
            {"paper_index": 0, "decision": "uncertain", "reason": "Need full text", "confidence": 0.3},
        ]
    )
    llm = MockScreeningLLM([response])
    screener = Screener(llm)

    papers = _make_papers(1)
    result = await screener.screen_all(papers, ["Criteria"], [])

    assert result[0].screening_decision == "uncertain"
    assert result[0].screening_confidence == 0.3


# ── Error handling ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_failure_marks_all_uncertain():
    """If the LLM call fails, all papers in the batch should be 'uncertain'."""
    llm = FailingLLM()
    screener = Screener(llm)

    papers = _make_papers(3)
    result = await screener.screen_all(papers, ["Criteria"], [])

    assert len(result) == 3
    assert all(p.screening_decision == "uncertain" for p in result)
    assert all(p.screening_confidence == 0.0 for p in result)


@pytest.mark.asyncio
async def test_invalid_json_marks_uncertain():
    """If LLM returns malformed JSON, papers should be marked uncertain."""
    llm = MockScreeningLLM(["not valid json at all"])
    screener = Screener(llm)

    papers = _make_papers(2)
    result = await screener.screen_all(papers, ["Criteria"], [])

    assert all(p.screening_decision == "uncertain" for p in result)


# ── Parse decisions validation ───────────────────────────────────────


def test_parse_invalid_decision_value():
    """Invalid decision strings should be normalized to 'uncertain'."""
    llm = MockScreeningLLM([])
    screener = Screener(llm)

    decisions = screener._parse_decisions(
        {
            "decisions": [
                {"paper_index": 0, "decision": "maybe", "reason": "Not sure", "confidence": 0.8},
            ]
        },
        expected_count=1,
    )
    assert len(decisions) == 1
    assert decisions[0].decision == "uncertain"


def test_parse_missing_papers_filled_uncertain():
    """Papers not mentioned in LLM output should be filled as 'uncertain'."""
    llm = MockScreeningLLM([])
    screener = Screener(llm)

    decisions = screener._parse_decisions(
        {
            "decisions": [
                {"paper_index": 0, "decision": "include", "reason": "Good", "confidence": 0.9},
            ]
        },
        expected_count=3,
    )
    assert len(decisions) == 3
    assert decisions[0].decision == "include"
    assert decisions[1].decision == "uncertain"
    assert decisions[2].decision == "uncertain"


def test_parse_out_of_range_index_ignored():
    """Paper indices outside valid range should be ignored."""
    llm = MockScreeningLLM([])
    screener = Screener(llm)

    decisions = screener._parse_decisions(
        {
            "decisions": [
                {"paper_index": 99, "decision": "include", "reason": "Good", "confidence": 0.9},
            ]
        },
        expected_count=2,
    )
    # Both papers should be uncertain (the index 99 decision was ignored)
    assert len(decisions) == 2
    assert all(d.decision == "uncertain" for d in decisions)


def test_parse_duplicate_indices():
    """Duplicate paper indices should keep only the first."""
    llm = MockScreeningLLM([])
    screener = Screener(llm)

    decisions = screener._parse_decisions(
        {
            "decisions": [
                {"paper_index": 0, "decision": "include", "reason": "A", "confidence": 0.9},
                {"paper_index": 0, "decision": "exclude", "reason": "B", "confidence": 0.8},
            ]
        },
        expected_count=1,
    )
    assert len(decisions) == 1
    assert decisions[0].decision == "include"  # First one wins


def test_parse_confidence_clamped():
    """Confidence values outside [0, 1] should be clamped."""
    llm = MockScreeningLLM([])
    screener = Screener(llm)

    decisions = screener._parse_decisions(
        {
            "decisions": [
                {"paper_index": 0, "decision": "include", "reason": "Good", "confidence": 1.5},
                {"paper_index": 1, "decision": "exclude", "reason": "Bad", "confidence": -0.3},
            ]
        },
        expected_count=2,
    )
    assert decisions[0].confidence == 1.0
    assert decisions[1].confidence == 0.0


def test_parse_empty_decisions_list():
    """Empty decisions list should mark all papers uncertain."""
    llm = MockScreeningLLM([])
    screener = Screener(llm)

    decisions = screener._parse_decisions({"decisions": []}, expected_count=3)
    assert len(decisions) == 3
    assert all(d.decision == "uncertain" for d in decisions)


# ── Format helpers ───────────────────────────────────────────────────


def test_format_papers():
    """Paper formatting should include title and truncated abstract."""
    papers = [
        PaperRecord(
            title="Test Paper Title",
            authors=["Alice", "Bob"],
            abstract="A" * 700,  # Longer than 600 char truncation
            published_date="2024-01-15",
        ),
    ]
    text = Screener._format_papers(papers)
    assert "[0] Title: Test Paper Title" in text
    assert "Alice, Bob" in text
    assert "2024-01-15" in text
    assert len(text) < 800  # Abstract should be truncated


def test_format_criteria():
    """Criteria formatting should include both inclusion and exclusion."""
    text = Screener._format_criteria(
        ["RCT design", "Adult participants"],
        ["Animal studies", "Case reports"],
    )
    assert "Inclusion criteria:" in text
    assert "RCT design" in text
    assert "Exclusion criteria:" in text
    assert "Animal studies" in text


def test_format_criteria_no_exclusion():
    """Exclusion header should be omitted when no exclusion criteria."""
    text = Screener._format_criteria(["RCT design"], [])
    assert "Inclusion criteria:" in text
    assert "Exclusion criteria:" not in text
