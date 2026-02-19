"""Tests for the validation layer."""

from evidentia.core.models import Citation, Claim, EvidenceSpan
from evidentia.validator.citation_validator import CitationValidator


def test_valid_claim_passes():
    validator = CitationValidator()
    claim = Claim(
        statement="Test claim with evidence.",
        citations=[Citation(source_id="s1", title="Source")],
        evidence_spans=[EvidenceSpan(source_id="s1", text="evidence text")],
    )
    issues = validator.validate_claim(claim)
    assert issues == []


def test_missing_citation_fails():
    validator = CitationValidator(require_citation=True)
    claim = Claim(
        statement="Claim without citation.",
        citations=[],
        evidence_spans=[EvidenceSpan(source_id="s1", text="evidence")],
    )
    issues = validator.validate_claim(claim)
    assert len(issues) == 1
    assert "citations" in issues[0].lower()


def test_missing_evidence_span_fails():
    validator = CitationValidator(require_evidence_span=True)
    claim = Claim(
        statement="Claim without evidence span.",
        citations=[Citation(source_id="s1", title="Source")],
        evidence_spans=[],
    )
    issues = validator.validate_claim(claim)
    assert len(issues) == 1
    assert "evidence" in issues[0].lower()


def test_conflicting_evidence_flagged():
    validator = CitationValidator()
    claim = Claim(
        statement="Controversial claim.",
        citations=[Citation(source_id="s1", title="Source")],
        evidence_spans=[EvidenceSpan(source_id="s1", text="supports")],
        conflicting_evidence=[EvidenceSpan(source_id="s2", text="contradicts")],
    )
    issues = validator.validate_claim(claim)
    assert len(issues) == 1
    assert "conflicting" in issues[0].lower()


def test_validate_multiple_claims():
    validator = CitationValidator()
    claims = [
        Claim(
            statement="Good claim.",
            citations=[Citation(source_id="s1", title="Source")],
            evidence_spans=[EvidenceSpan(source_id="s1", text="evidence")],
        ),
        Claim(
            statement="Bad claim — no citation.",
            citations=[],
            evidence_spans=[],
        ),
    ]
    passed, issues = validator.validate_claims(claims)
    assert not passed
    assert len(issues) >= 1
