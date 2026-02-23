"""Tests for Run listing and history endpoints."""

from __future__ import annotations


def test_list_runs_empty(client):
    """GET /api/v1/runs returns empty list when no runs exist."""
    resp = client.get("/api/v1/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_get_run_not_found(client):
    """GET /api/v1/runs/{id} returns 404 for non-existent run."""
    resp = client.get("/api/v1/runs/nonexistent123")
    assert resp.status_code == 404


def test_list_runs_returns_list(client):
    """GET /api/v1/runs is accessible and returns proper structure."""
    resp = client.get("/api/v1/runs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
