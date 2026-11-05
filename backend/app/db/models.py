"""Database schema — the sixteen tables of the approved Phase 3 design.

Design rules carried from Phase 3 and enforced here:

* Raw policy documents are **not** stored in the database. ``disclosure_snapshot``
  holds a filesystem path and the SHA-256 of the bytes, so the database stays
  small enough to dump and the retrieved document is never altered.
* Every audit run records the exact versions it used: both snapshots, the
  taxonomy mapping version and the three model versions. Seven NOT NULL foreign
  keys, so a report can always be reproduced and can never be silently
  reinterpreted by a later model.
* ``audit_run`` is also the job queue. There is no Redis and no Celery.
* Abstention is a first-class column, never an absent row. A low-confidence
  prediction is kept and flagged so it can propagate through F-15, F-17 and
  F-18 instead of being mistaken for a confident absence.
* Closed value sets are enforced with CHECK constraints against
  ``analysis.vocabulary``, so a typo fails at the database rather than becoming
  a silent eleventh verdict.

Portability: JSON columns use PostgreSQL ``JSONB`` and plain ``JSON``
elsewhere, so the unit test suite can run the real schema on SQLite without a
server. The constraints under test are the same ones production uses.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    desc,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from analysis.vocabulary import (
    ALIGNMENT_LABELS,
    AUDIT_STATUSES,
    GOLD_LABELS,
    MODEL_TASKS,
    MODEL_VARIANTS,
    RECORD_TYPES,
    SOURCE_TYPES,
    SPAN_TYPES,
    VERDICTS,
)

#: JSON that becomes JSONB on PostgreSQL.
#:
#: ``none_as_null=True`` matters more than it looks. By default SQLAlchemy
#: serialises Python ``None`` into the JSON literal ``null``, which satisfies a
#: NOT NULL column and lets a run be stored with no usable threshold
#: configuration at all. With this flag ``None`` becomes SQL NULL and the NOT
#: NULL constraint does its job.
JSONType = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")

#: 64-bit primary key that still autoincrements on SQLite.
#:
#: PostgreSQL gets BIGINT, which is what the high-volume tables need. SQLite
#: aliases the rowid only for a column declared exactly INTEGER, so a BIGINT
#: primary key there never autoincrements and every insert fails on NOT NULL.
#: The variant keeps the production type while letting the unit tests exercise
#: the real schema without a server.
BigIntType = BigInteger().with_variant(Integer, "sqlite")


def _in_set(column: str, values: tuple[str, ...]) -> str:
    """SQL fragment restricting a column to a closed set of values."""
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


class Base(DeclarativeBase):
    pass


# ===========================================================================
# 1. application
# ===========================================================================
class Application(Base):
    """An Android application, identified by its Play Store package name."""

    __tablename__ = "application"

    app_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    app_name: Mapped[str] = mapped_column(String(500), nullable=False)
    developer_name: Mapped[str | None] = mapped_column(String(500))
    #: The Play Store category, such as Tools or Health & Fitness. Nullable
    #: because the collector cannot always obtain it and a placeholder would be
    #: invented data.
    store_category: Mapped[str | None] = mapped_column(String(128))
    play_store_url: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    snapshots: Mapped[list[DisclosureSnapshot]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    audits: Mapped[list[AuditRun]] = relationship(back_populates="application")

    __table_args__ = (
        UniqueConstraint("package_name", name="uq_application_package_name"),
        # ALG-11: case-insensitive prefix search (F-01). A plain B-tree cannot
        # serve a leading-wildcard '%term%' query; prefix search on lower() can.
        # pg_trgm with a GIN index is the documented upgrade path if substring
        # search is later required.
        Index("ix_application_lower_name", func.lower(app_name)),
        Index("ix_application_lower_package", func.lower(package_name)),
        # C-53. The two indexes above use the default `text_ops` operator
        # class, which a prefix LIKE cannot use unless the database collation
        # is C. Confirmed against PostgreSQL 16 on 2026-11-05: F-01's
        # predicate produced no index condition. These two order byte-wise,
        # which is LIKE's own semantics, so the planner can use them. Both
        # pairs are kept: only the default class serves
        # ORDER BY lower(app_name), which F-01 also issues.
        #
        # The expression is LABELLED and `postgresql_ops` is keyed on that
        # label. Keying it on the column name instead compiles with no error
        # and silently drops the operator class, giving an index that looks
        # right and cannot serve the query. `postgresql_ops` is ignored by
        # other dialects, so SQLite receives plain `(lower(app_name))`.
        Index(
            "ix_application_lower_name_pattern",
            func.lower(app_name).label("lower_app_name"),
            postgresql_ops={"lower_app_name": "text_pattern_ops"},
        ),
        Index(
            "ix_application_lower_package_pattern",
            func.lower(package_name).label("lower_package_name"),
            postgresql_ops={"lower_package_name": "text_pattern_ops"},
        ),
    )


# ===========================================================================
# 2. disclosure_snapshot
# ===========================================================================
class DisclosureSnapshot(Base):
    """One retrieval of one disclosure source for one application.

    Snapshots are append-only. A policy that changes produces a new row, which
    is what makes audit comparison over time (F-30) meaningful.
    """

    __tablename__ = "disclosure_snapshot"

    snapshot_id: Mapped[int] = mapped_column(BigIntType, primary_key=True)
    app_id: Mapped[int] = mapped_column(
        ForeignKey("application.app_id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    retrieval_method: Mapped[str] = mapped_column(String(64), nullable=False)

    #: Path on the filesystem. The document body is never stored in the
    #: database, per the Phase 3 storage decision.
    storage_path: Mapped[str | None] = mapped_column(Text)
    #: SHA-256 of the retrieved bytes. Ties the stored file to this row and
    #: lets a later retrieval be recognised as unchanged.
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_bytes: Mapped[int | None] = mapped_column(Integer)
    http_status: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    application: Mapped[Application] = relationship(back_populates="snapshots")
    declared_practices: Mapped[list[DeclaredPractice]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    segments: Mapped[list[PolicySegment]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(_in_set("source_type", SOURCE_TYPES), name="ck_snapshot_source_type"),
        CheckConstraint("length(content_sha256) = 64", name="ck_snapshot_sha256_length"),
        # Phase 3 section 10.3 requires a descending time ordering, because
        # history queries (FR-25) read newest first.
        Index(
            "ix_snapshot_app_source",
            "app_id",
            "source_type",
            desc("retrieved_at"),
        ),
        Index("ix_snapshot_sha256", "content_sha256"),
    )


# ===========================================================================
# 3. declared_practice
# ===========================================================================
class DeclaredPractice(Base):
    """One line of a Data Safety declaration, normalised by F-16."""

    __tablename__ = "declared_practice"

    declared_practice_id: Mapped[int] = mapped_column(BigIntType, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("disclosure_snapshot.snapshot_id", ondelete="CASCADE"), nullable=False
    )

    #: One of the fourteen Google Play Data Safety categories. Validated at the
    #: application boundary rather than by a CHECK, so that a change to
    #: Google's taxonomy surfaces as a named pipeline failure (F-33) instead of
    #: a database rejection mid-run.
    ds_category: Mapped[str] = mapped_column(String(128), nullable=False)
    ds_data_type: Mapped[str | None] = mapped_column(String(128))

    is_collected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_optional: Mapped[bool | None] = mapped_column(Boolean)
    is_ephemeral: Mapped[bool | None] = mapped_column(Boolean)
    purpose: Mapped[str | None] = mapped_column(Text)
    raw_label: Mapped[str | None] = mapped_column(Text)

    snapshot: Mapped[DisclosureSnapshot] = relationship(back_populates="declared_practices")

    __table_args__ = (
        Index("ix_declared_snapshot_category", "snapshot_id", "ds_category"),
    )


# ===========================================================================
# 4. policy_segment
# ===========================================================================
class PolicySegment(Base):
    """A segment of privacy policy text, with offsets into the document.

    Offsets are character positions in the extracted plain text. They are what
    makes evidence quotable and verifiable, so they are never recomputed from a
    reformatted copy of the text.
    """

    __tablename__ = "policy_segment"

    segment_id: Mapped[int] = mapped_column(BigIntType, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("disclosure_snapshot.snapshot_id", ondelete="CASCADE"), nullable=False
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str | None] = mapped_column(Text)

    snapshot: Mapped[DisclosureSnapshot] = relationship(back_populates="segments")
    extracted_practices: Mapped[list[ExtractedPractice]] = relationship(
        back_populates="segment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("snapshot_id", "segment_index", name="uq_segment_snapshot_index"),
        CheckConstraint("char_end > char_start", name="ck_segment_offsets_ordered"),
        CheckConstraint("char_start >= 0", name="ck_segment_offset_nonnegative"),
        Index("ix_segment_snapshot", "snapshot_id", "segment_index"),
    )


# ===========================================================================
# 5. model_version
# ===========================================================================
class ModelVersion(Base):
    """A trained model, recorded so every result can be traced to what produced it.

    ``metrics`` holds measured evaluation output only. A row is created when a
    model is trained; its metrics are written when an evaluation has actually
    run. There is no field for an expected or target score.
    """

    __tablename__ = "model_version"

    model_version_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task: Mapped[str] = mapped_column(String(32), nullable=False)
    variant: Mapped[str] = mapped_column(String(16), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint_path: Mapped[str | None] = mapped_column(Text)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    random_seed: Mapped[int | None] = mapped_column(Integer)
    training_config: Mapped[dict | None] = mapped_column(JSONType)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("task", "version_label", name="uq_model_task_version"),
        CheckConstraint(_in_set("task", MODEL_TASKS), name="ck_model_task"),
        CheckConstraint(_in_set("variant", MODEL_VARIANTS), name="ck_model_variant"),
        Index("ix_model_active", "task", "is_active"),
    )


# ===========================================================================
# 6. extracted_practice
# ===========================================================================
class ExtractedPractice(Base):
    """A data practice the classifier (F-11) found in one policy segment.

    ``abstained`` is the reason this table keeps low-confidence rows instead of
    dropping them. An abstained practice is carried forward and marks every
    downstream judgement as abstained too, so the system reports Undetermined
    rather than inventing a confident absence.
    """

    __tablename__ = "extracted_practice"

    extracted_practice_id: Mapped[int] = mapped_column(BigIntType, primary_key=True)
    segment_id: Mapped[int] = mapped_column(
        ForeignKey("policy_segment.segment_id", ondelete="CASCADE"), nullable=False
    )
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_version.model_version_id"), nullable=False
    )

    #: One of the ten OPP-115 categories.
    opp115_category: Mapped[str] = mapped_column(String(128), nullable=False)

    #: Specified in the approved data dictionary.
    #:
    #: Phase 3 names this column and gives no value set for it anywhere in the
    #: report, including the F-11 specification. The column is restored here so
    #: the schema matches the dictionary, and left nullable with no CHECK
    #: because inventing a vocabulary for it would be fabricating part of the
    #: approved design. Recorded as audit finding E-3 for the team to define.
    practice_type: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    abstained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    threshold_applied: Mapped[float] = mapped_column(Float, nullable=False)

    segment: Mapped[PolicySegment] = relationship(back_populates="extracted_practices")
    spans: Mapped[list[ExtractedSpan]] = relationship(
        back_populates="practice", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_practice_confidence_range"),
        Index("ix_practice_segment_category", "segment_id", "opp115_category"),
        Index("ix_practice_model", "model_version_id"),
    )


# ===========================================================================
# 7. extracted_span
# ===========================================================================
class ExtractedSpan(Base):
    """A data type or purpose span located by F-12, with character offsets.

    Offsets are relative to the parent segment's text. ``span_text`` is stored
    verbatim as extracted; it is never regenerated, because evidence shown to a
    user must be the policy's own words.
    """

    __tablename__ = "extracted_span"

    span_id: Mapped[int] = mapped_column(BigIntType, primary_key=True)
    extracted_practice_id: Mapped[int] = mapped_column(
        ForeignKey("extracted_practice.extracted_practice_id", ondelete="CASCADE"),
        nullable=False,
    )
    #: The span extractor that produced this span. F-12 uses a different model
    #: from F-11, so a span cannot be attributed through its parent practice,
    #: which records only the classifier. Required by NFR-08 reproducibility
    #: and by the baseline-versus-improved comparison of GI-05.
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_version.model_version_id"), nullable=False
    )
    span_type: Mapped[str] = mapped_column(String(32), nullable=False)
    span_text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    normalised_value: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    abstained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    practice: Mapped[ExtractedPractice] = relationship(back_populates="spans")

    __table_args__ = (
        CheckConstraint(_in_set("span_type", SPAN_TYPES), name="ck_span_type"),
        CheckConstraint("char_end > char_start", name="ck_span_offsets_ordered"),
        CheckConstraint("char_start >= 0", name="ck_span_offset_nonnegative"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_span_confidence_range"),
        Index("ix_span_practice", "extracted_practice_id", "span_type"),
        Index("ix_span_model", "model_version_id"),
    )


# ===========================================================================
# 8. taxonomy_mapping_version
# ===========================================================================
class TaxonomyMappingVersion(Base):
    """A version of the OPP-115 to Data Safety category mapping (F-15).

    The mapping is a rule-based lookup, authored by the team and versioned so
    an audit can state which mapping produced it. It is deliberately not
    learned; conflating it with the learned alignment in F-18 would make the
    system's reasoning untraceable.
    """

    __tablename__ = "taxonomy_mapping_version"

    taxonomy_mapping_version_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    author_role: Mapped[str | None] = mapped_column(String(16))
    source_file: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    entries: Mapped[list[TaxonomyMappingEntry]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("version_label", name="uq_taxonomy_version_label"),
        Index("ix_taxonomy_version_active", "is_active"),
    )


# ===========================================================================
# 9. taxonomy_mapping_entry
# ===========================================================================
class TaxonomyMappingEntry(Base):
    """One OPP-115 category to Data Safety category correspondence."""

    __tablename__ = "taxonomy_mapping_entry"

    taxonomy_mapping_entry_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    taxonomy_mapping_version_id: Mapped[int] = mapped_column(
        ForeignKey(
            "taxonomy_mapping_version.taxonomy_mapping_version_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    opp115_category: Mapped[str] = mapped_column(String(128), nullable=False)
    opp115_data_type: Mapped[str | None] = mapped_column(String(255))
    ds_category: Mapped[str] = mapped_column(String(128), nullable=False)
    #: Set when the team judged a correspondence partial rather than direct.
    #: It records the authors' confidence in the rule, not a model's output.
    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rationale: Mapped[str | None] = mapped_column(Text)

    version: Mapped[TaxonomyMappingVersion] = relationship(back_populates="entries")

    __table_args__ = (
        UniqueConstraint(
            "taxonomy_mapping_version_id",
            "opp115_category",
            "opp115_data_type",
            "ds_category",
            name="uq_taxonomy_entry_unique_rule",
        ),
        Index("ix_taxonomy_entry_lookup", "taxonomy_mapping_version_id", "opp115_category"),
    )


# ===========================================================================
# 10. audit_run — also the job queue (F-32)
# ===========================================================================
class AuditRun(Base):
    """One audit of one application, and its queue entry.

    The seven NOT NULL foreign keys are what make a report reproducible: both
    disclosure snapshots, the taxonomy mapping version, and the three model
    versions used. Nothing about the inputs can be inferred after the fact.

    Queue semantics: a row is created ``queued``; a worker claims it by setting
    ``claimed_at`` and ``running``; it ends ``completed`` or ``failed`` with
    ``failure_reason`` populated on failure. There is no external broker.
    """

    __tablename__ = "audit_run"

    audit_id: Mapped[int] = mapped_column(BigIntType, primary_key=True)
    app_id: Mapped[int] = mapped_column(
        ForeignKey("application.app_id", ondelete="CASCADE"), nullable=False
    )
    ds_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("disclosure_snapshot.snapshot_id"), nullable=False
    )
    policy_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("disclosure_snapshot.snapshot_id"), nullable=False
    )
    taxonomy_mapping_version_id: Mapped[int] = mapped_column(
        ForeignKey("taxonomy_mapping_version.taxonomy_mapping_version_id"), nullable=False
    )
    classification_model_id: Mapped[int] = mapped_column(
        ForeignKey("model_version.model_version_id"), nullable=False
    )
    span_model_id: Mapped[int] = mapped_column(
        ForeignKey("model_version.model_version_id"), nullable=False
    )
    alignment_model_id: Mapped[int] = mapped_column(
        ForeignKey("model_version.model_version_id"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default="queued"
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    #: The confidence thresholds in force for this run. Stored per run because
    #: thresholds are tunable, and a report means nothing without them.
    threshold_config: Mapped[dict] = mapped_column(JSONType, nullable=False)

    application: Mapped[Application] = relationship(back_populates="audits")
    verdicts: Mapped[list[Verdict]] = relationship(
        back_populates="audit", cascade="all, delete-orphan"
    )
    judgements: Mapped[list[AlignmentJudgement]] = relationship(
        back_populates="audit", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(_in_set("status", AUDIT_STATUSES), name="ck_audit_status"),
        CheckConstraint(
            "(status <> 'failed') OR (failure_reason IS NOT NULL)",
            name="ck_audit_failed_has_reason",
        ),
        CheckConstraint(
            "(status <> 'completed') OR (completed_at IS NOT NULL)",
            name="ck_audit_completed_has_timestamp",
        ),
        CheckConstraint(
            "ds_snapshot_id <> policy_snapshot_id",
            name="ck_audit_distinct_snapshots",
        ),
        # The queue scan: oldest queued first.
        Index("ix_audit_queue", "status", "requested_at"),
        Index("ix_audit_app_history", "app_id", desc("requested_at")),
    )


# ===========================================================================
# 11. alignment_judgement
# ===========================================================================
class AlignmentJudgement(Base):
    """One F-18 decision on one candidate pair built by F-17.

    Exactly one of ``declared_practice_id`` and ``extracted_practice_id`` may be
    null: a declaration with nothing to compare it against, or a policy
    statement with no corresponding declaration. Both null would be a pair
    about nothing, and the CHECK rejects it.

    ``abstained`` is set when this judgement was below threshold **or** when the
    extracted practice it came from was itself abstained. That OR is the
    abstention propagation rule; losing it would turn an uncertain reading into
    a confident finding.
    """

    __tablename__ = "alignment_judgement"

    judgement_id: Mapped[int] = mapped_column(BigIntType, primary_key=True)
    audit_id: Mapped[int] = mapped_column(
        ForeignKey("audit_run.audit_id", ondelete="CASCADE"), nullable=False
    )
    ds_category: Mapped[str] = mapped_column(String(128), nullable=False)

    declared_practice_id: Mapped[int | None] = mapped_column(
        ForeignKey("declared_practice.declared_practice_id", ondelete="CASCADE")
    )
    extracted_practice_id: Mapped[int | None] = mapped_column(
        ForeignKey("extracted_practice.extracted_practice_id", ondelete="CASCADE")
    )
    segment_id: Mapped[int | None] = mapped_column(
        ForeignKey("policy_segment.segment_id", ondelete="CASCADE")
    )

    label: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    abstained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    threshold_applied: Mapped[float] = mapped_column(Float, nullable=False)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_version.model_version_id"), nullable=False
    )

    audit: Mapped[AuditRun] = relationship(back_populates="judgements")

    __table_args__ = (
        CheckConstraint(_in_set("label", ALIGNMENT_LABELS), name="ck_judgement_label"),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0", name="ck_judgement_confidence_range"
        ),
        CheckConstraint(
            "declared_practice_id IS NOT NULL OR extracted_practice_id IS NOT NULL",
            name="ck_judgement_has_at_least_one_side",
        ),
        Index("ix_judgement_audit_category", "audit_id", "ds_category"),
    )


# ===========================================================================
# 12. verdict
# ===========================================================================
class Verdict(Base):
    """The outcome for one Data Safety category in one audit (F-19, ALG-8).

    One row per category per audit, enforced by the unique constraint. A
    category cannot carry two verdicts.
    """

    __tablename__ = "verdict"

    verdict_id: Mapped[int] = mapped_column(BigIntType, primary_key=True)
    audit_id: Mapped[int] = mapped_column(
        ForeignKey("audit_run.audit_id", ondelete="CASCADE"), nullable=False
    )
    ds_category: Mapped[str] = mapped_column(String(128), nullable=False)
    verdict_value: Mapped[str] = mapped_column(String(32), nullable=False)

    #: Confidence of the judgement that determined this verdict (F-19 step 3).
    #: Nullable, as the approved data dictionary specifies: null where no
    #: judgement determined anything. NFR-07 requires this to reach the user.
    #:
    #: Stored as NUMERIC(5,4), the approved type, which holds exactly four
    #: decimal places with no representation error. The other confidence
    #: columns are still FLOAT pending the team's ruling on audit finding
    #: D-10; that asymmetry is deliberate and recorded, not an oversight.
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))

    #: True when the declaration asserted this category at all. Kept because
    #: ALG-8 resolves a decisive SUPPORTS against the declaration state, and the
    #: report has to be able to explain why.
    declared: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: True when any non-abstained judgement found the category in the policy.
    found_in_policy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: True when abstention affected this category, whether or not the verdict
    #: is Undetermined.
    abstention_involved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    audit: Mapped[AuditRun] = relationship(back_populates="verdicts")
    records: Mapped[list[EvidenceRecord]] = relationship(
        back_populates="verdict", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("audit_id", "ds_category", name="uq_verdict_audit_category"),
        CheckConstraint(_in_set("verdict_value", VERDICTS), name="ck_verdict_value"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_verdict_confidence_range",
        ),
        Index("ix_verdict_audit", "audit_id"),
    )


# ===========================================================================
# 13. evidence_record
# ===========================================================================
class EvidenceRecord(Base):
    """Support for a verdict: quoted text, a recorded absence, or an abstention.

    A Consistent verdict carries no record at all, which is why there is no
    NOT NULL link from verdict to this table.

    An ``evidence`` record must quote real policy text with offsets, because
    that is the whole point of it. An ``absence`` record must not, because
    there is nothing to quote — the finding *is* that nothing was found. The
    CHECK constraints enforce both directions, so a generated or empty quote
    cannot be stored as evidence.
    """

    __tablename__ = "evidence_record"

    evidence_record_id: Mapped[int] = mapped_column(BigIntType, primary_key=True)
    verdict_id: Mapped[int] = mapped_column(
        ForeignKey("verdict.verdict_id", ondelete="CASCADE"), nullable=False
    )
    record_type: Mapped[str] = mapped_column(String(16), nullable=False)

    segment_id: Mapped[int | None] = mapped_column(
        ForeignKey("policy_segment.segment_id", ondelete="SET NULL")
    )
    judgement_id: Mapped[int | None] = mapped_column(
        ForeignKey("alignment_judgement.judgement_id", ondelete="SET NULL")
    )

    #: Verbatim policy text. Never paraphrased, summarised or generated.
    quoted_text: Mapped[str | None] = mapped_column(Text)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)

    #: Why this record exists: which absence rule applied, or why the system
    #: abstained. Required for absence and inconclusive records.
    reason: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    verdict: Mapped[Verdict] = relationship(back_populates="records")

    __table_args__ = (
        CheckConstraint(_in_set("record_type", RECORD_TYPES), name="ck_record_type"),
        CheckConstraint(
            "(record_type <> 'evidence') OR "
            "(quoted_text IS NOT NULL AND length(quoted_text) > 0 "
            " AND segment_id IS NOT NULL "
            " AND char_start IS NOT NULL AND char_end IS NOT NULL "
            " AND char_end > char_start)",
            name="ck_record_evidence_requires_quote",
        ),
        CheckConstraint(
            "(record_type <> 'absence') OR (quoted_text IS NULL AND reason IS NOT NULL)",
            name="ck_record_absence_has_no_quote",
        ),
        CheckConstraint(
            "(record_type <> 'inconclusive') OR (reason IS NOT NULL)",
            name="ck_record_inconclusive_has_reason",
        ),
        Index("ix_record_verdict", "verdict_id", "display_order"),
    )


# ===========================================================================
# 14. gold_annotation
# ===========================================================================
class GoldAnnotation(Base):
    """A human label for one application and category, for evaluation (F-31).

    The CHECK restricts labels to the four annotation labels. Undetermined is
    not among them: it is a system abstention, and allowing a human to record
    it would make the evaluation set unfalsifiable.
    """

    __tablename__ = "gold_annotation"

    gold_annotation_id: Mapped[int] = mapped_column(BigIntType, primary_key=True)
    app_id: Mapped[int] = mapped_column(
        ForeignKey("application.app_id", ondelete="CASCADE"), nullable=False
    )
    ds_category: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(32), nullable=False)

    #: Role identifier of the annotator (R1 to R6), not a personal name.
    annotator_code: Mapped[str] = mapped_column(String(16), nullable=False)
    annotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: Set on the adjudicated label when annotators disagreed.
    is_adjudicated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supporting_quote: Mapped[str | None] = mapped_column(Text)
    annotator_notes: Mapped[str | None] = mapped_column(Text)
    guideline_version: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        UniqueConstraint(
            "app_id", "ds_category", "annotator_code", name="uq_gold_app_category_annotator"
        ),
        CheckConstraint(_in_set("label", GOLD_LABELS), name="ck_gold_label_is_annotation_label"),
        # Phase 3 section 10.3 requires (app_id, ds_category).
        Index("ix_gold_app", "app_id", "ds_category"),
    )


# ===========================================================================
# 15. evaluation_run
# ===========================================================================
class EvaluationRun(Base):
    """One evaluation of one model against the gold set.

    A row records an evaluation that happened. There is no column for a
    target or expected score, by design.
    """

    __tablename__ = "evaluation_run"

    evaluation_run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_version.model_version_id", ondelete="CASCADE"), nullable=False
    )
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: Which gold subset this used, e.g. 'test'. Splits are grouped by
    #: application, never by individual item.
    split_name: Mapped[str] = mapped_column(String(32), nullable=False)
    gold_set_version: Mapped[str | None] = mapped_column(String(64))
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    abstention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict | None] = mapped_column(JSONType)
    notes: Mapped[str | None] = mapped_column(Text)

    metrics: Mapped[list[EvaluationMetric]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("item_count >= 0", name="ck_evaluation_item_count"),
        CheckConstraint(
            "abstention_count >= 0 AND abstention_count <= item_count",
            name="ck_evaluation_abstention_within_items",
        ),
        Index("ix_evaluation_model", "model_version_id", "run_at"),
    )


# ===========================================================================
# 16. evaluation_metric
# ===========================================================================
class EvaluationMetric(Base):
    """One measured number from one evaluation run.

    Stored one metric per row rather than as columns, because the metrics that
    matter here are per class: precision, recall and F1 for each label, plus
    macro-F1 with ``class_label`` null. ``abstention_handling`` records which of
    the two required computations a number came from, so a figure that excluded
    abstentions can never be mistaken for one that counted them as errors.
    """

    __tablename__ = "evaluation_metric"

    evaluation_metric_id: Mapped[int] = mapped_column(BigIntType, primary_key=True)
    evaluation_run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_run.evaluation_run_id", ondelete="CASCADE"), nullable=False
    )
    #: Specified in the approved data dictionary, which describes
    #: "per-category and overall metrics". Phase 3 names the column but states
    #: no value set, so there is no CHECK here; the two values its prose
    #: implies are per-category and overall. Left for the team to confirm.
    #:
    #: Note: restoring this column alone does not make per-category metrics
    #: storable. The baseline breaks metrics down by Data Safety category and
    #: this implementation breaks them down by predicted class label, which is
    #: audit finding D-9 and still awaits a ruling.
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Null for aggregate metrics such as macro-F1.
    class_label: Mapped[str | None] = mapped_column(String(64))
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    support: Mapped[int | None] = mapped_column(Integer)
    #: 'excluded' = computed over non-abstained items only.
    #: 'counted_as_error' = abstentions counted as errors.
    abstention_handling: Mapped[str] = mapped_column(String(32), nullable=False)

    run: Mapped[EvaluationRun] = relationship(back_populates="metrics")

    __table_args__ = (
        UniqueConstraint(
            "evaluation_run_id",
            "metric_name",
            "class_label",
            "abstention_handling",
            name="uq_metric_unique_per_run",
        ),
        CheckConstraint(
            "abstention_handling IN ('excluded', 'counted_as_error')",
            name="ck_metric_abstention_handling",
        ),
        Index("ix_metric_run", "evaluation_run_id"),
    )


#: Every table in the approved design. Used by the schema tests to assert the
#: count has not drifted.
ALL_TABLES: tuple[type[Base], ...] = (
    Application,
    DisclosureSnapshot,
    DeclaredPractice,
    PolicySegment,
    ModelVersion,
    ExtractedPractice,
    ExtractedSpan,
    TaxonomyMappingVersion,
    TaxonomyMappingEntry,
    AuditRun,
    AlignmentJudgement,
    Verdict,
    EvidenceRecord,
    GoldAnnotation,
    EvaluationRun,
    EvaluationMetric,
)
