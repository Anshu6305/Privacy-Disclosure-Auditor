"""Repository layer: database access for everything above it.

Each repository takes an injected :class:`~sqlalchemy.orm.Session` and returns
plain dataclasses. Nothing above this package imports SQLAlchemy.
"""

from app.db.repositories.application_repo import (
    ApplicationDetail,
    ApplicationRepository,
    ApplicationSummary,
    UnknownApplicationReport,
    handle_unknown_application,
)

__all__ = [
    "ApplicationDetail",
    "ApplicationRepository",
    "ApplicationSummary",
    "UnknownApplicationReport",
    "handle_unknown_application",
]
