"""Domain objects for acquisition (T1).

These are plain frozen dataclasses with **no database dependency**. That is
deliberate and is what lets Milestone 3A proceed while design decision D-1 —
whether a disclosure snapshot is one row per collection event or one row per
source — remains unresolved.

The unit used throughout is the **single source document**: one Data Safety
declaration, or one privacy policy. That is the smallest unit both D-1 options
can be assembled from. Under the per-source option each becomes a row; under
the collection-event option a pair is grouped into one row. Nothing here
commits to either, and no persistent schema is introduced.

Field names follow the approved Phase 3 vocabulary where one exists. Nothing
is invented: every declaration field below corresponds to something Google's
own documentation states the Data safety section carries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from analysis.vocabulary import DS_CATEGORIES, SOURCE_TYPES

# ---------------------------------------------------------------------------
# Retrieval outcome and provenance (F-07)
# ---------------------------------------------------------------------------

#: How a document reached us.
RETRIEVAL_MODE_MANUAL = "manual_import"
RETRIEVAL_MODE_LIVE = "live_fetch"
RETRIEVAL_MODE_CACHE = "cache"

RETRIEVAL_MODES: tuple[str, ...] = (
    RETRIEVAL_MODE_MANUAL,
    RETRIEVAL_MODE_LIVE,
    RETRIEVAL_MODE_CACHE,
)

#: What happened. A failure is recorded, not discarded: F-33 and the audit
#: report both need to distinguish "nothing was found" from "we could not
#: look", and Phase 1 named scraper breakage the project's likeliest fault.
OUTCOME_SUCCESS = "success"
OUTCOME_NOT_FOUND = "not_found"
OUTCOME_FETCH_FAILED = "fetch_failed"
OUTCOME_PARSE_FAILED = "parse_failed"
OUTCOME_BLOCKED = "blocked"

RETRIEVAL_OUTCOMES: tuple[str, ...] = (
    OUTCOME_SUCCESS,
    OUTCOME_NOT_FOUND,
    OUTCOME_FETCH_FAILED,
    OUTCOME_PARSE_FAILED,
    OUTCOME_BLOCKED,
)


@dataclass(frozen=True)
class Provenance:
    """Where one source document came from and what happened (F-07).

    Deliberately **per source document**, not per collection event, so that it
    can be assembled either way once D-1 is decided.

    ``content_sha256`` is null only when nothing was retrieved. A successful
    outcome without a hash is rejected, because a document we cannot identify
    is not evidence of anything.
    """

    source_type: str
    source_url: str
    retrieved_at: datetime
    retrieval_mode: str
    outcome: str
    content_sha256: str | None = None
    content_bytes: int | None = None
    http_status: int | None = None
    failure_reason: str | None = None
    collector_note: str | None = None

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(
                f"unknown source type {self.source_type!r}; expected one of {SOURCE_TYPES}"
            )
        if self.retrieval_mode not in RETRIEVAL_MODES:
            raise ValueError(
                f"unknown retrieval mode {self.retrieval_mode!r}; expected one of "
                f"{RETRIEVAL_MODES}"
            )
        if self.outcome not in RETRIEVAL_OUTCOMES:
            raise ValueError(
                f"unknown outcome {self.outcome!r}; expected one of {RETRIEVAL_OUTCOMES}"
            )
        if self.outcome == OUTCOME_SUCCESS:
            if not self.content_sha256:
                raise ValueError(
                    "a successful retrieval must record the document hash; a "
                    "document that cannot be identified is not evidence"
                )
            if len(self.content_sha256) != 64:
                raise ValueError("content_sha256 must be a full 64-character SHA-256")
        elif not self.failure_reason:
            raise ValueError(
                f"outcome {self.outcome!r} must record a failure_reason so the "
                "report can distinguish 'nothing found' from 'could not look'"
            )

    @property
    def succeeded(self) -> bool:
        return self.outcome == OUTCOME_SUCCESS


# ---------------------------------------------------------------------------
# Data Safety declaration (F-04)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeclaredDataEntry:
    """One declared data practice.

    Google's documentation states that the section carries, per entry: a data
    type drawn from a fixed category list, whether it is collected or shared
    (declared separately), a purpose from a fixed list, and whether collection
    is optional. Those are the fields here and no others.

    ``is_ephemeral`` records the documented exclusion for data processed only
    on the device or ephemerally, which Google states is not disclosed as
    collected. It is nullable because a listing rarely states it.
    """

    ds_category: str
    data_type: str | None = None
    is_collected: bool = False
    is_shared: bool = False
    purposes: tuple[str, ...] = ()
    is_optional: bool | None = None
    is_ephemeral: bool | None = None
    #: The listing's own wording, kept verbatim so normalisation can be audited.
    raw_label: str | None = None

    def __post_init__(self) -> None:
        if not self.is_collected and not self.is_shared:
            raise ValueError(
                f"{self.ds_category}: an entry must declare collection, sharing or "
                "both. The published section lists only positive declarations, so "
                "an entry asserting neither has no source."
            )


@dataclass(frozen=True)
class SecurityPractices:
    """The security and deletion statements the section carries.

    Every field is nullable. A listing that does not state a practice is not
    the same as one that denies it, and conflating those would misrepresent
    the declaration.
    """

    data_encrypted_in_transit: bool | None = None
    data_deletion_available: bool | None = None
    independent_security_review: bool | None = None
    committed_to_play_families_policy: bool | None = None


@dataclass(frozen=True)
class DataSafetyDeclaration:
    """A normalised Data Safety declaration for one application (F-04).

    ``declares_no_data_collected`` records the app-level statement Google
    publishes when a developer declares the app collects and shares nothing.
    It is a real, distinct state: different from a declaration that merely
    omits a category, and different again from a section we could not read.
    Keeping the three apart is what finding E-2 is about.
    """

    package_name: str
    entries: tuple[DeclaredDataEntry, ...] = ()
    security: SecurityPractices = field(default_factory=SecurityPractices)
    declares_no_data_collected: bool = False
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if self.declares_no_data_collected and self.entries:
            raise ValueError(
                f"{self.package_name}: the declaration states that no data is "
                f"collected or shared, yet carries {len(self.entries)} data "
                "entries. One of the two readings is wrong and the record must "
                "be corrected rather than guessed at."
            )

    @property
    def collected_categories(self) -> tuple[str, ...]:
        return tuple(
            sorted({e.ds_category for e in self.entries if e.is_collected})
        )

    @property
    def shared_categories(self) -> tuple[str, ...]:
        return tuple(sorted({e.ds_category for e in self.entries if e.is_shared}))

    @property
    def declared_categories(self) -> tuple[str, ...]:
        return tuple(sorted({e.ds_category for e in self.entries}))

    def asserts(self, ds_category: str) -> bool:
        """Whether the declaration claims any practice for this category."""
        return ds_category in self.declared_categories


# ---------------------------------------------------------------------------
# Privacy policy document (F-05)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyDocument:
    """A privacy policy document as stored and verified (F-05).

    ``content`` is the file's bytes decoded as text. It is the document as
    retrieved: this class never edits, reformats or cleans it. Extraction and
    segmentation are F-08 and F-09, in Milestone 4, and they read from here.
    """

    package_name: str
    source_url: str
    content: str
    content_sha256: str
    storage_path: str
    media_type: str
    provenance: Provenance | None = None

    @property
    def length(self) -> int:
        return len(self.content)


# ---------------------------------------------------------------------------
# Corpus record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApplicationRecord:
    """One application in the operational corpus.

    This is the **Android application corpus**, not OPP-115. OPP-115 is a
    corpus of website privacy policies used to train the classifier; this is
    the set of Android applications the running system analyses. The two are
    never mixed.
    """

    package_name: str
    app_name: str
    developer_name: str | None = None
    store_category: str | None = None
    play_store_url: str | None = None
    policy_url: str | None = None
    declaration: DataSafetyDeclaration | None = None
    policy_path: str | None = None
    policy_sha256: str | None = None
    collected_at: datetime | None = None
    provenances: tuple[Provenance, ...] = ()
    validation_status: str = "unvalidated"

    @property
    def is_analysable(self) -> bool:
        """Whether both disclosures are present.

        An application missing either one cannot be audited. It is kept in the
        corpus with its provenance so the gap is visible and countable, rather
        than dropped and silently reducing the corpus size.
        """
        return self.declaration is not None and self.policy_sha256 is not None


def is_known_category(value: str) -> bool:
    return value in DS_CATEGORIES
