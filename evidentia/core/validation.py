"""Validation pipeline — compare Evidentia results against gold-standard reviews."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from evidentia.core.logging import get_logger

logger = get_logger(__name__)


# ── Data models ──────────────────────────────────────────────────────


@dataclass
class GoldPaper:
    """A paper in the gold standard with known include/exclude decision."""

    title: str
    doi: str | None = None
    decision: str = "include"  # "include" or "exclude"
    reason: str | None = None


@dataclass
class GoldStandardReview:
    """A known published systematic review to validate against."""

    title: str
    research_question: str
    included_papers: list[GoldPaper]  # papers that should be included
    excluded_papers: list[GoldPaper]  # papers that should be excluded
    total_identified: int
    total_screened: int
    total_included: int
    source: str  # "cochrane", "manual", etc.
    doi: str | None = None


@dataclass
class ValidationResult:
    """Result of comparing Evidentia output against a gold standard."""

    gold_standard_title: str
    evidentia_review_id: str | None

    # Confusion matrix
    true_positives: int = 0  # correctly included
    false_positives: int = 0  # included but shouldn't be
    true_negatives: int = 0  # correctly excluded
    false_negatives: int = 0  # excluded but should be included

    # Metrics
    sensitivity: float = 0.0  # TP / (TP + FN) — recall for inclusion
    specificity: float = 0.0  # TN / (TN + FP)
    precision: float = 0.0  # TP / (TP + FP)
    f1_score: float = 0.0
    accuracy: float = 0.0

    # Paper-level details
    matched_papers: list[dict[str, Any]] = field(default_factory=list)
    missed_papers: list[dict[str, Any]] = field(default_factory=list)  # should be included, were excluded
    extra_papers: list[dict[str, Any]] = field(default_factory=list)  # were included, shouldn't be

    # PRISMA flow comparison
    prisma_comparison: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gold_standard_title": self.gold_standard_title,
            "evidentia_review_id": self.evidentia_review_id,
            "confusion_matrix": {
                "true_positives": self.true_positives,
                "false_positives": self.false_positives,
                "true_negatives": self.true_negatives,
                "false_negatives": self.false_negatives,
            },
            "metrics": {
                "sensitivity": round(self.sensitivity, 4),
                "specificity": round(self.specificity, 4),
                "precision": round(self.precision, 4),
                "f1_score": round(self.f1_score, 4),
                "accuracy": round(self.accuracy, 4),
            },
            "matched_papers": self.matched_papers,
            "missed_papers": self.missed_papers,
            "extra_papers": self.extra_papers,
            "prisma_comparison": self.prisma_comparison,
        }


# ── Validation engine ────────────────────────────────────────────────


class ValidationEngine:
    """Compare Evidentia systematic review results against gold standards."""

    # Thresholds for matching
    JACCARD_THRESHOLD = 0.8
    LCS_RATIO_THRESHOLD = 0.85

    def validate_review(
        self,
        gold: GoldStandardReview,
        evidentia_papers: list[dict[str, Any]],
        evidentia_prisma: dict[str, Any] | None = None,
        review_id: str | None = None,
    ) -> ValidationResult:
        """Compare a set of Evidentia papers against a gold-standard review.

        Matching strategy:
        1. Exact DOI match (case-insensitive)
        2. Title similarity (normalized Jaccard similarity > 0.8)
        3. Fuzzy title match (longest common subsequence ratio > 0.85)

        Args:
            gold: The gold-standard review to compare against.
            evidentia_papers: List of dicts with keys: title, doi, screening_decision.
            evidentia_prisma: Optional PRISMA flow data from Evidentia.
            review_id: Optional Evidentia review ID.
        """
        result = ValidationResult(
            gold_standard_title=gold.title,
            evidentia_review_id=review_id,
        )

        # Build a mutable copy of Evidentia papers for tracking which ones get matched
        remaining_evidentia = list(evidentia_papers)

        # Track which Evidentia papers were matched to any gold paper
        matched_evidentia_indices: set[int] = set()

        # ── Process gold-standard included papers ──────────────────
        for gold_paper in gold.included_papers:
            match = self._match_paper(gold_paper, remaining_evidentia)
            if match is not None:
                ev_paper = match["evidentia_paper"]
                ev_decision = (ev_paper.get("screening_decision") or "").lower()

                if ev_decision == "include":
                    # True positive: gold says include, Evidentia says include
                    result.true_positives += 1
                    result.matched_papers.append(
                        {
                            "gold_title": gold_paper.title,
                            "gold_doi": gold_paper.doi,
                            "evidentia_title": ev_paper.get("title", ""),
                            "evidentia_doi": ev_paper.get("doi"),
                            "match_method": match["method"],
                            "match_score": match["score"],
                            "status": "true_positive",
                        }
                    )
                else:
                    # False negative: gold says include, Evidentia excluded/missed
                    result.false_negatives += 1
                    result.missed_papers.append(
                        {
                            "gold_title": gold_paper.title,
                            "gold_doi": gold_paper.doi,
                            "evidentia_title": ev_paper.get("title", ""),
                            "evidentia_decision": ev_decision,
                            "match_method": match["method"],
                            "match_score": match["score"],
                            "status": "false_negative",
                        }
                    )

                # Track the matched Evidentia paper index
                for idx, ep in enumerate(remaining_evidentia):
                    if ep is ev_paper:
                        matched_evidentia_indices.add(idx)
                        break
            else:
                # Gold paper not found at all in Evidentia results — false negative
                result.false_negatives += 1
                result.missed_papers.append(
                    {
                        "gold_title": gold_paper.title,
                        "gold_doi": gold_paper.doi,
                        "evidentia_title": None,
                        "evidentia_decision": None,
                        "match_method": None,
                        "match_score": 0.0,
                        "status": "false_negative_not_found",
                    }
                )

        # ── Process gold-standard excluded papers ──────────────────
        for gold_paper in gold.excluded_papers:
            match = self._match_paper(gold_paper, remaining_evidentia)
            if match is not None:
                ev_paper = match["evidentia_paper"]
                ev_decision = (ev_paper.get("screening_decision") or "").lower()

                if ev_decision == "exclude":
                    # True negative: gold says exclude, Evidentia says exclude
                    result.true_negatives += 1
                else:
                    # False positive: gold says exclude, Evidentia says include
                    result.false_positives += 1
                    result.extra_papers.append(
                        {
                            "gold_title": gold_paper.title,
                            "gold_doi": gold_paper.doi,
                            "gold_reason": gold_paper.reason,
                            "evidentia_title": ev_paper.get("title", ""),
                            "evidentia_decision": ev_decision,
                            "match_method": match["method"],
                            "match_score": match["score"],
                            "status": "false_positive",
                        }
                    )

                for idx, ep in enumerate(remaining_evidentia):
                    if ep is ev_paper:
                        matched_evidentia_indices.add(idx)
                        break
            else:
                # Gold excluded paper not found in Evidentia — Evidentia correctly
                # did not find it, count as true negative
                result.true_negatives += 1

        # ── Unmatched Evidentia "include" papers — potential false positives ──
        for idx, ep in enumerate(remaining_evidentia):
            if idx in matched_evidentia_indices:
                continue
            ev_decision = (ep.get("screening_decision") or "").lower()
            if ev_decision == "include":
                result.false_positives += 1
                result.extra_papers.append(
                    {
                        "gold_title": None,
                        "gold_doi": None,
                        "gold_reason": None,
                        "evidentia_title": ep.get("title", ""),
                        "evidentia_decision": ev_decision,
                        "match_method": None,
                        "match_score": 0.0,
                        "status": "false_positive_no_gold_match",
                    }
                )

        # ── Calculate metrics ──────────────────────────────────────
        tp = result.true_positives
        fp = result.false_positives
        tn = result.true_negatives
        fn = result.false_negatives

        result.sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        result.specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        result.precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        result.f1_score = (
            (2 * result.precision * result.sensitivity) / (result.precision + result.sensitivity)
            if (result.precision + result.sensitivity) > 0
            else 0.0
        )
        result.accuracy = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) > 0 else 0.0

        # ── Compare PRISMA flows if available ──────────────────────
        if evidentia_prisma:
            result.prisma_comparison = {
                "gold": {
                    "total_identified": gold.total_identified,
                    "total_screened": gold.total_screened,
                    "total_included": gold.total_included,
                },
                "evidentia": {
                    "total_identified": evidentia_prisma.get("total_identified", 0),
                    "total_screened": evidentia_prisma.get("records_screened", 0),
                    "total_included": evidentia_prisma.get("included_count", 0),
                },
                "differences": {
                    "identified_diff": (evidentia_prisma.get("total_identified", 0) - gold.total_identified),
                    "screened_diff": (evidentia_prisma.get("records_screened", 0) - gold.total_screened),
                    "included_diff": (evidentia_prisma.get("included_count", 0) - gold.total_included),
                },
            }

        logger.info(
            "validation_complete",
            gold_title=gold.title,
            tp=tp,
            fp=fp,
            tn=tn,
            fn=fn,
            sensitivity=round(result.sensitivity, 4),
            precision=round(result.precision, 4),
            f1=round(result.f1_score, 4),
        )

        return result

    def _match_paper(
        self,
        gold_paper: GoldPaper,
        evidentia_papers: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Try to find a matching Evidentia paper for a gold standard paper.

        Returns a dict with keys: evidentia_paper, method, score — or None.
        """
        # 1. Try DOI match (highest confidence)
        if gold_paper.doi:
            gold_doi = gold_paper.doi.lower().strip()
            for ep in evidentia_papers:
                ep_doi = (ep.get("doi") or "").lower().strip()
                if ep_doi and ep_doi == gold_doi:
                    return {"evidentia_paper": ep, "method": "doi", "score": 1.0}

        # 2. Try normalized title match (Jaccard similarity)
        gold_words = self._normalize_title(gold_paper.title)
        best_jaccard: float = 0.0
        best_jaccard_paper: dict[str, Any] | None = None

        for ep in evidentia_papers:
            ep_title = ep.get("title", "")
            if not ep_title:
                continue
            ep_words = self._normalize_title(ep_title)
            sim = self._jaccard_similarity(gold_words, ep_words)
            if sim > best_jaccard:
                best_jaccard = sim
                best_jaccard_paper = ep

        if best_jaccard >= self.JACCARD_THRESHOLD and best_jaccard_paper is not None:
            return {
                "evidentia_paper": best_jaccard_paper,
                "method": "jaccard",
                "score": best_jaccard,
            }

        # 3. Try fuzzy title match (LCS ratio)
        gold_lower = gold_paper.title.lower().strip()
        best_lcs: float = 0.0
        best_lcs_paper: dict[str, Any] | None = None

        for ep in evidentia_papers:
            ep_title = ep.get("title", "")
            if not ep_title:
                continue
            ratio = self._lcs_ratio(gold_lower, ep_title.lower().strip())
            if ratio > best_lcs:
                best_lcs = ratio
                best_lcs_paper = ep

        if best_lcs >= self.LCS_RATIO_THRESHOLD and best_lcs_paper is not None:
            return {
                "evidentia_paper": best_lcs_paper,
                "method": "lcs",
                "score": best_lcs,
            }

        return None

    @staticmethod
    def _normalize_title(title: str) -> set[str]:
        """Normalize a title to a set of lowercase words for Jaccard similarity."""
        words = re.findall(r"\w+", title.lower())
        stop_words = {
            "the",
            "a",
            "an",
            "of",
            "in",
            "for",
            "and",
            "or",
            "to",
            "is",
            "on",
            "at",
            "by",
            "with",
        }
        return {w for w in words if w not in stop_words}

    @staticmethod
    def _jaccard_similarity(set1: set[str], set2: set[str]) -> float:
        """Compute Jaccard similarity between two sets."""
        if not set1 or not set2:
            return 0.0
        intersection = set1 & set2
        union = set1 | set2
        return len(intersection) / len(union)

    @staticmethod
    def _lcs_ratio(s1: str, s2: str) -> float:
        """Compute longest common subsequence ratio.

        Returns 2 * LCS_length / (len(s1) + len(s2)), giving a value in [0, 1].
        """
        m, n = len(s1), len(s2)
        if m == 0 or n == 0:
            return 0.0

        # Space-optimized LCS
        prev = [0] * (n + 1)
        curr = [0] * (n + 1)
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i - 1] == s2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(prev[j], curr[j - 1])
            prev, curr = curr, [0] * (n + 1)

        lcs_len = prev[n]
        return (2 * lcs_len) / (m + n)


# ── Built-in gold standards ──────────────────────────────────────────


def get_sample_gold_standard() -> GoldStandardReview:
    """Return a sample gold standard for testing/demo.

    Based on a well-known Cochrane review topic:
    "Vitamin D supplementation for prevention of mortality in adults"
    (Bjelakovic et al., Cochrane Database Syst Rev, 2014)
    """
    return GoldStandardReview(
        title="Vitamin D supplementation for prevention of mortality in adults",
        research_question="Does vitamin D supplementation reduce mortality in adults?",
        doi="10.1002/14651858.CD007470.pub3",
        source="cochrane",
        total_identified=1772,
        total_screened=624,
        total_included=56,
        included_papers=[
            GoldPaper(
                title="Effect of vitamin D3 on overall mortality",
                doi="10.1001/jama.2012.1515",
            ),
            GoldPaper(
                title="Vitamin D and calcium supplementation reduces cancer risk",
                doi="10.3945/ajcn.2007.25592",
            ),
            GoldPaper(
                title="Annual high-dose oral vitamin D and falls among older women",
                doi="10.1001/archinte.168.1.103",
            ),
            GoldPaper(
                title="Vitamin D3 supplementation and upper respiratory tract infections",
                doi="10.1136/bmj.e6583",
            ),
            GoldPaper(
                title="Effects of vitamin D supplementation on bone density",
                doi="10.1016/S0140-6736(13)61647-5",
            ),
            GoldPaper(
                title="Mortality reduction with combined vitamin D3 and calcium",
                doi=None,
            ),
            GoldPaper(
                title="Randomized trial of vitamin D supplementation in chronic heart failure",
                doi=None,
            ),
            GoldPaper(
                title="Vitamin D supplementation in elderly adults: effect on mortality",
                doi=None,
            ),
        ],
        excluded_papers=[
            GoldPaper(
                title="Vitamin D and rickets in children",
                doi=None,
                decision="exclude",
                reason="Population not adults",
            ),
            GoldPaper(
                title="Vitamin D levels in pregnancy",
                doi=None,
                decision="exclude",
                reason="Population: pregnant women",
            ),
            GoldPaper(
                title="Observational study of vitamin D and mortality",
                doi=None,
                decision="exclude",
                reason="Not RCT",
            ),
        ],
    )


def create_gold_from_bibtex(
    title: str,
    research_question: str,
    included_bibtex: str,
    excluded_bibtex: str | None = None,
) -> GoldStandardReview:
    """Create a gold standard from BibTeX strings of included/excluded papers.

    Uses the bibliography parser to parse the BibTeX.
    """
    from evidentia.core.bibliography import parse_bibtex

    included_parsed = parse_bibtex(included_bibtex)
    included = [GoldPaper(title=p.title, doi=p.doi, decision="include") for p in included_parsed]

    excluded: list[GoldPaper] = []
    if excluded_bibtex:
        excluded_parsed = parse_bibtex(excluded_bibtex)
        excluded = [GoldPaper(title=p.title, doi=p.doi, decision="exclude") for p in excluded_parsed]

    return GoldStandardReview(
        title=title,
        research_question=research_question,
        included_papers=included,
        excluded_papers=excluded,
        total_identified=len(included) + len(excluded),
        total_screened=len(included) + len(excluded),
        total_included=len(included),
        source="manual",
    )
