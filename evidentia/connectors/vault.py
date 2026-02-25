"""Vault — encrypted storage for BYO-API credentials.

Uses the database for persistent storage when available,
falls back to in-memory storage for development / tests.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from evidentia.core.exceptions import ConnectorAuthError
from evidentia.core.logging import get_logger

logger = get_logger(__name__)


class StoredCredential(BaseModel):
    """An encrypted credential stored in the vault."""

    connector_name: str
    key_name: str
    encrypted_value: str  # base64-encoded
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def _encode(value: str) -> str:
    """Encode a credential value (base64 for now, KMS in production)."""
    return base64.b64encode(value.encode()).decode()


def _decode(encoded: str) -> str:
    """Decode a credential value."""
    return base64.b64decode(encoded).decode()


def _parse_user_id(connector_name: str) -> str | None:
    """Extract user_id from connector_name like 'user:<uuid>'."""
    if connector_name.startswith("user:"):
        return connector_name[5:]
    return None


class CredentialVault:
    """Credential storage for BYO-API keys.

    Tries the database first for persistent storage.
    Falls back to in-memory if the database is unavailable.
    """

    def __init__(self) -> None:
        self._memory_store: dict[str, StoredCredential] = {}

    async def _get_db_session(self):
        """Try to get a database session. Returns None if DB unavailable."""
        try:
            from evidentia.db.engine import _get_session_factory

            factory = _get_session_factory()
            return factory()
        except Exception:
            return None

    async def store_credential(
        self,
        connector_name: str,
        key_name: str,
        value: str,
    ) -> None:
        """Store an API key. Persists to DB if available, else in-memory."""
        encoded = _encode(value)
        user_id = _parse_user_id(connector_name)

        # Try DB first
        if user_id:
            try:
                await self._db_store(user_id, key_name, encoded)
                logger.info("credential_stored_db", connector=connector_name, key=key_name)
                return
            except Exception as exc:
                logger.debug("db_store_fallback_memory", error=str(exc))

        # Fallback: in-memory
        compound_key = f"{connector_name}:{key_name}"
        self._memory_store[compound_key] = StoredCredential(
            connector_name=connector_name,
            key_name=key_name,
            encrypted_value=encoded,
            created_at=datetime.now(UTC).isoformat(),
        )
        logger.info("credential_stored", connector=connector_name, key=key_name)

    async def get_credential(self, connector_name: str, key_name: str) -> str:
        """Retrieve a decrypted API key."""
        user_id = _parse_user_id(connector_name)

        # Try DB first
        if user_id:
            try:
                encoded = await self._db_get(user_id, key_name)
                if encoded is not None:
                    return _decode(encoded)
            except Exception:
                pass

        # Fallback: in-memory
        compound_key = f"{connector_name}:{key_name}"
        cred = self._memory_store.get(compound_key)
        if cred is None:
            raise ConnectorAuthError(f"No credential found for {connector_name}:{key_name}")
        return _decode(cred.encrypted_value)

    async def delete_credential(self, connector_name: str, key_name: str) -> bool:
        """Delete a stored credential."""
        user_id = _parse_user_id(connector_name)

        # Try DB first
        if user_id:
            try:
                deleted = await self._db_delete(user_id, key_name)
                if deleted:
                    logger.info("credential_deleted_db", connector=connector_name, key=key_name)
                    return True
            except Exception:
                pass

        # Fallback: in-memory
        compound_key = f"{connector_name}:{key_name}"
        if compound_key in self._memory_store:
            del self._memory_store[compound_key]
            logger.info("credential_deleted", connector=connector_name, key=key_name)
            return True
        return False

    async def list_credentials(self, connector_name: str | None = None) -> list[str]:
        """List stored credential keys (not values)."""
        user_id = _parse_user_id(connector_name) if connector_name else None

        # Try DB first
        if user_id:
            try:
                db_keys = await self._db_list(user_id)
                if db_keys is not None:
                    return [f"{connector_name}:{k}" for k in db_keys]
            except Exception:
                pass

        # Fallback: in-memory
        keys = list(self._memory_store.keys())
        if connector_name:
            keys = [k for k in keys if k.startswith(f"{connector_name}:")]
        return keys

    # ── Database operations ──────────────────────────────────────

    async def _db_store(self, user_id: str, service: str, encoded: str) -> None:
        """Upsert a credential in the database."""
        from sqlalchemy import select

        from evidentia.db.models import UserCredentialRow

        session = await self._get_db_session()
        if session is None:
            raise RuntimeError("No DB session")

        async with session:
            stmt = select(UserCredentialRow).where(
                UserCredentialRow.user_id == user_id,
                UserCredentialRow.service == service,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

            if row:
                row.encrypted_value = encoded
                row.updated_at = datetime.now(UTC)
            else:
                row = UserCredentialRow(
                    user_id=user_id,
                    service=service,
                    encrypted_value=encoded,
                )
                session.add(row)

            await session.commit()

    async def _db_get(self, user_id: str, service: str) -> str | None:
        """Get a credential from the database."""
        from sqlalchemy import select

        from evidentia.db.models import UserCredentialRow

        session = await self._get_db_session()
        if session is None:
            return None

        async with session:
            stmt = select(UserCredentialRow.encrypted_value).where(
                UserCredentialRow.user_id == user_id,
                UserCredentialRow.service == service,
            )
            result = await session.execute(stmt)
            value = result.scalar_one_or_none()
            return value

    async def _db_delete(self, user_id: str, service: str) -> bool:
        """Delete a credential from the database."""
        from sqlalchemy import delete, select

        from evidentia.db.models import UserCredentialRow

        session = await self._get_db_session()
        if session is None:
            return False

        async with session:
            # Check existence first
            stmt = select(UserCredentialRow.id).where(
                UserCredentialRow.user_id == user_id,
                UserCredentialRow.service == service,
            )
            result = await session.execute(stmt)
            if result.scalar_one_or_none() is None:
                return False

            await session.execute(
                delete(UserCredentialRow).where(
                    UserCredentialRow.user_id == user_id,
                    UserCredentialRow.service == service,
                )
            )
            await session.commit()
            return True

    async def _db_list(self, user_id: str) -> list[str] | None:
        """List services with stored credentials for a user."""
        from sqlalchemy import select

        from evidentia.db.models import UserCredentialRow

        session = await self._get_db_session()
        if session is None:
            return None

        async with session:
            stmt = select(UserCredentialRow.service).where(
                UserCredentialRow.user_id == user_id,
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]
