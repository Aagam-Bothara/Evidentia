"""Web Search tool — searches the web via SerpAPI or similar providers."""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from evidentia.core.exceptions import ToolExecutionError
from evidentia.schemas.tool_io import WebSearchInput, WebSearchOutput, WebSearchResult
from evidentia.tools.base import BaseTool, ToolMetadata


class WebSearchTool(BaseTool):
    """Search the web for relevant results."""

    metadata: ClassVar[ToolMetadata] = ToolMetadata(
        name="web_search",
        description="Search the web for relevant pages, articles, and documents.",
        category="public_api",
        input_schema=WebSearchInput.model_json_schema(),
        output_schema=WebSearchOutput.model_json_schema(),
        timeout_seconds=15,
        requires_auth=True,
    )

    def __init__(self, api_key: str, base_url: str = "https://serpapi.com/search") -> None:
        self._api_key = api_key
        self._base_url = base_url

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        params = WebSearchInput.model_validate(input_data)

        async with httpx.AsyncClient(timeout=self.metadata.timeout_seconds, follow_redirects=True) as client:
            try:
                resp = await client.get(
                    self._base_url,
                    params={
                        "q": params.query,
                        "num": params.max_results,
                        "api_key": self._api_key,
                        "engine": "google",
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
                    f"Web search returned {exc.response.status_code}: {exc}",
                    tool_name=self.metadata.name,
                    status_code=exc.response.status_code,
                    retry_after=retry_after,
                ) from exc
            except httpx.HTTPError as exc:
                raise ToolExecutionError(
                    f"Web search request failed: {exc}",
                    tool_name=self.metadata.name,
                ) from exc

        results = [
            WebSearchResult(
                title=r.get("title", ""),
                url=r.get("link", ""),
                snippet=r.get("snippet", ""),
            )
            for r in data.get("organic_results", [])
        ]

        output = WebSearchOutput(data=results)
        return output.model_dump()
