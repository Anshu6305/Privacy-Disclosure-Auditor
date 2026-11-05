"""Types for policy text processing (T2).

**The canonical coordinate base.** Every offset in this module refers to the
**cleaned plain text produced by F-08**, not to the raw HTML document. F-09
takes F-08's output as its input, so that is the only text its offsets can
describe.

This matters because F-20 quotes evidence and F-25 highlights it. Both need
the text the offsets index. The cleaned text is therefore written alongside
the raw document in the corpus, and extraction is deterministic so the same
raw document always yields the same cleaned text and the offsets stay valid.

Offsets into the raw HTML would need a character-level map maintained through
tag stripping, entity decoding, Unicode normalisation and whitespace
collapsing. The approved design does not call for one: Phase 3 defines F-09's
input as cleaned text, and §10.4 records that the segmented text is stored so
the pipeline never depends on the raw files. Nothing here changes what an
offset means.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analysis.verdict.models import PolicySegmentRef


@dataclass(frozen=True)
class ExtractionResult:
    """What F-08 produced, and whether it worked.

    Success and failure are distinguished explicitly. An unparseable document
    yields empty text with ``succeeded`` false and a reason, which F-10 then
    turns into a recorded audit failure rather than an empty set of verdicts.
    """

    text: str
    succeeded: bool
    source_sha256: str | None = None
    media_type: str | None = None
    reason: str | None = None
    #: Counts of the structural elements removed, for auditing what was
    #: discarded. Extraction is conservative, and this is how that is checked.
    removed: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.succeeded and not self.text.strip():
            raise ValueError(
                "an extraction that produced no text cannot be marked "
                "successful; set succeeded=False with a reason so F-10 can "
                "record why the audit stopped"
            )
        if not self.succeeded and not self.reason:
            raise ValueError("a failed extraction must carry a reason")

    @property
    def length(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class PolicySegment:
    """One analysis unit, with offsets into the cleaned text (F-09).

    The offset invariant is enforced on construction: ``char_end -
    char_start`` must equal ``len(text)``. If it did not, every quote taken
    from this segment would point somewhere else in the document, and the
    evidence in a report would be wrong in a way no later check could catch.

    ``text`` is the policy's own words, exactly. It is never lowercased,
    re-wrapped, paraphrased or otherwise altered, because F-20 quotes it
    verbatim into the audit report.
    """

    sequence_number: int
    text: str
    char_start: int
    char_end: int
    token_count: int = 0
    #: The nearest preceding heading, when extraction found one. Context for a
    #: reader; never part of the quoted evidence.
    heading: str | None = None

    def __post_init__(self) -> None:
        if self.sequence_number < 0:
            raise ValueError("sequence_number must not be negative")
        if self.char_start < 0:
            raise ValueError(
                f"segment {self.sequence_number}: char_start is negative"
            )
        if self.char_end <= self.char_start:
            raise ValueError(
                f"segment {self.sequence_number}: char_end must exceed char_start"
            )
        span = self.char_end - self.char_start
        if span != len(self.text):
            raise ValueError(
                f"segment {self.sequence_number}: offsets span {span} characters "
                f"but the text is {len(self.text)}. Quotes taken from this "
                f"segment would point at the wrong part of the document."
            )
        if self.token_count < 0:
            raise ValueError("token_count must not be negative")

    def slice_of(self, cleaned_text: str) -> str:
        """The text these offsets actually point at in the given document."""
        return cleaned_text[self.char_start : self.char_end]

    def verify_against(self, cleaned_text: str) -> bool:
        """Whether the offsets locate this exact text in the cleaned document."""
        return self.slice_of(cleaned_text) == self.text

    def to_segment_ref(self, segment_id: int) -> PolicySegmentRef:
        """Convert to the verdict layer's reference type.

        The two carry the same offset invariant, so a segment that is valid
        here is valid there.
        """
        return PolicySegmentRef(
            segment_id=segment_id,
            text=self.text,
            char_start=self.char_start,
            char_end=self.char_end,
        )


@dataclass(frozen=True)
class AnalysabilityThresholds:
    """Minimums a policy must meet to be worth analysing (F-10).

    **These values are provisional.** Phase 2 and Phase 3 require the
    comparison and name the two quantities, but set no numbers. The defaults
    on :data:`PROVISIONAL_THRESHOLDS` are the project's own proposal, chosen
    from the OPP-115 corpus and recorded in
    ``docs/M4_TEXT_PROCESSING_REPORT.md``. They are not an approved
    requirement and must not be reported as one.
    """

    min_segments: int
    min_tokens: int

    def __post_init__(self) -> None:
        if self.min_segments < 1:
            raise ValueError(
                f"min_segments must be at least 1, got {self.min_segments}. A "
                "threshold of zero would accept a document with no text."
            )
        if self.min_tokens < 1:
            raise ValueError(
                f"min_tokens must be at least 1, got {self.min_tokens}. A "
                "threshold of zero would accept a document with no words."
            )


#: Provisional, not approved. See the class docstring and the M4 report.
#:
#: Chosen against the OPP-115 corpus, whose shortest document is
#: ``988_solarviews.com`` at 703 characters in a single segment — a genuine but
#: minimal policy. The thresholds sit below that so a real short policy is
#: still analysed, while an error page or a cookie banner is not.
PROVISIONAL_THRESHOLDS = AnalysabilityThresholds(min_segments=1, min_tokens=50)


@dataclass(frozen=True)
class AnalysabilityResult:
    """Whether a policy can be analysed, and why not when it cannot (F-10)."""

    analysable: bool
    reason: str
    segment_count: int
    token_count: int
    thresholds: AnalysabilityThresholds | None = None

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError(
                "a result must always carry a reason, including a successful "
                "one, so the audit record says why the document was accepted"
            )
