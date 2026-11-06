"""The audit pipeline: one `audit_run` from queued to completed.

This is the component the project has never had — the one that connects
acquisition, text processing, the models, the mapping and the verdict engine
into a single run and persists the result.

Order, each step named by its approved function identifier::

    F-04/F-05  load the collection event's declaration and policy document
    F-08       extract cleaned text          F-09  segment with offsets
    F-10       analysability check           F-11  classify practices
    F-14       confidence gate               F-15  taxonomy mapping
    F-16       normalise the declaration     F-17  build candidates
    F-18       semantic alignment            F-19  ALG-8 verdicts
    F-20/21/22 evidence, absence, inconclusive records

**Two refusals are built in, and both exist so a report never claims more
than the data supports.**

*An unanalysable policy stops the run.* F-10 decides; if a policy is too short
or too thin to segment, the audit fails with that reason rather than
producing verdicts drawn from an error page.

*A missing model stops the run.* The classifier and the aligner are injected.
There is no default, no fallback and no stub inside this module: an audit
without a model would have to invent predictions, and that is the one thing
the project must never do. `AuditPipeline` cannot be constructed without both.

**Fixtures are allowed but never disguised.** A deterministic stub may be
injected for testing, and the `model_version` rows recorded against the audit
carry its identifier. `report.uses_fixture_models` reads those identifiers
back, so a fixture-backed report says so in its own provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from app.db.models import (
    AlignmentJudgement as AlignmentJudgementRow,
)
from app.db.models import (
    AuditRun,
    DeclaredPractice,
    DisclosureSnapshot,
    EvidenceRecord,
    ExtractedPractice,
    ModelVersion,
    PolicySegment,
    Verdict,
)
from app.db.repositories.snapshot_repo import SnapshotRepository
from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.confidence.gate import apply_threshold_to_all
from analysis.mapping.candidate_builder import build_candidates
from analysis.mapping.declaration_normaliser import normalise_declaration
from analysis.mapping.taxonomy_mapper import TaxonomyMapper
from analysis.text.models import AnalysabilityThresholds
from analysis.text.pipeline import process_policy_document
from analysis.verdict.models import (
    AlignmentCandidate,
    AlignmentJudgement,
    PolicyPractice,
    PolicySegmentRef,
)
from analysis.vocabulary import (
    RECORD_ABSENCE,
    RECORD_EVIDENCE,
    RECORD_INCONCLUSIVE,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
)

#: Marks a model_version row as a controlled stub rather than a trained model.
#: `model_identifier` is free text in the approved schema, so this needs no
#: migration, and it is visible in the report's provenance.
FIXTURE_MODEL_PREFIX = "fixture:"


class PracticeClassifier(Protocol):
    """F-11. Satisfied by the M5 baseline and by the M6 improved variant."""

    def predict_practices(
        self,
        segment: PolicySegmentRef,
        first_practice_id: int = 1,
        minimum_score: float = 0.0,
    ) -> list[PolicyPractice]:
        ...


class Aligner(Protocol):
    """F-18."""

    def judge(self, candidates: list[AlignmentCandidate]) -> list[AlignmentJudgement]:
        ...


class AuditFailedError(RuntimeError):
    """The run cannot produce an honest report. Carries the stored reason."""


@dataclass(frozen=True)
class AuditOutcome:
    audit_id: int
    verdict_count: int
    evidence_count: int
    judgement_count: int
    segment_count: int
    practice_count: int
    uses_fixture_models: bool


class AuditPipeline:
    """Runs one audit. Constructed per run, never shared between runs."""

    def __init__(
        self,
        session: Session,
        classifier: PracticeClassifier,
        aligner: Aligner,
        mapper: TaxonomyMapper,
        repository_root: Path | str = ".",
    ) -> None:
        if classifier is None or aligner is None:
            raise ValueError(
                "an audit needs a classifier and an aligner. There is no "
                "fallback: a run without a model would have to invent "
                "predictions."
            )
        self._session = session
        self._classifier = classifier
        self._aligner = aligner
        self._mapper = mapper
        self._snapshots = SnapshotRepository(session, policy_root=repository_root)

    # -- the run ----------------------------------------------------------

    def run(self, audit_id: int) -> AuditOutcome:
        audit = self._session.get(AuditRun, audit_id)
        if audit is None:
            raise AuditFailedError(f"no audit {audit_id}")

        try:
            outcome = self._execute(audit)
        except AuditFailedError as failure:
            audit.status = STATUS_FAILED
            audit.failure_reason = str(failure)
            audit.completed_at = datetime.now(timezone.utc)
            raise

        audit.status = STATUS_COMPLETED
        audit.completed_at = datetime.now(timezone.utc)
        return outcome

    def _execute(self, audit: AuditRun) -> AuditOutcome:
        snapshot = self._session.get(DisclosureSnapshot, audit.snapshot_id)
        if snapshot is None:
            raise AuditFailedError("the audit references a collection event that is gone")

        # F-05 -------------------------------------------------------------
        document = self._snapshots.load_policy_document(snapshot.snapshot_id)
        if document is None:
            raise AuditFailedError(
                f"the collection event has status {snapshot.status!r} and holds "
                "no policy document, so there is nothing to compare the "
                "declaration against."
            )

        # The run's own recorded configuration, read once. F-10 refuses to
        # invent analysability thresholds, so they come from here or the audit
        # fails saying so.
        thresholds = audit.threshold_config or {}
        classifier_threshold = float(thresholds.get("classifier", 0.5))
        alignment_threshold = float(thresholds.get("alignment", 0.5))
        analysability, allow_provisional = self._analysability_thresholds(thresholds)

        # F-08, F-09, F-10 --------------------------------------------------
        from acquisition.models import PolicyDocument as AcquisitionPolicyDocument

        processed = process_policy_document(
            AcquisitionPolicyDocument(
                package_name=snapshot.application.package_name,
                source_url=document.source_url,
                content=document.content,
                content_sha256=document.content_sha256,
                storage_path=document.storage_path,
                media_type="text/html",
            ),
            thresholds=analysability,
            allow_provisional=allow_provisional,
        )
        if not processed.analysability.analysable:
            raise AuditFailedError(
                "the policy is not analysable: "
                f"{processed.analysability.reason}. Verdicts drawn from it "
                "would describe an error page rather than a disclosure."
            )

        segment_rows = self._persist_segments(snapshot.snapshot_id, processed)

        # F-11 and F-14 ------------------------------------------------------
        practices: list[PolicyPractice] = []
        practice_id = 1
        for segment, _row in segment_rows:
            found = self._classifier.predict_practices(
                segment, first_practice_id=practice_id, minimum_score=0.01
            )
            practices.extend(found)
            practice_id += len(found)

        gated = apply_threshold_to_all(practices, classifier_threshold)

        # Persist the *gated* practices, not the classifier's raw output. The
        # stored `abstained` flag has to be the one the verdict engine acted
        # on; writing the pre-gate value would leave the database claiming a
        # practice was trusted while the report treated it as uncertain.
        rows_by_segment = {ref.segment_id: row for ref, row in segment_rows}
        practice_rows = self._persist_practices(
            gated, rows_by_segment, audit.classification_model_id,
            classifier_threshold,
        )

        # F-15 ---------------------------------------------------------------
        # Refusal three. With no authored rules, nothing the classifier found
        # can ever reach a Data Safety category, so every declared category
        # would come out Declared-not-in-policy — a page of findings produced
        # by a missing rule table rather than by the application's
        # disclosures. Failing here is the difference between "not yet
        # implemented" and a false accusation.
        if self._mapper.rule_count == 0:
            raise AuditFailedError(
                f"taxonomy mapping version {self._mapper.version_label!r} "
                "holds no rules (F-15). Without them no policy practice can "
                "reach a Data Safety category, and every declared category "
                "would be reported as missing from the policy. Author the "
                "mapping rules before running an audit."
            )

        mapped = self._mapper.map_all(gated)

        # F-16 and F-17 ------------------------------------------------------
        declaration = self._load_declaration_state(snapshot.snapshot_id)
        candidates_by_category = build_candidates(declaration, mapped)

        # F-18 ---------------------------------------------------------------
        flat: list[AlignmentCandidate] = []
        for candidates in candidates_by_category.values():
            flat.extend(candidates)
        judgements = self._aligner.judge(flat) if flat else []

        by_category: dict[str, list[AlignmentJudgement]] = {}
        for judgement in judgements:
            by_category.setdefault(judgement.ds_category, []).append(judgement)
        self._persist_judgements(
            audit, judgements, segment_rows, practice_rows, alignment_threshold
        )

        # F-19 to F-22 --------------------------------------------------------
        from analysis.verdict.verdict_engine import assign_verdicts

        verdicts = assign_verdicts(declaration, by_category)
        evidence_count = self._persist_verdicts(audit, verdicts, segment_rows)

        return AuditOutcome(
            audit_id=audit.audit_id,
            verdict_count=len(verdicts),
            evidence_count=evidence_count,
            judgement_count=len(judgements),
            segment_count=len(segment_rows),
            practice_count=len(practices),
            uses_fixture_models=self._uses_fixture_models(audit),
        )

    @staticmethod
    def _analysability_thresholds(
        thresholds: dict,
    ) -> tuple[AnalysabilityThresholds | None, bool]:
        """Resolve F-10's minimums from the audit's recorded configuration.

        `validate_analysability` refuses to pick numbers nobody chose, and
        this pipeline does not pick them either. Three cases:

        * both ``min_segments`` and ``min_tokens`` present — use them;
        * ``provisional`` true — accept the documented provisional values,
          which the audit row then records as the configuration it ran under;
        * neither — fail the audit, because the alternative is a report whose
          acceptance threshold is unknown.
        """
        min_segments = thresholds.get("min_segments")
        min_tokens = thresholds.get("min_tokens")
        if min_segments is not None and min_tokens is not None:
            return (
                AnalysabilityThresholds(
                    min_segments=int(min_segments), min_tokens=int(min_tokens)
                ),
                False,
            )
        if min_segments is not None or min_tokens is not None:
            raise AuditFailedError(
                "the audit's threshold_config sets only one of min_segments "
                "and min_tokens. F-10 compares both, so a half-configured "
                "pair would leave the other minimum unstated."
            )
        if thresholds.get("provisional"):
            return None, True
        raise AuditFailedError(
            "the audit's threshold_config names no analysability minimums. "
            "Set min_segments and min_tokens, or set provisional true to "
            "accept the documented provisional values. There is no default: "
            "a report must state the threshold it was accepted under."
        )

    # -- persistence -------------------------------------------------------

    def _persist_segments(
        self, snapshot_id: int, processed
    ) -> list[tuple[PolicySegmentRef, PolicySegment]]:
        """Store F-09's segments and return them paired with their rows.

        Offsets index the cleaned text, which is the canonical coordinate base
        M4 fixed. Storing anything else here would make every later quote
        point at the wrong characters.
        """
        existing = self._session.execute(
            select(PolicySegment).where(PolicySegment.snapshot_id == snapshot_id)
        ).scalars().all()
        if existing:
            # A re-audit of the same collection event reuses its segments: the
            # document has not changed, and new rows would duplicate evidence
            # offsets against one document.
            return [
                (
                    PolicySegmentRef(
                        segment_id=row.segment_id,
                        text=row.segment_text,
                        char_start=row.char_start,
                        char_end=row.char_end,
                    ),
                    row,
                )
                for row in sorted(existing, key=lambda r: r.segment_index)
            ]

        pairs: list[tuple[PolicySegmentRef, PolicySegment]] = []
        for segment in processed.segments:
            row = PolicySegment(
                snapshot_id=snapshot_id,
                segment_index=segment.sequence_number,
                segment_text=segment.text,
                char_start=segment.char_start,
                char_end=segment.char_end,
                heading=getattr(segment, "heading", None),
            )
            self._session.add(row)
            pairs.append((None, row))  # type: ignore[arg-type]
        self._session.flush()

        return [
            (
                PolicySegmentRef(
                    segment_id=row.segment_id,
                    text=row.segment_text,
                    char_start=row.char_start,
                    char_end=row.char_end,
                ),
                row,
            )
            for _placeholder, row in pairs
        ]

    def _persist_practices(
        self,
        practices: list[PolicyPractice],
        rows_by_segment: dict[int, PolicySegment],
        model_version_id: int,
        threshold: float,
    ) -> dict[int, ExtractedPractice]:
        """Store the gated practices and return them keyed by practice id.

        The returned mapping is what lets an `alignment_judgement` row name
        the policy side it judged. Without it the row would satisfy neither
        half of `ck_judgement_has_at_least_one_side` whenever a category is
        found in the policy but not declared.
        """
        stored: dict[int, ExtractedPractice] = {}
        for practice in practices:
            segment_row = rows_by_segment[practice.segment.segment_id]
            row = ExtractedPractice(
                segment_id=segment_row.segment_id,
                model_version_id=model_version_id,
                opp115_category=practice.opp115_category,
                confidence=practice.confidence,
                abstained=practice.abstained,
                threshold_applied=threshold,
            )
            self._session.add(row)
            stored[practice.practice_id] = row
        self._session.flush()
        return stored

    def _load_declaration_state(self, snapshot_id: int) -> dict:
        """F-16 over the stored declaration.

        A collection event whose Data Safety section was never read yields an
        empty state, not a state saying nothing is declared. The difference
        reaches ALG-8 through `declares_no_data_collected`, which F-02 has
        already required to be present before queueing the audit.
        """
        rows = self._session.execute(
            select(DeclaredPractice).where(DeclaredPractice.snapshot_id == snapshot_id)
        ).scalars().all()
        from analysis.verdict.models import DeclaredItem

        return normalise_declaration(
            [
                DeclaredItem(
                    declared_practice_id=row.declared_practice_id,
                    ds_category=row.ds_category,
                    data_type=row.ds_data_type,
                    is_collected=row.is_collected,
                    is_shared=row.is_shared,
                )
                for row in rows
            ]
        )

    def _persist_judgements(
        self,
        audit: AuditRun,
        judgements: list[AlignmentJudgement],
        segment_rows: list[tuple[PolicySegmentRef, PolicySegment]],
        practice_rows: dict[int, ExtractedPractice],
        threshold: float,
    ) -> None:
        by_segment_id = {ref.segment_id: row for ref, row in segment_rows}
        for judgement in judgements:
            segment = judgement.candidate.segment
            declared = judgement.candidate.declared_item
            mapped = judgement.candidate.mapped_practice
            practice_row = (
                practice_rows.get(mapped.practice.practice_id)
                if mapped is not None
                else None
            )
            row = AlignmentJudgementRow(
                audit_id=audit.audit_id,
                ds_category=judgement.ds_category,
                declared_practice_id=(
                    declared.declared_practice_id if declared is not None else None
                ),
                extracted_practice_id=(
                    practice_row.extracted_practice_id
                    if practice_row is not None
                    else None
                ),
                segment_id=(
                    by_segment_id[segment.segment_id].segment_id
                    if segment is not None and segment.segment_id in by_segment_id
                    else None
                ),
                label=judgement.label,
                confidence=judgement.confidence,
                # The structural rule: abstention is the property, which ORs
                # the model's own uncertainty with the candidate's.
                abstained=judgement.abstained,
                threshold_applied=threshold,
                model_version_id=audit.alignment_model_id,
            )
            self._session.add(row)
        self._session.flush()

    def _persist_verdicts(
        self,
        audit: AuditRun,
        verdicts,
        segment_rows: list[tuple[PolicySegmentRef, PolicySegment]],
    ) -> int:
        by_segment_id = {ref.segment_id for ref, _row in segment_rows}
        written = 0
        for verdict in verdicts:
            row = Verdict(
                audit_id=audit.audit_id,
                ds_category=verdict.ds_category,
                verdict_value=verdict.verdict,
                confidence=verdict.confidence,
                declared=verdict.declared,
                found_in_policy=verdict.found_in_policy,
                abstention_involved=verdict.abstention_involved,
            )
            self._session.add(row)
            self._session.flush()

            for order, record in enumerate(verdict.records, start=1):
                segment_id = record.segment_id
                self._session.add(
                    EvidenceRecord(
                        verdict_id=row.verdict_id,
                        record_type=record.record_type,
                        segment_id=segment_id if segment_id in by_segment_id else None,
                        quoted_text=(
                            record.quoted_text
                            if record.record_type == RECORD_EVIDENCE
                            else None
                        ),
                        char_start=record.char_start,
                        char_end=record.char_end,
                        reason=(
                            record.reason
                            if record.record_type in (RECORD_ABSENCE, RECORD_INCONCLUSIVE)
                            else None
                        ),
                        display_order=order,
                    )
                )
                written += 1
        self._session.flush()
        return written

    # -- provenance ---------------------------------------------------------

    def _uses_fixture_models(self, audit: AuditRun) -> bool:
        identifiers = self._session.execute(
            select(ModelVersion.model_identifier).where(
                ModelVersion.model_version_id.in_(
                    [
                        audit.classification_model_id,
                        audit.span_model_id,
                        audit.alignment_model_id,
                    ]
                )
            )
        ).scalars().all()
        return any(
            identifier.startswith(FIXTURE_MODEL_PREFIX) for identifier in identifiers
        )


def claim_next_audit(session: Session) -> AuditRun | None:
    """F-32: take the oldest queued audit, if nothing else is running.

    **One active audit at a time**, per approved design decision DD-2: the
    memory plan assumes one model set is resident. The row is locked with
    ``FOR UPDATE SKIP LOCKED`` on PostgreSQL so two workers cannot claim the
    same audit; on SQLite the clause is ignored and the single-worker
    assumption holds anyway.
    """
    running = session.execute(
        select(AuditRun).where(AuditRun.status == STATUS_RUNNING).limit(1)
    ).scalar_one_or_none()
    if running is not None:
        return None

    statement = (
        select(AuditRun)
        .where(AuditRun.status == "queued")
        .order_by(AuditRun.requested_at, AuditRun.audit_id)
        .limit(1)
    )
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)

    audit = session.execute(statement).scalar_one_or_none()
    if audit is None:
        return None

    audit.status = STATUS_RUNNING
    audit.claimed_at = datetime.now(timezone.utc)
    session.flush()
    return audit


__all__ = [
    "FIXTURE_MODEL_PREFIX",
    "Aligner",
    "AuditFailedError",
    "AuditOutcome",
    "AuditPipeline",
    "PracticeClassifier",
    "claim_next_audit",
]
