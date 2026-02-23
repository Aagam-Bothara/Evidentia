"""Upload endpoints — PDF ingestion and file management."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# In-memory PDF store (fallback when DB unavailable)
_pdf_store: dict[str, dict[str, Any]] = {}


class PDFUploadResponse(BaseModel):
    id: str
    filename: str
    page_count: int
    chunk_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class PDFListResponse(BaseModel):
    pdfs: list[PDFUploadResponse]


@router.post("/upload/pdf", response_model=PDFUploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    user: AuthenticatedUser = Depends(require_auth),
) -> PDFUploadResponse:
    """Upload a PDF for ingestion, chunking, and indexing."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Save to temp file
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=413, detail="File too large. Maximum 50MB.")

    tmp_dir = Path(tempfile.gettempdir()) / "evidentia_pdfs"
    tmp_dir.mkdir(exist_ok=True)
    pdf_id = uuid.uuid4().hex[:12]
    tmp_path = tmp_dir / f"{pdf_id}.pdf"
    tmp_path.write_bytes(content)

    # Run PDF ingestion tool
    try:
        from evidentia.tools.pdf_ingest import PDFIngestTool

        tool = PDFIngestTool()
        result = await tool.execute({"file_path": str(tmp_path)})
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail="PDF ingestion requires pymupdf. Install with: pip install pymupdf",
        ) from exc
    except Exception as exc:
        logger.error("pdf_upload_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"PDF processing failed: {exc}") from exc

    chunks = result.get("chunks", [])
    metadata = result.get("metadata", {})
    metadata["original_filename"] = file.filename

    # Persist to DB (fallback to in-memory)
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import PDFRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = PDFRepository(db)
            saved_pdf = await repo.save(
                user_id=user.user_id,
                filename=file.filename,
                page_count=result.get("page_count", 0),
                chunk_count=len(chunks),
                text=result.get("text", ""),
                metadata=metadata,
                file_path=str(tmp_path),
                chunks=chunks,
            )
            await db.commit()
            # Use the DB-generated UUID so Ask PDF can find it later
            pdf_id = str(saved_pdf.id)
    except Exception as exc:
        logger.warning("pdf_db_save_failed", error=str(exc))
        _pdf_store[pdf_id] = {
            "id": pdf_id,
            "filename": file.filename,
            "page_count": result.get("page_count", 0),
            "chunk_count": len(chunks),
            "chunks": chunks,
            "text": result.get("text", ""),
            "metadata": metadata,
            "path": str(tmp_path),
        }

    logger.info(
        "pdf_uploaded",
        pdf_id=pdf_id,
        filename=file.filename,
        pages=result.get("page_count", 0),
        chunks=len(chunks),
    )

    return PDFUploadResponse(
        id=pdf_id,
        filename=file.filename,
        page_count=result.get("page_count", 0),
        chunk_count=len(chunks),
        metadata=metadata,
    )


@router.get("/pdfs", response_model=PDFListResponse)
async def list_pdfs(user: AuthenticatedUser = Depends(require_auth)) -> PDFListResponse:
    """List all uploaded PDFs for the current user."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import PDFRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = PDFRepository(db)
            rows = await repo.list_all(user_id=user.user_id)
            return PDFListResponse(
                pdfs=[
                    PDFUploadResponse(
                        id=str(r.id),
                        filename=r.filename,
                        page_count=r.page_count,
                        chunk_count=r.chunk_count,
                        metadata=r.metadata_json or {},
                    )
                    for r in rows
                ]
            )
    except Exception:
        pass

    # Fallback to in-memory store
    return PDFListResponse(
        pdfs=[
            PDFUploadResponse(
                id=p["id"],
                filename=p["filename"],
                page_count=p["page_count"],
                chunk_count=p["chunk_count"],
                metadata=p["metadata"],
            )
            for p in _pdf_store.values()
        ]
    )


@router.delete("/pdfs/{pdf_id}")
async def delete_pdf(pdf_id: str, user: AuthenticatedUser = Depends(require_auth)) -> dict[str, str]:
    """Delete an uploaded PDF."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import PDFRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = PDFRepository(db)
            deleted = await repo.delete(uuid.UUID(pdf_id))
            if deleted:
                await db.commit()
                return {"status": "deleted", "id": pdf_id}
    except Exception:
        pass

    # Fallback to in-memory
    if pdf_id not in _pdf_store:
        raise HTTPException(status_code=404, detail="PDF not found.")

    entry = _pdf_store.pop(pdf_id)
    path = Path(entry.get("path", ""))
    if path.exists():
        path.unlink()

    return {"status": "deleted", "id": pdf_id}


# ═══════════════════════════════════════════════════════════════
# ASK PDF (RAG chat with document)
# ═══════════════════════════════════════════════════════════════

# In-memory vector stores per PDF
_pdf_vector_stores: dict[str, Any] = {}


class AskPDFRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class AskPDFResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]]


async def _load_pdf_data(pdf_id: str) -> dict[str, Any] | None:
    """Load PDF data from DB first, then fallback to in-memory store."""
    # Try DB
    try:
        import uuid as _uuid

        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import PDFRepository

        parsed_id = _uuid.UUID(pdf_id)
        factory = _get_session_factory()
        async with factory() as db:
            repo = PDFRepository(db)
            row = await repo.get(parsed_id)
            if row is not None:
                return {
                    "id": str(row.id),
                    "filename": row.filename,
                    "page_count": row.page_count,
                    "chunk_count": row.chunk_count,
                    "text": row.text,
                    "metadata": row.metadata_json or {},
                    "chunks": [
                        {
                            "text": c.text,
                            "page_number": c.page_number,
                            "chunk_index": c.chunk_index,
                        }
                        for c in row.chunks
                    ],
                }
    except (ValueError, Exception):
        # ValueError if pdf_id isn't a valid UUID (old short hex format)
        pass

    # Fallback to in-memory
    return _pdf_store.get(pdf_id)


@router.post("/pdfs/{pdf_id}/ask", response_model=AskPDFResponse)
async def ask_pdf(
    pdf_id: str,
    body: AskPDFRequest,
    user: AuthenticatedUser = Depends(require_auth),
) -> AskPDFResponse:
    """Ask a question about an uploaded PDF using RAG."""
    # Load PDF from DB or in-memory store
    pdf_data = await _load_pdf_data(pdf_id)
    if not pdf_data:
        raise HTTPException(status_code=404, detail="PDF not found")

    # Build/get vector store for this PDF
    if pdf_id not in _pdf_vector_stores:
        from evidentia.retrieval.vector_store import VectorStore

        vs = VectorStore()
        chunks_for_vs = [
            {
                "doc_id": f"{pdf_id}_chunk_{i}",
                "title": pdf_data["filename"],
                "text": chunk["text"],
                "metadata": {
                    "page_number": chunk.get("page_number", 0),
                    "chunk_index": chunk.get("chunk_index", i),
                    "source_file": pdf_data["filename"],
                },
            }
            for i, chunk in enumerate(pdf_data.get("chunks", []))
        ]
        await vs.add_chunks(chunks_for_vs)
        _pdf_vector_stores[pdf_id] = vs

    vs = _pdf_vector_stores[pdf_id]

    # Search for relevant chunks
    results = await vs.search(body.question, top_k=5)

    # Build context from top chunks
    context_parts = []
    sources = []
    for r in results:
        page = r.metadata.get("page_number", "?") if r.metadata else "?"
        context_parts.append(f"[Page {page}]\n{r.text}")
        sources.append(
            {
                "text": r.text[:200] + ("..." if len(r.text) > 200 else ""),
                "page": page,
                "score": round(r.score, 3),
            }
        )

    context_text = "\n\n---\n\n".join(context_parts)

    # Call LLM
    from evidentia.core.config import get_settings
    from evidentia.core.llm import create_llm

    settings = get_settings()
    llm = create_llm(settings)

    messages = [
        {
            "role": "system",
            "content": (
                f"You are a research assistant answering questions about the document '{pdf_data['filename']}'. "
                "Answer based ONLY on the provided document excerpts. "
                "Cite page numbers when referencing specific information. "
                "If the excerpts don't contain enough information to answer, say so clearly."
            ),
        },
        {
            "role": "user",
            "content": f"Document excerpts:\n\n{context_text}\n\n---\n\nQuestion: {body.question}",
        },
    ]

    response = await llm.chat(messages, temperature=0.0, max_tokens=1500)

    return AskPDFResponse(
        answer=response.content,
        sources=sources,
    )
