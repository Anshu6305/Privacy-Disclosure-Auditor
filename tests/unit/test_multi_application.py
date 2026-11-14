"""The system is generic over Android applications; Spotify is the first pilot.

The approved scope is a multi-application auditor: any application whose Play
Data Safety declaration and privacy policy are supplied can be audited. One
real application has been collected so far, so this is the test that the
*capability* is generic rather than the corpus large.

Nothing here collects or invents an application's real disclosures. Two
controlled applications are used to show that identity, sources and audits
stay separate, and that the pipeline reads whatever the audit names.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.db.models import (
    Application,
    AuditRun,
    Base,
    DeclaredPractice,
    DisclosureSnapshot,
    ModelVersion,
    TaxonomyMappingVersion,
)
from app.db.repositories.application_repo import ApplicationRepository
from app.services.audit_service import (
    REASON_UNKNOWN_APPLICATION,
    AuditRequested,
    AuditRequestRefused,
    AuditService,
)
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from analysis.vocabulary import (
    SNAPSHOT_COMPLETE,
    TASK_ALIGNMENT,
    TASK_CLASSIFICATION,
    TASK_SPAN_EXTRACTION,
    VARIANT_BASELINE,
)

ALPHA = "com.example.alpha"
BETA = "com.example.beta"


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


def add_application(session: Session, package: str, name: str, category: str) -> int:
    """One application, its own snapshot, its own policy file and declaration."""
    application = Application(package_name=package, app_name=name)
    session.add(application)
    session.flush()

    snapshot = DisclosureSnapshot(
        app_id=application.app_id,
        collected_at=datetime(2026, 11, 15, tzinfo=timezone.utc),
        source_url_listing=f"https://play.google.com/store/apps/details?id={package}",
        source_url_policy=f"https://{package}.invalid/privacy",
        retrieval_mode="manual_import",
        policy_doc_path=f"data/corpus/raw/policies/{package}.html",
        policy_doc_sha256=package.ljust(64, "0")[:64].replace(".", "0"),
        status=SNAPSHOT_COMPLETE,
        declares_no_data_collected=False,
    )
    session.add(snapshot)
    session.flush()
    session.add(
        DeclaredPractice(
            snapshot_id=snapshot.snapshot_id,
            ds_category=category,
            is_collected=True,
            is_shared=False,
        )
    )
    session.flush()
    return application.app_id


def seed_registry(session: Session) -> None:
    session.add(TaxonomyMappingVersion(version_label="map-v1", is_active=True))
    for task in (TASK_CLASSIFICATION, TASK_SPAN_EXTRACTION, TASK_ALIGNMENT):
        session.add(
            ModelVersion(
                task=task,
                variant=VARIANT_BASELINE,
                model_identifier=f"real/{task}",
                version_label=f"{task}-v1",
                checkpoint_path=f"ml/checkpoints/{task}",
                is_active=True,
            )
        )
    session.flush()


@pytest.fixture
def two_applications(session):
    alpha = add_application(session, ALPHA, "Alpha Player", "Location")
    beta = add_application(session, BETA, "Beta Reader", "Personal info")
    seed_registry(session)
    return {ALPHA: alpha, BETA: beta}


# -- identity ---------------------------------------------------------------


def test_two_applications_coexist_with_their_own_sources(session, two_applications):
    applications = session.execute(select(Application)).scalars().all()

    assert {a.package_name for a in applications} == {ALPHA, BETA}
    snapshots = session.execute(select(DisclosureSnapshot)).scalars().all()
    assert len(snapshots) == 2
    assert len({s.app_id for s in snapshots}) == 2
    assert len({s.policy_doc_path for s in snapshots}) == 2, (
        "each application keeps its own policy document"
    )


def test_lookup_is_by_package_name_and_not_fixed_to_one_application(
    session, two_applications
):
    repository = ApplicationRepository(session)

    assert repository.get_by_package(ALPHA).package_name == ALPHA
    assert repository.get_by_package(BETA).package_name == BETA
    assert repository.get_by_package("com.example.absent") is None


def test_search_matches_any_application(session, two_applications):
    found = ApplicationRepository(session).search("beta")

    assert [row.package_name for row in found] == [BETA]


# -- audits stay with their own application ---------------------------------


def test_each_application_gets_an_audit_bound_to_its_own_snapshot(
    session, two_applications
):
    service = AuditService(session)

    first = service.request_audit(ALPHA)
    second = service.request_audit(BETA)
    assert isinstance(first, AuditRequested)
    assert isinstance(second, AuditRequested)
    assert first.audit_id != second.audit_id

    for result, package in ((first, ALPHA), (second, BETA)):
        audit = session.get(AuditRun, result.audit_id)
        application = session.get(Application, audit.app_id)
        snapshot = session.get(DisclosureSnapshot, audit.snapshot_id)

        assert application.package_name == package
        assert snapshot.app_id == application.app_id
        assert package in snapshot.policy_doc_path, (
            "the audit must read its own application's policy document"
        )


def test_an_application_that_was_never_collected_is_refused(session, two_applications):
    """No audit is invented for an application with no supplied sources."""
    result = AuditService(session).request_audit("com.example.never")

    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_UNKNOWN_APPLICATION


def test_no_production_module_names_a_specific_application():
    """The pilot's package name must not appear in a code path. Comments that
    explain why a rule exists are allowed and are what the pilot produced."""
    import ast

    from app.config import PROJECT_ROOT

    roots = [
        PROJECT_ROOT / "backend" / "app",
        PROJECT_ROOT / "analysis",
        PROJECT_ROOT / "acquisition",
    ]
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))

            # Docstrings are documentation, like comments: the pilot is named
            # in several to record which real audit exposed a rule. Only a
            # string the code actually evaluates would make the system
            # application-specific.
            documentation = {
                id(node.body[0].value)
                for node in ast.walk(tree)
                if isinstance(node, holders)
                and node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            }

            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and "spotify" in node.value.lower()
                    and id(node) not in documentation
                ):
                    offenders.append(f"{path.name}: {node.value[:60]!r}")

    assert not offenders, (
        "a specific application appears in a string literal, not just a comment: "
        + "; ".join(offenders)
    )
