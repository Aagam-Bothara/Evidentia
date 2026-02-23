"""User API key management — store, list, delete BYO-API keys."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Canonical service names — only these are accepted
ALLOWED_SERVICES = frozenset(
    {
        "openai",
        "anthropic",
        "serpapi",
        "semantic_scholar",
        "ncbi",
        "openalex",
    }
)

# ── Singleton vault instance ─────────────────────────────────────

_vault = None


def _get_vault():
    """Return the singleton CredentialVault."""
    global _vault
    if _vault is None:
        from evidentia.connectors.vault import CredentialVault

        _vault = CredentialVault()
    return _vault


# ── Schemas ──────────────────────────────────────────────────────


class StoreKeyRequest(BaseModel):
    service: str = Field(..., description="Service name, e.g. 'openai'")
    api_key: str = Field(..., min_length=1, max_length=512)


class StoredKeyInfo(BaseModel):
    service: str
    masked_key: str


class StoreKeyResponse(BaseModel):
    service: str
    status: str = "stored"


class DeleteKeyResponse(BaseModel):
    service: str
    status: str = "deleted"


# ── Helpers ──────────────────────────────────────────────────────


def _mask_key(value: str) -> str:
    """Mask a key showing only the last 4 characters."""
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]


def _user_connector(user_id: str) -> str:
    """Build the vault connector_name scoped to a user."""
    return f"user:{user_id}"


# ── Endpoints ────────────────────────────────────────────────────


@router.post("/keys", response_model=StoreKeyResponse)
async def store_key(
    body: StoreKeyRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> StoreKeyResponse:
    """Store a BYO-API key for the authenticated user."""
    if body.service not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown service '{body.service}'. Allowed: {sorted(ALLOWED_SERVICES)}",
        )
    vault = _get_vault()
    connector = _user_connector(str(user.user_id))
    await vault.store_credential(connector, body.service, body.api_key)
    logger.info("user_key_stored", user_id=str(user.user_id), service=body.service)
    return StoreKeyResponse(service=body.service)


@router.get("/keys", response_model=list[StoredKeyInfo])
async def list_keys(
    user: AuthenticatedUser = Depends(require_auth),
) -> list[StoredKeyInfo]:
    """List all BYO-API keys for the authenticated user (masked values)."""
    vault = _get_vault()
    connector = _user_connector(str(user.user_id))
    stored_keys = await vault.list_credentials(connector)
    results = []
    for key_str in stored_keys:
        # key_str format is "user:<user_id>:<service>"
        service = key_str.split(":")[-1]
        try:
            value = await vault.get_credential(connector, service)
            results.append(StoredKeyInfo(service=service, masked_key=_mask_key(value)))
        except Exception:
            results.append(StoredKeyInfo(service=service, masked_key="****"))
    return results


@router.delete("/keys/{service}", response_model=DeleteKeyResponse)
async def delete_key(
    service: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> DeleteKeyResponse:
    """Delete a stored BYO-API key for the authenticated user."""
    if service not in ALLOWED_SERVICES:
        raise HTTPException(status_code=400, detail=f"Unknown service '{service}'.")
    vault = _get_vault()
    connector = _user_connector(str(user.user_id))
    deleted = await vault.delete_credential(connector, service)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No key stored for '{service}'.")
    logger.info("user_key_deleted", user_id=str(user.user_id), service=service)
    return DeleteKeyResponse(service=service)
