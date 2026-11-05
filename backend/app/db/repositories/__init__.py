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
from app.db.repositories.snapshot_repo import (
    LoadedPolicyDocument,
    PolicyDocumentUnavailableError,
    SnapshotNotFoundError,
    SnapshotRepository,
    SnapshotSummary,
    derive_status,
)

__all__ = [
    "ApplicationDetail",
    "ApplicationRepository",
    "ApplicationSummary",
    "LoadedPolicyDocument",
    "PolicyDocumentUnavailableError",
    "SnapshotNotFoundError",
    "SnapshotRepository",
    "SnapshotSummary",
    "UnknownApplicationReport",
    "derive_status",
    "handle_unknown_application",
]
