"""CrossRef Search tool — searches CrossRef for scholarly works by keyword."""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from evidentia.core.exceptions import ToolExecutionError
from evidentia.schemas.tool_io import CrossRefSearchInput, CrossRefSearchOutput, CrossRefWork
from evidentia.tools.base import BaseTool, ToolMetadata

CROSSREF_API_URL = "https://api.crossref.org/works"


class CrossRefSearchTool(BaseTool):
    """Search CrossRef for scholarly works by keyword query."""

    metadata: ClassVar[ToolMetadata] = ToolMetadata(
        name="crossref_search",
        description="Search CrossRef for scholarly works with DOIs, citation counts, and metadata.",
        category="public_api",
        input_schema=CrossRefSearchInput.model_json_schema(),
        output_schema=CrossRefSearchOutput.model_json_schema(),
        timeout_seconds=15,
        requires_auth=False,
    )

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        params = CrossRefSearchInput.model_validate(input_data)

        async with httpx.AsyncClient(timeout=self.metadata.timeout_seconds, follow_redirects=True) as client:
            try:
                resp = await client.get(
                    CROSSREF_API_URL,
                    params={
                        "query": params.query,
                        "rows": params.max_results,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as exc:
                retry_after = None
                if ra := exc.response.headers.get("Retry-After"):
                    try:
                        retry_after = float(ra)
                    except ValueError:
                        pass
                raise ToolExecutionError(
                    f"CrossRef search returned {exc.response.status_code}: {exc}",
                    tool_name=self.metadata.name,
                    status_code=exc.response.status_code,
                    retry_after=retry_after,
                ) from exc
            except httpx.HTTPError as exc:
                raise ToolExecutionError(
                    f"CrossRef search request failed: {exc}",
                    tool_name=self.metadata.name,
                ) from exc

        works = []
        for item in data.get("message", {}).get("items", []):
            # Authors
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in item.get("author", [])
            ]

            # Publication date
            date_parts = item.get("published-print", item.get("published-online", {}))
            date_str = ""
            if parts := date_parts.get("date-parts", [[]])[0]:
                date_str = "-".join(str(p) for p in parts)

            # Journal
            journal = ""
            container = item.get("container-title", [])
            if container:
                journal = container[0]

            # Title
            title = ""
            title_list = item.get("title", [])
            if title_list:
                title = title_list[0]

            doi = item.get("DOI", "")
            works.append(CrossRefWork(
                doi=doi,
                title=title,
                authors=authors,
                journal=journal,
                published_date=date_str,
                citation_count=item.get("is-referenced-by-count"),
                url=item.get("URL", f"https://doi.org/{doi}" if doi else ""),
            ))

        output = CrossRefSearchOutput(data=works)
        return output.model_dump()
