"""Tests for the PubMed tool."""

import httpx
import pytest

from evidentia.tools.pubmed import PubMedTool

# Realistic PubMed esearch JSON response
ESEARCH_RESPONSE = {
    "esearchresult": {
        "count": "2",
        "retmax": "2",
        "idlist": ["38000001", "38000002"],
    }
}

# Realistic PubMed efetch XML response
EFETCH_XML = """\
<?xml version="1.0" ?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>38000001</PMID>
      <Article>
        <ArticleTitle>CRISPR-Cas9 genome editing in human cells</ArticleTitle>
        <Abstract>
          <AbstractText>We demonstrate efficient genome editing using CRISPR-Cas9 in human cell lines.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Zhang</LastName><ForeName>Feng</ForeName></Author>
          <Author><LastName>Doudna</LastName><ForeName>Jennifer</ForeName></Author>
        </AuthorList>
        <Journal><Title>Nature</Title></Journal>
        <PubDate><Year>2024</Year><Month>Jan</Month></PubDate>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1038/s41586-024-00001</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>38000002</PMID>
      <Article>
        <ArticleTitle>RNA therapeutics for genetic diseases</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">RNA-based therapies are emerging.</AbstractText>
          <AbstractText Label="RESULTS">We show improved delivery mechanisms.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Weissman</LastName><ForeName>Drew</ForeName></Author>
        </AuthorList>
        <Journal><Title>Science</Title></Journal>
        <PubDate><Year>2024</Year></PubDate>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">38000002</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def _make_response(status_code: int, content: str | dict, headers: dict | None = None) -> httpx.Response:
    """Build a mock httpx.Response."""
    if isinstance(content, dict):
        import json

        raw_content = json.dumps(content).encode()
        content_type = "application/json"
    else:
        raw_content = content.encode()
        content_type = "text/xml"

    resp = httpx.Response(
        status_code=status_code,
        content=raw_content,
        headers=headers or {"content-type": content_type},
        request=httpx.Request("GET", "https://eutils.ncbi.nlm.nih.gov/test"),
    )
    return resp


@pytest.mark.asyncio
async def test_pubmed_search_success(monkeypatch):
    """Test successful PubMed search with two articles."""
    call_count = 0

    async def mock_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if "esearch" in url:
            return _make_response(200, ESEARCH_RESPONSE)
        else:
            return _make_response(200, EFETCH_XML)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = PubMedTool()
    result = await tool.execute({"query": "CRISPR genome editing", "max_results": 2})

    assert result["success"] is True
    assert len(result["data"]) == 2
    assert result["data"][0]["pmid"] == "38000001"
    assert result["data"][0]["title"] == "CRISPR-Cas9 genome editing in human cells"
    assert "Zhang, Feng" in result["data"][0]["authors"]
    assert result["data"][0]["doi"] == "10.1038/s41586-024-00001"
    assert "pubmed.ncbi.nlm.nih.gov" in result["data"][0]["url"]


@pytest.mark.asyncio
async def test_pubmed_structured_abstract(monkeypatch):
    """Test that structured abstracts (with labels) are parsed correctly."""

    async def mock_get(self, url, **kwargs):
        if "esearch" in url:
            return _make_response(200, ESEARCH_RESPONSE)
        else:
            return _make_response(200, EFETCH_XML)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = PubMedTool()
    result = await tool.execute({"query": "RNA therapeutics"})

    article2 = result["data"][1]
    assert "BACKGROUND:" in article2["abstract"]
    assert "RESULTS:" in article2["abstract"]


@pytest.mark.asyncio
async def test_pubmed_empty_results(monkeypatch):
    """Test that empty search results return empty list."""

    async def mock_get(self, url, **kwargs):
        return _make_response(200, {"esearchresult": {"count": "0", "idlist": []}})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = PubMedTool()
    result = await tool.execute({"query": "xyznonexistent123"})
    assert result["data"] == []


@pytest.mark.asyncio
async def test_pubmed_api_key_passed(monkeypatch):
    """Test that API key is included in requests when provided."""
    captured_params = {}

    async def mock_get(self, url, **kwargs):
        captured_params.update(kwargs.get("params", {}))
        if "esearch" in url:
            return _make_response(200, {"esearchresult": {"count": "0", "idlist": []}})
        return _make_response(200, EFETCH_XML)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = PubMedTool(api_key="test-key-123")
    await tool.execute({"query": "test"})
    assert captured_params.get("api_key") == "test-key-123"


@pytest.mark.asyncio
async def test_pubmed_rate_limit_error(monkeypatch):
    """Test that 429 errors propagate with status code and retry_after."""

    async def mock_get(self, url, **kwargs):
        resp = _make_response(429, "Rate limited", headers={"Retry-After": "5"})
        raise httpx.HTTPStatusError("429", request=resp.request, response=resp)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    from evidentia.core.exceptions import ToolExecutionError

    tool = PubMedTool()
    with pytest.raises(ToolExecutionError) as exc_info:
        await tool.execute({"query": "test"})

    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_after == 5.0


@pytest.mark.asyncio
async def test_pubmed_input_validation():
    """Test input validation rejects empty queries."""
    tool = PubMedTool()
    with pytest.raises(Exception):
        await tool.execute({"query": ""})


@pytest.mark.asyncio
async def test_pubmed_date_range(monkeypatch):
    """Test that date range parameter is passed to API."""
    captured_params = {}

    async def mock_get(self, url, **kwargs):
        captured_params.update(kwargs.get("params", {}))
        return _make_response(200, {"esearchresult": {"count": "0", "idlist": []}})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    tool = PubMedTool()
    await tool.execute({"query": "CRISPR", "date_range": "2023/01/01:2024/12/31"})
    assert captured_params.get("mindate") == "2023/01/01"
    assert captured_params.get("maxdate") == "2024/12/31"
