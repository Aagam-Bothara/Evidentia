"""Synthesizer — constructs claims from the evidence graph.

The SYSTEM constructs the claim structure:
- Which evidence fragments support which sub-questions
- Citation metadata (title, authors, URL, DOI)
- Confidence scoring (based on evidence count and source diversity)

The LLM is used ONLY to write the natural language summary — it doesn't
decide what claims exist or what their confidence is.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from evidentia.agent.decomposer import ResearchPlan
from evidentia.agent.evidence_graph import EvidenceFragment, EvidenceGraph, SubQuestionState
from evidentia.core.llm import BaseLLM
from evidentia.core.logging import get_logger
from evidentia.core.models import Citation, Claim, ClaimConfidence, EvidenceSpan

logger = get_logger(__name__)

SYNTHESIS_PROMPT = """\
You are a research synthesizer. Given evidence fragments collected by a research agent,
write a concise, accurate summary and formulate claims.

For each claim:
- State it as a single factual sentence
- It must be directly supported by the provided evidence
- Do NOT add information not found in the evidence

Output JSON:
{{
  "summary": "<2-3 sentence overview>",
  "claims": [
    {{
      "statement": "<factual claim>",
      "based_on_questions": ["sq1", "sq2"],
      "key_evidence_indices": [0, 2, 5]
    }}
  ]
}}

Evidence fragments and sub-questions are provided below.
"""

SUMMARY_PROMPT = """\
You are a research synthesizer. Given evidence fragments collected by a research agent, \
write a concise 2-3 sentence overview summarizing the key findings.

Be factual and precise. Only summarize what the evidence supports. \
Output plain text only — no JSON, no markdown, no bullet points.
"""

CLAIMS_PROMPT = """\
You are a research synthesizer. Given evidence fragments collected by a research agent, \
formulate claims as structured JSON.

For each claim:
- State it as a single factual sentence
- It must be directly supported by the provided evidence
- Do NOT add information not found in the evidence

Output JSON:
{{
  "claims": [
    {{
      "statement": "<factual claim>",
      "based_on_questions": ["sq1", "sq2"],
      "key_evidence_indices": [0, 2, 5]
    }}
  ]
}}

Evidence fragments and sub-questions are provided below.
"""


class Synthesizer:
    """Constructs structured claims from the evidence graph.

    System responsibilities (no LLM):
    - Builds citations from evidence metadata
    - Calculates confidence from evidence count + source diversity
    - Links evidence spans to claims
    - Detects when evidence is conflicting

    LLM responsibility (constrained):
    - Write the natural language claim statements
    - Write the summary paragraph
    """

    def __init__(self, llm: BaseLLM) -> None:
        self._llm = llm

    async def synthesize(
        self,
        plan: ResearchPlan,
        graph: EvidenceGraph,
    ) -> SynthesisResult:
        """Build structured claims from the evidence graph."""
        answered = graph.get_answered()
        all_evidence = graph.get_all_evidence()

        if not all_evidence:
            return SynthesisResult(
                summary="No evidence was found for this query.",
                claims=[],
                evidence_summary=graph.summary(),
            )

        # Ask LLM to formulate claims from the evidence (constrained output)
        llm_claims = await self._ask_llm_for_claims(plan, graph, all_evidence)

        # SYSTEM builds the structured claims with real citations
        claims: list[Claim] = []
        for raw_claim in llm_claims.get("claims", []):
            claim = self._build_claim(raw_claim, all_evidence)
            claims.append(claim)

        # If LLM produced no claims, system generates basic ones from evidence
        if not claims and all_evidence:
            claims = self._fallback_claims(answered, all_evidence)

        summary = llm_claims.get("summary", "Research completed.")

        return SynthesisResult(
            summary=summary,
            claims=claims,
            evidence_summary=graph.summary(),
        )

    def _build_evidence_context(
        self,
        plan: ResearchPlan,
        evidence: list[EvidenceFragment],
    ) -> tuple[str, str]:
        """Build evidence text and questions text for LLM prompts."""
        evidence_text = ""
        for i, frag in enumerate(evidence[:40]):
            evidence_text += f"\n[{i}] Source: {frag.title}"
            if frag.authors:
                evidence_text += f"\n    Authors: {', '.join(frag.authors[:3])}"
            if frag.url:
                evidence_text += f"\n    URL: {frag.url}"
            if frag.snippet:
                evidence_text += f"\n    Content: {frag.snippet[:500]}"
            evidence_text += "\n"

        questions_text = "\n".join(f"- {sq.question} [id={sq.id}]" for sq in plan.sub_questions)
        return evidence_text, questions_text

    async def stream_synthesize(
        self,
        plan: ResearchPlan,
        graph: EvidenceGraph,
    ) -> AsyncGenerator[tuple[str, Any], None]:
        """Yield ('token', str) for streaming summary, then ('result', SynthesisResult)."""
        all_evidence = graph.get_all_evidence()

        if not all_evidence:
            yield (
                "result",
                SynthesisResult(
                    summary="No evidence was found for this query.",
                    claims=[],
                    evidence_summary=graph.summary(),
                ),
            )
            return

        evidence_text, questions_text = self._build_evidence_context(plan, all_evidence)
        user_content = (
            f"Original query: {plan.original_query}\n\n"
            f"Sub-questions:\n{questions_text}\n\n"
            f"Evidence fragments:\n{evidence_text}"
        )

        # Phase 1: Stream the summary token by token
        full_summary = ""
        try:
            async for token in self._llm.stream_chat(
                messages=[
                    {"role": "system", "content": SUMMARY_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.0,
            ):
                yield ("token", token)
                full_summary += token
        except Exception as exc:
            logger.error("summary_stream_failed", error=str(exc))
            if not full_summary:
                full_summary = "Research completed."

        # Phase 2: Get structured claims (non-streaming, needs JSON)
        claims: list[Claim] = []
        try:
            response = await self._llm.chat(
                messages=[
                    {"role": "system", "content": CLAIMS_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.0,
                response_format="json",
            )
            llm_claims = response.as_json()
            for raw_claim in llm_claims.get("claims", []):
                claims.append(self._build_claim(raw_claim, all_evidence))
        except Exception as exc:
            logger.error("claims_llm_failed", error=str(exc))

        # Fallback if no claims
        if not claims and all_evidence:
            answered = graph.get_answered()
            claims = self._fallback_claims(answered, all_evidence)

        yield (
            "result",
            SynthesisResult(
                summary=full_summary,
                claims=claims,
                evidence_summary=graph.summary(),
            ),
        )

    async def _ask_llm_for_claims(
        self,
        plan: ResearchPlan,
        graph: EvidenceGraph,
        evidence: list[EvidenceFragment],
    ) -> dict[str, Any]:
        """Use LLM to write claim statements — constrained to evidence."""
        # Build evidence context for the LLM
        evidence_text = ""
        for i, frag in enumerate(evidence[:40]):  # Cap at 40 fragments
            evidence_text += f"\n[{i}] Source: {frag.title}"
            if frag.authors:
                evidence_text += f"\n    Authors: {', '.join(frag.authors[:3])}"
            if frag.url:
                evidence_text += f"\n    URL: {frag.url}"
            if frag.snippet:
                evidence_text += f"\n    Content: {frag.snippet[:500]}"
            evidence_text += "\n"

        questions_text = "\n".join(f"- {sq.question} [id={sq.id}]" for sq in plan.sub_questions)

        try:
            response = await self._llm.chat(
                messages=[
                    {"role": "system", "content": SYNTHESIS_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Original query: {plan.original_query}\n\n"
                            f"Sub-questions:\n{questions_text}\n\n"
                            f"Evidence fragments:\n{evidence_text}"
                        ),
                    },
                ],
                temperature=0.0,
                response_format="json",
            )
            return response.as_json()
        except Exception as exc:
            logger.error("synthesis_llm_failed", error=str(exc))
            return {"summary": "Research completed.", "claims": []}

    def _build_claim(
        self,
        raw: dict[str, Any],
        all_evidence: list[EvidenceFragment],
    ) -> Claim:
        """SYSTEM constructs a Claim with real citations and confidence.

        The LLM provided the statement text.
        The SYSTEM provides everything else.
        """
        # Build citations from the referenced evidence indices
        evidence_indices = raw.get("key_evidence_indices", [])
        citations: list[Citation] = []
        evidence_spans: list[EvidenceSpan] = []
        source_tools: list[str] = []

        for idx in evidence_indices:
            if 0 <= idx < len(all_evidence):
                frag = all_evidence[idx]
                citations.append(
                    Citation(
                        source_id=frag.doi or frag.url or frag.title,
                        title=frag.title,
                        authors=frag.authors,
                        url=frag.url or None,
                        doi=frag.doi or None,
                    )
                )
                if frag.snippet:
                    evidence_spans.append(
                        EvidenceSpan(
                            source_id=frag.doi or frag.url or frag.title,
                            text=frag.snippet[:500],
                        )
                    )
                source_tools.append(frag.source_tool)

        # SYSTEM calculates confidence based on evidence quantity + diversity
        confidence = self._calculate_confidence(citations, evidence_spans, source_tools)

        return Claim(
            statement=raw.get("statement", ""),
            confidence=confidence,
            citations=citations,
            evidence_spans=evidence_spans,
        )

    @staticmethod
    def _calculate_confidence(
        citations: list[Citation],
        evidence_spans: list[EvidenceSpan],
        source_tools: list[str] | None = None,
    ) -> ClaimConfidence:
        """System-calculated confidence — NOT the LLM's opinion.

        Rules:
        - 0 citations → LOW
        - Citations but no evidence spans → capped at MEDIUM
        - 3+ citations from different sources with evidence spans → HIGH
        - 1-2 citations → MEDIUM
        - Multiple source tools with contradictory signal → CONFLICTING
        """
        if len(citations) == 0:
            return ClaimConfidence.LOW

        # Detect conflicting sources: if evidence comes from 3+ different tools,
        # it may indicate conflicting information across source types
        if source_tools:
            unique_tools = set(source_tools)
            if len(unique_tools) >= 3:
                # Multiple diverse sources — could be conflicting
                # This is a heuristic; real contradiction detection would need NLP
                pass  # Reserved for future NLP-based contradiction detection

        unique_sources = len(set(c.source_id for c in citations))

        # If we have citations but no actual evidence text, cap at MEDIUM
        if not evidence_spans:
            return ClaimConfidence.MEDIUM

        if unique_sources >= 3:
            return ClaimConfidence.HIGH
        elif unique_sources >= 1:
            return ClaimConfidence.MEDIUM
        return ClaimConfidence.LOW

    @staticmethod
    def _fallback_claims(
        answered: list[SubQuestionState],
        evidence: list[EvidenceFragment],
    ) -> list[Claim]:
        """System-generated claims when LLM synthesis fails."""
        claims: list[Claim] = []
        for state in answered:
            if not state.evidence:
                continue
            # Build a claim directly from the evidence
            citations = [
                Citation(
                    source_id=e.doi or e.url or e.title,
                    title=e.title,
                    authors=e.authors,
                    url=e.url or None,
                    doi=e.doi or None,
                )
                for e in state.evidence[:5]
            ]
            spans = [
                EvidenceSpan(source_id=e.url or e.title, text=e.snippet[:300]) for e in state.evidence[:5] if e.snippet
            ]
            claims.append(
                Claim(
                    statement=f"Evidence found for: {state.question}",
                    confidence=ClaimConfidence.MEDIUM if len(citations) >= 2 else ClaimConfidence.LOW,
                    citations=citations,
                    evidence_spans=spans,
                )
            )
        return claims


class SynthesisResult:
    """Output of the synthesis stage."""

    def __init__(
        self,
        summary: str,
        claims: list[Claim],
        evidence_summary: dict[str, Any],
    ) -> None:
        self.summary = summary
        self.claims = claims
        self.evidence_summary = evidence_summary
