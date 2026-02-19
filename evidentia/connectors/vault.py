"""Vault — encrypted storage for BYO-API credentials."""

from __future__ import annotations

import base64
import os
from typing import Any

from pydantic import BaseModel, Field

from evidentia.core.exceptions import ConnectorAuthError
from evidentia.core.logging import get_logger

logger = get_logger(__name__)


class StoredCredential(BaseModel):
    """An encrypted credential stored in the vault."""

    connector_name: str
    key_name: str
    encrypted_value: str  # base64-encoded encrypted bytes
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CredentialVault:
    """Encrypted credential storage for BYO-API keys.

    In production this would integrate with HashiCorp Vault, AWS Secrets Manager,
    or similar. This implementation uses in-memory storage with basic encoding
    as a development placeholder.

    IMPORTANT: Replace with a real secrets manager before production deployment.
    """

    def __init__(self) -> None:
        self._store: dict[str, StoredCredential] = {}

    async def store_credential(
        self,
        connector_name: str,
        key_name: str,
        value: str,
    ) -> None:
        """Store an API key securely."""
        # In production: encrypt with Vault transit engine or KMS
        encoded = base64.b64encode(value.encode()).decode()
        key = f"{connector_name}:{key_name}"
        self._store[key] = StoredCredential(
            connector_name=connector_name,
            key_name=key_name,
            encrypted_value=encoded,
            created_at="",
        )
        logger.info("credential_stored", connector=connector_name, key=key_name)

    async def get_credential(self, connector_name: str, key_name: str) -> str:
        """Retrieve a decrypted API key."""
        key = f"{connector_name}:{key_name}"
        cred = self._store.get(key)
        if cred is None:
            raise ConnectorAuthError(
                f"No credential found for {connector_name}:{key_name}"
            )
        # In production: decrypt with Vault/KMS
        return base64.b64decode(cred.encrypted_value).decode()

    async def delete_credential(self, connector_name: str, key_name: str) -> bool:
        key = f"{connector_name}:{key_name}"
        if key in self._store:
            del self._store[key]
            logger.info("credential_deleted", connector=connector_name, key=key_name)
            return True
        return False

    async def list_credentials(self, connector_name: str | None = None) -> list[str]:
        """List stored credential keys (not values)."""
        keys = list(self._store.keys())
        if connector_name:
            keys = [k for k in keys if k.startswith(f"{connector_name}:")]
        return keys
