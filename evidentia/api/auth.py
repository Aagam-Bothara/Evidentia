"""Authentication — JWT tokens + API key validation."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from jose import JWTError, jwt

from evidentia.core.config import get_settings
from evidentia.core.logging import get_logger

logger = get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


# ── Password hashing ────────────────────────────────────────────────


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT tokens ──────────────────────────────────────────────────────


def create_access_token(user_id: str, email: str) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "exp": expires,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── FastAPI dependencies ────────────────────────────────────────────


class AuthenticatedUser:
    """Represents the authenticated user in a request."""

    def __init__(self, user_id: uuid.UUID, email: str) -> None:
        self.user_id = user_id
        self.email = email


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """Require authentication — tries JWT first, then API key.

    Works without a database by trusting the JWT payload. When DB is
    available, additionally verifies the user exists and is active.
    """
    # ── Try JWT ──────────────────────────────────────────────────
    if credentials is not None:
        payload = decode_access_token(credentials.credentials)
        user_id_str = payload.get("sub")
        email = payload.get("email", "")

        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

        # Try to parse as UUID (DB-created users) or use as-is (in-memory users)
        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            # In-memory user IDs are hex strings, not UUIDs — wrap them
            user_id = uuid.uuid5(uuid.NAMESPACE_URL, user_id_str)

        # Optionally verify against DB (graceful if DB unavailable)
        try:
            from evidentia.db.engine import _get_session_factory
            from evidentia.db.repositories import UserRepository

            factory = _get_session_factory()
            async with factory() as db:
                repo = UserRepository(db)
                user = await repo.get_by_id(uuid.UUID(user_id_str))
                if user is not None and not user.is_active:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account deactivated")
                if user is not None:
                    return AuthenticatedUser(user_id=user.id, email=email)
        except HTTPException:
            raise
        except (ValueError, Exception):
            # DB unavailable or user_id isn't a valid UUID — trust the JWT
            pass

        return AuthenticatedUser(user_id=user_id, email=email)

    # ── Try API key ──────────────────────────────────────────────
    api_key = request.headers.get("X-API-Key")
    if api_key:
        try:
            from evidentia.db.engine import _get_session_factory
            from evidentia.db.repositories import UserRepository

            factory = _get_session_factory()
            async with factory() as db:
                repo = UserRepository(db)
                user = await repo.get_by_api_key(api_key)
                if user is not None and user.is_active:
                    logger.info("api_key_auth", user_id=str(user.id))
                    return AuthenticatedUser(user_id=user.id, email=user.email)
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_ws_user(
    websocket: WebSocket,
    db: Any = None,
) -> AuthenticatedUser | None:
    """Extract auth from WebSocket query param ?token=..."""
    token = websocket.query_params.get("token")
    if not token:
        return None

    try:
        payload = decode_access_token(token)
        user_id_str = payload.get("sub")
        email = payload.get("email", "")
        if not user_id_str:
            return None

        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            user_id = uuid.uuid5(uuid.NAMESPACE_URL, user_id_str)

        # Optionally verify against DB
        if db is not None:
            try:
                from evidentia.db.repositories import UserRepository
                repo = UserRepository(db)
                user = await repo.get_by_id(uuid.UUID(user_id_str))
                if user and user.is_active:
                    return AuthenticatedUser(user_id=user.id, email=email)
            except (ValueError, Exception):
                pass

        # Trust JWT if DB unavailable
        return AuthenticatedUser(user_id=user_id, email=email)
    except HTTPException:
        return None
