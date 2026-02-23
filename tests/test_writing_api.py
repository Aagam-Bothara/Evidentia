"""Tests for Writing Workspace API endpoints."""

from __future__ import annotations


def test_create_document(client):
    """POST /api/v1/writing/documents creates a document and returns it."""
    resp = client.post("/api/v1/writing/documents", json={"title": "My Paper"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "My Paper"
    assert data["id"]
    assert data["status"] == "draft"
    assert data["mode"] == "plain"
    assert data["document_class"] == "article"


def test_list_documents(client):
    """GET /api/v1/writing/documents returns list after creating docs."""
    client.post("/api/v1/writing/documents", json={"title": "Doc 1"})
    client.post("/api/v1/writing/documents", json={"title": "Doc 2"})
    resp = client.get("/api/v1/writing/documents")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 2


def test_list_documents_empty(client):
    """GET /api/v1/writing/documents returns empty list initially."""
    resp = client.get("/api/v1/writing/documents")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_document(client):
    """GET /api/v1/writing/documents/{id} returns the created document."""
    create_resp = client.post("/api/v1/writing/documents", json={"title": "Get Me"})
    doc_id = create_resp.json()["id"]
    resp = client.get(f"/api/v1/writing/documents/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Get Me"


def test_get_document_not_found(client):
    """GET non-existent doc returns 404."""
    resp = client.get("/api/v1/writing/documents/nonexistent")
    assert resp.status_code == 404


def test_update_document(client):
    """PUT /api/v1/writing/documents/{id} updates fields."""
    create_resp = client.post("/api/v1/writing/documents", json={"title": "Original"})
    doc_id = create_resp.json()["id"]
    resp = client.put(
        f"/api/v1/writing/documents/{doc_id}",
        json={"title": "Updated", "plain_content": "Hello world"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Updated"
    assert data["plain_content"] == "Hello world"


def test_delete_document(client):
    """DELETE /api/v1/writing/documents/{id} removes the document."""
    create_resp = client.post("/api/v1/writing/documents", json={"title": "Delete Me"})
    doc_id = create_resp.json()["id"]
    resp = client.delete(f"/api/v1/writing/documents/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    # Verify it's gone
    get_resp = client.get(f"/api/v1/writing/documents/{doc_id}")
    assert get_resp.status_code == 404


def test_list_templates(client):
    """GET /api/v1/writing/templates returns all templates."""
    resp = client.get("/api/v1/writing/templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert isinstance(templates, list)
    assert len(templates) >= 8
    ids = [t["id"] for t in templates]
    assert "article" in ids
    assert "ieee_conference" in ids


def test_get_template(client):
    """GET /api/v1/writing/templates/{id} returns full template with preamble."""
    resp = client.get("/api/v1/writing/templates/article")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "article"
    assert "preamble" in data
    assert "skeleton" in data
    assert "\\documentclass" in data["preamble"]


def test_get_template_not_found(client):
    """GET /api/v1/writing/templates/{id} returns 404 for unknown template."""
    resp = client.get("/api/v1/writing/templates/nonexistent")
    assert resp.status_code == 404


def test_export_document(client):
    """GET /api/v1/writing/documents/{id}/export returns .tex content."""
    create_resp = client.post("/api/v1/writing/documents", json={"title": "Export Test"})
    doc_id = create_resp.json()["id"]
    client.put(
        f"/api/v1/writing/documents/{doc_id}",
        json={"plain_content": "This is my paper content."},
    )
    resp = client.get(f"/api/v1/writing/documents/{doc_id}/export")
    assert resp.status_code == 200
    assert "\\documentclass" in resp.text


def test_create_document_with_template(client):
    """Creating a document with a template_id pre-fills latex_content."""
    resp = client.post(
        "/api/v1/writing/documents",
        json={"title": "From Template", "template_id": "ieee_conference"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["template_id"] == "ieee_conference"
    assert data["latex_content"] != ""
