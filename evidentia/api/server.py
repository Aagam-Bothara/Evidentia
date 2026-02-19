"""FastAPI application — production-grade API gateway for Evidentia."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from evidentia import __version__
from evidentia.api.middleware import (
    ErrorSanitizationMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from evidentia.api.routes import annotations, auth, export, health, projects, query, reviews, teams, tools, upload
from evidentia.core.config import get_settings
from evidentia.core.logging import setup_logging, get_logger

logger = get_logger(__name__)

STATIC_DIR = Path(__file__).parent.parent / "web" / "static"

# Rate limiter (uses remote address by default)
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown."""
    settings = get_settings()
    setup_logging(
        log_level=settings.evidentia_log_level,
        json_output=settings.is_production,
    )

    # ── Startup ─────────────────────────────────────────────────
    # Initialize DB (graceful — don't crash if DB is unavailable)
    try:
        from evidentia.db.engine import init_db
        await init_db()
        logger.info("database_ready")
    except Exception as exc:
        logger.warning("database_unavailable", error=str(exc))

    # Initialize Redis (graceful)
    try:
        from evidentia.cache import get_redis
        await get_redis()
    except Exception as exc:
        logger.warning("redis_unavailable", error=str(exc))

    logger.info("app_started", version=__version__, env=settings.evidentia_env.value)

    yield

    # ── Shutdown ────────────────────────────────────────────────
    try:
        from evidentia.db.engine import close_db
        await close_db()
    except Exception:
        pass

    try:
        from evidentia.cache import close_redis
        await close_redis()
    except Exception:
        pass

    logger.info("app_shutdown")


app = FastAPI(
    title="Evidentia",
    description="A verifiable intelligence layer for research workflows.",
    version=__version__,
    lifespan=lifespan,
)

# ── Rate limiter ────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware (order matters: last added = first executed) ──────────
settings = get_settings()

# CORS — restricted to configured origins
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
if not settings.is_production:
    origins.append("*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-Id"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(ErrorSanitizationMiddleware)

# ── Prometheus metrics ──────────────────────────────────────────────
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    excluded_handlers=["/health", "/metrics"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# ── Static files ────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── API Routes ──────────────────────────────────────────────────────
# Public
app.include_router(health.router, tags=["health"])
app.include_router(tools.router, prefix="/api/v1", tags=["tools"])

# Auth
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])

# Protected (auth enforced per-route)
app.include_router(query.router, prefix="/api/v1", tags=["query"])
app.include_router(upload.router, prefix="/api/v1", tags=["upload"])
app.include_router(export.router, prefix="/api/v1", tags=["export"])
app.include_router(projects.router, prefix="/api/v1", tags=["projects"])
app.include_router(annotations.router, prefix="/api/v1", tags=["annotations"])
app.include_router(teams.router, prefix="/api/v1", tags=["teams"])
app.include_router(reviews.router, prefix="/api/v1", tags=["reviews"])


# ── Web UI ──────────────────────────────────────────────────────────

@app.get("/")
async def serve_ui():
    """Serve the Evidentia web UI."""
    return FileResponse(str(STATIC_DIR / "index.html"))


# ── WebSocket for streaming agent ───────────────────────────────────

@app.websocket("/ws/query")
async def websocket_query(ws: WebSocket):
    """WebSocket endpoint for real-time agent streaming.

    Authentication via query param: ws://host/ws/query?token=JWT
    Falls back to unauthenticated in development mode.
    """
    await ws.accept()

    # Authenticate WebSocket connection
    user_id = None
    try:
        from evidentia.db.engine import _get_session_factory
        factory = _get_session_factory()
        async with factory() as db:
            from evidentia.api.auth import get_ws_user
            ws_user = await get_ws_user(ws, db)
            if ws_user:
                user_id = ws_user.user_id

        if user_id is None and settings.is_production:
            await ws.send_text(json.dumps({
                "type": "error",
                "data": {"message": "Authentication required. Connect with ?token=JWT"},
            }))
            await ws.close()
            return
    except Exception:
        # DB unavailable — allow in dev mode
        if settings.is_production:
            await ws.send_text(json.dumps({
                "type": "error",
                "data": {"message": "Authentication service unavailable"},
            }))
            await ws.close()
            return

    try:
        # Receive query from client
        raw = await ws.receive_text()
        data = json.loads(raw)
        user_query = data.get("query", "")
        project_id = data.get("project_id")

        if not user_query:
            await ws.send_text(json.dumps({
                "type": "error",
                "data": {"message": "Empty query"},
            }))
            await ws.close()
            return

        # Build the real agent (system-driven, not a wrapper)
        try:
            from evidentia.agent.factory import build_agent
            agent = build_agent()
        except Exception as exc:
            await ws.send_text(json.dumps({
                "type": "error",
                "data": {"message": f"Failed to initialize agent: {str(exc)}. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."},
            }))
            await ws.close()
            return

        # Stream real agent events to client
        agent_output = None
        async for event in agent.stream(user_query):
            await ws.send_text(json.dumps(event.to_dict(), default=str))
            if event.type == "completed":
                agent_output = event.data.get("_output")

        # Persist run to database if authenticated
        if user_id and agent_output:
            try:
                from evidentia.db.engine import _get_session_factory
                factory = _get_session_factory()
                async with factory() as db:
                    from evidentia.db.repositories import RunRepository
                    repo = RunRepository(db)
                    import uuid as _uuid
                    _proj_id = None
                    if project_id:
                        try:
                            _proj_id = _uuid.UUID(project_id)
                        except ValueError:
                            pass
                    await repo.save_run(
                        user_id=user_id,
                        query=user_query,
                        summary=agent_output.summary,
                        claims=agent_output.claims,
                        plan_json=agent_output.plan.model_dump() if agent_output.plan else None,
                        evidence_summary=agent_output.evidence_summary,
                        total_tool_calls=agent_output.total_tool_calls,
                        total_iterations=agent_output.total_iterations,
                        elapsed_seconds=agent_output.elapsed_seconds,
                        success=agent_output.success,
                        project_id=_proj_id,
                    )
                    await db.commit()
                    logger.info("run_persisted", user_id=str(user_id))
            except Exception as exc:
                logger.warning("run_persist_failed", error=str(exc))

    except WebSocketDisconnect:
        logger.info("websocket_disconnected")
    except Exception as exc:
        logger.error("websocket_error", error=str(exc))
        try:
            await ws.send_text(json.dumps({
                "type": "error",
                "data": {"message": str(exc) if not settings.is_production else "Internal error"},
            }))
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# ── WebSocket for streaming systematic reviews ───────────────────

@app.websocket("/ws/review")
async def websocket_review(ws: WebSocket):
    """WebSocket endpoint for real-time systematic review streaming.

    Authentication via query param: ws://host/ws/review?token=JWT
    """
    await ws.accept()

    # Authenticate
    user_id = None
    try:
        from evidentia.db.engine import _get_session_factory
        factory = _get_session_factory()
        async with factory() as db:
            from evidentia.api.auth import get_ws_user
            ws_user = await get_ws_user(ws, db)
            if ws_user:
                user_id = ws_user.user_id

        if user_id is None and settings.is_production:
            await ws.send_text(json.dumps({
                "type": "error",
                "data": {"message": "Authentication required"},
            }))
            await ws.close()
            return
    except Exception:
        if settings.is_production:
            await ws.send_text(json.dumps({
                "type": "error",
                "data": {"message": "Authentication service unavailable"},
            }))
            await ws.close()
            return

    try:
        # Receive review config from client
        raw = await ws.receive_text()
        data = json.loads(raw)

        research_question = data.get("research_question", "")
        if not research_question:
            await ws.send_text(json.dumps({
                "type": "error",
                "data": {"message": "research_question is required"},
            }))
            await ws.close()
            return

        # Build review config
        from evidentia.review.models import ReviewConfig, ReviewMode
        mode_str = data.get("mode", "rigorous")
        try:
            review_mode = ReviewMode(mode_str)
        except ValueError:
            review_mode = ReviewMode.RIGOROUS
        config = ReviewConfig(
            research_question=research_question,
            inclusion_criteria=data.get("inclusion_criteria", []),
            exclusion_criteria=data.get("exclusion_criteria", []),
            databases=data.get("databases", ["pubmed_search", "openalex_search", "semantic_scholar"]),
            max_results_per_db=data.get("max_results_per_database", 100),
            mode=review_mode,
        )

        # Build the review engine
        try:
            from evidentia.agent.factory import build_review_engine
            engine = build_review_engine()
        except Exception as exc:
            await ws.send_text(json.dumps({
                "type": "error",
                "data": {"message": f"Failed to initialize review engine: {exc}"},
            }))
            await ws.close()
            return

        # Stream review events
        review_data = None
        async for event in engine.stream(config):
            await ws.send_text(json.dumps(event.to_dict(), default=str))
            if event.type == "review_completed":
                review_data = event.data

        # Persist to DB if authenticated
        if user_id and review_data:
            try:
                from evidentia.db.engine import _get_session_factory
                factory = _get_session_factory()
                async with factory() as db:
                    from evidentia.db.review_repository import ReviewRepository
                    from evidentia.review.models import PaperRecord, PRISMAFlowData
                    import uuid as _uuid

                    repo = ReviewRepository(db)
                    proj_id = None
                    if data.get("project_id"):
                        try:
                            proj_id = _uuid.UUID(data["project_id"])
                        except ValueError:
                            pass

                    review = await repo.create(
                        user_id=user_id,
                        research_question=config.research_question,
                        inclusion_criteria=config.inclusion_criteria,
                        exclusion_criteria=config.exclusion_criteria,
                        databases=config.databases,
                        project_id=proj_id,
                    )

                    # Save PRISMA counts
                    prisma_raw = review_data.get("prisma", {})
                    prisma = PRISMAFlowData(**prisma_raw)
                    await repo.update_review_status(
                        review.id,
                        status="completed",
                        prisma=prisma,
                        elapsed_seconds=review_data.get("elapsed_seconds"),
                    )

                    # Save papers
                    papers_raw = review_data.get("papers", [])
                    papers = [PaperRecord(**p) for p in papers_raw]
                    await repo.save_papers(review.id, papers)

                    await db.commit()
                    logger.info("review_persisted", user_id=str(user_id))
            except Exception as exc:
                logger.warning("review_persist_failed", error=str(exc))

    except WebSocketDisconnect:
        logger.info("review_ws_disconnected")
    except Exception as exc:
        logger.error("review_ws_error", error=str(exc))
        try:
            await ws.send_text(json.dumps({
                "type": "error",
                "data": {"message": str(exc) if not settings.is_production else "Internal error"},
            }))
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
