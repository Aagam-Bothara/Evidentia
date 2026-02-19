"""Base connector interface for BYO-API integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ConnectorMode(str, Enum):
    """How the connector executes tool calls."""

    HOSTED = "hosted"  # Keys stored in vault, executed server-side
    USER_OWNED = "user_owned"  # Executed in user's local/VPC runtime


class ConnectorConfig(BaseModel):
    """Configuration for a BYO-API connector."""

    name: str
    mode: ConnectorMode = ConnectorMode.HOSTED
    base_url: str
    auth_type: str = "api_key"  # api_key, oauth2, basic
    timeout_seconds: int = 30
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseConnector(ABC):
    """Abstract base class for all BYO-API connectors."""

    def __init__(self, config: ConnectorConfig) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def mode(self) -> ConnectorMode:
        return self._config.mode

    @abstractmethod
    async def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        """Execute a request against the connector's API.

        For HOSTED mode: uses vault-stored credentials.
        For USER_OWNED mode: forwards signed request to user's runtime.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the connector endpoint is reachable and authenticated."""
