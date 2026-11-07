"""F-02 — requesting an audit.

Module location is fixed by the approved function-to-module mapping (Phase 4
master plan §3).

An audit request is a **refusal-first** operation. Creating an `audit_run`
row commits the system to producing a report, and a report that was built
from one disclosure source would compare something against nothing. ALG-8
would then have to call that either agreement or absence, and both would be
wrong. So the preconditions are checked before the row exists, and a request
that cannot produce an honest report is declined with the reason rather than
queued and failed later.

What must hold before an audit is queued:

* the application is in the corpus (F-03 answers when it is not);
* it has an active collection event;
* that event captured **both** sources — ``status`` is auditable;
* an active taxonomy mapping version exists;
* an active model version exists for each of the three learning tasks.

The last two are recorded on the row so the report is reproducible: Phase 3
requires that nothing about an audit's inputs has to be inferred afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.db.models import AuditRun, ModelVersion, TaxonomyMappingVersion
from app.db.repositories.application_repo import ApplicationRepository
from app.db.repositories.snapshot_repo import SnapshotRepository, SnapshotSummary
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from analysis.models.variant import (
    MixedVariantError,
    UnknownVariantError,
    bind_variant,
    normalise_variant,
)
from analysis.vocabulary import (
    MODEL_TASKS,
    SNAPSHOT_AUDITABLE,
    SNAPSHOT_HAS_DECLARATION,
    SNAPSHOT_HAS_POLICY,
    STATUS_QUEUED,
)

#: Why an audit could not be requested. Each value is a distinct cause with a
#: distinct remedy, so a caller can say something useful rather than "failed".
REASON_UNKNOWN_APPLICATION = "unknown_application"
REASON_NO_COLLECTION_EVENT = "no_collection_event"
REASON_DECLARATION_MISSING = "declaration_missing"
REASON_POLICY_MISSING = "policy_missing"
REASON_SOURCES_MISSING = "sources_missing"
REASON_NO_TAXONOMY_MAPPING = "no_taxonomy_mapping"
REASON_NO_MODEL = "no_model_for_task"
REASON_UNKNOWN_VARIANT = "unknown_variant"
REASON_VARIANT_UNAVAILABLE = "variant_unavailable"
REASON_MIXED_VARIANT = "mixed_variant"


@dataclass(frozen=True, slots=True)
class AuditRequestRefused:
    """Why no audit was created, in terms the caller can act on."""

    package_name: str
    reason: str
    detail: str
    snapshot_status: str | None = None


@dataclass(frozen=True, slots=True)
class AuditRequested:
    """The queued audit and the inputs pinned to it."""

    audit_id: int
    app_id: int
    package_name: str
    snapshot_id: int
    taxonomy_mapping_version_id: int
    classification_model_id: int
    span_model_id: int
    alignment_model_id: int
    threshold_config: dict


class AuditService:
    """F-02. Creates at most one `audit_run` row, after checking it can be
    honoured."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._applications = ApplicationRepository(session)
        self._snapshots = SnapshotRepository(session)

    def request_audit(
        self, package_name: str, variant: str | None = None
    ) -> AuditRequested | AuditRequestRefused:
        """F-13/F-34. ``variant`` is optional and internal (DD-8).

        Omitted - every end-user request - the active version set is used.
        Supplied by the Corpus Maintainer's command-line tooling, that
        variant is bound for the whole audit and there is no fallback to
        another one.
        """
        # Before any work: an unknown variant is refused here, not after the
        # policy has been fetched and segmented.
        try:
            requested_variant = normalise_variant(variant)
        except UnknownVariantError as unknown:
            return AuditRequestRefused(
                package_name=(package_name or "").strip(),
                reason=REASON_UNKNOWN_VARIANT,
                detail=str(unknown),
            )

        application = self._applications.get_by_package(package_name)
        if application is None:
            return AuditRequestRefused(
                package_name=(package_name or "").strip(),
                reason=REASON_UNKNOWN_APPLICATION,
                detail=(
                    "The application is not in the offline corpus, so there "
                    "is nothing to audit. Collect and import it first."
                ),
            )

        snapshot = self._snapshots.latest_for_app(application.app_id)
        if snapshot is None:
            return AuditRequestRefused(
                package_name=application.package_name,
                reason=REASON_NO_COLLECTION_EVENT,
                detail=(
                    "The application is stored but no collection event has "
                    "been recorded for it, so neither disclosure source is "
                    "available."
                ),
            )

        incomplete = self._refuse_incomplete(application.package_name, snapshot)
        if incomplete is not None:
            return incomplete

        mapping = self._session.execute(
            select(TaxonomyMappingVersion)
            .where(TaxonomyMappingVersion.is_active.is_(True))
            .order_by(desc(TaxonomyMappingVersion.taxonomy_mapping_version_id))
            .limit(1)
        ).scalar_one_or_none()
        if mapping is None:
            return AuditRequestRefused(
                package_name=application.package_name,
                reason=REASON_NO_TAXONOMY_MAPPING,
                detail=(
                    "No active taxonomy mapping version exists. F-15 cannot "
                    "relate OPP-115 categories to Data Safety categories "
                    "without one, so no verdict could be produced."
                ),
                snapshot_status=snapshot.status,
            )

        models: dict[str, ModelVersion] = {}
        for task in MODEL_TASKS:
            query = select(ModelVersion).where(
                ModelVersion.task == task, ModelVersion.is_active.is_(True)
            )
            if requested_variant is not None:
                query = query.where(ModelVersion.variant == requested_variant)
            model = self._session.execute(
                query.order_by(desc(ModelVersion.model_version_id)).limit(1)
            ).scalar_one_or_none()
            if model is None:
                if requested_variant is not None:
                    # No fallback. Running the other variant would produce a
                    # report whose provenance names a model that never ran,
                    # which is exactly what a comparison must not do.
                    return AuditRequestRefused(
                        package_name=application.package_name,
                        reason=REASON_VARIANT_UNAVAILABLE,
                        detail=(
                            f"No active {requested_variant!r} model version "
                            f"for the {task!r} task. F-13 binds one variant "
                            "for the whole audit and does not fall back to "
                            "another, so the audit was not created."
                        ),
                        snapshot_status=snapshot.status,
                    )
                return AuditRequestRefused(
                    package_name=application.package_name,
                    reason=REASON_NO_MODEL,
                    detail=(
                        f"No active model version for the {task!r} task. An "
                        "audit records the model that produced every "
                        "judgement, so it cannot run without one."
                    ),
                    snapshot_status=snapshot.status,
                )
            models[task] = model

        # One variant for the whole audit. With none requested the active
        # registrations decide, and they must agree.
        # The variant itself needs no column: every model_version row
        # carries one, and the three ids recorded below are the binding.
        # This call is here for its refusal, not its return value.
        try:
            bind_variant(models, requested_variant)
        except MixedVariantError as mixed:
            return AuditRequestRefused(
                package_name=application.package_name,
                reason=REASON_MIXED_VARIANT,
                detail=str(mixed),
                snapshot_status=snapshot.status,
            )

        settings = get_settings()
        # Pinned per run, because thresholds are tunable and a report means
        # nothing without the values that produced it.
        threshold_config = {
            "classifier": settings.classifier_confidence_threshold,
            "span": settings.span_confidence_threshold,
            "alignment": settings.alignment_confidence_threshold,
            "provisional": True,
        }

        audit = AuditRun(
            app_id=application.app_id,
            snapshot_id=snapshot.snapshot_id,
            taxonomy_mapping_version_id=mapping.taxonomy_mapping_version_id,
            classification_model_id=models["classification"].model_version_id,
            span_model_id=models["span_extraction"].model_version_id,
            alignment_model_id=models["alignment"].model_version_id,
            status=STATUS_QUEUED,
            threshold_config=threshold_config,
        )
        self._session.add(audit)
        self._session.flush()

        return AuditRequested(
            audit_id=audit.audit_id,
            app_id=application.app_id,
            package_name=application.package_name,
            snapshot_id=snapshot.snapshot_id,
            taxonomy_mapping_version_id=mapping.taxonomy_mapping_version_id,
            classification_model_id=audit.classification_model_id,
            span_model_id=audit.span_model_id,
            alignment_model_id=audit.alignment_model_id,
            threshold_config=threshold_config,
        )

    @staticmethod
    def _refuse_incomplete(
        package_name: str, snapshot: SnapshotSummary
    ) -> AuditRequestRefused | None:
        """A partial collection event cannot produce an honest comparison.

        Each missing side gets its own reason, because the remedies differ and
        because "the declaration was never read" and "the policy could not be
        fetched" are different facts about the application. Neither is an
        absence of disclosure.
        """
        if snapshot.status in SNAPSHOT_AUDITABLE:
            return None

        has_declaration = snapshot.status in SNAPSHOT_HAS_DECLARATION
        has_policy = snapshot.status in SNAPSHOT_HAS_POLICY

        if has_declaration and not has_policy:
            reason, missing = REASON_POLICY_MISSING, "privacy policy"
        elif has_policy and not has_declaration:
            reason, missing = REASON_DECLARATION_MISSING, "Data Safety declaration"
        else:
            reason, missing = REASON_SOURCES_MISSING, "both disclosure sources"

        return AuditRequestRefused(
            package_name=package_name,
            reason=reason,
            detail=(
                f"The latest collection event has status {snapshot.status!r}, "
                f"so the {missing} is not available. An audit compares the two "
                "sources against each other; with one missing, any verdict "
                "would be drawn from an absence of data rather than from a "
                "disclosure. Re-collect the application before requesting an "
                "audit."
            ),
            snapshot_status=snapshot.status,
        )


__all__ = [
    "AuditRequestRefused",
    "AuditRequested",
    "AuditService",
    "REASON_DECLARATION_MISSING",
    "REASON_NO_COLLECTION_EVENT",
    "REASON_NO_MODEL",
    "REASON_NO_TAXONOMY_MAPPING",
    "REASON_POLICY_MISSING",
    "REASON_SOURCES_MISSING",
    "REASON_UNKNOWN_APPLICATION",
]
