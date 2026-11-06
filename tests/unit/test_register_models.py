"""Production model registration.

The write path is exercised against SQLite with the same metadata; what
PostgreSQL adds is the unique constraint on (task, version_label), which the
idempotency test relies on and which SQLite enforces too.

No test here calls `register_fixture_models`. The point of this script is
that the production registry contains only real identifiers.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from app.db.models import Base, EvaluationMetric, EvaluationRun, ModelVersion
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from analysis.vocabulary import (
    MODEL_TASKS,
    MODEL_VARIANTS,
    TASK_ALIGNMENT,
    TASK_CLASSIFICATION,
    TASK_SPAN_EXTRACTION,
)
from scripts.register_models import (
    FIXTURE_PREFIX,
    Registration,
    metric_rows,
    register,
    registrations,
)


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


def by_task(task: str) -> Registration:
    return next(r for r in registrations() if r.task == task)


# -- what the table declares ------------------------------------------------


def test_all_three_approved_tasks_are_covered():
    assert {r.task for r in registrations()} == set(MODEL_TASKS)


def test_every_registration_uses_an_approved_variant():
    for registration in registrations():
        assert registration.variant in MODEL_VARIANTS


def test_no_registration_uses_a_fixture_identifier():
    """`fixture:` marks a controlled stub so a report declares itself. One
    in the production registry would make a stub-backed audit look real."""
    for registration in registrations():
        assert not registration.model_identifier.startswith(FIXTURE_PREFIX)


def test_the_alignment_entry_states_that_it_is_zero_shot_and_unevaluated():
    """F-18 is not fine-tuned and has no metric. The registry row is the only
    place a reader of a report will see that."""
    alignment = by_task(TASK_ALIGNMENT)
    notes = alignment.notes.upper()
    assert "ZERO-SHOT" in notes
    assert "NOT FINE-TUNED" in notes
    assert "NOT EVALUATED" in notes
    assert alignment.training_config["fine_tuned"] is False
    assert alignment.metrics_path is None
    assert metric_rows(alignment) == []


def test_the_span_extractor_entry_states_its_low_accuracy():
    """0.107 exact-match F1 must not be discoverable only by reading a
    separate report."""
    notes = by_task(TASK_SPAN_EXTRACTION).notes
    assert "LOW ACCURACY" in notes
    assert "0.1072" in notes


# -- metrics come from the real files ---------------------------------------


def test_classifier_metrics_match_the_measured_file():
    rows = {
        (row["metric_name"], row["class_label"]): row["metric_value"]
        for row in metric_rows(by_task(TASK_CLASSIFICATION))
    }
    assert rows[("macro_f1", None)] == 0.7489
    assert rows[("micro_f1", None)] == 0.769
    assert ("f1", "First Party Collection/Use") in rows


def test_span_extractor_metrics_keep_exact_and_overlapping_apart():
    """Reporting one as the other is the single most misleading thing this
    registry could do with these numbers."""
    rows = {row["metric_name"]: row["metric_value"] for row in metric_rows(
        by_task(TASK_SPAN_EXTRACTION)
    )}
    assert rows["exact_f1"] == pytest.approx(0.10721649, abs=1e-6)
    assert rows["overlapping_f1"] == pytest.approx(0.56577319, abs=1e-6)
    assert rows["exact_f1"] < rows["overlapping_f1"]


# -- writing ----------------------------------------------------------------


def test_registering_writes_the_model_its_run_and_its_metrics(session):
    registration = by_task(TASK_CLASSIFICATION)
    outcome, count = register(session, registration, activate=True)
    assert outcome == "registered"
    assert count == 36

    model = session.scalars(select(ModelVersion)).one()
    assert model.model_identifier == registration.model_identifier
    assert model.checkpoint_path == "ml/checkpoints/classifier-baseline-v1"
    assert model.is_active is True
    assert model.random_seed == 20261105

    run = session.scalars(select(EvaluationRun)).one()
    assert run.split_name == "test"
    assert run.item_count == 541
    assert len(session.scalars(select(EvaluationMetric)).all()) == 36


def test_an_unevaluated_model_gets_no_evaluation_run(session):
    """F-18 has no metrics. An empty run would imply one was performed."""
    outcome, count = register(session, by_task(TASK_ALIGNMENT), activate=True)
    assert outcome == "registered"
    assert count == 0
    assert session.scalars(select(EvaluationRun)).all() == []


def test_running_twice_changes_nothing_the_second_time(session):
    """An audit records the model version it used. Editing a version after
    the fact would silently change what earlier reports meant."""
    registration = by_task(TASK_SPAN_EXTRACTION)
    assert register(session, registration, activate=True)[0] == "registered"
    session.flush()

    outcome, count = register(session, registration, activate=True)
    assert outcome == "already registered"
    assert count == 0

    assert len(session.scalars(select(ModelVersion)).all()) == 1
    assert len(session.scalars(select(EvaluationRun)).all()) == 1


def test_activating_supersedes_the_previous_active_row_without_deleting_it(session):
    """Deactivation is a flag change. The old row and any audit citing it
    must survive."""
    first = by_task(TASK_CLASSIFICATION)
    register(session, first, activate=True)
    session.flush()

    second = replace(
        first,
        version_label="m5-baseline-v2",
        model_identifier="tfidf-logistic-regression/classifier-baseline-v2",
    )
    register(session, second, activate=True)
    session.flush()

    rows = session.scalars(
        select(ModelVersion).where(ModelVersion.task == TASK_CLASSIFICATION)
    ).all()
    assert len(rows) == 2, "the superseded row was deleted"
    active = [row for row in rows if row.is_active]
    assert [row.version_label for row in active] == ["m5-baseline-v2"]


def test_no_activate_leaves_the_task_without_an_active_model(session):
    register(session, by_task(TASK_ALIGNMENT), activate=False)
    session.flush()
    assert session.scalars(select(ModelVersion)).one().is_active is False


def test_a_fixture_identifier_is_refused_outright(session):
    """The guard is in the writer, not only in the table above, so a future
    caller passing its own Registration cannot slip one in."""
    poisoned = replace(
        by_task(TASK_ALIGNMENT), model_identifier="fixture:alignment"
    )
    with pytest.raises(SystemExit, match="fixture prefix"):
        register(session, poisoned, activate=True)


# -- refusal ----------------------------------------------------------------


def test_a_model_that_cannot_load_is_reported_and_not_registered(session):
    """The whole reason each loader is called first.

    Registering from configuration alone would let an audit cite a
    model_version row for weights that are not on disk.
    """
    from scripts.register_models import probe

    def explode():
        from app.services.model_registry import ModelsUnavailableError

        raise ModelsUnavailableError("no checkpoint at ml/checkpoints/absent")

    broken = replace(by_task(TASK_ALIGNMENT), loader=explode)
    loaded, detail = probe(broken)
    assert loaded is False
    assert "no checkpoint" in detail

    # The script skips it; nothing is written for a model that did not load.
    assert session.scalars(select(ModelVersion)).all() == []


def test_probe_reports_the_real_class_when_a_model_loads():
    from scripts.register_models import probe

    loaded, detail = probe(
        replace(by_task(TASK_ALIGNMENT), loader=lambda: object())
    )
    assert loaded is True
    assert detail == "object"
