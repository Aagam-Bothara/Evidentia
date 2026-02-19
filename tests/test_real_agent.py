"""Tests for the real system-driven agent (not the LLM wrapper).

These tests verify that:
1. The SYSTEM decomposes queries (not the LLM deciding freely)
2. The SYSTEM selects tools based on evidence type mapping
3. The SYSTEM retries and falls back on failure
4. The SYSTEM decides when evidence is sufficient
5. The SYSTEM calculates confidence, not the LLM
"""

import json

import pytest

from evidentia.agent.agent import EvidentiAgent
from evidentia.agent.decomposer import (
    EvidenceType,
    QueryDecomposer,
    SubQuestion,
)
from evidentia.agent.evidence_graph import EvidenceFragment, EvidenceGraph
from evidentia.agent.executor import ToolExecutor
from evidentia.agent.synthesizer import Synthesizer
from evidentia.agent.tool_selector import ToolSelector
from evidentia.core.llm import BaseLLM, LLMResponse
from evidentia.core.models import ClaimConfidence
from evidentia.tools.base import BaseTool, ToolMetadata, ToolRegistry

# ── Mock LLM (constrained — only used for decomposition + synthesis) ──


class MockLLM(BaseLLM):
    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses) if responses else []
        self._call_index = 0

    async def chat(self, messages, temperature=0.0, max_tokens=4096, response_format=None):
        if self._call_index < len(self._responses):
            content = self._responses[self._call_index]
            self._call_index += 1
            return LLMResponse(content=content)
        return LLMResponse(content='{"scope": "fallback", "sub_questions": []}')

    async def chat_with_tools(self, messages, tools, temperature=0.0, max_tokens=4096):
        return await self.chat(messages)


class MockTool(BaseTool):
    metadata = ToolMetadata(
        name="arxiv_search",
        description="Mock arXiv",
        category="public_api",
        input_schema={},
        output_schema={},
        timeout_seconds=5,
    )

    def __init__(self, results: list[dict] | None = None, should_fail: bool = False):
        self._results = results or [
            {"title": "Paper A", "authors": ["Author 1"], "url": "https://arxiv.org/1", "abstract": "About topic A."},
            {"title": "Paper B", "authors": ["Author 2"], "url": "https://arxiv.org/2", "abstract": "About topic B."},
        ]
        self._should_fail = should_fail

    async def execute(self, input_data):
        if self._should_fail:
            raise Exception("Tool execution failed")
        return {"success": True, "data": self._results}


class MockSemanticScholar(BaseTool):
    metadata = ToolMetadata(
        name="semantic_scholar",
        description="Mock Semantic Scholar",
        category="public_api",
        input_schema={},
        output_schema={},
    )

    async def execute(self, input_data):
        return {
            "success": True,
            "data": [
                {
                    "title": "Paper C",
                    "authors": ["Author 3"],
                    "url": "https://s2.org/1",
                    "abstract": "Fallback result.",
                },
            ],
        }


# ── Test 1: System decomposes queries into structured sub-questions ──


@pytest.mark.asyncio
async def test_decomposer_produces_structured_plan():
    """The decomposer constrains LLM output to a fixed schema."""
    llm = MockLLM(
        [
            json.dumps(
                {
                    "scope": "Recent advances in protein folding",
                    "sub_questions": [
                        {
                            "id": "sq1",
                            "question": "What are recent protein folding methods?",
                            "evidence_type": "academic_papers",
                            "depends_on": [],
                            "priority": 1,
                        },
                        {
                            "id": "sq2",
                            "question": "How does AlphaFold compare to traditional methods?",
                            "evidence_type": "comparison",
                            "depends_on": ["sq1"],
                            "priority": 1,
                        },
                    ],
                }
            )
        ]
    )

    decomposer = QueryDecomposer(llm)
    plan = await decomposer.decompose("What are the latest advances in protein folding?")

    assert len(plan.sub_questions) == 2
    assert plan.sub_questions[0].evidence_type == EvidenceType.ACADEMIC_PAPERS
    assert plan.sub_questions[1].depends_on == ["sq1"]


@pytest.mark.asyncio
async def test_decomposer_fallback_on_bad_llm_output():
    """If LLM returns garbage, system generates a fallback plan."""
    llm = MockLLM(["this is not json at all!!!"])

    decomposer = QueryDecomposer(llm)
    plan = await decomposer.decompose("Some query")

    # Should fall back to a valid plan, not crash
    assert len(plan.sub_questions) >= 1
    assert plan.sub_questions[0].evidence_type in list(EvidenceType)


# ── Test 2: System selects tools based on evidence type mapping ──────


def test_tool_selector_picks_correct_tools():
    """Tool selection is deterministic — based on evidence_type, not LLM."""
    registry = ToolRegistry()
    registry.register(MockTool())  # arxiv_search
    registry.register(MockSemanticScholar())  # semantic_scholar

    selector = ToolSelector(registry)
    graph = EvidenceGraph()

    sq = SubQuestion(id="sq1", question="Test?", evidence_type=EvidenceType.ACADEMIC_PAPERS)
    graph.add_question("sq1", "Test?")

    selections = selector.select_tools([sq], graph)

    assert len(selections) == 1
    # Should pick arxiv_search first (it's first in EVIDENCE_TOOL_MAP for academic_papers)
    assert selections[0].tool_name == "arxiv_search"


def test_tool_selector_falls_back_after_failure():
    """After a tool fails, system picks the NEXT tool in the fallback chain."""
    registry = ToolRegistry()
    registry.register(MockTool())
    registry.register(MockSemanticScholar())

    selector = ToolSelector(registry)
    graph = EvidenceGraph()

    sq = SubQuestion(id="sq1", question="Test?", evidence_type=EvidenceType.ACADEMIC_PAPERS)
    graph.add_question("sq1", "Test?")

    # Simulate: arxiv already tried
    graph.mark_searching("sq1", "arxiv_search")
    graph.mark_tool_failed("sq1", "arxiv_search")

    selections = selector.select_tools([sq], graph)

    assert len(selections) == 1
    assert selections[0].tool_name == "semantic_scholar"  # Fell back


# ── Test 3: Evidence graph tracks state and detects gaps ─────────────


def test_evidence_graph_tracks_sufficiency():
    """System decides evidence sufficiency by graph analysis, not LLM."""
    graph = EvidenceGraph(min_evidence_per_question=2)
    graph.add_question("sq1", "Question 1")
    graph.add_question("sq2", "Question 2")

    # Not sufficient yet
    assert not graph.is_sufficient({"sq1", "sq2"})
    assert len(graph.get_gaps()) == 2

    # Add evidence to sq1
    graph.add_evidence("sq1", EvidenceFragment(source_tool="arxiv", title="Paper 1", snippet="..."))
    graph.add_evidence("sq1", EvidenceFragment(source_tool="arxiv", title="Paper 2", snippet="..."))

    # sq1 answered, sq2 still a gap
    assert len(graph.get_answered()) == 1
    assert len(graph.get_gaps()) == 1
    assert not graph.is_sufficient({"sq1", "sq2"})

    # Add evidence to sq2
    graph.add_evidence("sq2", EvidenceFragment(source_tool="s2", title="Paper 3", snippet="..."))
    graph.add_evidence("sq2", EvidenceFragment(source_tool="s2", title="Paper 4", snippet="..."))

    # Now sufficient
    assert graph.is_sufficient({"sq1", "sq2"})


def test_evidence_graph_deduplicates():
    """System deduplicates evidence — same title+url is not counted twice."""
    graph = EvidenceGraph(min_evidence_per_question=2)
    graph.add_question("sq1", "Test")

    frag = EvidenceFragment(source_tool="arxiv", title="Same Paper", url="https://arxiv.org/1", snippet="...")
    graph.add_evidence("sq1", frag)
    graph.add_evidence("sq1", frag)  # Duplicate

    state = graph._questions["sq1"]
    assert state.evidence_count == 1  # Not 2


# ── Test 4: System calculates confidence, not LLM ───────────────────


def test_confidence_scoring_is_system_logic():
    """Confidence is calculated by citation count, not LLM opinion."""
    from evidentia.core.models import Citation, EvidenceSpan

    # 3+ unique sources with evidence spans = HIGH
    citations_3 = [
        Citation(source_id="a", title="A"),
        Citation(source_id="b", title="B"),
        Citation(source_id="c", title="C"),
    ]
    spans_3 = [
        EvidenceSpan(source_id="a", text="Evidence A"),
        EvidenceSpan(source_id="b", text="Evidence B"),
        EvidenceSpan(source_id="c", text="Evidence C"),
    ]
    assert Synthesizer._calculate_confidence(citations_3, spans_3) == ClaimConfidence.HIGH

    # 3+ citations but NO evidence spans = capped at MEDIUM
    assert Synthesizer._calculate_confidence(citations_3, []) == ClaimConfidence.MEDIUM

    # 1-2 sources = MEDIUM
    citations_1 = [Citation(source_id="a", title="A")]
    assert Synthesizer._calculate_confidence(citations_1, []) == ClaimConfidence.MEDIUM

    # 0 sources = LOW
    assert Synthesizer._calculate_confidence([], []) == ClaimConfidence.LOW


# ── Test 5: Executor retries and handles failures ────────────────────


@pytest.mark.asyncio
async def test_executor_retries_on_failure():
    """Executor retries failed tools — system logic, not LLM."""
    registry = ToolRegistry()
    # Tool that fails
    failing_tool = MockTool(should_fail=True)
    registry.register(failing_tool)

    executor = ToolExecutor(registry, max_retries=2)
    graph = EvidenceGraph()
    graph.add_question("sq1", "Test")

    from evidentia.agent.tool_selector import ToolSelection

    selection = ToolSelection(question_id="sq1", tool_name="arxiv_search", query="test", reason="test")

    results = await executor.execute_batch([selection], graph)

    assert len(results) == 1
    assert not results[0].success
    assert executor.total_calls == 3  # Initial + 2 retries


# ── Test 6: Full agent pipeline is system-driven ─────────────────────


@pytest.mark.asyncio
async def test_full_agent_is_system_driven():
    """The full agent: system decomposes, selects tools, executes, checks, synthesizes."""
    llm = MockLLM(
        [
            # Response 1: decomposition
            json.dumps(
                {
                    "scope": "AI advances",
                    "sub_questions": [
                        {
                            "id": "sq1",
                            "question": "latest AI papers",
                            "evidence_type": "academic_papers",
                            "depends_on": [],
                            "priority": 1,
                        },
                    ],
                }
            ),
            # Response 2: synthesis
            json.dumps(
                {
                    "summary": "AI research has advanced significantly.",
                    "claims": [
                        {
                            "statement": "Recent papers show advances in AI.",
                            "based_on_questions": ["sq1"],
                            "key_evidence_indices": [0, 1],
                        }
                    ],
                }
            ),
        ]
    )

    registry = ToolRegistry()
    registry.register(MockTool())  # arxiv_search with mock results

    agent = EvidentiAgent(llm=llm, tool_registry=registry, max_iterations=3)
    result = await agent.run("What are the latest AI advances?")

    assert result.success
    assert len(result.claims) >= 1
    assert result.total_tool_calls >= 1
    # Confidence was set by SYSTEM, not LLM
    for claim in result.claims:
        assert claim.confidence in list(ClaimConfidence)


@pytest.mark.asyncio
async def test_agent_streams_events():
    """Agent emits structured events for the UI."""
    llm = MockLLM(
        [
            json.dumps(
                {
                    "scope": "Test",
                    "sub_questions": [
                        {
                            "id": "sq1",
                            "question": "test query",
                            "evidence_type": "academic_papers",
                            "depends_on": [],
                            "priority": 1,
                        },
                    ],
                }
            ),
            json.dumps(
                {
                    "summary": "Done.",
                    "claims": [
                        {"statement": "Test claim.", "based_on_questions": ["sq1"], "key_evidence_indices": [0]}
                    ],
                }
            ),
        ]
    )

    registry = ToolRegistry()
    registry.register(MockTool())

    agent = EvidentiAgent(llm=llm, tool_registry=registry)

    event_types = []
    async for event in agent.stream("test"):
        event_types.append(event.type)

    # Should have: run_started, phase(decompose), plan_ready, phase(gather),
    # tool_calling, tool_result, evidence_check, phase(synthesize), completed
    assert "run_started" in event_types
    assert "plan_ready" in event_types
    assert "tool_calling" in event_types
    assert "completed" in event_types
