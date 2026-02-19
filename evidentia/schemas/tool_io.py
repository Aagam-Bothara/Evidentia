"""Strict I/O schemas for tool execution contracts."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Tool contract ────────────────────────────────────────────────────

class ToolInput(BaseModel):
    """Base class for all tool inputs."""

    pass


class ToolOutput(BaseModel):
    """Base class for all tool outputs."""

    success: bool = True
    data: Any = None
    error: str | None = None


# ── Web Search ───────────────────────────────────────────────────────

class WebSearchInput(ToolInput):
    query: str = Field(..., min_length=1, max_length=1000)
    max_results: int = Field(default=10, ge=1, le=50)


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class WebSearchOutput(ToolOutput):
    data: list[WebSearchResult] = Field(default_factory=list)


# ── ArXiv ────────────────────────────────────────────────────────────

class ArxivSearchInput(ToolInput):
    query: str = Field(..., min_length=1)
    max_results: int = Field(default=10, ge=1, le=50)
    sort_by: str = Field(default="relevance")


class ArxivPaper(BaseModel):
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published: str
    url: str
    doi: str | None = None
    categories: list[str] = Field(default_factory=list)


class ArxivSearchOutput(ToolOutput):
    data: list[ArxivPaper] = Field(default_factory=list)


# ── Python Sandbox ───────────────────────────────────────────────────

class PythonSandboxInput(ToolInput):
    code: str = Field(..., min_length=1, max_length=10000)
    timeout_seconds: int = Field(default=30, ge=1, le=120)


class PythonSandboxOutput(ToolOutput):
    stdout: str = ""
    stderr: str = ""
    return_value: Any = None


# ── PDF Ingestion ────────────────────────────────────────────────────

class PDFIngestInput(ToolInput):
    url: str | None = None
    file_path: str | None = None


class PDFChunk(BaseModel):
    """A text chunk extracted from a PDF, with provenance."""

    text: str
    page_number: int
    chunk_index: int


class PDFIngestOutput(ToolOutput):
    text: str = ""
    page_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunks: list[PDFChunk] = Field(default_factory=list)


# ── DOI / Crossref ──────────────────────────────────────────────────

class DOILookupInput(ToolInput):
    doi: str


class DOILookupOutput(ToolOutput):
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    journal: str = ""
    published_date: str = ""
    url: str = ""
    citation_count: int | None = None


# ── Semantic Scholar ─────────────────────────────────────────────────

class SemanticScholarInput(ToolInput):
    query: str = Field(..., min_length=1)
    max_results: int = Field(default=10, ge=1, le=100)
    fields: list[str] = Field(
        default_factory=lambda: ["title", "abstract", "authors", "year", "citationCount", "url"]
    )


class SemanticScholarPaper(BaseModel):
    paper_id: str
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    citation_count: int | None = None
    url: str | None = None


class SemanticScholarOutput(ToolOutput):
    data: list[SemanticScholarPaper] = Field(default_factory=list)


# ── PubMed ──────────────────────────────────────────────────────────

class PubMedSearchInput(ToolInput):
    query: str = Field(..., min_length=1)
    max_results: int = Field(default=10, ge=1, le=100)
    date_range: str | None = Field(default=None, description="YYYY/MM/DD:YYYY/MM/DD")


class PubMedArticle(BaseModel):
    pmid: str
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    published_date: str = ""
    doi: str | None = None
    url: str | None = None


class PubMedSearchOutput(ToolOutput):
    data: list[PubMedArticle] = Field(default_factory=list)


# ── OpenAlex ────────────────────────────────────────────────────────

class OpenAlexSearchInput(ToolInput):
    query: str = Field(..., min_length=1)
    max_results: int = Field(default=10, ge=1, le=200)
    filter_open_access: bool = False


class OpenAlexWork(BaseModel):
    work_id: str
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    published_date: str = ""
    doi: str | None = None
    cited_by_count: int | None = None
    open_access_url: str | None = None
    url: str | None = None


class OpenAlexSearchOutput(ToolOutput):
    data: list[OpenAlexWork] = Field(default_factory=list)


# ── CrossRef Search ─────────────────────────────────────────────────

class CrossRefSearchInput(ToolInput):
    query: str = Field(..., min_length=1)
    max_results: int = Field(default=10, ge=1, le=100)


class CrossRefWork(BaseModel):
    doi: str
    title: str
    authors: list[str] = Field(default_factory=list)
    journal: str = ""
    published_date: str = ""
    citation_count: int | None = None
    url: str | None = None


class CrossRefSearchOutput(ToolOutput):
    data: list[CrossRefWork] = Field(default_factory=list)
