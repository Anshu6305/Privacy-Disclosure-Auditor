"""E1 to E11 against a seeded SQLite database.

The FastAPI session dependency is overridden so these run without PostgreSQL.
The same endpoints are exercised against PostgreSQL in
`tests/integration/test_m8_api_postgresql.py`.

**Every model here is a controlled stub**, registered with a `fixture:`
identifier. The reports these produce declare that, and no test in this file
demonstrates real model inference.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.api.routes import audits as audit_routes  # noqa: F401
from app.db.models import (
    Application,
    AuditRun,
    Base,
    DeclaredPractice,
    DisclosureSnapshot,
    EvidenceRecord,
    PolicySegment,
    TaxonomyMappingVersion,
    Verdict,
)
from app.db.session import get_session
from app.main import create_app
from app.services.model_registry import register_fixture_models
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from analysis.vocabulary import (
    RECORD_ABSENCE,
    RECORD_EVIDENCE,
    SNAPSHOT_COMPLETE,
    VERDICT_CONSISTENT,
)

PACKAGE = "com.example.endpoint"


@pytest.fixture
def engine():
    # StaticPool keeps the single in-memory connection, which TestClient's
    # worker thread needs to see the same tables the fixture created.
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
    return engine


@pytest.fixture
def seeded(engine):
    with Session(engine) as session:
        application = Application(package_name=PACKAGE, app_name="Endpoint App",
                                  developer_name="Endpoint Labs")
        session.add(application)
        session.flush()

        snapshot = DisclosureSnapshot(
            app_id=application.app_id,
            collected_at=datetime(2026, 11, 6, tzinfo=timezone.utc),
            source_url_listing="https://play.google.com/store/apps/details?id=" + PACKAGE,
            source_url_policy="https://example.invalid/privacy",
            retrieval_mode="manual_import",
            policy_doc_path="data/policies/raw/a.html",
            policy_doc_sha256="a" * 64,
            status=SNAPSHOT_COMPLETE,
            declares_no_data_collected=False,
        )
        session.add(snapshot)
        session.flush()
        segment = PolicySegment(
            snapshot_id=snapshot.snapshot_id,
            segment_index=0,
            segment_text="We collect your location.",
            char_start=0,
            char_end=25,
        )
        session.add(segment)
        session.flush()
        session.add(
            DeclaredPractice(
                snapshot_id=snapshot.snapshot_id,
                ds_category="Location",
                is_collected=True,
                is_shared=False,
            )
        )
        mapping = TaxonomyMappingVersion(version_label="map-v1", is_active=True)
        session.add(mapping)
        session.flush()
        models = register_fixture_models(session, "fixture-v1")

        audit = AuditRun(
            app_id=application.app_id,
            snapshot_id=snapshot.snapshot_id,
            taxonomy_mapping_version_id=mapping.taxonomy_mapping_version_id,
            classification_model_id=models["classification"],
            span_model_id=models["span_extraction"],
            alignment_model_id=models["alignment"],
            status="completed",
            completed_at=datetime(2026, 11, 6, tzinfo=timezone.utc),
            threshold_config={"classifier": 0.5, "alignment": 0.5, "provisional": True},
        )
        session.add(audit)
        session.flush()

        verdict = Verdict(
            audit_id=audit.audit_id,
            ds_category="Location",
            verdict_value=VERDICT_CONSISTENT,
            declared=True,
            found_in_policy=True,
            abstention_involved=False,
        )
        session.add(verdict)
        session.flush()
        session.add_all(
            [
                EvidenceRecord(
                    verdict_id=verdict.verdict_id,
                    record_type=RECORD_EVIDENCE,
                    segment_id=segment.segment_id,
                    quoted_text="We collect your location.",
                    char_start=0,
                    char_end=25,
                    display_order=1,
                ),
                EvidenceRecord(
                    verdict_id=verdict.verdict_id,
                    record_type=RECORD_ABSENCE,
                    reason="The policy does not mention this category.",
                    display_order=2,
                ),
            ]
        )
        session.commit()
        return {"app_id": application.app_id, "audit_id": audit.audit_id,
                "snapshot_id": snapshot.snapshot_id}


@pytest.fixture
def client(engine, seeded):
    app = create_app()

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    with TestClient(app) as client:
        client.seeded = seeded
        yield client


# -- E1 ---------------------------------------------------------------------


def test_e1_search_returns_matches(client):
    response = client.get("/api/applications", params={"q": "endpoint"})
    assert response.status_code == 200
    assert response.json()[0]["package_name"] == PACKAGE


def test_e1_a_short_query_returns_empty_not_an_error(client):
    response = client.get("/api/applications", params={"q": "e"})
    assert response.status_code == 200
    assert response.json() == []


# -- E2 ---------------------------------------------------------------------


def test_e2_detail_includes_the_latest_collection_event(client):
    body = client.get(f"/api/applications/{PACKAGE}").json()
    assert body["app_name"] == "Endpoint App"
    assert body["latest_snapshot"]["status"] == SNAPSHOT_COMPLETE
    assert body["latest_snapshot"]["has_policy"] is True


def test_e2_an_unknown_application_explains_itself(client):
    response = client.get("/api/applications/com.not.collected")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["present_in_corpus"] is False
    assert detail["can_request_audit"] is False


# -- E3 ---------------------------------------------------------------------


def test_e3_queues_an_audit(client):
    response = client.post("/api/audits", json={"package_name": PACKAGE})
    assert response.status_code == 202
    assert response.json()["status"] == "queued"


def test_e3_refuses_an_unknown_application_with_404(client):
    response = client.post("/api/audits", json={"package_name": "com.nope"})
    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "unknown_application"


# -- E4 ---------------------------------------------------------------------


def test_e4_reports_status(client):
    audit_id = client.seeded["audit_id"]
    body = client.get(f"/api/audits/{audit_id}").json()
    assert body["status"] == "completed"
    assert body["package_name"] == PACKAGE


def test_e4_unknown_audit_is_404(client):
    assert client.get("/api/audits/999999").status_code == 404


# -- E5 ---------------------------------------------------------------------


def test_e5_report_carries_verdicts_thresholds_and_provenance(client):
    body = client.get(f"/api/audits/{client.seeded['audit_id']}/report").json()
    assert body["verdicts"][0]["verdict"] == VERDICT_CONSISTENT
    assert body["thresholds"]["provisional"] is True
    assert len(body["models"]) == 3


def test_e5_a_fixture_backed_report_says_so(client):
    """The distinction between a stub and real inference must survive into
    the report, or a demonstration looks like a result."""
    body = client.get(f"/api/audits/{client.seeded['audit_id']}/report").json()
    assert body["uses_fixture_models"] is True
    assert all(
        model["model_identifier"].startswith("fixture:") for model in body["models"]
    )


def test_e5_every_report_states_its_scope(client):
    body = client.get(f"/api/audits/{client.seeded['audit_id']}/report").json()
    assert "does not observe what the application actually does" in body["scope_note"]
    assert "not a legal compliance finding" in body["scope_note"]


def test_e5_an_incomplete_audit_has_no_report(client, engine):
    """A partial report would present an unfinished analysis as a finding."""
    with Session(engine) as session:
        audit = session.get(AuditRun, client.seeded["audit_id"])
        audit.status = "running"
        session.commit()
    response = client.get(f"/api/audits/{client.seeded['audit_id']}/report")
    assert response.status_code == 409


# -- E6 ---------------------------------------------------------------------


def test_e6_returns_the_record_types_distinctly(client):
    """An absence record carries a reason and no quote; they are not
    interchangeable."""
    records = client.get(
        f"/api/audits/{client.seeded['audit_id']}/evidence/Location"
    ).json()
    by_type = {record["record_type"]: record for record in records}
    assert by_type[RECORD_EVIDENCE]["quoted_text"] == "We collect your location."
    assert by_type[RECORD_ABSENCE]["quoted_text"] is None
    assert by_type[RECORD_ABSENCE]["reason"]


def test_e6_unknown_category_is_404(client):
    response = client.get(
        f"/api/audits/{client.seeded['audit_id']}/evidence/Nonexistent"
    )
    assert response.status_code == 404


# -- E7, E8 -----------------------------------------------------------------


def test_e7_history_counts_verdicts(client):
    entries = client.get(f"/api/applications/{PACKAGE}/audits").json()
    assert entries[0]["verdict_counts"] == {VERDICT_CONSISTENT: 1}


def test_e8_compares_two_audits(client, engine):
    first = client.seeded["audit_id"]
    with Session(engine) as session:
        original = session.get(AuditRun, first)
        second = AuditRun(
            app_id=original.app_id,
            snapshot_id=original.snapshot_id,
            taxonomy_mapping_version_id=original.taxonomy_mapping_version_id,
            classification_model_id=original.classification_model_id,
            span_model_id=original.span_model_id,
            alignment_model_id=original.alignment_model_id,
            status="completed",
            completed_at=datetime(2026, 11, 6, tzinfo=timezone.utc),
            threshold_config={},
        )
        session.add(second)
        session.flush()
        session.add(
            Verdict(
                audit_id=second.audit_id,
                ds_category="Location",
                verdict_value="Declared-not-in-policy",
                declared=True,
                found_in_policy=False,
                abstention_involved=False,
            )
        )
        session.commit()
        second_id = second.audit_id

    body = client.get(f"/api/audits/{first}/compare/{second_id}").json()
    assert body["changed_count"] == 1
    assert body["changes"][0]["earlier_verdict"] == VERDICT_CONSISTENT
    assert body["changes"][0]["later_verdict"] == "Declared-not-in-policy"


def test_e8_refuses_to_compare_two_applications(client, engine):
    with Session(engine) as session:
        other = Application(package_name="com.other.app", app_name="Other")
        session.add(other)
        session.flush()
        snapshot = DisclosureSnapshot(
            app_id=other.app_id,
            source_url_listing="https://play.google.com/x",
            source_url_policy="https://example.invalid/p",
            retrieval_mode="manual_import",
            policy_doc_path="data/policies/raw/b.html",
            policy_doc_sha256="b" * 64,
            status=SNAPSHOT_COMPLETE,
        )
        session.add(snapshot)
        session.flush()
        original = session.get(AuditRun, client.seeded["audit_id"])
        foreign = AuditRun(
            app_id=other.app_id,
            snapshot_id=snapshot.snapshot_id,
            taxonomy_mapping_version_id=original.taxonomy_mapping_version_id,
            classification_model_id=original.classification_model_id,
            span_model_id=original.span_model_id,
            alignment_model_id=original.alignment_model_id,
            status="completed",
            completed_at=datetime(2026, 11, 6, tzinfo=timezone.utc),
            threshold_config={},
        )
        session.add(foreign)
        session.commit()
        foreign_id = foreign.audit_id

    response = client.get(
        f"/api/audits/{client.seeded['audit_id']}/compare/{foreign_id}"
    )
    assert response.status_code == 400
    assert "different applications" in response.json()["detail"]


# -- E9, E10, E11 -----------------------------------------------------------


def test_e9_returns_both_source_urls_and_the_hash(client):
    body = client.get(f"/api/applications/{PACKAGE}/sources").json()
    assert body["source_url_policy"] == "https://example.invalid/privacy"
    assert body["policy_doc_sha256"] == "a" * 64


def test_e10_versions_flag_fixture_models(client):
    body = client.get("/api/versions").json()
    assert body["uses_fixture_models"] is True
    assert body["taxonomy_mapping_version"] == "map-v1"


def test_e11_reports_configuration_not_success(client):
    body = client.get("/api/acquisition/status").json()
    assert body["live_retrieval_configured"] is False
    assert body["corpus_application_count"] >= 1
    assert "not a successful fetch" in body["detail"]
