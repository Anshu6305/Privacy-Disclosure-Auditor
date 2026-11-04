"""Database engine and session management.

The engine is created lazily. Importing this module never opens a connection,
so unit tests and the analysis package can import freely without a database
being present.
"""

from collections.abc import Iterator

from app.config import get_settings
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def engine_or_none() -> Engine | None:
    """Return the engine, creating it on first use.

    Returns None when no database password is configured, which is the normal
    state in a fresh checkout. Callers report that honestly rather than
    pretending a database is reachable.
    """
    global _engine
    if _engine is not None:
        return _engine

    settings = get_settings()
    if not settings.postgres_password:
        return None

    _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a transactional session."""
    global _session_factory

    engine = engine_or_none()
    if engine is None:
        raise RuntimeError(
            "Database is not configured. Set POSTGRES_PASSWORD in .env."
        )

    if _session_factory is None:
        _session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
