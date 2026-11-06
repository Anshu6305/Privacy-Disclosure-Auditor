"""Response shapes for E1 to E11.

Pydantic models rather than raw dicts, so the contract the frontend codes
against is declared in one place and a missing field is an error here rather
than a blank panel there.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ApplicationSummaryOut(BaseModel):
    """E1. Exactly the three fields FR-01 names."""

    package_name: str
    app_name: str
    developer_name: str | None = None


class SnapshotOut(BaseModel):
    snapshot_id: int
    collected_at: datetime
    status: str
    source_url_listing: str | None = None
    source_url_policy: str | None = None
    has_declaration: bool
    has_policy: bool
    #: Three-state on purpose. None means the Data Safety section was never
    #: read, which is not the same as an app declaring it collects nothing.
    declares_no_data_collected: bool | None = None


class ApplicationDetailOut(BaseModel):
    """E2."""

    package_name: str
    app_name: str
    developer_name: str | None = None
    store_category: str | None = None
    play_store_url: str | None = None
    first_seen_at: datetime
    latest_snapshot: SnapshotOut | None = None


class UnknownApplicationOut(BaseModel):
    """E2/E3 when the package is not in the corpus (F-03)."""

    package_name: str
    present_in_corpus: bool = False
    live_retrieval_configured: bool
    can_request_audit: bool
    reason: str
    suggested_action: str


class AuditRequestIn(BaseModel):
    package_name: str = Field(min_length=1)


class AuditAcceptedOut(BaseModel):
    """E3."""

    audit_id: int
    package_name: str
    status: str
    snapshot_id: int
    threshold_config: dict


class AuditRefusedOut(BaseModel):
    """E3 when the audit cannot produce an honest report."""

    package_name: str
    reason: str
    detail: str
    snapshot_status: str | None = None


class AuditStatusOut(BaseModel):
    """E4."""

    audit_id: int
    package_name: str
    status: str
    requested_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None


class EvidenceOut(BaseModel):
    """E6. One of three record types, and they are not interchangeable.

    ``evidence`` carries verbatim policy text with offsets. ``absence`` carries a
    system-generated statement and **no quote**: there is no text to quote
    when the finding is that nothing was said. ``inconclusive`` records that
    the system was not certain enough to decide.
    """

    record_type: str
    display_order: int
    quoted_text: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    reason: str | None = None
    segment_id: int | None = None


class VerdictOut(BaseModel):
    """E5."""

    ds_category: str
    verdict: str
    confidence: float | None = None
    declared: bool
    found_in_policy: bool
    abstention_involved: bool
    evidence: list[EvidenceOut] = Field(default_factory=list)


class ModelProvenanceOut(BaseModel):
    task: str
    variant: str
    model_identifier: str
    version_label: str


class ReportOut(BaseModel):
    """E5. The report, with everything needed to judge how much to trust it."""

    audit_id: int
    package_name: str
    status: str
    requested_at: datetime
    completed_at: datetime | None = None
    snapshot: SnapshotOut
    verdicts: list[VerdictOut]
    thresholds: dict
    models: list[ModelProvenanceOut]
    taxonomy_mapping_version: str | None = None
    #: True when any model behind this report is a controlled stub. A report
    #: produced from fixtures says so rather than resembling real inference.
    uses_fixture_models: bool
    #: Stated in every report, because the project's scope is narrower than
    #: readers tend to assume.
    scope_note: str = (
        "This audit compares a Google Play Data Safety declaration with the "
        "text of a privacy policy. It does not observe what the application "
        "actually does at runtime, and it is not a legal compliance finding."
    )


class AuditHistoryEntryOut(BaseModel):
    """E7."""

    audit_id: int
    status: str
    requested_at: datetime
    completed_at: datetime | None = None
    snapshot_id: int
    verdict_counts: dict[str, int] = Field(default_factory=dict)


class VerdictChangeOut(BaseModel):
    ds_category: str
    earlier_verdict: str | None = None
    later_verdict: str | None = None
    changed: bool


class AuditComparisonOut(BaseModel):
    """E8."""

    package_name: str
    earlier_audit_id: int
    later_audit_id: int
    changes: list[VerdictChangeOut]
    changed_count: int


class SourceLinksOut(BaseModel):
    """E9."""

    package_name: str
    snapshot_id: int
    collected_at: datetime
    source_url_listing: str | None = None
    source_url_policy: str | None = None
    policy_doc_sha256: str | None = None


class VersionsOut(BaseModel):
    """E10."""

    schema_revision: str | None = None
    taxonomy_mapping_version: str | None = None
    models: list[ModelProvenanceOut]
    uses_fixture_models: bool


class AcquisitionStatusOut(BaseModel):
    """E11, the single team-facing path. Never says a fetch succeeded unless
    one did."""

    live_retrieval_configured: bool
    corpus_application_count: int
    detail: str
