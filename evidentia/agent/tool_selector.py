"""Tool Selector — the SYSTEM picks which tools to run, not the LLM.

The tool selector uses:
1. Evidence type of the sub-question (from the decomposer)
2. The mapping table (evidence_type → tools)
3. Which tools have already been tried (from the evidence graph)
4. Which tools are available (from the registry)
5. Fallback ordering

This is deterministic system logic. No LLM involved.
"""

from __future__ import annotations

from evidentia.agent.decomposer import EVIDENCE_TOOL_MAP, EvidenceType, SubQuestion
from evidentia.agent.evidence_graph import EvidenceGraph, SubQuestionState
from evidentia.core.logging import get_logger
from evidentia.tools.base import ToolRegistry

logger = get_logger(__name__)


class ToolSelection:
    """A tool selection decision with rationale."""

    def __init__(
        self,
        question_id: str,
        tool_name: str,
        query: str,
        reason: str,
    ) -> None:
        self.question_id = question_id
        self.tool_name = tool_name
        self.query = query
        self.reason = reason


class ToolSelector:
    """System-driven tool selection.

    Decision tree (no LLM):
    1. Look at the sub-question's evidence_type
    2. Get the ordered list of tools for that type
    3. Filter out tools already tried for this question
    4. Filter out tools not available in the registry
    5. Pick the first available one
    6. If none left, return None (question is unfillable)
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._available = set(registry.tool_names)

    def select_tools(
        self,
        questions: list[SubQuestion],
        graph: EvidenceGraph,
    ) -> list[ToolSelection]:
        """For each sub-question, pick the best available tool.

        Returns a list of tool selections to execute.
        """
        selections: list[ToolSelection] = []

        for sq in questions:
            selection = self._select_for_question(sq, graph)
            if selection:
                selections.append(selection)
            else:
                logger.warning(
                    "no_tools_available",
                    question_id=sq.id,
                    evidence_type=sq.evidence_type,
                )

        return selections

    def _select_for_question(
        self,
        sq: SubQuestion,
        graph: EvidenceGraph,
    ) -> ToolSelection | None:
        """Pick the best tool for a specific sub-question."""
        # Get the ordered tool list for this evidence type
        candidate_tools = EVIDENCE_TOOL_MAP.get(sq.evidence_type, [])

        # Get what's already been tried
        state = graph._questions.get(sq.id)
        tried = set(state.tools_tried) if state else set()
        failed = set(state.tools_failed) if state else set()

        for tool_name in candidate_tools:
            # Skip if not available in registry
            if tool_name not in self._available:
                continue

            # Skip if already tried for this question
            if tool_name in tried:
                continue

            # DOI lookup only works with actual DOIs, not natural language queries
            if tool_name == "doi_lookup" and not self._looks_like_doi(sq.question):
                continue

            # Build the search query for this tool
            search_query = self._build_query(sq, tool_name)

            reason = f"evidence_type={sq.evidence_type.value}, first untried tool in priority order"
            if failed:
                reason += f", fallback from failed: {', '.join(failed)}"

            return ToolSelection(
                question_id=sq.id,
                tool_name=tool_name,
                query=search_query,
                reason=reason,
            )

        return None

    def get_fallback(
        self,
        question_id: str,
        sq: SubQuestion,
        graph: EvidenceGraph,
    ) -> ToolSelection | None:
        """Get the next fallback tool after a failure."""
        return self._select_for_question(sq, graph)

    @staticmethod
    def _looks_like_doi(text: str) -> bool:
        """Check if the text looks like a DOI (e.g., 10.1234/something)."""
        return text.strip().startswith("10.") and "/" in text

    @staticmethod
    def _build_query(sq: SubQuestion, tool_name: str) -> str:
        """Transform the sub-question into a tool-appropriate query.

        This is system logic — different tools need different query formats.
        """
        question = sq.question

        if tool_name == "arxiv_search":
            # ArXiv works better with keyword-style queries
            # Strip question marks and common filler words
            q = question.rstrip("?").strip()
            for word in ["What are", "What is", "How does", "Why do", "Can you explain"]:
                if q.lower().startswith(word.lower()):
                    q = q[len(word):].strip()
            return q

        if tool_name == "doi_lookup":
            # DOI lookup needs a DOI — extract if present, otherwise skip
            return question

        # Default: use the question as-is
        return question
