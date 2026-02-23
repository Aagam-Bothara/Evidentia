"""Project endpoints — CRUD for research projects."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# In-memory fallback when DB unavailable
_project_store: dict[str, dict[str, Any]] = {}
_project_runs: dict[str, list[dict[str, Any]]] = {}


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    run_count: int = 0
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]


class RunSummary(BaseModel):
    id: str
    query: str
    status: str
    summary: str | None = None
    created_at: str


class ProjectDetailResponse(ProjectResponse):
    recent_runs: list[RunSummary] = Field(default_factory=list)


@router.post("/projects", response_model=ProjectResponse)
async def create_project(
    body: ProjectCreate,
    user: AuthenticatedUser = Depends(require_auth),
) -> ProjectResponse:
    """Create a new research project."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import ProjectRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ProjectRepository(db)
            project = await repo.create(
                user_id=user.user_id,
                name=body.name,
                description=body.description,
            )
            await db.commit()
            return ProjectResponse(
                id=str(project.id),
                name=project.name,
                description=project.description,
                run_count=0,
                created_at=project.created_at.isoformat(),
                updated_at=project.updated_at.isoformat(),
            )
    except Exception as exc:
        logger.warning("project_db_create_failed", error=str(exc))

    # Fallback to in-memory
    project_id = uuid.uuid4().hex[:12]
    now = datetime.now(UTC).isoformat()
    _project_store[project_id] = {
        "id": project_id,
        "user_id": str(user.user_id),
        "name": body.name,
        "description": body.description,
        "created_at": now,
        "updated_at": now,
    }
    _project_runs[project_id] = []

    return ProjectResponse(
        id=project_id,
        name=body.name,
        description=body.description,
        run_count=0,
        created_at=now,
        updated_at=now,
    )


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    user: AuthenticatedUser = Depends(require_auth),
) -> ProjectListResponse:
    """List all projects for the current user."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import ProjectRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ProjectRepository(db)
            projects = await repo.list_by_user(user.user_id)
            return ProjectListResponse(
                projects=[
                    ProjectResponse(
                        id=str(p.id),
                        name=p.name,
                        description=p.description,
                        run_count=len(p.runs) if p.runs else 0,
                        created_at=p.created_at.isoformat(),
                        updated_at=p.updated_at.isoformat(),
                    )
                    for p in projects
                ]
            )
    except Exception:
        pass

    # Fallback to in-memory
    user_projects = [p for p in _project_store.values() if p["user_id"] == str(user.user_id)]
    return ProjectListResponse(
        projects=[
            ProjectResponse(
                id=p["id"],
                name=p["name"],
                description=p["description"],
                run_count=len(_project_runs.get(p["id"], [])),
                created_at=p["created_at"],
                updated_at=p["updated_at"],
            )
            for p in user_projects
        ]
    )


@router.get("/projects/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> ProjectDetailResponse:
    """Get project details with recent runs."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import ProjectRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ProjectRepository(db)
            project = await repo.get(uuid.UUID(project_id))
            if project is None or project.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Project not found")
            runs = await repo.get_runs(project.id, limit=10)
            return ProjectDetailResponse(
                id=str(project.id),
                name=project.name,
                description=project.description,
                run_count=len(project.runs) if project.runs else 0,
                created_at=project.created_at.isoformat(),
                updated_at=project.updated_at.isoformat(),
                recent_runs=[
                    RunSummary(
                        id=str(r.id),
                        query=r.query,
                        status=r.status,
                        summary=r.summary,
                        created_at=r.created_at.isoformat(),
                    )
                    for r in runs
                ],
            )
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback to in-memory
    project = _project_store.get(project_id)
    if project is None or project["user_id"] != str(user.user_id):
        raise HTTPException(status_code=404, detail="Project not found")

    runs = _project_runs.get(project_id, [])
    return ProjectDetailResponse(
        id=project["id"],
        name=project["name"],
        description=project["description"],
        run_count=len(runs),
        created_at=project["created_at"],
        updated_at=project["updated_at"],
        recent_runs=[
            RunSummary(
                id=r["id"],
                query=r["query"],
                status=r.get("status", "completed"),
                summary=r.get("summary"),
                created_at=r.get("created_at", ""),
            )
            for r in runs[:10]
        ],
    )


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: AuthenticatedUser = Depends(require_auth),
) -> ProjectResponse:
    """Update project name or description."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import ProjectRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ProjectRepository(db)
            project = await repo.get(uuid.UUID(project_id))
            if project is None or project.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Project not found")

            updates = {}
            if body.name is not None:
                updates["name"] = body.name
            if body.description is not None:
                updates["description"] = body.description

            if updates:
                project = await repo.update(project.id, **updates)

            await db.commit()
            return ProjectResponse(
                id=str(project.id),
                name=project.name,
                description=project.description,
                run_count=len(project.runs) if project.runs else 0,
                created_at=project.created_at.isoformat(),
                updated_at=project.updated_at.isoformat(),
            )
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback to in-memory
    project = _project_store.get(project_id)
    if project is None or project["user_id"] != str(user.user_id):
        raise HTTPException(status_code=404, detail="Project not found")

    if body.name is not None:
        project["name"] = body.name
    if body.description is not None:
        project["description"] = body.description
    project["updated_at"] = datetime.now(UTC).isoformat()

    return ProjectResponse(
        id=project["id"],
        name=project["name"],
        description=project["description"],
        run_count=len(_project_runs.get(project_id, [])),
        created_at=project["created_at"],
        updated_at=project["updated_at"],
    )


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, str]:
    """Delete a project. Runs are not deleted, just unlinked."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import ProjectRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ProjectRepository(db)
            project = await repo.get(uuid.UUID(project_id))
            if project is None or project.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Project not found")
            await repo.delete(project.id)
            await db.commit()
            return {"status": "deleted", "id": project_id}
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback to in-memory
    if project_id not in _project_store:
        raise HTTPException(status_code=404, detail="Project not found")
    project = _project_store[project_id]
    if project["user_id"] != str(user.user_id):
        raise HTTPException(status_code=404, detail="Project not found")

    del _project_store[project_id]
    _project_runs.pop(project_id, None)
    return {"status": "deleted", "id": project_id}


@router.get("/projects/{project_id}/runs")
async def list_project_runs(
    project_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, Any]:
    """List runs in a project."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import ProjectRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = ProjectRepository(db)
            project = await repo.get(uuid.UUID(project_id))
            if project is None or project.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Project not found")
            runs = await repo.get_runs(project.id)
            return {
                "runs": [
                    {
                        "id": str(r.id),
                        "query": r.query,
                        "status": r.status,
                        "summary": r.summary,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in runs
                ]
            }
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback to in-memory
    project = _project_store.get(project_id)
    if project is None or project["user_id"] != str(user.user_id):
        raise HTTPException(status_code=404, detail="Project not found")

    return {"runs": _project_runs.get(project_id, [])}


# ── Collaborators (in-memory) ──────────────────────────────────────
# Maps project_id → list of {email, role, added_at}
_project_collaborators: dict[str, list[dict[str, str]]] = {}


class CollaboratorAdd(BaseModel):
    email: str
    role: str = "editor"


@router.get("/projects/{project_id}/collaborators")
async def list_collaborators(
    project_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, Any]:
    """List collaborators for a project."""
    project = _project_store.get(project_id)
    if project is None or project["user_id"] != str(user.user_id):
        # Check if user is a collaborator
        collabs = _project_collaborators.get(project_id, [])
        if not any(c["email"] == user.email for c in collabs):
            raise HTTPException(status_code=404, detail="Project not found")

    owner = _project_store.get(project_id, {})
    owner_email = ""
    # Find owner email from auth in-memory store
    try:
        from evidentia.api.routes.auth import _user_store

        for _uid, udata in _user_store.items():
            if udata.get("user_id") == owner.get("user_id"):
                owner_email = udata.get("email", "")
                break
    except Exception:
        pass

    collabs = _project_collaborators.get(project_id, [])
    return {
        "owner": {"email": owner_email, "role": "owner"},
        "collaborators": collabs,
    }


@router.post("/projects/{project_id}/collaborators")
async def add_collaborator(
    project_id: str,
    body: CollaboratorAdd,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, str]:
    """Add a collaborator to a project by email."""
    project = _project_store.get(project_id)
    if project is None or project["user_id"] != str(user.user_id):
        raise HTTPException(status_code=403, detail="Only the project owner can add collaborators")

    if project_id not in _project_collaborators:
        _project_collaborators[project_id] = []

    # Don't add duplicates
    existing = _project_collaborators[project_id]
    if any(c["email"] == body.email for c in existing):
        raise HTTPException(status_code=409, detail="User already a collaborator")

    new_collab = {
        "email": body.email,
        "role": body.role,
        "added_at": datetime.now(UTC).isoformat(),
    }
    existing.append(new_collab)
    logger.info("collaborator_added", project=project_id, email=body.email)
    return {"status": "added", "email": body.email, "role": body.role}


@router.delete("/projects/{project_id}/collaborators/{email}")
async def remove_collaborator(
    project_id: str,
    email: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, str]:
    """Remove a collaborator from a project."""
    project = _project_store.get(project_id)
    if project is None or project["user_id"] != str(user.user_id):
        raise HTTPException(status_code=403, detail="Only the project owner can remove collaborators")

    collabs = _project_collaborators.get(project_id, [])
    before = len(collabs)
    _project_collaborators[project_id] = [c for c in collabs if c["email"] != email]
    if len(_project_collaborators[project_id]) == before:
        raise HTTPException(status_code=404, detail="Collaborator not found")

    logger.info("collaborator_removed", project=project_id, email=email)
    return {"status": "removed", "email": email}
