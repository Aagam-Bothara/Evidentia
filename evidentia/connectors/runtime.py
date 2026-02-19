"""User-Owned Connector Runtime — executes signed requests in user's environment."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx
from pydantic import BaseModel

from evidentia.core.exceptions import ConnectorRuntimeError
from evidentia.core.logging import get_logger

logger = get_logger(__name__)


class ExecutionRequest(BaseModel):
    """A signed request sent to the user-owned connector runtime."""

    request_id: str
    connector_name: str
    method: str
    endpoint: str
    payload: dict[str, Any]
    signature: str  # HMAC signature for request integrity


class ExecutionResponse(BaseModel):
    """Response from the user-owned connector runtime."""

    request_id: str
    status_code: int
    data: Any
    error: str | None = None


class ConnectorRuntime:
    """Client for communicating with the user-owned connector runtime.

    The runtime is a lightweight agent (Docker container or binary)
    running in the user's local environment or VPC. It receives
    signed execution requests and executes them against user APIs
    without exposing credentials to the Evidentia server.
    """

    def __init__(self, runtime_url: str, signing_key: str) -> None:
        self._runtime_url = runtime_url.rstrip("/")
        self._signing_key = signing_key

    def sign_request(self, request: ExecutionRequest) -> str:
        """Generate HMAC signature for request integrity."""
        payload_str = json.dumps(
            {
                "request_id": request.request_id,
                "connector_name": request.connector_name,
                "method": request.method,
                "endpoint": request.endpoint,
                "payload": request.payload,
            },
            sort_keys=True,
        )
        return hmac.new(
            self._signing_key.encode(),
            payload_str.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        """Send a signed request to the user-owned runtime."""
        request.signature = self.sign_request(request)

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    f"{self._runtime_url}/execute",
                    json=request.model_dump(),
                )
                resp.raise_for_status()
                return ExecutionResponse.model_validate(resp.json())
            except httpx.HTTPError as exc:
                raise ConnectorRuntimeError(f"Failed to reach connector runtime at {self._runtime_url}: {exc}") from exc

    async def health_check(self) -> bool:
        """Check if the runtime is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._runtime_url}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
