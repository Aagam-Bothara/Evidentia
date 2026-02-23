"""CSL-JSON citation export — universal format for Zotero, Mendeley, and other managers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from evidentia.core.logging import get_logger
from evidentia.core.models import Citation, Claim

logger = get_logger(__name__)

# ── CSL-JSON type mapping ──────────────────────────────────────────

# Map common source hints to CSL-JSON item types.
_CSL_TYPE_MAP: dict[str, str] = {
    "journal": "article-journal",
    "article": "article-journal",
    "conference": "paper-conference",
    "book": "book",
    "chapter": "chapter",
    "webpage": "webpage",
    "preprint": "article",
    "thesis": "thesis",
    "report": "report",
    "dataset": "dataset",
}


@dataclass
class CSLItem:
    """A single CSL-JSON item (one bibliographic record)."""

    id: str
    type: str  # "article-journal", "paper-conference", "book", "webpage", ...
    title: str
    authors: list[dict[str, str]] = field(default_factory=list)
    issued: dict[str, Any] | None = None  # {"date-parts": [[2024, 1, 15]]}
    DOI: str | None = None
    URL: str | None = None
    abstract: str | None = None
    container_title: str | None = None  # journal / conference name
    volume: str | None = None
    page: str | None = None
    citation_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a CSL-JSON-compliant dict."""
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "author": self.authors,
        }
        if self.issued:
            d["issued"] = self.issued
        if self.DOI:
            d["DOI"] = self.DOI
        if self.URL:
            d["URL"] = self.URL
        if self.abstract:
            d["abstract"] = self.abstract
        if self.container_title:
            d["container-title"] = self.container_title
        if self.volume:
            d["volume"] = self.volume
        if self.page:
            d["page"] = self.page
        if self.citation_count is not None:
            # Non-standard but useful; CSL processors ignore unknown keys.
            d["citation-count"] = self.citation_count
        return d


# ── Public API ──────────────────────────────────────────────────────


def claims_to_csl_json(claims: list[Claim | dict[str, Any]]) -> str:
    """Convert Evidentia claims (with citations) to a CSL-JSON array string.

    Accepts both ``Claim`` model instances and raw dicts (e.g. from an API
    request body).  Citations are deduplicated by DOI / URL so the exported
    list contains no duplicate records.

    Returns:
        A JSON string containing an array of CSL-JSON items.
    """
    parsed_claims = _normalise_claims(claims)
    citations = _deduplicate_citations(parsed_claims)
    items = [_citation_to_csl_item(c, idx) for idx, c in enumerate(citations, start=1)]
    return json.dumps([item.to_dict() for item in items], indent=2, ensure_ascii=False) + "\n"


def papers_to_csl_json(papers: list[Any]) -> str:
    """Convert review papers (``PaperRecord`` or dict) to CSL-JSON.

    Designed for systematic-review paper export where the source objects
    come from ``evidentia.review.models.PaperRecord``.
    """
    items: list[dict[str, Any]] = []
    for idx, paper in enumerate(papers, start=1):
        p = paper if isinstance(paper, dict) else paper.model_dump() if hasattr(paper, "model_dump") else paper.__dict__
        csl = CSLItem(
            id=f"paper_{idx}",
            type=_guess_csl_type(p.get("journal")),
            title=p.get("title", ""),
            authors=[_parse_author_name(a) for a in (p.get("authors") or [])],
            issued=_parse_date(p.get("published_date")),
            DOI=p.get("doi"),
            URL=p.get("url"),
            abstract=p.get("abstract"),
            container_title=p.get("journal"),
            citation_count=p.get("citation_count"),
        )
        items.append(csl.to_dict())
    return json.dumps(items, indent=2, ensure_ascii=False) + "\n"


# ── Internal helpers ────────────────────────────────────────────────


def _normalise_claims(claims: list[Claim | dict[str, Any]]) -> list[Claim]:
    """Accept both Claim objects and raw dicts, returning a list of Claims."""
    out: list[Claim] = []
    for c in claims:
        if isinstance(c, Claim):
            out.append(c)
        else:
            out.append(Claim.model_validate(c))
    return out


def _deduplicate_citations(claims: list[Claim]) -> list[Citation]:
    """Collect unique citations across all claims (same DOI or URL = same)."""
    seen_dois: set[str] = set()
    seen_urls: set[str] = set()
    unique: list[Citation] = []

    for claim in claims:
        for citation in claim.citations:
            if citation.doi:
                doi_lower = citation.doi.lower()
                if doi_lower in seen_dois:
                    continue
                seen_dois.add(doi_lower)

            if citation.url:
                if citation.url in seen_urls:
                    continue
                seen_urls.add(citation.url)

            unique.append(citation)

    return unique


def _citation_to_csl_item(citation: Citation, index: int) -> CSLItem:
    """Map an Evidentia ``Citation`` to a ``CSLItem``."""
    return CSLItem(
        id=f"evidentia_{index}",
        type=_guess_csl_type(None),
        title=citation.title,
        authors=[_parse_author_name(a) for a in citation.authors],
        issued=_parse_date(citation.published_date),
        DOI=citation.doi,
        URL=citation.url,
    )


def _guess_csl_type(journal: str | None) -> str:
    """Return a reasonable CSL type string.

    If a journal name is present the source is most likely a journal
    article; otherwise default to ``"article"`` (generic).
    """
    if journal:
        return "article-journal"
    return "article"


def _parse_author_name(name: str) -> dict[str, str]:
    """Parse a human-readable author name into a CSL name object.

    Handles:
    * ``"Smith, John"``  -> ``{"family": "Smith", "given": "John"}``
    * ``"John Smith"``   -> ``{"family": "Smith", "given": "John"}``
    * ``"Smith"``        -> ``{"family": "Smith"}``
    """
    name = name.strip()
    if not name:
        return {"family": ""}

    if "," in name:
        parts = name.split(",", 1)
        result: dict[str, str] = {"family": parts[0].strip()}
        given = parts[1].strip()
        if given:
            result["given"] = given
        return result

    parts = name.split()
    if len(parts) == 1:
        return {"family": parts[0]}
    return {"family": parts[-1], "given": " ".join(parts[:-1])}


def _parse_date(date_str: str | None) -> dict[str, Any] | None:
    """Parse a date string into a CSL date object.

    Supported formats: ``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``.
    Returns ``None`` when the input cannot be parsed.
    """
    if not date_str:
        return None
    m = re.match(r"(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", date_str.strip())
    if m:
        parts: list[int] = [int(m.group(1))]
        if m.group(2):
            parts.append(int(m.group(2)))
        if m.group(3):
            parts.append(int(m.group(3)))
        return {"date-parts": [parts]}
    return None
