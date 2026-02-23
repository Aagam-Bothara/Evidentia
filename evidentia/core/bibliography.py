"""Pure-Python parser for BibTeX and RIS bibliography formats.

Converts bibliography files into a unified ImportedPaper format for
ingestion into systematic reviews. No external dependencies required.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from evidentia.core.logging import get_logger

logger = get_logger(__name__)

# ── Data model ──────────────────────────────────────────────────────


@dataclass
class ImportedPaper:
    """Unified representation of a paper parsed from a bibliography file."""

    title: str
    authors: list[str] = field(default_factory=list)
    year: str | None = None
    doi: str | None = None
    url: str | None = None
    journal: str | None = None
    abstract: str | None = None
    volume: str | None = None
    pages: str | None = None
    source_format: str = ""  # "bibtex" or "ris"
    raw_entry: str = ""  # original text for debugging


# ── LaTeX special character conversion ──────────────────────────────

# Mapping of LaTeX accent commands to combining Unicode characters.
# Pattern: \'{x} or \'x  ->  x + combining accent
_LATEX_ACCENT_MAP: dict[str, str] = {
    "`": "\u0300",  # grave
    "'": "\u0301",  # acute
    "^": "\u0302",  # circumflex
    "~": "\u0303",  # tilde
    '"': "\u0308",  # diaeresis / umlaut
    "=": "\u0304",  # macron
    ".": "\u0307",  # dot above
    "u": "\u0306",  # breve
    "v": "\u030c",  # caron / hacek
    "H": "\u030b",  # double acute
    "c": "\u0327",  # cedilla
    "d": "\u0323",  # dot below
    "b": "\u0331",  # bar below
    "k": "\u0328",  # ogonek
    "r": "\u030a",  # ring above
}

# Special LaTeX commands that map to single characters.
_LATEX_SPECIAL_CHARS: dict[str, str] = {
    r"\aa": "\u00e5",  # å
    r"\AA": "\u00c5",  # Å
    r"\ae": "\u00e6",  # æ
    r"\AE": "\u00c6",  # Æ
    r"\oe": "\u0153",  # œ
    r"\OE": "\u0152",  # Œ
    r"\o": "\u00f8",  # ø
    r"\O": "\u00d8",  # Ø
    r"\ss": "\u00df",  # ß
    r"\l": "\u0142",  # ł
    r"\L": "\u0141",  # Ł
    r"\i": "\u0131",  # ı (dotless i)
    r"\j": "\u0237",  # ȷ (dotless j)
    r"\&": "&",
    r"\%": "%",
    r"\$": "$",
    r"\#": "#",
    r"\_": "_",
    r"\{": "{",
    r"\}": "}",
    r"~": "\u00a0",  # non-breaking space (when not an accent)
    "---": "\u2014",  # em dash
    "--": "\u2013",  # en dash
}


def _convert_latex(text: str) -> str:
    """Convert LaTeX special characters and accents to Unicode.

    Handles patterns like:
      \\'{e}  -> é      \\'{\\i}  -> í
      \\'e    -> é      \\~{n}   -> ñ
      \\ss    -> ß      \\ae     -> æ
    """
    if "\\" not in text and "~" not in text and "--" not in text:
        return text

    result = text

    # 1. Replace special character commands first (longer patterns first)
    for latex_cmd, replacement in sorted(_LATEX_SPECIAL_CHARS.items(), key=lambda x: -len(x[0])):
        result = result.replace(latex_cmd, replacement)

    # 2. Handle accent commands: \X{char} and \X char patterns
    # Pattern: \accent{content}  e.g. \'{e} or \"{o} or \c{c}
    def _replace_braced_accent(match: re.Match[str]) -> str:
        accent_cmd = match.group(1)
        content = match.group(2)
        combining = _LATEX_ACCENT_MAP.get(accent_cmd)
        if combining is None:
            return match.group(0)  # unknown accent, leave as-is
        # Handle \i and \j inside braces
        if content == r"\i":
            content = "\u0131"
        elif content == r"\j":
            content = "\u0237"
        return unicodedata.normalize("NFC", content + combining)

    result = re.sub(
        r"\\([`'^\"~=.uvHcdbkr])\{([^}]*)\}",
        _replace_braced_accent,
        result,
    )

    # Pattern: \accent<single-char>  e.g. \'e or \"o  (no braces)
    def _replace_bare_accent(match: re.Match[str]) -> str:
        accent_cmd = match.group(1)
        char = match.group(2)
        combining = _LATEX_ACCENT_MAP.get(accent_cmd)
        if combining is None:
            return match.group(0)
        return unicodedata.normalize("NFC", char + combining)

    result = re.sub(
        r"\\([`'^\"~=.uvHcdbkr])([A-Za-z])",
        _replace_bare_accent,
        result,
    )

    # 3. Strip remaining braces (BibTeX uses {} for case protection)
    result = result.replace("{", "").replace("}", "")

    return result.strip()


# ── BibTeX parser ───────────────────────────────────────────────────

# Regex to find BibTeX entries: @type{key, ... }
_BIBTEX_ENTRY_RE = re.compile(
    r"@(\w+)\s*\{([^,]*),",
    re.IGNORECASE,
)

# Regex for a field assignment: fieldname = {value} or fieldname = "value" or fieldname = number
_BIBTEX_FIELD_RE = re.compile(
    r"(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|\"([^\"]*)\"|(\d+))",
    re.DOTALL,
)


def _extract_bibtex_entries(text: str) -> list[str]:
    """Split raw BibTeX text into individual entry strings.

    Handles nested braces correctly by counting brace depth.
    """
    entries: list[str] = []
    i = 0
    length = len(text)

    while i < length:
        # Find next @type{
        match = _BIBTEX_ENTRY_RE.search(text, i)
        if match is None:
            break

        start = match.start()
        # Find the opening brace of the entry body
        brace_pos = text.index("{", match.start())
        depth = 1
        pos = brace_pos + 1

        while pos < length and depth > 0:
            ch = text[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            pos += 1

        entries.append(text[start:pos])
        i = pos

    return entries


def _parse_bibtex_fields(entry_body: str) -> dict[str, str]:
    """Extract field name -> value pairs from a single BibTeX entry body."""
    fields: dict[str, str] = {}
    for match in _BIBTEX_FIELD_RE.finditer(entry_body):
        name = match.group(1).lower()
        # Value can be in braces (group 2), quotes (group 3), or bare number (group 4)
        value = match.group(2) or match.group(3) or match.group(4) or ""
        fields[name] = value.strip()
    return fields


def _split_bibtex_authors(raw: str) -> list[str]:
    """Split a BibTeX author string on ' and ' into individual names.

    Handles:
      "Last, First and Last2, First2"
      "First Last and First2 Last2"
    """
    # Split on " and " (case-insensitive)
    parts = re.split(r"\s+and\s+", raw, flags=re.IGNORECASE)
    authors: list[str] = []
    for part in parts:
        cleaned = _convert_latex(part.strip())
        if cleaned:
            authors.append(cleaned)
    return authors


def parse_bibtex(text: str) -> list[ImportedPaper]:
    """Parse BibTeX-formatted text into a list of ImportedPaper records.

    Supports @article, @inproceedings, @book, @misc, @phdthesis,
    @mastersthesis, @techreport, and other standard entry types.
    """
    entries = _extract_bibtex_entries(text)
    papers: list[ImportedPaper] = []

    for raw_entry in entries:
        match = _BIBTEX_ENTRY_RE.match(raw_entry)
        if match is None:
            continue

        entry_type = match.group(1).lower()

        # Skip non-document entry types
        if entry_type in ("comment", "preamble", "string"):
            continue

        fields = _parse_bibtex_fields(raw_entry)

        title = _convert_latex(fields.get("title", ""))
        if not title:
            logger.debug("bibtex_skip_no_title", raw=raw_entry[:100])
            continue

        authors = _split_bibtex_authors(fields.get("author", ""))

        year = fields.get("year")

        doi = fields.get("doi")
        if doi:
            # Clean DOI: strip URL prefix if present
            doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip())

        url = fields.get("url")

        # Journal: try journal, then booktitle (for inproceedings)
        journal = _convert_latex(fields.get("journal", "")) or _convert_latex(fields.get("booktitle", "")) or None

        abstract = _convert_latex(fields.get("abstract", "")) or None

        volume = fields.get("volume")

        pages = fields.get("pages")
        if pages:
            # Normalise double-dash to en-dash
            pages = pages.replace("--", "\u2013")

        papers.append(
            ImportedPaper(
                title=title,
                authors=authors,
                year=year,
                doi=doi,
                url=url,
                journal=journal,
                abstract=abstract,
                volume=volume,
                pages=pages,
                source_format="bibtex",
                raw_entry=raw_entry,
            )
        )

    logger.info("bibtex_parsed", total=len(papers))
    return papers


# ── RIS parser ──────────────────────────────────────────────────────

# RIS tag pattern: two uppercase letters followed by optional digits,
# then "  - " then the value.
_RIS_TAG_RE = re.compile(r"^([A-Z][A-Z0-9]{0,3})\s{2}-\s(.*)$")


def parse_ris(text: str) -> list[ImportedPaper]:
    """Parse RIS-formatted text into a list of ImportedPaper records.

    Each record starts with "TY  - " and ends with "ER  - ".
    Multiple AU lines produce multiple authors.
    """
    papers: list[ImportedPaper] = []

    # Normalise line endings
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    # Accumulate tags for the current record
    current_tags: dict[str, list[str]] = {}
    raw_lines: list[str] = []
    in_record = False

    for line in lines:
        match = _RIS_TAG_RE.match(line)
        if match is None:
            # Continuation or blank line — append to raw_lines if in record
            if in_record:
                raw_lines.append(line)
            continue

        tag = match.group(1)
        value = match.group(2).strip()

        if tag == "TY":
            # Start of a new record
            in_record = True
            current_tags = {"TY": [value]}
            raw_lines = [line]
            continue

        if not in_record:
            continue

        raw_lines.append(line)

        if tag == "ER":
            # End of record — build the ImportedPaper
            paper = _build_ris_paper(current_tags, "\n".join(raw_lines))
            if paper is not None:
                papers.append(paper)
            in_record = False
            current_tags = {}
            raw_lines = []
            continue

        # Accumulate tag values (supports repeatable tags like AU)
        current_tags.setdefault(tag, []).append(value)

    # Handle unterminated record (missing ER)
    if in_record and current_tags:
        paper = _build_ris_paper(current_tags, "\n".join(raw_lines))
        if paper is not None:
            papers.append(paper)

    logger.info("ris_parsed", total=len(papers))
    return papers


def _ris_first(tags: dict[str, list[str]], key: str) -> str | None:
    """Return the first value for a RIS tag, or None."""
    values = tags.get(key)
    if values:
        return values[0].strip() or None
    return None


def _build_ris_paper(tags: dict[str, list[str]], raw_entry: str) -> ImportedPaper | None:
    """Convert accumulated RIS tags into an ImportedPaper."""
    # Title: TI or T1
    title = _ris_first(tags, "TI") or _ris_first(tags, "T1") or ""
    if not title:
        logger.debug("ris_skip_no_title", raw=raw_entry[:100])
        return None

    # Authors: AU or A1 (repeatable)
    authors = [a.strip() for a in tags.get("AU", tags.get("A1", [])) if a.strip()]

    # Year: PY or Y1 (often "YYYY/MM/DD/" or "YYYY")
    raw_year = _ris_first(tags, "PY") or _ris_first(tags, "Y1")
    year: str | None = None
    if raw_year:
        # Extract the 4-digit year from formats like "2023/01/15/"
        year_match = re.match(r"(\d{4})", raw_year)
        year = year_match.group(1) if year_match else raw_year

    # DOI: DO
    doi = _ris_first(tags, "DO")
    if doi:
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip())

    # URL: UR
    url = _ris_first(tags, "UR")

    # Journal: JO, JF, JA, or T2
    journal = _ris_first(tags, "JO") or _ris_first(tags, "JF") or _ris_first(tags, "JA") or _ris_first(tags, "T2")

    # Abstract: AB or N2
    abstract = _ris_first(tags, "AB") or _ris_first(tags, "N2")

    # Volume: VL
    volume = _ris_first(tags, "VL")

    # Pages: SP (start) and EP (end)
    sp = _ris_first(tags, "SP")
    ep = _ris_first(tags, "EP")
    pages: str | None = None
    if sp and ep:
        pages = f"{sp}\u2013{ep}"
    elif sp:
        pages = sp

    return ImportedPaper(
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        url=url,
        journal=journal,
        abstract=abstract,
        volume=volume,
        pages=pages,
        source_format="ris",
        raw_entry=raw_entry,
    )


# ── Format detection and unified entry point ────────────────────────


def detect_format(text: str) -> str:
    """Auto-detect bibliography format from file content.

    Returns:
        "bibtex" or "ris".

    Raises:
        ValueError: If the format cannot be determined.
    """
    stripped = text.strip()

    # BibTeX: look for @type{ pattern
    if re.search(r"@\w+\s*\{", stripped):
        return "bibtex"

    # RIS: look for tag lines like "TY  - "
    if re.search(r"^TY\s{2}-\s", stripped, re.MULTILINE):
        return "ris"

    raise ValueError(
        "Unable to detect bibliography format. Expected BibTeX (@article{...}) or RIS (TY  - ...) content."
    )


def parse_bibliography(text: str) -> list[ImportedPaper]:
    """Auto-detect format and parse a bibliography file.

    Combines detect_format() with the appropriate parser.

    Returns:
        List of ImportedPaper records.

    Raises:
        ValueError: If the format cannot be detected.
    """
    fmt = detect_format(text)
    if fmt == "bibtex":
        return parse_bibtex(text)
    return parse_ris(text)
