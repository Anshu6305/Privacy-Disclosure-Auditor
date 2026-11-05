"""F-04, F-05, F-07 — persisting and loading one collection event.

The distinctions under test are the ones that decide whether a verdict is
honest. Most of these assert that something is **not** claimed: that an
unread section does not become a denial, that a failed fetch does not become
an empty declaration, and that a category nobody mentioned does not acquire a
row saying it is not collected.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.db.models import Application, Base, DeclaredPractice
from app.db.repositories import (
    PolicyDocumentUnavailableError,
    SnapshotNotFoundError,
    SnapshotRepository,
    derive_status,
)
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from acquisition.models import (
    OUTCOME_FETCH_FAILED,
    OUTCOME_NOT_FOUND,
    OUTCOME_PARSE_FAILED,
    OUTCOME_SUCCESS,
    RETRIEVAL_MODE_MANUAL,
    ApplicationRecord,
    DataSafetyDeclaration,
    DeclaredDataEntry,
    Provenance,
    SecurityPractices,
)
from acquisition.policy_document import sha256_of_bytes
from analysis.vocabulary import (
    SNAPSHOT_COMPLETE,
    SNAPSHOT_DECLARATION_ABSENT,
    SNAPSHOT_DECLARATION_ONLY,
    SNAPSHOT_FETCH_FAILED,
    SNAPSHOT_PARSE_FAILED,
    SNAPSHOT_POLICY_ONLY,
    SOURCE_DATA_SAFETY,
    SOURCE_PRIVACY_POLICY,
)

PACKAGE = "com.example.fixture"
LISTING = "https://play.google.com/store/apps/details?id=com.example.fixture"
POLICY_URL = "https://example.com/privacy"
POLICY_BODY = b"<html><body><p>We collect your email address.</p></body></html>"
POLICY_SHA = sha256_of_bytes(POLICY_BODY)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def app_id(session: Session) -> int:
    application = Application(package_name=PACKAGE, app_name="Fixture App")
    session.add(application)
    session.flush()
    return application.app_id


@pytest.fixture
def policy_file(tmp_path):
    path = tmp_path / "policies" / f"{POLICY_SHA}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(POLICY_BODY)
    return path


def provenance(source_type: str, outcome: str, url: str, **kwargs) -> Provenance:
    return Provenance(
        source_type=source_type,
        source_url=url,
        retrieved_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
        retrieval_mode=RETRIEVAL_MODE_MANUAL,
        outcome=outcome,
        content_sha256=POLICY_SHA if outcome == OUTCOME_SUCCESS else None,
        failure_reason=None if outcome == OUTCOME_SUCCESS else "recorded failure",
        **kwargs,
    )


def declaration(*, no_data: bool = False, entries=()) -> DataSafetyDeclaration:
    return DataSafetyDeclaration(
        package_name=PACKAGE,
        entries=tuple(entries),
        security=SecurityPractices(),
        declares_no_data_collected=no_data,
    )


def record(**overrides) -> ApplicationRecord:
    base = {
        "package_name": PACKAGE,
        "app_name": "Fixture App",
        "developer_name": "Fixture Labs",
        "store_category": "Tools",
        "play_store_url": LISTING,
        "policy_url": POLICY_URL,
        "declaration": declaration(
            entries=[
                DeclaredDataEntry(
                    ds_category="Personal info",
                    data_type="Email address",
                    is_collected=True,
                    is_shared=False,
                    purposes=("App functionality", "Analytics"),
                )
            ]
        ),
        "policy_path": None,
        "policy_sha256": None,
        "collected_at": datetime(2026, 11, 5, tzinfo=timezone.utc),
        "provenances": (
            provenance(SOURCE_DATA_SAFETY, OUTCOME_SUCCESS, LISTING),
            provenance(SOURCE_PRIVACY_POLICY, OUTCOME_SUCCESS, POLICY_URL),
        ),
        "validation_status": "complete",
    }
    base.update(overrides)
    return ApplicationRecord(**base)


# ---------------------------------------------------------------------------
# Status derivation (E-2)
# ---------------------------------------------------------------------------


def test_both_sources_present_is_complete(policy_file):
    assert (
        derive_status(record(policy_path=str(policy_file), policy_sha256=POLICY_SHA))
        == SNAPSHOT_COMPLETE
    )


def test_declaration_without_a_policy():
    assert derive_status(record()) == SNAPSHOT_DECLARATION_ONLY


def test_policy_without_a_declaration(policy_file):
    assert (
        derive_status(
            record(
                declaration=None,
                policy_path=str(policy_file),
                policy_sha256=POLICY_SHA,
                provenances=(
                    provenance(SOURCE_PRIVACY_POLICY, OUTCOME_SUCCESS, POLICY_URL),
                ),
            )
        )
        == SNAPSHOT_POLICY_ONLY
    )


def test_a_listing_with_no_data_safety_section_is_not_a_failure(policy_file):
    """`declaration_absent` is a fact about the application.

    A listing that was reached and carries no Data Safety section is different
    from a listing that could not be fetched. Collapsing the two would let a
    network problem read as an application that declares nothing.
    """
    assert (
        derive_status(
            record(
                declaration=None,
                policy_path=str(policy_file),
                policy_sha256=POLICY_SHA,
                provenances=(
                    provenance(SOURCE_DATA_SAFETY, OUTCOME_NOT_FOUND, LISTING),
                    provenance(SOURCE_PRIVACY_POLICY, OUTCOME_SUCCESS, POLICY_URL),
                ),
            )
        )
        == SNAPSHOT_DECLARATION_ABSENT
    )


def test_an_unparseable_listing_is_distinguished_from_an_absent_one(policy_file):
    """The remedy differs: a parse failure means the adapter needs updating."""
    assert (
        derive_status(
            record(
                declaration=None,
                policy_path=str(policy_file),
                policy_sha256=POLICY_SHA,
                provenances=(
                    provenance(SOURCE_DATA_SAFETY, OUTCOME_PARSE_FAILED, LISTING),
                    provenance(SOURCE_PRIVACY_POLICY, OUTCOME_SUCCESS, POLICY_URL),
                ),
            )
        )
        == SNAPSHOT_PARSE_FAILED
    )


def test_neither_source_captured_is_a_fetch_failure():
    assert (
        derive_status(
            record(
                declaration=None,
                provenances=(
                    provenance(SOURCE_DATA_SAFETY, OUTCOME_FETCH_FAILED, LISTING),
                    provenance(SOURCE_PRIVACY_POLICY, OUTCOME_FETCH_FAILED, POLICY_URL),
                ),
            )
        )
        == SNAPSHOT_FETCH_FAILED
    )


# ---------------------------------------------------------------------------
# F-07 — recording the event
# ---------------------------------------------------------------------------


def test_one_record_becomes_one_collection_event(session, app_id, policy_file):
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(
        app_id, record(policy_path=str(policy_file), policy_sha256=POLICY_SHA)
    )
    session.flush()

    assert snapshot.status == SNAPSHOT_COMPLETE
    assert snapshot.source_url_listing == LISTING
    assert snapshot.source_url_policy == POLICY_URL
    assert snapshot.policy_doc_sha256 == POLICY_SHA
    assert snapshot.is_active is True


def test_purposes_are_joined_into_the_single_approved_column(session, app_id):
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(app_id, record())
    session.flush()

    (practice,) = session.execute(
        select(DeclaredPractice).where(
            DeclaredPractice.snapshot_id == snapshot.snapshot_id
        )
    ).scalars()
    assert practice.purpose == "App functionality; Analytics"


def test_only_declared_categories_get_rows(session, app_id):
    """An absent category must stay absent.

    A row per known category, with is_collected false for the unmentioned
    ones, would turn "not mentioned" into "declared not collected" — a
    different disclosure and a different verdict under ALG-8.
    """
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(app_id, record())
    session.flush()

    categories = session.execute(
        select(DeclaredPractice.ds_category).where(
            DeclaredPractice.snapshot_id == snapshot.snapshot_id
        )
    ).scalars().all()
    assert categories == ["Personal info"]


def test_a_failed_collection_writes_no_declared_practices(session, app_id):
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(
        app_id,
        record(
            declaration=None,
            provenances=(
                provenance(SOURCE_DATA_SAFETY, OUTCOME_FETCH_FAILED, LISTING),
                provenance(SOURCE_PRIVACY_POLICY, OUTCOME_FETCH_FAILED, POLICY_URL),
            ),
        ),
    )
    session.flush()

    assert snapshot.status == SNAPSHOT_FETCH_FAILED
    assert (
        session.execute(
            select(DeclaredPractice).where(
                DeclaredPractice.snapshot_id == snapshot.snapshot_id
            )
        ).first()
        is None
    )


def test_an_unread_section_leaves_the_flag_unknown(session, app_id, policy_file):
    """NULL, not False. The difference is the whole point of the column."""
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(
        app_id,
        record(
            declaration=None,
            policy_path=str(policy_file),
            policy_sha256=POLICY_SHA,
            provenances=(
                provenance(SOURCE_PRIVACY_POLICY, OUTCOME_SUCCESS, POLICY_URL),
            ),
        ),
    )
    session.flush()
    assert snapshot.declares_no_data_collected is None


def test_an_explicit_no_collection_declaration_is_recorded_as_true(session, app_id):
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(
        app_id, record(declaration=declaration(no_data=True))
    )
    session.flush()
    assert snapshot.declares_no_data_collected is True


def test_a_read_section_without_the_statement_is_false(session, app_id):
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(app_id, record())
    session.flush()
    assert snapshot.declares_no_data_collected is False


def test_a_record_with_no_source_at_all_is_rejected(session, app_id):
    with pytest.raises(ValueError, match="neither a listing URL nor a policy URL"):
        SnapshotRepository(session).record_collection_event(
            app_id,
            record(
                play_store_url=None,
                policy_url=None,
                declaration=None,
                provenances=(),
            ),
        )


def test_a_new_event_supersedes_the_previous_active_one(session, app_id):
    repo = SnapshotRepository(session)
    first = repo.record_collection_event(app_id, record())
    second = repo.record_collection_event(app_id, record())
    session.flush()

    assert first.is_active is False
    assert second.is_active is True
    assert len(repo.history_for_app(app_id)) == 2


# ---------------------------------------------------------------------------
# F-04 — loading the declaration back
# ---------------------------------------------------------------------------


def test_the_declaration_round_trips(session, app_id):
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(app_id, record())
    session.flush()

    loaded = repo.load_declaration(snapshot.snapshot_id)
    assert loaded is not None
    (entry,) = loaded.entries
    assert entry.ds_category == "Personal info"
    assert entry.data_type == "Email address"
    assert entry.is_collected is True
    assert entry.purposes == ("App functionality", "Analytics")


def test_loading_a_declaration_that_was_never_read_returns_none(
    session, app_id, policy_file
):
    """None, not an empty declaration.

    An empty `DataSafetyDeclaration` asserts "we read the section and it
    declares nothing". None says "we never read it". Returning the former
    here would manufacture a disclosure.
    """
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(
        app_id,
        record(
            declaration=None,
            policy_path=str(policy_file),
            policy_sha256=POLICY_SHA,
            provenances=(
                provenance(SOURCE_PRIVACY_POLICY, OUTCOME_SUCCESS, POLICY_URL),
            ),
        ),
    )
    session.flush()
    assert repo.load_declaration(snapshot.snapshot_id) is None


def test_loading_an_unknown_snapshot_raises(session):
    with pytest.raises(SnapshotNotFoundError):
        SnapshotRepository(session).load_declaration(999999)


# ---------------------------------------------------------------------------
# F-05 — loading the policy document
# ---------------------------------------------------------------------------


def test_the_policy_document_loads_and_verifies(session, app_id, policy_file):
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(
        app_id, record(policy_path=str(policy_file), policy_sha256=POLICY_SHA)
    )
    session.flush()

    loaded = repo.load_policy_document(snapshot.snapshot_id)
    assert loaded is not None
    assert loaded.content_sha256 == POLICY_SHA
    assert "email address" in loaded.content


def test_an_event_without_a_policy_returns_none(session, app_id):
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(app_id, record())
    session.flush()
    assert repo.load_policy_document(snapshot.snapshot_id) is None


def test_a_missing_file_is_reported_not_silently_skipped(
    session, app_id, policy_file
):
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(
        app_id, record(policy_path=str(policy_file), policy_sha256=POLICY_SHA)
    )
    session.flush()
    policy_file.unlink()

    with pytest.raises(PolicyDocumentUnavailableError, match="does not"):
        repo.load_policy_document(snapshot.snapshot_id)


def test_a_changed_document_is_refused(session, app_id, policy_file):
    """Evidence quoted from a changed document would not be what was audited."""
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(
        app_id, record(policy_path=str(policy_file), policy_sha256=POLICY_SHA)
    )
    session.flush()
    policy_file.write_bytes(b"<html><body><p>Entirely different.</p></body></html>")

    with pytest.raises(PolicyDocumentUnavailableError, match="hashes to"):
        repo.load_policy_document(snapshot.snapshot_id)


# ---------------------------------------------------------------------------
# Reading events back
# ---------------------------------------------------------------------------


def test_latest_for_app_returns_the_active_event(session, app_id):
    repo = SnapshotRepository(session)
    repo.record_collection_event(app_id, record())
    second = repo.record_collection_event(app_id, record())
    session.flush()

    latest = repo.latest_for_app(app_id)
    assert latest is not None
    assert latest.snapshot_id == second.snapshot_id
    assert latest.has_declaration is True
    assert latest.has_policy is False


def test_latest_for_an_application_with_no_events_is_none(session, app_id):
    assert SnapshotRepository(session).latest_for_app(app_id) is None


# ---------------------------------------------------------------------------
# Corpus import: application upsert plus collection event
# ---------------------------------------------------------------------------


def test_upsert_creates_then_refreshes(session):
    from app.db.repositories import ApplicationRepository

    repo = ApplicationRepository(session)
    app_id, created = repo.upsert_from_record(record())
    assert created is True

    same_id, created_again = repo.upsert_from_record(
        record(app_name="Fixture App v2", developer_name="Renamed Labs")
    )
    assert same_id == app_id
    assert created_again is False

    stored = repo.get_by_package(PACKAGE)
    assert stored is not None
    assert stored.app_name == "Fixture App v2"
    assert stored.developer_name == "Renamed Labs"
    assert stored.last_seen_at is not None


def test_a_later_record_missing_a_field_does_not_blank_it(session):
    """A collector who could not read the developer name this time has not
    discovered that the application has none."""
    from app.db.repositories import ApplicationRepository

    repo = ApplicationRepository(session)
    repo.upsert_from_record(record())
    repo.upsert_from_record(record(developer_name=None, store_category=None))

    stored = repo.get_by_package(PACKAGE)
    assert stored is not None
    assert stored.developer_name == "Fixture Labs"
    assert stored.store_category == "Tools"


def test_import_then_audit_preconditions_hold(session, policy_file):
    """The import path end to end: corpus record in, auditable event out."""
    from app.db.repositories import ApplicationRepository

    app_id, _ = ApplicationRepository(session).upsert_from_record(record())
    repo = SnapshotRepository(session)
    repo.record_collection_event(
        app_id, record(policy_path=str(policy_file), policy_sha256=POLICY_SHA)
    )
    session.flush()

    latest = repo.latest_for_app(app_id)
    assert latest is not None
    assert latest.status == SNAPSHOT_COMPLETE
    assert latest.has_declaration and latest.has_policy

    loaded = repo.load_policy_document(latest.snapshot_id)
    assert loaded is not None and loaded.content_sha256 == POLICY_SHA
    declaration_back = repo.load_declaration(latest.snapshot_id)
    assert declaration_back is not None and len(declaration_back.entries) == 1


def test_a_partial_record_still_imports(session):
    """A corpus of only the records that worked would misrepresent itself."""
    from app.db.repositories import ApplicationRepository

    app_id, _ = ApplicationRepository(session).upsert_from_record(record())
    snapshot = SnapshotRepository(session).record_collection_event(
        app_id,
        record(
            declaration=None,
            provenances=(
                provenance(SOURCE_DATA_SAFETY, OUTCOME_NOT_FOUND, LISTING),
                provenance(SOURCE_PRIVACY_POLICY, OUTCOME_FETCH_FAILED, POLICY_URL),
            ),
        ),
    )
    session.flush()
    assert snapshot.status == SNAPSHOT_FETCH_FAILED
    assert snapshot.declares_no_data_collected is None


# ---------------------------------------------------------------------------
# C-64: a failed declaration side does not hide a retrieved policy
# ---------------------------------------------------------------------------


def _event_with_policy_but_no_declaration(session, app_id, policy_file, outcome):
    return SnapshotRepository(session).record_collection_event(
        app_id,
        record(
            declaration=None,
            policy_path=str(policy_file),
            policy_sha256=POLICY_SHA,
            provenances=(
                provenance(SOURCE_DATA_SAFETY, outcome, LISTING),
                provenance(SOURCE_PRIVACY_POLICY, OUTCOME_SUCCESS, POLICY_URL),
            ),
        ),
    )


@pytest.mark.parametrize(
    "outcome,expected_status",
    [
        (OUTCOME_NOT_FOUND, SNAPSHOT_DECLARATION_ABSENT),
        (OUTCOME_PARSE_FAILED, SNAPSHOT_PARSE_FAILED),
    ],
)
def test_a_policy_loads_even_when_the_declaration_side_failed(
    session, app_id, policy_file, outcome, expected_status
):
    """C-64. The bug this replaces returned None for a stored document.

    `declaration_absent` and `parse_failed` describe what happened to the
    **declaration**. The policy was retrieved normally in both cases, and
    `derive_status` only returns either when a document is present. Excluding
    them from SNAPSHOT_HAS_POLICY made load_policy_document refuse to read a
    document the row was holding — silently, by returning None rather than
    raising, so it read as "this event has no policy".
    """
    repo = SnapshotRepository(session)
    snapshot = _event_with_policy_but_no_declaration(
        session, app_id, policy_file, outcome
    )
    session.flush()
    assert snapshot.status == expected_status

    loaded = repo.load_policy_document(snapshot.snapshot_id)
    assert loaded is not None, f"{expected_status} hides its policy document"
    assert loaded.content_sha256 == POLICY_SHA

    # The declaration is still absent, which is the other half of the point.
    assert repo.load_declaration(snapshot.snapshot_id) is None


def test_the_summary_agrees_with_what_can_be_loaded(session, app_id, policy_file):
    repo = SnapshotRepository(session)
    _event_with_policy_but_no_declaration(
        session, app_id, policy_file, OUTCOME_NOT_FOUND
    )
    session.flush()

    summary = repo.latest_for_app(app_id)
    assert summary is not None
    assert summary.has_policy is True
    assert summary.has_declaration is False


def test_every_status_that_implies_a_policy_is_in_the_has_policy_set():
    """The structural guard, not just the two cases above.

    `derive_status` decides, from a record, which statuses can occur with a
    policy document present. Anything it can return there must be in
    SNAPSHOT_HAS_POLICY, or a stored document becomes unreadable again the
    next time a status is added.
    """
    from analysis.vocabulary import SNAPSHOT_HAS_POLICY

    reachable_with_policy = set()
    for outcome in (
        OUTCOME_SUCCESS,
        OUTCOME_NOT_FOUND,
        OUTCOME_PARSE_FAILED,
        OUTCOME_FETCH_FAILED,
    ):
        for has_declaration in (True, False):
            candidate = record(
                declaration=declaration() if has_declaration else None,
                policy_path="data/policies/raw/x.html",
                policy_sha256=POLICY_SHA,
                provenances=(
                    provenance(SOURCE_DATA_SAFETY, outcome, LISTING),
                    provenance(SOURCE_PRIVACY_POLICY, OUTCOME_SUCCESS, POLICY_URL),
                ),
            )
            reachable_with_policy.add(derive_status(candidate))

    missing = reachable_with_policy - SNAPSHOT_HAS_POLICY
    assert not missing, (
        "derive_status can return these for an event that holds a policy "
        f"document, but SNAPSHOT_HAS_POLICY excludes them: {sorted(missing)}"
    )


def test_every_status_that_implies_a_declaration_is_in_its_set():
    """The same guard for the declaration side."""
    from analysis.vocabulary import SNAPSHOT_HAS_DECLARATION

    reachable = {
        derive_status(record()),
        derive_status(
            record(policy_path="data/policies/raw/x.html", policy_sha256=POLICY_SHA)
        ),
    }
    assert reachable <= SNAPSHOT_HAS_DECLARATION
