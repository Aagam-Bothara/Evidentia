"""Health check endpoints — liveness and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from evidentia import __version__
from evidentia.core.config import get_settings
from evidentia.schemas.api import HealthResponse

router = APIRouter()


class ComponentStatus(BaseModel):
    status: str  # "ok" or "unavailable"
    latency_ms: float | None = None


class ReadinessResponse(BaseModel):
    status: str  # "ok" or "degraded"
    version: str
    environment: str
    database: ComponentStatus
    redis: ComponentStatus


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Lightweight liveness probe — always returns ok if the process is running."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=settings.evidentia_env.value,
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness_check() -> ReadinessResponse:
    """Readiness probe — checks database and Redis connectivity."""
    import time

    settings = get_settings()

    # Check database
    db_status = ComponentStatus(status="unavailable")
    try:
        from evidentia.db.engine import check_db

        start = time.monotonic()
        if await check_db():
            db_status = ComponentStatus(
                status="ok",
                latency_ms=round((time.monotonic() - start) * 1000, 1),
            )
    except Exception:
        pass

    # Check Redis
    redis_status = ComponentStatus(status="unavailable")
    try:
        from evidentia.cache import check_redis

        start = time.monotonic()
        if await check_redis():
            redis_status = ComponentStatus(
                status="ok",
                latency_ms=round((time.monotonic() - start) * 1000, 1),
            )
    except Exception:
        pass

    overall = "ok" if db_status.status == "ok" else "degraded"

    return ReadinessResponse(
        status=overall,
        version=__version__,
        environment=settings.evidentia_env.value,
        database=db_status,
        redis=redis_status,
    )
