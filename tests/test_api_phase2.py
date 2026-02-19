"""Tests for Phase 2 API endpoints — upload, export, and tools list."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.api.server import app


# Mock authenticated user for protected endpoints
_mock_user = AuthenticatedUser(user_id=uuid.uuid4(), email="test@example.com")


@pytest.fixture
def client():
    # Override require_auth to bypass DB-backed authentication in tests
    app.dependency_overrides[require_auth] = lambda: _mock_user
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── Tools list ──────────────────────────────────────────────────────


def test_tools_list_includes_pdf_ingest(client):
    resp = client.get("/api/v1/tools")
    assert resp.status_code == 200
    data = resp.json()
    names = [t["name"] for t in data["tools"]]
    assert "pdf_ingest" in names


def test_tools_list_has_category(client):
    resp = client.get("/api/v1/tools")
    data = resp.json()
    pdf_tool = next(t for t in data["tools"] if t["name"] == "pdf_ingest")
    assert pdf_tool["category"] == "document"


# ── PDF upload ──────────────────────────────────────────────────────


def test_upload_rejects_non_pdf(client):
    resp = client.post(
        "/api/v1/upload/pdf",
        files={"file": ("test.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]


# ── PDF list (empty at start) ──────────────────────────────────────


def test_list_pdfs_initially_empty(client):
    resp = client.get("/api/v1/pdfs")
    assert resp.status_code == 200
    data = resp.json()
    assert "pdfs" in data


# ── Delete nonexistent PDF ──────────────────────────────────────────


def test_delete_nonexistent_pdf(client):
    resp = client.delete("/api/v1/pdfs/nonexistent123")
    assert resp.status_code == 404


# ── Export citations ────────────────────────────────────────────────


def test_export_bibtex(client):
    payload = {
        "claims": [
            {
                "statement": "Test claim",
                "confidence": "high",
                "citations": [
                    {
                        "source_id": "s1",
                        "title": "Test Paper",
                        "authors": ["Author, A."],
                        "doi": "10.1234/test",
                        "published_date": "2024",
                    }
                ],
            }
        ],
        "format": "bibtex",
    }
    resp = client.post("/api/v1/export/citations", json=payload)
    assert resp.status_code == 200
    assert "@article{" in resp.text
    assert "Test Paper" in resp.text


def test_export_ris(client):
    payload = {
        "claims": [
            {
                "statement": "Test",
                "confidence": "medium",
                "citations": [
                    {"source_id": "s1", "title": "RIS Paper", "authors": ["Bob"]}
                ],
            }
        ],
        "format": "ris",
    }
    resp = client.post("/api/v1/export/citations", json=payload)
    assert resp.status_code == 200
    assert "TY  - JOUR" in resp.text
    assert "RIS Paper" in resp.text


def test_export_apa(client):
    payload = {
        "claims": [
            {
                "statement": "Test",
                "confidence": "low",
                "citations": [
                    {
                        "source_id": "s1",
                        "title": "APA Paper",
                        "authors": ["Smith, J.", "Doe, K."],
                        "published_date": "2023",
                    }
                ],
            }
        ],
        "format": "apa",
    }
    resp = client.post("/api/v1/export/citations", json=payload)
    assert resp.status_code == 200
    assert "APA Paper" in resp.text
    assert "(2023)" in resp.text


def test_export_json(client):
    payload = {
        "claims": [
            {
                "statement": "JSON claim",
                "confidence": "high",
                "citations": [
                    {"source_id": "s1", "title": "JSON Paper", "authors": []}
                ],
            }
        ],
        "format": "json",
    }
    resp = client.post("/api/v1/export/citations", json=payload)
    assert resp.status_code == 200
    data = json.loads(resp.text)
    assert isinstance(data, list)
    assert data[0]["statement"] == "JSON claim"


def test_export_rejects_empty_claims(client):
    payload = {"claims": [], "format": "bibtex"}
    resp = client.post("/api/v1/export/citations", json=payload)
    assert resp.status_code == 422  # Pydantic validation (min_length=1)


def test_export_rejects_invalid_format(client):
    payload = {
        "claims": [{"statement": "Test", "confidence": "high", "citations": []}],
        "format": "xml",
    }
    resp = client.post("/api/v1/export/citations", json=payload)
    assert resp.status_code == 422  # Pydantic pattern validation
