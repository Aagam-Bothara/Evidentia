"""FastAPI application — production-grade API gateway for Evidentia."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

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
from evidentia.api.routes import (
    annotations,
    auth,
    chat,
    citation_export,
    export,
    health,
    import_library,
    keys,
    prisma_export,
    projects,
    query,
    reviews,
    teams,
    tools,
    upload,
    validation,
    writing,
)
from evidentia.core.config import get_settings
from evidentia.core.logging import get_logger, setup_logging

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
    import asyncio as _aio

    async def _init_db():
        try:
            from evidentia.db.engine import init_db

            await _aio.wait_for(init_db(), timeout=8.0)
            logger.info("database_ready")
        except Exception as exc:
            logger.warning("database_init_error", error=str(exc))

    async def _init_redis():
        try:
            from evidentia.cache import get_redis

            await _aio.wait_for(get_redis(), timeout=3.0)
        except Exception as exc:
            logger.warning("redis_unavailable", error=str(exc))

    # Run DB + Redis init concurrently so startup is fast
    await _aio.gather(_init_db(), _init_redis())

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
app.include_router(citation_export.router, prefix="/api/v1", tags=["citation-export"])
app.include_router(projects.router, prefix="/api/v1", tags=["projects"])
app.include_router(annotations.router, prefix="/api/v1", tags=["annotations"])
app.include_router(teams.router, prefix="/api/v1", tags=["teams"])
app.include_router(reviews.router, prefix="/api/v1", tags=["reviews"])
app.include_router(prisma_export.router, prefix="/api/v1", tags=["prisma"])
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(validation.router, prefix="/api/v1", tags=["validation"])
app.include_router(import_library.router, prefix="/api/v1", tags=["import"])
app.include_router(writing.router, prefix="/api/v1", tags=["writing"])
app.include_router(keys.router, prefix="/api/v1", tags=["keys"])


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
            await ws.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "data": {"message": "Authentication required. Connect with ?token=JWT"},
                    }
                )
            )
            await ws.close()
            return
    except Exception:
        # DB unavailable — allow in dev mode
        if settings.is_production:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "data": {"message": "Authentication service unavailable"},
                    }
                )
            )
            await ws.close()
            return

    try:
        # Receive query from client
        raw = await ws.receive_text()
        data = json.loads(raw)
        user_query = data.get("query", "")
        project_id = data.get("project_id")

        if not user_query:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "data": {"message": "Empty query"},
                    }
                )
            )
            await ws.close()
            return

        # Build the real agent (system-driven, not a wrapper)
        try:
            if user_id:
                from evidentia.agent.factory import build_agent_for_user

                agent = await build_agent_for_user(str(user_id))
            else:
                from evidentia.agent.factory import build_agent

                agent = build_agent()
        except Exception as exc:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "data": {
                            "message": (
                                f"Failed to initialize agent: {str(exc)}. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."
                            ),
                        },
                    }
                )
            )
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
                    saved_run = await repo.save_run(
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

                    # Send run_id to client so history can be reloaded
                    await ws.send_text(
                        json.dumps(
                            {
                                "type": "run_saved",
                                "data": {"run_id": str(saved_run.id)},
                            }
                        )
                    )
            except Exception as exc:
                logger.warning("run_persist_failed", error=str(exc))

        # Build and verify provenance chain (non-blocking)
        if agent_output and agent_output.claims:
            try:
                from evidentia.core.provenance import (
                    build_provenance_chain,
                    store_provenance,
                    verify_provenance_chain,
                )

                # Extract evidence fragments from evidence_summary for matching
                evidence_frags = []
                _ = agent_output.evidence_summary or {}
                # The evidence_summary from the graph contains aggregated info;
                # we also walk the claims to gather fragment-like data
                for claim in agent_output.claims:
                    for cit in claim.citations:
                        evidence_frags.append(
                            {
                                "title": cit.title,
                                "doi": cit.doi or "",
                                "url": cit.url or "",
                                "source_tool": "unknown",
                                "retrieved_at": "",
                            }
                        )

                import uuid as _uuid2

                run_id_for_prov = _uuid2.uuid4().hex

                chain = build_provenance_chain(
                    run_id=run_id_for_prov,
                    query=user_query,
                    claims=agent_output.claims,
                    evidence_fragments=evidence_frags,
                )

                # Verify DOIs asynchronously (non-blocking for the run)
                chain = await verify_provenance_chain(chain)

                # Store the provenance chain
                store_provenance(chain)

                # Send provenance event to client
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "provenance",
                            "data": chain.to_dict(),
                        },
                        default=str,
                    )
                )

                logger.info(
                    "provenance_chain_built",
                    run_id=run_id_for_prov,
                    links=len(chain.links),
                    coverage=chain.coverage_score,
                )
            except Exception as exc:
                logger.warning("provenance_build_failed", error=str(exc))

        # Build reproducibility fingerprint and send to client
        if agent_output:
            try:
                import uuid as _fp_uuid

                from evidentia.core.reproducibility import build_fingerprint as _build_fp

                _fp_run_id = _fp_uuid.uuid4().hex
                claims_dicts = [c.model_dump() for c in agent_output.claims]

                fp = _build_fp(
                    run_id=_fp_run_id,
                    query=user_query,
                    claims=claims_dicts,
                )

                # Store in the in-memory fingerprint store for API access
                from evidentia.api.routes.query import (
                    _run_claims,
                    _run_fingerprints,
                    _run_queries,
                )

                _run_fingerprints[_fp_run_id] = fp.to_dict()
                _run_claims[_fp_run_id] = claims_dicts
                _run_queries[_fp_run_id] = user_query

                # Send fingerprint event to client
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "fingerprint",
                            "data": fp.to_dict(),
                        },
                        default=str,
                    )
                )

                logger.info(
                    "fingerprint_built",
                    run_id=_fp_run_id,
                    composite_hash=fp.short_hash,
                    tool_calls=len(fp.tool_call_log),
                )
            except Exception as exc:
                logger.warning("fingerprint_build_failed", error=str(exc))

    except WebSocketDisconnect:
        logger.info("websocket_disconnected")
    except Exception as exc:
        logger.error("websocket_error", error=str(exc))
        try:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "data": {"message": str(exc) if not settings.is_production else "Internal error"},
                    }
                )
            )
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
            await ws.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "data": {"message": "Authentication required"},
                    }
                )
            )
            await ws.close()
            return
    except Exception:
        if settings.is_production:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "data": {"message": "Authentication service unavailable"},
                    }
                )
            )
            await ws.close()
            return

    try:
        # Receive review config from client
        raw = await ws.receive_text()
        data = json.loads(raw)

        research_question = data.get("research_question", "")
        if not research_question:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "data": {"message": "research_question is required"},
                    }
                )
            )
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
            if user_id:
                from evidentia.agent.factory import build_review_engine_for_user

                engine = await build_review_engine_for_user(str(user_id))
            else:
                from evidentia.agent.factory import build_review_engine

                engine = build_review_engine()
        except Exception as exc:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "data": {"message": f"Failed to initialize review engine: {exc}"},
                    }
                )
            )
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
                    import uuid as _uuid

                    from evidentia.db.review_repository import ReviewRepository
                    from evidentia.review.models import PaperRecord, PRISMAFlowData

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
            await ws.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "data": {"message": str(exc) if not settings.is_production else "Internal error"},
                    }
                )
            )
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# ── WebSocket for real-time project chat ─────────────────────────

# In-memory room manager: project_id → { user_id_str: (WebSocket, email) }
_chat_rooms: dict[str, dict[str, tuple[WebSocket, str]]] = {}
# In-memory message store (fallback when DB is unavailable)
_chat_msg_store: dict[str, list[dict]] = {}


def _build_presence(room: dict[str, tuple[WebSocket, str]]) -> list[dict]:
    """Build presence list for a chat room."""
    return [{"user_id": uid, "email": info[1], "online": True} for uid, info in room.items()]


async def _broadcast_to_room(project_id: str, message: dict, exclude_user: str | None = None) -> None:
    """Send a message to all connected users in a chat room."""
    room = _chat_rooms.get(project_id, {})
    payload = json.dumps(message, default=str)
    disconnected = []
    for uid, (ws_conn, _email) in room.items():
        if uid == exclude_user:
            continue
        try:
            await ws_conn.send_text(payload)
        except Exception:
            disconnected.append(uid)
    for uid in disconnected:
        room.pop(uid, None)


def _is_db_available() -> bool:
    """Quick check: can we get a DB session factory without error?"""
    try:
        from evidentia.db.engine import _get_engine

        engine = _get_engine()
        return engine.pool.checkedin() >= 0  # pool exists
    except Exception:
        return False


@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    """WebSocket endpoint for real-time project chat.

    Authentication via query param: ws://host/ws/chat?token=JWT&project_id=UUID
    Works fully in-memory when DB is unavailable.
    """
    import asyncio
    import uuid as _uuid
    from datetime import UTC, datetime

    await ws.accept()

    project_id = ws.query_params.get("project_id", "")
    if not project_id:
        await ws.send_text(json.dumps({"type": "error", "data": {"message": "project_id required"}}))
        await ws.close()
        return

    # ── Authenticate (JWT only — no DB needed) ───────────────────
    user_id_str = None
    user_email = "anonymous"
    try:
        from evidentia.api.auth import get_ws_user

        ws_user = await get_ws_user(ws)
        if ws_user:
            user_id_str = str(ws_user.user_id)
            user_email = ws_user.email
    except Exception as exc:
        logger.debug("chat_ws_auth_error", error=str(exc))

    if not user_id_str:
        if settings.is_production:
            await ws.send_text(json.dumps({"type": "error", "data": {"message": "Authentication required"}}))
            await ws.close()
            return
        user_id_str = str(_uuid.uuid4())
        user_email = "dev@local"

    # ── Join room ────────────────────────────────────────────────
    if project_id not in _chat_rooms:
        _chat_rooms[project_id] = {}
    _chat_rooms[project_id][user_id_str] = (ws, user_email)

    logger.info("chat_ws_connected", user=user_email, project=project_id)

    # ── Send chat history (DB with 2s timeout, else in-memory) ───
    history_msgs: list[dict] = _chat_msg_store.get(project_id, [])[-50:]
    try:
        from evidentia.db.chat_repository import ChatRepository
        from evidentia.db.engine import _get_session_factory

        factory = _get_session_factory()
        async with factory() as db:
            repo = ChatRepository(db)
            rows = await asyncio.wait_for(
                repo.get_messages(_uuid.UUID(project_id), limit=50),
                timeout=2.0,
            )
            history_msgs = [
                {
                    "id": str(r.id),
                    "user_id": str(r.user_id),
                    "user_email": r.user_email,
                    "content": r.content,
                    "ref_type": r.ref_type,
                    "ref_id": r.ref_id,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]
    except Exception:
        pass  # already set to in-memory fallback above

    await ws.send_text(json.dumps({"type": "chat_history", "messages": history_msgs}))

    # ── Broadcast presence ───────────────────────────────────────
    await _broadcast_to_room(
        project_id,
        {"type": "presence_update", "users": _build_presence(_chat_rooms[project_id])},
    )

    # ── Message loop ─────────────────────────────────────────────
    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "")

            if msg_type == "chat_message":
                content = data.get("content", "").strip()
                if not content:
                    continue

                msg_id = str(_uuid.uuid4())
                now = datetime.now(UTC).isoformat()

                msg_payload = {
                    "id": msg_id,
                    "project_id": project_id,
                    "user_id": user_id_str,
                    "user_email": user_email,
                    "content": content,
                    "ref_type": data.get("ref_type"),
                    "ref_id": data.get("ref_id"),
                    "created_at": now,
                }

                # Persist to DB (best-effort, 2s timeout)
                try:
                    from evidentia.db.chat_repository import ChatRepository
                    from evidentia.db.engine import _get_session_factory

                    factory = _get_session_factory()
                    async with factory() as db:
                        repo = ChatRepository(db)
                        saved = await asyncio.wait_for(
                            repo.save_message(
                                project_id=_uuid.UUID(project_id),
                                user_id=_uuid.UUID(user_id_str),
                                user_email=user_email,
                                content=content,
                                ref_type=data.get("ref_type"),
                                ref_id=data.get("ref_id"),
                            ),
                            timeout=2.0,
                        )
                        await asyncio.wait_for(db.commit(), timeout=2.0)
                        msg_payload["id"] = str(saved.id)
                except Exception:
                    # In-memory fallback
                    if project_id not in _chat_msg_store:
                        _chat_msg_store[project_id] = []
                    _chat_msg_store[project_id].append(msg_payload)

                # Broadcast to all users in room
                await _broadcast_to_room(project_id, {"type": "chat_message", **msg_payload})

            elif msg_type == "typing":
                await _broadcast_to_room(
                    project_id,
                    {"type": "typing", "user_id": user_id_str, "user_email": user_email},
                    exclude_user=user_id_str,
                )

    except WebSocketDisconnect:
        logger.info("chat_ws_disconnected", user=user_email, project=project_id)
    except Exception as exc:
        logger.error("chat_ws_error", error=str(exc))
    finally:
        room = _chat_rooms.get(project_id, {})
        room.pop(user_id_str, None)
        if not room:
            _chat_rooms.pop(project_id, None)
        else:
            try:
                await _broadcast_to_room(
                    project_id,
                    {"type": "presence_update", "users": _build_presence(room)},
                )
            except Exception:
                pass
        try:
            await ws.close()
        except Exception:
            pass
