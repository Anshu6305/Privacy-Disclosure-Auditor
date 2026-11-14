"""What the worker says about itself before it starts polling.

Audit 9 sat `queued` in `privacy_auditor_pilot` while the worker polled
`privacy_auditor`, because `.env` sets POSTGRES_DB and
`scripts/request_audit.py` defaults to `--database privacy_auditor_pilot`.
The worker logged only "worker started; one audit at a time", so a worker
attached to the wrong database was indistinguishable from an empty queue
(C-96).

The startup line now names the target and the queue depth. These tests pin
the two things that line must get right: it identifies the database, and it
never prints the password.
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
from app.worker.worker import count_queued, describe_target
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from analysis.vocabulary import (
    SNAPSHOT_COMPLETE,
    STATUS_COMPLETED,
    STATUS_QUEUED,
    TASK_ALIGNMENT,
    TASK_CLASSIFICATION,
    TASK_SPAN_EXTRACTION,
    VARIANT_BASELINE,
)

SECRET = "sup3r-s3cret-pw"
URL = f"postgresql+psycopg://auditor:{SECRET}@localhost:5432/privacy_auditor_pilot"


# -- the startup line ------------------------------------------------------


def test_the_target_names_host_port_and_database():
    """The fact that was missing from the logs."""
    assert describe_target(URL) == "localhost:5432/privacy_auditor_pilot"


def test_the_target_never_contains_the_password():
    """Credentials are not printed anywhere in this project."""
    described = describe_target(URL)

    assert SECRET not in described
    assert "auditor:" not in described


@pytest.mark.parametrize(
    "database", ["privacy_auditor", "privacy_auditor_pilot"]
)
def test_two_databases_on_one_host_are_distinguishable(database):
    """The whole point: the two differ only in the database name, so the line
    has to include it."""
    url = f"postgresql+psycopg://auditor:{SECRET}@localhost:5432/{database}"

    assert describe_target(url).endswith(f"/{database}")


# -- the queue depth -------------------------------------------------------


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as open_session:
        yield open_session


def queue_one(session: Session, status: str) -> None:
    application = Application(
        package_name=f"com.example.{status}", app_name="Queue App"
    )
    session.add(application)
    session.flush()
    snapshot = DisclosureSnapshot(
        app_id=application.app_id,
        collected_at=datetime(2026, 11, 11, tzinfo=timezone.utc),
        source_url_listing="https://play.google.com/x",
        source_url_policy="https://example.invalid/p",
        retrieval_mode="manual_import",
        policy_doc_path="data/policies/raw/p.html",
        policy_doc_sha256="a" * 64,
        status=SNAPSHOT_COMPLETE,
        declares_no_data_collected=False,
    )
    mapping = TaxonomyMappingVersion(
        version_label=f"map-{status}", is_active=True
    )
    session.add_all([snapshot, mapping])
    session.flush()
    ids = []
    for task in (TASK_CLASSIFICATION, TASK_SPAN_EXTRACTION, TASK_ALIGNMENT):
        model = ModelVersion(
            task=task,
            variant=VARIANT_BASELINE,
            model_identifier=f"real/{task}-{status}",
            version_label=f"{task}-{status}-v1",
            checkpoint_path=f"ml/checkpoints/{task}",
            is_active=True,
        )
        session.add(model)
        session.flush()
        ids.append(model.model_version_id)
    session.add(
        AuditRun(
            app_id=application.app_id,
            snapshot_id=snapshot.snapshot_id,
            taxonomy_mapping_version_id=mapping.taxonomy_mapping_version_id,
            classification_model_id=ids[0],
            span_model_id=ids[1],
            alignment_model_id=ids[2],
            status=status,
            # ck_audit_completed_has_timestamp: a completed audit carries one.
            completed_at=(
                datetime(2026, 11, 11, tzinfo=timezone.utc)
                if status == STATUS_COMPLETED
                else None
            ),
            threshold_config={"classifier": 0.5},
        )
    )
    session.flush()


def test_an_empty_queue_counts_zero_rather_than_raising(session):
    """This runs before the loop, so it must not be the thing that crashes a
    worker attached to a database with nothing in it."""
    assert count_queued(session) == 0


def test_only_queued_audits_are_counted(session):
    queue_one(session, STATUS_QUEUED)
    queue_one(session, STATUS_COMPLETED)

    assert count_queued(session) == 1


def test_a_running_audit_is_reported_because_it_blocks_the_queue(session):
    """DD-2 allows one active audit, so a stuck `running` row looks exactly
    like an idle worker unless the startup line says so."""
    from app.worker.worker import count_by_status

    from analysis.vocabulary import STATUS_RUNNING

    queue_one(session, STATUS_QUEUED)
    queue_one(session, STATUS_RUNNING)

    assert count_queued(session) == 1
    assert count_by_status(session, STATUS_RUNNING) == 1
