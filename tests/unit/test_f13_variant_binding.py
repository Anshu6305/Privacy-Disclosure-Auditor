"""F-13 — model variant binding.

FR-13 requires an audit to run on either the baseline or the improved model
so the two can be compared on the same input. The rules F-13 adds are all
about not changing its mind: one variant for the whole audit, resolved
through the registry (F-34), recorded on `audit_run`, bound when the job is
claimed, never switched, and an unknown variant rejected before work begins.

Per DD-8 the variant is internal. These tests cover the maintainer's path
(a variant supplied) and the end-user path (omitted), and assert that the
two produce different, correct version sets.
"""

from __future__ import annotations

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
    REASON_MIXED_VARIANT,
    REASON_UNKNOWN_VARIANT,
    REASON_VARIANT_UNAVAILABLE,
    AuditRequested,
    AuditRequestRefused,
    AuditService,
)
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from analysis.models.variant import (
    MixedVariantError,
    UnknownVariantError,
    bind_variant,
    normalise_variant,
)
from analysis.vocabulary import (
    MODEL_TASKS,
    SNAPSHOT_COMPLETE,
    VARIANT_BASELINE,
    VARIANT_IMPROVED,
)

PACKAGE = "com.example.variant"


@pytest.fixture
def session():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def register(session, variant: str, *, skip_task: str | None = None, active=True):
    for task in MODEL_TASKS:
        if task == skip_task:
            continue
        session.add(
            ModelVersion(
                task=task,
                variant=variant,
                model_identifier=f"{variant}-{task}",
                version_label=f"{variant}-v1",
                checkpoint_path=f"ml/checkpoints/{variant}-{task}",
                is_active=active,
            )
        )
    session.flush()


@pytest.fixture
def ready(session):
    application = Application(package_name=PACKAGE, app_name="Variant App")
    session.add(application)
    session.flush()
    session.add(
        DisclosureSnapshot(
            app_id=application.app_id,
            source_url_listing="https://play.google.com/x",
            source_url_policy="https://example.invalid/p",
            retrieval_mode="manual_import",
            policy_doc_path="data/policies/raw/p.html",
            policy_doc_sha256="a" * 64,
            status=SNAPSHOT_COMPLETE,
            declares_no_data_collected=False,
        )
    )
    session.add(TaxonomyMappingVersion(version_label="map-v1", is_active=True))
    session.flush()
    return application


# -- validation, before any work -------------------------------------------


def test_an_unknown_variant_is_rejected_before_work_begins(session, ready):
    """F-13 requires this at the door. Refusing after the policy had been
    fetched and segmented would waste the work and leave a half-finished
    audit behind."""
    register(session, VARIANT_BASELINE)
    result = AuditService(session).request_audit(PACKAGE, variant="experimental")

    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_UNKNOWN_VARIANT
    assert "experimental" in result.detail
    assert session.scalars(select(AuditRun)).all() == [], "an audit was created"


def test_an_unknown_variant_is_rejected_even_before_the_application_is_looked_up(
    session,
):
    """Nothing is stored, so there is nothing to look up against."""
    result = AuditService(session).request_audit("com.nobody.holds", variant="bogus")
    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_UNKNOWN_VARIANT


@pytest.mark.parametrize("value", ["BASELINE", " improved ", "Improved"])
def test_a_variant_is_matched_case_and_space_insensitively(value):
    assert normalise_variant(value) in {VARIANT_BASELINE, VARIANT_IMPROVED}


@pytest.mark.parametrize("value", [None, "", "   "])
def test_an_absent_variant_means_the_active_set(value):
    assert normalise_variant(value) is None


def test_an_unknown_variant_raises_rather_than_defaulting():
    with pytest.raises(UnknownVariantError, match="unknown model variant"):
        normalise_variant("tiny")


# -- the end-user path: no variant -----------------------------------------


def test_a_request_without_a_variant_uses_the_active_set(session, ready):
    register(session, VARIANT_BASELINE)
    result = AuditService(session).request_audit(PACKAGE)

    assert isinstance(result, AuditRequested)
    audit = session.get(AuditRun, result.audit_id)
    for model_id in (
        audit.classification_model_id,
        audit.span_model_id,
        audit.alignment_model_id,
    ):
        assert session.get(ModelVersion, model_id).variant == VARIANT_BASELINE


def test_active_registrations_spanning_two_variants_are_refused(session, ready):
    """F-13 binds one variant for the whole audit. A classifier from one and
    an aligner from another is a mixture nobody chose and has no honest
    label, so there is nothing to bind."""
    register(session, VARIANT_BASELINE, skip_task="alignment")
    session.add(
        ModelVersion(
            task="alignment",
            variant=VARIANT_IMPROVED,
            model_identifier="improved-alignment",
            version_label="improved-v1",
            is_active=True,
        )
    )
    session.flush()

    result = AuditService(session).request_audit(PACKAGE)
    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_MIXED_VARIANT
    assert session.scalars(select(AuditRun)).all() == []


# -- the maintainer path: a variant supplied -------------------------------


def test_a_requested_variant_binds_that_version_set(session, ready):
    """Both variants registered; the request picks one and gets only it."""
    register(session, VARIANT_BASELINE)
    register(session, VARIANT_IMPROVED)

    result = AuditService(session).request_audit(PACKAGE, variant=VARIANT_IMPROVED)
    assert isinstance(result, AuditRequested)

    audit = session.get(AuditRun, result.audit_id)
    for model_id in (
        audit.classification_model_id,
        audit.span_model_id,
        audit.alignment_model_id,
    ):
        assert session.get(ModelVersion, model_id).variant == VARIANT_IMPROVED


def test_the_same_application_can_be_audited_on_each_variant(session, ready):
    """FR-13 itself: the two models compared on the same input."""
    register(session, VARIANT_BASELINE)
    register(session, VARIANT_IMPROVED)
    service = AuditService(session)

    first = service.request_audit(PACKAGE, variant=VARIANT_BASELINE)
    second = service.request_audit(PACKAGE, variant=VARIANT_IMPROVED)
    assert isinstance(first, AuditRequested)
    assert isinstance(second, AuditRequested)
    assert first.audit_id != second.audit_id
    assert first.snapshot_id == second.snapshot_id, "not the same input"
    assert first.classification_model_id != second.classification_model_id


def test_an_unavailable_variant_is_refused_with_no_fallback(session, ready):
    """The one that matters most.

    Falling back to the baseline would produce a report whose provenance
    says improved. A comparison built on that would be comparing a model
    against itself without anyone knowing.
    """
    register(session, VARIANT_BASELINE)

    result = AuditService(session).request_audit(PACKAGE, variant=VARIANT_IMPROVED)
    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_VARIANT_UNAVAILABLE
    assert "improved" in result.detail
    assert session.scalars(select(AuditRun)).all() == [], "an audit was created"


def test_a_variant_missing_for_one_task_only_is_still_refused(session, ready):
    """Partial availability is unavailability: F-13 binds all three or none."""
    register(session, VARIANT_BASELINE)
    register(session, VARIANT_IMPROVED, skip_task="alignment")

    result = AuditService(session).request_audit(PACKAGE, variant=VARIANT_IMPROVED)
    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_VARIANT_UNAVAILABLE
    assert "alignment" in result.detail


def test_an_inactive_registration_does_not_satisfy_a_variant(session, ready):
    register(session, VARIANT_BASELINE)
    register(session, VARIANT_IMPROVED, active=False)

    result = AuditService(session).request_audit(PACKAGE, variant=VARIANT_IMPROVED)
    assert isinstance(result, AuditRequestRefused)
    assert result.reason == REASON_VARIANT_UNAVAILABLE


# -- determinism ------------------------------------------------------------


def test_binding_is_deterministic_across_repeated_requests(session, ready):
    register(session, VARIANT_BASELINE)
    register(session, VARIANT_IMPROVED)
    service = AuditService(session)

    sets = set()
    for _ in range(4):
        result = service.request_audit(PACKAGE, variant=VARIANT_BASELINE)
        assert isinstance(result, AuditRequested)
        sets.add(
            (
                result.classification_model_id,
                result.span_model_id,
                result.alignment_model_id,
            )
        )
    assert len(sets) == 1, "the same request resolved to different models"


def test_bind_variant_requires_agreement_only_when_none_is_requested():
    class Row:
        def __init__(self, variant):
            self.variant = variant

    mixed = {"a": Row(VARIANT_BASELINE), "b": Row(VARIANT_IMPROVED)}
    assert bind_variant(mixed, VARIANT_IMPROVED) == VARIANT_IMPROVED
    with pytest.raises(MixedVariantError):
        bind_variant(mixed, None)


# -- claim-time binding: the worker uses what the audit recorded -----------


def test_the_factory_loads_exactly_the_versions_the_audit_recorded(
    session, ready, tmp_path, monkeypatch
):
    """F-13: bound when the job is claimed, never re-resolved.

    Before this, the worker loaded default checkpoints regardless of what
    the audit recorded, so an audit whose provenance said `improved` would
    have run on the baseline and nothing would have said so.
    """
    from app.services import model_registry

    register(session, VARIANT_BASELINE)
    register(session, VARIANT_IMPROVED)
    requested = AuditService(session).request_audit(PACKAGE, variant=VARIANT_IMPROVED)
    assert isinstance(requested, AuditRequested)
    session.flush()

    loaded: list[tuple[str, str, str]] = []

    def fake_load(model, repository_root="."):
        loaded.append((model.task, model.variant, model.checkpoint_path))
        return object()

    monkeypatch.setattr(model_registry, "load_for_model_version", fake_load)
    monkeypatch.setattr(model_registry, "load_mapper", lambda s: object())
    monkeypatch.setattr(
        model_registry, "AuditPipeline", lambda *a, **k: ("pipeline", k)
    )

    factory = model_registry.build_bound_pipeline_factory(tmp_path)
    factory(session, requested.audit_id)

    assert {variant for _task, variant, _path in loaded} == {VARIANT_IMPROVED}, (
        "the worker loaded a variant the audit did not record"
    )
    assert {task for task, _v, _p in loaded} == set(MODEL_TASKS)


def test_the_factory_refuses_a_version_row_with_no_checkpoint(session, ready, tmp_path):
    """A registry row that names no artefact cannot be loaded, and guessing
    a path would be the fallback F-13 forbids."""
    from app.services.model_registry import (
        ModelsUnavailableError,
        load_for_model_version,
    )

    model = ModelVersion(
        task="classification",
        variant=VARIANT_BASELINE,
        model_identifier="no-path",
        version_label="x",
        is_active=True,
    )
    session.add(model)
    session.flush()

    with pytest.raises(ModelsUnavailableError, match="records no"):
        load_for_model_version(model, tmp_path)


def test_the_improved_classifier_refuses_rather_than_using_the_baseline(
    session, tmp_path
):
    """The improved variant has no trained checkpoint. Substituting the
    baseline would make a comparison compare a model with itself."""
    from app.services.model_registry import (
        ModelsUnavailableError,
        load_for_model_version,
    )

    model = ModelVersion(
        task="classification",
        variant=VARIANT_IMPROVED,
        model_identifier="improved",
        version_label="improved-v1",
        checkpoint_path="ml/checkpoints/improved_classifier",
        is_active=True,
    )
    session.add(model)
    session.flush()

    with pytest.raises(ModelsUnavailableError) as raised:
        load_for_model_version(model, tmp_path)
    assert "has not been trained" in str(raised.value)
    assert "NOT substituted" in str(raised.value)
