"""Which models an audit actually runs with, and what to do when there are none.

The project's state, stated here because the rest of the backend depends on
it: **the M5 baseline is the only trained model that exists.** The M6 improved
classifier is implemented and untrained, F-12's tagger has no training loop
yet, and F-18 is zero-shot against a checkpoint that could not be downloaded
in the build environment.

So this module resolves what is genuinely loadable, and **refuses** rather
than substituting anything invented. There is no code path here that produces
a prediction without a model behind it.

Fixtures are available and clearly marked: `register_fixture_models` writes
`model_version` rows whose identifiers begin with ``fixture:``, and the
pipeline reads those back so a fixture-backed report says so in its own
provenance.
"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.db.models import ModelVersion, TaxonomyMappingEntry, TaxonomyMappingVersion
from app.services.audit_pipeline import FIXTURE_MODEL_PREFIX, AuditPipeline
from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.mapping.taxonomy_mapper import MappingRule, TaxonomyMapper
from analysis.vocabulary import (
    TASK_ALIGNMENT,
    TASK_CLASSIFICATION,
    TASK_SPAN_EXTRACTION,
    VARIANT_BASELINE,
)

DEFAULT_BASELINE_CHECKPOINT = Path("ml/checkpoints/baseline_classifier")


class ModelsUnavailableError(RuntimeError):
    """No usable model set. The caller must refuse to run audits."""


def load_baseline_classifier(checkpoint: Path | str = DEFAULT_BASELINE_CHECKPOINT):
    """The M5 baseline, the only evaluated classifier in the project."""
    from analysis.models.practice_classifier import BaselinePracticeClassifier

    checkpoint = Path(checkpoint)
    if not checkpoint.is_dir():
        raise ModelsUnavailableError(
            f"the M5 baseline artefact is not at {checkpoint}. It is "
            "git-ignored by design; rebuild it with "
            "python ml/train_baseline_classifier.py"
        )
    return BaselinePracticeClassifier.load(checkpoint)


def load_aligner(threshold: float = 0.50):
    """F-18 zero-shot. Raises when the NLI checkpoint cannot be loaded."""
    from analysis.alignment.nli import ZeroShotAligner

    try:
        from ml.backends import TransformersNliBackend
    except ImportError as exc:
        raise ModelsUnavailableError(
            "F-18 needs transformers, which is not installed: "
            "pip install -r backend/requirements-ml.txt"
        ) from exc

    try:
        backend = TransformersNliBackend()
    except Exception as exc:  # noqa: BLE001 - the reason is what matters
        raise ModelsUnavailableError(
            f"the F-18 NLI checkpoint could not be loaded: "
            f"{type(exc).__name__}: {exc}. Fine-tuning has not happened and "
            "the zero-shot checkpoint must be downloadable for an audit to "
            "run with a real aligner."
        ) from exc
    return ZeroShotAligner(backend, threshold=threshold)


def load_mapper(session: Session) -> TaxonomyMapper:
    """F-15 from the active taxonomy mapping version.

    **No rules have been authored.** The mechanism works and has nothing to
    look up, so the mapper this returns today holds zero rules and
    `AuditPipeline` will refuse the audit. That is a real gap, reported
    rather than filled with invented rules.
    """
    version = session.execute(
        select(TaxonomyMappingVersion)
        .where(TaxonomyMappingVersion.is_active.is_(True))
        .limit(1)
    ).scalar_one_or_none()
    if version is None:
        raise ModelsUnavailableError("no active taxonomy mapping version")

    rules = load_mapping_rules(session, version.taxonomy_mapping_version_id)
    return TaxonomyMapper(rules, version.version_label)


def load_mapping_rules(session: Session, version_id: int) -> list[MappingRule]:
    """Read F-15's rules from `taxonomy_mapping_entry`.

    Returns an empty list when none are authored, which is the current state:
    the lookup works and has nothing to look up.

    An empty rule set is **not** a usable configuration. With no rules, no
    policy practice can reach a Data Safety category, so every declared
    category would reach ALG-8 with the declaration side only and be reported
    Declared-not-in-policy — findings manufactured by the missing table.
    `AuditPipeline` therefore refuses to run when `rule_count` is zero rather
    than producing that report.
    """
    entries = session.execute(
        select(TaxonomyMappingEntry).where(
            TaxonomyMappingEntry.taxonomy_mapping_version_id == version_id
        )
    ).scalars().all()
    return [
        MappingRule(
            opp115_category=entry.opp115_category,
            ds_category=entry.ds_category,
            opp115_data_type=entry.opp115_data_type,
            is_partial=entry.is_partial,
            rationale=entry.rationale or "",
        )
        for entry in entries
    ]


def build_pipeline_factory(repository_root: Path | str = "."):
    """A callable the worker uses to build one pipeline per session.

    Raises at **startup** when the models are unavailable, so a worker never
    reaches an audit it cannot honestly run.
    """
    classifier = load_baseline_classifier()
    aligner = load_aligner(get_settings().alignment_confidence_threshold)

    def factory(session: Session) -> AuditPipeline:
        return AuditPipeline(
            session,
            classifier=classifier,
            aligner=aligner,
            mapper=load_mapper(session),
            repository_root=repository_root,
        )

    return factory


def register_fixture_models(session: Session, version_label: str) -> dict[str, int]:
    """Create `model_version` rows for a fixture-backed run.

    Identifiers begin with ``fixture:``, which `AuditPipeline` reads back to
    set `uses_fixture_models`. A report produced this way therefore declares
    it, instead of looking like real inference.
    """
    identifiers: dict[str, int] = {}
    for task in (TASK_CLASSIFICATION, TASK_SPAN_EXTRACTION, TASK_ALIGNMENT):
        row = ModelVersion(
            task=task,
            variant=VARIANT_BASELINE,
            model_identifier=f"{FIXTURE_MODEL_PREFIX}{task}",
            version_label=version_label,
            is_active=True,
            notes="Controlled stub for integration testing. Not a trained model.",
        )
        session.add(row)
        session.flush()
        identifiers[task] = row.model_version_id
    return identifiers


__all__ = [
    "ModelsUnavailableError",
    "load_mapping_rules",
    "build_pipeline_factory",
    "load_aligner",
    "load_baseline_classifier",
    "load_mapper",
    "register_fixture_models",
]
