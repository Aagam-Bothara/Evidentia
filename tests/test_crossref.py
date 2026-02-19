"""Tests for the CrossRef Search tool."""

import json

import httpx
import pytest

from evidentia.tools.crossref_search import CrossRefSearchTool

# Realistic CrossRef API response
CROSSREF_RESPONSE = {
    "status": "ok",
    "message": {
        "total-results": 2,
        "items": [
            {
                "DOI": "10.1038/s41586-024-00001",
                "title": ["Deep learning for protein structure prediction"],
                "author": [
                    {"given": "John", "family": "Jumper"},
                    {"given": "Richard", "family": "Evans"},
                ],
                "container-title": ["Nature"],
                "published-print": {"date-parts": [[2024, 1, 15]]},
                "is-referenced-by-count": 5000,
                "URL": "https://doi.org/10.1038/s41586-024-00001",
            },
            {
                "DOI": "10.1126/science.abc1234",
                "title": ["mRNA vaccines: a new era"],
                "author": [
                    {"given": "Katalin", "family": "Kariko"},
                ],
                "container-title": ["Science"],
                "published-online": {"date-parts": [[2023, 6]]},
                "is-referenced-by-count": 1200,
                "URL": "https://doi.org/10.1126/science.abc1234",
            },
        ],
    },
}


def _make_response(status_code: int, data: dict, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(data).encode(),
        headers=headers or {"content-type": "application/json"},
        request=httpx.Request("GET", "https://api.crossref.org/works"),
    )


@pytest.mark.asyncio
async def test_crossref_search_success(monkeypatch):
    """Test successful CrossRef search."""

    async def mock_get(self, url, **kwargs):
        return _make_response(200, CROSSREF_RESPONSE)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = CrossRefSearchTool()
    result = await tool.execute({"query": "protein structure prediction"})

    assert result["success"] is True
    assert len(result["data"]) == 2

    work1 = result["data"][0]
    assert work1["doi"] == "10.1038/s41586-024-00001"
    assert work1["title"] == "Deep learning for protein structure prediction"
    assert "John Jumper" in work1["authors"]
    assert work1["journal"] == "Nature"
    assert work1["published_date"] == "2024-1-15"
    assert work1["citation_count"] == 5000


@pytest.mark.asyncio
async def test_crossref_online_date_fallback(monkeypatch):
    """Test that published-online is used when published-print is missing."""

    async def mock_get(self, url, **kwargs):
        return _make_response(200, CROSSREF_RESPONSE)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = CrossRefSearchTool()
    result = await tool.execute({"query": "mRNA vaccines"})

    work2 = result["data"][1]
    assert work2["published_date"] == "2023-6"


@pytest.mark.asyncio
async def test_crossref_empty_results(monkeypatch):
    """Test empty search results."""

    async def mock_get(self, url, **kwargs):
        return _make_response(200, {"status": "ok", "message": {"items": []}})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = CrossRefSearchTool()
    result = await tool.execute({"query": "xyznonexistent"})
    assert result["data"] == []


@pytest.mark.asyncio
async def test_crossref_max_results_param(monkeypatch):
    """Test that max_results is passed as rows parameter."""
    captured_params = {}

    async def mock_get(self, url, **kwargs):
        captured_params.update(kwargs.get("params", {}))
        return _make_response(200, {"status": "ok", "message": {"items": []}})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = CrossRefSearchTool()
    await tool.execute({"query": "test", "max_results": 25})
    assert captured_params.get("rows") == 25


@pytest.mark.asyncio
async def test_crossref_rate_limit_error(monkeypatch):
    """Test 429 error propagation with status code."""

    async def mock_get(self, url, **kwargs):
        resp = _make_response(429, {"error": "rate limited"}, headers={"Retry-After": "3"})
        raise httpx.HTTPStatusError("429", request=resp.request, response=resp)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    from evidentia.core.exceptions import ToolExecutionError

    tool = CrossRefSearchTool()
    with pytest.raises(ToolExecutionError) as exc_info:
        await tool.execute({"query": "test"})

    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_after == 3.0


@pytest.mark.asyncio
async def test_crossref_server_error(monkeypatch):
    """Test 500 error propagation."""

    async def mock_get(self, url, **kwargs):
        resp = _make_response(500, {"error": "internal server error"})
        raise httpx.HTTPStatusError("500", request=resp.request, response=resp)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    from evidentia.core.exceptions import ToolExecutionError

    tool = CrossRefSearchTool()
    with pytest.raises(ToolExecutionError) as exc_info:
        await tool.execute({"query": "test"})

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_crossref_network_error(monkeypatch):
    """Test network error propagation."""

    async def mock_get(self, url, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    from evidentia.core.exceptions import ToolExecutionError

    tool = CrossRefSearchTool()
    with pytest.raises(ToolExecutionError) as exc_info:
        await tool.execute({"query": "test"})

    assert exc_info.value.status_code is None


@pytest.mark.asyncio
async def test_crossref_missing_fields(monkeypatch):
    """Test handling of items with missing optional fields."""
    sparse_response = {
        "status": "ok",
        "message": {
            "items": [
                {
                    "DOI": "10.1234/sparse",
                    "title": [],
                    "author": [],
                    "container-title": [],
                },
            ],
        },
    }

    async def mock_get(self, url, **kwargs):
        return _make_response(200, sparse_response)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = CrossRefSearchTool()
    result = await tool.execute({"query": "test"})
    assert len(result["data"]) == 1
    assert result["data"][0]["doi"] == "10.1234/sparse"
    assert result["data"][0]["title"] == ""
    assert result["data"][0]["authors"] == []
