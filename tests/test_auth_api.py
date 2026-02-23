"""Tests for Authentication API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from evidentia.api.server import app


def _unauth_client() -> TestClient:
    """Client without auth override — for testing register/login."""
    return TestClient(app, raise_server_exceptions=False)


def test_register():
    """POST /api/v1/auth/register creates account and returns JWT."""
    client = _unauth_client()
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "new@test.com", "password": "securepassword123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user_id"]
    assert data["expires_in"] > 0


def test_register_duplicate():
    """Registering with same email twice returns 409."""
    client = _unauth_client()
    payload = {"email": "dup@test.com", "password": "securepassword123"}
    resp1 = client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201
    resp2 = client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 409


def test_login():
    """POST /api/v1/auth/login with correct credentials returns JWT."""
    client = _unauth_client()
    client.post(
        "/api/v1/auth/register",
        json={"email": "login@test.com", "password": "securepassword123"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "login@test.com", "password": "securepassword123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user_id"]


def test_login_wrong_password():
    """POST /api/v1/auth/login with wrong password returns 401."""
    client = _unauth_client()
    client.post(
        "/api/v1/auth/register",
        json={"email": "wrongpw@test.com", "password": "correctpassword"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@test.com", "password": "wrongpassword1"},
    )
    assert resp.status_code == 401


def test_profile(client):
    """GET /api/v1/auth/me returns current user profile."""
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert "email" in data
    assert data["email"] == "test@example.com"
