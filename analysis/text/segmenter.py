"""F-09 — segment cleaned policy text into ordered, quotable units (ALG-1).

**Offsets index the cleaned text that F-08 produced.** That is the canonical
coordinate base for the whole project, and it is stated here because the value
of an offset depends entirely on which document it counts characters in. The
cleaned text is stored alongside the raw document so a reader following an
offset arrives at the sentence the report quoted.

The segmentation itself is deliberately unclever:

1. Split on paragraph breaks, which F-08 writes as exactly two newlines.
2. Keep a paragraph whole when it fits the size limit.
3. Split an over-long paragraph at **sentence boundaries only**, never
   mid-sentence, so no segment ever cuts a sentence in half.

Sentence boundaries come from spaCy, as the approved design specifies, which
is what handles "e.g.", "Inc." and "U.S." without splitting after the full
stop.

**Nothing here alters the text.** Every segment's text is a verbatim slice of
the cleaned document, obtained by slicing it — not by reassembling tokens.
That is enforced on construction by :class:`PolicySegment`, which refuses to
exist unless its offsets span exactly its text, and it is what lets F-20 quote
and F-25 highlight.

Complexity: O(n) over the cleaned text, in a single pass per paragraph.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from analysis.text.models import PolicySegment

#: Paragraph boundary, exactly as F-08 writes it.
_PARAGRAPH_BREAK = re.compile(r"\n\n")

#: The model the approved design calls for. Pinned so segmentation is
#: reproducible: a different model would place sentence boundaries differently
#: and the same policy would yield different segments on different machines,
#: which NFR-08 does not allow.
SPACY_MODEL = "en_core_web_sm"

#: Above this many characters a paragraph is split at sentence boundaries.
#: Provisional, not an approved requirement. Chosen so a segment stays within
#: the 512-token input limit of the encoder models under consideration for
#: F-11, with room for sub-word expansion. Recorded in the M4 report.
DEFAULT_MAX_SEGMENT_CHARS = 1000

#: A heading is a short line with no terminal punctuation. Used only to label
#: a segment for a human reader; it never becomes part of quoted evidence.
_HEADING_MAX_CHARS = 80
_SENTENCE_END = re.compile(r"[.!?:;]\s*$")


class SegmenterUnavailableError(RuntimeError):
    """spaCy or its model is not installed.

    Raised rather than silently falling back to a simpler splitter. A fallback
    would place sentence boundaries differently, so the same policy would
    segment differently depending on what happened to be installed, and two
    team members would get different evidence offsets for the same document.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"{detail}\n"
            f"  F-09 uses spaCy sentence boundaries, as the approved design "
            f"specifies. Install them with:\n"
            f"      pip install -r backend/requirements.txt\n"
            f"      python -m spacy download {SPACY_MODEL}\n"
            f"  There is deliberately no fallback splitter: a different "
            f"splitter would move sentence boundaries, and the same policy "
            f"would then produce different segments and different evidence "
            f"offsets on different machines."
        )


@lru_cache(maxsize=2)
def load_sentencizer(model: str = SPACY_MODEL) -> Any:
    """Load spaCy with only what sentence splitting needs.

    The parser, tagger and named-entity components are disabled: F-09 needs
    sentence boundaries and nothing else, and loading the rest would cost
    memory the design budget assigns to the classifier.
    """
    try:
        import spacy
    except ImportError as exc:
        raise SegmenterUnavailableError(f"spaCy is not installed ({exc}).") from exc

    try:
        nlp = spacy.load(model, exclude=["ner", "lemmatizer", "textcat"])
    except OSError as exc:
        raise SegmenterUnavailableError(
            f"The spaCy model {model!r} is not installed ({exc})."
        ) from exc

    if "senter" not in nlp.pipe_names and "parser" not in nlp.pipe_names:
        nlp.add_pipe("sentencizer")
    return nlp


def _paragraph_spans(text: str) -> Iterator[tuple[int, int]]:
    """(start, end) of each paragraph in the cleaned text.

    Spans are computed from the text itself so they are offsets into it, not
    into a reconstruction of it.
    """
    cursor = 0
    for match in _PARAGRAPH_BREAK.finditer(text):
        if match.start() > cursor:
            yield cursor, match.start()
        cursor = match.end()
    if cursor < len(text):
        yield cursor, len(text)


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Narrow a span past surrounding whitespace, or None if it is all space.

    Trimming by moving the offsets, rather than by calling ``strip()`` on a
    copy, is what keeps the offsets and the text in agreement.
    """
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if end > start else None


def _looks_like_heading(fragment: str) -> bool:
    return (
        len(fragment) <= _HEADING_MAX_CHARS
        and "\n" not in fragment
        and not _SENTENCE_END.search(fragment)
    )


def _sentence_spans(nlp: Any, text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Sentence spans within a paragraph, as offsets into the whole text."""
    doc = nlp(text[start:end])
    spans = []
    for sentence in doc.sents:
        trimmed = _trimmed_span(text, start + sentence.start_char, start + sentence.end_char)
        if trimmed is not None:
            spans.append(trimmed)
    return spans


def _group_sentences(
    spans: list[tuple[int, int]], max_chars: int
) -> list[tuple[int, int]]:
    """Greedily merge consecutive sentences up to the size limit.

    Consecutive, so order is preserved and no sentence is skipped or repeated.
    A single sentence longer than the limit is kept whole: splitting it would
    cut a sentence in half, and a half-sentence is not quotable evidence.
    """
    if not spans:
        return []

    groups: list[tuple[int, int]] = []
    group_start, group_end = spans[0]

    for span_start, span_end in spans[1:]:
        if span_end - group_start <= max_chars:
            group_end = span_end
        else:
            groups.append((group_start, group_end))
            group_start, group_end = span_start, span_end

    groups.append((group_start, group_end))
    return groups


def segment_policy_text(
    cleaned_text: str,
    max_segment_chars: int = DEFAULT_MAX_SEGMENT_CHARS,
    nlp: Any | None = None,
    count_tokens: bool = True,
) -> list[PolicySegment]:
    """Split cleaned policy text into ordered segments with offsets.

    Returns an empty list for empty or whitespace-only input, which F-10 then
    reports as not analysable. That is the documented path: Phase 3 states
    that no sentences produces an empty list handled by F-10.

    Every returned segment satisfies ``cleaned_text[s.char_start:s.char_end]
    == s.text``.
    """
    if max_segment_chars < 1:
        raise ValueError("max_segment_chars must be at least 1")

    if not cleaned_text or not cleaned_text.strip():
        return []

    engine = nlp if nlp is not None else load_sentencizer()

    segments: list[PolicySegment] = []
    current_heading: str | None = None
    sequence = 0

    for raw_start, raw_end in _paragraph_spans(cleaned_text):
        trimmed = _trimmed_span(cleaned_text, raw_start, raw_end)
        if trimmed is None:
            continue
        start, end = trimmed
        fragment = cleaned_text[start:end]

        # A heading becomes a segment in its own right and also labels the
        # segments that follow. It is kept rather than dropped because a
        # heading such as "Information we share with third parties" is itself
        # a statement about a data practice.
        if _looks_like_heading(fragment):
            current_heading = fragment

        if end - start <= max_segment_chars:
            spans = [(start, end)]
        else:
            sentence_spans = _sentence_spans(engine, cleaned_text, start, end)
            spans = _group_sentences(sentence_spans, max_segment_chars) or [(start, end)]

        for span_start, span_end in spans:
            text = cleaned_text[span_start:span_end]
            segments.append(
                PolicySegment(
                    sequence_number=sequence,
                    text=text,
                    char_start=span_start,
                    char_end=span_end,
                    token_count=count_tokens_in(text, engine) if count_tokens else 0,
                    heading=current_heading,
                )
            )
            sequence += 1

    return segments


def count_tokens_in(text: str, nlp: Any | None = None) -> int:
    """Token count using the same tokeniser that found the sentences.

    F-10 compares a total token count against a threshold, so the count has to
    mean one definite thing. Using the segmentation tokeniser keeps the number
    consistent with the segments it describes.
    """
    engine = nlp if nlp is not None else load_sentencizer()
    return sum(1 for token in engine.tokenizer(text) if not token.is_space)


def verify_segments(cleaned_text: str, segments: list[PolicySegment]) -> list[str]:
    """Check the guarantees F-09 must provide. Empty list means all hold.

    Used by the tests and available to a caller that wants to assert them in
    production. The checks are: offsets locate the exact text; sequence
    numbers are consecutive from zero; segments are ordered and do not
    overlap; and no non-whitespace character of the document is lost or
    counted twice.
    """
    problems: list[str] = []

    for index, segment in enumerate(segments):
        if not segment.verify_against(cleaned_text):
            problems.append(
                f"segment {segment.sequence_number}: offsets do not locate its text"
            )
        if segment.sequence_number != index:
            problems.append(
                f"position {index} carries sequence_number {segment.sequence_number}"
            )

    for earlier, later in zip(segments, segments[1:], strict=False):
        if later.char_start < earlier.char_end:
            problems.append(
                f"segments {earlier.sequence_number} and {later.sequence_number} overlap"
            )

    covered = sum(
        1
        for index, character in enumerate(cleaned_text)
        if not character.isspace()
        and any(s.char_start <= index < s.char_end for s in segments)
    )
    total = sum(1 for character in cleaned_text if not character.isspace())
    if covered != total:
        problems.append(
            f"{total - covered} non-whitespace characters are in no segment; "
            f"text would be missing from the analysis"
        )

    return problems
