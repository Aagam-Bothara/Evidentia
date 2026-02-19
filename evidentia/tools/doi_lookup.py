"""DOI / Crossref tool — resolves DOIs to structured citation metadata."""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from evidentia.core.exceptions import ToolExecutionError
from evidentia.schemas.tool_io import DOILookupInput, DOILookupOutput
from evidentia.tools.base import BaseTool, ToolMetadata

CROSSREF_API_URL = "https://api.crossref.org/works"


class DOILookupTool(BaseTool):
    """Resolve a DOI to structured citation metadata via Crossref."""

    metadata: ClassVar[ToolMetadata] = ToolMetadata(
        name="doi_lookup",
        description="Resolve a DOI to structured metadata (title, authors, abstract, journal).",
        category="public_api",
        input_schema=DOILookupInput.model_json_schema(),
        output_schema=DOILookupOutput.model_json_schema(),
        timeout_seconds=10,
        requires_auth=False,
    )

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        params = DOILookupInput.model_validate(input_data)

        async with httpx.AsyncClient(timeout=self.metadata.timeout_seconds, follow_redirects=True) as client:
            try:
                resp = await client.get(f"{CROSSREF_API_URL}/{params.doi}")
                resp.raise_for_status()
                data = resp.json().get("message", {})
            except httpx.HTTPStatusError as exc:
                retry_after = None
                if ra := exc.response.headers.get("Retry-After"):
                    try:
                        retry_after = float(ra)
                    except ValueError:
                        pass
                raise ToolExecutionError(
                    f"Crossref DOI lookup returned {exc.response.status_code}: {exc}",
                    tool_name=self.metadata.name,
                    status_code=exc.response.status_code,
                    retry_after=retry_after,
                ) from exc
            except httpx.HTTPError as exc:
                raise ToolExecutionError(
                    f"Crossref DOI lookup failed: {exc}",
                    tool_name=self.metadata.name,
                ) from exc

        authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in data.get("author", [])]

        # Extract publication date
        date_parts = data.get("published-print", data.get("published-online", {}))
        date_str = ""
        if parts := date_parts.get("date-parts", [[]])[0]:
            date_str = "-".join(str(p) for p in parts)

        output = DOILookupOutput(
            success=True,
            title=data.get("title", [""])[0] if data.get("title") else "",
            authors=authors,
            abstract=data.get("abstract", ""),
            journal=data.get("container-title", [""])[0] if data.get("container-title") else "",
            published_date=date_str,
            url=data.get("URL", ""),
            citation_count=data.get("is-referenced-by-count"),
        )
        return output.model_dump()
