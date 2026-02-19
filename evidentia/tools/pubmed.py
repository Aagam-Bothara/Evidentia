"""PubMed tool — searches NCBI PubMed for biomedical literature."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, ClassVar

import httpx

from evidentia.core.exceptions import ToolExecutionError
from evidentia.schemas.tool_io import PubMedArticle, PubMedSearchInput, PubMedSearchOutput
from evidentia.tools.base import BaseTool, ToolMetadata

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedTool(BaseTool):
    """Search PubMed for biomedical and life science articles."""

    metadata: ClassVar[ToolMetadata] = ToolMetadata(
        name="pubmed_search",
        description="Search PubMed for biomedical and life science papers.",
        category="public_api",
        input_schema=PubMedSearchInput.model_json_schema(),
        output_schema=PubMedSearchOutput.model_json_schema(),
        timeout_seconds=20,
        requires_auth=False,
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        params = PubMedSearchInput.model_validate(input_data)

        headers: dict[str, str] = {}
        search_params: dict[str, Any] = {
            "db": "pubmed",
            "term": params.query,
            "retmax": params.max_results,
            "retmode": "json",
        }
        if self._api_key:
            search_params["api_key"] = self._api_key
        if params.date_range:
            parts = params.date_range.split(":")
            if len(parts) == 2:
                search_params["mindate"] = parts[0]
                search_params["maxdate"] = parts[1]
                search_params["datetype"] = "pdat"

        async with httpx.AsyncClient(timeout=self.metadata.timeout_seconds, follow_redirects=True) as client:
            # Step 1: esearch to get PMIDs
            try:
                resp = await client.get(f"{EUTILS_BASE}/esearch.fcgi", params=search_params)
                resp.raise_for_status()
                search_data = resp.json()
            except httpx.HTTPStatusError as exc:
                retry_after = None
                if ra := exc.response.headers.get("Retry-After"):
                    try:
                        retry_after = float(ra)
                    except ValueError:
                        pass
                raise ToolExecutionError(
                    f"PubMed search returned {exc.response.status_code}: {exc}",
                    tool_name=self.metadata.name,
                    status_code=exc.response.status_code,
                    retry_after=retry_after,
                ) from exc
            except httpx.HTTPError as exc:
                raise ToolExecutionError(
                    f"PubMed search request failed: {exc}",
                    tool_name=self.metadata.name,
                ) from exc

            pmids = search_data.get("esearchresult", {}).get("idlist", [])
            if not pmids:
                return PubMedSearchOutput(data=[]).model_dump()

            # Step 2: efetch to get article details
            fetch_params: dict[str, Any] = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "xml",
                "rettype": "abstract",
            }
            if self._api_key:
                fetch_params["api_key"] = self._api_key

            try:
                resp = await client.get(f"{EUTILS_BASE}/efetch.fcgi", params=fetch_params)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                retry_after = None
                if ra := exc.response.headers.get("Retry-After"):
                    try:
                        retry_after = float(ra)
                    except ValueError:
                        pass
                raise ToolExecutionError(
                    f"PubMed fetch returned {exc.response.status_code}: {exc}",
                    tool_name=self.metadata.name,
                    status_code=exc.response.status_code,
                    retry_after=retry_after,
                ) from exc
            except httpx.HTTPError as exc:
                raise ToolExecutionError(
                    f"PubMed fetch request failed: {exc}",
                    tool_name=self.metadata.name,
                ) from exc

        articles = self._parse_xml(resp.text)
        output = PubMedSearchOutput(data=articles)
        return output.model_dump()

    @staticmethod
    def _parse_xml(xml_text: str) -> list[PubMedArticle]:
        """Parse PubMed efetch XML into article objects."""
        articles: list[PubMedArticle] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return articles

        for article_el in root.findall(".//PubmedArticle"):
            medline = article_el.find(".//MedlineCitation")
            if medline is None:
                continue

            pmid_el = medline.find("PMID")
            pmid = pmid_el.text if pmid_el is not None else ""

            art = medline.find("Article")
            if art is None:
                continue

            title_el = art.find("ArticleTitle")
            title = title_el.text if title_el is not None else ""

            # Abstract may have multiple AbstractText elements
            abstract_parts = []
            abstract_el = art.find("Abstract")
            if abstract_el is not None:
                for at in abstract_el.findall("AbstractText"):
                    if at.text:
                        label = at.get("Label", "")
                        if label:
                            abstract_parts.append(f"{label}: {at.text}")
                        else:
                            abstract_parts.append(at.text)
            abstract = " ".join(abstract_parts) if abstract_parts else None

            # Authors
            authors = []
            author_list = art.find("AuthorList")
            if author_list is not None:
                for author in author_list.findall("Author"):
                    last = author.findtext("LastName") or ""
                    first = author.findtext("ForeName") or ""
                    if last:
                        authors.append(f"{last}, {first}".strip(", "))

            # Published date
            pub_date = art.find(".//PubDate")
            date_str = ""
            if pub_date is not None:
                year = pub_date.findtext("Year") or ""
                month = pub_date.findtext("Month") or ""
                day = pub_date.findtext("Day") or ""
                date_str = "-".join(p for p in [year, month, day] if p)

            # DOI
            doi = None
            for eid in article_el.findall(".//ArticleId"):
                if eid.get("IdType") == "doi":
                    doi = eid.text
                    break

            articles.append(PubMedArticle(
                pmid=pmid,
                title=title or "",
                abstract=abstract,
                authors=authors,
                published_date=date_str,
                doi=doi,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            ))

        return articles
