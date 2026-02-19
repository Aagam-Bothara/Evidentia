"""Citation Exporter — converts claims and citations to BibTeX, RIS, APA, and JSON."""

from __future__ import annotations

import json
import re
from typing import Any

from evidentia.core.models import Citation, Claim


class CitationExporter:
    """Export citations from research claims into standard bibliographic formats."""

    # ── Public API ──────────────────────────────────────────────────────

    @staticmethod
    def to_bibtex(claims: list[Claim]) -> str:
        """Export deduplicated citations as a BibTeX string."""
        citations = CitationExporter._deduplicate_citations(claims)
        entries: list[str] = []

        for idx, citation in enumerate(citations, start=1):
            key = CitationExporter._make_bibtex_key(idx, citation)
            year = CitationExporter._extract_year(citation.published_date)
            authors = " and ".join(citation.authors) if citation.authors else ""

            lines = [f"@article{{{key},"]
            lines.append(f"  title = {{{citation.title}}},")
            if authors:
                lines.append(f"  author = {{{authors}}},")
            if year:
                lines.append(f"  year = {{{year}}},")
            if citation.url:
                lines.append(f"  url = {{{citation.url}}},")
            if citation.doi:
                lines.append(f"  doi = {{{citation.doi}}},")
            lines.append("  note = {Retrieved via Evidentia}")
            lines.append("}")

            entries.append("\n".join(lines))

        return "\n\n".join(entries) + "\n" if entries else ""

    @staticmethod
    def to_ris(claims: list[Claim]) -> str:
        """Export deduplicated citations as an RIS string."""
        citations = CitationExporter._deduplicate_citations(claims)
        entries: list[str] = []

        for citation in citations:
            year = CitationExporter._extract_year(citation.published_date)
            lines = ["TY  - JOUR"]
            lines.append(f"TI  - {citation.title}")
            for author in citation.authors:
                lines.append(f"AU  - {author}")
            if citation.url:
                lines.append(f"UR  - {citation.url}")
            if citation.doi:
                lines.append(f"DO  - {citation.doi}")
            if year:
                lines.append(f"PY  - {year}")
            lines.append("ER  - ")

            entries.append("\n".join(lines))

        return "\n".join(entries) + "\n" if entries else ""

    @staticmethod
    def to_apa(claims: list[Claim]) -> str:
        """Export deduplicated citations as APA-formatted references."""
        citations = CitationExporter._deduplicate_citations(claims)
        references: list[str] = []

        for citation in citations:
            ref = CitationExporter._format_apa_entry(citation)
            references.append(ref)

        return "\n\n".join(references) + "\n" if references else ""

    @staticmethod
    def to_json(claims: list[Claim]) -> str:
        """Export all claims with their citations as structured JSON."""
        output: list[dict[str, Any]] = []

        for claim in claims:
            claim_data: dict[str, Any] = {
                "id": claim.id,
                "statement": claim.statement,
                "confidence": claim.confidence.value,
                "citations": [
                    {
                        "source_id": c.source_id,
                        "title": c.title,
                        "authors": c.authors,
                        "url": c.url,
                        "doi": c.doi,
                        "published_date": c.published_date,
                    }
                    for c in claim.citations
                ],
                "evidence_spans": [
                    {
                        "source_id": e.source_id,
                        "text": e.text,
                        "start_offset": e.start_offset,
                        "end_offset": e.end_offset,
                    }
                    for e in claim.evidence_spans
                ],
                "conflicting_evidence": [
                    {
                        "source_id": e.source_id,
                        "text": e.text,
                        "start_offset": e.start_offset,
                        "end_offset": e.end_offset,
                    }
                    for e in claim.conflicting_evidence
                ],
            }
            output.append(claim_data)

        return json.dumps(output, indent=2, ensure_ascii=False) + "\n"

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _deduplicate_citations(claims: list[Claim]) -> list[Citation]:
        """Collect unique citations across all claims (same DOI or URL = same)."""
        seen_dois: set[str] = set()
        seen_urls: set[str] = set()
        unique: list[Citation] = []

        for claim in claims:
            for citation in claim.citations:
                # Deduplicate by DOI first, then by URL
                if citation.doi:
                    doi_lower = citation.doi.lower()
                    if doi_lower in seen_dois:
                        continue
                    seen_dois.add(doi_lower)

                if citation.url:
                    if citation.url in seen_urls:
                        continue
                    seen_urls.add(citation.url)

                # If neither DOI nor URL matched a previous entry, add it
                # (also handles citations with no DOI and no URL)
                unique.append(citation)

        return unique

    @staticmethod
    def _extract_year(date_str: str | None) -> str:
        """Extract a four-digit year from a date string.

        Handles formats like "2024", "2024-01", "2024-01-15", etc.
        Returns empty string if no year can be extracted.
        """
        if not date_str:
            return ""
        match = re.search(r"\b(\d{4})\b", date_str)
        return match.group(1) if match else ""

    @staticmethod
    def _make_bibtex_key(index: int, citation: Citation) -> str:
        """Generate a clean BibTeX citation key like ``evidentia_1``."""
        return f"evidentia_{index}"

    @staticmethod
    def _format_apa_entry(citation: Citation) -> str:
        """Format a single citation in APA style (plain text)."""
        year = CitationExporter._extract_year(citation.published_date)
        year_part = f"({year})" if year else "(n.d.)"

        # Build author string with APA ampersand convention
        author_part = CitationExporter._format_apa_authors(citation.authors)

        # Title in APA is italicised — represented as plain text here
        title_part = citation.title

        # Assemble: Author(s) (Year). Title.
        parts = []
        if author_part:
            parts.append(f"{author_part} {year_part}. {title_part}.")
        else:
            parts.append(f"{title_part} {year_part}.")

        # Append retrieval URL or DOI
        if citation.doi:
            parts.append(f"https://doi.org/{citation.doi}")
        elif citation.url:
            parts.append(f"Retrieved from {citation.url}")

        return " ".join(parts)

    @staticmethod
    def _format_apa_authors(authors: list[str]) -> str:
        """Format an author list according to APA conventions.

        - 1 author:  ``Author, A.``
        - 2 authors: ``Author, A., & Author, B.``
        - 3+ authors: ``Author, A., Author, B., & Author, C.``
        """
        if not authors:
            return ""
        if len(authors) == 1:
            return authors[0]
        if len(authors) == 2:
            return f"{authors[0]}, & {authors[1]}"
        # Three or more
        leading = ", ".join(authors[:-1])
        return f"{leading}, & {authors[-1]}"
