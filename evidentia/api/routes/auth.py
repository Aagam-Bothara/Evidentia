"""Authentication endpoints — register, login, profile, API key management."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from evidentia.api.auth import (
    AuthenticatedUser,
    create_access_token,
    hash_password,
    require_auth,
    verify_password,
)
from evidentia.core.config import get_settings
from evidentia.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# In-memory user store (fallback when DB unavailable)
_user_store: dict[str, dict[str, Any]] = {}


# ── Schemas ─────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str


class UserProfile(BaseModel):
    user_id: str
    email: str
    api_key: str | None


class ApiKeyResponse(BaseModel):
    api_key: str


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """Register a new user and return a JWT."""
    settings = get_settings()

    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import UserRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = UserRepository(db)

            existing = await repo.get_by_email(request.email)
            if existing is not None:
                raise HTTPException(status_code=409, detail="Email already registered")

            hashed = hash_password(request.password)
            user = await repo.create(email=request.email, hashed_password=hashed)
            await db.commit()

            token = create_access_token(user_id=str(user.id), email=user.email)
            logger.info("user_registered", user_id=str(user.id), email=user.email)

            return TokenResponse(
                access_token=token,
                token_type="bearer",
                expires_in=settings.jwt_expiration_minutes * 60,
                user_id=str(user.id),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("auth_db_unavailable_register", error=str(exc))

    # Fallback to in-memory store
    email = request.email.lower()
    if email in _user_store:
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = uuid.uuid4().hex[:12]
    hashed = hash_password(request.password)
    _user_store[email] = {
        "id": user_id,
        "email": email,
        "hashed_password": hashed,
        "is_active": True,
        "api_key": None,
    }

    token = create_access_token(user_id=user_id, email=email)
    logger.info("user_registered_inmemory", user_id=user_id, email=email)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expiration_minutes * 60,
        user_id=user_id,
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Authenticate and return a JWT."""
    settings = get_settings()

    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import UserRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = UserRepository(db)
            user = await repo.get_by_email(request.email)

            if user is None or not verify_password(request.password, user.hashed_password):
                logger.warning("login_failed", email=request.email)
                raise HTTPException(status_code=401, detail="Invalid email or password")

            if not user.is_active:
                raise HTTPException(status_code=403, detail="Account is deactivated")

            token = create_access_token(user_id=str(user.id), email=user.email)
            logger.info("user_login", user_id=str(user.id))

            return TokenResponse(
                access_token=token,
                token_type="bearer",
                expires_in=settings.jwt_expiration_minutes * 60,
                user_id=str(user.id),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("auth_db_unavailable_login", error=str(exc))

    # Fallback to in-memory store
    email = request.email.lower()
    user_data = _user_store.get(email)

    if user_data is None or not verify_password(request.password, user_data["hashed_password"]):
        logger.warning("login_failed", email=request.email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user_data["is_active"]:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    token = create_access_token(user_id=user_data["id"], email=email)
    logger.info("user_login_inmemory", user_id=user_data["id"])

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expiration_minutes * 60,
        user_id=user_data["id"],
    )


@router.get("/auth/me", response_model=UserProfile)
async def get_me(user: AuthenticatedUser = Depends(require_auth)):
    """Return the current user's profile."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import UserRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = UserRepository(db)
            db_user = await repo.get_by_id(user.user_id)
            if db_user is not None:
                return UserProfile(
                    user_id=str(db_user.id),
                    email=db_user.email,
                    api_key=db_user.api_key,
                )
    except Exception:
        pass

    # Fallback to in-memory
    return UserProfile(
        user_id=str(user.user_id),
        email=user.email,
        api_key=None,
    )


@router.post("/auth/api-key", response_model=ApiKeyResponse)
async def regenerate_api_key(user: AuthenticatedUser = Depends(require_auth)):
    """Generate or regenerate the user's API key."""
    # Try DB first
    try:
        from evidentia.db.engine import _get_session_factory
        from evidentia.db.repositories import UserRepository

        factory = _get_session_factory()
        async with factory() as db:
            repo = UserRepository(db)
            new_key = await repo.regenerate_api_key(user.user_id)
            await db.commit()
            logger.info("api_key_regenerated", user_id=str(user.user_id))
            return ApiKeyResponse(api_key=new_key)
    except Exception:
        pass

    # Fallback: generate key in memory
    import secrets
    new_key = f"ev_{secrets.token_hex(24)}"
    email = user.email.lower()
    if email in _user_store:
        _user_store[email]["api_key"] = new_key

    logger.info("api_key_regenerated_inmemory", user_id=str(user.user_id))
    return ApiKeyResponse(api_key=new_key)
