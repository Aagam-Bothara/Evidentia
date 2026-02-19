"""PDF ingestion tool — extracts text, metadata, and overlapping chunks from PDFs."""

from __future__ import annotations

import os
import tempfile
from typing import Any, ClassVar

import httpx

from evidentia.core.exceptions import ToolExecutionError
from evidentia.schemas.tool_io import PDFChunk, PDFIngestInput, PDFIngestOutput
from evidentia.tools.base import BaseTool, ToolMetadata

# Default chunking parameters
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 100


def _check_pymupdf() -> bool:
    """Return True if pymupdf (fitz) is importable."""
    try:
        import fitz  # noqa: F401

        return True
    except ImportError:
        return False


class PDFIngestTool(BaseTool):
    """Extract text, metadata, and overlapping chunks from a PDF.

    Supports both local file paths and remote URLs.  Uses pymupdf (fitz) for
    extraction; raises a clear error when the optional dependency is missing.
    """

    metadata: ClassVar[ToolMetadata] = ToolMetadata(
        name="pdf_ingest",
        description="Extract text, metadata, and overlapping chunks from a PDF document.",
        category="ingestion",
        input_schema=PDFIngestInput.model_json_schema(),
        output_schema=PDFIngestOutput.model_json_schema(),
        timeout_seconds=60,
        requires_auth=False,
    )

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        params = PDFIngestInput.model_validate(input_data)

        if not params.file_path and not params.url:
            raise ToolExecutionError(
                "Either 'file_path' or 'url' must be provided.",
                tool_name=self.metadata.name,
            )

        if not _check_pymupdf():
            raise ToolExecutionError(
                "pymupdf is not installed. Install it with: pip install 'evidentia[pdf]'",
                tool_name=self.metadata.name,
            )

        # Resolve the PDF bytes to a local file path
        pdf_path = await self._resolve_pdf_path(params)

        try:
            page_texts, page_count, doc_metadata = self._extract_with_pymupdf(pdf_path)
        finally:
            # Clean up temp file if we downloaded from a URL
            if params.url and not params.file_path and os.path.exists(pdf_path):
                os.unlink(pdf_path)

        full_text = "\n\n".join(page_texts)
        chunks = self._create_chunks(page_texts)

        output = PDFIngestOutput(
            text=full_text,
            page_count=page_count,
            metadata=doc_metadata,
            chunks=chunks,
        )
        return output.model_dump()

    # ── Internal helpers ─────────────────────────────────────────────

    async def _resolve_pdf_path(self, params: PDFIngestInput) -> str:
        """Return a local file path, downloading from URL if necessary."""
        if params.file_path:
            path = params.file_path
            if not os.path.isfile(path):
                raise ToolExecutionError(
                    f"File not found: {path}",
                    tool_name=self.metadata.name,
                )
            return path

        # Download from URL to a temp file
        assert params.url is not None
        return await self._download_pdf(params.url)

    async def _download_pdf(self, url: str) -> str:
        """Download a PDF from *url* and return the path to a temp file."""
        async with httpx.AsyncClient(
            timeout=self.metadata.timeout_seconds,
            follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ToolExecutionError(
                    f"Failed to download PDF from {url}: {exc}",
                    tool_name=self.metadata.name,
                ) from exc

        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
            raise ToolExecutionError(
                f"URL does not appear to point to a PDF (content-type: {content_type}).",
                tool_name=self.metadata.name,
            )

        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        try:
            os.write(fd, resp.content)
        finally:
            os.close(fd)

        return tmp_path

    def _extract_with_pymupdf(
        self, pdf_path: str
    ) -> tuple[list[str], int, dict[str, Any]]:
        """Extract per-page text and document metadata using pymupdf (fitz).

        Returns:
            A tuple of (page_texts, page_count, metadata_dict).
        """
        import fitz  # pymupdf — guarded by _check_pymupdf()

        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:
            raise ToolExecutionError(
                f"Failed to open PDF: {exc}",
                tool_name=self.metadata.name,
            ) from exc

        try:
            page_texts: list[str] = []
            for page in doc:
                text = page.get_text("text")
                page_texts.append(text.strip())

            # Build metadata from the document info dict
            raw_meta = doc.metadata or {}
            metadata: dict[str, Any] = {
                "title": raw_meta.get("title", "") or "",
                "author": raw_meta.get("author", "") or "",
                "subject": raw_meta.get("subject", "") or "",
                "creator": raw_meta.get("creator", "") or "",
                "producer": raw_meta.get("producer", "") or "",
                "creation_date": raw_meta.get("creationDate", "") or "",
                "modification_date": raw_meta.get("modDate", "") or "",
                "page_count": len(doc),
            }

            page_count = len(doc)
        finally:
            doc.close()

        return page_texts, page_count, metadata

    @staticmethod
    def _create_chunks(
        page_texts: list[str],
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> list[PDFChunk]:
        """Split page texts into overlapping character-based chunks.

        Each chunk records the page it originated from and a sequential index.
        Chunks are created *within* each page — a single chunk never spans two
        pages, which keeps page-number provenance clean.
        """
        chunks: list[PDFChunk] = []
        chunk_index = 0

        for page_number, page_text in enumerate(page_texts, start=1):
            if not page_text:
                continue

            start = 0
            while start < len(page_text):
                end = start + chunk_size
                chunk_text = page_text[start:end].strip()

                if chunk_text:
                    chunks.append(
                        PDFChunk(
                            text=chunk_text,
                            page_number=page_number,
                            chunk_index=chunk_index,
                        )
                    )
                    chunk_index += 1

                # Advance by (chunk_size - overlap) so consecutive chunks overlap
                start += chunk_size - overlap

        return chunks
