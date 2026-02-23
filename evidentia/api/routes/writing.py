"""Writing workspace endpoints — document CRUD, LaTeX conversion, export."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ── In-memory fallback ──────────────────────────────────────────────
_doc_store: dict[str, dict] = {}


# ── Request / Response models ───────────────────────────────────────


class CreateDocumentRequest(BaseModel):
    title: str = Field(default="Untitled", max_length=500)
    project_id: str | None = None
    document_class: str = Field(default="article")
    template_id: str | None = Field(default=None)


class UpdateDocumentRequest(BaseModel):
    title: str | None = None
    plain_content: str | None = None
    latex_content: str | None = None
    mode: str | None = Field(default=None, pattern="^(plain|latex)$")
    document_class: str | None = Field(default=None)


class ConvertRequest(BaseModel):
    content: str = Field(..., min_length=1)
    document_class: str = Field(default="article", pattern="^(article|report|book)$")


class DocumentResponse(BaseModel):
    id: str
    title: str
    plain_content: str
    latex_content: str
    mode: str
    document_class: str
    template_id: str | None = None
    status: str
    created_at: str
    updated_at: str


class ConvertResponse(BaseModel):
    latex: str
    tokens_used: int


# ── Helpers ─────────────────────────────────────────────────────────

LATEX_SYSTEM_PROMPT = """You are a LaTeX expert. Convert the user's plain English text into well-formatted LaTeX.

Rules:
- Output ONLY the LaTeX content (body), not a full document with \\documentclass unless asked
- Use proper LaTeX formatting: \\section{}, \\subsection{}, \\textbf{}, \\textit{}, etc.
- Convert bullet points to \\begin{itemize}...\\end{itemize}
- Convert numbered lists to \\begin{enumerate}...\\end{enumerate}
- Convert tables to \\begin{tabular}...
- Preserve mathematical expressions and equations using $ ... $ or \\[ ... \\]
- Use \\cite{} placeholders for any referenced works
- Keep the content faithful to the original — do not add or remove information
- Use clean, readable LaTeX with proper indentation"""


def _row_to_dict(row) -> dict:
    return {
        "id": str(row.id),
        "title": row.title,
        "plain_content": row.plain_content,
        "latex_content": row.latex_content,
        "mode": row.mode,
        "document_class": row.document_class,
        "template_id": getattr(row, "template_id", None),
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def _mem_to_dict(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "title": doc.get("title", "Untitled"),
        "plain_content": doc.get("plain_content", ""),
        "latex_content": doc.get("latex_content", ""),
        "mode": doc.get("mode", "plain"),
        "document_class": doc.get("document_class", "article"),
        "template_id": doc.get("template_id"),
        "status": doc.get("status", "draft"),
        "created_at": doc.get("created_at", ""),
        "updated_at": doc.get("updated_at", ""),
    }


# ── Templates Endpoint ──────────────────────────────────────────────


@router.get("/writing/templates")
async def list_writing_templates(
    user: AuthenticatedUser = Depends(require_auth),
):
    """List all available LaTeX templates."""
    from evidentia.writing.templates import list_templates

    return list_templates()


@router.get("/writing/templates/{template_id}")
async def get_writing_template(
    template_id: str,
    user: AuthenticatedUser = Depends(require_auth),
):
    """Get a single template with full preamble and skeleton."""
    from evidentia.writing.templates import get_template

    tmpl = get_template(template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return tmpl


# ── CRUD Endpoints ──────────────────────────────────────────────────


@router.post("/writing/documents", response_model=DocumentResponse)
async def create_document(
    request: CreateDocumentRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> DocumentResponse:
    """Create a new writing document, optionally from a template."""
    # If a template is selected, render the skeleton as initial latex_content
    initial_latex = ""
    template_id = request.template_id
    if template_id:
        from evidentia.writing.templates import render_template

        initial_latex = render_template(template_id, title=request.title)

    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.writing_models import WritingDocumentRow

        factory = _get_session_factory()
        async with factory() as db:
            row = WritingDocumentRow(
                user_id=user.user_id,
                project_id=uuid.UUID(request.project_id) if request.project_id else None,
                title=request.title,
                document_class=request.document_class,
                template_id=template_id,
                latex_content=initial_latex,
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return DocumentResponse(**_row_to_dict(row))
    except Exception:
        logger.warning("writing_db_fallback", action="create")

    # In-memory fallback
    now = datetime.now(UTC).isoformat()
    doc_id = uuid.uuid4().hex
    doc = {
        "id": doc_id,
        "user_id": str(user.user_id),
        "title": request.title,
        "plain_content": "",
        "latex_content": initial_latex,
        "mode": "plain",
        "document_class": request.document_class,
        "template_id": template_id,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }
    _doc_store[doc_id] = doc
    return DocumentResponse(**_mem_to_dict(doc))


@router.get("/writing/documents", response_model=list[DocumentResponse])
async def list_documents(
    user: AuthenticatedUser = Depends(require_auth),
) -> list[DocumentResponse]:
    """List all writing documents for the current user."""
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.writing_models import WritingDocumentRow

        factory = _get_session_factory()
        async with factory() as db:
            stmt = (
                select(WritingDocumentRow)
                .where(WritingDocumentRow.user_id == user.user_id)
                .order_by(WritingDocumentRow.updated_at.desc())
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()
            return [DocumentResponse(**_row_to_dict(r)) for r in rows]
    except Exception:
        logger.warning("writing_db_fallback", action="list")

    # In-memory fallback
    docs = [_mem_to_dict(d) for d in _doc_store.values() if d.get("user_id") == str(user.user_id)]
    docs.sort(key=lambda d: d["updated_at"], reverse=True)
    return [DocumentResponse(**d) for d in docs]


@router.get("/writing/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> DocumentResponse:
    """Get a single writing document."""
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.writing_models import WritingDocumentRow

        factory = _get_session_factory()
        async with factory() as db:
            row = await db.get(WritingDocumentRow, uuid.UUID(doc_id))
            if row is None or row.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Document not found")
            return DocumentResponse(**_row_to_dict(row))
    except HTTPException:
        raise
    except Exception:
        logger.warning("writing_db_fallback", action="get")

    # In-memory fallback
    doc = _doc_store.get(doc_id)
    if doc is None or doc.get("user_id") != str(user.user_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse(**_mem_to_dict(doc))


@router.put("/writing/documents/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: str,
    request: UpdateDocumentRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> DocumentResponse:
    """Update a writing document."""
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.writing_models import WritingDocumentRow

        factory = _get_session_factory()
        async with factory() as db:
            row = await db.get(WritingDocumentRow, uuid.UUID(doc_id))
            if row is None or row.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Document not found")

            if request.title is not None:
                row.title = request.title
            if request.plain_content is not None:
                row.plain_content = request.plain_content
            if request.latex_content is not None:
                row.latex_content = request.latex_content
            if request.mode is not None:
                row.mode = request.mode
            if request.document_class is not None:
                row.document_class = request.document_class
            row.updated_at = datetime.now(UTC)

            await db.commit()
            await db.refresh(row)
            return DocumentResponse(**_row_to_dict(row))
    except HTTPException:
        raise
    except Exception:
        logger.warning("writing_db_fallback", action="update")

    # In-memory fallback
    doc = _doc_store.get(doc_id)
    if doc is None or doc.get("user_id") != str(user.user_id):
        raise HTTPException(status_code=404, detail="Document not found")

    if request.title is not None:
        doc["title"] = request.title
    if request.plain_content is not None:
        doc["plain_content"] = request.plain_content
    if request.latex_content is not None:
        doc["latex_content"] = request.latex_content
    if request.mode is not None:
        doc["mode"] = request.mode
    if request.document_class is not None:
        doc["document_class"] = request.document_class
    doc["updated_at"] = datetime.now(UTC).isoformat()
    return DocumentResponse(**_mem_to_dict(doc))


@router.delete("/writing/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    user: AuthenticatedUser = Depends(require_auth),
):
    """Delete a writing document."""
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.writing_models import WritingDocumentRow

        factory = _get_session_factory()
        async with factory() as db:
            row = await db.get(WritingDocumentRow, uuid.UUID(doc_id))
            if row is None or row.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Document not found")
            await db.delete(row)
            await db.commit()
            return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception:
        logger.warning("writing_db_fallback", action="delete")

    # In-memory fallback
    doc = _doc_store.get(doc_id)
    if doc is None or doc.get("user_id") != str(user.user_id):
        raise HTTPException(status_code=404, detail="Document not found")
    del _doc_store[doc_id]
    return {"status": "deleted"}


# ── LaTeX Conversion ────────────────────────────────────────────────


@router.post("/writing/convert", response_model=ConvertResponse)
async def convert_to_latex(
    request: ConvertRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> ConvertResponse:
    """Convert plain English text to LaTeX using the LLM."""
    try:
        from evidentia.core.config import get_settings
        from evidentia.core.llm import create_llm

        settings = get_settings()
        llm = create_llm(settings)

        messages = [
            {"role": "system", "content": LATEX_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Document class: {request.document_class}\n\nConvert the following to LaTeX:\n\n{request.content}"
                ),
            },
        ]

        response = await llm.chat(messages, temperature=0.1, max_tokens=4096)
        tokens = response.usage.get("total_tokens", 0) if response.usage else 0

        return ConvertResponse(latex=response.content, tokens_used=tokens)

    except Exception as exc:
        logger.error("latex_conversion_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"LaTeX conversion failed: {exc}") from exc


# ── Export ──────────────────────────────────────────────────────────


@router.get("/writing/documents/{doc_id}/export")
async def export_document(
    doc_id: str,
    user: AuthenticatedUser = Depends(require_auth),
):
    """Export a writing document as a .tex file."""
    # Get the document first
    doc_data = None
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.writing_models import WritingDocumentRow

        factory = _get_session_factory()
        async with factory() as db:
            row = await db.get(WritingDocumentRow, uuid.UUID(doc_id))
            if row is None or row.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Document not found")
            doc_data = _row_to_dict(row)
    except HTTPException:
        raise
    except Exception:
        logger.warning("writing_db_fallback", action="export")
        doc = _doc_store.get(doc_id)
        if doc is None or doc.get("user_id") != str(user.user_id):
            raise HTTPException(status_code=404, detail="Document not found") from None
        doc_data = _mem_to_dict(doc)

    # Build .tex content
    latex = doc_data.get("latex_content", "")
    title = doc_data.get("title", "Untitled")
    tmpl_id = doc_data.get("template_id")

    if not latex.strip():
        # If no LaTeX content, export plain content as-is
        latex = doc_data.get("plain_content", "")

    # Wrap in a full document if it's just body content
    if "\\documentclass" not in latex:
        # Use the template preamble if available
        if tmpl_id:
            from evidentia.writing.templates import render_template

            full_doc = render_template(tmpl_id, title=title)
            # Replace the skeleton body with actual content
            if "\\maketitle" in full_doc:
                parts = full_doc.split("\\maketitle", 1)
                full_doc = parts[0] + "\\maketitle\n\n" + latex + "\n\n\\end{document}\n"
            else:
                full_doc = full_doc + "\n" + latex
        else:
            from evidentia.writing.templates import render_template

            full_doc = render_template("article", title=title)
            parts = full_doc.split("\\maketitle", 1)
            full_doc = parts[0] + "\\maketitle\n\n" + latex + "\n\n\\end{document}\n"
    else:
        full_doc = latex

    safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
    filename = f"{safe_title or 'document'}.tex"

    return PlainTextResponse(
        content=full_doc,
        media_type="application/x-tex",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
