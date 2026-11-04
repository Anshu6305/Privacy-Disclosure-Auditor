"""Controlled vocabularies shared across the system.

This module is the single definition of every closed set of values the system
uses: verdicts, annotation labels, alignment labels, record types, job states
and the two taxonomies. It lives in ``analysis/`` because the pipeline needs it
and must not depend on the web or database layers; the database models import
it in the other direction, which is the dependency direction Phase 3 section
6.1 requires.

Nothing here is a tuning parameter. These are the value sets the approved
design fixes, and changing one is a design change, not a configuration change.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# System verdicts (five) — ALG-8
# ---------------------------------------------------------------------------

VERDICT_CONSISTENT: Final = "Consistent"
VERDICT_DECLARED_NOT_IN_POLICY: Final = "Declared-not-in-policy"
VERDICT_IN_POLICY_NOT_DECLARED: Final = "In-policy-not-declared"
VERDICT_CONTRADICTORY: Final = "Contradictory"
VERDICT_UNDETERMINED: Final = "Undetermined"

VERDICTS: Final[tuple[str, ...]] = (
    VERDICT_CONSISTENT,
    VERDICT_DECLARED_NOT_IN_POLICY,
    VERDICT_IN_POLICY_NOT_DECLARED,
    VERDICT_CONTRADICTORY,
    VERDICT_UNDETERMINED,
)

# ---------------------------------------------------------------------------
# Ground-truth annotation labels (four)
#
# Undetermined is deliberately absent. It is a system abstention produced when
# confidence falls below threshold, not a judgement a human annotator can
# record. An annotator who cannot decide does not label the case at all.
# The gold_annotation table enforces this with a CHECK constraint.
# ---------------------------------------------------------------------------

GOLD_LABELS: Final[tuple[str, ...]] = (
    VERDICT_CONSISTENT,
    VERDICT_DECLARED_NOT_IN_POLICY,
    VERDICT_IN_POLICY_NOT_DECLARED,
    VERDICT_CONTRADICTORY,
)

# ---------------------------------------------------------------------------
# Alignment labels (three) — F-18
# ---------------------------------------------------------------------------

ALIGN_SUPPORTS: Final = "SUPPORTS"
ALIGN_CONTRADICTS: Final = "CONTRADICTS"
ALIGN_NO_MATCH: Final = "NO_MATCH"

ALIGNMENT_LABELS: Final[tuple[str, ...]] = (
    ALIGN_SUPPORTS,
    ALIGN_CONTRADICTS,
    ALIGN_NO_MATCH,
)

# ---------------------------------------------------------------------------
# Evidence record types (three) — F-20, F-21, F-22
#
# A Consistent verdict carries no record at all. The three types cover the
# other four verdicts: quoted text where a statement exists, a recorded absence
# where the point is that nothing was found, and an inconclusive record where
# the system abstained.
# ---------------------------------------------------------------------------

RECORD_EVIDENCE: Final = "evidence"
RECORD_ABSENCE: Final = "absence"
RECORD_INCONCLUSIVE: Final = "inconclusive"

RECORD_TYPES: Final[tuple[str, ...]] = (
    RECORD_EVIDENCE,
    RECORD_ABSENCE,
    RECORD_INCONCLUSIVE,
)

#: Verdicts that require at least one record. Consistent is absent by design.
VERDICTS_REQUIRING_RECORDS: Final[frozenset[str]] = frozenset(
    {
        VERDICT_DECLARED_NOT_IN_POLICY,
        VERDICT_IN_POLICY_NOT_DECLARED,
        VERDICT_CONTRADICTORY,
        VERDICT_UNDETERMINED,
    }
)

# ---------------------------------------------------------------------------
# Audit job states — F-32
# ---------------------------------------------------------------------------

STATUS_QUEUED: Final = "queued"
STATUS_RUNNING: Final = "running"
STATUS_COMPLETED: Final = "completed"
STATUS_FAILED: Final = "failed"

AUDIT_STATUSES: Final[tuple[str, ...]] = (
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_COMPLETED,
    STATUS_FAILED,
)

TERMINAL_STATUSES: Final[frozenset[str]] = frozenset({STATUS_COMPLETED, STATUS_FAILED})

# ---------------------------------------------------------------------------
# Disclosure sources
# ---------------------------------------------------------------------------

SOURCE_DATA_SAFETY: Final = "data_safety"
SOURCE_PRIVACY_POLICY: Final = "privacy_policy"

SOURCE_TYPES: Final[tuple[str, ...]] = (SOURCE_DATA_SAFETY, SOURCE_PRIVACY_POLICY)

# ---------------------------------------------------------------------------
# Learning tasks — model_version.task
# ---------------------------------------------------------------------------

TASK_CLASSIFICATION: Final = "classification"
TASK_SPAN_EXTRACTION: Final = "span_extraction"
TASK_ALIGNMENT: Final = "alignment"

MODEL_TASKS: Final[tuple[str, ...]] = (
    TASK_CLASSIFICATION,
    TASK_SPAN_EXTRACTION,
    TASK_ALIGNMENT,
)

VARIANT_BASELINE: Final = "baseline"
VARIANT_IMPROVED: Final = "improved"

MODEL_VARIANTS: Final[tuple[str, ...]] = (VARIANT_BASELINE, VARIANT_IMPROVED)

# ---------------------------------------------------------------------------
# Extracted span types — F-12
# ---------------------------------------------------------------------------

SPAN_DATA_TYPE: Final = "data_type"
SPAN_PURPOSE: Final = "purpose"

SPAN_TYPES: Final[tuple[str, ...]] = (SPAN_DATA_TYPE, SPAN_PURPOSE)

# ---------------------------------------------------------------------------
# Google Play Data Safety categories (fourteen)
#
# Source: Google Play Console Help, "Provide information for Google Play's Data
# safety section", read 2026-11-04. The names below are Google's, reproduced
# exactly, because a declaration is matched against them.
#
# Deliberately NOT enforced as a database CHECK constraint. Google can revise
# its taxonomy, and if it does, an audit must fail with a clear pipeline error
# that names the unrecognised category (F-33) rather than the database
# rejecting the insert and taking the run down with it. Validation happens at
# the application boundary against this tuple.
# ---------------------------------------------------------------------------

DS_CATEGORIES: Final[tuple[str, ...]] = (
    "Location",
    "Personal info",
    "Financial info",
    "Health and fitness",
    "Messages",
    "Photos and videos",
    "Audio files",
    "Files and docs",
    "Calendar",
    "Contacts",
    "App activity",
    "Web browsing",
    "App info and performance",
    "Device or other IDs",
)

# ---------------------------------------------------------------------------
# OPP-115 annotation categories (ten)
#
# Source: the corpus itself; confirmed against all 23,194 annotated practices
# by ml/data/verify_opp115.py on 2026-11-04. Duplicated from
# ml/data/opp115_schema.py by import rather than by copying, so the two cannot
# drift apart.
# ---------------------------------------------------------------------------


def opp115_categories() -> tuple[str, ...]:
    """The ten OPP-115 categories, imported lazily.

    Lazy because ``analysis`` must remain importable without the ``ml``
    package on the path, which is the case inside the API container.
    """
    from ml.data.opp115_schema import CATEGORIES

    return CATEGORIES


def is_known_ds_category(value: str) -> bool:
    return value in DS_CATEGORIES
