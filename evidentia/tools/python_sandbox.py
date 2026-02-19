"""Python Sandbox tool — executes user code in an isolated subprocess."""

from __future__ import annotations

import asyncio
import sys
from typing import Any, ClassVar

from evidentia.core.exceptions import ToolExecutionError
from evidentia.schemas.tool_io import PythonSandboxInput, PythonSandboxOutput
from evidentia.tools.base import BaseTool, ToolMetadata


class PythonSandboxTool(BaseTool):
    """Execute Python code in an isolated subprocess with resource limits."""

    metadata: ClassVar[ToolMetadata] = ToolMetadata(
        name="python_sandbox",
        description="Execute Python code in an isolated sandbox and return stdout/stderr.",
        category="local_execution",
        input_schema=PythonSandboxInput.model_json_schema(),
        output_schema=PythonSandboxOutput.model_json_schema(),
        timeout_seconds=60,
        requires_auth=False,
    )

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        params = PythonSandboxInput.model_validate(input_data)

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                params.code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=params.timeout_seconds,
            )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            output = PythonSandboxOutput(
                success=proc.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                error=stderr if proc.returncode != 0 else None,
            )

        except asyncio.TimeoutError:
            raise ToolExecutionError(
                f"Python sandbox timed out after {params.timeout_seconds}s",
                tool_name=self.metadata.name,
            )
        except Exception as exc:
            raise ToolExecutionError(
                f"Sandbox execution failed: {exc}",
                tool_name=self.metadata.name,
            ) from exc

        return output.model_dump()
