"""Tests for the systematic review REST API endpoints."""

import uuid

import pytest
from fastapi.testclient import TestClient

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.api.server import app

# ── Auth override ────────────────────────────────────────────────────

_mock_user = AuthenticatedUser(user_id=uuid.uuid4(), email="reviewer@test.com")


@pytest.fixture
def client():
    app.dependency_overrides[require_auth] = lambda: _mock_user
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── Helpers ──────────────────────────────────────────────────────────


def _create_payload(**overrides) -> dict:
    base = {
        "research_question": "What is the effectiveness of CBT for anxiety disorders in adults?",
        "inclusion_criteria": ["RCT design", "Adult participants"],
        "exclusion_criteria": ["Animal studies"],
        "databases": ["pubmed_search", "openalex_search"],
        "max_results_per_database": 50,
    }
    base.update(overrides)
    return base


# ── Create Review ────────────────────────────────────────────────────


def test_create_review(client):
    """POST /api/v1/reviews should create a review and return it."""
    resp = client.post("/api/v1/reviews", json=_create_payload())
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["research_question"] == "What is the effectiveness of CBT for anxiety disorders in adults?"
    assert data["status"] == "pending"


def test_create_review_missing_question(client):
    """Should reject reviews with a missing research question."""
    resp = client.post(
        "/api/v1/reviews",
        json={
            "research_question": "",
            "inclusion_criteria": ["Some criteria"],
        },
    )
    assert resp.status_code == 422  # Validation error


def test_create_review_missing_criteria(client):
    """Should reject reviews with empty inclusion criteria."""
    resp = client.post(
        "/api/v1/reviews",
        json={
            "research_question": "A valid research question for testing purposes here",
            "inclusion_criteria": [],
        },
    )
    assert resp.status_code == 422


# ── List Reviews ─────────────────────────────────────────────────────


def test_list_reviews(client):
    """GET /api/v1/reviews should return list of reviews."""
    # Create two reviews
    client.post("/api/v1/reviews", json=_create_payload())
    client.post(
        "/api/v1/reviews",
        json=_create_payload(research_question="Second question about machine learning for drug discovery"),
    )

    resp = client.get("/api/v1/reviews")
    assert resp.status_code == 200
    data = resp.json()
    assert "reviews" in data
    assert len(data["reviews"]) >= 2


# ── Get Single Review ────────────────────────────────────────────────


def test_get_review(client):
    """GET /api/v1/reviews/{id} should return the review."""
    create_resp = client.post("/api/v1/reviews", json=_create_payload())
    review_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/reviews/{review_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == review_id


def test_get_review_not_found(client):
    """Should return 404 for a non-existent review."""
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/api/v1/reviews/{fake_id}")
    assert resp.status_code == 404


# ── Delete Review ────────────────────────────────────────────────────


def test_delete_review(client):
    """DELETE /api/v1/reviews/{id} should remove the review."""
    create_resp = client.post("/api/v1/reviews", json=_create_payload())
    review_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/v1/reviews/{review_id}")
    assert del_resp.status_code == 200

    # Should be gone
    get_resp = client.get(f"/api/v1/reviews/{review_id}")
    assert get_resp.status_code == 404


def test_delete_review_not_found(client):
    """DELETE for non-existent review should return 404."""
    fake_id = str(uuid.uuid4())
    resp = client.delete(f"/api/v1/reviews/{fake_id}")
    assert resp.status_code == 404


# ── Papers ───────────────────────────────────────────────────────────


def test_get_papers_empty(client):
    """New review should have no papers."""
    create_resp = client.post("/api/v1/reviews", json=_create_payload())
    review_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/reviews/{review_id}/papers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["papers"] == []
    assert data["total"] == 0


def test_get_papers_not_found(client):
    """Papers endpoint for non-existent review should return 404."""
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/api/v1/reviews/{fake_id}/papers")
    assert resp.status_code == 404


# ── PRISMA endpoint ──────────────────────────────────────────────────


def test_get_prisma(client):
    """GET /api/v1/reviews/{id}/prisma should return PRISMA flow data."""
    create_resp = client.post("/api/v1/reviews", json=_create_payload())
    review_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/reviews/{review_id}/prisma")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_identified" in data
    assert "duplicates_removed" in data
    assert "included_count" in data


def test_get_prisma_not_found(client):
    """PRISMA for non-existent review should return 404."""
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/api/v1/reviews/{fake_id}/prisma")
    assert resp.status_code == 404


# ── Export ───────────────────────────────────────────────────────────


def test_export_csv(client):
    """Export should return CSV content as plain text."""
    create_resp = client.post("/api/v1/reviews", json=_create_payload())
    review_id = create_resp.json()["id"]

    resp = client.post(f"/api/v1/reviews/{review_id}/export", json={"format": "csv"})
    assert resp.status_code == 200
    # PlainTextResponse — CSV headers in first line
    assert "Title" in resp.text


def test_export_bibtex(client):
    """Export should return BibTeX content as plain text."""
    create_resp = client.post("/api/v1/reviews", json=_create_payload())
    review_id = create_resp.json()["id"]

    resp = client.post(f"/api/v1/reviews/{review_id}/export", json={"format": "bibtex"})
    assert resp.status_code == 200
    # Empty review has no included papers, so BibTeX is empty
    assert isinstance(resp.text, str)


def test_export_ris(client):
    """Export should return RIS content as plain text."""
    create_resp = client.post("/api/v1/reviews", json=_create_payload())
    review_id = create_resp.json()["id"]

    resp = client.post(f"/api/v1/reviews/{review_id}/export", json={"format": "ris"})
    assert resp.status_code == 200
    assert isinstance(resp.text, str)


def test_export_not_found(client):
    """Export for non-existent review should return 404."""
    fake_id = str(uuid.uuid4())
    resp = client.post(f"/api/v1/reviews/{fake_id}/export", json={"format": "csv"})
    assert resp.status_code == 404


# ── Exporter unit tests ─────────────────────────────────────────────


def test_csv_export_includes_headers():
    """CSV export should have proper column headers."""
    from evidentia.review.exporter import ReviewExporter
    from evidentia.review.models import PaperRecord

    papers = [
        PaperRecord(
            title="Test Paper",
            authors=["Author A", "Author B"],
            doi="10.1234/test",
            source_database="pubmed_search",
            screening_decision="include",
        )
    ]
    csv_str = ReviewExporter.to_csv(papers)
    assert "Title" in csv_str
    assert "Authors" in csv_str
    assert "DOI" in csv_str
    assert "Test Paper" in csv_str
    assert "Author A; Author B" in csv_str


def test_csv_export_excludes_excluded_by_default():
    """CSV export should skip excluded papers unless include_excluded=True."""
    from evidentia.review.exporter import ReviewExporter
    from evidentia.review.models import PaperRecord

    papers = [
        PaperRecord(title="Included", screening_decision="include"),
        PaperRecord(title="Excluded", screening_decision="exclude"),
    ]
    csv_no_excluded = ReviewExporter.to_csv(papers, include_excluded=False)
    csv_with_excluded = ReviewExporter.to_csv(papers, include_excluded=True)

    assert "Included" in csv_no_excluded
    assert "Excluded" not in csv_no_excluded
    assert "Excluded" in csv_with_excluded


def test_csv_export_skips_duplicates():
    """CSV export should always skip duplicate papers."""
    from evidentia.review.exporter import ReviewExporter
    from evidentia.review.models import PaperRecord

    papers = [
        PaperRecord(title="Original", screening_decision="include"),
        PaperRecord(title="Duplicate", screening_decision="include", is_duplicate=True),
    ]
    csv_str = ReviewExporter.to_csv(papers)
    assert "Original" in csv_str
    assert "Duplicate" not in csv_str


def test_bibtex_only_includes_included():
    """BibTeX export should only contain included papers."""
    from evidentia.review.exporter import ReviewExporter
    from evidentia.review.models import PaperRecord

    papers = [
        PaperRecord(title="Included Paper", screening_decision="include", authors=["Author"]),
        PaperRecord(title="Excluded Paper", screening_decision="exclude"),
        PaperRecord(title="Uncertain Paper", screening_decision="uncertain"),
    ]
    bib = ReviewExporter.to_bibtex(papers)
    assert "Included Paper" in bib
    assert "Excluded Paper" not in bib
    assert "Uncertain Paper" not in bib


def test_ris_only_includes_included():
    """RIS export should only contain included papers."""
    from evidentia.review.exporter import ReviewExporter
    from evidentia.review.models import PaperRecord

    papers = [
        PaperRecord(title="Included Paper", screening_decision="include", authors=["Author"]),
        PaperRecord(title="Excluded Paper", screening_decision="exclude"),
    ]
    ris = ReviewExporter.to_ris(papers)
    assert "Included Paper" in ris
    assert "Excluded Paper" not in ris
    assert "TY  - JOUR" in ris
    assert "ER  - " in ris


def test_bibtex_empty_papers():
    """BibTeX with no included papers should return empty string."""
    from evidentia.review.exporter import ReviewExporter

    assert ReviewExporter.to_bibtex([]) == ""


def test_ris_empty_papers():
    """RIS with no included papers should return empty string."""
    from evidentia.review.exporter import ReviewExporter

    assert ReviewExporter.to_ris([]) == ""


def test_extract_year():
    """Year extraction from various date formats."""
    from evidentia.review.exporter import ReviewExporter

    assert ReviewExporter._extract_year("2024-01-15") == "2024"
    assert ReviewExporter._extract_year("2023-06") == "2023"
    assert ReviewExporter._extract_year("2022") == "2022"
    assert ReviewExporter._extract_year(None) == ""
    assert ReviewExporter._extract_year("") == ""
    assert ReviewExporter._extract_year("no year") == ""
