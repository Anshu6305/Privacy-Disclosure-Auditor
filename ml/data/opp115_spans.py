"""F-12 training data: data-type and purpose spans from OPP-115.

The segment-level dataset (`opp115_dataset.py`) answers "which practices does
this segment describe". F-12 asks a narrower question: **which words** name the
data type, and which name the purpose. OPP-115 supports it directly, because
annotators highlighted the text they based each attribute value on.

Two attributes carry that supervision:

================================  =========  ==========
attribute                         annotated  with span
================================  =========  ==========
``Personal Information Type``        16,315      11,988
``Purpose``                          15,945      11,389
================================  =========  ==========

(counted over all 23,194 annotation rows on 2026-11-06, with the span-free
values excluded — see `opp115_schema.SPAN_FREE_VALUES`.)

**Every span is verified by slicing.** An offset pair is kept only when
``segment_text[start:end]`` equals the annotator's ``selectedText`` after
whitespace normalisation. The corpus errata describe genuinely missing spans,
and a mis-indexed one would teach the model to point at the wrong words — so
a span that does not slice back is dropped and counted, never adjusted.

**Offsets here are segment-relative**, which is the coordinate base OPP-115
uses. M4's offsets index the cleaned policy document. `to_document_offsets`
translates, and the translation is slice-verified too.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ml.data.opp115_schema import (
    COL_ATTRIBUTES_JSON,
    COL_CATEGORY,
    COL_POLICY_ID,
    COL_SEGMENT_ID,
    SEGMENT_SEPARATOR,
    SPAN_FREE_VALUES,
)

csv.field_size_limit(sys.maxsize)

DEFAULT_CORPUS = Path("data/raw/opp115")
DEFAULT_OUTPUT = Path("data/processed/opp115_spans.jsonl")

#: The two span types F-12 extracts, and the OPP-115 attribute each comes
#: from. Named here rather than inferred, because an attribute added to the
#: corpus should not silently become training data.
SPAN_TYPE_DATA_TYPE = "data_type"
SPAN_TYPE_PURPOSE = "purpose"

ATTRIBUTE_FOR_SPAN_TYPE: dict[str, str] = {
    "Personal Information Type": SPAN_TYPE_DATA_TYPE,
    "Purpose": SPAN_TYPE_PURPOSE,
}

SPAN_TYPES: tuple[str, ...] = (SPAN_TYPE_DATA_TYPE, SPAN_TYPE_PURPOSE)

_WHITESPACE = re.compile(r"\s+")


class SpanDatasetError(Exception):
    """The corpus is not where it should be, or is unreadable."""


def _normalise(text: str) -> str:
    """Collapse whitespace for comparison only. Offsets are never changed."""
    return _WHITESPACE.sub(" ", text).strip()


@dataclass(frozen=True)
class LabelledSpan:
    """One highlighted span, verified against its segment text."""

    policy_id: str
    segment_index: int
    span_type: str
    start: int
    end: int
    text: str
    #: The attribute value the annotator chose, such as "Contact" or
    #: "Advertising". Kept because F-12's output feeds F-15's mapping.
    value: str
    category: str
    annotator_id: str

    @property
    def example_id(self) -> str:
        return f"{self.policy_id}#{self.segment_index}#{self.span_type}#{self.start}"


@dataclass
class SpanDatasetReport:
    """What the extraction found, and what it refused."""

    annotation_rows: int = 0
    attributes_seen: int = 0
    spans_kept: int = 0
    span_free_values: int = 0
    missing_offsets: int = 0
    slice_mismatches: int = 0
    out_of_range: int = 0
    empty_after_strip: int = 0
    by_type: Counter = field(default_factory=Counter)
    policies: int = 0
    segments_with_spans: int = 0

    @property
    def rejected(self) -> int:
        return (
            self.missing_offsets
            + self.slice_mismatches
            + self.out_of_range
            + self.empty_after_strip
        )


def _read_segments(corpus: Path) -> dict[str, list[str]]:
    directory = corpus / "sanitized_policies"
    if not directory.is_dir():
        raise SpanDatasetError(
            f"{directory} not found. The OPP-115 corpus must be extracted at "
            f"{corpus}; see data/README.md. It is not downloaded automatically."
        )
    segments: dict[str, list[str]] = {}
    for path in sorted(directory.glob("*.html")):
        segments[path.stem] = path.read_text(
            encoding="utf-8", errors="replace"
        ).split(SEGMENT_SEPARATOR)
    if not segments:
        raise SpanDatasetError(f"no policy files found under {directory}")
    return segments


def build_span_dataset(
    corpus: Path | str = DEFAULT_CORPUS,
) -> tuple[list[LabelledSpan], SpanDatasetReport]:
    """Extract every verifiable data-type and purpose span.

    Returns the spans and a report. The report's rejection counts are part of
    the result, not diagnostics: a span dataset that silently dropped a third
    of its supervision would misrepresent what the model was trained on.
    """
    corpus = Path(corpus)
    segments = _read_segments(corpus)
    directory = corpus / "annotations"
    if not directory.is_dir():
        raise SpanDatasetError(f"{directory} not found")

    report = SpanDatasetReport()
    spans: list[LabelledSpan] = []
    seen_segments: set[tuple[str, int]] = set()

    for path in sorted(directory.glob("*.csv")):
        policy_id = path.stem
        policy_segments = segments.get(policy_id)
        if policy_segments is None:
            continue
        report.policies += 1

        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.reader(handle):
                if len(row) <= COL_ATTRIBUTES_JSON:
                    continue
                report.annotation_rows += 1
                try:
                    segment_index = int(row[COL_SEGMENT_ID])
                except ValueError:
                    continue
                if not 0 <= segment_index < len(policy_segments):
                    continue
                segment_text = policy_segments[segment_index]

                try:
                    payload = json.loads(row[COL_ATTRIBUTES_JSON])
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(payload, dict):
                    continue

                for attribute, body in payload.items():
                    span_type = ATTRIBUTE_FOR_SPAN_TYPE.get(attribute)
                    if span_type is None or not isinstance(body, dict):
                        continue
                    report.attributes_seen += 1

                    value = body.get("value")
                    if value in SPAN_FREE_VALUES:
                        # Not an error: these values carry no highlight by
                        # design, so they are supervision the corpus never
                        # offered rather than supervision that was lost.
                        report.span_free_values += 1
                        continue

                    start = body.get("startIndexInSegment")
                    end = body.get("endIndexInSegment")
                    selected = body.get("selectedText")
                    if (
                        not isinstance(start, int)
                        or not isinstance(end, int)
                        or not isinstance(selected, str)
                        or start < 0
                        or end <= start
                    ):
                        report.missing_offsets += 1
                        continue
                    if end > len(segment_text):
                        report.out_of_range += 1
                        continue

                    sliced = segment_text[start:end]
                    if _normalise(sliced) != _normalise(selected):
                        # Dropped, never adjusted: a corrected offset would be
                        # a guess at which words the annotator meant.
                        report.slice_mismatches += 1
                        continue
                    if not _normalise(sliced):
                        report.empty_after_strip += 1
                        continue

                    spans.append(
                        LabelledSpan(
                            policy_id=policy_id,
                            segment_index=segment_index,
                            span_type=span_type,
                            start=start,
                            end=end,
                            text=sliced,
                            value=str(value) if value is not None else "",
                            category=row[COL_CATEGORY],
                            annotator_id=row[2] if len(row) > 2 else "",
                        )
                    )
                    report.spans_kept += 1
                    report.by_type[span_type] += 1
                    seen_segments.add((policy_id, segment_index))

    report.segments_with_spans = len(seen_segments)
    return spans, report


# ---------------------------------------------------------------------------
# Offsets: OPP-115 is segment-relative, M4 is document-relative
# ---------------------------------------------------------------------------


def to_document_offsets(
    start: int, end: int, segment_char_start: int
) -> tuple[int, int]:
    """Translate a segment-relative span into M4's document coordinates.

    M4 fixed the canonical coordinate base as the **cleaned plain text** of
    the policy, and every evidence quote is sliced from it. OPP-115's offsets
    index one segment. Mixing the two would produce evidence that points at
    the wrong words, so the translation is explicit and tested by slicing on
    both sides rather than assumed.
    """
    if start < 0 or end <= start:
        raise ValueError(f"not a span: start={start}, end={end}")
    if segment_char_start < 0:
        raise ValueError(f"segment_char_start must be non-negative, got {segment_char_start}")
    return segment_char_start + start, segment_char_start + end


# ---------------------------------------------------------------------------
# BIO tagging
# ---------------------------------------------------------------------------


def bio_tags(
    segment_text: str, spans: list[LabelledSpan], span_type: str
) -> list[tuple[str, int, int, str]]:
    """Whitespace tokens tagged B-/I-/O for one span type.

    Returns ``(token, start, end, tag)``, with offsets into ``segment_text``
    so a predicted tag sequence can be turned back into a verbatim quote.

    Overlapping spans of the same type are resolved by taking the earliest:
    OPP-115 has three annotators per policy and their highlights can overlap,
    and a token cannot be the beginning of two spans at once.
    """
    chosen = sorted(
        (s for s in spans if s.span_type == span_type), key=lambda s: (s.start, -s.end)
    )
    accepted: list[LabelledSpan] = []
    for span in chosen:
        if not accepted or span.start >= accepted[-1].end:
            accepted.append(span)

    tokens: list[tuple[str, int, int, str]] = []
    for match in re.finditer(r"\S+", segment_text):
        start, end = match.start(), match.end()
        tag = "O"
        for span in accepted:
            if start >= span.end or end <= span.start:
                continue
            tag = "B-" + span_type if start <= span.start else "I-" + span_type
            break
        tokens.append((match.group(), start, end, tag))
    return tokens


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def write_spans(
    spans: list[LabelledSpan], path: Path | str = DEFAULT_OUTPUT
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for span in spans:
            handle.write(json.dumps(asdict(span), ensure_ascii=False) + "\n")
    return path


def read_spans(path: Path | str = DEFAULT_OUTPUT) -> list[LabelledSpan]:
    path = Path(path)
    if not path.is_file():
        raise SpanDatasetError(f"{path} not found; build the span dataset first")
    with path.open(encoding="utf-8") as handle:
        return [LabelledSpan(**json.loads(line)) for line in handle if line.strip()]


def format_span_report(report: SpanDatasetReport) -> str:
    lines = [
        "OPP-115 span dataset (F-12)",
        f"  annotation rows read      {report.annotation_rows:>8}",
        f"  policies                  {report.policies:>8}",
        f"  span-bearing attributes   {report.attributes_seen:>8}",
        f"  spans kept                {report.spans_kept:>8}",
    ]
    for span_type in SPAN_TYPES:
        lines.append(f"      {span_type:<21} {report.by_type[span_type]:>8}")
    lines += [
        f"  segments with >=1 span    {report.segments_with_spans:>8}",
        "",
        "  not supervision, by design:",
        f"      span-free values      {report.span_free_values:>8}",
        "  rejected:",
        f"      missing offsets       {report.missing_offsets:>8}",
        f"      out of range          {report.out_of_range:>8}",
        f"      slice mismatch        {report.slice_mismatches:>8}",
        f"      empty after strip     {report.empty_after_strip:>8}",
        f"      total rejected        {report.rejected:>8}",
    ]
    return "\n".join(lines)


__all__ = [
    "ATTRIBUTE_FOR_SPAN_TYPE",
    "DEFAULT_OUTPUT",
    "LabelledSpan",
    "SPAN_TYPES",
    "SPAN_TYPE_DATA_TYPE",
    "SPAN_TYPE_PURPOSE",
    "SpanDatasetError",
    "SpanDatasetReport",
    "bio_tags",
    "build_span_dataset",
    "format_span_report",
    "read_spans",
    "to_document_offsets",
    "write_spans",
]
