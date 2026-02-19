"""Streaming agent — wraps ResearchAgent with real-time event emission."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from evidentia.core.llm import BaseLLM
from evidentia.core.logging import get_logger
from evidentia.core.models import RunStatus
from evidentia.tools.base import ToolRegistry

logger = get_logger(__name__)


class StreamEvent:
    """A single event emitted during agent execution."""

    def __init__(self, event_type: str, data: dict[str, Any]) -> None:
        self.type = event_type
        self.data = data
        self.timestamp = datetime.now(UTC).isoformat()

    def to_json(self) -> str:
        return json.dumps(
            {
                "type": self.type,
                "data": self.data,
                "timestamp": self.timestamp,
            },
            default=str,
        )


class StreamingAgent:
    """Wraps ResearchAgent to yield real-time events for the UI."""

    def __init__(
        self,
        llm: BaseLLM,
        tool_registry: ToolRegistry,
        max_iterations: int = 10,
        max_tool_calls: int = 30,
    ) -> None:
        self._llm = llm
        self._tools = tool_registry
        self._max_iterations = max_iterations
        self._max_tool_calls = max_tool_calls

    async def stream(self, query: str) -> AsyncGenerator[StreamEvent, None]:
        """Execute the agent loop, yielding events as they happen."""
        from evidentia.agent.researcher import AGENT_SYSTEM_PROMPT
        from evidentia.core.models import Run

        run = Run(query=query, status=RunStatus.EXECUTING)

        yield StreamEvent(
            "run_started",
            {
                "run_id": run.id,
                "query": query,
            },
        )

        # Build system prompt
        tool_descriptions = self._format_tool_descriptions()
        system_prompt = AGENT_SYSTEM_PROMPT.format(tool_descriptions=tool_descriptions)

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

        total_tool_calls = 0

        for iteration in range(self._max_iterations):
            yield StreamEvent(
                "thinking",
                {
                    "iteration": iteration + 1,
                    "message": f"Reasoning (iteration {iteration + 1})...",
                },
            )

            # Ask LLM
            response = await self._llm.chat(messages, temperature=0.0)

            yield StreamEvent(
                "agent_response",
                {
                    "iteration": iteration + 1,
                    "content": response.content[:500],
                },
            )

            # Parse action
            action = self._parse_action(response.content)

            if action is None:
                # Plain text — nudge the LLM
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Please use a tool to gather evidence, or produce "
                            "your final_answer in the required JSON format."
                        ),
                    }
                )
                continue

            # Final answer
            if action["action"] == "final_answer":
                yield StreamEvent("synthesizing", {"message": "Building claims from evidence..."})

                claims_data = []
                for raw in action.get("claims", []):
                    claims_data.append(
                        {
                            "statement": raw.get("statement", ""),
                            "confidence": raw.get("confidence", "medium"),
                            "citations": raw.get("citations", []),
                            "evidence": raw.get("evidence", []),
                            "conflicting_evidence": raw.get("conflicting_evidence", []),
                        }
                    )

                yield StreamEvent(
                    "completed",
                    {
                        "run_id": run.id,
                        "summary": action.get("summary", ""),
                        "claims": claims_data,
                        "total_tool_calls": total_tool_calls,
                        "total_iterations": iteration + 1,
                    },
                )
                return

            # Tool calls
            if action["action"] == "tool_call":
                calls = [{"tool": action["tool"], "input": action.get("input", {})}]
            elif action["action"] == "multi_tool_call":
                calls = action.get("calls", [])
            else:
                continue

            results_parts: list[str] = []
            for call in calls:
                if total_tool_calls >= self._max_tool_calls:
                    break

                tool_name = call["tool"]
                tool_input = call.get("input", {})

                yield StreamEvent(
                    "tool_calling",
                    {
                        "tool": tool_name,
                        "input": tool_input,
                    },
                )

                tool = self._tools.get(tool_name)
                if tool is None:
                    error_msg = f"Tool '{tool_name}' not found"
                    yield StreamEvent("tool_error", {"tool": tool_name, "error": error_msg})
                    results_parts.append(f"**{tool_name}**: Error — {error_msg}")
                    total_tool_calls += 1
                    continue

                try:
                    output = await tool.execute_with_timeout(tool_input)
                    total_tool_calls += 1
                    result_text = json.dumps(output, indent=2, default=str)
                    if len(result_text) > 8000:
                        result_text = result_text[:8000] + "\n...(truncated)"

                    # Summarize for UI
                    summary = self._summarize_tool_output(tool_name, output)
                    yield StreamEvent(
                        "tool_result",
                        {
                            "tool": tool_name,
                            "summary": summary,
                            "result_count": self._count_results(output),
                        },
                    )
                    results_parts.append(f"**{tool_name}**:\n```json\n{result_text}\n```")

                except Exception as exc:
                    total_tool_calls += 1
                    yield StreamEvent("tool_error", {"tool": tool_name, "error": str(exc)})
                    results_parts.append(f"**{tool_name}**: Error — {str(exc)}")

            combined = "\n\n".join(results_parts)
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": f"Tool results:\n\n{combined}"})

        # Max iterations reached
        yield StreamEvent(
            "failed",
            {
                "run_id": run.id,
                "reason": "Maximum iterations reached without final answer.",
                "total_tool_calls": total_tool_calls,
            },
        )

    def _parse_action(self, content: str) -> dict[str, Any] | None:
        """Extract JSON action from LLM response."""
        text = content.strip()
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start) if "```" in text[start:] else len(text)
            text = text[start:end].strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "action" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

        brace_start = text.find("{")
        if brace_start == -1:
            return None
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[brace_start : i + 1])
                        if isinstance(parsed, dict) and "action" in parsed:
                            return parsed
                    except json.JSONDecodeError:
                        pass
                    break
        return None

    def _format_tool_descriptions(self) -> str:
        lines: list[str] = []
        for meta in self._tools.list_tools():
            lines.append(f"- **{meta.name}** ({meta.category}): {meta.description}")
        return "\n".join(lines)

    @staticmethod
    def _summarize_tool_output(tool_name: str, output: dict[str, Any]) -> str:
        data = output.get("data", [])
        if isinstance(data, list) and data:
            first = data[0]
            title = first.get("title", first.get("arxiv_id", ""))
            return f"Found {len(data)} results. Top: {title}"
        return "Completed"

    @staticmethod
    def _count_results(output: dict[str, Any]) -> int:
        data = output.get("data", [])
        return len(data) if isinstance(data, list) else 1
