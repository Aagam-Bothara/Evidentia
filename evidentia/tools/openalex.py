"""OpenAlex tool — searches OpenAlex for academic works."""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from evidentia.core.exceptions import ToolExecutionError
from evidentia.schemas.tool_io import OpenAlexSearchInput, OpenAlexSearchOutput, OpenAlexWork
from evidentia.tools.base import BaseTool, ToolMetadata

OPENALEX_API_URL = "https://api.openalex.org/works"


class OpenAlexTool(BaseTool):
    """Search OpenAlex for academic works across all disciplines."""

    metadata: ClassVar[ToolMetadata] = ToolMetadata(
        name="openalex_search",
        description="Search OpenAlex for academic works with citation counts and open access links.",
        category="public_api",
        input_schema=OpenAlexSearchInput.model_json_schema(),
        output_schema=OpenAlexSearchOutput.model_json_schema(),
        timeout_seconds=15,
        requires_auth=False,
    )

    def __init__(self, contact_email: str | None = None) -> None:
        self._contact_email = contact_email

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        params = OpenAlexSearchInput.model_validate(input_data)

        query_params: dict[str, Any] = {
            "search": params.query,
            "per-page": params.max_results,
        }
        if self._contact_email:
            query_params["mailto"] = self._contact_email
        if params.filter_open_access:
            query_params["filter"] = "open_access.is_oa:true"

        async with httpx.AsyncClient(timeout=self.metadata.timeout_seconds, follow_redirects=True) as client:
            try:
                resp = await client.get(OPENALEX_API_URL, params=query_params)
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
                    f"OpenAlex API returned {exc.response.status_code}: {exc}",
                    tool_name=self.metadata.name,
                    status_code=exc.response.status_code,
                    retry_after=retry_after,
                ) from exc
            except httpx.HTTPError as exc:
                raise ToolExecutionError(
                    f"OpenAlex API request failed: {exc}",
                    tool_name=self.metadata.name,
                ) from exc

        works = []
        for result in data.get("results", []):
            # Reconstruct abstract from inverted index
            abstract = self._reconstruct_abstract(result.get("abstract_inverted_index"))

            # Extract authors
            authors = []
            for authorship in result.get("authorships", []):
                author = authorship.get("author", {})
                name = author.get("display_name", "")
                if name:
                    authors.append(name)

            # DOI
            doi_raw = result.get("doi")
            doi = doi_raw.replace("https://doi.org/", "") if doi_raw else None

            # Open access URL
            oa = result.get("open_access", {})
            oa_url = oa.get("oa_url")

            works.append(
                OpenAlexWork(
                    work_id=result.get("id", ""),
                    title=result.get("title") or "",
                    abstract=abstract,
                    authors=authors,
                    published_date=result.get("publication_date", ""),
                    doi=doi,
                    cited_by_count=result.get("cited_by_count"),
                    open_access_url=oa_url,
                    url=result.get("id", ""),
                )
            )

        output = OpenAlexSearchOutput(data=works)
        return output.model_dump()

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
        """Reconstruct abstract text from OpenAlex's inverted index format.

        The inverted index maps words to their positions:
        {"The": [0], "cat": [1, 5], "sat": [2], ...}
        """
        if not inverted_index:
            return None

        # Build position -> word mapping
        words: dict[int, str] = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                words[pos] = word

        if not words:
            return None

        # Reconstruct text in order
        max_pos = max(words.keys())
        return " ".join(words.get(i, "") for i in range(max_pos + 1))
