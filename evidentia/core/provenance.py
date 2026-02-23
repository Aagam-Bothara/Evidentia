"""Provenance Chain — every claim must trace back to a real paper with a real DOI and a real quote.

No hallucinated citations, ever.

The provenance chain walks each claim's citations, matches them to retrieved
evidence fragments, and flags any citation that cannot be traced to a real source.
DOI verification is async and non-blocking.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

from evidentia.core.logging import get_logger
from evidentia.core.models import Citation, Claim, EvidenceSpan, new_id

logger = get_logger(__name__)


# ── Provenance Models ────────────────────────────────────────────────


class ProvenanceLink(BaseModel):
    """One link in the evidence chain: Claim -> Citation -> Evidence Quote -> Source Paper."""

    claim_id: str
    claim_text: str
    citation: Citation
    evidence_span: EvidenceSpan | None = None
    retrieval_tool: str = "unknown"
    retrieval_timestamp: str = ""
    verification_status: str = "unverified"  # "verified" | "unverified" | "broken"
    doi_verified: bool = False


class ProvenanceReport(BaseModel):
    """Summary report after verification."""

    total_links: int = 0
    verified_count: int = 0
    unverified_count: int = 0
    broken_count: int = 0
    coverage_score: float = 0.0
    ungrounded_claims: list[str] = Field(default_factory=list)
    verification_timestamp: str = ""


class ProvenanceChain(BaseModel):
    """Full provenance chain for a research run."""

    run_id: str = Field(default_factory=new_id)
    query: str = ""
    links: list[ProvenanceLink] = Field(default_factory=list)
    ungrounded_claims: list[str] = Field(default_factory=list)
    coverage_score: float = 0.0

    def verify(self) -> ProvenanceReport:
        """Generate a provenance report from the current chain state."""
        verified = sum(1 for link in self.links if link.verification_status == "verified")
        unverified = sum(1 for link in self.links if link.verification_status == "unverified")
        broken = sum(1 for link in self.links if link.verification_status == "broken")
        total = len(self.links)

        return ProvenanceReport(
            total_links=total,
            verified_count=verified,
            unverified_count=unverified,
            broken_count=broken,
            coverage_score=self.coverage_score,
            ungrounded_claims=list(self.ungrounded_claims),
            verification_timestamp=datetime.now(UTC).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire provenance chain for API responses."""
        return {
            "run_id": self.run_id,
            "query": self.query,
            "links": [link.model_dump() for link in self.links],
            "ungrounded_claims": self.ungrounded_claims,
            "coverage_score": self.coverage_score,
            "report": self.verify().model_dump(),
        }


# ── DOI Verification ─────────────────────────────────────────────────


async def verify_doi(doi: str, timeout: float = 5.0) -> bool:
    """Quick check if a DOI resolves via doi.org HEAD request.

    Non-blocking — uses httpx async client with a short timeout.
    Returns True if the DOI resolves (HTTP 2xx or 3xx redirect), False otherwise.
    """
    if not doi:
        return False

    # Normalize DOI
    doi = doi.strip()
    if doi.startswith("http"):
        # Already a URL — extract the DOI part
        if "doi.org/" in doi:
            doi = doi.split("doi.org/", 1)[1]
        else:
            return False

    url = f"https://doi.org/{doi}"

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            resp = await client.head(url)
            # doi.org returns 302 redirect to the publisher for valid DOIs
            return resp.status_code in (200, 301, 302, 303, 307, 308)
    except Exception as exc:
        logger.debug("doi_verification_failed", doi=doi, error=str(exc))
        return False


async def verify_dois_batch(dois: list[str], timeout: float = 5.0) -> dict[str, bool]:
    """Verify multiple DOIs concurrently. Returns a mapping of DOI -> verified."""
    if not dois:
        return {}

    tasks = {doi: verify_doi(doi, timeout) for doi in dois if doi}
    results: dict[str, bool] = {}

    gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for doi, result in zip(tasks.keys(), gathered, strict=False):
        if isinstance(result, Exception):
            results[doi] = False
        else:
            results[doi] = result

    return results


# ── Evidence Fragment Matching ────────────────────────────────────────


def _match_evidence_to_citation(
    citation: Citation,
    evidence_spans: list[EvidenceSpan],
) -> EvidenceSpan | None:
    """Find the best matching evidence span for a citation.

    Matches by source_id. Returns the first matching span or None.
    """
    for span in evidence_spans:
        if span.source_id == citation.source_id:
            return span
    return None


def _infer_retrieval_tool(citation: Citation, evidence_fragments: list[dict[str, Any]]) -> str:
    """Infer which retrieval tool found this citation by matching against evidence fragments."""
    for frag in evidence_fragments:
        frag_doi = frag.get("doi", "")
        frag_title = frag.get("title", "")
        frag_url = frag.get("url", "")

        # Match by DOI
        if citation.doi and frag_doi and citation.doi.strip().lower() == frag_doi.strip().lower():
            return frag.get("source_tool", "unknown")

        # Match by title (case-insensitive)
        if citation.title and frag_title and citation.title.strip().lower() == frag_title.strip().lower():
            return frag.get("source_tool", "unknown")

        # Match by URL
        if citation.url and frag_url and citation.url.strip() == frag_url.strip():
            return frag.get("source_tool", "unknown")

    return "unknown"


# ── Build Provenance Chain ────────────────────────────────────────────


def build_provenance_chain(
    run_id: str,
    query: str,
    claims: list[Claim],
    evidence_fragments: list[dict[str, Any]] | None = None,
) -> ProvenanceChain:
    """Walk each claim's citations, match them to evidence fragments, and build the chain.

    Args:
        run_id: The unique run identifier.
        query: The original research query.
        claims: List of Claim objects from the agent output.
        evidence_fragments: Raw evidence fragment dicts from the evidence graph
                           (each should have source_tool, title, doi, url, snippet, etc.).

    Returns:
        A ProvenanceChain with all links populated and ungrounded claims flagged.
    """
    if evidence_fragments is None:
        evidence_fragments = []

    links: list[ProvenanceLink] = []
    ungrounded: list[str] = []
    total_citations = 0

    for claim in claims:
        has_any_link = False

        for citation in claim.citations:
            total_citations += 1

            # Match evidence span to this citation
            matched_span = _match_evidence_to_citation(
                citation,
                claim.evidence_spans + claim.conflicting_evidence,
            )

            # Infer retrieval tool from evidence fragments
            tool = _infer_retrieval_tool(citation, evidence_fragments)

            # Find retrieval timestamp from evidence fragments
            timestamp = ""
            for frag in evidence_fragments:
                frag_doi = frag.get("doi", "")
                frag_title = frag.get("title", "")
                if (citation.doi and frag_doi and citation.doi.strip().lower() == frag_doi.strip().lower()) or (
                    citation.title and frag_title and citation.title.strip().lower() == frag_title.strip().lower()
                ):
                    timestamp = frag.get("retrieved_at", "")
                    if hasattr(timestamp, "isoformat"):
                        timestamp = timestamp.isoformat()
                    else:
                        timestamp = str(timestamp) if timestamp else ""
                    break

            link = ProvenanceLink(
                claim_id=claim.id,
                claim_text=claim.statement,
                citation=citation,
                evidence_span=matched_span,
                retrieval_tool=tool,
                retrieval_timestamp=timestamp,
                verification_status="unverified",
                doi_verified=False,
            )

            links.append(link)
            has_any_link = True

        # Claims with NO citations at all are ungrounded
        if not has_any_link:
            ungrounded.append(claim.statement)

    # Calculate coverage: links with evidence spans / total citations
    grounded_links = sum(1 for link in links if link.evidence_span is not None)
    coverage = grounded_links / total_citations if total_citations > 0 else 0.0

    chain = ProvenanceChain(
        run_id=run_id,
        query=query,
        links=links,
        ungrounded_claims=ungrounded,
        coverage_score=coverage,
    )

    return chain


async def verify_provenance_chain(chain: ProvenanceChain) -> ProvenanceChain:
    """Verify DOIs in the provenance chain asynchronously.

    Updates each link's verification_status and doi_verified fields.
    This is designed to be non-blocking and should be called after the chain is built.
    """
    # Collect all unique DOIs
    doi_map: dict[str, list[ProvenanceLink]] = {}
    for link in chain.links:
        doi = link.citation.doi
        if doi:
            if doi not in doi_map:
                doi_map[doi] = []
            doi_map[doi].append(link)

    if not doi_map:
        # No DOIs to verify — mark all as unverified
        for link in chain.links:
            link.verification_status = "unverified"
        return chain

    # Verify all DOIs concurrently
    verification_results = await verify_dois_batch(list(doi_map.keys()))

    # Update links with verification results
    for doi, is_valid in verification_results.items():
        for link in doi_map.get(doi, []):
            link.doi_verified = is_valid
            if is_valid:
                link.verification_status = "verified"
            else:
                link.verification_status = "broken"

    # Links without DOIs remain "unverified"
    for link in chain.links:
        if not link.citation.doi:
            link.verification_status = "unverified"

    # Recalculate coverage based on verified links
    verified_count = sum(1 for link in chain.links if link.verification_status == "verified")
    total = len(chain.links)
    chain.coverage_score = verified_count / total if total > 0 else 0.0

    logger.info(
        "provenance_verified",
        run_id=chain.run_id,
        total_links=total,
        verified=verified_count,
        coverage=chain.coverage_score,
    )

    return chain


# ── In-Memory Provenance Store ────────────────────────────────────────

# Simple in-memory store for provenance chains (keyed by run_id).
# In production this would be persisted to the database.
_provenance_store: dict[str, ProvenanceChain] = {}


def store_provenance(chain: ProvenanceChain) -> None:
    """Store a provenance chain in the in-memory store."""
    _provenance_store[chain.run_id] = chain


def get_provenance(run_id: str) -> ProvenanceChain | None:
    """Retrieve a provenance chain by run_id."""
    return _provenance_store.get(run_id)


def get_all_provenance_ids() -> list[str]:
    """List all stored provenance chain run IDs."""
    return list(_provenance_store.keys())
