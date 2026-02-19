"""Tests for the systematic review engine pipeline."""

import json
from typing import Any

import pytest

from evidentia.core.llm import BaseLLM, LLMResponse
from evidentia.review.engine import SystematicReviewEngine
from evidentia.review.models import ReviewConfig, ReviewEvent, ReviewMode
from evidentia.tools.base import BaseTool, ToolMetadata, ToolRegistry

# ── Mock LLM ─────────────────────────────────────────────────────────


class MockReviewLLM(BaseLLM):
    """Returns screening decisions for testing the engine pipeline."""

    def __init__(self, decision: str = "include", confidence: float = 0.9) -> None:
        self._decision = decision
        self._confidence = confidence

    async def chat(self, messages, temperature=0.0, max_tokens=4096, response_format=None):
        # Parse how many papers are in the batch from the user message
        user_msg = messages[-1]["content"] if messages else ""
        # Count [N] patterns to determine paper count
        import re

        indices = re.findall(r"\[(\d+)\]", user_msg)
        count = len(indices) if indices else 1

        decisions = [
            {
                "paper_index": i,
                "decision": self._decision,
                "reason": f"Test reason for paper {i}",
                "confidence": self._confidence,
            }
            for i in range(count)
        ]
        content = json.dumps({"decisions": decisions})
        return LLMResponse(content=content, usage={"total_tokens": 50})

    async def chat_with_tools(self, messages, tools, temperature=0.0, max_tokens=4096):
        return await self.chat(messages, temperature, max_tokens)


# ── Mock Search Tools ────────────────────────────────────────────────


class MockPubMedTool(BaseTool):
    metadata = ToolMetadata(
        name="pubmed_search",
        description="Mock PubMed search",
        category="search",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        output_schema={"type": "object"},
    )

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "data": [
                {
                    "title": "PubMed Paper: CBT for Anxiety",
                    "authors": ["Smith, J.", "Jones, K."],
                    "abstract": "A randomized controlled trial of CBT for anxiety disorders.",
                    "doi": "10.1234/pm001",
                    "pmid": "12345678",
                    "published_date": "2023-06-15",
                    "journal": "J Clin Psych",
                },
                {
                    "title": "PubMed Paper: Exercise and Depression",
                    "authors": ["Lee, A."],
                    "abstract": "A meta-analysis of exercise interventions for depression.",
                    "doi": "10.1234/pm002",
                    "pmid": "12345679",
                    "published_date": "2023-03-10",
                    "journal": "BMJ",
                },
            ],
        }


class MockOpenAlexTool(BaseTool):
    metadata = ToolMetadata(
        name="openalex_search",
        description="Mock OpenAlex search",
        category="search",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        output_schema={"type": "object"},
    )

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "data": [
                {
                    "title": "PubMed Paper: CBT for Anxiety",  # Duplicate of PubMed
                    "authors": ["Smith, J.", "Jones, K."],
                    "abstract": "A randomized controlled trial of CBT.",
                    "doi": "10.1234/pm001",  # Same DOI
                    "work_id": "W123456",
                    "published_date": "2023-06-15",
                },
                {
                    "title": "OpenAlex Paper: Mindfulness and Stress",
                    "authors": ["Chen, W."],
                    "abstract": "Mindfulness-based stress reduction in adults.",
                    "doi": "10.1234/oa001",
                    "work_id": "W789012",
                    "published_date": "2022-11-20",
                    "cited_by_count": 42,
                },
            ],
        }


class FailingSearchTool(BaseTool):
    metadata = ToolMetadata(
        name="failing_search",
        description="A tool that always fails",
        category="search",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        output_schema={"type": "object"},
    )

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("Database unreachable")


class EmptySearchTool(BaseTool):
    metadata = ToolMetadata(
        name="empty_search",
        description="Returns no results",
        category="search",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        output_schema={"type": "object"},
    )

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "data": []}


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def registry_with_two_dbs() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(MockPubMedTool())
    registry.register(MockOpenAlexTool())
    return registry


@pytest.fixture
def basic_config() -> ReviewConfig:
    return ReviewConfig(
        research_question="effectiveness of CBT for anxiety",
        inclusion_criteria=["RCT design", "Adult participants"],
        exclusion_criteria=["Animal studies"],
        databases=["pubmed_search", "openalex_search"],
        max_results_per_db=100,
        mode=ReviewMode.FAST,
    )


# ── Full pipeline tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_pipeline(registry_with_two_dbs, basic_config):
    """Full pipeline: identify → deduplicate → screen → report."""
    llm = MockReviewLLM(decision="include", confidence=0.9)
    engine = SystematicReviewEngine(llm=llm, tool_registry=registry_with_two_dbs)

    events: list[ReviewEvent] = []
    async for event in engine.stream(basic_config):
        events.append(event)

    event_types = [e.type for e in events]

    # All phases should be present
    assert "review_phase_started" in event_types
    assert "review_identification_complete" in event_types
    assert "review_deduplication_complete" in event_types
    assert "review_screening_progress" in event_types
    assert "review_screening_complete" in event_types
    assert "review_completed" in event_types

    # Check completed event data
    completed = [e for e in events if e.type == "review_completed"][0]
    prisma = completed.data["prisma"]

    assert prisma["total_identified"] == 4  # 2 PubMed + 2 OpenAlex
    assert prisma["duplicates_removed"] == 1  # 1 DOI duplicate
    assert prisma["records_screened"] == 3  # 4 - 1 duplicate
    assert prisma["included_count"] == 3  # All included by mock LLM
    assert completed.data["elapsed_seconds"] >= 0


@pytest.mark.asyncio
async def test_deduplication_in_pipeline(registry_with_two_dbs, basic_config):
    """Deduplication should correctly remove the DOI duplicate."""
    llm = MockReviewLLM()
    engine = SystematicReviewEngine(llm=llm, tool_registry=registry_with_two_dbs)

    events: list[ReviewEvent] = []
    async for event in engine.stream(basic_config):
        events.append(event)

    dedup_event = [e for e in events if e.type == "review_deduplication_complete"][0]
    assert dedup_event.data["unique"] == 3
    assert dedup_event.data["duplicates"] == 1


@pytest.mark.asyncio
async def test_screening_with_exclusions(registry_with_two_dbs, basic_config):
    """Engine should correctly tally exclusions."""
    llm = MockReviewLLM(decision="exclude", confidence=0.9)
    engine = SystematicReviewEngine(llm=llm, tool_registry=registry_with_two_dbs)

    events: list[ReviewEvent] = []
    async for event in engine.stream(basic_config):
        events.append(event)

    completed = [e for e in events if e.type == "review_completed"][0]
    assert completed.data["excluded_count"] == 3
    assert completed.data["included_count"] == 0


# ── Edge cases ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_results_from_databases():
    """Engine should handle zero results gracefully."""
    registry = ToolRegistry()
    registry.register(EmptySearchTool())

    config = ReviewConfig(
        research_question="nonexistent topic",
        inclusion_criteria=["Some criteria"],
        databases=["empty_search"],
    )

    llm = MockReviewLLM()
    engine = SystematicReviewEngine(llm=llm, tool_registry=registry)

    events: list[ReviewEvent] = []
    async for event in engine.stream(config):
        events.append(event)

    event_types = [e.type for e in events]
    assert "review_completed" in event_types
    # Should NOT have screening events (no papers to screen)
    assert "review_screening_progress" not in event_types

    completed = [e for e in events if e.type == "review_completed"][0]
    assert completed.data["papers"] == []


@pytest.mark.asyncio
async def test_partial_database_failure():
    """If one database fails, engine should still process results from others."""
    registry = ToolRegistry()
    registry.register(MockPubMedTool())
    registry.register(FailingSearchTool())

    config = ReviewConfig(
        research_question="CBT for anxiety",
        inclusion_criteria=["RCT design"],
        databases=["pubmed_search", "failing_search"],
    )

    llm = MockReviewLLM()
    engine = SystematicReviewEngine(llm=llm, tool_registry=registry)

    events: list[ReviewEvent] = []
    async for event in engine.stream(config):
        events.append(event)

    # Should complete despite failing_search error
    event_types = [e.type for e in events]
    assert "review_completed" in event_types

    # Check that the error was captured
    db_complete_events = [e for e in events if e.type == "review_database_complete"]
    failing_db = [e for e in db_complete_events if e.data.get("database") == "failing_search"]
    assert len(failing_db) == 1
    assert failing_db[0].data["count"] == 0
    assert "error" in failing_db[0].data

    # PubMed results should still be processed
    completed = [e for e in events if e.type == "review_completed"][0]
    assert completed.data["prisma"]["total_identified"] == 2


@pytest.mark.asyncio
async def test_unknown_database_skipped():
    """Databases not in the tool registry should be silently skipped."""
    registry = ToolRegistry()
    registry.register(MockPubMedTool())

    config = ReviewConfig(
        research_question="test query",
        inclusion_criteria=["Criteria"],
        databases=["pubmed_search", "nonexistent_database"],
    )

    llm = MockReviewLLM()
    engine = SystematicReviewEngine(llm=llm, tool_registry=registry)

    events: list[ReviewEvent] = []
    async for event in engine.stream(config):
        events.append(event)

    assert "review_completed" in [e.type for e in events]


# ── Event structure ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_event_to_dict(registry_with_two_dbs, basic_config):
    """All events should serialize via to_dict()."""
    llm = MockReviewLLM()
    engine = SystematicReviewEngine(llm=llm, tool_registry=registry_with_two_dbs)

    async for event in engine.stream(basic_config):
        d = event.to_dict()
        assert "type" in d
        assert "data" in d
        assert "timestamp" in d
        # Should be JSON-serializable
        json.dumps(d, default=str)


# ── Normalization ────────────────────────────────────────────────────


def test_normalize_pubmed_results():
    """PubMed-style results should be normalized to PaperRecord."""
    llm = MockReviewLLM()
    registry = ToolRegistry()
    engine = SystematicReviewEngine(llm=llm, tool_registry=registry)

    papers = engine._normalize_results(
        "pubmed_search",
        {
            "data": [
                {
                    "title": "Test Paper",
                    "authors": ["Author A"],
                    "abstract": "An abstract",
                    "doi": "10.1234/test",
                    "pmid": "99999",
                    "published_date": "2024-01-01",
                }
            ]
        },
    )
    assert len(papers) == 1
    assert papers[0].title == "Test Paper"
    assert papers[0].source_database == "pubmed_search"
    assert papers[0].source_id == "99999"  # Uses pmid


def test_normalize_openalex_results():
    """OpenAlex-style results should use work_id and cited_by_count."""
    llm = MockReviewLLM()
    registry = ToolRegistry()
    engine = SystematicReviewEngine(llm=llm, tool_registry=registry)

    papers = engine._normalize_results(
        "openalex_search",
        {
            "data": [
                {
                    "title": "OA Paper",
                    "authors": ["Author B"],
                    "work_id": "W123",
                    "cited_by_count": 50,
                    "published": "2023-06",
                }
            ]
        },
    )
    assert len(papers) == 1
    assert papers[0].source_id == "W123"
    assert papers[0].citation_count == 50
    assert papers[0].published_date == "2023-06"


def test_normalize_skips_empty_titles():
    """Papers with empty titles should be filtered out."""
    llm = MockReviewLLM()
    registry = ToolRegistry()
    engine = SystematicReviewEngine(llm=llm, tool_registry=registry)

    papers = engine._normalize_results(
        "test",
        {
            "data": [
                {"title": "", "authors": []},
                {"title": "Valid Paper", "authors": ["Author"]},
            ]
        },
    )
    assert len(papers) == 1
    assert papers[0].title == "Valid Paper"


def test_normalize_empty_data():
    """Empty data list should return empty paper list."""
    llm = MockReviewLLM()
    registry = ToolRegistry()
    engine = SystematicReviewEngine(llm=llm, tool_registry=registry)

    papers = engine._normalize_results("test", {"data": []})
    assert papers == []


def test_normalize_missing_data_key():
    """Missing 'data' key should return empty paper list."""
    llm = MockReviewLLM()
    registry = ToolRegistry()
    engine = SystematicReviewEngine(llm=llm, tool_registry=registry)

    papers = engine._normalize_results("test", {"success": True})
    assert papers == []
