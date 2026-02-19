"""ArXiv tool — searches arXiv for academic papers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, ClassVar

import httpx

from evidentia.core.exceptions import ToolExecutionError
from evidentia.schemas.tool_io import ArxivPaper, ArxivSearchInput, ArxivSearchOutput
from evidentia.tools.base import BaseTool, ToolMetadata

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


class ArxivTool(BaseTool):
    """Search arXiv for academic papers by query."""

    metadata: ClassVar[ToolMetadata] = ToolMetadata(
        name="arxiv_search",
        description="Search arXiv for academic papers matching a query.",
        category="public_api",
        input_schema=ArxivSearchInput.model_json_schema(),
        output_schema=ArxivSearchOutput.model_json_schema(),
        timeout_seconds=20,
        requires_auth=False,
    )

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        params = ArxivSearchInput.model_validate(input_data)

        sort_map = {
            "relevance": "relevance",
            "date": "lastUpdatedDate",
            "submitted": "submittedDate",
        }

        async with httpx.AsyncClient(timeout=self.metadata.timeout_seconds, follow_redirects=True) as client:
            try:
                resp = await client.get(
                    ARXIV_API_URL,
                    params={
                        "search_query": f"all:{params.query}",
                        "start": 0,
                        "max_results": params.max_results,
                        "sortBy": sort_map.get(params.sort_by, "relevance"),
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                retry_after = None
                if ra := exc.response.headers.get("Retry-After"):
                    try:
                        retry_after = float(ra)
                    except ValueError:
                        pass
                raise ToolExecutionError(
                    f"ArXiv API returned {exc.response.status_code}: {exc}",
                    tool_name=self.metadata.name,
                    status_code=exc.response.status_code,
                    retry_after=retry_after,
                ) from exc
            except httpx.HTTPError as exc:
                raise ToolExecutionError(
                    f"ArXiv API request failed: {exc}",
                    tool_name=self.metadata.name,
                ) from exc

        papers = self._parse_response(resp.text)
        output = ArxivSearchOutput(data=papers)
        return output.model_dump()

    def _parse_response(self, xml_text: str) -> list[ArxivPaper]:
        root = ET.fromstring(xml_text)
        papers: list[ArxivPaper] = []

        for entry in root.findall(f"{ATOM_NS}entry"):
            arxiv_id = (entry.findtext(f"{ATOM_NS}id") or "").split("/abs/")[-1]
            title = (entry.findtext(f"{ATOM_NS}title") or "").strip().replace("\n", " ")
            abstract = (entry.findtext(f"{ATOM_NS}summary") or "").strip().replace("\n", " ")
            published = entry.findtext(f"{ATOM_NS}published") or ""

            authors = [(a.findtext(f"{ATOM_NS}name") or "").strip() for a in entry.findall(f"{ATOM_NS}author")]

            # Extract DOI if present
            doi = None
            for link in entry.findall(f"{ATOM_NS}link"):
                if link.get("title") == "doi":
                    doi = link.get("href")

            categories = [c.get("term", "") for c in entry.findall("{http://arxiv.org/schemas/atom}primary_category")]

            url = f"https://arxiv.org/abs/{arxiv_id}"

            papers.append(
                ArxivPaper(
                    arxiv_id=arxiv_id,
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    published=published,
                    url=url,
                    doi=doi,
                    categories=categories,
                )
            )

        return papers
