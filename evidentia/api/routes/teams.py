"""Teams endpoints — team management and project sharing."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from evidentia.api.auth import AuthenticatedUser, require_auth
from evidentia.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# In-memory fallback
_team_store: dict[str, dict[str, Any]] = {}
_team_members: dict[str, list[dict[str, Any]]] = {}


class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class MemberAdd(BaseModel):
    email: str
    role: str = "viewer"


class MemberResponse(BaseModel):
    user_id: str
    email: str
    role: str


class TeamResponse(BaseModel):
    id: str
    name: str
    member_count: int = 0
    created_at: str


class TeamDetailResponse(TeamResponse):
    members: list[MemberResponse] = Field(default_factory=list)


class TeamListResponse(BaseModel):
    teams: list[TeamResponse]


@router.post("/teams", response_model=TeamResponse)
async def create_team(
    body: TeamCreate,
    user: AuthenticatedUser = Depends(require_auth),
) -> TeamResponse:
    """Create a new team. Creator is auto-added as admin."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import TeamRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = TeamRepository(db)
            team = await repo.create(name=body.name, created_by=user.user_id)
            await db.commit()
            return TeamResponse(
                id=str(team.id),
                name=team.name,
                member_count=1,
                created_at=team.created_at.isoformat(),
            )
    except Exception as exc:
        logger.warning("team_db_create_failed", error=str(exc))

    # Fallback to in-memory
    team_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    _team_store[team_id] = {
        "id": team_id,
        "name": body.name,
        "created_by": str(user.user_id),
        "created_at": now,
    }
    _team_members[team_id] = [{
        "user_id": str(user.user_id),
        "email": user.email,
        "role": "admin",
    }]

    return TeamResponse(
        id=team_id,
        name=body.name,
        member_count=1,
        created_at=now,
    )


@router.get("/teams", response_model=TeamListResponse)
async def list_teams(
    user: AuthenticatedUser = Depends(require_auth),
) -> TeamListResponse:
    """List teams the current user belongs to."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import TeamRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = TeamRepository(db)
            teams = await repo.list_by_user(user.user_id)
            return TeamListResponse(
                teams=[
                    TeamResponse(
                        id=str(t.id),
                        name=t.name,
                        member_count=len(t.members) if t.members else 0,
                        created_at=t.created_at.isoformat(),
                    )
                    for t in teams
                ]
            )
    except Exception:
        pass

    # Fallback to in-memory
    user_teams = []
    for team_id, members in _team_members.items():
        if any(m["user_id"] == str(user.user_id) for m in members):
            team = _team_store.get(team_id)
            if team:
                user_teams.append(TeamResponse(
                    id=team["id"],
                    name=team["name"],
                    member_count=len(members),
                    created_at=team["created_at"],
                ))
    return TeamListResponse(teams=user_teams)


@router.post("/teams/{team_id}/members", response_model=MemberResponse)
async def add_member(
    team_id: str,
    body: MemberAdd,
    user: AuthenticatedUser = Depends(require_auth),
) -> MemberResponse:
    """Invite a member to a team by email. Requires admin role."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import TeamRepository, UserRepository

        factory = _get_session_factory()
        async with factory() as db:
            team_repo = TeamRepository(db)
            user_repo = UserRepository(db)

            # Check caller is admin
            role = await team_repo.get_member_role(uuid.UUID(team_id), user.user_id)
            if role not in ("admin", "editor"):
                raise HTTPException(status_code=403, detail="Only admins can add members")

            # Find user by email
            target_user = await user_repo.get_by_email(body.email)
            if target_user is None:
                raise HTTPException(status_code=404, detail="User not found")

            member = await team_repo.add_member(
                team_id=uuid.UUID(team_id),
                user_id=target_user.id,
                role=body.role,
            )
            await db.commit()
            return MemberResponse(
                user_id=str(target_user.id),
                email=body.email,
                role=member.role,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("team_db_add_member_failed", error=str(exc))

    # Fallback to in-memory
    members = _team_members.get(team_id, [])
    if not any(m["user_id"] == str(user.user_id) and m["role"] == "admin" for m in members):
        raise HTTPException(status_code=403, detail="Only admins can add members")

    new_member = {
        "user_id": uuid.uuid4().hex[:12],
        "email": body.email,
        "role": body.role,
    }
    members.append(new_member)
    return MemberResponse(**new_member)


@router.delete("/teams/{team_id}/members/{member_user_id}")
async def remove_member(
    team_id: str,
    member_user_id: str,
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, str]:
    """Remove a member from a team."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import TeamRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = TeamRepository(db)
            role = await repo.get_member_role(uuid.UUID(team_id), user.user_id)
            if role != "admin":
                raise HTTPException(status_code=403, detail="Only admins can remove members")

            removed = await repo.remove_member(uuid.UUID(team_id), uuid.UUID(member_user_id))
            if not removed:
                raise HTTPException(status_code=404, detail="Member not found")
            await db.commit()
            return {"status": "removed", "user_id": member_user_id}
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback to in-memory
    members = _team_members.get(team_id, [])
    if not any(m["user_id"] == str(user.user_id) and m["role"] == "admin" for m in members):
        raise HTTPException(status_code=403, detail="Only admins can remove members")

    _team_members[team_id] = [m for m in members if m["user_id"] != member_user_id]
    return {"status": "removed", "user_id": member_user_id}


@router.post("/projects/{project_id}/share")
async def share_project(
    project_id: str,
    body: dict[str, str],
    user: AuthenticatedUser = Depends(require_auth),
) -> dict[str, str]:
    """Share a project with a team."""
    team_id = body.get("team_id")
    if not team_id:
        raise HTTPException(status_code=400, detail="team_id required")

    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import ProjectRepository, TeamRepository

        factory = _get_session_factory()
        async with factory() as db:
            project_repo = ProjectRepository(db)
            team_repo = TeamRepository(db)

            project = await project_repo.get(uuid.UUID(project_id))
            if project is None or project.user_id != user.user_id:
                raise HTTPException(status_code=404, detail="Project not found")

            if not await team_repo.is_member(uuid.UUID(team_id), user.user_id):
                raise HTTPException(status_code=403, detail="Not a team member")

            await project_repo.update(project.id, team_id=uuid.UUID(team_id))
            await db.commit()
            return {"status": "shared", "project_id": project_id, "team_id": team_id}
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback: just store team_id on the project
    from evidentia.api.routes.projects import _project_store
    project = _project_store.get(project_id)
    if project is None or project["user_id"] != str(user.user_id):
        raise HTTPException(status_code=404, detail="Project not found")

    project["team_id"] = team_id
    return {"status": "shared", "project_id": project_id, "team_id": team_id}
