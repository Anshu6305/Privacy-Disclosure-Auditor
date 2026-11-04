"""Health and readiness endpoints.

These are not part of E1 to E11. They exist so that the container stack and the
database connection can be checked independently of any feature.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness. Answers only that the process is serving requests."""
    return {"status": "ok"}


@router.get("/health/database")
def database_health() -> dict[str, str]:
    """Readiness of the database connection.

    Reports the real outcome of a trivial query. It never reports healthy
    without having executed one.
    """
    from app.db.session import engine_or_none
    from sqlalchemy import text

    engine = engine_or_none()
    if engine is None:
        return {"status": "unconfigured", "detail": "No database URL is configured."}

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - the message is the useful part
        return {"status": "unavailable", "detail": type(exc).__name__}

    return {"status": "ok"}
