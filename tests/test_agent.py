"""Tests for the research agent using a mock LLM."""

import json

import pytest

from evidentia.agent.researcher import ResearchAgent
from evidentia.core.llm import BaseLLM, LLMResponse
from evidentia.core.models import RunStatus
from evidentia.tools.base import BaseTool, ToolMetadata, ToolRegistry

# ── Mock LLM ─────────────────────────────────────────────────────────


class MockLLM(BaseLLM):
    """LLM that returns pre-scripted responses for testing."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_index = 0

    async def chat(self, messages, temperature=0.0, max_tokens=4096, response_format=None):
        if self._call_index < len(self._responses):
            content = self._responses[self._call_index]
            self._call_index += 1
            return LLMResponse(content=content, usage={"total_tokens": 100})
        return LLMResponse(content='{"action": "final_answer", "claims": [], "summary": "No more responses"}')

    async def chat_with_tools(self, messages, tools, temperature=0.0, max_tokens=4096):
        return await self.chat(messages, temperature, max_tokens)


# ── Mock Tool ────────────────────────────────────────────────────────


class MockSearchTool(BaseTool):
    """A fake search tool that returns canned results."""

    metadata = ToolMetadata(
        name="mock_search",
        description="Mock search for testing",
        category="test",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"data": {"type": "array"}}},
    )

    async def execute(self, input_data):
        return {
            "success": True,
            "data": [
                {
                    "title": "Test Paper: Advances in AI",
                    "authors": ["Alice Smith", "Bob Jones"],
                    "url": "https://example.com/paper1",
                    "abstract": "This paper explores recent advances in AI research.",
                }
            ],
        }


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_calls_tool_then_answers():
    """Agent should: receive query -> call tool -> get results -> produce final answer."""
    mock_responses = [
        # Iteration 1: Agent decides to search
        json.dumps(
            {
                "action": "tool_call",
                "tool": "mock_search",
                "input": {"query": "advances in AI"},
            }
        ),
        # Iteration 2: Agent sees results, produces final answer
        json.dumps(
            {
                "action": "final_answer",
                "claims": [
                    {
                        "statement": "Recent AI research has made significant advances.",
                        "confidence": "high",
                        "citations": [
                            {
                                "title": "Test Paper: Advances in AI",
                                "authors": ["Alice Smith", "Bob Jones"],
                                "url": "https://example.com/paper1",
                            }
                        ],
                        "evidence": ["This paper explores recent advances in AI research."],
                        "conflicting_evidence": [],
                    }
                ],
                "summary": "AI research has advanced significantly based on recent papers.",
            }
        ),
    ]

    llm = MockLLM(mock_responses)
    registry = ToolRegistry()
    registry.register(MockSearchTool())

    agent = ResearchAgent(llm=llm, tool_registry=registry, max_iterations=5)
    result = await agent.run("What are the latest advances in AI?")

    assert result.success
    assert result.run.status == RunStatus.COMPLETED
    assert len(result.claims) == 1
    assert result.claims[0].statement == "Recent AI research has made significant advances."
    assert result.claims[0].confidence.value == "high"
    assert len(result.claims[0].citations) == 1
    assert result.total_tool_calls == 1
    assert result.summary == "AI research has advanced significantly based on recent papers."


@pytest.mark.asyncio
async def test_agent_handles_multi_tool_call():
    """Agent should be able to call multiple tools at once."""
    mock_responses = [
        json.dumps(
            {
                "action": "multi_tool_call",
                "calls": [
                    {"tool": "mock_search", "input": {"query": "topic A"}},
                    {"tool": "mock_search", "input": {"query": "topic B"}},
                ],
            }
        ),
        json.dumps(
            {
                "action": "final_answer",
                "claims": [
                    {
                        "statement": "Both topics are well-researched.",
                        "confidence": "medium",
                        "citations": [],
                        "evidence": [],
                        "conflicting_evidence": [],
                    }
                ],
                "summary": "Covered both topics.",
            }
        ),
    ]

    llm = MockLLM(mock_responses)
    registry = ToolRegistry()
    registry.register(MockSearchTool())

    agent = ResearchAgent(llm=llm, tool_registry=registry)
    result = await agent.run("Compare topic A and topic B")

    assert result.success
    assert result.total_tool_calls == 2


@pytest.mark.asyncio
async def test_agent_handles_unknown_tool():
    """Agent should handle gracefully when it tries to call a non-existent tool."""
    mock_responses = [
        json.dumps(
            {
                "action": "tool_call",
                "tool": "nonexistent_tool",
                "input": {"query": "test"},
            }
        ),
        json.dumps(
            {
                "action": "final_answer",
                "claims": [],
                "summary": "Could not find the requested tool.",
            }
        ),
    ]

    llm = MockLLM(mock_responses)
    registry = ToolRegistry()
    registry.register(MockSearchTool())

    agent = ResearchAgent(llm=llm, tool_registry=registry)
    result = await agent.run("Test query")

    assert result.success
    assert result.total_tool_calls == 1  # It tried one call (which failed)


@pytest.mark.asyncio
async def test_agent_respects_max_iterations():
    """Agent should stop after max_iterations even if LLM never gives final_answer."""
    # LLM keeps calling tools forever
    mock_responses = [
        json.dumps({"action": "tool_call", "tool": "mock_search", "input": {"query": f"search {i}"}}) for i in range(20)
    ]

    llm = MockLLM(mock_responses)
    registry = ToolRegistry()
    registry.register(MockSearchTool())

    agent = ResearchAgent(llm=llm, tool_registry=registry, max_iterations=3)
    result = await agent.run("Endless query")

    assert not result.success
    assert result.run.status == RunStatus.FAILED
    assert result.total_iterations == 3


@pytest.mark.asyncio
async def test_agent_handles_plain_text_response():
    """Agent should nudge the LLM if it responds with plain text instead of JSON."""
    mock_responses = [
        "Let me think about this... I should search for papers on this topic.",  # plain text
        json.dumps(
            {
                "action": "tool_call",
                "tool": "mock_search",
                "input": {"query": "test"},
            }
        ),
        json.dumps(
            {
                "action": "final_answer",
                "claims": [
                    {
                        "statement": "Found relevant results.",
                        "confidence": "medium",
                        "citations": [],
                        "evidence": [],
                        "conflicting_evidence": [],
                    }
                ],
                "summary": "Done.",
            }
        ),
    ]

    llm = MockLLM(mock_responses)
    registry = ToolRegistry()
    registry.register(MockSearchTool())

    agent = ResearchAgent(llm=llm, tool_registry=registry)
    result = await agent.run("Test query")

    assert result.success
    assert result.total_tool_calls == 1


@pytest.mark.asyncio
async def test_agent_result_to_dict():
    """Agent result should serialize cleanly to JSON."""
    mock_responses = [
        json.dumps(
            {
                "action": "final_answer",
                "claims": [
                    {
                        "statement": "Test claim.",
                        "confidence": "high",
                        "citations": [{"title": "Source", "authors": ["Author"], "url": "https://example.com"}],
                        "evidence": ["evidence text"],
                        "conflicting_evidence": [],
                    }
                ],
                "summary": "Test summary.",
            }
        ),
    ]

    llm = MockLLM(mock_responses)
    registry = ToolRegistry()
    agent = ResearchAgent(llm=llm, tool_registry=registry)
    result = await agent.run("Test")

    data = result.to_dict()
    assert data["status"] == "completed"
    assert data["summary"] == "Test summary."
    assert len(data["claims"]) == 1

    # Should be JSON serializable
    json_str = json.dumps(data, default=str)
    assert len(json_str) > 0
