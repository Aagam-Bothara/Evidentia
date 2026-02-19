"""Base tool interface — all tools must implement this contract."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel

from evidentia.core.exceptions import ToolTimeoutError


class ToolMetadata(BaseModel):
    """Declarative metadata for a tool."""

    name: str
    description: str
    category: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    timeout_seconds: int = 30
    max_retries: int = 3
    requires_auth: bool = False


class BaseTool(ABC):
    """Abstract base class for all Evidentia tools.

    Every tool must declare:
    - metadata (name, schemas, timeout, auth requirements)
    - execute() method with strict input validation
    """

    metadata: ClassVar[ToolMetadata]

    @abstractmethod
    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute the tool with validated input and return validated output.

        Args:
            input_data: Dict matching the tool's declared input_schema.

        Returns:
            Dict matching the tool's declared output_schema.

        Raises:
            ToolSchemaError: If input/output doesn't match declared schemas.
            ToolTimeoutError: If execution exceeds the configured timeout.
            ToolExecutionError: If the tool fails after all retries.
        """

    async def execute_with_timeout(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Wrapper that enforces the tool's timeout policy."""
        try:
            return await asyncio.wait_for(
                self.execute(input_data),
                timeout=self.metadata.timeout_seconds,
            )
        except TimeoutError as exc:
            raise ToolTimeoutError(
                f"Tool '{self.metadata.name}' timed out after {self.metadata.timeout_seconds}s",
                tool_name=self.metadata.name,
            ) from exc


class ToolRegistry:
    """Central registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.metadata.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolMetadata]:
        return [t.metadata for t in self._tools.values()]

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    @property
    def tools(self) -> dict[str, BaseTool]:
        return dict(self._tools)
