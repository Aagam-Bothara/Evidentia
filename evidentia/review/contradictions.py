"""Cross-study contradiction detection — finds conflicting findings.

Analyzes included papers to identify where studies disagree on outcomes,
effect sizes, or conclusions. This helps researchers identify evidence
gaps and areas needing further investigation.

Features:
- Contradiction taxonomy: empirical vs methodological vs interpretive
- Severity levels: mild, moderate, strong
- Evidence spans: quotes from each paper supporting the contradiction

This is a moat feature: requires accumulated paper analysis that no
simple API wrapper can provide.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from evidentia.core.llm import BaseLLM
from evidentia.core.logging import get_logger
from evidentia.review.models import PaperRecord

logger = get_logger(__name__)


class ContradictionType(str, Enum):
    """Taxonomy of scientific disagreements."""

    EMPIRICAL = "empirical"  # Opposite empirical findings (e.g., different effect directions)
    METHODOLOGICAL = "methodological"  # Different methods leading to different conclusions
    INTERPRETIVE = "interpretive"  # Same data, different interpretations or framing
    POPULATION = "population"  # Different results due to different study populations
    UNKNOWN = "unknown"


CONTRADICTION_TYPE_DESCRIPTIONS: dict[ContradictionType, str] = {
    ContradictionType.EMPIRICAL: "Direct empirical disagreement — opposite findings or effect directions",
    ContradictionType.METHODOLOGICAL: "Methodological divergence — different methods produce different results",
    ContradictionType.INTERPRETIVE: "Interpretive disagreement — similar data, different conclusions",
    ContradictionType.POPULATION: "Population difference — results differ due to different study populations",
    ContradictionType.UNKNOWN: "Unclassified disagreement",
}


class ContradictionPair(BaseModel):
    """A detected contradiction between two papers."""

    paper_a_index: int
    paper_b_index: int
    paper_a_title: str = ""
    paper_b_title: str = ""
    dimension: str = ""  # e.g. "effect_size", "conclusion", "methodology"
    contradiction_type: ContradictionType = ContradictionType.UNKNOWN
    description: str = ""
    severity: str = "moderate"  # mild, moderate, strong
    confidence: float = 0.0
    evidence_a: str = ""  # Text span from paper A
    evidence_b: str = ""  # Text span from paper B


class ContradictionReport(BaseModel):
    """Full contradiction analysis for a set of papers."""

    total_papers_analyzed: int = 0
    contradictions: list[ContradictionPair] = Field(default_factory=list)
    consensus_areas: list[str] = Field(default_factory=list)
    summary: str = ""
    type_distribution: dict[str, int] = Field(default_factory=dict)


CONTRADICTION_SYSTEM_PROMPT = """\
You are a research synthesis expert. Analyze a set of academic papers and \
identify contradictions — cases where studies disagree on findings, effect \
sizes, conclusions, or methodological approaches.

For each pair of contradicting papers, identify:
- Which papers contradict (by index)
- The dimension of disagreement (effect_size, conclusion, population, methodology, outcome_measure)
- The contradiction TYPE — this is critical for researchers:
  * "empirical": Direct empirical disagreement (e.g., Paper A finds treatment works, Paper B finds it doesn't)
  * "methodological": Different methods lead to different results (e.g., RCT vs observational study differ)
  * "interpretive": Similar data but different conclusions/framing
  * "population": Different results because of different study populations
- A clear description of the contradiction
- Severity: "mild" (minor differences), "moderate" (different conclusions), "strong" (opposite findings)
- Your confidence in this being a genuine contradiction (0.0-1.0)
- evidence_a: A brief quote or paraphrase from Paper A's abstract supporting the contradiction
- evidence_b: A brief quote or paraphrase from Paper B's abstract supporting the contradiction

Also identify areas of consensus — topics where all papers agree.

Output JSON:
{
  "contradictions": [
    {
      "paper_a_index": 0,
      "paper_b_index": 2,
      "dimension": "effect_size",
      "contradiction_type": "empirical",
      "description": "Paper 0 reports large positive effect (d=0.8) while Paper 2 finds no significant effect (d=0.1)",
      "severity": "strong",
      "confidence": 0.85,
      "evidence_a": "showed significant improvement (d=0.8, p<0.001)",
      "evidence_b": "no statistically significant difference was observed (d=0.1, p=0.42)"
    }
  ],
  "consensus_areas": [
    "All studies agree that intervention X is safe with minimal side effects",
    "Consistent finding that the effect is stronger in younger populations"
  ],
  "summary": "3 contradictions found across 5 papers, primarily around effect sizes. Strong consensus on safety."
}

Rules:
- Only flag genuine contradictions, not just different study populations or timeframes
- Confidence < 0.6 should not be included
- Focus on substantive scientific disagreements, not stylistic differences
- ALWAYS classify the contradiction_type — this helps researchers understand WHY studies disagree
"""


class ContradictionDetector:
    """Detects conflicting findings across papers in a systematic review."""

    BATCH_SIZE = 8  # Larger batches since we need cross-paper comparison

    def __init__(self, llm: BaseLLM) -> None:
        self._llm = llm

    async def detect(self, papers: list[PaperRecord]) -> ContradictionReport:
        """Analyze papers for contradictions."""
        if len(papers) < 2:
            return ContradictionReport(
                total_papers_analyzed=len(papers),
                summary="Insufficient papers for contradiction analysis (need at least 2).",
            )

        all_contradictions: list[ContradictionPair] = []
        all_consensus: list[str] = []

        # Process in overlapping windows to catch cross-batch contradictions
        for batch_start in range(0, len(papers), self.BATCH_SIZE):
            batch = papers[batch_start : batch_start + self.BATCH_SIZE]
            if len(batch) < 2:
                continue

            result = await self._analyze_batch(batch, offset=batch_start)
            all_contradictions.extend(result.contradictions)
            all_consensus.extend(result.consensus_areas)

            if batch_start + self.BATCH_SIZE < len(papers):
                await asyncio.sleep(0.5)

        # Deduplicate contradictions (same pair might appear in overlapping batches)
        unique_contradictions = self._dedupe_contradictions(all_contradictions)

        # Sort by severity then confidence
        severity_order = {"strong": 0, "moderate": 1, "mild": 2}
        unique_contradictions.sort(key=lambda c: (severity_order.get(c.severity, 1), -c.confidence))

        # Deduplicate consensus areas
        unique_consensus = list(dict.fromkeys(all_consensus))

        # Type distribution
        type_dist: dict[str, int] = {}
        for c in unique_contradictions:
            t = c.contradiction_type.value
            type_dist[t] = type_dist.get(t, 0) + 1

        summary = self._build_summary(unique_contradictions, unique_consensus, len(papers))

        return ContradictionReport(
            total_papers_analyzed=len(papers),
            contradictions=unique_contradictions,
            consensus_areas=unique_consensus[:10],
            summary=summary,
            type_distribution=type_dist,
        )

    async def _analyze_batch(self, papers: list[PaperRecord], offset: int = 0) -> ContradictionReport:
        """Analyze a batch of papers for contradictions."""
        papers_text = self._format_papers(papers, offset)

        try:
            response = await self._llm.chat(
                messages=[
                    {"role": "system", "content": CONTRADICTION_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Analyze these papers for contradictions:\n\n{papers_text}"},
                ],
                temperature=0.0,
                response_format="json",
            )
            data = response.as_json()
            return self._parse_result(data, papers, offset)
        except Exception as exc:
            logger.warning("contradiction_llm_failed", error=str(exc))
            return ContradictionReport(
                total_papers_analyzed=len(papers),
                summary=f"Contradiction analysis failed: {exc}",
            )

    def _parse_result(
        self,
        data: dict[str, Any],
        papers: list[PaperRecord],
        offset: int,
    ) -> ContradictionReport:
        """Parse LLM contradiction analysis output."""
        contradictions: list[ContradictionPair] = []

        for raw in data.get("contradictions", []):
            a_idx = raw.get("paper_a_index", -1)
            b_idx = raw.get("paper_b_index", -1)
            confidence = raw.get("confidence", 0.0)

            # Skip low-confidence contradictions
            if confidence < 0.6:
                continue

            # Validate indices
            if not (0 <= a_idx - offset < len(papers) and 0 <= b_idx - offset < len(papers)):
                # Try treating as local indices
                if 0 <= a_idx < len(papers) and 0 <= b_idx < len(papers):
                    a_idx = a_idx + offset
                    b_idx = b_idx + offset
                else:
                    continue

            a_local = a_idx - offset
            b_local = b_idx - offset

            # Parse contradiction type
            raw_type = raw.get("contradiction_type", "unknown")
            try:
                ctype = ContradictionType(raw_type)
            except ValueError:
                ctype = ContradictionType.UNKNOWN

            contradictions.append(
                ContradictionPair(
                    paper_a_index=a_idx,
                    paper_b_index=b_idx,
                    paper_a_title=papers[a_local].title if 0 <= a_local < len(papers) else "",
                    paper_b_title=papers[b_local].title if 0 <= b_local < len(papers) else "",
                    dimension=raw.get("dimension", "unspecified"),
                    contradiction_type=ctype,
                    description=raw.get("description", ""),
                    severity=(
                        raw.get("severity", "moderate")
                        if raw.get("severity") in ("mild", "moderate", "strong")
                        else "moderate"
                    ),
                    confidence=max(0.0, min(1.0, float(confidence))),
                    evidence_a=str(raw.get("evidence_a", "")),
                    evidence_b=str(raw.get("evidence_b", "")),
                )
            )

        consensus = data.get("consensus_areas", [])
        summary = data.get("summary", "")

        return ContradictionReport(
            total_papers_analyzed=len(papers),
            contradictions=contradictions,
            consensus_areas=consensus if isinstance(consensus, list) else [],
            summary=summary,
        )

    @staticmethod
    def _dedupe_contradictions(
        contradictions: list[ContradictionPair],
    ) -> list[ContradictionPair]:
        """Remove duplicate contradiction pairs."""
        seen: set[tuple[int, int, str]] = set()
        unique: list[ContradictionPair] = []

        for c in contradictions:
            key = (min(c.paper_a_index, c.paper_b_index), max(c.paper_a_index, c.paper_b_index), c.dimension)
            if key not in seen:
                seen.add(key)
                unique.append(c)

        return unique

    @staticmethod
    def _build_summary(
        contradictions: list[ContradictionPair],
        consensus: list[str],
        total_papers: int,
    ) -> str:
        """Build a human-readable summary."""
        if not contradictions:
            if consensus:
                return (
                    f"No contradictions found across {total_papers} papers."
                    f" Strong consensus on {len(consensus)} area(s)."
                )
            return f"No contradictions detected across {total_papers} papers."

        strong = sum(1 for c in contradictions if c.severity == "strong")
        moderate = sum(1 for c in contradictions if c.severity == "moderate")
        mild = sum(1 for c in contradictions if c.severity == "mild")

        parts = [f"{len(contradictions)} contradiction(s) found across {total_papers} papers"]
        severity_parts = []
        if strong:
            severity_parts.append(f"{strong} strong")
        if moderate:
            severity_parts.append(f"{moderate} moderate")
        if mild:
            severity_parts.append(f"{mild} mild")
        if severity_parts:
            parts.append(f"({', '.join(severity_parts)})")

        # Add type breakdown
        type_counts: dict[str, int] = {}
        for c in contradictions:
            t = c.contradiction_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        type_parts = [f"{count} {t}" for t, count in type_counts.items() if t != "unknown"]
        if type_parts:
            parts.append(f". Types: {', '.join(type_parts)}")

        if consensus:
            parts.append(f". Consensus on {len(consensus)} area(s)")

        return " ".join(parts) + "."

    @staticmethod
    def _format_papers(papers: list[PaperRecord], offset: int = 0) -> str:
        parts: list[str] = []
        for i, p in enumerate(papers):
            idx = offset + i
            lines = [f"[{idx}] Title: {p.title}"]
            if p.abstract:
                lines.append(f"    Abstract: {p.abstract[:800]}")
            if p.authors:
                lines.append(f"    Authors: {', '.join(p.authors[:5])}")
            if p.published_date:
                lines.append(f"    Date: {p.published_date}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)
