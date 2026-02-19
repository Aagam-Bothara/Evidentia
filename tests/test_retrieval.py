"""Tests for the retrieval system."""

import pytest

from evidentia.core.models import Source, SourceType
from evidentia.retrieval.hybrid_search import HybridSearchEngine
from evidentia.retrieval.reranker import Reranker
from evidentia.retrieval.store import DocumentStore


@pytest.fixture
def sample_sources() -> list[Source]:
    return [
        Source(
            source_type=SourceType.PAPER,
            title="Attention Is All You Need",
            content=(
                "The dominant sequence transduction models are based on"
                " complex recurrent or convolutional neural networks."
                " We propose a new simple network architecture the"
                " Transformer based solely on attention mechanisms."
            ),
        ),
        Source(
            source_type=SourceType.PAPER,
            title="BERT: Pre-training of Deep Bidirectional Transformers",
            content=(
                "We introduce BERT a new language representation model."
                " BERT is designed to pre-train deep bidirectional"
                " representations from unlabeled text."
            ),
        ),
        Source(
            source_type=SourceType.WEBPAGE,
            title="Python Tutorial",
            content=(
                "Python is a programming language that lets you work quickly and integrate systems more effectively."
            ),
        ),
    ]


def test_bm25_search(sample_sources):
    engine = HybridSearchEngine()
    engine.index(sample_sources)
    results = engine.search_bm25("transformer attention mechanism", top_k=5)
    assert len(results) > 0
    assert results[0].source.title == "Attention Is All You Need"


def test_bm25_no_results(sample_sources):
    engine = HybridSearchEngine()
    engine.index(sample_sources)
    results = engine.search_bm25("quantum computing entanglement")
    assert len(results) == 0


def test_reranker_boosts_title_matches(sample_sources):
    engine = HybridSearchEngine()
    engine.index(sample_sources)
    results = engine.search_bm25("BERT transformer", top_k=5)

    reranker = Reranker(title_boost=2.0)
    reranked = reranker.rerank("BERT", results)
    if reranked:
        assert "BERT" in reranked[0].source.title


@pytest.mark.asyncio
async def test_document_store_add_and_get():
    store = DocumentStore()
    source = Source(
        source_type=SourceType.PAPER,
        title="Test Paper",
        content="Some content here.",
    )
    stored = await store.add(source)
    assert stored.content_hash is not None

    fetched = await store.get(stored.id)
    assert fetched is not None
    assert fetched.title == "Test Paper"


@pytest.mark.asyncio
async def test_document_store_deduplication():
    store = DocumentStore()
    source1 = Source(source_type=SourceType.PAPER, title="Paper A", content="Same content")
    source2 = Source(source_type=SourceType.PAPER, title="Paper B", content="Same content")

    stored1 = await store.add(source1)
    stored2 = await store.add(source2)

    # Should return the same document (deduplicated)
    assert stored1.id == stored2.id
    docs = await store.list_all()
    assert len(docs) == 1
