"""The M8 audit pipeline, the queue claim and the worker loop.

Every model here is a **controlled stub** injected through the pipeline's
constructor, and every audit these tests run records `fixture:` model
identifiers. Nothing in this file demonstrates real inference, and the
assertions on `uses_fixture_models` exist to keep that distinction visible in
the output rather than only in this docstring.

The database is SQLite. These tests cover orchestration and refusal logic;
PostgreSQL persistence and the `FOR UPDATE SKIP LOCKED` claim are covered in
`tests/integration/test_m8_pipeline_postgresql.py`.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest
from app.db.models import AlignmentJudgement as AlignmentJudgementRow
from app.db.models import (
    Application,
    AuditRun,
    Base,
    DeclaredPractice,
    DisclosureSnapshot,
    EvidenceRecord,
    ExtractedPractice,
    ModelVersion,
    PolicySegment,
    TaxonomyMappingVersion,
    Verdict,
)
from app.services.audit_pipeline import (
    FIXTURE_MODEL_PREFIX,
    AuditFailedError,
    AuditPipeline,
    claim_next_audit,
)
from app.services.model_registry import register_fixture_models
from app.worker.worker import AuditWorker
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from analysis.mapping.taxonomy_mapper import MappingRule, TaxonomyMapper
from analysis.verdict.models import (
    AlignmentJudgement,
    PolicyPractice,
)
from analysis.vocabulary import (
    ALIGN_NO_MATCH,
    ALIGN_SUPPORTS,
    RECORD_EVIDENCE,
    SNAPSHOT_COMPLETE,
    SNAPSHOT_DECLARATION_ONLY,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    VERDICT_CONSISTENT,
    VERDICT_IN_POLICY_NOT_DECLARED,
)

PACKAGE = "com.example.pipeline"

#: Long enough to clear the provisional analysability floor of 50 tokens, and
#: deliberately mentioning one declared category and one undeclared one.
POLICY_HTML = """<html><body>
<h2>Information we collect</h2>
<p>We collect your precise location so that the application can show nearby
results, suggest routes and remember the places you have visited recently.</p>
<p>We also collect your contact list in order to suggest people you may
already know, and we keep that list for as long as your account is open.</p>
<h2>Sharing</h2>
<p>We do not sell any of the information described above to advertising
networks, data brokers or any other third party for their own purposes.</p>
</body></html>"""

UNANALYSABLE_HTML = "<html><body><p>Error 404.</p></body></html>"


# -- stubs ------------------------------------------------------------------


class StubClassifier:
    """Deterministic F-11 substitute.

    Emits a high-confidence practice for a segment mentioning location and a
    low-confidence one for a segment mentioning contacts, so the confidence
    gate has something to act on in both directions.
    """

    def __init__(self, high: float = 0.92, low: float = 0.20) -> None:
        self.high = high
        self.low = low
        self.calls: list[str] = []

    def predict_practices(self, segment, first_practice_id=1, minimum_score=0.0):
        self.calls.append(segment.text)
        lowered = segment.text.lower()
        if "location" in lowered:
            score = self.high
        elif "contact list" in lowered:
            score = self.low
        else:
            return []
        if score < minimum_score:
            return []
        return [
            PolicyPractice(
                practice_id=first_practice_id,
                segment=segment,
                opp115_category="First Party Collection/Use",
                confidence=score,
            )
        ]


class StubAligner:
    """Deterministic F-18 substitute.

    SUPPORTS when the candidate carries a mapped policy practice, NO_MATCH
    when it does not. The label is about the *policy* side only: whether the
    declaration also asserts the category is the verdict engine's decision
    (ALG-8), not the aligner's, so this stub does not look at it.

    `model_abstained` stays False, so any abstention seen downstream must have
    propagated from the upstream practice — which is what the gate test
    checks.
    """

    def __init__(self) -> None:
        self.seen = 0

    def judge(self, candidates):
        self.seen += len(candidates)
        judgements = []
        for candidate in candidates:
            mapped = candidate.mapped_practice
            judgements.append(
                AlignmentJudgement(
                    candidate=candidate,
                    label=ALIGN_SUPPORTS if mapped is not None else ALIGN_NO_MATCH,
                    confidence=mapped.practice.confidence if mapped else 0.5,
                )
            )
        return judgements


def stub_mapper() -> TaxonomyMapper:
    return TaxonomyMapper(
        [MappingRule(opp115_category="First Party Collection/Use",
                     ds_category="Location")],
        version_label="fixture-map-v1",
    )


# -- fixtures ---------------------------------------------------------------


@pytest.fixture
def engine():
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


def _write_policy(tmp_path, html: str) -> tuple[str, str]:
    directory = tmp_path / "data" / "policies" / "raw"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "policy.html"
    path.write_text(html, encoding="utf-8")
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    return "data/policies/raw/policy.html", digest


def _seed(session, tmp_path, *, html: str | None = POLICY_HTML,
          status: str = SNAPSHOT_COMPLETE, declared: bool = True) -> int:
    """Create an application, a collection event and one queued audit."""
    application = Application(package_name=PACKAGE, app_name="Pipeline App")
    session.add(application)
    session.flush()

    if html is None:
        path = digest = None
    else:
        path, digest = _write_policy(tmp_path, html)

    snapshot = DisclosureSnapshot(
        app_id=application.app_id,
        collected_at=datetime(2026, 11, 6, tzinfo=timezone.utc),
        source_url_listing=f"https://play.google.com/store/apps/details?id={PACKAGE}",
        source_url_policy="https://example.invalid/privacy",
        retrieval_mode="manual_import",
        policy_doc_path=path,
        policy_doc_sha256=digest,
        status=status,
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

    mapping = TaxonomyMappingVersion(version_label="fixture-map-v1", is_active=True)
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
        status=STATUS_QUEUED,
        threshold_config={"classifier": 0.5, "alignment": 0.5, "provisional": True},
    )
    session.add(audit)
    session.flush()
    session.commit()
    return audit.audit_id


def build_pipeline(session, tmp_path, classifier=None, aligner=None):
    return AuditPipeline(
        session,
        classifier=classifier or StubClassifier(),
        aligner=aligner or StubAligner(),
        mapper=stub_mapper(),
        repository_root=tmp_path,
    )


# -- a complete fixture-backed run ------------------------------------------


def test_a_complete_run_reaches_completed_and_persists_every_stage(engine, tmp_path):
    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)
        outcome = build_pipeline(session, tmp_path).run(audit_id)
        session.commit()

        assert outcome.segment_count > 0
        assert outcome.practice_count > 0
        assert outcome.verdict_count > 0

        audit = session.get(AuditRun, audit_id)
        assert audit.status == STATUS_COMPLETED
        assert audit.completed_at is not None
        assert session.scalars(select(PolicySegment)).all()
        assert session.scalars(select(ExtractedPractice)).all()
        assert session.scalars(select(AlignmentJudgementRow)).all()
        assert session.scalars(select(Verdict)).all()


def test_the_run_declares_that_it_used_fixture_models(engine, tmp_path):
    """A stub-backed run must be legible as one in its own record."""
    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)
        outcome = build_pipeline(session, tmp_path).run(audit_id)
        assert outcome.uses_fixture_models is True

        audit = session.get(AuditRun, audit_id)
        for model_id in (
            audit.classification_model_id,
            audit.span_model_id,
            audit.alignment_model_id,
        ):
            model = session.get(ModelVersion, model_id)
            assert model.model_identifier.startswith(FIXTURE_MODEL_PREFIX)
            assert "Not a trained model" in model.notes


def test_the_declared_category_is_consistent_when_the_policy_states_it(
    engine, tmp_path
):
    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)
        build_pipeline(session, tmp_path).run(audit_id)
        verdicts = {
            verdict.ds_category: verdict
            for verdict in session.scalars(
                select(Verdict).where(Verdict.audit_id == audit_id)
            )
        }
        assert verdicts["Location"].verdict_value == VERDICT_CONSISTENT
        assert verdicts["Location"].declared is True
        assert verdicts["Location"].found_in_policy is True


def test_a_consistent_verdict_carries_no_evidence_record(engine, tmp_path):
    """F-23: affirmative agreement needs no quote.

    Asserted here because the pipeline must not add records the approved
    design withholds — a report listing quotes under every agreement would
    imply the system had found a disagreement to support.
    """
    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)
        build_pipeline(session, tmp_path).run(audit_id)
        session.commit()

        location = session.scalars(
            select(Verdict).where(Verdict.ds_category == "Location")
        ).one()
        assert location.verdict_value == VERDICT_CONSISTENT
        assert not session.scalars(
            select(EvidenceRecord).where(EvidenceRecord.verdict_id == location.verdict_id)
        ).all()


def test_an_undeclared_category_found_in_the_policy_is_quoted_verbatim(
    engine, tmp_path
):
    """The quote must be the document's own characters at the stored offsets.

    The offsets index the cleaned text M4 fixed as canonical, so the check
    re-extracts the document and slices it. If this drifts, a report shows the
    reader text the policy does not contain — the failure the whole evidence
    design exists to prevent.
    """
    from acquisition.models import PolicyDocument as AcquisitionPolicyDocument
    from analysis.text.extractor import extract_policy_text

    with Session(engine) as session:
        # Location is deliberately *not* declared, so the support becomes
        # In-policy-not-declared and the verdict carries quotes.
        audit_id = _seed(session, tmp_path, declared=False)
        build_pipeline(session, tmp_path).run(audit_id)
        session.commit()

        location = session.scalars(
            select(Verdict).where(Verdict.ds_category == "Location")
        ).one()
        assert location.verdict_value == VERDICT_IN_POLICY_NOT_DECLARED

        records = session.scalars(
            select(EvidenceRecord).where(EvidenceRecord.record_type == RECORD_EVIDENCE)
        ).all()
        assert records, "In-policy-not-declared must quote the policy"

        cleaned = extract_policy_text(
            AcquisitionPolicyDocument(
                package_name=PACKAGE,
                source_url="https://example.invalid/privacy",
                content=POLICY_HTML,
                content_sha256=hashlib.sha256(POLICY_HTML.encode("utf-8")).hexdigest(),
                storage_path="data/policies/raw/policy.html",
                media_type="text/html",
            )
        ).text

        for record in records:
            segment = session.get(PolicySegment, record.segment_id)
            assert record.quoted_text == segment.segment_text
            assert record.char_start == segment.char_start
            assert record.char_end == segment.char_end
            assert cleaned[record.char_start:record.char_end] == record.quoted_text
            assert "location" in record.quoted_text.lower()


def test_a_low_confidence_practice_is_kept_and_flagged_not_discarded(engine, tmp_path):
    """The gate flags; it does not delete. Dropping the row would erase the
    uncertainty the verdict engine needs."""
    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)
        build_pipeline(session, tmp_path).run(audit_id)
        session.commit()

        practices = session.scalars(select(ExtractedPractice)).all()
        scores = sorted(practice.confidence for practice in practices)
        assert scores[0] < 0.5, "the low-confidence practice should be stored"
        assert any(practice.abstained for practice in practices)


# -- the two refusals --------------------------------------------------------


def test_an_unanalysable_policy_fails_the_audit_with_its_reason(engine, tmp_path):
    with Session(engine) as session:
        audit_id = _seed(session, tmp_path, html=UNANALYSABLE_HTML)
        with pytest.raises(AuditFailedError, match="not analysable"):
            build_pipeline(session, tmp_path).run(audit_id)
        session.commit()

        audit = session.get(AuditRun, audit_id)
        assert audit.status == STATUS_FAILED
        assert "not analysable" in audit.failure_reason
        assert not session.scalars(select(Verdict)).all(), (
            "a failed audit must leave no verdicts behind"
        )


def test_a_collection_event_without_a_policy_fails_rather_than_guessing(
    engine, tmp_path
):
    with Session(engine) as session:
        audit_id = _seed(
            session, tmp_path, html=None, status=SNAPSHOT_DECLARATION_ONLY
        )
        with pytest.raises(AuditFailedError, match="no policy document"):
            build_pipeline(session, tmp_path).run(audit_id)
        session.commit()
        assert session.get(AuditRun, audit_id).status == STATUS_FAILED


def test_a_pipeline_cannot_be_built_without_a_classifier_or_an_aligner(engine):
    """There is no default model. A pipeline without one could only invent
    predictions, so construction fails instead."""
    with Session(engine) as session:
        with pytest.raises(ValueError, match="classifier and an aligner"):
            AuditPipeline(session, classifier=None, aligner=StubAligner(),
                          mapper=stub_mapper())
        with pytest.raises(ValueError, match="classifier and an aligner"):
            AuditPipeline(session, classifier=StubClassifier(), aligner=None,
                          mapper=stub_mapper())


def test_an_unknown_audit_id_fails_loudly(engine):
    with Session(engine) as session:
        pipeline = AuditPipeline(session, classifier=StubClassifier(),
                                 aligner=StubAligner(), mapper=stub_mapper())
        with pytest.raises(AuditFailedError, match="no audit"):
            pipeline.run(999999)


# -- the queue claim ---------------------------------------------------------


def test_claim_takes_the_queued_audit_and_marks_it_running(engine, tmp_path):
    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)
        claimed = claim_next_audit(session)
        assert claimed.audit_id == audit_id
        assert claimed.status == STATUS_RUNNING
        assert claimed.claimed_at is not None


def test_claim_returns_nothing_while_another_audit_is_running(engine, tmp_path):
    """DD-2: one active audit at a time, because one model set is resident."""
    with Session(engine) as session:
        _seed(session, tmp_path)
        first = claim_next_audit(session)
        assert first is not None
        session.commit()

        second = AuditRun(
            app_id=first.app_id,
            snapshot_id=first.snapshot_id,
            taxonomy_mapping_version_id=first.taxonomy_mapping_version_id,
            classification_model_id=first.classification_model_id,
            span_model_id=first.span_model_id,
            alignment_model_id=first.alignment_model_id,
            status=STATUS_QUEUED,
            threshold_config={},
        )
        session.add(second)
        session.commit()

        assert claim_next_audit(session) is None


def test_claim_returns_nothing_on_an_empty_queue(engine):
    with Session(engine) as session:
        assert claim_next_audit(session) is None


# -- the worker loop ---------------------------------------------------------


def test_the_worker_runs_one_audit_and_commits_it(engine, tmp_path):
    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)

    def session_factory():
        return Session(engine)

    worker = AuditWorker(
        session_factory, lambda session, _audit_id: build_pipeline(session, tmp_path)
    )
    assert worker.run_once() is True
    assert worker.run_once() is False, "the queue is empty after one audit"
    assert worker.stats.completed == 1
    assert worker.stats.failed == 0

    with Session(engine) as session:
        assert session.get(AuditRun, audit_id).status == STATUS_COMPLETED


def test_the_worker_records_a_failed_audit_without_crashing(engine, tmp_path):
    with Session(engine) as session:
        _seed(session, tmp_path, html=UNANALYSABLE_HTML)

    worker = AuditWorker(
        lambda: Session(engine), lambda session, _audit_id: build_pipeline(session, tmp_path)
    )
    assert worker.run_once() is True
    assert worker.stats.failed == 1
    assert worker.stats.completed == 0

    with Session(engine) as session:
        audit = session.scalars(select(AuditRun)).one()
        assert audit.status == STATUS_FAILED
        assert audit.failure_reason


def test_a_stopped_worker_still_finishes_the_audit_in_hand(engine, tmp_path):
    """`stop()` sets a flag the loop reads between audits; it never abandons a
    claimed run, which would leave a row `running` forever."""
    with Session(engine) as session:
        _seed(session, tmp_path)

    worker = AuditWorker(
        lambda: Session(engine), lambda session, _audit_id: build_pipeline(session, tmp_path)
    )
    worker.stop()
    assert worker.run_once() is True
    assert worker.stats.completed == 1


def test_an_empty_mapping_table_fails_the_audit_instead_of_accusing(engine, tmp_path):
    """No authored F-15 rules must stop the run.

    With an empty rule table nothing the classifier finds can reach a Data
    Safety category, so every declared category would be reported
    Declared-not-in-policy. That report would look like a page of findings and
    would in fact be an artefact of the missing rules. This is the project's
    current real state, so the refusal is load-bearing, not hypothetical.
    """
    empty_mapper = TaxonomyMapper([], version_label="unauthored-v0")
    assert empty_mapper.rule_count == 0

    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)
        pipeline = AuditPipeline(
            session,
            classifier=StubClassifier(),
            aligner=StubAligner(),
            mapper=empty_mapper,
            repository_root=tmp_path,
        )
        with pytest.raises(AuditFailedError, match="holds no rules"):
            pipeline.run(audit_id)
        session.commit()

        audit = session.get(AuditRun, audit_id)
        assert audit.status == STATUS_FAILED
        assert "Author the mapping rules" in audit.failure_reason
        assert not session.scalars(select(Verdict)).all()


def test_the_rule_count_reflects_both_general_and_specific_rules(engine):
    """`rule_count` must not be a proxy for one index only, or the refusal
    above would pass vacuously for a version holding only specific rules."""
    mapper = TaxonomyMapper(
        [
            MappingRule(opp115_category="First Party Collection/Use",
                        ds_category="Location"),
            MappingRule(opp115_category="First Party Collection/Use",
                        ds_category="Personal info",
                        opp115_data_type="phone number"),
        ],
        version_label="two-rules",
    )
    assert mapper.rule_count == 2


# -- M10: F-15 rules keyed on a data type, and the F-12 signal that keys them


class StubSpanExtractor:
    """Deterministic F-12 substitute.

    Returns a data-type span for a segment mentioning location. Like the
    other stubs here it is injected, and an audit that uses it records
    fixture model identifiers.
    """

    def __init__(self, value: str = "Location", confidence: float = 0.9) -> None:
        self.value = value
        self.confidence = confidence
        self.calls = 0

    def extract(self, segment_text, document_text, segment_char_start):
        from analysis.models.span_extractor import ExtractedSpan

        self.calls += 1
        lowered = segment_text.lower()
        needle = "location"
        index = lowered.find(needle)
        if index < 0:
            return []
        start = segment_char_start + index
        return [
            ExtractedSpan(
                span_type="data_type",
                start=start,
                end=start + len(needle),
                text=document_text[start : start + len(needle)],
                confidence=self.confidence,
                abstained=self.confidence < 0.5,
                value=self.value,
            )
        ]


def authored_mapper():
    from analysis.mapping.rule_loader import load_mapping_file

    return load_mapping_file().mapper()


def test_a_data_type_only_table_with_no_extractor_refuses_the_audit(engine, tmp_path):
    """The second half of the F-15 guard, and the one that bites now.

    Every authored rule is keyed on a data type. With no F-12 extractor no
    practice can carry one, so the whole table is unreachable: the mapping
    would be empty for structural reasons and the report would blame the
    application for it. `rule_count` alone cannot catch this, because the
    table is complete and correct.
    """
    mapper = authored_mapper()
    assert mapper.rule_count > 0 and mapper.general_rule_count == 0

    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)
        pipeline = AuditPipeline(
            session,
            classifier=StubClassifier(),
            aligner=StubAligner(),
            mapper=mapper,
            repository_root=tmp_path,
            span_extractor=None,
        )
        with pytest.raises(AuditFailedError, match="no F-12 span extractor is loaded"):
            pipeline.run(audit_id)
        session.commit()

        assert session.get(AuditRun, audit_id).status == STATUS_FAILED
        assert not session.scalars(select(Verdict)).all()


def test_the_authored_rules_fire_once_f12_supplies_a_data_type(engine, tmp_path):
    """The chain F-11 -> F-14 -> F-12 -> F-15 -> F-18 -> ALG-8, end to end,
    with the real rule table and stubs standing in only for the models."""
    extractor = StubSpanExtractor()
    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)
        AuditPipeline(
            session,
            classifier=StubClassifier(),
            aligner=StubAligner(),
            mapper=authored_mapper(),
            repository_root=tmp_path,
            span_extractor=extractor,
        ).run(audit_id)
        session.commit()

        assert extractor.calls > 0, "the pipeline never consulted F-12"
        location = session.scalars(
            select(Verdict).where(Verdict.ds_category == "Location")
        ).one()
        assert location.found_in_policy is True
        assert location.verdict_value == VERDICT_CONSISTENT


def test_an_unmapped_data_type_produces_no_verdict_rather_than_a_guess(engine, tmp_path):
    """'Unspecified' is the corpus's own 'nothing to select' value.

    A practice carrying it must reach no Data Safety category at all. If it
    mapped anywhere, the commonest value in the attribute would manufacture
    a declaration thousands of times over.
    """
    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)
        AuditPipeline(
            session,
            classifier=StubClassifier(),
            aligner=StubAligner(),
            mapper=authored_mapper(),
            repository_root=tmp_path,
            span_extractor=StubSpanExtractor(value="Unspecified"),
        ).run(audit_id)
        session.commit()

        location = session.scalars(
            select(Verdict).where(Verdict.ds_category == "Location")
        ).one()
        assert location.found_in_policy is False


def test_a_span_that_does_not_slice_out_of_the_document_fails_the_audit(
    engine, tmp_path
):
    """A span whose offsets have drifted would quote text the policy does not
    contain. That is a defect in the extractor, not a property of the policy,
    so the audit stops rather than publishing the quote."""

    class BrokenExtractor:
        def extract(self, segment_text, document_text, segment_char_start):
            raise ValueError("span 10:20 does not slice back out of the document")

    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)
        pipeline = AuditPipeline(
            session,
            classifier=StubClassifier(),
            aligner=StubAligner(),
            mapper=authored_mapper(),
            repository_root=tmp_path,
            span_extractor=BrokenExtractor(),
        )
        with pytest.raises(AuditFailedError, match="unusable span"):
            pipeline.run(audit_id)
        session.commit()
        assert session.get(AuditRun, audit_id).status == STATUS_FAILED


# -- the worker must never leave an audit stuck in `running` ----------------


def test_an_unexpected_error_leaves_the_audit_failed_not_running(engine, tmp_path):
    """The defect that stranded the Spotify pilot audit.

    The claim is committed before the work begins, so a rollback alone
    leaves the row `running` for ever. `claim_next_audit` returns nothing
    while any audit is running, so one unexpected error did not fail one
    audit — it wedged the whole queue permanently.
    """

    class ExplodingClassifier:
        def predict_practices(self, segment, first_practice_id=1, minimum_score=0.0):
            raise RuntimeError("the checkpoint is corrupt")

    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)

    worker = AuditWorker(
        lambda: Session(engine),
        lambda session, _audit_id: AuditPipeline(
            session,
            classifier=ExplodingClassifier(),
            aligner=StubAligner(),
            mapper=stub_mapper(),
            repository_root=tmp_path,
        ),
    )
    with pytest.raises(RuntimeError, match="checkpoint is corrupt"):
        worker.run_once()

    with Session(engine) as session:
        audit = session.get(AuditRun, audit_id)
        assert audit.status == STATUS_FAILED, "the audit was left running"
        assert audit.completed_at is not None
        assert "RuntimeError" in audit.failure_reason
        assert "checkpoint is corrupt" in audit.failure_reason


def test_the_queue_is_not_wedged_by_an_unexpected_error(engine, tmp_path):
    """The consequence worth asserting separately: a later audit still runs."""

    class ExplodingClassifier:
        def predict_practices(self, segment, first_practice_id=1, minimum_score=0.0):
            raise RuntimeError("boom")

    with Session(engine) as session:
        first = _seed(session, tmp_path)

    broken = AuditWorker(
        lambda: Session(engine),
        lambda session, _audit_id: AuditPipeline(
            session,
            classifier=ExplodingClassifier(),
            aligner=StubAligner(),
            mapper=stub_mapper(),
            repository_root=tmp_path,
        ),
    )
    with pytest.raises(RuntimeError):
        broken.run_once()

    # A second audit for the same application, queued after the failure.
    with Session(engine) as session:
        original = session.get(AuditRun, first)
        second = AuditRun(
            app_id=original.app_id,
            snapshot_id=original.snapshot_id,
            taxonomy_mapping_version_id=original.taxonomy_mapping_version_id,
            classification_model_id=original.classification_model_id,
            span_model_id=original.span_model_id,
            alignment_model_id=original.alignment_model_id,
            status=STATUS_QUEUED,
            threshold_config=original.threshold_config,
        )
        session.add(second)
        session.commit()
        second_id = second.audit_id

    healthy = AuditWorker(
        lambda: Session(engine), lambda session, _audit_id: build_pipeline(session, tmp_path)
    )
    assert healthy.run_once() is True, "the queue was still blocked"
    with Session(engine) as session:
        assert session.get(AuditRun, second_id).status == STATUS_COMPLETED


def test_a_model_that_will_not_load_fails_the_audit_rather_than_stranding_it(
    engine, tmp_path
):
    """Building the pipeline loads the models, so it must be inside the try.

    It was outside, which meant an unavailable checkpoint stranded the audit
    exactly as a mid-run crash did.
    """

    def cannot_build(_session, _audit_id):
        from app.services.model_registry import ModelsUnavailableError

        raise ModelsUnavailableError("no F-12 checkpoint at ml/checkpoints/absent")

    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)

    worker = AuditWorker(lambda: Session(engine), cannot_build)
    with pytest.raises(Exception, match="no F-12 checkpoint"):
        worker.run_once()

    with Session(engine) as session:
        audit = session.get(AuditRun, audit_id)
        assert audit.status == STATUS_FAILED
        assert "no F-12 checkpoint" in audit.failure_reason


def test_marking_failed_does_not_overwrite_a_completed_audit(engine, tmp_path):
    """Defensive: the bookkeeping write must never rewrite a terminal row."""
    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)

    worker = AuditWorker(
        lambda: Session(engine), lambda session, _audit_id: build_pipeline(session, tmp_path)
    )
    assert worker.run_once() is True

    worker._mark_failed(audit_id, RuntimeError("late and wrong"))
    with Session(engine) as session:
        audit = session.get(AuditRun, audit_id)
        assert audit.status == STATUS_COMPLETED
        assert audit.failure_reason is None


def test_releasing_a_stuck_audit_only_touches_running_rows(engine, tmp_path):
    """The one-off for rows stranded before the worker fix.

    It must not disturb a queued audit waiting its turn, nor rewrite a
    completed one.
    """
    from scripts.release_stuck_audits import release

    with Session(engine) as session:
        audit_id = _seed(session, tmp_path)
        stuck = session.get(AuditRun, audit_id)
        stuck.status = STATUS_RUNNING
        stuck.claimed_at = datetime(2026, 11, 6, tzinfo=timezone.utc)

        queued = AuditRun(
            app_id=stuck.app_id,
            snapshot_id=stuck.snapshot_id,
            taxonomy_mapping_version_id=stuck.taxonomy_mapping_version_id,
            classification_model_id=stuck.classification_model_id,
            span_model_id=stuck.span_model_id,
            alignment_model_id=stuck.alignment_model_id,
            status=STATUS_QUEUED,
            threshold_config={},
        )
        done = AuditRun(
            app_id=stuck.app_id,
            snapshot_id=stuck.snapshot_id,
            taxonomy_mapping_version_id=stuck.taxonomy_mapping_version_id,
            classification_model_id=stuck.classification_model_id,
            span_model_id=stuck.span_model_id,
            alignment_model_id=stuck.alignment_model_id,
            status=STATUS_COMPLETED,
            completed_at=datetime(2026, 11, 6, tzinfo=timezone.utc),
            threshold_config={},
        )
        session.add_all([queued, done])
        session.commit()
        queued_id, done_id = queued.audit_id, done.audit_id

    with Session(engine) as session:
        assert release(session) == [audit_id]
        session.commit()

    with Session(engine) as session:
        assert session.get(AuditRun, audit_id).status == STATUS_FAILED
        assert "queue blocked" in session.get(AuditRun, audit_id).failure_reason
        assert session.get(AuditRun, queued_id).status == STATUS_QUEUED
        assert session.get(AuditRun, done_id).status == STATUS_COMPLETED
        assert session.get(AuditRun, done_id).failure_reason is None


def test_releasing_unblocks_the_queue(engine, tmp_path):
    from scripts.release_stuck_audits import release

    with Session(engine) as session:
        _seed(session, tmp_path)
        claimed = claim_next_audit(session)
        session.commit()
        assert claimed is not None
        assert claim_next_audit(session) is None, "a running audit blocks the queue"

        release(session)
        session.commit()
        # Nothing left queued here, but the blocker is gone: a new audit can
        # now be claimed rather than being refused by the running row.
        assert session.get(AuditRun, claimed.audit_id).status == STATUS_FAILED
