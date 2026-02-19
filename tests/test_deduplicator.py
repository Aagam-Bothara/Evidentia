"""Tests for the systematic review deduplicator."""

from evidentia.review.deduplicator import Deduplicator
from evidentia.review.models import PaperRecord

# ── Helpers ──────────────────────────────────────────────────────────


def _paper(
    title: str = "Test Paper",
    doi: str | None = None,
    source_db: str = "pubmed_search",
    source_id: str | None = None,
) -> PaperRecord:
    return PaperRecord(
        title=title,
        doi=doi,
        source_database=source_db,
        source_id=source_id or title[:10],
    )


# ── Exact DOI deduplication ──────────────────────────────────────────


def test_exact_doi_match():
    """Papers with the same DOI should be deduplicated."""
    dedup = Deduplicator()
    papers = [
        _paper("Paper A", doi="10.1234/abc", source_db="pubmed_search", source_id="pm1"),
        _paper("Paper B", doi="10.1234/abc", source_db="openalex_search", source_id="oa1"),
    ]
    unique, dups = dedup.deduplicate(papers)
    assert len(unique) == 1
    assert len(dups) == 1
    assert dups[0].is_duplicate is True
    assert dups[0].duplicate_of == "pm1"


def test_doi_case_insensitive():
    """DOI matching should be case-insensitive."""
    dedup = Deduplicator()
    papers = [
        _paper("Paper A", doi="10.1234/ABC"),
        _paper("Paper B", doi="10.1234/abc"),
    ]
    unique, dups = dedup.deduplicate(papers)
    assert len(unique) == 1
    assert len(dups) == 1


def test_doi_whitespace_stripped():
    """DOI matching should strip leading/trailing whitespace."""
    dedup = Deduplicator()
    papers = [
        _paper("Paper A", doi="10.1234/test"),
        _paper("Paper B", doi=" 10.1234/test "),
    ]
    unique, dups = dedup.deduplicate(papers)
    assert len(unique) == 1
    assert len(dups) == 1


def test_different_dois_not_deduplicated():
    """Papers with different DOIs should not be deduplicated."""
    dedup = Deduplicator()
    papers = [
        _paper("Paper A", doi="10.1234/aaa"),
        _paper("Paper B", doi="10.1234/bbb"),
    ]
    unique, dups = dedup.deduplicate(papers)
    assert len(unique) == 2
    assert len(dups) == 0


# ── Fuzzy title deduplication ────────────────────────────────────────


def test_fuzzy_title_match():
    """Nearly identical titles should be deduplicated via Jaccard."""
    dedup = Deduplicator()
    papers = [
        _paper("A randomized controlled trial of mindfulness based stress reduction for chronic pain management"),
        _paper("Randomized controlled trial of mindfulness based stress reduction for chronic pain management"),
    ]
    # Jaccard: 12/13 ≈ 0.923 > 0.85 threshold
    unique, dups = dedup.deduplicate(papers)
    assert len(unique) == 1
    assert len(dups) == 1
    assert dups[0].is_duplicate is True


def test_different_titles_not_deduplicated():
    """Clearly different titles should NOT be matched."""
    dedup = Deduplicator()
    papers = [
        _paper("Machine learning for drug discovery"),
        _paper("Climate change effects on marine biodiversity"),
    ]
    unique, dups = dedup.deduplicate(papers)
    assert len(unique) == 2
    assert len(dups) == 0


def test_short_titles_not_false_positive():
    """Short common titles should not spuriously match."""
    dedup = Deduplicator()
    papers = [
        _paper("A review"),
        _paper("A study"),
    ]
    unique, dups = dedup.deduplicate(papers)
    assert len(unique) == 2


def test_custom_threshold():
    """Lower threshold should match more aggressively."""
    dedup = Deduplicator(title_threshold=0.5)
    papers = [
        _paper("Advances in deep learning for NLP"),
        _paper("Advances in machine learning for NLP"),
    ]
    unique, dups = dedup.deduplicate(papers)
    assert len(unique) == 1
    assert len(dups) == 1


# ── Mixed deduplication ──────────────────────────────────────────────


def test_mixed_doi_and_title_dedup():
    """DOI match and title match should both work in the same run."""
    dedup = Deduplicator()
    papers = [
        _paper("Paper One: A Novel Approach to Systematic Reviews", doi="10.1234/one", source_id="s1"),
        _paper("Paper Two: A Novel Approach to Systematic Reviews", doi="10.1234/one", source_id="s2"),  # DOI dup
        _paper("Paper One A Novel Approach to Systematic Reviews", source_id="s3"),  # title dup (no DOI)
        _paper("Completely Different Paper About Climate Change", source_id="s4"),  # unique
    ]
    unique, dups = dedup.deduplicate(papers)
    assert len(unique) == 2  # Paper One + Climate Change
    assert len(dups) == 2  # DOI dup + title dup


# ── Edge cases ───────────────────────────────────────────────────────


def test_empty_list():
    """Empty paper list should return empty results."""
    dedup = Deduplicator()
    unique, dups = dedup.deduplicate([])
    assert unique == []
    assert dups == []


def test_single_paper():
    """Single paper should always be unique."""
    dedup = Deduplicator()
    papers = [_paper("Only Paper")]
    unique, dups = dedup.deduplicate(papers)
    assert len(unique) == 1
    assert len(dups) == 0


def test_papers_without_doi_use_title_only():
    """Papers without DOIs should still be deduplicated by title."""
    dedup = Deduplicator()
    papers = [
        _paper("The role of CRISPR in gene therapy", source_id="s1"),
        _paper("The role of CRISPR in gene therapy", source_id="s2"),
    ]
    unique, dups = dedup.deduplicate(papers)
    assert len(unique) == 1
    assert len(dups) == 1


def test_triple_duplicate():
    """Three copies of the same paper from different databases."""
    dedup = Deduplicator()
    papers = [
        _paper(
            "Systematic review of exercise interventions",
            doi="10.1234/ex",
            source_db="pubmed_search",
            source_id="pm1",
        ),
        _paper(
            "Systematic review of exercise interventions",
            doi="10.1234/ex",
            source_db="openalex_search",
            source_id="oa1",
        ),
        _paper(
            "Systematic review of exercise interventions",
            doi="10.1234/ex",
            source_db="semantic_scholar",
            source_id="ss1",
        ),
    ]
    unique, dups = dedup.deduplicate(papers)
    assert len(unique) == 1
    assert len(dups) == 2


# ── Tokenizer and Jaccard internals ────────────────────────────────


def test_tokenize_strips_punctuation():
    words = Deduplicator._tokenize("Hello, World! It's a test.")
    assert "hello" in words
    assert "world" in words
    assert "its" in words  # apostrophe stripped


def test_jaccard_identical():
    assert Deduplicator._jaccard({"a", "b", "c"}, {"a", "b", "c"}) == 1.0


def test_jaccard_disjoint():
    assert Deduplicator._jaccard({"a", "b"}, {"c", "d"}) == 0.0


def test_jaccard_partial():
    score = Deduplicator._jaccard({"a", "b", "c"}, {"a", "b", "d"})
    assert 0.4 < score < 0.6  # 2/4 = 0.5


def test_jaccard_empty_sets():
    assert Deduplicator._jaccard(set(), {"a"}) == 0.0
    assert Deduplicator._jaccard(set(), set()) == 0.0
