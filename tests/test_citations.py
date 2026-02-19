"""Tests for citation export — BibTeX, RIS, APA, JSON."""

import json

import pytest

from evidentia.core.models import Citation, Claim, ClaimConfidence, EvidenceSpan
from evidentia.export.citations import CitationExporter


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def sample_claims() -> list[Claim]:
    return [
        Claim(
            id="c1",
            statement="Transformers outperform RNNs on machine translation.",
            confidence=ClaimConfidence.HIGH,
            citations=[
                Citation(
                    source_id="s1",
                    title="Attention Is All You Need",
                    authors=["Vaswani, A.", "Shazeer, N.", "Parmar, N."],
                    url="https://arxiv.org/abs/1706.03762",
                    doi="10.5555/3295222.3295349",
                    published_date="2017-06-12",
                ),
            ],
            evidence_spans=[
                EvidenceSpan(source_id="s1", text="The Transformer model achieves state-of-the-art..."),
            ],
        ),
        Claim(
            id="c2",
            statement="BERT uses bidirectional pre-training.",
            confidence=ClaimConfidence.MEDIUM,
            citations=[
                Citation(
                    source_id="s2",
                    title="BERT: Pre-training of Deep Bidirectional Transformers",
                    authors=["Devlin, J.", "Chang, M."],
                    url="https://arxiv.org/abs/1810.04805",
                    doi="10.18653/v1/N19-1423",
                    published_date="2019",
                ),
                Citation(
                    source_id="s3",
                    title="Language Models are Few-Shot Learners",
                    authors=["Brown, T."],
                    url="https://arxiv.org/abs/2005.14165",
                    published_date="2020-05",
                ),
            ],
        ),
    ]


@pytest.fixture
def empty_claims() -> list[Claim]:
    return []


@pytest.fixture
def claim_no_citations() -> list[Claim]:
    return [
        Claim(
            id="c3",
            statement="A claim with no citations.",
            confidence=ClaimConfidence.LOW,
            citations=[],
        ),
    ]


# ── BibTeX ──────────────────────────────────────────────────────────


def test_bibtex_basic(sample_claims):
    bib = CitationExporter.to_bibtex(sample_claims)
    assert "@article{evidentia_1," in bib
    assert "Attention Is All You Need" in bib
    assert "Vaswani, A. and Shazeer, N. and Parmar, N." in bib
    assert "year = {2017}" in bib
    assert "doi = {10.5555/3295222.3295349}" in bib


def test_bibtex_multiple_entries(sample_claims):
    bib = CitationExporter.to_bibtex(sample_claims)
    assert bib.count("@article{") == 3  # 3 unique citations


def test_bibtex_empty(empty_claims):
    assert CitationExporter.to_bibtex(empty_claims) == ""


def test_bibtex_no_citations(claim_no_citations):
    assert CitationExporter.to_bibtex(claim_no_citations) == ""


# ── RIS ─────────────────────────────────────────────────────────────


def test_ris_basic(sample_claims):
    ris = CitationExporter.to_ris(sample_claims)
    assert "TY  - JOUR" in ris
    assert "TI  - Attention Is All You Need" in ris
    assert "AU  - Vaswani, A." in ris
    assert "DO  - 10.5555/3295222.3295349" in ris
    assert "PY  - 2017" in ris
    assert "ER  - " in ris


def test_ris_multiple_entries(sample_claims):
    ris = CitationExporter.to_ris(sample_claims)
    assert ris.count("TY  - JOUR") == 3


def test_ris_empty(empty_claims):
    assert CitationExporter.to_ris(empty_claims) == ""


# ── APA ─────────────────────────────────────────────────────────────


def test_apa_basic(sample_claims):
    apa = CitationExporter.to_apa(sample_claims)
    assert "Vaswani, A." in apa
    assert "(2017)" in apa
    assert "Attention Is All You Need" in apa
    assert "doi.org" in apa


def test_apa_single_author():
    claims = [
        Claim(
            id="c1",
            statement="Test",
            citations=[
                Citation(
                    source_id="s1",
                    title="Solo Paper",
                    authors=["Author, A."],
                    published_date="2023",
                ),
            ],
        ),
    ]
    apa = CitationExporter.to_apa(claims)
    assert "Author, A. (2023)" in apa


def test_apa_two_authors():
    claims = [
        Claim(
            id="c1",
            statement="Test",
            citations=[
                Citation(
                    source_id="s1",
                    title="Duo Paper",
                    authors=["Alpha, A.", "Beta, B."],
                    published_date="2022",
                ),
            ],
        ),
    ]
    apa = CitationExporter.to_apa(claims)
    assert "Alpha, A., & Beta, B." in apa


def test_apa_no_date():
    claims = [
        Claim(
            id="c1",
            statement="Test",
            citations=[
                Citation(source_id="s1", title="Dateless Paper", authors=["Author"]),
            ],
        ),
    ]
    apa = CitationExporter.to_apa(claims)
    assert "(n.d.)" in apa


def test_apa_empty(empty_claims):
    assert CitationExporter.to_apa(empty_claims) == ""


# ── JSON ────────────────────────────────────────────────────────────


def test_json_basic(sample_claims):
    raw = CitationExporter.to_json(sample_claims)
    data = json.loads(raw)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["statement"] == "Transformers outperform RNNs on machine translation."
    assert data[0]["confidence"] == "high"
    assert len(data[0]["citations"]) == 1


def test_json_serializable(sample_claims):
    raw = CitationExporter.to_json(sample_claims)
    # Should not raise
    parsed = json.loads(raw)
    # Round-trip
    json.dumps(parsed)


def test_json_empty(empty_claims):
    raw = CitationExporter.to_json(empty_claims)
    assert json.loads(raw) == []


# ── Deduplication ───────────────────────────────────────────────────


def test_dedup_by_doi():
    """Same DOI across two claims should be deduplicated."""
    shared_doi = "10.1234/test"
    claims = [
        Claim(
            id="c1",
            statement="Claim A",
            citations=[Citation(source_id="s1", title="Paper", doi=shared_doi)],
        ),
        Claim(
            id="c2",
            statement="Claim B",
            citations=[Citation(source_id="s1", title="Paper", doi=shared_doi)],
        ),
    ]
    bib = CitationExporter.to_bibtex(claims)
    assert bib.count("@article{") == 1


def test_dedup_by_url():
    """Same URL across two claims should be deduplicated."""
    shared_url = "https://example.com/paper"
    claims = [
        Claim(
            id="c1",
            statement="Claim A",
            citations=[Citation(source_id="s1", title="Paper A", url=shared_url)],
        ),
        Claim(
            id="c2",
            statement="Claim B",
            citations=[Citation(source_id="s2", title="Paper A", url=shared_url)],
        ),
    ]
    ris = CitationExporter.to_ris(claims)
    assert ris.count("TY  - JOUR") == 1


def test_dedup_doi_case_insensitive():
    """DOI deduplication should be case-insensitive."""
    claims = [
        Claim(
            id="c1",
            statement="Claim A",
            citations=[Citation(source_id="s1", title="Paper", doi="10.1234/ABC")],
        ),
        Claim(
            id="c2",
            statement="Claim B",
            citations=[Citation(source_id="s1", title="Paper", doi="10.1234/abc")],
        ),
    ]
    unique = CitationExporter._deduplicate_citations(claims)
    assert len(unique) == 1


# ── Year extraction ─────────────────────────────────────────────────


def test_extract_year_full_date():
    assert CitationExporter._extract_year("2024-01-15") == "2024"


def test_extract_year_year_month():
    assert CitationExporter._extract_year("2023-06") == "2023"


def test_extract_year_only():
    assert CitationExporter._extract_year("2022") == "2022"


def test_extract_year_none():
    assert CitationExporter._extract_year(None) == ""


def test_extract_year_empty():
    assert CitationExporter._extract_year("") == ""


def test_extract_year_no_match():
    assert CitationExporter._extract_year("no year here") == ""
