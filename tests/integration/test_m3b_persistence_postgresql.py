"""M3B Part 2 on real PostgreSQL — F-02, F-04, F-05, F-06, F-07.

The unit suite runs these paths on SQLite with the same metadata. What only
PostgreSQL can answer is whether the database **enforces** the collection-event
constraints the repositories rely on, whether `declares_no_data_collected`
really round-trips as three states through a real `boolean` column, and
whether the JSONB threshold config written by F-02 comes back as a dict.

**Safety.** Same contract as the rest of this directory: only the database
named in `TEST_DATABASE_URL`, only one whose name ends in `_test`, every test
inside a transaction that is rolled back. No DDL, no DROP, no TRUNCATE.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db.models import (
    Application,
    AuditRun,
    DeclaredPractice,
    ModelVersion,
    TaxonomyMappingVersion,
)
from app.db.repositories import (
    ApplicationRepository,
    PolicyDocumentUnavailableError,
    SnapshotRepository,
)
from app.services.acquisition_service import LiveAcquisitionService, LiveRetrievalResult
from app.services.audit_service import (
    REASON_POLICY_MISSING,
    AuditRequested,
    AuditRequestRefused,
    AuditService,
)
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from acquisition.gateway import AcquisitionGateway
from acquisition.models import (
    OUTCOME_FETCH_FAILED,
    OUTCOME_NOT_FOUND,
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
    MODEL_TASKS,
    SNAPSHOT_COMPLETE,
    SNAPSHOT_DECLARATION_ONLY,
    SOURCE_DATA_SAFETY,
    SOURCE_PRIVACY_POLICY,
)

pytestmark = pytest.mark.integration

TEST_URL_VAR = "TEST_DATABASE_URL"
BACKEND = Path(__file__).resolve().parents[2] / "backend"
HEAD_REQUIRED = "0003_collection_event"

POLICY_BODY = b"<html><body><p>We collect your email address.</p></body></html>"
POLICY_SHA = sha256_of_bytes(POLICY_BODY)
LISTING = "https://play.google.com/store/apps/details?id="
POLICY_URL = "https://example.invalid/privacy.html"


@pytest.fixture(scope="module")
def pg_engine():
    url = os.environ.get(TEST_URL_VAR)
    if not url:
        pytest.skip(f"{TEST_URL_VAR} is not set; these tests never guess a database.")
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail(f"{TEST_URL_VAR} names {database!r}, which does not end in '_test'")
    try:
        engine = create_engine(url, future=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL not usable here: {type(exc).__name__}: {exc}")
    return engine


@pytest.fixture(scope="module", autouse=True)
def requires_collection_event_schema(pg_engine) -> None:
    """These exercise the Option A repositories, so they need revision 0003."""
    if "disclosure_snapshot" not in set(inspect(pg_engine).get_table_names()):
        pytest.fail("the test database has no schema; apply the migrations first")

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    scripts = ScriptDirectory.from_config(config)

    with pg_engine.connect() as connection:
        current = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars().all()
    ancestry = (
        {s.revision for s in scripts.iterate_revisions(current[0], "base")}
        if current
        else set()
    )
    if HEAD_REQUIRED not in ancestry:
        pytest.skip(
            f"{HEAD_REQUIRED} is not in this database's applied ancestry "
            f"({sorted(ancestry) or 'none'}). M3B Part 2 needs the "
            "collection-event schema."
        )


@pytest.fixture
def session(pg_engine):
    """A session whose work is always rolled back."""
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def package(session) -> str:
    """A package name unique to this test, so rows never collide."""
    return f"com.test.m3b{os.urandom(4).hex()}"


@pytest.fixture
def policy_file(tmp_path):
    path = tmp_path / "policies" / f"{POLICY_SHA}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(POLICY_BODY)
    return path


def provenance(source_type: str, outcome: str, url: str) -> Provenance:
    return Provenance(
        source_type=source_type,
        source_url=url,
        retrieved_at=datetime(2026, 11, 6, tzinfo=timezone.utc),
        retrieval_mode=RETRIEVAL_MODE_MANUAL,
        outcome=outcome,
        content_sha256=POLICY_SHA if outcome == OUTCOME_SUCCESS else None,
        failure_reason=None if outcome == OUTCOME_SUCCESS else "recorded failure",
    )


def make_record(package: str, *, policy_path=None, declaration=True, **overrides):
    base = {
        "package_name": package,
        "app_name": "M3B Integration App",
        "developer_name": "Integration Labs",
        "store_category": "Tools",
        "play_store_url": LISTING + package,
        "policy_url": POLICY_URL,
        "declaration": (
            DataSafetyDeclaration(
                package_name=package,
                entries=(
                    DeclaredDataEntry(
                        ds_category="Personal info",
                        data_type="Email address",
                        is_collected=True,
                        is_shared=False,
                        purposes=("App functionality", "Analytics"),
                    ),
                ),
                security=SecurityPractices(),
                declares_no_data_collected=False,
            )
            if declaration
            else None
        ),
        "policy_path": str(policy_path) if policy_path else None,
        "policy_sha256": POLICY_SHA if policy_path else None,
        "collected_at": datetime(2026, 11, 6, tzinfo=timezone.utc),
        "provenances": (
            provenance(SOURCE_DATA_SAFETY, OUTCOME_SUCCESS, LISTING + package),
            provenance(SOURCE_PRIVACY_POLICY, OUTCOME_SUCCESS, POLICY_URL),
        ),
        "validation_status": "complete",
    }
    base.update(overrides)
    return ApplicationRecord(**base)


def seed_models(session) -> None:
    suffix = os.urandom(4).hex()
    session.add(TaxonomyMappingVersion(version_label=f"v-{suffix}", is_active=True))
    for task in MODEL_TASKS:
        session.add(
            ModelVersion(
                task=task,
                variant="baseline",
                model_identifier="stub",
                version_label=f"{task}-{suffix}",
                is_active=True,
            )
        )
    session.flush()


# ---------------------------------------------------------------------------
# F-07 — persistence
# ---------------------------------------------------------------------------


def test_a_collection_event_persists_to_postgresql(session, package, policy_file):
    app_id, created = ApplicationRepository(session).upsert_from_record(
        make_record(package, policy_path=policy_file)
    )
    assert created is True

    snapshot = SnapshotRepository(session).record_collection_event(
        app_id, make_record(package, policy_path=policy_file)
    )
    session.flush()

    assert snapshot.status == SNAPSHOT_COMPLETE
    assert snapshot.policy_doc_sha256 == POLICY_SHA
    assert snapshot.collected_at.tzinfo is not None


def test_declared_practices_persist_with_joined_purposes(session, package):
    app_id, _ = ApplicationRepository(session).upsert_from_record(make_record(package))
    snapshot = SnapshotRepository(session).record_collection_event(
        app_id, make_record(package)
    )
    session.flush()

    (practice,) = session.execute(
        select(DeclaredPractice).where(
            DeclaredPractice.snapshot_id == snapshot.snapshot_id
        )
    ).scalars()
    assert practice.purpose == "App functionality; Analytics"


def test_the_three_states_of_the_no_collection_flag_round_trip(session, package):
    """A real boolean column, where NULL and False are different values."""
    repo = SnapshotRepository(session)
    applications = ApplicationRepository(session)

    app_id, _ = applications.upsert_from_record(make_record(package))
    read_no_statement = repo.record_collection_event(app_id, make_record(package))
    session.flush()
    assert read_no_statement.declares_no_data_collected is False

    unread = repo.record_collection_event(
        app_id,
        make_record(
            package,
            declaration=False,
            policy_path=None,
            provenances=(
                provenance(SOURCE_PRIVACY_POLICY, OUTCOME_FETCH_FAILED, POLICY_URL),
            ),
        ),
    )
    session.flush()
    assert unread.declares_no_data_collected is None


def test_postgresql_rejects_a_status_outside_the_vocabulary(session, package):
    """E-2's CHECK, enforced by the database rather than only declared."""
    from app.db.models import DisclosureSnapshot
    from sqlalchemy.exc import IntegrityError

    application = Application(package_name=package, app_name="X")
    session.add(application)
    session.flush()

    session.add(
        DisclosureSnapshot(
            app_id=application.app_id,
            source_url_listing=LISTING + package,
            retrieval_mode="manual_import",
            status="sort_of_worked",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_postgresql_rejects_complete_without_both_urls(session, package):
    """A partial event cannot be recorded as complete."""
    from app.db.models import DisclosureSnapshot
    from sqlalchemy.exc import IntegrityError

    application = Application(package_name=package, app_name="X")
    session.add(application)
    session.flush()

    session.add(
        DisclosureSnapshot(
            app_id=application.app_id,
            source_url_policy=POLICY_URL,
            retrieval_mode="manual_import",
            status=SNAPSHOT_COMPLETE,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


# ---------------------------------------------------------------------------
# Duplicate handling
# ---------------------------------------------------------------------------


def test_re_importing_refreshes_rather_than_duplicating(session, package):
    repo = ApplicationRepository(session)
    first_id, created = repo.upsert_from_record(make_record(package))
    second_id, created_again = repo.upsert_from_record(
        make_record(package, app_name="Renamed")
    )
    session.flush()

    assert (first_id, created, created_again) == (second_id, True, False)
    stored = repo.get_by_package(package)
    assert stored is not None and stored.app_name == "Renamed"
    assert stored.last_seen_at is not None


def test_a_second_event_supersedes_the_first_in_postgresql(session, package):
    app_id, _ = ApplicationRepository(session).upsert_from_record(make_record(package))
    repo = SnapshotRepository(session)
    first = repo.record_collection_event(app_id, make_record(package))
    second = repo.record_collection_event(app_id, make_record(package))
    session.flush()

    assert first.is_active is False
    assert second.is_active is True
    assert len(repo.history_for_app(app_id)) == 2
    latest = repo.latest_for_app(app_id)
    assert latest is not None and latest.snapshot_id == second.snapshot_id


# ---------------------------------------------------------------------------
# F-04 and F-05 — loading back
# ---------------------------------------------------------------------------


def test_the_declaration_round_trips_through_postgresql(session, package):
    app_id, _ = ApplicationRepository(session).upsert_from_record(make_record(package))
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(app_id, make_record(package))
    session.flush()

    loaded = repo.load_declaration(snapshot.snapshot_id)
    assert loaded is not None
    (entry,) = loaded.entries
    assert entry.purposes == ("App functionality", "Analytics")
    assert entry.is_collected is True


def test_an_unread_declaration_loads_as_none_not_empty(session, package, policy_file):
    app_id, _ = ApplicationRepository(session).upsert_from_record(make_record(package))
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(
        app_id,
        make_record(
            package,
            declaration=False,
            policy_path=policy_file,
            provenances=(
                provenance(SOURCE_PRIVACY_POLICY, OUTCOME_SUCCESS, POLICY_URL),
            ),
        ),
    )
    session.flush()
    assert repo.load_declaration(snapshot.snapshot_id) is None


def test_hash_verification_runs_on_every_load(session, package, policy_file):
    app_id, _ = ApplicationRepository(session).upsert_from_record(make_record(package))
    repo = SnapshotRepository(session)
    snapshot = repo.record_collection_event(
        app_id, make_record(package, policy_path=policy_file)
    )
    session.flush()

    loaded = repo.load_policy_document(snapshot.snapshot_id)
    assert loaded is not None and loaded.content_sha256 == POLICY_SHA

    policy_file.write_bytes(b"<html><body>changed</body></html>")
    with pytest.raises(PolicyDocumentUnavailableError, match="hashes to"):
        repo.load_policy_document(snapshot.snapshot_id)


# ---------------------------------------------------------------------------
# F-02 — audit requests
# ---------------------------------------------------------------------------


def test_an_audit_is_queued_for_a_complete_event(session, package, policy_file):
    app_id, _ = ApplicationRepository(session).upsert_from_record(make_record(package))
    SnapshotRepository(session).record_collection_event(
        app_id, make_record(package, policy_path=policy_file)
    )
    seed_models(session)

    result = AuditService(session).request_audit(package)
    assert isinstance(result, AuditRequested)
    session.flush()

    audit = session.get(AuditRun, result.audit_id)
    assert audit is not None
    # JSONB round trip: a dict in, a dict out.
    assert isinstance(audit.threshold_config, dict)
    assert audit.threshold_config["provisional"] is True


def test_a_partial_event_is_refused_and_writes_no_audit(session, package):
    app_id, _ = ApplicationRepository(session).upsert_from_record(make_record(package))
    snapshot = SnapshotRepository(session).record_collection_event(
        app_id, make_record(package)
    )
    session.flush()
    assert snapshot.status == SNAPSHOT_DECLARATION_ONLY
    seed_models(session)

    before = session.execute(select(AuditRun)).all()
    result = AuditService(session).request_audit(package)
    session.flush()

    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_POLICY_MISSING
    assert session.execute(select(AuditRun)).all() == before


# ---------------------------------------------------------------------------
# F-06 — live retrieval, through a controlled adapter
# ---------------------------------------------------------------------------


class _FakeAdapter:
    def __init__(self, responses: dict[str, tuple[int, bytes]]) -> None:
        self._responses = responses
        self.requested: list[str] = []

    def fetch(self, url: str) -> tuple[int, bytes]:
        self.requested.append(url)
        for fragment, response in self._responses.items():
            if fragment in url:
                return response
        return 404, b""


def test_live_retrieval_persists_a_partial_event_honestly(
    session, package, tmp_path
):
    """No parser is configured, which is the project's real state.

    The Data Safety page is reached and not understood. The event must record
    that, not an application that declares nothing.
    """
    adapter = _FakeAdapter(
        {"datasafety": (200, b"<html>data safety</html>"), "privacy.html": (200, POLICY_BODY)}
    )
    service = LiveAcquisitionService(
        session,
        AcquisitionGateway(adapter=adapter),
        corpus_root=tmp_path / "corpus",
        repository_root=tmp_path,
    )
    result = service.collect(package, policy_url=POLICY_URL)
    session.flush()

    assert isinstance(result, LiveRetrievalResult)
    assert result.succeeded is False
    assert result.snapshot_id is not None

    snapshot = SnapshotRepository(session).latest_for_app(
        ApplicationRepository(session).get_by_package(package).app_id
    )
    assert snapshot is not None
    assert snapshot.declares_no_data_collected is None


def test_live_retrieval_is_unavailable_without_an_adapter(session, package, tmp_path):
    """Offline-first: a deployment with no adapter is supported."""
    from app.services.acquisition_service import LiveRetrievalUnavailable

    service = LiveAcquisitionService(
        session,
        AcquisitionGateway(adapter=None),
        corpus_root=tmp_path / "corpus",
        repository_root=tmp_path,
    )
    assert service.available is False
    assert isinstance(
        service.collect(package, policy_url=POLICY_URL), LiveRetrievalUnavailable
    )


def test_a_live_stored_document_verifies_when_loaded_back(
    session, package, tmp_path
):
    """F-06 into F-05, against the real database."""
    adapter = _FakeAdapter({"privacy.html": (200, POLICY_BODY)})
    service = LiveAcquisitionService(
        session,
        AcquisitionGateway(adapter=adapter),
        corpus_root=tmp_path / "corpus",
        repository_root=tmp_path,
    )
    result = service.collect(package, policy_url=POLICY_URL)
    session.flush()

    assert isinstance(result, LiveRetrievalResult)
    loaded = SnapshotRepository(session, policy_root=tmp_path).load_policy_document(
        result.snapshot_id
    )
    assert loaded is not None
    assert loaded.content_sha256 == POLICY_SHA


def test_a_not_found_declaration_is_not_an_empty_declaration(
    session, package, tmp_path
):
    adapter = _FakeAdapter({"privacy.html": (200, POLICY_BODY)})
    service = LiveAcquisitionService(
        session,
        AcquisitionGateway(adapter=adapter),
        corpus_root=tmp_path / "corpus",
        repository_root=tmp_path,
    )
    result = service.collect(package, policy_url=POLICY_URL)
    session.flush()

    assert isinstance(result, LiveRetrievalResult)
    assert result.declaration_outcome == OUTCOME_NOT_FOUND
    app = ApplicationRepository(session).get_by_package(package)
    assert app is not None
    assert SnapshotRepository(session).load_declaration(result.snapshot_id) is None
