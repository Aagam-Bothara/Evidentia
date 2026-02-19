"""Tests for vector store, embeddings, and hybrid search."""

import math

import pytest

from evidentia.core.models import Source, SourceType
from evidentia.retrieval.vector_store import VectorSearchResult, VectorStore

# ── Cosine similarity (pure math, no model needed) ──────────────────


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert VectorStore._cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert VectorStore._cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert VectorStore._cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        assert VectorStore._cosine_similarity(a, b) == 0.0

    def test_known_angle(self):
        """45 degree angle -> cosine ~0.707"""
        a = [1.0, 0.0]
        b = [1.0, 1.0]
        expected = 1.0 / math.sqrt(2)
        assert VectorStore._cosine_similarity(a, b) == pytest.approx(expected, rel=1e-6)


# ── VectorStore with mock embeddings ────────────────────────────────


class FakeEmbedder:
    """Deterministic embedder for testing — uses character frequency as a vector."""

    def __init__(self):
        self._dim = 26  # one dimension per letter a-z

    def embed(self, text: str) -> list[float]:
        return self._char_vector(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._char_vector(t) for t in texts]

    @property
    def dimension(self) -> int:
        return self._dim

    def _char_vector(self, text: str) -> list[float]:
        """Simple character frequency vector (a=0, b=1, ... z=25)."""
        vec = [0.0] * 26
        for ch in text.lower():
            if "a" <= ch <= "z":
                vec[ord(ch) - ord("a")] += 1.0
        # Normalize
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


@pytest.fixture
def fake_vector_store():
    """VectorStore with a deterministic fake embedder."""
    store = VectorStore.__new__(VectorStore)
    store._embedder = FakeEmbedder()
    store._vectors = []
    store._id_index = {}
    return store


@pytest.fixture
def sample_docs():
    return [
        Source(
            id="doc1",
            source_type=SourceType.PAPER,
            title="Attention and Transformers",
            content="attention mechanism transformer architecture neural network",
        ),
        Source(
            id="doc2",
            source_type=SourceType.PAPER,
            title="Recurrent Neural Networks",
            content="recurrent network lstm gated hidden state sequence",
        ),
        Source(
            id="doc3",
            source_type=SourceType.WEBPAGE,
            title="Python Programming",
            content="python programming language code function class module",
        ),
    ]


@pytest.mark.asyncio
async def test_add_documents(fake_vector_store, sample_docs):
    await fake_vector_store.add_documents(sample_docs)
    assert fake_vector_store.count == 3


@pytest.mark.asyncio
async def test_add_documents_empty(fake_vector_store):
    await fake_vector_store.add_documents([])
    assert fake_vector_store.count == 0


@pytest.mark.asyncio
async def test_search_returns_results(fake_vector_store, sample_docs):
    await fake_vector_store.add_documents(sample_docs)
    results = await fake_vector_store.search("attention transformer", top_k=3)
    assert len(results) > 0
    assert isinstance(results[0], VectorSearchResult)
    assert results[0].score > 0


@pytest.mark.asyncio
async def test_search_empty_store(fake_vector_store):
    results = await fake_vector_store.search("anything")
    assert results == []


@pytest.mark.asyncio
async def test_search_top_k_limit(fake_vector_store, sample_docs):
    await fake_vector_store.add_documents(sample_docs)
    results = await fake_vector_store.search("test", top_k=1)
    assert len(results) <= 1


@pytest.mark.asyncio
async def test_search_scores_descending(fake_vector_store, sample_docs):
    await fake_vector_store.add_documents(sample_docs)
    results = await fake_vector_store.search("neural network", top_k=3)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_upsert_replaces_document(fake_vector_store, sample_docs):
    await fake_vector_store.add_documents(sample_docs)
    assert fake_vector_store.count == 3

    # Add a document with the same id — should replace, not duplicate
    updated_doc = Source(
        id="doc1",
        source_type=SourceType.PAPER,
        title="Updated Attention Paper",
        content="new content about attention",
    )
    await fake_vector_store.add_documents([updated_doc])
    assert fake_vector_store.count == 3  # Still 3, not 4


@pytest.mark.asyncio
async def test_add_chunks(fake_vector_store):
    chunks = [
        {"doc_id": "chunk_1", "text": "first chunk of text", "title": "Paper A"},
        {"doc_id": "chunk_2", "text": "second chunk of text", "title": "Paper A"},
    ]
    await fake_vector_store.add_chunks(chunks)
    assert fake_vector_store.count == 2


@pytest.mark.asyncio
async def test_search_by_vector(fake_vector_store, sample_docs):
    await fake_vector_store.add_documents(sample_docs)
    # Create a query vector using the fake embedder
    query_vec = fake_vector_store._embedder.embed("attention")
    results = await fake_vector_store.search_by_vector(query_vec, top_k=2)
    assert len(results) <= 2
    assert all(isinstance(r, VectorSearchResult) for r in results)


# ── Hybrid search (RRF) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hybrid_search_combines_results(fake_vector_store, sample_docs):
    from evidentia.retrieval.hybrid_search import HybridSearchEngine

    engine = HybridSearchEngine()
    engine.index(sample_docs)
    await fake_vector_store.add_documents(sample_docs)

    results = await engine.search_hybrid(
        "attention neural network",
        vector_store=fake_vector_store,
        top_k=3,
    )
    assert len(results) > 0
    assert all(r.match_type == "hybrid" for r in results)


@pytest.mark.asyncio
async def test_hybrid_search_scores_descending(fake_vector_store, sample_docs):
    from evidentia.retrieval.hybrid_search import HybridSearchEngine

    engine = HybridSearchEngine()
    engine.index(sample_docs)
    await fake_vector_store.add_documents(sample_docs)

    results = await engine.search_hybrid(
        "transformer architecture",
        vector_store=fake_vector_store,
        top_k=3,
    )
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
