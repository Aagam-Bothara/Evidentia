"""Tests for the Reproducibility Fingerprinting System."""

from __future__ import annotations

from evidentia.core.reproducibility import (
    build_fingerprint,
    compare_runs,
    verify_fingerprint,
)

SAMPLE_CLAIMS = [
    {
        "statement": "Transformers improve protein folding prediction.",
        "confidence": "high",
        "citations": [
            {"source_id": "s1", "title": "AlphaFold 2", "doi": "10.1038/example1"},
        ],
    },
    {
        "statement": "Attention mechanisms capture long-range interactions.",
        "confidence": "medium",
        "citations": [
            {"source_id": "s2", "title": "Attention Is All You Need", "doi": "10.1234/example2"},
        ],
    },
]

QUERY = "What are the latest advances in transformer architectures for protein folding?"


def test_build_fingerprint():
    """build_fingerprint produces a valid RunFingerprint with all hashes."""
    fp = build_fingerprint(run_id="run_001", query=QUERY, claims=SAMPLE_CLAIMS)
    assert fp.run_id == "run_001"
    assert len(fp.query_hash) == 64  # SHA-256 hex
    assert len(fp.evidence_hash) == 64
    assert len(fp.claims_hash) == 64
    assert len(fp.tool_calls_hash) == 64
    assert len(fp.composite_hash) == 64
    assert fp.short_hash == fp.composite_hash[:8]
    assert fp.created_at


def test_build_fingerprint_deterministic():
    """Same inputs produce the same fingerprint hashes."""
    fp1 = build_fingerprint(run_id="a", query=QUERY, claims=SAMPLE_CLAIMS)
    fp2 = build_fingerprint(run_id="b", query=QUERY, claims=SAMPLE_CLAIMS)
    # Same query/claims → same query/evidence/claims hashes
    assert fp1.query_hash == fp2.query_hash
    assert fp1.evidence_hash == fp2.evidence_hash
    assert fp1.claims_hash == fp2.claims_hash


def test_verify_fingerprint_pass():
    """verify_fingerprint passes when data matches the original fingerprint."""
    fp = build_fingerprint(run_id="run_v", query=QUERY, claims=SAMPLE_CLAIMS)
    result = verify_fingerprint(fp, query=QUERY, claims=SAMPLE_CLAIMS)
    assert result.passed is True
    assert result.run_id == "run_v"
    assert len(result.mismatches) == 0
    assert result.expected_composite == result.actual_composite


def test_verify_fingerprint_mismatch():
    """verify_fingerprint fails when claims change."""
    fp = build_fingerprint(run_id="run_m", query=QUERY, claims=SAMPLE_CLAIMS)
    modified_claims = [
        {"statement": "Completely different claim.", "confidence": "low", "citations": []},
    ]
    result = verify_fingerprint(fp, query=QUERY, claims=modified_claims)
    assert result.passed is False
    assert "claims_hash" in result.mismatches


def test_compare_runs():
    """compare_runs identifies matching and diverging hashes between two runs."""
    fp1 = build_fingerprint(run_id="r1", query=QUERY, claims=SAMPLE_CLAIMS)
    different_claims = [
        {
            "statement": "Different conclusion about transformers.",
            "confidence": "high",
            "citations": [
                {"source_id": "s3", "title": "New Paper", "doi": "10.5678/new"},
            ],
        },
    ]
    fp2 = build_fingerprint(run_id="r2", query=QUERY, claims=different_claims)
    result = compare_runs(fp1, fp2, claims_a=SAMPLE_CLAIMS, claims_b=different_claims)
    assert result.same_query is True
    assert result.same_claims is False
    assert result.composite_match is False
    assert result.run_id_a == "r1"
    assert result.run_id_b == "r2"
