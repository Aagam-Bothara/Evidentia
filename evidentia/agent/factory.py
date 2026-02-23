"""Agent factory — assembles the full agent from config."""

from __future__ import annotations

from evidentia.agent.agent import EvidentiAgent
from evidentia.core.config import LLMProvider, Settings, get_settings
from evidentia.core.llm import AnthropicLLM, OpenAILLM, create_llm
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


# ── Per-user key resolution (BYO-API vault) ─────────────────────


async def _resolve_key(
    vault, user_id: str, service: str, server_fallback: str | None
) -> str | None:
    """Try user's vault key first, fall back to server config."""
    try:
        connector = f"user:{user_id}"
        return await vault.get_credential(connector, service)
    except Exception:
        return server_fallback


def _create_llm_with_key(settings: Settings, openai_key: str | None, anthropic_key: str | None):
    """Create an LLM client using resolved per-user keys."""
    if settings.llm_provider == LLMProvider.OPENAI and openai_key:
        return OpenAILLM(api_key=openai_key)
    elif settings.llm_provider == LLMProvider.ANTHROPIC and anthropic_key:
        return AnthropicLLM(api_key=anthropic_key)
    return create_llm(settings)


async def _build_tool_registry_for_user(
    settings: Settings, user_id: str, vault
) -> ToolRegistry:
    """Build a tool registry using per-user keys with server fallback."""
    registry = ToolRegistry()

    serpapi_key = await _resolve_key(vault, user_id, "serpapi", settings.serpapi_key)
    s2_key = await _resolve_key(vault, user_id, "semantic_scholar", settings.semantic_scholar_api_key)
    ncbi_key = await _resolve_key(vault, user_id, "ncbi", settings.ncbi_api_key)
    openalex_email = await _resolve_key(vault, user_id, "openalex", settings.openalex_email)

    registry.register(ArxivTool())
    registry.register(DOILookupTool())
    registry.register(PythonSandboxTool())
    registry.register(CrossRefSearchTool())
    registry.register(OpenAlexTool(contact_email=openalex_email))

    if s2_key:
        registry.register(SemanticScholarTool(api_key=s2_key))
    else:
        registry.register(SemanticScholarTool())

    registry.register(PubMedTool(api_key=ncbi_key))

    if serpapi_key:
        registry.register(WebSearchTool(api_key=serpapi_key))

    return registry


async def build_agent_for_user(
    user_id: str, settings: Settings | None = None
) -> EvidentiAgent:
    """Create an agent with per-user API keys (vault first, server fallback)."""
    from evidentia.api.routes.keys import _get_vault

    if settings is None:
        settings = get_settings()

    vault = _get_vault()
    openai_key = await _resolve_key(vault, user_id, "openai", settings.openai_api_key)
    anthropic_key = await _resolve_key(vault, user_id, "anthropic", settings.anthropic_api_key)

    llm = _create_llm_with_key(settings, openai_key, anthropic_key)
    registry = await _build_tool_registry_for_user(settings, user_id, vault)

    return EvidentiAgent(
        llm=llm,
        tool_registry=registry,
        max_iterations=5,
        max_tool_calls=settings.max_tool_calls_per_run,
        min_evidence_per_question=2,
    )


async def build_review_engine_for_user(
    user_id: str, settings: Settings | None = None
):
    """Create a SystematicReviewEngine with per-user API keys."""
    from evidentia.api.routes.keys import _get_vault
    from evidentia.review.engine import SystematicReviewEngine

    if settings is None:
        settings = get_settings()

    vault = _get_vault()
    openai_key = await _resolve_key(vault, user_id, "openai", settings.openai_api_key)
    anthropic_key = await _resolve_key(vault, user_id, "anthropic", settings.anthropic_api_key)

    llm = _create_llm_with_key(settings, openai_key, anthropic_key)
    registry = await _build_tool_registry_for_user(settings, user_id, vault)

    return SystematicReviewEngine(llm=llm, tool_registry=registry)
