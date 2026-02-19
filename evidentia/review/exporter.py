"""Export systematic review results in CSV, BibTeX, and RIS formats."""

from __future__ import annotations

import csv
import io
import re

from evidentia.review.models import PaperRecord


class ReviewExporter:
    """Export review papers in standard formats."""

    @staticmethod
    def to_csv(papers: list[PaperRecord], include_excluded: bool = False) -> str:
        """Export papers as CSV with screening decisions."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Title",
            "Authors",
            "DOI",
            "URL",
            "Published Date",
            "Journal",
            "Citation Count",
            "Source Database",
            "Decision",
            "Exclusion Reason",
        ])

        for paper in papers:
            if not include_excluded and paper.screening_decision == "exclude":
                continue
            if paper.is_duplicate:
                continue

            writer.writerow([
                paper.title,
                "; ".join(paper.authors),
                paper.doi or "",
                paper.url or "",
                paper.published_date or "",
                paper.journal or "",
                paper.citation_count or "",
                paper.source_database,
                paper.screening_decision or "unscreened",
                paper.exclusion_reason or "",
            ])

        return output.getvalue()

    @staticmethod
    def to_bibtex(papers: list[PaperRecord]) -> str:
        """Export included papers as BibTeX."""
        entries: list[str] = []

        for idx, paper in enumerate(papers, start=1):
            if paper.is_duplicate or paper.screening_decision != "include":
                continue

            key = f"review_{idx}"
            year = ReviewExporter._extract_year(paper.published_date)
            authors = " and ".join(paper.authors) if paper.authors else ""

            lines = [f"@article{{{key},"]
            lines.append(f"  title = {{{paper.title}}},")
            if authors:
                lines.append(f"  author = {{{authors}}},")
            if year:
                lines.append(f"  year = {{{year}}},")
            if paper.journal:
                lines.append(f"  journal = {{{paper.journal}}},")
            if paper.url:
                lines.append(f"  url = {{{paper.url}}},")
            if paper.doi:
                lines.append(f"  doi = {{{paper.doi}}},")
            lines.append("  note = {Included via Evidentia systematic review}")
            lines.append("}")

            entries.append("\n".join(lines))

        return "\n\n".join(entries) + "\n" if entries else ""

    @staticmethod
    def to_ris(papers: list[PaperRecord]) -> str:
        """Export included papers as RIS."""
        entries: list[str] = []

        for paper in papers:
            if paper.is_duplicate or paper.screening_decision != "include":
                continue

            year = ReviewExporter._extract_year(paper.published_date)
            lines = ["TY  - JOUR"]
            lines.append(f"TI  - {paper.title}")
            for author in paper.authors:
                lines.append(f"AU  - {author}")
            if paper.journal:
                lines.append(f"JO  - {paper.journal}")
            if paper.url:
                lines.append(f"UR  - {paper.url}")
            if paper.doi:
                lines.append(f"DO  - {paper.doi}")
            if year:
                lines.append(f"PY  - {year}")
            lines.append("ER  - ")

            entries.append("\n".join(lines))

        return "\n".join(entries) + "\n" if entries else ""

    @staticmethod
    def _extract_year(date_str: str | None) -> str:
        """Extract a four-digit year from a date string."""
        if not date_str:
            return ""
        match = re.search(r"\b(\d{4})\b", date_str)
        return match.group(1) if match else ""
