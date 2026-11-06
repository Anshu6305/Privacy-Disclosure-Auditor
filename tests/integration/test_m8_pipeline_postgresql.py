"""M8 on real PostgreSQL — the pipeline, the queue claim and the API.

The unit suite runs these paths on SQLite against the same metadata. What
only PostgreSQL can answer:

* whether the database **enforces** the audit-run and evidence constraints a
  complete run depends on, in particular `ck_judgement_has_at_least_one_side`
  and `ck_record_evidence_requires_quote`;
* whether `threshold_config` survives the round trip through a real `jsonb`
  column and comes back as a dict the report can read;
* whether `claim_next_audit` really takes the ``FOR UPDATE SKIP LOCKED``
  branch, so two workers cannot claim one audit — a clause SQLite ignores,
  which means the unit tests cannot test it at all;
* whether evidence offsets and quoted text survive real `integer` and `text`
  columns with non-ASCII characters intact.

**Every model used here is a controlled stub.** The audits these tests run
record `fixture:` identifiers and `uses_fixture_models` is True. Nothing here
demonstrates real inference.

**Safety.** Same contract as the rest of this directory: only the database
named in `TEST_DATABASE_URL`, only one whose name ends in `_test`, no DDL, no
DROP, no TRUNCATE. Every test runs inside a transaction that is rolled back,
with one exception documented at `committed_queue`, which needs two
connections to see the same row and deletes exactly the rows it inserted.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.api.schemas.audit import ReportOut
from app.db.models import (
    AlignmentJudgement as AlignmentJudgementRow,
)
from app.db.models import (
    Application,
    AuditRun,
    DeclaredPractice,
    DisclosureSnapshot,
    EvidenceRecord,
    ExtractedPractice,
    ModelVersion,
    PolicySegment,
    TaxonomyMappingVersion,
    Verdict,
)
from app.db.session import get_session
from app.main import create_app
from app.services.audit_pipeline import AuditPipeline, claim_next_audit
from app.services.model_registry import register_fixture_models
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from analysis.vocabulary import (
    SNAPSHOT_COMPLETE,
    STATUS_COMPLETED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    VERDICT_IN_POLICY_NOT_DECLARED,
)
from tests.unit.test_audit_pipeline import (
    POLICY_HTML,
    StubAligner,
    StubClassifier,
    stub_mapper,
)

pytestmark = pytest.mark.integration

TEST_URL_VAR = "TEST_DATABASE_URL"
BACKEND = Path(__file__).resolve().parents[2] / "backend"
HEAD_REQUIRED = "0003_collection_event"

#: A non-ASCII character in the policy, so the round trip through `text` is
#: tested rather than assumed.
POLICY_WITH_UNICODE = POLICY_HTML.replace(
    "nearby\nresults", "nearby results — including cafés and événements —"
)
POLICY_SHA = hashlib.sha256(POLICY_WITH_UNICODE.encode("utf-8")).hexdigest()


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
    """M8 persists through the Option A repositories, so revision 0003 is
    required. Checked by ancestry, not equality: the chain keeps growing and a
    head assertion would fail on the next migration."""
    if "audit_run" not in set(inspect(pg_engine).get_table_names()):
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
            f"({sorted(ancestry) or 'none'}). M8 needs the collection-event "
            "schema."
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
def package() -> str:
    return f"com.test.m8{os.urandom(4).hex()}"


@pytest.fixture
def policy_root(tmp_path) -> Path:
    path = tmp_path / "data" / "policies" / "raw" / "policy.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(POLICY_WITH_UNICODE, encoding="utf-8")
    return tmp_path


def seed(session: Session, package: str, *, declared: bool) -> int:
    """One application, one collection event, one queued audit."""
    application = Application(package_name=package, app_name="M8 Integration")
    session.add(application)
    session.flush()

    snapshot = DisclosureSnapshot(
        app_id=application.app_id,
        collected_at=datetime(2026, 11, 6, tzinfo=timezone.utc),
        source_url_listing=(
            f"https://play.google.com/store/apps/details?id={package}"
        ),
        source_url_policy="https://example.invalid/privacy",
        retrieval_mode="manual_import",
        policy_doc_path="data/policies/raw/policy.html",
        policy_doc_sha256=POLICY_SHA,
        status=SNAPSHOT_COMPLETE,
        declares_no_data_collected=False,
    )
    session.add(snapshot)
    session.flush()

    if declared:
        session.add(
            DeclaredPractice(
                snapshot_id=snapshot.snapshot_id,
                ds_category="Location",
                is_collected=True,
                is_shared=False,
            )
        )

    mapping = TaxonomyMappingVersion(
        version_label=f"fixture-map-{os.urandom(3).hex()}", is_active=False
    )
    session.add(mapping)
    session.flush()
    models = register_fixture_models(session, f"fixture-{os.urandom(3).hex()}")

    audit = AuditRun(
        app_id=application.app_id,
        snapshot_id=snapshot.snapshot_id,
        taxonomy_mapping_version_id=mapping.taxonomy_mapping_version_id,
        classification_model_id=models["classification"],
        span_model_id=models["span_extraction"],
        alignment_model_id=models["alignment"],
        status=STATUS_QUEUED,
        threshold_config={
            "classifier": 0.5,
            "alignment": 0.5,
            "provisional": True,
            "notes": "fixture run",
        },
    )
    session.add(audit)
    session.flush()
    return audit.audit_id


def pipeline(session: Session, policy_root: Path) -> AuditPipeline:
    return AuditPipeline(
        session,
        classifier=StubClassifier(),
        aligner=StubAligner(),
        mapper=stub_mapper(),
        repository_root=policy_root,
    )


# -- a complete run against real constraints --------------------------------


def test_a_complete_run_persists_every_stage_under_real_constraints(
    session, package, policy_root
):
    audit_id = seed(session, package, declared=False)
    outcome = pipeline(session, policy_root).run(audit_id)
    session.flush()

    assert outcome.uses_fixture_models is True
    audit = session.get(AuditRun, audit_id)
    assert audit.status == STATUS_COMPLETED

    segments = session.scalars(
        select(PolicySegment).where(
            PolicySegment.snapshot_id == audit.snapshot_id
        )
    ).all()
    assert segments

    practices = session.scalars(
        select(ExtractedPractice).where(
            ExtractedPractice.segment_id.in_([s.segment_id for s in segments])
        )
    ).all()
    assert practices

    judgements = session.scalars(
        select(AlignmentJudgementRow).where(
            AlignmentJudgementRow.audit_id == audit_id
        )
    ).all()
    assert judgements
    assert all(
        judgement.declared_practice_id is not None
        or judgement.extracted_practice_id is not None
        for judgement in judgements
    ), "PostgreSQL enforces ck_judgement_has_at_least_one_side"

    verdicts = session.scalars(
        select(Verdict).where(Verdict.audit_id == audit_id)
    ).all()
    assert len(verdicts) == 14, "ALG-8 gives every Data Safety category a verdict"


def test_the_threshold_config_returns_from_jsonb_as_a_dict(
    session, package, policy_root
):
    """The report reads the thresholds back out of this column. If jsonb came
    back as a string the report would show the run's configuration as text and
    `thresholds["classifier"]` would raise."""
    audit_id = seed(session, package, declared=True)
    pipeline(session, policy_root).run(audit_id)
    session.flush()
    session.expire_all()

    stored = session.get(AuditRun, audit_id).threshold_config
    assert isinstance(stored, dict)
    assert stored["classifier"] == 0.5
    assert stored["provisional"] is True
    assert stored["notes"] == "fixture run"


def test_evidence_offsets_and_unicode_quotes_survive_the_round_trip(
    session, package, policy_root
):
    audit_id = seed(session, package, declared=False)
    pipeline(session, policy_root).run(audit_id)
    session.flush()
    session.expire_all()

    location = session.scalars(
        select(Verdict).where(
            Verdict.audit_id == audit_id, Verdict.ds_category == "Location"
        )
    ).one()
    assert location.verdict_value == VERDICT_IN_POLICY_NOT_DECLARED

    records = session.scalars(
        select(EvidenceRecord).where(EvidenceRecord.verdict_id == location.verdict_id)
    ).all()
    assert records
    for record in records:
        segment = session.get(PolicySegment, record.segment_id)
        assert record.quoted_text == segment.segment_text
        assert record.char_start == segment.char_start
        assert record.char_end == segment.char_end

    quoted = " ".join(record.quoted_text for record in records)
    if "caf" in quoted:
        assert "cafés" in quoted, "non-ASCII text must not be mangled"


def test_the_report_endpoint_reads_a_postgresql_audit_back(
    pg_engine, session, package, policy_root
):
    """E5 over the real database, on the same uncommitted transaction, so the
    report is assembled from rows PostgreSQL itself validated."""
    audit_id = seed(session, package, declared=True)
    pipeline(session, policy_root).run(audit_id)
    session.flush()

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        response = client.get(f"/api/audits/{audit_id}/report")
        assert response.status_code == 200
        report = ReportOut.model_validate(response.json())

    assert report.package_name == package
    assert report.uses_fixture_models is True
    assert len(report.verdicts) == 14
    assert report.thresholds["provisional"] is True
    assert "not a legal compliance finding" in report.scope_note


# -- the claim, which only PostgreSQL can test ------------------------------


@pytest.fixture
def committed_queue(pg_engine, package, policy_root):
    """One **committed** queued audit, visible to two connections.

    Row locking cannot be observed across uncommitted transactions, so this
    fixture is the one place in this directory that commits. It deletes
    exactly the rows it inserted afterwards, by primary key, in the
    disposable `_test` database — no DDL, no TRUNCATE, nothing belonging to
    another test touched.
    """
    with Session(pg_engine) as setup:
        audit_id = seed(setup, package, declared=True)
        audit = setup.get(AuditRun, audit_id)
        ids = {
            "audit": audit_id,
            "app": audit.app_id,
            "snapshot": audit.snapshot_id,
            "mapping": audit.taxonomy_mapping_version_id,
            "models": [
                audit.classification_model_id,
                audit.span_model_id,
                audit.alignment_model_id,
            ],
        }
        setup.commit()

    try:
        yield ids
    finally:
        with Session(pg_engine) as cleanup:
            cleanup.execute(
                delete(AuditRun).where(AuditRun.audit_id == ids["audit"])
            )
            cleanup.execute(
                delete(DeclaredPractice).where(
                    DeclaredPractice.snapshot_id == ids["snapshot"]
                )
            )
            cleanup.execute(
                delete(DisclosureSnapshot).where(
                    DisclosureSnapshot.snapshot_id == ids["snapshot"]
                )
            )
            cleanup.execute(
                delete(Application).where(Application.app_id == ids["app"])
            )
            cleanup.execute(
                delete(TaxonomyMappingVersion).where(
                    TaxonomyMappingVersion.taxonomy_mapping_version_id
                    == ids["mapping"]
                )
            )
            cleanup.execute(
                delete(ModelVersion).where(
                    ModelVersion.model_version_id.in_(ids["models"])
                )
            )
            cleanup.commit()


def test_a_second_worker_skips_an_audit_the_first_has_locked(
    pg_engine, committed_queue
):
    """`FOR UPDATE SKIP LOCKED` in practice.

    Worker A claims without committing; the row is locked and still reads as
    `queued` to anyone else. Worker B must skip it and return None rather than
    claim the same audit, which would run one audit twice and break DD-2.
    SQLite ignores the clause, so this cannot be tested anywhere but here.
    """
    first = Session(pg_engine)
    second = Session(pg_engine)
    try:
        claimed = claim_next_audit(first)
        assert claimed is not None
        assert claimed.audit_id == committed_queue["audit"]
        assert claimed.status == STATUS_RUNNING

        assert claim_next_audit(second) is None, (
            "the second worker claimed a locked audit"
        )
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()


def test_the_queue_is_empty_again_after_the_claim_is_rolled_back(
    pg_engine, committed_queue
):
    """A crash before the claim commits must leave the audit claimable, not
    stranded."""
    with Session(pg_engine) as aborted:
        assert claim_next_audit(aborted) is not None
        aborted.rollback()

    with Session(pg_engine) as retry:
        try:
            recovered = claim_next_audit(retry)
            assert recovered is not None
            assert recovered.audit_id == committed_queue["audit"]
        finally:
            retry.rollback()
