"""F-01 and F-03 — application search and unknown-application handling.

Module location is fixed by the approved function-to-module mapping (Phase 4
master plan §3): both F-01 and F-03 live here.

**Why a repository.** Everything above this layer — the API, and later the
worker — needs application records without needing SQLAlchemy. The search
returns plain frozen dataclasses carrying exactly the fields FR-01 asks for,
so a caller cannot accidentally lazy-load a relationship, hold a detached
instance, or expose ``app_id`` in a response that should be keyed by package
name.

**What this module deliberately does not do.** It writes nothing. Creating an
application row belongs to the corpus import path, which cannot be built until
D-1 settles what a ``disclosure_snapshot`` is. F-03 therefore *reports* that an
application is absent; it does not insert it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.config import get_settings
from app.db.models import Application
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ApplicationSummary:
    """One search hit.

    Exactly the three fields FR-01 names: application name, developer name and
    package identifier. ``app_id`` is absent on purpose — it is an internal
    surrogate key, and the package name is the identifier every other part of
    the system uses.
    """

    package_name: str
    app_name: str
    developer_name: str | None


@dataclass(frozen=True, slots=True)
class ApplicationDetail:
    """A single application, retrieved by package identifier.

    Carries ``app_id`` because the audit-request path (F-02) will need the
    foreign key. Nothing in F-01's response shape includes it.
    """

    app_id: int
    package_name: str
    app_name: str
    developer_name: str | None
    store_category: str | None
    play_store_url: str | None
    first_seen_at: datetime
    last_seen_at: datetime | None


@dataclass(frozen=True, slots=True)
class UnknownApplicationReport:
    """F-03 — what to say when a package identifier is not in the corpus.

    ``live_retrieval_configured`` states whether an adapter is present, which
    means a fetch can be *attempted*. It never means a fetch would succeed:
    Phase 1 named scraper breakage the project's highest-probability risk, and
    ``AcquisitionGateway`` returns recorded failures rather than raising. The
    message below says so in those words so no caller can read availability as
    success.

    ``can_request_audit`` is always False. An audit needs two disclosure
    snapshots, and an application absent from the corpus has none.
    """

    package_name: str
    present_in_corpus: bool
    live_retrieval_configured: bool
    can_request_audit: bool
    reason: str
    suggested_action: str


# ---------------------------------------------------------------------------
# ALG-11 — case-insensitive prefix search
# ---------------------------------------------------------------------------

#: Characters with a special meaning inside a SQL ``LIKE`` pattern. A user
#: searching for ``%`` must not match every row, and ``_`` must not behave as
#: a single-character wildcard.
_LIKE_ESCAPE = "\\"


def _normalise(term: str | None) -> str:
    """Trim and case-fold a query term. Returns '' for anything unusable."""
    if not term:
        return ""
    return term.strip().lower()


def escape_like(term: str) -> str:
    """Escape ``LIKE`` metacharacters so the term matches literally."""
    out = term.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
    return out.replace("%", _LIKE_ESCAPE + "%").replace("_", _LIKE_ESCAPE + "_")


class ApplicationRepository:
    """Read access to stored application records.

    The session is injected. Nothing here creates an engine, reads settings for
    a connection, or opens a transaction, so the same class is used by the API
    dependency, by the integration tests against a ``_test`` database, and by
    unit tests against an in-memory SQLite session.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # -- F-01 -------------------------------------------------------------

    def search(self, term: str | None, limit: int | None = None) -> list[ApplicationSummary]:
        """ALG-11: case-insensitive prefix search over name and package.

        Matches a term that is a prefix of either ``app_name`` or
        ``package_name``, compared case-insensitively through ``lower()`` so
        the two functional indexes on ``application`` can serve the predicate.

        A query shorter than the configured minimum returns an empty list
        rather than raising. FR-01 describes an as-you-type search box; a
        single keystroke that matched a fifth of the corpus would be useless,
        and an exception would be worse.
        """
        normalised = _normalise(term)
        settings = get_settings()

        if len(normalised) < settings.application_search_min_query_length:
            return []

        effective_limit = (
            settings.application_search_limit if limit is None else limit
        )
        if effective_limit <= 0:
            return []

        pattern = escape_like(normalised) + "%"
        statement = (
            select(
                Application.package_name,
                Application.app_name,
                Application.developer_name,
            )
            .where(
                func.lower(Application.app_name).like(pattern, escape=_LIKE_ESCAPE)
                | func.lower(Application.package_name).like(
                    pattern, escape=_LIKE_ESCAPE
                )
            )
            # Deterministic ordering. Without it the same query can return the
            # same rows in a different order on a different plan, which makes
            # a paged interface and a test both unreliable.
            .order_by(func.lower(Application.app_name), Application.package_name)
            .limit(effective_limit)
        )

        rows: Sequence[tuple[str, str, str | None]] = self._session.execute(
            statement
        ).all()
        return [
            ApplicationSummary(
                package_name=package_name,
                app_name=app_name,
                developer_name=developer_name,
            )
            for package_name, app_name, developer_name in rows
        ]

    # -- Retrieval by identifier ------------------------------------------

    def get_by_package(self, package_name: str | None) -> ApplicationDetail | None:
        """Return one application, or None when the package is not stored.

        The package name is matched exactly, not case-insensitively. Android
        package names are case-sensitive identifiers and ``package_name``
        carries a UNIQUE constraint; folding case here would let two distinct
        identifiers resolve to one row.
        """
        if not package_name or not package_name.strip():
            return None

        row = self._session.execute(
            select(Application).where(Application.package_name == package_name.strip())
        ).scalar_one_or_none()
        if row is None:
            return None

        return ApplicationDetail(
            app_id=row.app_id,
            package_name=row.package_name,
            app_name=row.app_name,
            developer_name=row.developer_name,
            store_category=row.store_category,
            play_store_url=row.play_store_url,
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at,
        )

    def exists(self, package_name: str | None) -> bool:
        """Whether a package identifier is present, without loading the row."""
        if not package_name or not package_name.strip():
            return False
        found = self._session.execute(
            select(Application.app_id).where(
                Application.package_name == package_name.strip()
            )
        ).first()
        return found is not None

    # -- F-03 -------------------------------------------------------------

    def resolve_or_report(
        self, package_name: str | None, *, live_retrieval_configured: bool = False
    ) -> ApplicationDetail | UnknownApplicationReport:
        """Return the application, or F-03's report on why it is absent.

        One call site, two outcomes, no exception for the ordinary case. An
        application being absent from an offline corpus of a few hundred
        records is the expected case, not an error.
        """
        found = self.get_by_package(package_name)
        if found is not None:
            return found
        return handle_unknown_application(
            package_name, live_retrieval_configured=live_retrieval_configured
        )


# ---------------------------------------------------------------------------
# F-03 — handleUnknownApplication
# ---------------------------------------------------------------------------


def handle_unknown_application(
    package_name: str | None, *, live_retrieval_configured: bool = False
) -> UnknownApplicationReport:
    """Describe an application that is not in the stored corpus.

    ``live_retrieval_configured`` is supplied by the caller from the
    acquisition gateway (``gateway.adapter is not None``) rather than read
    here, so this module stays independent of the acquisition package and of
    whatever transport is in use.

    The default is False: an unconfigured gateway is the project's normal
    state, and the offline corpus is what every audit reads.
    """
    identifier = (package_name or "").strip()

    if not identifier:
        return UnknownApplicationReport(
            package_name="",
            present_in_corpus=False,
            live_retrieval_configured=live_retrieval_configured,
            can_request_audit=False,
            reason="No package identifier was supplied.",
            suggested_action=(
                "Supply a Play Store package name, for example "
                "'com.example.app'."
            ),
        )

    if live_retrieval_configured:
        suggested_action = (
            "Live retrieval is configured, so a fetch can be attempted for "
            "this package. Attempting it is not the same as obtaining the "
            "data: the request may return not-found, fail, or be refused by "
            "the service, and the outcome is recorded either way. Until a "
            "retrieval succeeds and the records are imported, no audit can "
            "run for this application."
        )
    else:
        suggested_action = (
            "Live retrieval is not configured for this deployment, so this "
            "application cannot be added automatically. Collect it manually "
            "using the procedure in docs/M3_ACQUISITION_REPORT.md section 10 "
            "and import it into the corpus."
        )

    return UnknownApplicationReport(
        package_name=identifier,
        present_in_corpus=False,
        live_retrieval_configured=live_retrieval_configured,
        can_request_audit=False,
        reason=(
            f"'{identifier}' is not present in the offline corpus. No "
            f"disclosure snapshot is stored for it, so there is nothing to "
            f"audit."
        ),
        suggested_action=suggested_action,
    )
