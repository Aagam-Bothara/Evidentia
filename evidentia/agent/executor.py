"""Executor — runs tools with self-healing: retries, fallbacks, strategy switching.

The executor does NOT ask the LLM what to do when something fails.
It has built-in strategies:

1. Timeout → retry with backoff
2. API error → try the next tool in the fallback chain
3. Empty results → broaden the query and retry
4. All tools exhausted → mark sub-question as unfillable
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from evidentia.agent.evidence_graph import EvidenceFragment, EvidenceGraph
from evidentia.agent.tool_selector import ToolSelection
from evidentia.core.exceptions import ToolExecutionError
from evidentia.core.logging import get_logger
from evidentia.tools.base import ToolRegistry

logger = get_logger(__name__)


class ExecutionResult:
    """Result of executing a tool selection."""

    def __init__(
        self,
        question_id: str,
        tool_name: str,
        success: bool,
        fragments: list[EvidenceFragment],
        error: str | None = None,
    ) -> None:
        self.question_id = question_id
        self.tool_name = tool_name
        self.success = success
        self.fragments = fragments
        self.error = error


class ToolExecutor:
    """Executes tool calls with self-healing strategies.

    This is system logic — no LLM involved in error recovery.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        max_retries: int = 2,
    ) -> None:
        self._registry = registry
        self._max_retries = max_retries
        self.total_calls = 0

    async def execute_batch(
        self,
        selections: list[ToolSelection],
        graph: EvidenceGraph,
    ) -> list[ExecutionResult]:
        """Execute multiple tool calls, potentially in parallel.

        Independent selections run concurrently. The system decides parallelism
        based on whether the selections are for different sub-questions.
        """
        # Execute with staggered starts to avoid rate limiting
        results_raw: list[ExecutionResult | Exception] = []
        for i, sel in enumerate(selections):
            if i > 0:
                await asyncio.sleep(1.5)  # Stagger to avoid 429s
            result = await self._execute_one(sel, graph)
            results_raw.append(result)

        execution_results: list[ExecutionResult] = []
        for sel, result in zip(selections, results_raw, strict=False):
            if isinstance(result, Exception):
                execution_results.append(
                    ExecutionResult(
                        question_id=sel.question_id,
                        tool_name=sel.tool_name,
                        success=False,
                        fragments=[],
                        error=str(result),
                    )
                )
            else:
                execution_results.append(result)

        return execution_results

    async def _execute_one(
        self,
        selection: ToolSelection,
        graph: EvidenceGraph,
    ) -> ExecutionResult:
        """Execute a single tool call with retry logic."""
        tool = self._registry.get(selection.tool_name)
        if tool is None:
            return ExecutionResult(
                question_id=selection.question_id,
                tool_name=selection.tool_name,
                success=False,
                fragments=[],
                error=f"Tool '{selection.tool_name}' not found",
            )

        graph.mark_searching(selection.question_id, selection.tool_name)

        # Build tool input
        tool_input = self._build_input(selection)

        # Check cache first
        try:
            from evidentia.cache import RedisCache

            cached = await RedisCache.get(selection.tool_name, tool_input)
            if cached is not None:
                logger.info("tool_cache_hit", tool=selection.tool_name)
                fragments = self._extract_fragments(selection.tool_name, cached)
                for fragment in fragments:
                    graph.add_evidence(selection.question_id, fragment)
                return ExecutionResult(
                    question_id=selection.question_id,
                    tool_name=selection.tool_name,
                    success=len(fragments) > 0,
                    fragments=fragments,
                )
        except Exception:
            pass  # Cache miss or unavailable — proceed normally

        for attempt in range(self._max_retries + 1):
            try:
                self.total_calls += 1
                logger.info(
                    "executing_tool",
                    tool=selection.tool_name,
                    question=selection.question_id,
                    attempt=attempt + 1,
                )

                output = await tool.execute_with_timeout(tool_input)

                # Parse output into evidence fragments
                fragments = self._extract_fragments(selection.tool_name, output)

                if not fragments and attempt < self._max_retries:
                    # Strategy: empty results → broaden the query
                    logger.info("empty_results_retrying", tool=selection.tool_name)
                    tool_input = self._broaden_query(tool_input)
                    continue

                # Store evidence in the graph
                for fragment in fragments:
                    graph.add_evidence(selection.question_id, fragment)

                # Cache successful results
                if fragments:
                    try:
                        from evidentia.cache import RedisCache

                        await RedisCache.set(selection.tool_name, tool_input, output)
                    except Exception:
                        pass

                return ExecutionResult(
                    question_id=selection.question_id,
                    tool_name=selection.tool_name,
                    success=len(fragments) > 0,
                    fragments=fragments,
                )

            except Exception as exc:
                logger.warning(
                    "tool_attempt_failed",
                    tool=selection.tool_name,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt < self._max_retries:
                    delay = self._compute_backoff(exc, attempt)
                    logger.info("backoff_wait", tool=selection.tool_name, delay=f"{delay:.1f}s")
                    await asyncio.sleep(delay)
                    continue

                graph.mark_tool_failed(selection.question_id, selection.tool_name)
                return ExecutionResult(
                    question_id=selection.question_id,
                    tool_name=selection.tool_name,
                    success=False,
                    fragments=[],
                    error=str(exc),
                )

        # Should not reach here, but just in case
        return ExecutionResult(
            question_id=selection.question_id,
            tool_name=selection.tool_name,
            success=False,
            fragments=[],
            error="Exhausted retries",
        )

    def _extract_fragments(
        self,
        tool_name: str,
        output: dict[str, Any],
    ) -> list[EvidenceFragment]:
        """System logic: extract evidence fragments from tool output.

        Each tool has a known output schema — we parse it deterministically.
        """
        fragments: list[EvidenceFragment] = []
        data = output.get("data", [])

        if not isinstance(data, list):
            # Non-list outputs (e.g., python sandbox)
            if output.get("stdout") or output.get("return_value"):
                fragments.append(
                    EvidenceFragment(
                        source_tool=tool_name,
                        title="Computation result",
                        snippet=str(output.get("stdout", output.get("return_value", ""))),
                        raw_data=output,
                    )
                )
            return fragments

        for item in data:
            if not isinstance(item, dict):
                continue

            fragments.append(
                EvidenceFragment(
                    source_tool=tool_name,
                    title=item.get("title") or item.get("arxiv_id") or "",
                    authors=item.get("authors") or [],
                    url=item.get("url") or item.get("link") or "",
                    doi=item.get("doi") or "",
                    snippet=item.get("abstract") or item.get("snippet") or item.get("text") or "",
                    raw_data=item,
                )
            )

        return fragments

    @staticmethod
    def _compute_backoff(exc: Exception, attempt: int) -> float:
        """Compute backoff delay based on error type and attempt number.

        - 429 rate limit: exponential backoff with jitter, respects Retry-After
        - 5xx server errors: gentler exponential backoff
        - Other errors: linear backoff
        """
        if isinstance(exc, ToolExecutionError) and exc.status_code is not None:
            if exc.status_code == 429:
                if exc.retry_after is not None:
                    return min(exc.retry_after + random.uniform(0, 1), 60)
                return min(2**attempt + random.uniform(0, 1), 60)
            if exc.status_code >= 500:
                return min(1.5**attempt + random.uniform(0, 0.5), 30)
        return 1.0 * (attempt + 1)

    @staticmethod
    def _build_input(selection: ToolSelection) -> dict[str, Any]:
        """Build tool-specific input from the selection."""
        base: dict[str, Any] = {"query": selection.query}

        academic_tools = (
            "arxiv_search",
            "semantic_scholar",
            "pubmed_search",
            "openalex_search",
            "crossref_search",
        )
        if selection.tool_name in academic_tools:
            base["max_results"] = 10
        elif selection.tool_name == "web_search":
            base["max_results"] = 8
        elif selection.tool_name == "doi_lookup":
            base = {"doi": selection.query}

        return base

    @staticmethod
    def _broaden_query(tool_input: dict[str, Any]) -> dict[str, Any]:
        """System strategy: broaden a query when results are empty."""
        query = tool_input.get("query", "")
        # Remove specifics, keep core terms
        words = query.split()
        if len(words) > 4:
            tool_input["query"] = " ".join(words[:4])
        # Increase result limit
        if "max_results" in tool_input:
            tool_input["max_results"] = min(tool_input["max_results"] * 2, 20)
        return tool_input
