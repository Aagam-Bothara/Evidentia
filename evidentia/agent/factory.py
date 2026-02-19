"""Agent factory — assembles the full agent from config."""

from __future__ import annotations

from evidentia.agent.agent import EvidentiAgent
from evidentia.core.config import Settings, get_settings
from evidentia.core.llm import create_llm
from evidentia.tools.arxiv import ArxivTool
from evidentia.tools.base import ToolRegistry
from evidentia.tools.crossref_search import CrossRefSearchTool
from evidentia.tools.doi_lookup import DOILookupTool
from evidentia.tools.openalex import OpenAlexTool
from evidentia.tools.pubmed import PubMedTool
from evidentia.tools.python_sandbox import PythonSandboxTool
from evidentia.tools.semantic_scholar import SemanticScholarTool
from evidentia.tools.web_search import WebSearchTool


def build_tool_registry(settings: Settings) -> ToolRegistry:
    """Register all available tools based on config."""
    registry = ToolRegistry()

    # Always-available tools (no API key required)
    registry.register(ArxivTool())
    registry.register(DOILookupTool())
    registry.register(PythonSandboxTool())
    registry.register(CrossRefSearchTool())
    registry.register(OpenAlexTool(contact_email=settings.openalex_email))

    # Semantic Scholar works without an API key (rate-limited)
    if settings.semantic_scholar_api_key:
        registry.register(SemanticScholarTool(api_key=settings.semantic_scholar_api_key))
    else:
        registry.register(SemanticScholarTool())

    # PubMed works without an API key (3 req/s), optional key for 10 req/s
    registry.register(PubMedTool(api_key=settings.ncbi_api_key))

    # Optional tools (require BYO-API keys)
    if settings.serpapi_key:
        registry.register(WebSearchTool(api_key=settings.serpapi_key))

    return registry


def build_review_engine(settings: Settings | None = None):
    """Create a SystematicReviewEngine from application settings."""
    from evidentia.review.engine import SystematicReviewEngine

    if settings is None:
        settings = get_settings()
    llm = create_llm(settings)
    registry = build_tool_registry(settings)
    return SystematicReviewEngine(llm=llm, tool_registry=registry)


def build_agent(settings: Settings | None = None) -> EvidentiAgent:
    """Create a fully-wired EvidentiAgent from application settings.

    This is the main entry point. It:
    1. Loads config
    2. Creates the LLM client (BYO-API)
    3. Registers available tools
    4. Returns a ready-to-use agent
    """
    if settings is None:
        settings = get_settings()

    llm = create_llm(settings)
    registry = build_tool_registry(settings)

    return EvidentiAgent(
        llm=llm,
        tool_registry=registry,
        max_iterations=5,
        max_tool_calls=settings.max_tool_calls_per_run,
        min_evidence_per_question=2,
    )
