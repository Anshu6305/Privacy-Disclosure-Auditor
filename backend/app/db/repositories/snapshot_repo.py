"""F-04, F-05 and F-07 — persisting and loading one collection event.

Module location is fixed by the approved function-to-module mapping (Phase 4
master plan §3).

**One row per collection event**, per the D-1 Option A ruling. An
``ApplicationRecord`` from the filesystem corpus is written as exactly one
``disclosure_snapshot``, carrying both source URLs, the policy document's path
and hash, and the ``status`` that says what the event actually achieved.

Three distinctions this module exists to preserve, because collapsing any of
them would turn missing information into a confident claim:

* **Absent category** against **declared not collected.** A category with no
  ``declared_practice`` row was never mentioned; a row with
  ``is_collected = false`` was mentioned and denied. Only rows that the
  declaration actually contains are written.
* **Unknown** against **declared no collection.**
  ``declares_no_data_collected`` is three-state: ``None`` when the Data Safety
  section was never read, ``False`` when it was read and carries no such
  statement, ``True`` when it does.
* **Failure** against **absence.** A source that could not be retrieved is
  recorded in ``status``, never as an empty declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.db.models import DeclaredPractice, DisclosureSnapshot
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from acquisition.models import (
    OUTCOME_NOT_FOUND,
    OUTCOME_PARSE_FAILED,
    ApplicationRecord,
    DataSafetyDeclaration,
    DeclaredDataEntry,
    Provenance,
)
from analysis.vocabulary import (
    SNAPSHOT_COMPLETE,
    SNAPSHOT_DECLARATION_ABSENT,
    SNAPSHOT_DECLARATION_ONLY,
    SNAPSHOT_FETCH_FAILED,
    SNAPSHOT_HAS_DECLARATION,
    SNAPSHOT_HAS_POLICY,
    SNAPSHOT_PARSE_FAILED,
    SNAPSHOT_POLICY_ONLY,
    SOURCE_DATA_SAFETY,
    SOURCE_PRIVACY_POLICY,
)

#: Joins the purposes tuple into the single TEXT column Phase 3 specifies.
#: Recorded rather than silently chosen: the schema has one column and a
#: declaration may list several purposes.
PURPOSE_SEPARATOR = "; "


class SnapshotNotFoundError(LookupError):
    """No collection event exists for the application."""


class PolicyDocumentUnavailableError(LookupError):
    """The snapshot references a policy document that cannot be read.

    Distinct from "this event has no policy", which is an expected state
    recorded in ``status``. This means the row claims a document and the
    filesystem disagrees, which is a corpus problem rather than a disclosure
    fact.
    """


@dataclass(frozen=True, slots=True)
class LoadedPolicyDocument:
    """F-05 — a policy document read back and hash-verified."""

    snapshot_id: int
    source_url: str
    storage_path: str
    content: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class SnapshotSummary:
    """What a collection event achieved, without loading its contents."""

    snapshot_id: int
    app_id: int
    collected_at: datetime
    status: str
    source_url_listing: str | None
    source_url_policy: str | None
    policy_doc_sha256: str | None
    declares_no_data_collected: bool | None

    @property
    def has_declaration(self) -> bool:
        return self.status in SNAPSHOT_HAS_DECLARATION

    @property
    def has_policy(self) -> bool:
        return self.status in SNAPSHOT_HAS_POLICY


# ---------------------------------------------------------------------------
# Status derivation (E-2)
# ---------------------------------------------------------------------------


def derive_status(record: ApplicationRecord) -> str:
    """What this collection event achieved, from what it actually captured.

    Derived rather than taken on trust: a corpus record could claim any
    status, and the status is what stops a failed source reading downstream
    as an absent declaration.

    ``declaration_absent`` is reserved for the case the acquisition layer
    reports as ``not_found`` — the listing was reached and carries no Data
    Safety section. That is a fact about the application. A fetch that failed
    is a fact about one moment, and the two must not be confused.
    """
    has_declaration = record.declaration is not None
    has_policy = bool(record.policy_path and record.policy_sha256)

    if has_declaration and has_policy:
        return SNAPSHOT_COMPLETE
    if has_declaration:
        return SNAPSHOT_DECLARATION_ONLY
    if has_policy:
        # The listing produced no declaration. Why decides the status.
        for provenance in record.provenances:
            if provenance.source_type != SOURCE_DATA_SAFETY:
                continue
            if provenance.outcome == OUTCOME_NOT_FOUND:
                return SNAPSHOT_DECLARATION_ABSENT
            if provenance.outcome == OUTCOME_PARSE_FAILED:
                return SNAPSHOT_PARSE_FAILED
        return SNAPSHOT_POLICY_ONLY
    return SNAPSHOT_FETCH_FAILED


def _provenance_for(record: ApplicationRecord, source_type: str) -> Provenance | None:
    for provenance in record.provenances:
        if provenance.source_type == source_type:
            return provenance
    return None


def _declares_no_data_collected(record: ApplicationRecord) -> bool | None:
    """Three states, and the middle one is the point.

    ``None`` is returned when the Data Safety section was not read at all.
    Returning ``False`` there would assert that the application was checked
    and makes no such declaration, which is a claim the corpus cannot support.
    """
    if record.declaration is None:
        return None
    return record.declaration.declares_no_data_collected


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class SnapshotRepository:
    """Collection events: write one, read the latest, load its contents.

    The session is injected and never committed here. A corpus import writes
    many applications and decides its own transaction boundary.
    """

    def __init__(self, session: Session, policy_root: Path | str | None = None) -> None:
        self._session = session
        #: Resolves relative ``policy_doc_path`` values. Corpus records store
        #: repository-relative paths so a corpus stays portable between
        #: machines.
        self._policy_root = Path(policy_root) if policy_root is not None else Path(".")

    # -- F-07: record the event and its provenance -------------------------

    def record_collection_event(
        self, app_id: int, record: ApplicationRecord
    ) -> DisclosureSnapshot:
        """Write one collection event. Returns the unflushed row.

        Supersedes any earlier active event for the application: snapshots are
        append-only, so the previous row is marked inactive rather than
        updated, and history is preserved for F-30.
        """
        status = derive_status(record)
        policy_provenance = _provenance_for(record, SOURCE_PRIVACY_POLICY)
        declaration_provenance = _provenance_for(record, SOURCE_DATA_SAFETY)

        # A URL is recorded when the source was attempted at all, so a failed
        # attempt is visible rather than indistinguishable from one never made.
        listing_url = record.play_store_url or (
            declaration_provenance.source_url if declaration_provenance else None
        )
        policy_url = record.policy_url or (
            policy_provenance.source_url if policy_provenance else None
        )
        if listing_url is None and policy_url is None:
            raise ValueError(
                f"{record.package_name}: the record names neither a listing "
                "URL nor a policy URL, so there is no collection event to "
                "record. A total failure belongs in provenance, not in a "
                "snapshot row."
            )

        has_policy_document = bool(record.policy_path and record.policy_sha256)

        for previous in self._session.execute(
            select(DisclosureSnapshot).where(
                DisclosureSnapshot.app_id == app_id,
                DisclosureSnapshot.is_active.is_(True),
            )
        ).scalars():
            previous.is_active = False

        snapshot = DisclosureSnapshot(
            app_id=app_id,
            collected_at=record.collected_at or datetime.now(timezone.utc),
            source_url_listing=listing_url,
            source_url_policy=policy_url,
            retrieval_mode=self._retrieval_mode(record),
            policy_doc_path=record.policy_path if has_policy_document else None,
            policy_doc_sha256=record.policy_sha256 if has_policy_document else None,
            policy_doc_bytes=(
                policy_provenance.content_bytes if policy_provenance else None
            ),
            policy_http_status=(
                policy_provenance.http_status if policy_provenance else None
            ),
            status=status,
            declares_no_data_collected=_declares_no_data_collected(record),
            is_active=True,
        )
        self._session.add(snapshot)
        self._session.flush()

        if record.declaration is not None:
            self._write_declared_practices(snapshot.snapshot_id, record.declaration)

        return snapshot

    @staticmethod
    def _retrieval_mode(record: ApplicationRecord) -> str:
        """One mode for the event, from its provenance.

        Option A has one column for what were per-source values. Where the two
        sources disagree the policy document's mode wins, because it is the
        one the stored document came from; the per-source modes remain in the
        filesystem record.
        """
        policy = _provenance_for(record, SOURCE_PRIVACY_POLICY)
        if policy is not None:
            return policy.retrieval_mode
        if record.provenances:
            return record.provenances[0].retrieval_mode
        return "manual_import"

    def _write_declared_practices(
        self, snapshot_id: int, declaration: DataSafetyDeclaration
    ) -> None:
        """One row per declared entry, and **no rows for anything else**.

        An absent category must stay absent. Writing a placeholder row for
        every category the taxonomy knows about would turn "not mentioned"
        into "declared not collected", which is a different disclosure and a
        different verdict under ALG-8.
        """
        for entry in declaration.entries:
            self._session.add(
                DeclaredPractice(
                    snapshot_id=snapshot_id,
                    ds_category=entry.ds_category,
                    ds_data_type=entry.data_type,
                    is_collected=entry.is_collected,
                    is_shared=entry.is_shared,
                    is_optional=entry.is_optional,
                    is_ephemeral=entry.is_ephemeral,
                    purpose=(
                        PURPOSE_SEPARATOR.join(entry.purposes)
                        if entry.purposes
                        else None
                    ),
                    raw_label=entry.raw_label,
                )
            )

    # -- Reading -----------------------------------------------------------

    def latest_for_app(self, app_id: int) -> SnapshotSummary | None:
        """The most recent active collection event, or None."""
        row = self._session.execute(
            select(DisclosureSnapshot)
            .where(
                DisclosureSnapshot.app_id == app_id,
                DisclosureSnapshot.is_active.is_(True),
            )
            .order_by(desc(DisclosureSnapshot.collected_at))
            .limit(1)
        ).scalar_one_or_none()
        return None if row is None else self._summarise(row)

    def history_for_app(self, app_id: int, limit: int = 20) -> list[SnapshotSummary]:
        """Every collection event, newest first. Inactive ones included: that
        is what makes FR-25's history meaningful."""
        rows = self._session.execute(
            select(DisclosureSnapshot)
            .where(DisclosureSnapshot.app_id == app_id)
            .order_by(desc(DisclosureSnapshot.collected_at), desc(DisclosureSnapshot.snapshot_id))
            .limit(limit)
        ).scalars()
        return [self._summarise(row) for row in rows]

    @staticmethod
    def _summarise(row: DisclosureSnapshot) -> SnapshotSummary:
        return SnapshotSummary(
            snapshot_id=row.snapshot_id,
            app_id=row.app_id,
            collected_at=row.collected_at,
            status=row.status,
            source_url_listing=row.source_url_listing,
            source_url_policy=row.source_url_policy,
            policy_doc_sha256=row.policy_doc_sha256,
            declares_no_data_collected=row.declares_no_data_collected,
        )

    # -- F-04: load the declaration back -----------------------------------

    def load_declaration(self, snapshot_id: int) -> DataSafetyDeclaration | None:
        """Rebuild the declaration from ``declared_practice``.

        Returns ``None`` when the event carries no declaration — which is not
        the same as an empty one. An empty ``DataSafetyDeclaration`` would say
        "we read the section and it declares nothing"; ``None`` says "we never
        read it".
        """
        snapshot = self._session.get(DisclosureSnapshot, snapshot_id)
        if snapshot is None:
            raise SnapshotNotFoundError(f"no collection event {snapshot_id}")

        # Keyed on the column, not on a status set. `declares_no_data_collected`
        # is NULL exactly when the Data Safety section was never read, which is
        # the question being asked here. Deriving it from `status` instead put
        # the answer one indirection away from the fact, and the equivalent
        # mistake on the policy side became C-64.
        if snapshot.declares_no_data_collected is None:
            return None

        rows = self._session.execute(
            select(DeclaredPractice)
            .where(DeclaredPractice.snapshot_id == snapshot_id)
            .order_by(DeclaredPractice.declared_practice_id)
        ).scalars()

        entries = tuple(
            DeclaredDataEntry(
                ds_category=row.ds_category,
                data_type=row.ds_data_type,
                is_collected=row.is_collected,
                is_shared=row.is_shared,
                purposes=(
                    tuple(part.strip() for part in row.purpose.split(PURPOSE_SEPARATOR))
                    if row.purpose
                    else ()
                ),
                is_optional=row.is_optional,
                is_ephemeral=row.is_ephemeral,
                raw_label=row.raw_label,
            )
            for row in rows
        )

        return DataSafetyDeclaration(
            package_name=snapshot.application.package_name,
            entries=entries,
            # SecurityPractices has no approved column. Rebuilding it with
            # False would assert four things the database never stored, so the
            # default all-unknown instance is used and the gap is reported in
            # docs/M3B_IMPLEMENTATION_PLAN.md section 7.
            declares_no_data_collected=bool(snapshot.declares_no_data_collected),
        )

    # -- F-05: load the policy document ------------------------------------

    def load_policy_document(self, snapshot_id: int) -> LoadedPolicyDocument | None:
        """Read the stored policy document and verify its hash.

        Returns ``None`` when the event has no policy — an expected state, not
        an error. Raises only when the row claims a document the filesystem
        cannot supply, or supplies with different bytes.
        """
        from acquisition.policy_document import sha256_of_bytes

        snapshot = self._session.get(DisclosureSnapshot, snapshot_id)
        if snapshot is None:
            raise SnapshotNotFoundError(f"no collection event {snapshot_id}")
        # The row holding a path is the authoritative fact that a document
        # exists; a CHECK constraint already ties the path to its hash. The
        # status is a summary of the event, not the record of what it stored.
        if not snapshot.policy_doc_path:
            return None

        path = Path(snapshot.policy_doc_path)
        if not path.is_absolute():
            path = self._policy_root / path
        if not path.is_file():
            raise PolicyDocumentUnavailableError(
                f"snapshot {snapshot_id} references {path}, which does not "
                "exist. The database and the corpus have diverged; re-import "
                "rather than editing the row."
            )

        raw = path.read_bytes()
        actual = sha256_of_bytes(raw)
        if actual != snapshot.policy_doc_sha256:
            raise PolicyDocumentUnavailableError(
                f"snapshot {snapshot_id} records {snapshot.policy_doc_sha256} "
                f"for {path}, but the file hashes to {actual}. The document "
                "has changed since collection, so any evidence quoted from it "
                "would not be the text that was audited."
            )

        return LoadedPolicyDocument(
            snapshot_id=snapshot_id,
            source_url=snapshot.source_url_policy or "",
            storage_path=str(path),
            content=raw.decode("utf-8", errors="replace"),
            content_sha256=actual,
        )


__all__ = [
    "LoadedPolicyDocument",
    "PolicyDocumentUnavailableError",
    "SnapshotNotFoundError",
    "SnapshotRepository",
    "SnapshotSummary",
    "derive_status",
]
