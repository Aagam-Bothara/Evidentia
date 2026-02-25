"""Async database engine and session management.

Tries PostgreSQL first; falls back to a local SQLite file so data
persists across server restarts even without a running Postgres instance.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from evidentia.core.config import get_settings
from evidentia.core.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_using_sqlite: bool = False


def _sqlite_url() -> str:
    """Return an aiosqlite URL pointing at a file next to the project root."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_path = os.path.join(base_dir, "evidentia_local.db")
    return f"sqlite+aiosqlite:///{db_path}"


def _get_engine() -> AsyncEngine:
    global _engine, _using_sqlite
    if _engine is None:
        settings = get_settings()
        db_url = settings.database_url

        if db_url.startswith("postgresql"):
            try:
                _engine = create_async_engine(
                    db_url,
                    echo=settings.evidentia_debug,
                    pool_size=10,
                    max_overflow=20,
                    pool_pre_ping=True,
                    pool_recycle=300,
                    pool_timeout=3,
                    connect_args={"timeout": 3, "command_timeout": 5},
                )
                logger.info("db_engine_created", url=db_url.split("@")[-1])
                return _engine
            except Exception as exc:
                logger.warning("postgres_engine_failed", error=str(exc))
                _engine = None

        # Fallback to SQLite
        if _engine is None:
            sqlite_url = _sqlite_url()
            _engine = create_async_engine(
                sqlite_url,
                echo=settings.evidentia_debug,
            )
            _using_sqlite = True
            logger.info("db_engine_created_sqlite", path=sqlite_url)
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async DB session."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize the database engine (call during app startup).

    For SQLite, auto-creates all tables.
    For PostgreSQL, just verifies connectivity.
    """
    global _engine, _session_factory, _using_sqlite

    settings = get_settings()
    db_url = settings.database_url

    # Try PostgreSQL first
    if db_url.startswith("postgresql"):
        try:
            pg_engine = create_async_engine(
                db_url,
                echo=settings.evidentia_debug,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=300,
                pool_timeout=3,
                connect_args={"timeout": 3, "command_timeout": 5},
            )
            async with pg_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            _engine = pg_engine
            _session_factory = None  # reset so it picks up new engine
            _using_sqlite = False
            logger.info("db_connected_postgres")
            return
        except Exception as exc:
            logger.warning("postgres_unavailable_fallback_sqlite", error=str(exc))
            _engine = None
            _session_factory = None

    # Fallback: SQLite with auto-create tables
    sqlite_url = _sqlite_url()
    _engine = create_async_engine(sqlite_url, echo=settings.evidentia_debug)
    _session_factory = None
    _using_sqlite = True

    # Import all models so Base.metadata knows about them
    from evidentia.db.chat_models import ChatMessageRow  # noqa: F401
    from evidentia.db.models import Base, UserCredentialRow  # noqa: F401
    from evidentia.db.review_models import ReviewPaperRow, SystematicReviewRow  # noqa: F401
    from evidentia.db.writing_models import WritingDocumentRow  # noqa: F401

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("db_connected_sqlite", path=sqlite_url)


async def close_db() -> None:
    """Dispose of the engine (call during app shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("db_disconnected")


async def check_db() -> bool:
    """Return True if the database is reachable."""
    try:
        engine = _get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
