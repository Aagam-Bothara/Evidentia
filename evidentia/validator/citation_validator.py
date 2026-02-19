"""Citation Validator — ensures claims have proper citations and evidence spans."""

from __future__ import annotations

from evidentia.core.logging import get_logger
from evidentia.core.models import Claim

logger = get_logger(__name__)


class CitationValidator:
    """Validates that claims have sufficient citations and evidence."""

    def __init__(
        self,
        require_citation: bool = True,
        require_evidence_span: bool = True,
        min_citations_per_claim: int = 1,
    ) -> None:
        self._require_citation = require_citation
        self._require_evidence_span = require_evidence_span
        self._min_citations = min_citations_per_claim

    def validate_claim(self, claim: Claim) -> list[str]:
        """Validate a single claim. Returns list of issues (empty = valid)."""
        issues: list[str] = []

        if self._require_citation and len(claim.citations) < self._min_citations:
            issues.append(
                f"Claim '{claim.statement[:50]}...' has {len(claim.citations)} citations "
                f"(minimum: {self._min_citations})"
            )

        if self._require_evidence_span and not claim.evidence_spans:
            issues.append(f"Claim '{claim.statement[:50]}...' has no evidence spans")

        if claim.conflicting_evidence:
            issues.append(
                f"Claim '{claim.statement[:50]}...' has {len(claim.conflicting_evidence)} "
                f"conflicting evidence spans — flagged for review"
            )

        return issues

    def validate_claims(self, claims: list[Claim]) -> tuple[bool, list[str]]:
        """Validate all claims. Returns (all_valid, list_of_issues)."""
        all_issues: list[str] = []
        for claim in claims:
            all_issues.extend(self.validate_claim(claim))

        passed = len(all_issues) == 0
        if not passed:
            logger.warning("citation_validation_failed", issue_count=len(all_issues))

        return passed, all_issues
