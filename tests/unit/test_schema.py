"""Schema constraint tests.

Every test here tries to write something the design forbids and asserts the
database refuses it. A constraint that is declared but not exercised is not a
guarantee, so each one gets an attempt.

These run on in-memory SQLite with foreign keys enabled. The CHECK, UNIQUE and
foreign-key constraints under test are the same objects PostgreSQL will build
from the same metadata.
"""

from __future__ import annotations

import pytest
from app.db.models import (
    ALL_TABLES,
    AlignmentJudgement,
    Application,
    AuditRun,
    Base,
    DeclaredPractice,
    DisclosureSnapshot,
    EvaluationMetric,
    EvaluationRun,
    EvidenceRecord,
    ExtractedPractice,
    ExtractedSpan,
    GoldAnnotation,
    ModelVersion,
    PolicySegment,
    TaxonomyMappingEntry,
    TaxonomyMappingVersion,
    Verdict,
)
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from analysis.vocabulary import (
    ALIGNMENT_LABELS,
    GOLD_LABELS,
    RECORD_TYPES,
    VERDICT_UNDETERMINED,
    VERDICTS,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")

    # SQLite ignores foreign keys unless asked. Without this the FK tests
    # would pass vacuously, which is worse than not having them.
    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def seed(session: Session) -> dict:
    """A minimal valid graph: app, two snapshots, mapping, three models, audit."""
    app = Application(package_name="com.example.app", app_name="Example App")
    session.add(app)
    session.flush()

    ds = DisclosureSnapshot(
        app_id=app.app_id,
        source_type="data_safety",
        source_url="https://play.google.com/store/apps/details?id=com.example.app",
        retrieval_method="scraper",
        content_sha256="a" * 64,
    )
    policy = DisclosureSnapshot(
        app_id=app.app_id,
        source_type="privacy_policy",
        source_url="https://example.com/privacy",
        retrieval_method="http_get",
        content_sha256="b" * 64,
        storage_path="data/policies/raw/bb.html",
    )
    mapping = TaxonomyMappingVersion(version_label="v1", is_active=True)
    models = [
        ModelVersion(
            task=task,
            variant="baseline",
            model_identifier=f"stub-{task}",
            version_label="v1",
        )
        for task in ("classification", "span_extraction", "alignment")
    ]
    session.add_all([ds, policy, mapping, *models])
    session.flush()

    segment = PolicySegment(
        snapshot_id=policy.snapshot_id,
        segment_index=0,
        segment_text="We collect your email address to send you updates.",
        char_start=0,
        char_end=50,
    )
    declared = DeclaredPractice(
        snapshot_id=ds.snapshot_id,
        ds_category="Personal info",
        ds_data_type="Email address",
        is_collected=True,
    )
    session.add_all([segment, declared])
    session.flush()

    audit = AuditRun(
        app_id=app.app_id,
        ds_snapshot_id=ds.snapshot_id,
        policy_snapshot_id=policy.snapshot_id,
        taxonomy_mapping_version_id=mapping.taxonomy_mapping_version_id,
        classification_model_id=models[0].model_version_id,
        span_model_id=models[1].model_version_id,
        alignment_model_id=models[2].model_version_id,
        status="queued",
        threshold_config={"classifier": 0.5, "span": 0.5, "alignment": 0.5},
    )
    session.add(audit)
    session.flush()

    return {
        "app": app,
        "ds": ds,
        "policy": policy,
        "mapping": mapping,
        "models": models,
        "segment": segment,
        "declared": declared,
        "audit": audit,
    }


def rejects(session: Session, obj) -> None:
    """Assert the database refuses this write."""
    session.add(obj)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_exactly_sixteen_tables():
    """The approved design has sixteen tables. Adding a seventeenth is a
    design change, not an implementation detail."""
    assert len(Base.metadata.tables) == 16
    assert len(ALL_TABLES) == 16


def test_audit_run_has_seven_not_null_foreign_keys(session: Session):
    """Reproducibility depends on every input being recorded."""
    table = Base.metadata.tables["audit_run"]
    fk_columns = {fk.parent.name for fk in table.foreign_keys}
    assert len(fk_columns) == 7
    for name in fk_columns:
        assert not table.columns[name].nullable, f"{name} must be NOT NULL"


def test_policy_documents_are_not_stored_in_the_database(session: Session):
    """The snapshot table holds a path and a hash, not the document body."""
    columns = set(Base.metadata.tables["disclosure_snapshot"].columns.keys())
    assert "storage_path" in columns
    assert "content_sha256" in columns
    for forbidden in ("content", "body", "html", "document_text", "raw_text"):
        assert forbidden not in columns


def test_abstention_is_a_column_on_every_stage(session: Session):
    """Abstention must survive each hand-off, so each stage stores it."""
    for table_name in ("extracted_practice", "extracted_span", "alignment_judgement"):
        assert "abstained" in Base.metadata.tables[table_name].columns
    assert "abstention_involved" in Base.metadata.tables["verdict"].columns


def test_case_insensitive_search_indexes_exist():
    """ALG-11 needs functional indexes on lower(); a plain B-tree cannot serve
    the search in F-01."""
    index_names = {index.name for index in Base.metadata.tables["application"].indexes}
    assert "ix_application_lower_name" in index_names
    assert "ix_application_lower_package" in index_names


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------


def test_verdict_accepts_all_five_approved_values(session: Session, seed):
    for offset, value in enumerate(VERDICTS):
        session.add(
            Verdict(
                audit_id=seed["audit"].audit_id,
                ds_category=f"Category {offset}",
                verdict_value=value,
                declared=True,
                found_in_policy=False,
            )
        )
    session.flush()
    assert session.query(Verdict).count() == 5


def test_verdict_rejects_an_invented_value(session: Session, seed):
    rejects(
        session,
        Verdict(
            audit_id=seed["audit"].audit_id,
            ds_category="Location",
            verdict_value="Probably Fine",
            declared=True,
            found_in_policy=True,
        ),
    )


def test_one_verdict_per_category_per_audit(session: Session, seed):
    session.add(
        Verdict(
            audit_id=seed["audit"].audit_id,
            ds_category="Location",
            verdict_value="Consistent",
            declared=True,
            found_in_policy=True,
        )
    )
    session.flush()

    rejects(
        session,
        Verdict(
            audit_id=seed["audit"].audit_id,
            ds_category="Location",
            verdict_value="Contradictory",
            declared=True,
            found_in_policy=True,
        ),
    )


# ---------------------------------------------------------------------------
# Gold annotations — the four-label rule
# ---------------------------------------------------------------------------


def test_gold_annotation_accepts_the_four_annotation_labels(session: Session, seed):
    for offset, label in enumerate(GOLD_LABELS):
        session.add(
            GoldAnnotation(
                app_id=seed["app"].app_id,
                ds_category=f"Category {offset}",
                label=label,
                annotator_code="R1",
            )
        )
    session.flush()
    assert session.query(GoldAnnotation).count() == 4


def test_gold_annotation_rejects_undetermined(session: Session, seed):
    """Undetermined is a system abstention. A human cannot annotate it, and
    allowing it would make the evaluation set unfalsifiable."""
    assert VERDICT_UNDETERMINED not in GOLD_LABELS
    rejects(
        session,
        GoldAnnotation(
            app_id=seed["app"].app_id,
            ds_category="Location",
            label=VERDICT_UNDETERMINED,
            annotator_code="R1",
        ),
    )


def test_one_annotation_per_annotator_per_category(session: Session, seed):
    session.add(
        GoldAnnotation(
            app_id=seed["app"].app_id,
            ds_category="Location",
            label="Consistent",
            annotator_code="R1",
        )
    )
    session.flush()

    rejects(
        session,
        GoldAnnotation(
            app_id=seed["app"].app_id,
            ds_category="Location",
            label="Contradictory",
            annotator_code="R1",
        ),
    )


def test_two_annotators_may_disagree_on_the_same_category(session: Session, seed):
    """Disagreement must be recordable; it is the input to adjudication."""
    session.add_all(
        [
            GoldAnnotation(
                app_id=seed["app"].app_id,
                ds_category="Location",
                label="Consistent",
                annotator_code="R1",
            ),
            GoldAnnotation(
                app_id=seed["app"].app_id,
                ds_category="Location",
                label="Contradictory",
                annotator_code="R2",
            ),
        ]
    )
    session.flush()
    assert session.query(GoldAnnotation).count() == 2


# ---------------------------------------------------------------------------
# Evidence records
# ---------------------------------------------------------------------------


@pytest.fixture
def verdict_row(session: Session, seed) -> Verdict:
    verdict = Verdict(
        audit_id=seed["audit"].audit_id,
        ds_category="Personal info",
        verdict_value="Contradictory",
        declared=True,
        found_in_policy=True,
    )
    session.add(verdict)
    session.flush()
    return verdict


def test_evidence_record_requires_a_real_quote_with_offsets(
    session: Session, seed, verdict_row
):
    """An evidence record without quoted text and offsets would be a claim
    with nothing behind it."""
    rejects(
        session,
        EvidenceRecord(
            verdict_id=verdict_row.verdict_id,
            record_type="evidence",
            reason="the policy says so",
        ),
    )


def test_evidence_record_rejects_an_empty_quote(session: Session, seed, verdict_row):
    rejects(
        session,
        EvidenceRecord(
            verdict_id=verdict_row.verdict_id,
            record_type="evidence",
            segment_id=seed["segment"].segment_id,
            quoted_text="",
            char_start=0,
            char_end=10,
        ),
    )


def test_evidence_record_rejects_reversed_offsets(session: Session, seed, verdict_row):
    rejects(
        session,
        EvidenceRecord(
            verdict_id=verdict_row.verdict_id,
            record_type="evidence",
            segment_id=seed["segment"].segment_id,
            quoted_text="We collect your email address",
            char_start=29,
            char_end=3,
        ),
    )


def test_valid_evidence_record_is_accepted(session: Session, seed, verdict_row):
    session.add(
        EvidenceRecord(
            verdict_id=verdict_row.verdict_id,
            record_type="evidence",
            segment_id=seed["segment"].segment_id,
            quoted_text="We collect your email address",
            char_start=0,
            char_end=29,
        )
    )
    session.flush()
    assert session.query(EvidenceRecord).count() == 1


def test_absence_record_may_not_carry_a_quote(session: Session, seed, verdict_row):
    """Declared-not-in-policy is an absence. There is nothing to quote, and a
    quote attached to it would misrepresent the finding."""
    rejects(
        session,
        EvidenceRecord(
            verdict_id=verdict_row.verdict_id,
            record_type="absence",
            quoted_text="no mention of location anywhere in the policy",
            reason="no matching statement found",
        ),
    )


def test_absence_record_requires_a_reason(session: Session, seed, verdict_row):
    rejects(
        session,
        EvidenceRecord(verdict_id=verdict_row.verdict_id, record_type="absence"),
    )


def test_valid_absence_record_is_accepted(session: Session, seed, verdict_row):
    session.add(
        EvidenceRecord(
            verdict_id=verdict_row.verdict_id,
            record_type="absence",
            reason="No policy statement mapped to this category.",
        )
    )
    session.flush()
    assert session.query(EvidenceRecord).count() == 1


def test_inconclusive_record_requires_a_reason(session: Session, seed, verdict_row):
    rejects(
        session,
        EvidenceRecord(verdict_id=verdict_row.verdict_id, record_type="inconclusive"),
    )


def test_record_type_is_restricted_to_three_values(session: Session, seed, verdict_row):
    assert len(RECORD_TYPES) == 3
    rejects(
        session,
        EvidenceRecord(
            verdict_id=verdict_row.verdict_id,
            record_type="probably",
            reason="x",
        ),
    )


def test_consistent_verdict_needs_no_record(session: Session, seed):
    """F-23: a Consistent verdict carries no evidence record. Nothing in the
    schema may require one."""
    verdict = Verdict(
        audit_id=seed["audit"].audit_id,
        ds_category="Calendar",
        verdict_value="Consistent",
        declared=False,
        found_in_policy=False,
    )
    session.add(verdict)
    session.flush()
    assert verdict.records == []


# ---------------------------------------------------------------------------
# Alignment judgements
# ---------------------------------------------------------------------------


def test_judgement_requires_at_least_one_side(session: Session, seed):
    """A pair with neither a declaration nor a policy practice is a judgement
    about nothing."""
    rejects(
        session,
        AlignmentJudgement(
            audit_id=seed["audit"].audit_id,
            ds_category="Location",
            label="NO_MATCH",
            confidence=0.9,
            threshold_applied=0.5,
            model_version_id=seed["models"][2].model_version_id,
        ),
    )


def test_judgement_accepts_a_declaration_with_no_policy_side(session: Session, seed):
    """This is exactly the Declared-not-in-policy case and must be storable."""
    session.add(
        AlignmentJudgement(
            audit_id=seed["audit"].audit_id,
            ds_category="Personal info",
            declared_practice_id=seed["declared"].declared_practice_id,
            label="NO_MATCH",
            confidence=0.88,
            threshold_applied=0.5,
            model_version_id=seed["models"][2].model_version_id,
        )
    )
    session.flush()
    assert session.query(AlignmentJudgement).count() == 1


def test_judgement_label_is_restricted_to_three_values(session: Session, seed):
    assert len(ALIGNMENT_LABELS) == 3
    rejects(
        session,
        AlignmentJudgement(
            audit_id=seed["audit"].audit_id,
            ds_category="Location",
            declared_practice_id=seed["declared"].declared_practice_id,
            label="MAYBE",
            confidence=0.5,
            threshold_applied=0.5,
            model_version_id=seed["models"][2].model_version_id,
        ),
    )


@pytest.mark.parametrize("confidence", [-0.1, 1.5])
def test_confidence_must_be_a_probability(session: Session, seed, confidence):
    rejects(
        session,
        AlignmentJudgement(
            audit_id=seed["audit"].audit_id,
            ds_category="Location",
            declared_practice_id=seed["declared"].declared_practice_id,
            label="SUPPORTS",
            confidence=confidence,
            threshold_applied=0.5,
            model_version_id=seed["models"][2].model_version_id,
        ),
    )


# ---------------------------------------------------------------------------
# Audit run and job queue
# ---------------------------------------------------------------------------


def test_audit_status_is_restricted(session: Session, seed):
    seed["audit"].status = "nearly done"
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_failed_audit_must_record_why(session: Session, seed):
    """A failure with no reason gives the user nothing and hides the fault."""
    seed["audit"].status = "failed"
    seed["audit"].failure_reason = None
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_completed_audit_must_have_a_completion_time(session: Session, seed):
    seed["audit"].status = "completed"
    seed["audit"].completed_at = None
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_audit_cannot_compare_a_snapshot_with_itself(session: Session, seed):
    rejects(
        session,
        AuditRun(
            app_id=seed["app"].app_id,
            ds_snapshot_id=seed["ds"].snapshot_id,
            policy_snapshot_id=seed["ds"].snapshot_id,
            taxonomy_mapping_version_id=seed["mapping"].taxonomy_mapping_version_id,
            classification_model_id=seed["models"][0].model_version_id,
            span_model_id=seed["models"][1].model_version_id,
            alignment_model_id=seed["models"][2].model_version_id,
            threshold_config={},
        ),
    )


def test_audit_requires_an_existing_application(session: Session, seed):
    """Foreign keys are enforced; this fails if the PRAGMA is ever dropped."""
    rejects(
        session,
        AuditRun(
            app_id=999_999,
            ds_snapshot_id=seed["ds"].snapshot_id,
            policy_snapshot_id=seed["policy"].snapshot_id,
            taxonomy_mapping_version_id=seed["mapping"].taxonomy_mapping_version_id,
            classification_model_id=seed["models"][0].model_version_id,
            span_model_id=seed["models"][1].model_version_id,
            alignment_model_id=seed["models"][2].model_version_id,
            threshold_config={},
        ),
    )


def test_threshold_config_is_required(session: Session, seed):
    """A report is uninterpretable without the thresholds that produced it."""
    rejects(
        session,
        AuditRun(
            app_id=seed["app"].app_id,
            ds_snapshot_id=seed["ds"].snapshot_id,
            policy_snapshot_id=seed["policy"].snapshot_id,
            taxonomy_mapping_version_id=seed["mapping"].taxonomy_mapping_version_id,
            classification_model_id=seed["models"][0].model_version_id,
            span_model_id=seed["models"][1].model_version_id,
            alignment_model_id=seed["models"][2].model_version_id,
            threshold_config=None,
        ),
    )


# ---------------------------------------------------------------------------
# Applications, snapshots, segments, spans
# ---------------------------------------------------------------------------


def test_package_name_is_unique(session: Session, seed):
    rejects(session, Application(package_name="com.example.app", app_name="Clone"))


def test_snapshot_source_type_is_restricted(session: Session, seed):
    rejects(
        session,
        DisclosureSnapshot(
            app_id=seed["app"].app_id,
            source_type="app_store_listing",
            source_url="https://example.com",
            retrieval_method="http_get",
            content_sha256="c" * 64,
        ),
    )


def test_snapshot_hash_must_be_a_full_sha256(session: Session, seed):
    """A truncated hash cannot identify a document."""
    rejects(
        session,
        DisclosureSnapshot(
            app_id=seed["app"].app_id,
            source_type="privacy_policy",
            source_url="https://example.com",
            retrieval_method="http_get",
            content_sha256="deadbeef",
        ),
    )


def test_segment_index_is_unique_within_a_snapshot(session: Session, seed):
    rejects(
        session,
        PolicySegment(
            snapshot_id=seed["policy"].snapshot_id,
            segment_index=0,
            segment_text="duplicate index",
            char_start=100,
            char_end=200,
        ),
    )


def test_segment_offsets_must_be_ordered(session: Session, seed):
    rejects(
        session,
        PolicySegment(
            snapshot_id=seed["policy"].snapshot_id,
            segment_index=7,
            segment_text="bad offsets",
            char_start=90,
            char_end=20,
        ),
    )


def test_span_offsets_must_be_ordered(session: Session, seed):
    practice = ExtractedPractice(
        segment_id=seed["segment"].segment_id,
        model_version_id=seed["models"][0].model_version_id,
        opp115_category="First Party Collection/Use",
        confidence=0.91,
        threshold_applied=0.5,
    )
    session.add(practice)
    session.flush()

    rejects(
        session,
        ExtractedSpan(
            extracted_practice_id=practice.extracted_practice_id,
            span_type="data_type",
            span_text="email address",
            char_start=30,
            char_end=10,
            confidence=0.8,
        ),
    )


def test_span_type_is_restricted(session: Session, seed):
    practice = ExtractedPractice(
        segment_id=seed["segment"].segment_id,
        model_version_id=seed["models"][0].model_version_id,
        opp115_category="First Party Collection/Use",
        confidence=0.91,
        threshold_applied=0.5,
    )
    session.add(practice)
    session.flush()

    rejects(
        session,
        ExtractedSpan(
            extracted_practice_id=practice.extracted_practice_id,
            span_type="retention_period",
            span_text="30 days",
            char_start=0,
            char_end=7,
            confidence=0.8,
        ),
    )


def test_abstained_practice_is_stored_not_discarded(session: Session, seed):
    """A low-confidence prediction is kept and flagged. Dropping it would let
    the pipeline mistake uncertainty for a confident absence."""
    practice = ExtractedPractice(
        segment_id=seed["segment"].segment_id,
        model_version_id=seed["models"][0].model_version_id,
        opp115_category="Data Retention",
        confidence=0.31,
        abstained=True,
        threshold_applied=0.5,
    )
    session.add(practice)
    session.flush()

    stored = session.query(ExtractedPractice).one()
    assert stored.abstained is True
    assert stored.confidence == pytest.approx(0.31)


# ---------------------------------------------------------------------------
# Models, taxonomy, evaluation
# ---------------------------------------------------------------------------


def test_model_task_and_variant_are_restricted(session: Session, seed):
    rejects(
        session,
        ModelVersion(
            task="summarisation",
            variant="baseline",
            model_identifier="x",
            version_label="v9",
        ),
    )


def test_model_version_label_is_unique_per_task(session: Session, seed):
    rejects(
        session,
        ModelVersion(
            task="classification",
            variant="improved",
            model_identifier="other",
            version_label="v1",
        ),
    )


def test_taxonomy_rule_is_unique_within_a_version(session: Session, seed):
    entry = TaxonomyMappingEntry(
        taxonomy_mapping_version_id=seed["mapping"].taxonomy_mapping_version_id,
        opp115_category="First Party Collection/Use",
        opp115_data_type="Contact",
        ds_category="Personal info",
    )
    session.add(entry)
    session.flush()

    rejects(
        session,
        TaxonomyMappingEntry(
            taxonomy_mapping_version_id=seed["mapping"].taxonomy_mapping_version_id,
            opp115_category="First Party Collection/Use",
            opp115_data_type="Contact",
            ds_category="Personal info",
        ),
    )


def test_abstention_count_cannot_exceed_item_count(session: Session, seed):
    rejects(
        session,
        EvaluationRun(
            model_version_id=seed["models"][0].model_version_id,
            split_name="test",
            item_count=10,
            abstention_count=11,
        ),
    )


def test_metric_must_declare_how_abstentions_were_handled(session: Session, seed):
    """The same F1 means different things with abstentions excluded versus
    counted as errors. Both are required, so each number says which it is."""
    run = EvaluationRun(
        model_version_id=seed["models"][0].model_version_id,
        split_name="test",
        item_count=100,
        abstention_count=12,
    )
    session.add(run)
    session.flush()

    rejects(
        session,
        EvaluationMetric(
            evaluation_run_id=run.evaluation_run_id,
            metric_name="macro_f1",
            metric_value=0.71,
            abstention_handling="whichever",
        ),
    )


def test_both_abstention_handlings_coexist_for_one_metric(session: Session, seed):
    run = EvaluationRun(
        model_version_id=seed["models"][0].model_version_id,
        split_name="test",
        item_count=100,
        abstention_count=12,
    )
    session.add(run)
    session.flush()

    session.add_all(
        [
            EvaluationMetric(
                evaluation_run_id=run.evaluation_run_id,
                metric_name="macro_f1",
                metric_value=0.71,
                abstention_handling="excluded",
            ),
            EvaluationMetric(
                evaluation_run_id=run.evaluation_run_id,
                metric_name="macro_f1",
                metric_value=0.63,
                abstention_handling="counted_as_error",
            ),
        ]
    )
    session.flush()
    assert session.query(EvaluationMetric).count() == 2


def test_cascade_delete_removes_dependent_rows(session: Session, seed):
    """Deleting an audit must not leave orphaned verdicts behind."""
    verdict = Verdict(
        audit_id=seed["audit"].audit_id,
        ds_category="Location",
        verdict_value="Consistent",
        declared=True,
        found_in_policy=True,
    )
    session.add(verdict)
    session.flush()

    session.delete(seed["audit"])
    session.flush()
    assert session.query(Verdict).count() == 0


def test_every_table_has_a_primary_key(session: Session):
    engine = session.get_bind()
    inspector = inspect(engine)
    for table in Base.metadata.tables:
        pk = inspector.get_pk_constraint(table)
        assert pk["constrained_columns"], f"{table} has no primary key"
