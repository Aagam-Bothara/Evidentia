"""Citation-manager export endpoints — CSL-JSON, Zotero, and Mendeley."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger
from evidentia.core.models import Claim

logger = get_logger(__name__)

router = APIRouter()


# ── Request schemas ─────────────────────────────────────────────────


class ExportCitationsRequest(BaseModel):
    """Shared request body for CSL-JSON and Mendeley/RIS export."""

    claims: list[dict] = Field(..., min_length=1)


class ZoteroExportRequest(BaseModel):
    """Request body for direct Zotero library push."""

    claims: list[dict] = Field(..., min_length=1)
    zotero_api_key: str
    zotero_user_id: str | None = None
    zotero_group_id: str | None = None
    collection_id: str | None = None


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/export/csl-json")
async def export_csl_json(
    request: ExportCitationsRequest,
    user: AuthenticatedUser = Depends(require_auth),
):
    """Export citations as CSL-JSON (compatible with Zotero, Mendeley, etc.).

    The response is a downloadable JSON file containing an array of
    CSL-JSON items derived from the supplied claims' citations.
    """
    try:
        from evidentia.export.csl_json import claims_to_csl_json

        claims = [Claim.model_validate(c) for c in request.claims]
        content = claims_to_csl_json(claims)

        logger.info("csl_json_export", user=user.email, claim_count=len(claims))

        return PlainTextResponse(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=evidentia_references_csl.json",
            },
        )
    except Exception as exc:
        logger.error("csl_json_export_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"CSL-JSON export failed: {exc}") from exc


@router.post("/export/zotero")
async def export_to_zotero(
    request: ZoteroExportRequest,
    user: AuthenticatedUser = Depends(require_auth),
):
    """Export citations directly to a Zotero library via the Zotero Web API.

    The caller must supply a valid ``zotero_api_key`` and either
    ``zotero_user_id`` (personal library) or ``zotero_group_id``
    (group library).  An optional ``collection_id`` files the new
    items into a specific Zotero collection.

    Returns a JSON summary with success / failure counts.
    """
    if not request.zotero_user_id and not request.zotero_group_id:
        raise HTTPException(
            status_code=422,
            detail="Either zotero_user_id or zotero_group_id is required.",
        )

    try:
        import json

        from evidentia.export.csl_json import claims_to_csl_json
        from evidentia.export.zotero import ZoteroClient

        # Build CSL-JSON items from claims
        claims = [Claim.model_validate(c) for c in request.claims]
        csl_str = claims_to_csl_json(claims)
        csl_items: list[dict] = json.loads(csl_str)

        if not csl_items:
            raise HTTPException(status_code=400, detail="No citations found in the provided claims.")

        # Set up the Zotero client and verify the key
        client = ZoteroClient(
            api_key=request.zotero_api_key,
            user_id=request.zotero_user_id,
            group_id=request.zotero_group_id,
        )
        key_ok = await client.verify_key()
        if not key_ok:
            raise HTTPException(status_code=401, detail="Invalid Zotero API key.")

        # Push items
        result = await client.create_items(csl_items, collection_id=request.collection_id)

        logger.info(
            "zotero_export",
            user=user.email,
            success=result.get("success"),
            failed=result.get("failed"),
        )

        return result

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("zotero_export_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Zotero export failed: {exc}") from exc


@router.post("/export/mendeley")
async def export_mendeley_ris(
    request: ExportCitationsRequest,
    user: AuthenticatedUser = Depends(require_auth),
):
    """Export citations as RIS optimised for Mendeley import.

    Mendeley's desktop and web importers accept standard RIS files.
    This endpoint re-uses the existing RIS exporter and returns the
    file with Mendeley-friendly headers.
    """
    try:
        from evidentia.export.citations import CitationExporter

        claims = [Claim.model_validate(c) for c in request.claims]
        content = CitationExporter.to_ris(claims)

        if not content.strip():
            raise HTTPException(status_code=400, detail="No citations found in the provided claims.")

        logger.info("mendeley_ris_export", user=user.email, claim_count=len(claims))

        return PlainTextResponse(
            content=content,
            media_type="application/x-research-info-systems",
            headers={
                "Content-Disposition": "attachment; filename=evidentia_references_mendeley.ris",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("mendeley_ris_export_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Mendeley RIS export failed: {exc}") from exc
