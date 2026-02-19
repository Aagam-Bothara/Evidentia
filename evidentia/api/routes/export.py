"""Export endpoints — citation export in various formats."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger
from evidentia.core.models import Claim

logger = get_logger(__name__)

router = APIRouter()


class ExportRequest(BaseModel):
    claims: list[dict] = Field(..., min_length=1)
    format: str = Field(default="bibtex", pattern="^(bibtex|ris|apa|json)$")


@router.post("/export/citations")
async def export_citations(
    request: ExportRequest,
    user: AuthenticatedUser = Depends(require_auth),
):
    """Export citations from claims in the requested format."""
    try:
        from evidentia.export.citations import CitationExporter

        # Parse claims from dicts
        claims = [Claim.model_validate(c) for c in request.claims]

        if request.format == "bibtex":
            content = CitationExporter.to_bibtex(claims)
            return PlainTextResponse(
                content=content,
                media_type="application/x-bibtex",
                headers={"Content-Disposition": "attachment; filename=evidentia_references.bib"},
            )
        elif request.format == "ris":
            content = CitationExporter.to_ris(claims)
            return PlainTextResponse(
                content=content,
                media_type="application/x-research-info-systems",
                headers={"Content-Disposition": "attachment; filename=evidentia_references.ris"},
            )
        elif request.format == "apa":
            content = CitationExporter.to_apa(claims)
            return PlainTextResponse(
                content=content,
                media_type="text/plain",
                headers={"Content-Disposition": "attachment; filename=evidentia_references.txt"},
            )
        elif request.format == "json":
            content = CitationExporter.to_json(claims)
            return PlainTextResponse(
                content=content,
                media_type="application/json",
                headers={"Content-Disposition": "attachment; filename=evidentia_references.json"},
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {request.format}")

    except ImportError as exc:
        raise HTTPException(status_code=501, detail="Export module not available.") from exc
    except Exception as exc:
        logger.error("export_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc
