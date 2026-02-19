"""Evidentia Agent — the REAL agent, not a wrapper.

The control loop is SYSTEM-DRIVEN:

    ┌─────────────────────────────────────────────────────┐
    │  1. DECOMPOSE  (system + LLM for structure only)    │
    │     Query → Sub-questions with evidence types       │
    │                                                      │
    │  2. SELECT TOOLS  (system only, no LLM)             │
    │     Evidence type → tool mapping → pick tools       │
    │                                                      │
    │  3. EXECUTE  (system only, no LLM)                  │
    │     Run tools, retry on failure, fallback to next   │
    │                                                      │
    │  4. CHECK EVIDENCE  (system only, no LLM)           │
    │     Evidence graph: sufficient? gaps? contradictions?│
    │                                                      │
    │  5. If gaps → go to 2 with remaining questions      │
    │     If sufficient → go to 6                         │
    │                                                      │
    │  6. SYNTHESIZE  (system builds structure, LLM prose) │
    │     Evidence graph → Claims + Citations + Summary   │
    └─────────────────────────────────────────────────────┘

The LLM is used in exactly TWO places:
- Step 1: Extract sub-questions from the query (constrained to a schema)
- Step 6: Write natural language claim statements (constrained to evidence)

Everything else — tool selection, execution, retries, fallbacks,
evidence sufficiency, confidence scoring — is SYSTEM logic.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from evidentia.agent.decomposer import QueryDecomposer, ResearchPlan, SubQuestion
from evidentia.agent.evidence_graph import EvidenceGraph, EvidenceStatus
from evidentia.agent.executor import ToolExecutor
from evidentia.agent.synthesizer import Synthesizer, SynthesisResult
from evidentia.agent.tool_selector import ToolSelector
from evidentia.core.llm import BaseLLM
from evidentia.core.logging import get_logger
from evidentia.core.models import Claim, Run, RunStatus
from evidentia.tools.base import ToolRegistry

logger = get_logger(__name__)


class AgentEvent:
    """Event emitted during agent execution for UI streaming."""

    def __init__(self, event_type: str, data: dict[str, Any]) -> None:
        self.type = event_type
        self.data = data
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data, "timestamp": self.timestamp.isoformat()}


class AgentOutput:
    """Final structured output from the agent."""

    def __init__(
        self,
        query: str,
        summary: str,
        claims: list[Claim],
        evidence_summary: dict[str, Any],
        plan: ResearchPlan,
        total_tool_calls: int,
        total_iterations: int,
        elapsed_seconds: float,
        success: bool,
    ) -> None:
        self.query = query
        self.summary = summary
        self.claims = claims
        self.evidence_summary = evidence_summary
        self.plan = plan
        self.total_tool_calls = total_tool_calls
        self.total_iterations = total_iterations
        self.elapsed_seconds = elapsed_seconds
        self.success = success

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "summary": self.summary,
            "claims": [c.model_dump() for c in self.claims],
            "evidence_summary": self.evidence_summary,
            "plan": self.plan.model_dump(),
            "total_tool_calls": self.total_tool_calls,
            "total_iterations": self.total_iterations,
            "elapsed_seconds": self.elapsed_seconds,
            "success": self.success,
        }


class EvidentiAgent:
    """The real Evidentia agent — system-driven, not an LLM wrapper.

    The LLM is a component used for two specific tasks:
    1. Decomposing the query into sub-questions
    2. Writing natural language claim statements

    The agent itself controls:
    - Which tools to call and when
    - When evidence is sufficient
    - Retries and fallback strategies
    - Confidence scoring
    - Citation construction
    """

    def __init__(
        self,
        llm: BaseLLM,
        tool_registry: ToolRegistry,
        max_iterations: int = 5,
        max_tool_calls: int = 30,
        min_evidence_per_question: int = 1,
    ) -> None:
        self._decomposer = QueryDecomposer(llm)
        self._selector = ToolSelector(tool_registry)
        self._executor = ToolExecutor(tool_registry)
        self._synthesizer = Synthesizer(llm)
        self._max_iterations = max_iterations
        self._max_tool_calls = max_tool_calls
        self._min_evidence = min_evidence_per_question

    async def run(self, query: str) -> AgentOutput:
        """Execute the agent — collect all events and return final output."""
        output = None
        async for event in self.stream(query):
            if event.type == "completed":
                output = event.data.get("_output")
        if output:
            return output
        return AgentOutput(
            query=query, summary="Agent failed.", claims=[], evidence_summary={},
            plan=ResearchPlan(original_query=query, sub_questions=[]),
            total_tool_calls=0, total_iterations=0, elapsed_seconds=0, success=False,
        )

    async def stream(self, query: str) -> AsyncGenerator[AgentEvent, None]:
        """Execute the agent, yielding events for the UI."""
        start_time = datetime.now(timezone.utc)

        yield AgentEvent("run_started", {"query": query})

        # ── Step 1: DECOMPOSE ────────────────────────────────────────
        yield AgentEvent("phase", {"phase": "decompose", "message": "Analyzing query..."})

        try:
            plan = await self._decomposer.decompose(query)
        except Exception as exc:
            yield AgentEvent("error", {"message": f"Failed to decompose query: {exc}"})
            return

        yield AgentEvent("plan_ready", {
            "scope": plan.scope,
            "sub_questions": [
                {"id": sq.id, "question": sq.question, "evidence_type": sq.evidence_type.value}
                for sq in plan.sub_questions
            ],
        })

        # ── Initialize evidence graph ────────────────────────────────
        graph = EvidenceGraph(min_evidence_per_question=self._min_evidence)
        for sq in plan.sub_questions:
            graph.add_question(sq.id, sq.question)

        required_ids = {sq.id for sq in plan.required_questions}
        sq_map = {sq.id: sq for sq in plan.sub_questions}

        # ── Steps 2-4: SELECT → EXECUTE → CHECK (loop) ──────────────
        for iteration in range(self._max_iterations):
            yield AgentEvent("phase", {
                "phase": "gather",
                "iteration": iteration + 1,
                "message": f"Gathering evidence (round {iteration + 1})...",
            })

            # Step 2: SYSTEM selects tools (no LLM)
            ready_questions = plan.get_ready_questions(
                completed_ids={
                    s.question_id for s in graph.get_answered()
                }
            )

            if not ready_questions:
                # All questions either answered or blocked
                break

            selections = self._selector.select_tools(ready_questions, graph)

            if not selections:
                # No tools left to try — mark remaining as failed
                for sq in ready_questions:
                    state = graph._questions.get(sq.id)
                    if state:
                        state.status = EvidenceStatus.FAILED
                break

            # Emit what tools we're calling
            for sel in selections:
                yield AgentEvent("tool_calling", {
                    "tool": sel.tool_name,
                    "question": sq_map[sel.question_id].question,
                    "reason": sel.reason,
                })

            # Step 3: SYSTEM executes tools (no LLM)
            if self._executor.total_calls >= self._max_tool_calls:
                yield AgentEvent("budget_warning", {"message": "Tool call budget reached"})
                break

            results = await self._executor.execute_batch(selections, graph)

            for result in results:
                if result.success:
                    yield AgentEvent("tool_result", {
                        "tool": result.tool_name,
                        "question_id": result.question_id,
                        "evidence_count": len(result.fragments),
                        "summary": self._summarize_fragments(result.fragments),
                    })
                else:
                    yield AgentEvent("tool_error", {
                        "tool": result.tool_name,
                        "question_id": result.question_id,
                        "error": result.error or "Unknown error",
                    })

                    # System fallback: try next tool for this question
                    sq = sq_map.get(result.question_id)
                    if sq:
                        fallback = self._selector.get_fallback(result.question_id, sq, graph)
                        if fallback:
                            yield AgentEvent("fallback", {
                                "from_tool": result.tool_name,
                                "to_tool": fallback.tool_name,
                                "question_id": result.question_id,
                            })
                            fb_results = await self._executor.execute_batch([fallback], graph)
                            for fb in fb_results:
                                if fb.success:
                                    yield AgentEvent("tool_result", {
                                        "tool": fb.tool_name,
                                        "question_id": fb.question_id,
                                        "evidence_count": len(fb.fragments),
                                        "summary": self._summarize_fragments(fb.fragments),
                                    })

            # Step 4: SYSTEM checks evidence sufficiency (no LLM)
            ev_summary = graph.summary()
            yield AgentEvent("evidence_check", {
                "coverage": ev_summary["coverage"],
                "answered": ev_summary["answered"],
                "gaps": ev_summary["gaps"],
                "total_evidence": ev_summary["total_evidence_fragments"],
            })

            if graph.is_sufficient(required_ids):
                logger.info("evidence_sufficient", coverage=ev_summary["coverage"])
                break
            else:
                logger.info("evidence_insufficient", gaps=ev_summary["gaps"])

        # ── Step 6: SYNTHESIZE ───────────────────────────────────────
        yield AgentEvent("phase", {"phase": "synthesize", "message": "Building claims from evidence..."})

        synthesis = await self._synthesizer.synthesize(plan, graph)

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        output = AgentOutput(
            query=query,
            summary=synthesis.summary,
            claims=synthesis.claims,
            evidence_summary=graph.summary(),
            plan=plan,
            total_tool_calls=self._executor.total_calls,
            total_iterations=min(iteration + 1, self._max_iterations) if 'iteration' in dir() else 0,
            elapsed_seconds=elapsed,
            success=len(synthesis.claims) > 0,
        )

        yield AgentEvent("completed", {
            "summary": synthesis.summary,
            "claims": [c.model_dump() for c in synthesis.claims],
            "evidence_summary": graph.summary(),
            "total_tool_calls": self._executor.total_calls,
            "total_iterations": output.total_iterations,
            "elapsed_seconds": elapsed,
            "_output": output,  # Internal: for non-streaming .run() method
        })

    @staticmethod
    def _summarize_fragments(fragments: list) -> str:
        if not fragments:
            return "No results"
        first = fragments[0]
        title = first.title or "Untitled"
        return f"Found {len(fragments)} results. Top: {title}"
