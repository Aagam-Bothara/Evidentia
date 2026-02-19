"""Research Agent — the core agent loop that drives Evidentia.

This is the actual agent. It:
1. Takes a user query
2. Asks the LLM to plan which tools to call
3. Executes those tools
4. Feeds results back to the LLM for reasoning
5. Repeats until the LLM has enough evidence
6. Synthesizes claims with citations
7. Returns a structured, verifiable answer

This implements a ReAct-style (Reason + Act) agent loop.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from evidentia.core.exceptions import BudgetExhaustedError
from evidentia.core.llm import BaseLLM
from evidentia.core.logging import get_logger
from evidentia.core.models import (
    Citation,
    Claim,
    ClaimConfidence,
    EvidenceSpan,
    Run,
    RunStatus,
    StepResult,
    StepStatus,
)
from evidentia.tools.base import ToolRegistry

logger = get_logger(__name__)

AGENT_SYSTEM_PROMPT = """\
You are Evidentia, a research agent that answers questions using real tools.
You MUST use tools to find evidence before making claims. Never fabricate information.

## Available Tools
{tool_descriptions}

## How You Work
1. THINK: Analyze the query and decide what information you need.
2. ACT: Call one or more tools to gather evidence.
3. OBSERVE: Review the tool results.
4. REPEAT: If you need more information, call more tools.
5. SYNTHESIZE: When you have enough evidence, produce your final answer.

## Output Rules
- Every claim must be backed by evidence from tool results.
- Cite sources with their titles, authors, and URLs.
- If sources conflict, flag the disagreement.
- If you can't find evidence, say so honestly.

## Tool Calling Format
When you want to call a tool, respond with a JSON block:
```json
{{"action": "tool_call", "tool": "<tool_name>", "input": {{<tool_input>}}}}
```

When you want to call multiple tools at once:
```json
{{"action": "multi_tool_call", "calls": [
  {{"tool": "<tool_name>", "input": {{<tool_input>}}}},
  {{"tool": "<tool_name>", "input": {{<tool_input>}}}}
]}}
```

When you have enough evidence and are ready to answer:
```json
{{"action": "final_answer", "claims": [
  {{
    "statement": "<atomic claim>",
    "confidence": "high|medium|low|conflicting",
    "citations": [
      {{"title": "<source title>", "authors": ["<author>"], "url": "<url>", "doi": "<doi or null>"}}
    ],
    "evidence": ["<exact text snippet from source>"],
    "conflicting_evidence": []
  }}
], "summary": "<brief natural language summary>"}}
```

Think step by step. Be thorough but efficient.
"""


class ResearchAgent:
    """The actual research agent — a ReAct loop over tools and an LLM.

    This is the heart of Evidentia. It takes a query and autonomously:
    - Plans what to search
    - Executes tool calls
    - Reasons over results
    - Decides when it has enough evidence
    - Produces structured claims with citations
    """

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

    async def run(self, query: str) -> AgentResult:
        """Execute the full agent loop for a research query."""
        run = Run(query=query, status=RunStatus.EXECUTING)
        logger.info("agent_started", run_id=run.id, query=query)

        # Build system prompt with actual tool descriptions
        tool_descriptions = self._format_tool_descriptions()
        system_prompt = AGENT_SYSTEM_PROMPT.format(tool_descriptions=tool_descriptions)

        # Conversation history for the agent
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

        total_tool_calls = 0
        all_steps: list[StepResult] = []
        trace: list[TraceEntry] = []

        for iteration in range(self._max_iterations):
            logger.info("agent_iteration", iteration=iteration + 1, run_id=run.id)

            # Ask the LLM what to do next
            response = await self._llm.chat(messages, temperature=0.0)
            trace.append(TraceEntry(role="assistant", content=response.content))

            # Parse the agent's response
            action = self._parse_action(response.content)

            if action is None:
                # LLM gave a plain text response — treat as reasoning, ask it to act
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Please use a tool to gather evidence, or if you have enough evidence, "
                            "produce your final_answer in the required JSON format."
                        ),
                    }
                )
                continue

            # ── Final answer ─────────────────────────────────────────
            if action["action"] == "final_answer":
                run.status = RunStatus.COMPLETED
                run.completed_at = datetime.now(UTC)
                claims = self._parse_claims(action)
                run.claims = claims

                logger.info(
                    "agent_completed",
                    run_id=run.id,
                    iterations=iteration + 1,
                    tool_calls=total_tool_calls,
                    claims=len(claims),
                )

                return AgentResult(
                    run=run,
                    claims=claims,
                    summary=action.get("summary", ""),
                    steps=all_steps,
                    trace=trace,
                    total_tool_calls=total_tool_calls,
                    total_iterations=iteration + 1,
                )

            # ── Single tool call ─────────────────────────────────────
            if action["action"] == "tool_call":
                if total_tool_calls >= self._max_tool_calls:
                    raise BudgetExhaustedError(f"Exceeded {self._max_tool_calls} tool calls")

                tool_name = action["tool"]
                tool_input = action.get("input", {})
                step, result_text = await self._execute_tool(tool_name, tool_input)
                all_steps.append(step)
                total_tool_calls += 1

                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Tool `{tool_name}` returned:\n```json\n{result_text}\n```",
                    }
                )
                trace.append(TraceEntry(role="tool", tool=tool_name, content=result_text))

            # ── Multiple tool calls ──────────────────────────────────
            elif action["action"] == "multi_tool_call":
                calls = action.get("calls", [])
                results_text_parts: list[str] = []

                for call in calls:
                    if total_tool_calls >= self._max_tool_calls:
                        break
                    tool_name = call["tool"]
                    tool_input = call.get("input", {})
                    step, result_text = await self._execute_tool(tool_name, tool_input)
                    all_steps.append(step)
                    total_tool_calls += 1
                    results_text_parts.append(f"**{tool_name}**:\n```json\n{result_text}\n```")
                    trace.append(TraceEntry(role="tool", tool=tool_name, content=result_text))

                combined_results = "\n\n".join(results_text_parts)
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Tool results:\n\n{combined_results}",
                    }
                )

        # Exhausted iterations
        run.status = RunStatus.FAILED
        run.completed_at = datetime.now(UTC)
        logger.warning("agent_max_iterations", run_id=run.id)

        return AgentResult(
            run=run,
            claims=[],
            summary="Agent exhausted maximum iterations without producing a final answer.",
            steps=all_steps,
            trace=trace,
            total_tool_calls=total_tool_calls,
            total_iterations=self._max_iterations,
        )

    async def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> tuple[StepResult, str]:
        """Execute a single tool and return (StepResult, result_text)."""
        tool = self._tools.get(tool_name)

        if tool is None:
            error_msg = f"Tool '{tool_name}' not found. Available: {self._tools.tool_names}"
            step = StepResult(
                step_id=f"step_{tool_name}",
                tool_name=tool_name,
                status=StepStatus.FAILED,
                error=error_msg,
            )
            return step, json.dumps({"error": error_msg})

        started = datetime.now(UTC)
        try:
            logger.info("tool_executing", tool=tool_name, input_keys=list(tool_input.keys()))
            output = await tool.execute_with_timeout(tool_input)
            step = StepResult(
                step_id=f"step_{tool_name}",
                tool_name=tool_name,
                status=StepStatus.SUCCESS,
                output=output,
                started_at=started,
                completed_at=datetime.now(UTC),
            )
            # Truncate large outputs for the LLM context
            result_text = json.dumps(output, indent=2, default=str)
            if len(result_text) > 8000:
                result_text = result_text[:8000] + "\n... (truncated)"
            return step, result_text

        except Exception as exc:
            logger.error("tool_failed", tool=tool_name, error=str(exc))
            step = StepResult(
                step_id=f"step_{tool_name}",
                tool_name=tool_name,
                status=StepStatus.FAILED,
                error=str(exc),
                started_at=started,
                completed_at=datetime.now(UTC),
            )
            return step, json.dumps({"error": str(exc)})

    def _parse_action(self, content: str) -> dict[str, Any] | None:
        """Extract a JSON action block from the LLM response."""
        # Try to find JSON in the response
        text = content.strip()

        # Look for ```json blocks
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start) if "```" in text[start:] else len(text)
            text = text[start:end].strip()

        # Try direct JSON parse
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "action" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in the text
        brace_start = text.find("{")
        if brace_start == -1:
            return None

        # Find matching closing brace
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

    def _parse_claims(self, action: dict[str, Any]) -> list[Claim]:
        """Parse claims from the agent's final_answer action."""
        claims: list[Claim] = []
        for raw in action.get("claims", []):
            citations = [
                Citation(
                    source_id=c.get("doi", c.get("url", "")),
                    title=c.get("title", ""),
                    authors=c.get("authors", []),
                    url=c.get("url"),
                    doi=c.get("doi"),
                )
                for c in raw.get("citations", [])
            ]

            evidence_spans = [EvidenceSpan(source_id="", text=e) for e in raw.get("evidence", [])]

            conflicting = [EvidenceSpan(source_id="", text=e) for e in raw.get("conflicting_evidence", [])]

            confidence_map = {
                "high": ClaimConfidence.HIGH,
                "medium": ClaimConfidence.MEDIUM,
                "low": ClaimConfidence.LOW,
                "conflicting": ClaimConfidence.CONFLICTING,
            }

            claims.append(
                Claim(
                    statement=raw.get("statement", ""),
                    confidence=confidence_map.get(raw.get("confidence", "medium"), ClaimConfidence.MEDIUM),
                    citations=citations,
                    evidence_spans=evidence_spans,
                    conflicting_evidence=conflicting,
                )
            )

        return claims

    def _format_tool_descriptions(self) -> str:
        """Format tool metadata into a string for the system prompt."""
        lines: list[str] = []
        for meta in self._tools.list_tools():
            lines.append(f"- **{meta.name}** ({meta.category}): {meta.description}")
            lines.append(f"  Input: {json.dumps(meta.input_schema, indent=2)}")
        return "\n".join(lines)


class TraceEntry:
    """A single entry in the agent's execution trace."""

    def __init__(self, role: str, content: str, tool: str | None = None) -> None:
        self.role = role
        self.content = content
        self.tool = tool
        self.timestamp = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "tool": self.tool,
            "content": self.content[:500],  # Truncate for display
            "timestamp": self.timestamp.isoformat(),
        }


class AgentResult:
    """The complete result of an agent run."""

    def __init__(
        self,
        run: Run,
        claims: list[Claim],
        summary: str,
        steps: list[StepResult],
        trace: list[TraceEntry],
        total_tool_calls: int,
        total_iterations: int,
    ) -> None:
        self.run = run
        self.claims = claims
        self.summary = summary
        self.steps = steps
        self.trace = trace
        self.total_tool_calls = total_tool_calls
        self.total_iterations = total_iterations

    @property
    def success(self) -> bool:
        return self.run.status == RunStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run.id,
            "query": self.run.query,
            "status": self.run.status.value,
            "summary": self.summary,
            "claims": [c.model_dump() for c in self.claims],
            "total_tool_calls": self.total_tool_calls,
            "total_iterations": self.total_iterations,
            "elapsed_seconds": self.run.elapsed_seconds,
            "trace": [t.to_dict() for t in self.trace],
        }
