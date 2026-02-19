"""Query Decomposer — the system breaks a research query into evidence needs.

This is NOT "ask the LLM what to do." The decomposer uses the LLM as a tool
to extract structure, but the SYSTEM defines what structure it needs:
- Sub-questions that must be answered
- What type of evidence each sub-question requires
- What tools are appropriate for each evidence type
- Dependencies between sub-questions

The system controls the schema. The LLM fills in the blanks.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from evidentia.core.llm import BaseLLM
from evidentia.core.logging import get_logger

logger = get_logger(__name__)


class EvidenceType(str, Enum):
    """What kind of evidence a sub-question needs."""

    ACADEMIC_PAPERS = "academic_papers"
    WEB_SOURCES = "web_sources"
    DATA_ANALYSIS = "data_analysis"
    FACTUAL_LOOKUP = "factual_lookup"
    COMPARISON = "comparison"
    DEFINITION = "definition"


# System-defined mapping: evidence type -> which tools can provide it
EVIDENCE_TOOL_MAP: dict[EvidenceType, list[str]] = {
    EvidenceType.ACADEMIC_PAPERS: [
        "arxiv_search",
        "semantic_scholar",
        "pubmed_search",
        "openalex_search",
        "crossref_search",
        "doi_lookup",
    ],
    EvidenceType.WEB_SOURCES: ["web_search"],
    EvidenceType.DATA_ANALYSIS: ["python_sandbox"],
    EvidenceType.FACTUAL_LOOKUP: ["web_search", "doi_lookup", "crossref_search"],
    EvidenceType.COMPARISON: ["arxiv_search", "semantic_scholar", "openalex_search", "web_search"],
    EvidenceType.DEFINITION: ["web_search", "semantic_scholar", "openalex_search"],
}


class SubQuestion(BaseModel):
    """A single atomic sub-question that needs evidence."""

    id: str
    question: str
    evidence_type: EvidenceType
    depends_on: list[str] = Field(default_factory=list)
    priority: int = 1  # 1 = must answer, 2 = should answer, 3 = nice to have


class ResearchPlan(BaseModel):
    """System-structured plan: what evidence do we need?"""

    original_query: str
    sub_questions: list[SubQuestion]
    scope: str = ""  # Brief description of the research scope

    @property
    def required_questions(self) -> list[SubQuestion]:
        return [sq for sq in self.sub_questions if sq.priority == 1]

    @property
    def independent_questions(self) -> list[SubQuestion]:
        """Sub-questions with no dependencies — can execute in parallel."""
        return [sq for sq in self.sub_questions if not sq.depends_on]

    def get_ready_questions(self, completed_ids: set[str]) -> list[SubQuestion]:
        """Return sub-questions whose dependencies are all satisfied."""
        return [
            sq
            for sq in self.sub_questions
            if sq.id not in completed_ids and all(dep in completed_ids for dep in sq.depends_on)
        ]


# The LLM is constrained to THIS exact schema — it doesn't decide the plan format.
DECOMPOSITION_PROMPT = """\
You are a query decomposition engine. Given a research query, break it into
atomic sub-questions that each need a specific type of evidence.

You MUST output valid JSON matching this EXACT schema:
{{
  "scope": "<one sentence describing the research scope>",
  "sub_questions": [
    {{
      "id": "sq1",
      "question": "<specific, searchable sub-question>",
      "evidence_type": "<one of: academic_papers, web_sources, data_analysis, factual_lookup, comparison, definition>",
      "depends_on": [],
      "priority": 1
    }}
  ]
}}

Rules:
- Each sub-question must be ATOMIC (answerable by a single search)
- evidence_type MUST be one of: academic_papers, web_sources, data_analysis, factual_lookup, comparison, definition
- priority: 1=must answer, 2=should answer, 3=nice to have
- depends_on: list of sub-question IDs that must be answered first
- Generate 4-10 sub-questions to ensure thorough coverage.
- For each key claim, create separate sub-questions that search different angles \
(e.g., one for definitions, one for empirical evidence, one for recent developments).
- Make questions specific enough to search for. "What is X?" is better than "Understand X."
"""


class QueryDecomposer:
    """Decomposes a user query into structured evidence needs.

    The LLM is used ONLY to extract sub-questions. The system defines:
    - The output schema (ResearchPlan)
    - The evidence type taxonomy (EvidenceType)
    - The tool mapping (EVIDENCE_TOOL_MAP)
    - The dependency logic
    """

    def __init__(self, llm: BaseLLM) -> None:
        self._llm = llm

    async def decompose(self, query: str) -> ResearchPlan:
        """Break a query into sub-questions with evidence type annotations."""
        response = await self._llm.chat(
            messages=[
                {"role": "system", "content": DECOMPOSITION_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
            response_format="json",
        )

        try:
            raw = response.as_json()
        except Exception:
            # Fallback: single sub-question matching the original query
            logger.warning("decomposition_parse_failed", query=query)
            return self._fallback_plan(query)

        return self._parse_plan(query, raw)

    def _parse_plan(self, query: str, raw: dict[str, Any]) -> ResearchPlan:
        """Parse LLM output into a validated ResearchPlan."""
        sub_questions: list[SubQuestion] = []

        for i, sq_raw in enumerate(raw.get("sub_questions", [])):
            # System validates evidence_type — reject if invalid
            try:
                ev_type = EvidenceType(sq_raw.get("evidence_type", "web_sources"))
            except ValueError:
                ev_type = EvidenceType.WEB_SOURCES

            sub_questions.append(
                SubQuestion(
                    id=sq_raw.get("id", f"sq{i + 1}"),
                    question=sq_raw.get("question", ""),
                    evidence_type=ev_type,
                    depends_on=sq_raw.get("depends_on", []),
                    priority=min(max(sq_raw.get("priority", 1), 1), 3),
                )
            )

        if not sub_questions:
            return self._fallback_plan(query)

        # System validation: remove invalid dependencies
        valid_ids = {sq.id for sq in sub_questions}
        for sq in sub_questions:
            sq.depends_on = [d for d in sq.depends_on if d in valid_ids]

        return ResearchPlan(
            original_query=query,
            sub_questions=sub_questions,
            scope=raw.get("scope", ""),
        )

    @staticmethod
    def _fallback_plan(query: str) -> ResearchPlan:
        """Generate a minimal plan when decomposition fails."""
        return ResearchPlan(
            original_query=query,
            sub_questions=[
                SubQuestion(
                    id="sq1",
                    question=query,
                    evidence_type=EvidenceType.ACADEMIC_PAPERS,
                    priority=1,
                ),
                SubQuestion(
                    id="sq2",
                    question=query,
                    evidence_type=EvidenceType.WEB_SOURCES,
                    priority=2,
                ),
            ],
        )
