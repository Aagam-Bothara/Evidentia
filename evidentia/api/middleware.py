"""Production middleware — security headers, request ID, error sanitization."""

from __future__ import annotations

import uuid
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from evidentia.core.config import get_settings
from evidentia.core.logging import get_logger

logger = get_logger(__name__)


# ── Request ID ──────────────────────────────────────────────────────


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generate a unique request ID for every request and bind to structlog."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id

        structlog.contextvars.unbind_contextvars("request_id")
        return response


# ── Security Headers ────────────────────────────────────────────────


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        settings = get_settings()
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data:; "
                "connect-src 'self' ws: wss:;"
            )

        return response


# ── Error Sanitization ──────────────────────────────────────────────


class ErrorSanitizationMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions — sanitize in production, verbose in dev."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            request_id = request.headers.get("X-Request-Id", "unknown")

            logger.error(
                "unhandled_exception",
                error=str(exc),
                error_type=type(exc).__name__,
                path=request.url.path,
                method=request.method,
                exc_info=True,
            )

            settings = get_settings()
            if settings.is_production:
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": "Internal server error",
                        "request_id": request_id,
                    },
                )
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": str(exc),
                        "error_type": type(exc).__name__,
                        "request_id": request_id,
                    },
                )
