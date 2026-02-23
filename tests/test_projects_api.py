"""Tests for Projects CRUD API endpoints."""

from __future__ import annotations


def test_create_project(client):
    """POST /api/v1/projects creates a project."""
    resp = client.post(
        "/api/v1/projects",
        json={"name": "Test Project", "description": "A test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Project"
    assert data["description"] == "A test"
    assert data["id"]
    assert data["run_count"] == 0


def test_list_projects(client):
    """GET /api/v1/projects returns created projects."""
    client.post("/api/v1/projects", json={"name": "Project A"})
    client.post("/api/v1/projects", json={"name": "Project B"})
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["projects"]) == 2


def test_list_projects_empty(client):
    """GET /api/v1/projects returns empty list initially."""
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    assert resp.json()["projects"] == []


def test_get_project(client):
    """GET /api/v1/projects/{id} returns project details."""
    create_resp = client.post(
        "/api/v1/projects",
        json={"name": "Detail Project", "description": "Details"},
    )
    proj_id = create_resp.json()["id"]
    resp = client.get(f"/api/v1/projects/{proj_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Project"
    assert "recent_runs" in data


def test_get_project_not_found(client):
    """GET /api/v1/projects/{id} returns 404 for non-existent project."""
    resp = client.get("/api/v1/projects/nonexistent")
    assert resp.status_code == 404


def test_delete_project(client):
    """DELETE /api/v1/projects/{id} removes the project."""
    create_resp = client.post(
        "/api/v1/projects",
        json={"name": "Delete Me"},
    )
    proj_id = create_resp.json()["id"]
    resp = client.delete(f"/api/v1/projects/{proj_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    # Verify it's gone
    get_resp = client.get(f"/api/v1/projects/{proj_id}")
    assert get_resp.status_code == 404


def test_delete_project_not_found(client):
    """DELETE non-existent project returns 404."""
    resp = client.delete("/api/v1/projects/nonexistent")
    assert resp.status_code == 404
