"""Tests for PDF ingestion — chunking logic and tool contract."""

import pytest

from evidentia.schemas.tool_io import PDFChunk, PDFIngestInput, PDFIngestOutput
from evidentia.tools.pdf_ingest import DEFAULT_CHUNK_OVERLAP, PDFIngestTool

# ── Schema tests ────────────────────────────────────────────────────


def test_pdf_ingest_input_accepts_file_path():
    inp = PDFIngestInput(file_path="/tmp/test.pdf")
    assert inp.file_path == "/tmp/test.pdf"
    assert inp.url is None


def test_pdf_ingest_input_accepts_url():
    inp = PDFIngestInput(url="https://example.com/paper.pdf")
    assert inp.url == "https://example.com/paper.pdf"
    assert inp.file_path is None


def test_pdf_ingest_input_accepts_both():
    inp = PDFIngestInput(file_path="/tmp/test.pdf", url="https://example.com/paper.pdf")
    assert inp.file_path is not None
    assert inp.url is not None


def test_pdf_chunk_model():
    chunk = PDFChunk(text="Hello world", page_number=1, chunk_index=0)
    assert chunk.text == "Hello world"
    assert chunk.page_number == 1
    assert chunk.chunk_index == 0


def test_pdf_ingest_output_defaults():
    out = PDFIngestOutput()
    assert out.text == ""
    assert out.page_count == 0
    assert out.metadata == {}
    assert out.chunks == []
    assert out.success is True


def test_pdf_ingest_output_with_chunks():
    chunks = [
        PDFChunk(text="chunk 1", page_number=1, chunk_index=0),
        PDFChunk(text="chunk 2", page_number=1, chunk_index=1),
    ]
    out = PDFIngestOutput(text="full text", page_count=1, chunks=chunks)
    assert len(out.chunks) == 2
    assert out.chunks[0].text == "chunk 1"


# ── Chunking logic ──────────────────────────────────────────────────


class TestChunking:
    """Test the static _create_chunks method directly."""

    def test_empty_pages(self):
        chunks = PDFIngestTool._create_chunks([])
        assert chunks == []

    def test_empty_string_page(self):
        chunks = PDFIngestTool._create_chunks([""])
        assert chunks == []

    def test_single_short_page(self):
        """A page shorter than chunk_size produces exactly one chunk."""
        text = "This is a short page."
        chunks = PDFIngestTool._create_chunks([text])
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].page_number == 1
        assert chunks[0].chunk_index == 0

    def test_long_page_produces_overlapping_chunks(self):
        """A page longer than chunk_size should produce multiple overlapping chunks."""
        text = "a" * 1200  # 1200 chars > DEFAULT_CHUNK_SIZE (500)
        chunks = PDFIngestTool._create_chunks([text])
        assert len(chunks) > 1

        # Check overlap: end of chunk 0 overlaps with start of chunk 1
        c0_end = chunks[0].text
        c1_start = chunks[1].text
        # With 500 size and 100 overlap, chunk 0 covers 0:500, chunk 1 covers 400:900
        # So last 100 chars of chunk 0 == first 100 chars of chunk 1
        assert c0_end[-DEFAULT_CHUNK_OVERLAP:] == c1_start[:DEFAULT_CHUNK_OVERLAP]

    def test_multiple_pages_separate_chunks(self):
        """Chunks should not span pages."""
        pages = ["Page one content.", "Page two content."]
        chunks = PDFIngestTool._create_chunks(pages)
        assert len(chunks) == 2
        assert chunks[0].page_number == 1
        assert chunks[1].page_number == 2

    def test_chunk_indices_sequential(self):
        """Chunk indices should be globally sequential across pages."""
        pages = ["a" * 1200, "b" * 600]
        chunks = PDFIngestTool._create_chunks(pages)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_custom_chunk_size(self):
        text = "x" * 200
        chunks = PDFIngestTool._create_chunks([text], chunk_size=100, overlap=20)
        assert len(chunks) >= 2
        # Each chunk should be at most 100 chars
        for c in chunks:
            assert len(c.text) <= 100

    def test_page_numbers_correct(self):
        pages = ["Alpha", "Beta", "Gamma"]
        chunks = PDFIngestTool._create_chunks(pages)
        assert [c.page_number for c in chunks] == [1, 2, 3]


# ── Tool metadata ───────────────────────────────────────────────────


def test_tool_metadata():
    assert PDFIngestTool.metadata.name == "pdf_ingest"
    assert PDFIngestTool.metadata.category == "ingestion"
    assert PDFIngestTool.metadata.timeout_seconds == 60


# ── Tool execution (requires no external dependencies) ──────────────


@pytest.mark.asyncio
async def test_execute_rejects_no_input():
    """Tool should raise when neither file_path nor url is provided."""
    tool = PDFIngestTool()
    with pytest.raises(Exception, match="Either.*file_path.*url"):
        await tool.execute({"file_path": None, "url": None})


@pytest.mark.asyncio
async def test_execute_rejects_missing_file():
    """Tool should raise when file_path points to a nonexistent file."""
    tool = PDFIngestTool()
    with pytest.raises(Exception, match="File not found|not found"):
        await tool.execute({"file_path": "/nonexistent/path/fake.pdf"})
