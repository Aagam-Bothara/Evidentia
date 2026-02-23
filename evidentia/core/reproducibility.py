"""Reproducible Research Runs — cryptographic fingerprinting for verifiable evidence trails.

Every research run produces a RunFingerprint that captures:
- The original query (hashed)
- All evidence sources (sorted and hashed)
- All claims (sorted and hashed)
- The full tool call sequence (ordered and hashed)
- A composite hash of all the above

Two runs of the same query that produce the same evidence will have
identical composite hashes, enabling reproducibility verification.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ── Data classes ─────────────────────────────────────────────────────


@dataclass
class ToolCallRecord:
    """Record of a single tool invocation for audit trail."""

    tool_name: str
    input_params: dict[str, Any]
    output_hash: str  # SHA-256 of the tool's response
    timestamp: str
    cached: bool  # was this from cache?
    source_count: int  # how many sources returned

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "input_params": self.input_params,
            "output_hash": self.output_hash,
            "timestamp": self.timestamp,
            "cached": self.cached,
            "source_count": self.source_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolCallRecord:
        return cls(
            tool_name=data.get("tool_name", ""),
            input_params=data.get("input_params", {}),
            output_hash=data.get("output_hash", ""),
            timestamp=data.get("timestamp", ""),
            cached=data.get("cached", False),
            source_count=data.get("source_count", 0),
        )


@dataclass
class RunFingerprint:
    """Cryptographic fingerprint of a research run for reproducibility."""

    run_id: str
    query_hash: str  # SHA-256 of the original query
    evidence_hash: str  # SHA-256 of sorted evidence sources
    claims_hash: str  # SHA-256 of claim statements
    tool_calls_hash: str  # SHA-256 of tool call sequence + results
    composite_hash: str  # SHA-256 of all above combined
    created_at: str
    tool_call_log: list[ToolCallRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "query_hash": self.query_hash,
            "evidence_hash": self.evidence_hash,
            "claims_hash": self.claims_hash,
            "tool_calls_hash": self.tool_calls_hash,
            "composite_hash": self.composite_hash,
            "created_at": self.created_at,
            "tool_call_log": [tc.to_dict() for tc in self.tool_call_log],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunFingerprint:
        log = [ToolCallRecord.from_dict(tc) for tc in data.get("tool_call_log", [])]
        return cls(
            run_id=data.get("run_id", ""),
            query_hash=data.get("query_hash", ""),
            evidence_hash=data.get("evidence_hash", ""),
            claims_hash=data.get("claims_hash", ""),
            tool_calls_hash=data.get("tool_calls_hash", ""),
            composite_hash=data.get("composite_hash", ""),
            created_at=data.get("created_at", ""),
            tool_call_log=log,
        )

    @property
    def short_hash(self) -> str:
        """First 8 characters of the composite hash."""
        return self.composite_hash[:8]


@dataclass
class VerificationResult:
    """Result of verifying a fingerprint against stored data."""

    passed: bool
    run_id: str
    expected_composite: str
    actual_composite: str
    mismatches: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "run_id": self.run_id,
            "expected_composite": self.expected_composite,
            "actual_composite": self.actual_composite,
            "mismatches": self.mismatches,
            "details": self.details,
        }


@dataclass
class ComparisonResult:
    """Result of comparing two run fingerprints."""

    run_id_a: str
    run_id_b: str
    same_query: bool
    same_evidence: bool
    same_claims: bool
    same_tool_calls: bool
    composite_match: bool
    overlapping_evidence: list[str] = field(default_factory=list)
    unique_to_a: list[str] = field(default_factory=list)
    unique_to_b: list[str] = field(default_factory=list)
    claims_in_both: list[str] = field(default_factory=list)
    claims_only_a: list[str] = field(default_factory=list)
    claims_only_b: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id_a": self.run_id_a,
            "run_id_b": self.run_id_b,
            "same_query": self.same_query,
            "same_evidence": self.same_evidence,
            "same_claims": self.same_claims,
            "same_tool_calls": self.same_tool_calls,
            "composite_match": self.composite_match,
            "overlapping_evidence": self.overlapping_evidence,
            "unique_to_a": self.unique_to_a,
            "unique_to_b": self.unique_to_b,
            "claims_in_both": self.claims_in_both,
            "claims_only_a": self.claims_only_a,
            "claims_only_b": self.claims_only_b,
        }


# ── Hashing utilities ───────────────────────────────────────────────


def _sha256(data: str) -> str:
    """Compute SHA-256 hex digest of a string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _hash_json(obj: Any) -> str:
    """Deterministically hash a JSON-serializable object.

    Sort keys and list items to ensure identical inputs produce
    identical hashes regardless of insertion order.
    """
    payload = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=True)
    return _sha256(payload)


def _normalize_evidence_key(citation: dict[str, Any]) -> str:
    """Build a canonical key for deduplication/sorting of evidence sources.

    Prefer DOI > URL > source_id > title as the canonical identifier.
    """
    doi = (citation.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    url = (citation.get("url") or "").strip().lower()
    if url:
        return f"url:{url}"
    source_id = (citation.get("source_id") or "").strip()
    if source_id:
        return f"id:{source_id}"
    title = (citation.get("title") or "").strip().lower()
    return f"title:{title}"


# ── Engine ──────────────────────────────────────────────────────────


class ReproducibilityEngine:
    """Build and verify reproducibility fingerprints for research runs."""

    # ── Build ────────────────────────────────────────────────────────

    def build_fingerprint(
        self,
        run_id: str,
        query: str,
        claims: list[dict[str, Any]],
        tool_calls: list[ToolCallRecord] | None = None,
    ) -> RunFingerprint:
        """Build a fingerprint after a run completes.

        Args:
            run_id: Unique identifier for the run.
            query: The original research query string.
            claims: List of claim dicts (each with 'statement', 'citations', etc.).
            tool_calls: Ordered list of tool call records.

        Returns:
            A RunFingerprint with all sub-hashes and the composite hash.
        """
        if tool_calls is None:
            tool_calls = []

        query_hash = _sha256(query.strip())
        evidence_hash = self._hash_evidence(claims)
        claims_hash = self._hash_claims(claims)
        tool_calls_hash = self._hash_tool_calls(tool_calls)

        # Composite: hash of all sub-hashes combined
        composite_payload = "|".join(
            [
                query_hash,
                evidence_hash,
                claims_hash,
                tool_calls_hash,
            ]
        )
        composite_hash = _sha256(composite_payload)

        return RunFingerprint(
            run_id=run_id,
            query_hash=query_hash,
            evidence_hash=evidence_hash,
            claims_hash=claims_hash,
            tool_calls_hash=tool_calls_hash,
            composite_hash=composite_hash,
            created_at=datetime.now(UTC).isoformat(),
            tool_call_log=tool_calls,
        )

    # ── Verify ───────────────────────────────────────────────────────

    def verify_fingerprint(
        self,
        fingerprint: RunFingerprint,
        query: str,
        claims: list[dict[str, Any]],
        tool_calls: list[ToolCallRecord] | None = None,
    ) -> VerificationResult:
        """Re-verify a fingerprint against stored data.

        Recomputes all hashes from the stored data and compares
        them against the fingerprint. Returns pass/fail with details.
        """
        if tool_calls is None:
            tool_calls = []

        rebuilt = self.build_fingerprint(
            run_id=fingerprint.run_id,
            query=query,
            claims=claims,
            tool_calls=tool_calls,
        )

        mismatches: list[str] = []
        details: dict[str, Any] = {}

        hash_pairs = [
            ("query_hash", fingerprint.query_hash, rebuilt.query_hash),
            ("evidence_hash", fingerprint.evidence_hash, rebuilt.evidence_hash),
            ("claims_hash", fingerprint.claims_hash, rebuilt.claims_hash),
            ("tool_calls_hash", fingerprint.tool_calls_hash, rebuilt.tool_calls_hash),
            ("composite_hash", fingerprint.composite_hash, rebuilt.composite_hash),
        ]

        for name, expected, actual in hash_pairs:
            details[name] = {
                "expected": expected,
                "actual": actual,
                "match": expected == actual,
            }
            if expected != actual:
                mismatches.append(name)

        return VerificationResult(
            passed=len(mismatches) == 0,
            run_id=fingerprint.run_id,
            expected_composite=fingerprint.composite_hash,
            actual_composite=rebuilt.composite_hash,
            mismatches=mismatches,
            details=details,
        )

    # ── Compare ──────────────────────────────────────────────────────

    def compare_runs(
        self,
        fp1: RunFingerprint,
        fp2: RunFingerprint,
        claims_a: list[dict[str, Any]] | None = None,
        claims_b: list[dict[str, Any]] | None = None,
    ) -> ComparisonResult:
        """Compare two run fingerprints.

        Shows what evidence overlaps, what differs, and which claims changed.
        If claims_a/claims_b are provided, performs detailed claim-level diff.
        """
        # Evidence source comparison
        evidence_a = self._extract_evidence_keys(claims_a or [])
        evidence_b = self._extract_evidence_keys(claims_b or [])
        overlapping = sorted(evidence_a & evidence_b)
        unique_a = sorted(evidence_a - evidence_b)
        unique_b = sorted(evidence_b - evidence_a)

        # Claims comparison
        stmts_a = {(c.get("statement") or "").strip() for c in (claims_a or [])}
        stmts_b = {(c.get("statement") or "").strip() for c in (claims_b or [])}
        in_both = sorted(stmts_a & stmts_b)
        only_a = sorted(stmts_a - stmts_b)
        only_b = sorted(stmts_b - stmts_a)

        return ComparisonResult(
            run_id_a=fp1.run_id,
            run_id_b=fp2.run_id,
            same_query=fp1.query_hash == fp2.query_hash,
            same_evidence=fp1.evidence_hash == fp2.evidence_hash,
            same_claims=fp1.claims_hash == fp2.claims_hash,
            same_tool_calls=fp1.tool_calls_hash == fp2.tool_calls_hash,
            composite_match=fp1.composite_hash == fp2.composite_hash,
            overlapping_evidence=overlapping,
            unique_to_a=unique_a,
            unique_to_b=unique_b,
            claims_in_both=in_both,
            claims_only_a=only_a,
            claims_only_b=only_b,
        )

    # ── Internal hashing helpers ─────────────────────────────────────

    def _hash_evidence(self, claims: list[dict[str, Any]]) -> str:
        """Hash all evidence sources across all claims, sorted deterministically."""
        all_sources: list[str] = []
        for claim in claims:
            for cit in claim.get("citations", []):
                key = _normalize_evidence_key(cit)
                all_sources.append(key)
        # Sort and deduplicate for determinism
        unique_sorted = sorted(set(all_sources))
        return _hash_json(unique_sorted)

    def _hash_claims(self, claims: list[dict[str, Any]]) -> str:
        """Hash all claim statements, sorted alphabetically."""
        statements = sorted((c.get("statement") or "").strip() for c in claims)
        return _hash_json(statements)

    def _hash_tool_calls(self, tool_calls: list[ToolCallRecord]) -> str:
        """Hash the tool call sequence (order-preserving)."""
        if not tool_calls:
            return _sha256("[]")
        records = [
            {
                "tool_name": tc.tool_name,
                "input_params": tc.input_params,
                "output_hash": tc.output_hash,
            }
            for tc in tool_calls
        ]
        return _hash_json(records)

    def _extract_evidence_keys(self, claims: list[dict[str, Any]]) -> set[str]:
        """Extract canonical evidence keys from claims for comparison."""
        keys: set[str] = set()
        for claim in claims:
            for cit in claim.get("citations", []):
                keys.add(_normalize_evidence_key(cit))
        return keys


# ── Module-level convenience instance ───────────────────────────────

_engine = ReproducibilityEngine()


def build_fingerprint(
    run_id: str,
    query: str,
    claims: list[dict[str, Any]],
    tool_calls: list[ToolCallRecord] | None = None,
) -> RunFingerprint:
    """Module-level convenience: build a fingerprint."""
    return _engine.build_fingerprint(run_id, query, claims, tool_calls)


def verify_fingerprint(
    fingerprint: RunFingerprint,
    query: str,
    claims: list[dict[str, Any]],
    tool_calls: list[ToolCallRecord] | None = None,
) -> VerificationResult:
    """Module-level convenience: verify a fingerprint."""
    return _engine.verify_fingerprint(fingerprint, query, claims, tool_calls)


def compare_runs(
    fp1: RunFingerprint,
    fp2: RunFingerprint,
    claims_a: list[dict[str, Any]] | None = None,
    claims_b: list[dict[str, Any]] | None = None,
) -> ComparisonResult:
    """Module-level convenience: compare two fingerprints."""
    return _engine.compare_runs(fp1, fp2, claims_a, claims_b)
