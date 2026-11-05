"""F-02 — requesting an audit.

Most of these assert a **refusal**. Creating an `audit_run` row commits the
system to producing a report, and a report built from one disclosure source
would compare something against nothing — which ALG-8 would have to call
either agreement or absence, both wrong. The preconditions are therefore
checked before the row exists.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.db.models import (
    Application,
    AuditRun,
    Base,
    DisclosureSnapshot,
    ModelVersion,
    TaxonomyMappingVersion,
)
from app.services.audit_service import (
    REASON_DECLARATION_MISSING,
    REASON_NO_COLLECTION_EVENT,
    REASON_NO_MODEL,
    REASON_NO_TAXONOMY_MAPPING,
    REASON_POLICY_MISSING,
    REASON_SOURCES_MISSING,
    REASON_UNKNOWN_APPLICATION,
    AuditRequested,
    AuditRequestRefused,
    AuditService,
)
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from analysis.vocabulary import (
    MODEL_TASKS,
    SNAPSHOT_COMPLETE,
    SNAPSHOT_DECLARATION_ONLY,
    SNAPSHOT_FETCH_FAILED,
    SNAPSHOT_POLICY_ONLY,
    STATUS_QUEUED,
)

PACKAGE = "com.example.auditable"
LISTING = "https://play.google.com/store/apps/details?id=com.example.auditable"
POLICY_URL = "https://example.com/privacy"


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


def add_application(session: Session) -> Application:
    application = Application(package_name=PACKAGE, app_name="Auditable App")
    session.add(application)
    session.flush()
    return application


def add_snapshot(session: Session, app_id: int, status: str = SNAPSHOT_COMPLETE):
    snapshot = DisclosureSnapshot(
        app_id=app_id,
        collected_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
        source_url_listing=LISTING,
        source_url_policy=POLICY_URL,
        retrieval_mode="manual_import",
        policy_doc_path="data/policies/raw/a.html",
        policy_doc_sha256="a" * 64,
        status=status,
        declares_no_data_collected=False,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def add_models_and_mapping(session: Session, *, skip_task: str | None = None) -> None:
    session.add(TaxonomyMappingVersion(version_label="v1", is_active=True))
    for task in MODEL_TASKS:
        if task == skip_task:
            continue
        session.add(
            ModelVersion(
                task=task,
                variant="baseline",
                model_identifier=f"stub-{task}",
                version_label="v1",
                is_active=True,
            )
        )
    session.flush()


@pytest.fixture
def ready(session: Session):
    application = add_application(session)
    snapshot = add_snapshot(session, application.app_id)
    add_models_and_mapping(session)
    return application, snapshot


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_a_complete_collection_event_can_be_audited(session, ready):
    application, snapshot = ready
    result = AuditService(session).request_audit(PACKAGE)

    assert isinstance(result, AuditRequested)
    assert result.snapshot_id == snapshot.snapshot_id
    assert result.app_id == application.app_id

    (audit,) = session.execute(select(AuditRun)).scalars()
    assert audit.status == STATUS_QUEUED
    assert audit.snapshot_id == snapshot.snapshot_id


def test_every_input_is_pinned_to_the_run(session, ready):
    """Phase 3 requires that nothing about an audit's inputs is inferred
    afterwards."""
    result = AuditService(session).request_audit(PACKAGE)
    assert isinstance(result, AuditRequested)
    for identifier in (
        result.taxonomy_mapping_version_id,
        result.classification_model_id,
        result.span_model_id,
        result.alignment_model_id,
    ):
        assert identifier > 0


def test_thresholds_are_recorded_and_flagged_provisional(session, ready):
    """A report means nothing without the thresholds that produced it, and
    these have not been tuned on a gold set."""
    result = AuditService(session).request_audit(PACKAGE)
    assert isinstance(result, AuditRequested)
    assert set(result.threshold_config) == {
        "classifier",
        "span",
        "alignment",
        "provisional",
    }
    assert result.threshold_config["provisional"] is True


# ---------------------------------------------------------------------------
# Refusals — each a distinct cause with a distinct remedy
# ---------------------------------------------------------------------------


def test_an_unknown_application_is_refused(session):
    add_models_and_mapping(session)
    result = AuditService(session).request_audit("com.not.collected")
    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_UNKNOWN_APPLICATION


def test_an_application_with_no_collection_event_is_refused(session):
    add_application(session)
    add_models_and_mapping(session)
    result = AuditService(session).request_audit(PACKAGE)
    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_NO_COLLECTION_EVENT


@pytest.mark.parametrize(
    "status,expected_reason",
    [
        (SNAPSHOT_DECLARATION_ONLY, REASON_POLICY_MISSING),
        (SNAPSHOT_POLICY_ONLY, REASON_DECLARATION_MISSING),
        (SNAPSHOT_FETCH_FAILED, REASON_SOURCES_MISSING),
    ],
)
def test_a_partial_collection_event_is_refused(session, status, expected_reason):
    """The distinction this whole milestone protects.

    A missing source is not an absence of disclosure. Queueing the audit
    anyway would make ALG-8 choose between calling it agreement or absence,
    and both would be a claim the data cannot support.
    """
    application = add_application(session)
    add_snapshot(session, application.app_id, status=status)
    add_models_and_mapping(session)

    result = AuditService(session).request_audit(PACKAGE)
    assert isinstance(result, AuditRequestRefused)
    assert result.reason == expected_reason
    assert result.snapshot_status == status
    assert "absence of data" in result.detail


def test_a_refusal_creates_no_audit_row(session):
    application = add_application(session)
    add_snapshot(session, application.app_id, status=SNAPSHOT_POLICY_ONLY)
    add_models_and_mapping(session)

    AuditService(session).request_audit(PACKAGE)
    assert session.execute(select(AuditRun)).first() is None


def test_a_missing_taxonomy_mapping_is_refused(session):
    application = add_application(session)
    add_snapshot(session, application.app_id)
    for task in MODEL_TASKS:
        session.add(
            ModelVersion(
                task=task,
                variant="baseline",
                model_identifier=f"stub-{task}",
                version_label="v1",
                is_active=True,
            )
        )
    session.flush()

    result = AuditService(session).request_audit(PACKAGE)
    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_NO_TAXONOMY_MAPPING


@pytest.mark.parametrize("missing_task", MODEL_TASKS)
def test_a_missing_model_for_any_task_is_refused(session, missing_task):
    application = add_application(session)
    add_snapshot(session, application.app_id)
    add_models_and_mapping(session, skip_task=missing_task)

    result = AuditService(session).request_audit(PACKAGE)
    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_NO_MODEL
    assert missing_task in result.detail


def test_an_inactive_model_does_not_count(session):
    application = add_application(session)
    add_snapshot(session, application.app_id)
    session.add(TaxonomyMappingVersion(version_label="v1", is_active=True))
    for task in MODEL_TASKS:
        session.add(
            ModelVersion(
                task=task,
                variant="baseline",
                model_identifier=f"stub-{task}",
                version_label="v1",
                is_active=(task != "alignment"),
            )
        )
    session.flush()

    result = AuditService(session).request_audit(PACKAGE)
    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_NO_MODEL


def test_the_latest_collection_event_is_the_one_audited(session):
    application = add_application(session)
    old = add_snapshot(session, application.app_id)
    old.is_active = False
    newer = add_snapshot(session, application.app_id)
    add_models_and_mapping(session)

    result = AuditService(session).request_audit(PACKAGE)
    assert isinstance(result, AuditRequested)
    assert result.snapshot_id == newer.snapshot_id
