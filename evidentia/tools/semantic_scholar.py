"""Semantic Scholar tool — searches academic papers via the Semantic Scholar API."""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import httpx

from evidentia.core.exceptions import ToolExecutionError
from evidentia.schemas.tool_io import (
    SemanticScholarInput,
    SemanticScholarOutput,
    SemanticScholarPaper,
)
from evidentia.tools.base import BaseTool, ToolMetadata

S2_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0  # seconds


class SemanticScholarTool(BaseTool):
    """Search Semantic Scholar for academic papers."""

    metadata: ClassVar[ToolMetadata] = ToolMetadata(
        name="semantic_scholar",
        description="Search Semantic Scholar for papers by query with citation counts.",
        category="public_api",
        input_schema=SemanticScholarInput.model_json_schema(),
        output_schema=SemanticScholarOutput.model_json_schema(),
        timeout_seconds=30,
        requires_auth=False,
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        params = SemanticScholarInput.model_validate(input_data)

        headers: dict[str, str] = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key

        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=self.metadata.timeout_seconds, follow_redirects=True) as client:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await client.get(
                        S2_API_URL,
                        params={
                            "query": params.query,
                            "limit": params.max_results,
                            "fields": ",".join(params.fields),
                        },
                        headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except httpx.HTTPStatusError as exc:
                    last_exc = exc
                    if exc.response.status_code == 429:
                        retry_after = _BACKOFF_BASE * (2**attempt)
                        if ra := exc.response.headers.get("Retry-After"):
                            try:
                                retry_after = max(float(ra), retry_after)
                            except ValueError:
                                pass
                        if attempt < _MAX_RETRIES - 1:
                            await asyncio.sleep(retry_after)
                            continue
                    retry_after_val = None
                    if ra := exc.response.headers.get("Retry-After"):
                        try:
                            retry_after_val = float(ra)
                        except ValueError:
                            pass
                    raise ToolExecutionError(
                        f"Semantic Scholar API returned {exc.response.status_code}: {exc}",
                        tool_name=self.metadata.name,
                        status_code=exc.response.status_code,
                        retry_after=retry_after_val,
                    ) from exc
                except httpx.HTTPError as exc:
                    last_exc = exc
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(_BACKOFF_BASE * (2**attempt))
                        continue
                    raise ToolExecutionError(
                        f"Semantic Scholar API request failed: {exc}",
                        tool_name=self.metadata.name,
                    ) from exc
            else:
                raise ToolExecutionError(
                    f"Semantic Scholar API failed after {_MAX_RETRIES} retries: {last_exc}",
                    tool_name=self.metadata.name,
                ) from last_exc

        papers = [
            SemanticScholarPaper(
                paper_id=p.get("paperId", ""),
                title=p.get("title", ""),
                abstract=p.get("abstract"),
                authors=[a.get("name", "") for a in p.get("authors", [])],
                year=p.get("year"),
                citation_count=p.get("citationCount"),
                url=p.get("url"),
            )
            for p in data.get("data", [])
        ]

        output = SemanticScholarOutput(data=papers)
        return output.model_dump()
