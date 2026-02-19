"""LLM-based title/abstract screening for systematic reviews.

Screens papers in batches of 5 against user-defined inclusion/exclusion
criteria. Uses structured JSON output with temperature=0.0 for consistency.

Features:
- Per-criteria explainability: each decision maps to specific criteria
- Evidence spans: cites text from the abstract justifying the decision
- Multi-pass calibration: runs N passes and tracks inter-pass agreement
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import Any

from evidentia.core.llm import BaseLLM
from evidentia.core.logging import get_logger
from evidentia.review.models import (
    CriterionEvaluation,
    PaperRecord,
    ScreeningDecision,
)

logger = get_logger(__name__)

SCREENING_SYSTEM_PROMPT = """\
You are a systematic review screening assistant. You evaluate academic papers \
against inclusion and exclusion criteria based on their title and abstract.

For each paper, decide:
- INCLUDE: Paper clearly meets all inclusion criteria and violates no exclusion criteria
- EXCLUDE: Paper clearly fails at least one inclusion criterion or meets an exclusion criterion
- UNCERTAIN: Cannot determine from title/abstract alone; needs full-text review

You MUST output valid JSON with this exact structure:
{
  "decisions": [
    {
      "paper_index": 0,
      "decision": "include",
      "reason": "Meets all inclusion criteria: RCT design, adult participants, CBT intervention",
      "confidence": 0.92,
      "criteria_evaluations": [
        {
          "criterion": "Must be a randomized controlled trial",
          "criterion_type": "inclusion",
          "met": true,
          "rationale": "Abstract states 'randomized controlled trial'",
          "evidence_span": "We conducted a randomized controlled trial"
        },
        {
          "criterion": "Must include adult participants",
          "criterion_type": "inclusion",
          "met": true,
          "rationale": "Participants are adults aged 25-65",
          "evidence_span": "adults aged 25-65 years"
        }
      ],
      "evidence_spans": [
        "We conducted a randomized controlled trial",
        "adults aged 25-65 years were enrolled"
      ]
    }
  ]
}

Rules:
- One decision per paper, in order
- decision must be exactly "include", "exclude", or "uncertain"
- reason must reference specific criteria
- confidence is 0.0 to 1.0
- criteria_evaluations: evaluate EVERY inclusion and exclusion criterion
- evidence_spans: quote 1-3 short text spans from the abstract that support the decision
- If abstract is insufficient, set met=null and note the limitation
"""


class Screener:
    """LLM-based title/abstract screening with explainability and calibration."""

    BATCH_SIZE = 5

    def __init__(self, llm: BaseLLM) -> None:
        self._llm = llm

    async def screen_all(
        self,
        papers: list[PaperRecord],
        inclusion_criteria: list[str],
        exclusion_criteria: list[str],
    ) -> list[PaperRecord]:
        """Screen all papers, updating their screening_decision in place.

        Returns the papers list with decisions populated.
        """
        total_batches = (len(papers) + self.BATCH_SIZE - 1) // self.BATCH_SIZE

        for batch_idx in range(0, len(papers), self.BATCH_SIZE):
            batch = papers[batch_idx : batch_idx + self.BATCH_SIZE]
            decisions = await self._screen_one_batch(
                batch, inclusion_criteria, exclusion_criteria
            )

            # Apply decisions to papers
            for decision in decisions:
                idx = batch_idx + decision.paper_index
                if 0 <= idx < len(papers):
                    paper = papers[idx]
                    # Low confidence → force uncertain
                    if decision.confidence < 0.7 and decision.decision != "uncertain":
                        paper.screening_decision = "uncertain"
                        paper.exclusion_reason = (
                            f"Low confidence ({decision.confidence:.2f}): {decision.reason}"
                        )
                    else:
                        paper.screening_decision = decision.decision
                        paper.exclusion_reason = decision.reason if decision.decision == "exclude" else None
                    paper.screening_confidence = decision.confidence
                    paper.criteria_evaluations = decision.criteria_evaluations or None
                    paper.evidence_spans = decision.evidence_spans or None

            batch_num = batch_idx // self.BATCH_SIZE + 1
            logger.info(
                "screening_batch_complete",
                batch=batch_num,
                total_batches=total_batches,
                screened=min(batch_idx + self.BATCH_SIZE, len(papers)),
                total=len(papers),
            )

            # Stagger to avoid rate limiting
            if batch_idx + self.BATCH_SIZE < len(papers):
                await asyncio.sleep(0.5)

        return papers

    async def screen_calibrated(
        self,
        papers: list[PaperRecord],
        inclusion_criteria: list[str],
        exclusion_criteria: list[str],
        num_passes: int = 2,
    ) -> list[PaperRecord]:
        """Multi-pass screening with inter-pass agreement tracking.

        Runs screening N times and uses majority vote for the final decision.
        Tracks agreement rate per paper — low agreement flags unreliable decisions.
        """
        if num_passes < 2:
            return await self.screen_all(papers, inclusion_criteria, exclusion_criteria)

        # Collect votes from each pass
        all_pass_decisions: list[list[ScreeningDecision]] = []
        temperatures = [0.0] + [0.1 * (i + 1) for i in range(num_passes - 1)]
        temperatures = temperatures[:num_passes]

        for pass_idx in range(num_passes):
            pass_decisions: list[ScreeningDecision] = []

            for batch_idx in range(0, len(papers), self.BATCH_SIZE):
                batch = papers[batch_idx : batch_idx + self.BATCH_SIZE]
                decisions = await self._screen_one_batch(
                    batch, inclusion_criteria, exclusion_criteria,
                    temperature=temperatures[pass_idx],
                )
                # Adjust paper indices to global
                for d in decisions:
                    d.paper_index = batch_idx + d.paper_index
                pass_decisions.extend(decisions)

                if batch_idx + self.BATCH_SIZE < len(papers):
                    await asyncio.sleep(0.3)

            all_pass_decisions.append(pass_decisions)

            logger.info(
                "calibration_pass_complete",
                pass_num=pass_idx + 1,
                total_passes=num_passes,
            )

        # Aggregate: majority vote with agreement tracking
        for paper_idx, paper in enumerate(papers):
            votes: list[str] = []
            best_decision: ScreeningDecision | None = None
            best_confidence = -1.0

            for pass_decisions in all_pass_decisions:
                for d in pass_decisions:
                    if d.paper_index == paper_idx:
                        votes.append(d.decision)
                        if d.confidence > best_confidence:
                            best_confidence = d.confidence
                            best_decision = d
                        break

            if not votes or best_decision is None:
                paper.screening_decision = "uncertain"
                paper.screening_confidence = 0.0
                paper.screening_votes = []
                paper.screening_agreement = 0.0
                continue

            # Majority vote
            vote_counts = Counter(votes)
            majority_decision = vote_counts.most_common(1)[0][0]
            agreement = vote_counts[majority_decision] / len(votes)

            # Apply decision
            if agreement < 0.5 or best_confidence < 0.7:
                paper.screening_decision = "uncertain"
                paper.exclusion_reason = (
                    f"Low agreement ({agreement:.0%}): votes={votes}"
                )
            else:
                paper.screening_decision = majority_decision
                paper.exclusion_reason = (
                    best_decision.reason if majority_decision == "exclude" else None
                )

            paper.screening_confidence = best_confidence
            paper.screening_agreement = round(agreement, 3)
            paper.screening_votes = votes
            paper.criteria_evaluations = best_decision.criteria_evaluations or None
            paper.evidence_spans = best_decision.evidence_spans or None

        return papers

    async def _screen_one_batch(
        self,
        papers: list[PaperRecord],
        inclusion: list[str],
        exclusion: list[str],
        temperature: float = 0.0,
    ) -> list[ScreeningDecision]:
        """Screen a batch of up to 5 papers in one LLM call."""
        papers_text = self._format_papers(papers)
        criteria_text = self._format_criteria(inclusion, exclusion)

        try:
            response = await self._llm.chat(
                messages=[
                    {"role": "system", "content": SCREENING_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"{criteria_text}\n\nPapers to screen:\n{papers_text}",
                    },
                ],
                temperature=temperature,
                response_format="json",
            )
            return self._parse_decisions(response.as_json(), len(papers))
        except Exception as exc:
            logger.warning("screening_llm_failed", error=str(exc))
            # On failure, mark all as uncertain
            return [
                ScreeningDecision(
                    paper_index=i,
                    decision="uncertain",
                    reason=f"Screening failed: {exc}",
                    confidence=0.0,
                )
                for i in range(len(papers))
            ]

    def _parse_decisions(
        self, data: dict[str, Any], expected_count: int
    ) -> list[ScreeningDecision]:
        """Parse and validate LLM JSON output."""
        decisions: list[ScreeningDecision] = []
        raw_decisions = data.get("decisions", [])
        seen_indices: set[int] = set()

        for raw in raw_decisions:
            idx = raw.get("paper_index", -1)
            decision = raw.get("decision", "uncertain")
            reason = raw.get("reason", "")
            confidence = raw.get("confidence", 0.0)

            # Validate decision value
            if decision not in ("include", "exclude", "uncertain"):
                decision = "uncertain"
                reason = f"Invalid decision from LLM: {raw.get('decision')}"

            # Validate confidence range
            if not isinstance(confidence, (int, float)):
                confidence = 0.0
            confidence = max(0.0, min(1.0, float(confidence)))

            # Parse criteria evaluations
            criteria_evals = self._parse_criteria_evaluations(
                raw.get("criteria_evaluations", [])
            )

            # Parse evidence spans
            evidence_spans = raw.get("evidence_spans", [])
            if not isinstance(evidence_spans, list):
                evidence_spans = []
            evidence_spans = [str(s) for s in evidence_spans if s][:5]

            if 0 <= idx < expected_count and idx not in seen_indices:
                seen_indices.add(idx)
                decisions.append(
                    ScreeningDecision(
                        paper_index=idx,
                        decision=decision,
                        reason=reason,
                        confidence=confidence,
                        criteria_evaluations=criteria_evals,
                        evidence_spans=evidence_spans,
                    )
                )

        # Fill in missing papers as uncertain
        for i in range(expected_count):
            if i not in seen_indices:
                decisions.append(
                    ScreeningDecision(
                        paper_index=i,
                        decision="uncertain",
                        reason="No decision returned by screening LLM",
                        confidence=0.0,
                    )
                )

        return sorted(decisions, key=lambda d: d.paper_index)

    @staticmethod
    def _parse_criteria_evaluations(
        raw_evals: list[dict[str, Any]],
    ) -> list[CriterionEvaluation]:
        """Parse criteria evaluation list from LLM output."""
        evaluations: list[CriterionEvaluation] = []
        if not isinstance(raw_evals, list):
            return evaluations

        for raw in raw_evals:
            if not isinstance(raw, dict):
                continue
            criterion = raw.get("criterion", "")
            if not criterion:
                continue

            met = raw.get("met")
            if met is not None and not isinstance(met, bool):
                met = None  # Invalid → uncertain

            evaluations.append(CriterionEvaluation(
                criterion=str(criterion),
                criterion_type=raw.get("criterion_type", "inclusion"),
                met=met,
                rationale=str(raw.get("rationale", "")),
                evidence_span=str(raw.get("evidence_span", "")),
            ))

        return evaluations

    @staticmethod
    def _format_papers(papers: list[PaperRecord]) -> str:
        """Format papers for the LLM prompt."""
        parts: list[str] = []
        for i, p in enumerate(papers):
            lines = [f"[{i}] Title: {p.title}"]
            if p.abstract:
                lines.append(f"    Abstract: {p.abstract[:600]}")
            if p.authors:
                lines.append(f"    Authors: {', '.join(p.authors[:5])}")
            if p.published_date:
                lines.append(f"    Date: {p.published_date}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    @staticmethod
    def _format_criteria(inclusion: list[str], exclusion: list[str]) -> str:
        """Format criteria for the LLM prompt."""
        lines = ["Inclusion criteria:"]
        for i, c in enumerate(inclusion, 1):
            lines.append(f"  IC{i}: {c}")
        if exclusion:
            lines.append("\nExclusion criteria:")
            for i, c in enumerate(exclusion, 1):
                lines.append(f"  EC{i}: {c}")
        return "\n".join(lines)
