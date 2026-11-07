"""E1 to E11 — the approved API surface.

One router, because the endpoints share a session dependency and a small set
of lookups. Each is marked with its approved identifier.

Two conventions run through all of them:

* **A refusal is a response, not an exception.** An application that is not in
  the corpus, or a collection event missing a source, produces 404 or 409 with
  the reason and the remedy. Those are expected states of an offline corpus.
* **Nothing is invented to fill a field.** Where the system does not know, the
  response says so — `declares_no_data_collected` stays null, a report
  produced from stub models is flagged, and the scope note appears on every
  report.
"""

from __future__ import annotations

from dataclasses import asdict

from app.api.schemas.audit import (
    AcquisitionStatusOut,
    ApplicationDetailOut,
    ApplicationSummaryOut,
    AuditAcceptedOut,
    AuditComparisonOut,
    AuditHistoryEntryOut,
    AuditRequestIn,
    AuditStatusOut,
    EvidenceOut,
    ModelProvenanceOut,
    ReportOut,
    SnapshotOut,
    SourceLinksOut,
    UnknownApplicationOut,
    VerdictChangeOut,
    VerdictOut,
    VersionsOut,
)
from app.db.models import (
    Application,
    AuditRun,
    EvidenceRecord,
    ModelVersion,
    TaxonomyMappingVersion,
    Verdict,
)
from app.db.repositories.application_repo import (
    ApplicationRepository,
    handle_unknown_application,
)
from app.db.repositories.snapshot_repo import SnapshotRepository, SnapshotSummary
from app.db.session import get_session
from app.services.audit_pipeline import FIXTURE_MODEL_PREFIX
from app.services.audit_service import AuditRequested, AuditService
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api", tags=["audits"])


def _snapshot_out(summary: SnapshotSummary) -> SnapshotOut:
    return SnapshotOut(
        snapshot_id=summary.snapshot_id,
        collected_at=summary.collected_at,
        status=summary.status,
        source_url_listing=summary.source_url_listing,
        source_url_policy=summary.source_url_policy,
        has_declaration=summary.has_declaration,
        has_policy=summary.has_policy,
        declares_no_data_collected=summary.declares_no_data_collected,
    )


def _models_for(session: Session, audit: AuditRun) -> list[ModelProvenanceOut]:
    rows = session.execute(
        select(ModelVersion).where(
            ModelVersion.model_version_id.in_(
                [
                    audit.classification_model_id,
                    audit.span_model_id,
                    audit.alignment_model_id,
                ]
            )
        )
    ).scalars().all()
    return [
        ModelProvenanceOut(
            task=row.task,
            variant=row.variant,
            model_identifier=row.model_identifier,
            version_label=row.version_label,
        )
        for row in rows
    ]


def _require_application(session: Session, package_name: str) -> Application:
    application = session.execute(
        select(Application).where(Application.package_name == package_name)
    ).scalar_one_or_none()
    if application is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"{package_name!r} is not in the offline corpus. Collect and "
                "import it before requesting an audit."
            ),
        )
    return application


# ---------------------------------------------------------------------------
# E1 — application search (F-01)
# ---------------------------------------------------------------------------


@router.get("/applications", response_model=list[ApplicationSummaryOut])
def search_applications(
    q: str = Query(default="", description="Prefix of a name or package"),
    session: Session = Depends(get_session),
) -> list[ApplicationSummaryOut]:
    results = ApplicationRepository(session).search(q)
    return [
        ApplicationSummaryOut(
            package_name=result.package_name,
            app_name=result.app_name,
            developer_name=result.developer_name,
        )
        for result in results
    ]


# ---------------------------------------------------------------------------
# E2 — application detail (F-03 for the unknown case)
# ---------------------------------------------------------------------------


@router.get(
    "/applications/{package_name}",
    response_model=ApplicationDetailOut,
    responses={404: {"model": UnknownApplicationOut}},
)
def application_detail(
    package_name: str, session: Session = Depends(get_session)
) -> ApplicationDetailOut:
    repository = ApplicationRepository(session)
    detail = repository.get_by_package(package_name)
    if detail is None:
        report = handle_unknown_application(package_name)
        # asdict, not __dict__: the report is a slots dataclass and has none.
        raise HTTPException(status_code=404, detail=asdict(report))

    latest = SnapshotRepository(session).latest_for_app(detail.app_id)
    return ApplicationDetailOut(
        package_name=detail.package_name,
        app_name=detail.app_name,
        developer_name=detail.developer_name,
        store_category=detail.store_category,
        play_store_url=detail.play_store_url,
        first_seen_at=detail.first_seen_at,
        latest_snapshot=None if latest is None else _snapshot_out(latest),
    )


# ---------------------------------------------------------------------------
# E3 — request an audit (F-02)
# ---------------------------------------------------------------------------


@router.post("/audits", response_model=AuditAcceptedOut, status_code=202)
def request_audit(
    payload: AuditRequestIn, session: Session = Depends(get_session)
) -> AuditAcceptedOut:
    result = AuditService(session).request_audit(
        payload.package_name, variant=payload.variant
    )
    if not isinstance(result, AuditRequested):
        # 409: the application exists but its data cannot support a report.
        # 404 would say the application is unknown, which is a different fact.
        # 404 only for an application nobody holds. A bad variant is a
        # malformed request, and everything else is a real conflict with the
        # stored data.
        if result.reason == "unknown_application":
            status = 404
        elif result.reason == "unknown_variant":
            status = 422
        else:
            status = 409
        raise HTTPException(
            status_code=status,
            detail={
                "package_name": result.package_name,
                "reason": result.reason,
                "detail": result.detail,
                "snapshot_status": result.snapshot_status,
            },
        )
    return AuditAcceptedOut(
        audit_id=result.audit_id,
        package_name=result.package_name,
        status="queued",
        snapshot_id=result.snapshot_id,
        threshold_config=result.threshold_config,
    )


# ---------------------------------------------------------------------------
# E4 — audit status
# ---------------------------------------------------------------------------


@router.get("/audits/{audit_id}", response_model=AuditStatusOut)
def audit_status(
    audit_id: int, session: Session = Depends(get_session)
) -> AuditStatusOut:
    audit = session.get(AuditRun, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail=f"no audit {audit_id}")
    return AuditStatusOut(
        audit_id=audit.audit_id,
        package_name=audit.application.package_name,
        status=audit.status,
        requested_at=audit.requested_at,
        claimed_at=audit.claimed_at,
        completed_at=audit.completed_at,
        failure_reason=audit.failure_reason,
    )


# ---------------------------------------------------------------------------
# E5 — the report
# ---------------------------------------------------------------------------


@router.get("/audits/{audit_id}/report", response_model=ReportOut)
def audit_report(
    audit_id: int, session: Session = Depends(get_session)
) -> ReportOut:
    audit = session.get(AuditRun, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail=f"no audit {audit_id}")
    if audit.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=(
                f"audit {audit_id} is {audit.status!r}. A report is available "
                "only once the audit has completed; a partial one would "
                "present an unfinished analysis as a finding."
            ),
        )

    verdict_rows = session.execute(
        select(Verdict).where(Verdict.audit_id == audit_id).order_by(Verdict.ds_category)
    ).scalars().all()

    verdicts: list[VerdictOut] = []
    for row in verdict_rows:
        records = session.execute(
            select(EvidenceRecord)
            .where(EvidenceRecord.verdict_id == row.verdict_id)
            .order_by(EvidenceRecord.display_order)
        ).scalars().all()
        verdicts.append(
            VerdictOut(
                ds_category=row.ds_category,
                verdict=row.verdict_value,
                confidence=float(row.confidence) if row.confidence is not None else None,
                declared=row.declared,
                found_in_policy=row.found_in_policy,
                abstention_involved=row.abstention_involved,
                evidence=[
                    EvidenceOut(
                        record_type=record.record_type,
                        display_order=record.display_order,
                        quoted_text=record.quoted_text,
                        char_start=record.char_start,
                        char_end=record.char_end,
                        reason=record.reason,
                        segment_id=record.segment_id,
                    )
                    for record in records
                ],
            )
        )

    snapshot = SnapshotRepository(session).latest_for_app(audit.app_id)
    models = _models_for(session, audit)
    mapping = session.get(TaxonomyMappingVersion, audit.taxonomy_mapping_version_id)

    return ReportOut(
        audit_id=audit.audit_id,
        package_name=audit.application.package_name,
        status=audit.status,
        requested_at=audit.requested_at,
        completed_at=audit.completed_at,
        snapshot=_snapshot_out(snapshot),
        verdicts=verdicts,
        thresholds=audit.threshold_config or {},
        models=models,
        taxonomy_mapping_version=None if mapping is None else mapping.version_label,
        uses_fixture_models=any(
            model.model_identifier.startswith(FIXTURE_MODEL_PREFIX)
            for model in models
        ),
    )


# ---------------------------------------------------------------------------
# E6 — evidence for one category
# ---------------------------------------------------------------------------


@router.get(
    "/audits/{audit_id}/evidence/{ds_category}", response_model=list[EvidenceOut]
)
def category_evidence(
    audit_id: int, ds_category: str, session: Session = Depends(get_session)
) -> list[EvidenceOut]:
    verdict = session.execute(
        select(Verdict).where(
            Verdict.audit_id == audit_id, Verdict.ds_category == ds_category
        )
    ).scalar_one_or_none()
    if verdict is None:
        raise HTTPException(
            status_code=404,
            detail=f"audit {audit_id} has no verdict for {ds_category!r}",
        )
    records = session.execute(
        select(EvidenceRecord)
        .where(EvidenceRecord.verdict_id == verdict.verdict_id)
        .order_by(EvidenceRecord.display_order)
    ).scalars().all()
    return [
        EvidenceOut(
            record_type=record.record_type,
            display_order=record.display_order,
            quoted_text=record.quoted_text,
            char_start=record.char_start,
            char_end=record.char_end,
            reason=record.reason,
            segment_id=record.segment_id,
        )
        for record in records
    ]


# ---------------------------------------------------------------------------
# E7 — audit history
# ---------------------------------------------------------------------------


@router.get(
    "/applications/{package_name}/audits",
    response_model=list[AuditHistoryEntryOut],
)
def audit_history(
    package_name: str, session: Session = Depends(get_session)
) -> list[AuditHistoryEntryOut]:
    application = _require_application(session, package_name)
    audits = session.execute(
        select(AuditRun)
        .where(AuditRun.app_id == application.app_id)
        .order_by(AuditRun.requested_at.desc(), AuditRun.audit_id.desc())
    ).scalars().all()

    entries: list[AuditHistoryEntryOut] = []
    for audit in audits:
        counts = dict(
            session.execute(
                select(Verdict.verdict_value, func.count())
                .where(Verdict.audit_id == audit.audit_id)
                .group_by(Verdict.verdict_value)
            ).all()
        )
        entries.append(
            AuditHistoryEntryOut(
                audit_id=audit.audit_id,
                status=audit.status,
                requested_at=audit.requested_at,
                completed_at=audit.completed_at,
                snapshot_id=audit.snapshot_id,
                verdict_counts=counts,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# E8 — compare two audits
# ---------------------------------------------------------------------------


@router.get("/audits/{earlier_id}/compare/{later_id}", response_model=AuditComparisonOut)
def compare_audits(
    earlier_id: int, later_id: int, session: Session = Depends(get_session)
) -> AuditComparisonOut:
    earlier = session.get(AuditRun, earlier_id)
    later = session.get(AuditRun, later_id)
    if earlier is None or later is None:
        raise HTTPException(status_code=404, detail="one of the audits does not exist")
    if earlier.app_id != later.app_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "the two audits are of different applications; comparing them "
                "would describe a change that never happened"
            ),
        )

    def verdicts_of(audit_id: int) -> dict[str, str]:
        return dict(
            session.execute(
                select(Verdict.ds_category, Verdict.verdict_value).where(
                    Verdict.audit_id == audit_id
                )
            ).all()
        )

    before, after = verdicts_of(earlier_id), verdicts_of(later_id)
    changes = [
        VerdictChangeOut(
            ds_category=category,
            earlier_verdict=before.get(category),
            later_verdict=after.get(category),
            changed=before.get(category) != after.get(category),
        )
        for category in sorted(set(before) | set(after))
    ]
    return AuditComparisonOut(
        package_name=later.application.package_name,
        earlier_audit_id=earlier_id,
        later_audit_id=later_id,
        changes=changes,
        changed_count=sum(1 for change in changes if change.changed),
    )


# ---------------------------------------------------------------------------
# E9 — source links
# ---------------------------------------------------------------------------


@router.get("/applications/{package_name}/sources", response_model=SourceLinksOut)
def source_links(
    package_name: str, session: Session = Depends(get_session)
) -> SourceLinksOut:
    application = _require_application(session, package_name)
    snapshot = SnapshotRepository(session).latest_for_app(application.app_id)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"{package_name!r} has no collection event recorded",
        )
    return SourceLinksOut(
        package_name=package_name,
        snapshot_id=snapshot.snapshot_id,
        collected_at=snapshot.collected_at,
        source_url_listing=snapshot.source_url_listing,
        source_url_policy=snapshot.source_url_policy,
        policy_doc_sha256=snapshot.policy_doc_sha256,
    )


# ---------------------------------------------------------------------------
# E10 — version metadata
# ---------------------------------------------------------------------------


@router.get("/versions", response_model=VersionsOut)
def versions(session: Session = Depends(get_session)) -> VersionsOut:
    revision = session.execute(
        select(func.max(ModelVersion.version_label)).where(ModelVersion.is_active)
    ).scalar()
    mapping = session.execute(
        select(TaxonomyMappingVersion)
        .where(TaxonomyMappingVersion.is_active.is_(True))
        .limit(1)
    ).scalar_one_or_none()
    rows = session.execute(
        select(ModelVersion).where(ModelVersion.is_active.is_(True))
    ).scalars().all()
    models = [
        ModelProvenanceOut(
            task=row.task,
            variant=row.variant,
            model_identifier=row.model_identifier,
            version_label=row.version_label,
        )
        for row in rows
    ]
    return VersionsOut(
        schema_revision=revision,
        taxonomy_mapping_version=None if mapping is None else mapping.version_label,
        models=models,
        uses_fixture_models=any(
            model.model_identifier.startswith(FIXTURE_MODEL_PREFIX)
            for model in models
        ),
    )


# ---------------------------------------------------------------------------
# E11 — acquisition status, the single team-facing path
# ---------------------------------------------------------------------------


@router.get("/acquisition/status", response_model=AcquisitionStatusOut)
def acquisition_status(session: Session = Depends(get_session)) -> AcquisitionStatusOut:
    """Reports whether live retrieval is configured. Never that it succeeded."""
    count = session.execute(select(func.count()).select_from(Application)).scalar() or 0
    return AcquisitionStatusOut(
        live_retrieval_configured=False,
        corpus_application_count=count,
        detail=(
            "Live retrieval is attempted through the acquisition gateway and "
            "is optional: audits read the stored corpus and never require "
            "network access. This endpoint reports configuration, not a "
            "successful fetch."
        ),
    )
