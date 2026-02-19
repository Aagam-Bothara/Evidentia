"""Tests for the OpenAlex tool."""

import json

import httpx
import pytest

from evidentia.tools.openalex import OpenAlexTool

# Realistic OpenAlex API response
OPENALEX_RESPONSE = {
    "meta": {"count": 2, "per_page": 10},
    "results": [
        {
            "id": "https://openalex.org/W2741809807",
            "title": "Attention Is All You Need",
            "abstract_inverted_index": {
                "The": [0, 9],
                "dominant": [1],
                "sequence": [2],
                "transduction": [3],
                "models": [4],
                "are": [5],
                "based": [6],
                "on": [7],
                "attention.": [8],
                "Transformer": [10],
                "uses": [11],
                "self-attention.": [12],
            },
            "authorships": [
                {"author": {"display_name": "Ashish Vaswani"}},
                {"author": {"display_name": "Noam Shazeer"}},
            ],
            "publication_date": "2017-06-12",
            "doi": "https://doi.org/10.48550/arXiv.1706.03762",
            "cited_by_count": 120000,
            "open_access": {"is_oa": True, "oa_url": "https://arxiv.org/pdf/1706.03762"},
        },
        {
            "id": "https://openalex.org/W1234567890",
            "title": "BERT: Pre-training Transformers",
            "abstract_inverted_index": None,
            "authorships": [
                {"author": {"display_name": "Jacob Devlin"}},
            ],
            "publication_date": "2018-10-11",
            "doi": None,
            "cited_by_count": 80000,
            "open_access": {"is_oa": False, "oa_url": None},
        },
    ],
}


def _make_response(status_code: int, data: dict, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(data).encode(),
        headers=headers or {"content-type": "application/json"},
        request=httpx.Request("GET", "https://api.openalex.org/works"),
    )


@pytest.mark.asyncio
async def test_openalex_search_success(monkeypatch):
    """Test successful OpenAlex search with abstract reconstruction."""
    async def mock_get(self, url, **kwargs):
        return _make_response(200, OPENALEX_RESPONSE)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = OpenAlexTool()
    result = await tool.execute({"query": "transformer attention"})

    assert result["success"] is True
    assert len(result["data"]) == 2

    work1 = result["data"][0]
    assert work1["title"] == "Attention Is All You Need"
    assert "Ashish Vaswani" in work1["authors"]
    assert work1["cited_by_count"] == 120000
    assert work1["doi"] == "10.48550/arXiv.1706.03762"
    assert work1["open_access_url"] == "https://arxiv.org/pdf/1706.03762"

    # Abstract should be reconstructed from inverted index
    assert work1["abstract"] is not None
    assert "dominant" in work1["abstract"]
    assert "attention" in work1["abstract"].lower()


@pytest.mark.asyncio
async def test_openalex_null_abstract(monkeypatch):
    """Test that null abstract_inverted_index returns None."""
    async def mock_get(self, url, **kwargs):
        return _make_response(200, OPENALEX_RESPONSE)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = OpenAlexTool()
    result = await tool.execute({"query": "BERT"})

    work2 = result["data"][1]
    assert work2["abstract"] is None


@pytest.mark.asyncio
async def test_openalex_contact_email(monkeypatch):
    """Test that contact email is passed for polite pool."""
    captured_params = {}

    async def mock_get(self, url, **kwargs):
        captured_params.update(kwargs.get("params", {}))
        return _make_response(200, {"meta": {}, "results": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = OpenAlexTool(contact_email="test@example.com")
    await tool.execute({"query": "test"})
    assert captured_params.get("mailto") == "test@example.com"


@pytest.mark.asyncio
async def test_openalex_open_access_filter(monkeypatch):
    """Test that open access filter is applied."""
    captured_params = {}

    async def mock_get(self, url, **kwargs):
        captured_params.update(kwargs.get("params", {}))
        return _make_response(200, {"meta": {}, "results": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = OpenAlexTool()
    await tool.execute({"query": "test", "filter_open_access": True})
    assert "open_access.is_oa:true" in captured_params.get("filter", "")


@pytest.mark.asyncio
async def test_openalex_empty_results(monkeypatch):
    """Test empty search results."""
    async def mock_get(self, url, **kwargs):
        return _make_response(200, {"meta": {"count": 0}, "results": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = OpenAlexTool()
    result = await tool.execute({"query": "xyznonexistent"})
    assert result["data"] == []


@pytest.mark.asyncio
async def test_openalex_rate_limit_error(monkeypatch):
    """Test 429 error propagation."""
    async def mock_get(self, url, **kwargs):
        resp = _make_response(429, {"error": "rate limited"}, headers={"Retry-After": "10"})
        raise httpx.HTTPStatusError("429", request=resp.request, response=resp)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    from evidentia.core.exceptions import ToolExecutionError
    tool = OpenAlexTool()
    with pytest.raises(ToolExecutionError) as exc_info:
        await tool.execute({"query": "test"})

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_openalex_abstract_reconstruction():
    """Test the abstract reconstruction helper directly."""
    inverted_index = {
        "Hello": [0],
        "world": [1],
        "this": [2],
        "is": [3],
        "a": [4],
        "test": [5],
    }
    result = OpenAlexTool._reconstruct_abstract(inverted_index)
    assert result == "Hello world this is a test"


@pytest.mark.asyncio
async def test_openalex_abstract_reconstruction_empty():
    """Test abstract reconstruction with empty/None input."""
    assert OpenAlexTool._reconstruct_abstract(None) is None
    assert OpenAlexTool._reconstruct_abstract({}) is None
