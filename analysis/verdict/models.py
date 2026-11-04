"""Domain types for the verdict and evidence engine.

These are plain frozen dataclasses with no database or web dependency, so the
whole engine can be reasoned about and tested on its own.

One design point is worth reading before the rest: **abstention propagation is
structural here, not a step someone has to remember.** An
:class:`AlignmentJudgement` stores what the model reported
(``model_abstained``) but exposes ``abstained`` as a property that is also true
whenever the candidate it came from was already uncertain. There is no way to
construct a judgement that looks confident while resting on an uncertain
upstream prediction, because the propagation happens in the type rather than in
a function that could be skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analysis.vocabulary import (
    ALIGN_CONTRADICTS,
    ALIGN_NO_MATCH,
    ALIGN_SUPPORTS,
    ALIGNMENT_LABELS,
    RECORD_TYPES,
    VERDICTS,
)

# ---------------------------------------------------------------------------
# Policy side
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicySegmentRef:
    """A segment of privacy policy text and its offsets in the document.

    ``char_end - char_start`` must equal ``len(text)``. If the offsets do not
    describe this exact text then every evidence quote taken from the segment
    would point somewhere else in the document, so the invariant is checked
    rather than assumed.
    """

    segment_id: int
    text: str
    char_start: int
    char_end: int

    def __post_init__(self) -> None:
        if self.char_start < 0:
            raise ValueError(f"segment {self.segment_id}: char_start is negative")
        if self.char_end <= self.char_start:
            raise ValueError(
                f"segment {self.segment_id}: char_end must be greater than char_start"
            )
        expected = self.char_end - self.char_start
        if expected != len(self.text):
            raise ValueError(
                f"segment {self.segment_id}: offsets span {expected} characters but "
                f"the text is {len(self.text)} characters. Evidence offsets taken "
                f"from this segment would be wrong."
            )


@dataclass(frozen=True)
class PolicyPractice:
    """A data practice found in one policy segment.

    Produced by F-11 and F-12 and passed through the confidence gate (F-14).
    ``abstained`` means the prediction fell below threshold: the practice is
    kept and flagged, never discarded, so the uncertainty can travel downstream.
    """

    practice_id: int
    segment: PolicySegmentRef
    opp115_category: str
    confidence: float
    abstained: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"practice {self.practice_id}: confidence {self.confidence} is not a "
                "probability"
            )


@dataclass(frozen=True)
class MappedPolicyPractice:
    """A policy practice after rule-based taxonomy mapping (F-15).

    ``abstained`` is carried from the source practice. F-15 is a deterministic
    lookup and never introduces or removes uncertainty of its own; it only
    passes along what F-14 decided.
    """

    practice: PolicyPractice
    ds_category: str
    is_partial: bool = False

    @property
    def abstained(self) -> bool:
        return self.practice.abstained

    @property
    def segment(self) -> PolicySegmentRef:
        return self.practice.segment


# ---------------------------------------------------------------------------
# Declaration side
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeclaredItem:
    """One line of a Data Safety declaration."""

    declared_practice_id: int
    ds_category: str
    data_type: str | None = None
    is_collected: bool = False
    is_shared: bool = False

    @property
    def asserts_practice(self) -> bool:
        """Whether this line claims the app does anything with the data.

        A line that declares neither collection nor sharing asserts nothing,
        and must not be treated as a declaration of the category.
        """
        return self.is_collected or self.is_shared


@dataclass(frozen=True)
class DeclarationState:
    """What the declaration says about one Data Safety category (F-16)."""

    ds_category: str
    items: tuple[DeclaredItem, ...] = ()

    @property
    def declared(self) -> bool:
        return any(item.asserts_practice for item in self.items)


# ---------------------------------------------------------------------------
# Cross-source pairing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlignmentCandidate:
    """A pair put forward for comparison by F-17.

    At least one side must be present. A candidate with neither a declared item
    nor a policy practice would be a comparison about nothing, which is also
    what the ``ck_judgement_has_at_least_one_side`` database constraint
    prevents.
    """

    ds_category: str
    declared_item: DeclaredItem | None = None
    mapped_practice: MappedPolicyPractice | None = None

    def __post_init__(self) -> None:
        if self.declared_item is None and self.mapped_practice is None:
            raise ValueError(
                f"{self.ds_category}: a candidate needs a declared item, a policy "
                "practice, or both"
            )

    @property
    def abstained_upstream(self) -> bool:
        """True when the policy practice in this pair was itself uncertain."""
        return self.mapped_practice is not None and self.mapped_practice.abstained

    @property
    def segment(self) -> PolicySegmentRef | None:
        return None if self.mapped_practice is None else self.mapped_practice.segment


@dataclass(frozen=True)
class AlignmentJudgement:
    """One decision about one candidate pair.

    Produced by F-18, which belongs to Milestone 6 and does not exist yet. The
    verdict engine consumes these; in the current codebase they come only from
    controlled test fixtures.

    ``abstained`` is deliberately a property rather than a stored field. It is
    true when the alignment model itself was below threshold **or** when the
    candidate already carried an uncertain policy practice. That OR is the
    abstention propagation rule, and putting it here means no caller can
    produce a confident-looking judgement that rests on an uncertain input.
    """

    candidate: AlignmentCandidate
    label: str
    confidence: float
    model_abstained: bool = False

    def __post_init__(self) -> None:
        if self.label not in ALIGNMENT_LABELS:
            raise ValueError(
                f"unknown alignment label {self.label!r}; expected one of "
                f"{ALIGNMENT_LABELS}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence {self.confidence} is not a probability")

    @property
    def abstained(self) -> bool:
        return self.model_abstained or self.candidate.abstained_upstream

    @property
    def ds_category(self) -> str:
        return self.candidate.ds_category

    @property
    def is_decisive(self) -> bool:
        """A judgement the engine may act on: trusted and not a non-match.

        An abstained judgement is never decisive whatever its label, because
        the label is exactly what the system does not trust.
        """
        return not self.abstained and self.label in (ALIGN_SUPPORTS, ALIGN_CONTRADICTS)

    @property
    def is_decisive_support(self) -> bool:
        return not self.abstained and self.label == ALIGN_SUPPORTS

    @property
    def is_decisive_contradiction(self) -> bool:
        return not self.abstained and self.label == ALIGN_CONTRADICTS

    @property
    def is_decisive_no_match(self) -> bool:
        return not self.abstained and self.label == ALIGN_NO_MATCH


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceRecord:
    """Support for a verdict: a verbatim quote, an absence, or an abstention.

    The validation here mirrors the CHECK constraints on ``evidence_record`` so
    that an invalid record is rejected at the point it is built, where the
    error is readable, rather than at insert time.
    """

    record_type: str
    reason: str | None = None
    segment_id: int | None = None
    quoted_text: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    judgement_label: str | None = None
    judgement_confidence: float | None = None
    display_order: int = 0

    def __post_init__(self) -> None:
        if self.record_type not in RECORD_TYPES:
            raise ValueError(
                f"unknown record type {self.record_type!r}; expected one of "
                f"{RECORD_TYPES}"
            )

        if self.record_type == "evidence":
            if not self.quoted_text:
                raise ValueError("an evidence record must carry quoted policy text")
            if self.segment_id is None:
                raise ValueError("an evidence record must name the segment it came from")
            if self.char_start is None or self.char_end is None:
                raise ValueError("an evidence record must carry character offsets")
            if self.char_end <= self.char_start:
                raise ValueError("evidence offsets must be ordered")
            if self.char_end - self.char_start != len(self.quoted_text):
                raise ValueError(
                    "evidence offsets do not match the length of the quoted text"
                )

        if self.record_type == "absence":
            if self.quoted_text is not None:
                raise ValueError(
                    "an absence record cannot quote text: the finding is that nothing "
                    "was found"
                )
            if not self.reason:
                raise ValueError("an absence record must state why nothing was found")

        if self.record_type == "inconclusive" and not self.reason:
            raise ValueError(
                "an inconclusive record must state why the system abstained"
            )


@dataclass(frozen=True)
class CategoryVerdict:
    """The outcome for one Data Safety category.

    ``consistency_basis`` keeps the two kinds of Consistent apart. Both are
    genuinely consistent, but they mean different things to a reader: one is
    affirmative agreement between the two sources, the other is that neither
    source mentions the category at all. The report must not present them as
    the same finding.

    It is derived from ``declared`` and ``found_in_policy``, which the database
    already stores, so recording it needs no schema change.
    """

    ds_category: str
    verdict: str
    declared: bool
    found_in_policy: bool
    abstention_involved: bool = False
    records: tuple[EvidenceRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ValueError(
                f"unknown verdict {self.verdict!r}; expected one of {VERDICTS}"
            )

    @property
    def consistency_basis(self) -> str | None:
        """Why this category is Consistent, or None when it is not."""
        if self.verdict != "Consistent":
            return None
        if self.declared and self.found_in_policy:
            return "affirmative_agreement"
        return "neither_source_mentions"
