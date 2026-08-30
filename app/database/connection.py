"""SQLAlchemy engine, session factory and declarative base.

PostgreSQL is the primary database. SQLite is supported as a lightweight
fallback (handy for tests and for running the project without a PostgreSQL
server) — the connection string simply drives which backend is used.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings
from app.logging_setup import get_logger

logger = get_logger(__name__)

Base = declarative_base()

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _build_engine(database_url: str | None = None) -> Engine:
    url = database_url or settings.database_url
    is_sqlite = url.startswith("sqlite")

    kwargs: dict = {"echo": False, "future": True}
    if is_sqlite:
        # SQLite needs this flag to share a connection across threads
        # (FastAPI uses a threadpool).
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Keep a small pool; avoids exhausting the PostgreSQL server.
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10
        kwargs["pool_pre_ping"] = True

    engine = create_engine(url, **kwargs)
    logger.info("Database engine created (sqlite=%s)", is_sqlite)
    return engine


def get_engine(database_url: str | None = None) -> Engine:
    """Return the shared engine, creating it on first use."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = _build_engine(database_url)
        _SessionLocal = sessionmaker(
            bind=_engine, autocommit=False, autoflush=False, expire_on_commit=False
        )
    return _engine


def get_session(database_url: str | None = None) -> Session:
    """Return a new session bound to the shared engine."""
    if _SessionLocal is None:
        get_engine(database_url)
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def init_db(database_url: str | None = None) -> None:
    """Create all tables (idempotent). Used by scripts/init_db.py and tests."""
    from app.database import models  # noqa: F401  (registers tables on Base)

    engine = get_engine(database_url)
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema ensured (all tables created if missing)")


def reset_db(database_url: str | None = None) -> None:
    """Drop and recreate all tables. Used only by tests / explicit resets."""
    from app.database import models  # noqa: F401

    engine = get_engine(database_url)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema reset")
