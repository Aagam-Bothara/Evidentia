"""Systematic Review Engine — PRISMA-compliant multi-database review pipeline.

Phases:
1. IDENTIFICATION:  Search all selected databases in parallel
2. DEDUPLICATION:   Remove duplicates by DOI (exact) and title (fuzzy)
3. SCREENING:       LLM screens title+abstract against criteria (with calibration)
4. QUALITY SCORING: Multi-dimensional evidence quality assessment
5. CONTRADICTION:   Cross-study contradiction detection with taxonomy
6. REPORTING:       Generate PRISMA flow data, reproducibility hash, and results

Supports three review modes: fast, rigorous, publication-grade.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncGenerator

from evidentia.core.llm import BaseLLM
from evidentia.core.logging import get_logger
from evidentia.review.contradictions import ContradictionDetector
from evidentia.review.deduplicator import Deduplicator
from evidentia.review.models import (
    PRISMAFlowData,
    PaperRecord,
    REVIEW_MODE_PARAMS,
    ReviewConfig,
    ReviewEvent,
    ReviewRunManifest,
)
from evidentia.review.quality import QualityScorer
from evidentia.review.screener import Screener
from evidentia.tools.base import ToolRegistry

logger = get_logger(__name__)


class SystematicReviewEngine:
    """PRISMA-compliant systematic review pipeline."""

    def __init__(
        self,
        llm: BaseLLM,
        tool_registry: ToolRegistry,
        max_results_per_db: int = 100,
    ) -> None:
        self._llm = llm
        self._tools = tool_registry
        self._deduplicator = Deduplicator()
        self._screener = Screener(llm)
        self._quality_scorer = QualityScorer(llm)
        self._contradiction_detector = ContradictionDetector(llm)
        self._max_results = max_results_per_db

    async def stream(
        self, config: ReviewConfig
    ) -> AsyncGenerator[ReviewEvent, None]:
        """Execute the full review pipeline, yielding events."""
        start_time = time.time()

        # Resolve mode parameters
        mode_params = REVIEW_MODE_PARAMS[config.mode]
        screening_passes = mode_params["screening_passes"]
        do_quality = mode_params["quality_scoring"]
        do_contradictions = mode_params["contradiction_detection"]

        # Build reproducibility manifest
        manifest = ReviewRunManifest(
            config=config,
            model_id=getattr(self._llm, "model_id", "unknown"),
            screening_temperature=mode_params["screening_temperature"],
            screening_passes=screening_passes,
            quality_scoring_enabled=do_quality,
            contradiction_detection_enabled=do_contradictions,
        )
        run_hash = manifest.compute_hash()

        yield ReviewEvent(
            type="review_started",
            data={
                "mode": config.mode.value,
                "run_hash": run_hash,
                "screening_passes": screening_passes,
                "quality_scoring": do_quality,
                "contradiction_detection": do_contradictions,
            },
        )

        # ── Phase 1: IDENTIFICATION ──────────────────────────────────
        yield ReviewEvent(
            type="review_phase_started",
            data={"phase": "identification", "databases": config.databases},
        )

        all_papers: list[PaperRecord] = []
        records_per_db: dict[str, int] = {}

        # Search databases in parallel
        tasks = {
            db_name: self._search_database(db_name, config.research_question)
            for db_name in config.databases
            if self._tools.get(db_name) is not None
        }

        for db_name in tasks:
            yield ReviewEvent(
                type="review_database_searching",
                data={"database": db_name},
            )

        results = await asyncio.gather(
            *tasks.values(), return_exceptions=True
        )

        for db_name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning(
                    "review_db_search_failed",
                    database=db_name,
                    error=str(result),
                )
                records_per_db[db_name] = 0
                yield ReviewEvent(
                    type="review_database_complete",
                    data={
                        "database": db_name,
                        "count": 0,
                        "error": str(result),
                    },
                )
            else:
                papers = result
                all_papers.extend(papers)
                records_per_db[db_name] = len(papers)
                yield ReviewEvent(
                    type="review_database_complete",
                    data={"database": db_name, "count": len(papers)},
                )

        total_identified = len(all_papers)
        yield ReviewEvent(
            type="review_identification_complete",
            data={
                "total": total_identified,
                "per_database": records_per_db,
            },
        )

        if total_identified == 0:
            yield ReviewEvent(
                type="review_completed",
                data={
                    "prisma": PRISMAFlowData(
                        databases_searched=config.databases,
                        records_per_database=records_per_db,
                    ).model_dump(),
                    "papers": [],
                    "elapsed_seconds": time.time() - start_time,
                    "run_hash": run_hash,
                },
            )
            return

        # ── Phase 2: DEDUPLICATION ───────────────────────────────────
        yield ReviewEvent(
            type="review_phase_started",
            data={"phase": "deduplication"},
        )

        unique_papers, duplicate_papers = self._deduplicator.deduplicate(
            all_papers
        )

        yield ReviewEvent(
            type="review_deduplication_complete",
            data={
                "unique": len(unique_papers),
                "duplicates": len(duplicate_papers),
                "total": total_identified,
            },
        )

        # ── Phase 3: SCREENING ───────────────────────────────────────
        yield ReviewEvent(
            type="review_phase_started",
            data={
                "phase": "screening",
                "total_papers": len(unique_papers),
                "passes": screening_passes,
            },
        )

        if screening_passes >= 2:
            # Calibrated multi-pass screening
            await self._screener.screen_calibrated(
                unique_papers,
                config.inclusion_criteria,
                config.exclusion_criteria,
                num_passes=screening_passes,
            )
        else:
            # Single-pass screening with inline progress
            batch_size = self._screener.BATCH_SIZE
            total_batches = (len(unique_papers) + batch_size - 1) // batch_size

            for batch_idx in range(0, len(unique_papers), batch_size):
                batch = unique_papers[batch_idx : batch_idx + batch_size]
                decisions = await self._screener._screen_one_batch(
                    batch, config.inclusion_criteria, config.exclusion_criteria
                )

                # Apply decisions to papers
                for decision in decisions:
                    idx = batch_idx + decision.paper_index
                    if 0 <= idx < len(unique_papers):
                        paper = unique_papers[idx]
                        if decision.confidence < 0.7 and decision.decision != "uncertain":
                            paper.screening_decision = "uncertain"
                            paper.exclusion_reason = (
                                f"Low confidence ({decision.confidence:.2f}): {decision.reason}"
                            )
                        else:
                            paper.screening_decision = decision.decision
                            paper.exclusion_reason = (
                                decision.reason if decision.decision == "exclude" else None
                            )
                        paper.screening_confidence = decision.confidence
                        paper.criteria_evaluations = decision.criteria_evaluations or None
                        paper.evidence_spans = decision.evidence_spans or None

                yield ReviewEvent(
                    type="review_screening_progress",
                    data={
                        "screened": min(batch_idx + batch_size, len(unique_papers)),
                        "total": len(unique_papers),
                        "batch": batch_idx // batch_size + 1,
                        "total_batches": total_batches,
                    },
                )

                # Stagger between batches
                if batch_idx + batch_size < len(unique_papers):
                    await asyncio.sleep(0.5)

        # Tally results
        included = [p for p in unique_papers if p.screening_decision == "include"]
        excluded = [p for p in unique_papers if p.screening_decision == "exclude"]
        uncertain = [p for p in unique_papers if p.screening_decision == "uncertain"]

        # Count exclusion reasons
        exclusion_reasons: dict[str, int] = {}
        for p in excluded:
            reason_key = (p.exclusion_reason or "unspecified").split(":")[0].strip()
            exclusion_reasons[reason_key] = exclusion_reasons.get(reason_key, 0) + 1

        # Calibration stats
        calibration_data: dict[str, Any] = {}
        if screening_passes >= 2:
            agreements = [p.screening_agreement for p in unique_papers if p.screening_agreement is not None]
            if agreements:
                calibration_data = {
                    "passes": screening_passes,
                    "mean_agreement": round(sum(agreements) / len(agreements), 3),
                    "full_agreement_count": sum(1 for a in agreements if a >= 1.0),
                    "low_agreement_count": sum(1 for a in agreements if a < 0.67),
                }

        yield ReviewEvent(
            type="review_screening_complete",
            data={
                "included": len(included),
                "excluded": len(excluded),
                "uncertain": len(uncertain),
                "exclusion_reasons": exclusion_reasons,
                "calibration": calibration_data,
            },
        )

        # ── Phase 4: QUALITY SCORING ──────────────────────────────────
        # Score non-excluded papers (included + uncertain)
        papers_to_score = included + uncertain
        quality_scores = []
        contradictions_data = {}

        if papers_to_score and do_quality:
            yield ReviewEvent(
                type="review_phase_started",
                data={"phase": "quality_scoring", "total_papers": len(papers_to_score)},
            )

            try:
                quality_scores = await self._quality_scorer.score_papers(papers_to_score)

                # Attach scores to paper records
                for paper, score in zip(papers_to_score, quality_scores):
                    paper.quality_score = score.overall_score
                    paper.quality_grade = score.grade
                    paper.quality_dimensions = {
                        "study_design": score.study_design.value,
                        "sample_size": score.sample_size,
                        "dimensions": [
                            {"name": d.name, "score": d.score, "rationale": d.rationale}
                            for d in score.dimensions
                        ],
                        "summary": score.summary,
                        "has_control_group": score.has_control_group,
                        "is_preregistered": score.is_preregistered,
                        "has_open_data": score.has_open_data,
                        "funding_bias_risk": score.funding_bias_risk,
                    }

                # Grade distribution
                grade_dist: dict[str, int] = {}
                for s in quality_scores:
                    grade_dist[s.grade] = grade_dist.get(s.grade, 0) + 1

                avg_score = sum(s.overall_score for s in quality_scores) / len(quality_scores)

                yield ReviewEvent(
                    type="review_quality_complete",
                    data={
                        "scored": len(quality_scores),
                        "average_score": round(avg_score, 3),
                        "grade_distribution": grade_dist,
                    },
                )
            except Exception as exc:
                logger.warning("quality_scoring_failed", error=str(exc))
                yield ReviewEvent(
                    type="review_quality_complete",
                    data={"scored": 0, "error": str(exc)},
                )

        # ── Phase 5: CONTRADICTION DETECTION ──────────────────────────
        if len(included) >= 2 and do_contradictions:
            yield ReviewEvent(
                type="review_phase_started",
                data={"phase": "contradiction_detection", "total_papers": len(included)},
            )

            try:
                report = await self._contradiction_detector.detect(included)
                contradictions_data = {
                    "total_contradictions": len(report.contradictions),
                    "contradictions": [c.model_dump() for c in report.contradictions],
                    "consensus_areas": report.consensus_areas,
                    "summary": report.summary,
                    "type_distribution": report.type_distribution,
                }

                yield ReviewEvent(
                    type="review_contradictions_complete",
                    data=contradictions_data,
                )
            except Exception as exc:
                logger.warning("contradiction_detection_failed", error=str(exc))
                contradictions_data = {"total_contradictions": 0, "error": str(exc)}
                yield ReviewEvent(
                    type="review_contradictions_complete",
                    data=contradictions_data,
                )

        # ── Phase 6: REPORTING ────────────────────────────────────────
        prisma = PRISMAFlowData(
            databases_searched=config.databases,
            records_per_database=records_per_db,
            total_identified=total_identified,
            duplicates_removed=len(duplicate_papers),
            records_screened=len(unique_papers),
            excluded_at_screening=len(excluded),
            exclusion_reasons=exclusion_reasons,
            uncertain_count=len(uncertain),
            included_count=len(included),
        )

        elapsed = time.time() - start_time

        yield ReviewEvent(
            type="review_completed",
            data={
                "prisma": prisma.model_dump(),
                "included_count": len(included),
                "excluded_count": len(excluded),
                "uncertain_count": len(uncertain),
                "papers": [p.model_dump() for p in unique_papers + duplicate_papers],
                "quality_scores": [
                    {
                        "overall": s.overall_score,
                        "grade": s.grade,
                        "design": s.study_design.value,
                        "summary": s.summary,
                    }
                    for s in quality_scores
                ],
                "contradictions": contradictions_data,
                "calibration": calibration_data,
                "run_hash": run_hash,
                "mode": config.mode.value,
                "elapsed_seconds": round(elapsed, 2),
            },
        )

    async def _search_database(
        self, tool_name: str, query: str
    ) -> list[PaperRecord]:
        """Search a single database and normalize results to PaperRecord."""
        tool = self._tools.get(tool_name)
        if tool is None:
            return []

        input_data: dict[str, Any] = {
            "query": query,
            "max_results": self._max_results,
        }

        output = await tool.execute_with_timeout(input_data)
        return self._normalize_results(tool_name, output)

    def _normalize_results(
        self, tool_name: str, output: dict[str, Any]
    ) -> list[PaperRecord]:
        """Convert tool-specific output to unified PaperRecord list."""
        papers: list[PaperRecord] = []
        data = output.get("data", [])

        for item in data:
            paper = PaperRecord(
                title=item.get("title") or "",
                authors=item.get("authors") or [],
                abstract=(
                    item.get("abstract")
                    or item.get("snippet")
                    or None
                ),
                doi=item.get("doi") or None,
                url=item.get("url") or item.get("open_access_url") or None,
                published_date=(
                    item.get("published_date")
                    or item.get("published")
                    or (str(item["year"]) if item.get("year") else None)
                ),
                journal=item.get("journal") or None,
                citation_count=(
                    item.get("citation_count")
                    or item.get("cited_by_count")
                    or None
                ),
                source_database=tool_name,
                source_id=(
                    item.get("pmid")
                    or item.get("work_id")
                    or item.get("paper_id")
                    or item.get("arxiv_id")
                    or item.get("doi")
                    or None
                ),
            )
            if paper.title:  # Skip empty results
                papers.append(paper)

        return papers
