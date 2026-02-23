"""Shared test fixtures for the Evidentia test suite."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.api.server import app

# ── Reusable mock user ─────────────────────────────────────────────
_mock_user = AuthenticatedUser(user_id=uuid.uuid4(), email="test@example.com")


@pytest.fixture
def mock_user() -> AuthenticatedUser:
    """Return a mock authenticated user for testing."""
    return _mock_user


@pytest.fixture
def client(mock_user: AuthenticatedUser):
    """Synchronous test client with auth override."""
    app.dependency_overrides[require_auth] = lambda: mock_user
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clear_in_memory_stores():
    """Clear all in-memory stores between tests to ensure isolation."""
    yield

    # Auth store
    try:
        from evidentia.api.routes.auth import _user_store

        _user_store.clear()
    except ImportError:
        pass

    # Project stores
    try:
        from evidentia.api.routes.projects import (
            _project_collaborators,
            _project_runs,
            _project_store,
        )

        _project_store.clear()
        _project_runs.clear()
        _project_collaborators.clear()
    except ImportError:
        pass

    # Writing store
    try:
        from evidentia.api.routes.writing import _doc_store

        _doc_store.clear()
    except ImportError:
        pass

    # Query/Run stores
    try:
        from evidentia.api.routes.query import (
            _pending_runs,
            _run_claims,
            _run_fingerprints,
            _run_queries,
        )

        _pending_runs.clear()
        _run_fingerprints.clear()
        _run_claims.clear()
        _run_queries.clear()
    except ImportError:
        pass

    # Upload/PDF stores
    try:
        from evidentia.api.routes.upload import _pdf_store

        _pdf_store.clear()
    except ImportError:
        pass

    # Review stores
    try:
        from evidentia.api.routes.reviews import _review_papers_store, _review_store

        _review_store.clear()
        _review_papers_store.clear()
    except ImportError:
        pass

    # Chat stores
    try:
        from evidentia.api.routes.chat import _chat_store

        _chat_store.clear()
    except ImportError:
        pass

    try:
        from evidentia.api.server import _chat_msg_store

        _chat_msg_store.clear()
    except ImportError:
        pass

    # Team stores
    try:
        from evidentia.api.routes.teams import _team_store

        _team_store.clear()
    except ImportError:
        pass

    # Annotation stores
    try:
        from evidentia.api.routes.annotations import _annotation_store

        _annotation_store.clear()
    except ImportError:
        pass
