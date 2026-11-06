"""F-12 — data-type and purpose span extraction.

**What is trained, what is rule-based, what is provisional.** Stated up front
because the distinction decides how much weight a result can carry:

======================================  ===================================
part                                    status
======================================  ===================================
BIO tag scheme and token alignment      rule-based, deterministic, tested
Offset translation into M4 coordinates  rule-based, slice-verified
Span decoding from a tag sequence       rule-based, deterministic, tested
The tagger that produces the tags       **trained** — encoder, `ml/train_span_extractor.py`
Confidence threshold (0.50)             **provisional**, never tuned on a gold set
======================================  ===================================

The supervision is real: 23,150 spans extracted from OPP-115 and verified by
slicing (11,913 data type, 11,237 purpose) — see `ml/data/opp115_spans.py`.

**Offsets are the whole point.** A span that cannot be sliced back out of the
canonical cleaned text is not evidence, it is a paraphrase. Every span this
module emits carries offsets into M4's cleaned document text, and
`verify_against` re-slices to prove it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ml.data.opp115_spans import SPAN_TYPES

#: Below this, a span is kept and flagged rather than dropped. PROVISIONAL:
#: Phase 3 requires a configurable threshold and sets no value, and no gold
#: set exists to tune one against.
DEFAULT_SPAN_CONFIDENCE_THRESHOLD = 0.50


@dataclass(frozen=True)
class ExtractedSpan:
    """One span, in the coordinates of the cleaned policy document.

    ``text`` is sliced from that document, never generated. ``abstained`` is
    set when the tagger was below threshold; the span is still returned,
    because discarding it would hide an uncertain finding rather than report
    one.
    """

    span_type: str
    start: int
    end: int
    text: str
    confidence: float
    abstained: bool = False
    #: The OPP-115 attribute value the tagger assigned, such as "Contact" or
    #: "Advertising". Added in M10 and optional by default.
    #:
    #: F-15's rules are keyed on this value, not on the span type: a span of
    #: type ``data_type`` says that the sentence names *some* data, and only
    #: the value says which, so without it no span can reach a Data Safety
    #: category. A tagger trained on span boundaries alone leaves this None
    #: and the span is still valid evidence, just not mappable.
    value: str | None = None

    def __post_init__(self) -> None:
        if self.span_type not in SPAN_TYPES:
            raise ValueError(
                f"unknown span type {self.span_type!r}; expected one of {SPAN_TYPES}"
            )
        if self.start < 0 or self.end <= self.start:
            raise ValueError(f"not a span: start={self.start}, end={self.end}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence {self.confidence} is not a probability")

    def verify_against(self, document_text: str) -> bool:
        """Does this span still slice out of the document it claims to index?

        Called before a span becomes evidence. A False here means the offsets
        and the text have diverged, and the span must not be quoted.
        """
        return document_text[self.start : self.end] == self.text


@dataclass(frozen=True)
class TaggedToken:
    """One token with its predicted BIO tag and the tagger's confidence."""

    token: str
    start: int
    end: int
    tag: str
    confidence: float = 1.0


class SpanTaggerBackend(Protocol):
    """Predicts BIO tags for whitespace tokens.

    Injected so the decoding logic is testable without a checkpoint. The
    transformers-backed implementation lives in `ml/span_backend.py`, the only
    place that imports torch.
    """

    def tag(self, tokens: Sequence[tuple[str, int, int]]) -> list[TaggedToken]:
        ...


def decode_bio(
    tokens: Sequence[TaggedToken],
    document_text: str,
    *,
    offset_shift: int = 0,
    threshold: float = DEFAULT_SPAN_CONFIDENCE_THRESHOLD,
) -> list[ExtractedSpan]:
    """Turn a tag sequence into spans sliced from ``document_text``.

    ``offset_shift`` is the segment's ``char_start`` in the cleaned document,
    so token offsets measured within a segment land in M4's coordinate base.

    An ``I-`` tag with no preceding ``B-`` opens a span rather than being
    dropped. Taggers produce that sequence, and discarding it would lose a
    real span over a formatting detail; the span's confidence still reflects
    the model's uncertainty.
    """
    spans: list[ExtractedSpan] = []
    current_type: str | None = None
    current_value: str | None = None
    current_start = 0
    current_end = 0
    confidences: list[float] = []

    def close() -> None:
        nonlocal current_type, current_value
        if current_type is None:
            return
        start = current_start + offset_shift
        end = current_end + offset_shift
        text = document_text[start:end]
        if text.strip():
            mean = sum(confidences) / len(confidences)
            spans.append(
                ExtractedSpan(
                    span_type=current_type,
                    start=start,
                    end=end,
                    text=text,
                    confidence=mean,
                    abstained=mean < threshold,
                    value=current_value,
                )
            )
        current_type = None
        current_value = None
        confidences.clear()

    for token in tokens:
        tag = token.tag
        if tag == "O":
            close()
            continue
        prefix, _, payload = tag.partition("-")
        # A tag may name the attribute value after a colon, as in
        # "B-data_type:Contact". Plain "B-data_type" remains valid and yields
        # a span with no value: both shapes exist because a boundary-only
        # tagger is still useful as evidence even though F-15 cannot key on it.
        span_type, _, value = payload.partition(":")
        value = value or None
        if span_type not in SPAN_TYPES:
            close()
            continue
        if prefix == "B" or current_type != span_type or current_value != value:
            close()
            current_type = span_type
            current_value = value
            current_start = token.start
        current_end = token.end
        confidences.append(token.confidence)

    close()
    return spans


class SpanExtractor:
    """F-12. Tags a policy segment and returns verifiable spans."""

    def __init__(
        self,
        backend: SpanTaggerBackend,
        threshold: float = DEFAULT_SPAN_CONFIDENCE_THRESHOLD,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold {threshold} is not a probability")
        self._backend = backend
        self.threshold = threshold

    def extract(
        self, segment_text: str, document_text: str, segment_char_start: int
    ) -> list[ExtractedSpan]:
        """Extract spans from one segment, in document coordinates.

        ``segment_text`` must be the slice of ``document_text`` beginning at
        ``segment_char_start``; that is checked rather than trusted, because
        a mismatch would produce offsets that point at the wrong words while
        still looking valid.
        """
        expected = document_text[
            segment_char_start : segment_char_start + len(segment_text)
        ]
        if expected != segment_text:
            raise ValueError(
                "segment_text is not the slice of document_text at "
                f"{segment_char_start}. The offsets would point at the wrong "
                "words, so no spans are returned."
            )

        import re

        tokens = [
            (match.group(), match.start(), match.end())
            for match in re.finditer(r"\S+", segment_text)
        ]
        if not tokens:
            return []

        tagged = self._backend.tag(tokens)
        if len(tagged) != len(tokens):
            raise ValueError(
                f"the backend returned {len(tagged)} tags for {len(tokens)} tokens"
            )

        spans = decode_bio(
            tagged,
            document_text,
            offset_shift=segment_char_start,
            threshold=self.threshold,
        )
        for span in spans:
            if not span.verify_against(document_text):
                raise ValueError(
                    f"span {span.start}:{span.end} does not slice back out of "
                    "the document; it must not be used as evidence"
                )
        return spans


__all__ = [
    "DEFAULT_SPAN_CONFIDENCE_THRESHOLD",
    "ExtractedSpan",
    "SpanExtractor",
    "SpanTaggerBackend",
    "TaggedToken",
    "decode_bio",
]
