"""Tools endpoint — list and inspect available tools."""

from __future__ import annotations

from fastapi import APIRouter

from evidentia.schemas.api import ToolListItem, ToolListResponse

router = APIRouter()

# Default tool manifest (loaded from registry at startup in production)
DEFAULT_TOOLS = [
    ToolListItem(
        name="web_search",
        description="Search the web for relevant pages, articles, and documents.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}},
        output_schema={"type": "object", "properties": {"data": {"type": "array"}}},
        category="public_api",
    ),
    ToolListItem(
        name="arxiv_search",
        description="Search arXiv for academic papers matching a query.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}},
        output_schema={"type": "object", "properties": {"data": {"type": "array"}}},
        category="public_api",
    ),
    ToolListItem(
        name="semantic_scholar",
        description="Search Semantic Scholar for papers with citation counts.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}},
        output_schema={"type": "object", "properties": {"data": {"type": "array"}}},
        category="public_api",
    ),
    ToolListItem(
        name="doi_lookup",
        description="Resolve a DOI to structured citation metadata via Crossref.",
        input_schema={"type": "object", "properties": {"doi": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"title": {"type": "string"}}},
        category="public_api",
    ),
    ToolListItem(
        name="python_sandbox",
        description="Execute Python code in an isolated sandbox.",
        input_schema={"type": "object", "properties": {"code": {"type": "string"}, "timeout_seconds": {"type": "integer"}}},
        output_schema={"type": "object", "properties": {"stdout": {"type": "string"}}},
        category="local_execution",
    ),
    ToolListItem(
        name="pdf_ingest",
        description="Upload and ingest PDF documents for evidence extraction.",
        input_schema={"type": "object", "properties": {"file_path": {"type": "string"}, "url": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"text": {"type": "string"}, "page_count": {"type": "integer"}, "chunks": {"type": "array"}}},
        category="document",
    ),
    ToolListItem(
        name="pubmed_search",
        description="Search PubMed for biomedical and life science papers.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}},
        output_schema={"type": "object", "properties": {"data": {"type": "array"}}},
        category="public_api",
    ),
    ToolListItem(
        name="openalex_search",
        description="Search OpenAlex for academic works with citation counts and open access links.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}},
        output_schema={"type": "object", "properties": {"data": {"type": "array"}}},
        category="public_api",
    ),
    ToolListItem(
        name="crossref_search",
        description="Search CrossRef for scholarly works with DOIs and citation counts.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}},
        output_schema={"type": "object", "properties": {"data": {"type": "array"}}},
        category="public_api",
    ),
]


@router.get("/tools", response_model=ToolListResponse)
async def list_tools() -> ToolListResponse:
    """List all available tools with their schemas."""
    return ToolListResponse(tools=DEFAULT_TOOLS)
