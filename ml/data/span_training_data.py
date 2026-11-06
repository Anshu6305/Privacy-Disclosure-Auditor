"""F-12 training data: BIO-tagged segments, split by source policy.

Built from the span dataset M6 verified — 23,150 spans whose text matches
`segment_text[start:end]` exactly, 294 rejected and counted rather than
corrected.

**The tag carries the attribute value, not only the span type.** A tag is
``B-data_type:Contact`` rather than ``B-data_type``. F-15's rules are keyed on
the value, so a tagger that learned boundaries alone would produce spans no
rule could ever match. Both shapes decode (`analysis/models/span_extractor.py`),
and only the valued one closes the chain to a Data Safety category.

Data-type and purpose share one tag sequence and one model. They rarely
overlap in the corpus, and where two annotators' highlights do collide the
earliest wins, which is `bio_tags`' existing rule applied across both types
rather than within one.

**The split is M5's**, by policy and with the same seed. Segments from one
policy never cross a boundary: a policy reuses its own phrasing, so splitting
by segment would put near-duplicates of a test segment into training.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ml.data.opp115_spans import (
    DEFAULT_CORPUS,
    SPAN_TYPES,
    LabelledSpan,
    _read_segments,
    read_spans,
)
from ml.data.splits import DEFAULT_PROPORTIONS, DEFAULT_SEED, split_by_policy

OUTSIDE = "O"


@dataclass(frozen=True)
class TaggedSegment:
    """One segment of one policy, tokenised and tagged."""

    policy_id: str
    segment_index: int
    text: str
    tokens: tuple[str, ...]
    offsets: tuple[tuple[int, int], ...]
    tags: tuple[str, ...]

    def __post_init__(self) -> None:
        if not (len(self.tokens) == len(self.offsets) == len(self.tags)):
            raise ValueError(
                f"{self.policy_id}#{self.segment_index}: "
                f"{len(self.tokens)} tokens, {len(self.offsets)} offsets, "
                f"{len(self.tags)} tags"
            )

    @property
    def labels(self) -> tuple[str, ...]:
        """The distinct non-O tags in this segment.

        Named `labels` so `split_by_policy` can report per-label support
        without a second code path. Its reliability warnings are phrased for
        the ten OPP-115 categories and will not recognise these tags; the
        split itself, which is what this reuses, is unaffected.
        """
        return tuple(sorted({tag for tag in self.tags if tag != OUTSIDE}))

    def verify_offsets(self) -> bool:
        """Does every token still slice out of the segment at its offsets?

        Checked before training and again after decoding. An offset that has
        drifted produces a quote the policy does not contain, which is the
        one failure the evidence design exists to prevent.
        """
        return all(
            self.text[start:end] == token
            for token, (start, end) in zip(self.tokens, self.offsets, strict=True)
        )


def tag_label(span_type: str, value: str, prefix: str) -> str:
    return f"{prefix}-{span_type}:{value}"


def tag_segment(
    segment_text: str, spans: list[LabelledSpan]
) -> tuple[list[str], list[tuple[int, int]], list[str]]:
    """Tag one segment across both span types.

    Overlaps are resolved by taking the earliest-starting, longest span, the
    same rule `bio_tags` applies within a type. Applying it across types too
    is necessary because a token cannot begin two spans at once, and the
    alternative — dropping the collision — would silently lose supervision.
    """
    usable = sorted(
        (s for s in spans if s.span_type in SPAN_TYPES and s.value),
        key=lambda s: (s.start, -s.end),
    )
    accepted: list[LabelledSpan] = []
    for span in usable:
        if not accepted or span.start >= accepted[-1].end:
            accepted.append(span)

    tokens: list[str] = []
    offsets: list[tuple[int, int]] = []
    tags: list[str] = []
    for match in re.finditer(r"\S+", segment_text):
        start, end = match.start(), match.end()
        tag = OUTSIDE
        for span in accepted:
            if start >= span.end or end <= span.start:
                continue
            prefix = "B" if start <= span.start else "I"
            tag = tag_label(span.span_type, span.value, prefix)
            break
        tokens.append(match.group())
        offsets.append((start, end))
        tags.append(tag)
    return tokens, offsets, tags


def build_tagged_segments(
    spans: list[LabelledSpan] | None = None,
    corpus: Path | str = DEFAULT_CORPUS,
) -> list[TaggedSegment]:
    """Group the verified spans by segment and tag each segment once.

    The segment text comes from the corpus, not from the span records: a
    span stores offsets into its segment and the text it highlighted, never
    the whole segment. Reading the corpus is also what makes the offset
    check below meaningful, since it compares the tokeniser against the same
    bytes the annotators saw.
    """
    spans = read_spans() if spans is None else spans
    corpus_segments = _read_segments(Path(corpus))

    by_segment: dict[tuple[str, int], list[LabelledSpan]] = {}
    for span in spans:
        by_segment.setdefault((span.policy_id, span.segment_index), []).append(span)

    segments: list[TaggedSegment] = []
    for (policy_id, segment_index), group in sorted(by_segment.items()):
        policy = corpus_segments.get(policy_id)
        if policy is None or segment_index >= len(policy):
            raise ValueError(
                f"{policy_id}#{segment_index} is in the span dataset but not "
                "in the corpus on disk. The two have diverged; rebuild the "
                "span dataset rather than skipping the segment."
            )
        text = policy[segment_index]
        tokens, offsets, tags = tag_segment(text, group)
        if not tokens:
            continue
        segment = TaggedSegment(
            policy_id=policy_id,
            segment_index=segment_index,
            text=text,
            tokens=tuple(tokens),
            offsets=tuple(offsets),
            tags=tuple(tags),
        )
        if not segment.verify_offsets():
            raise ValueError(
                f"{policy_id}#{segment_index}: a token does not slice out of "
                "its segment. The dataset and the tokeniser disagree, and "
                "training on it would learn wrong offsets."
            )
        segments.append(segment)
    return segments


def read_jsonl(path: Path | str) -> list[TaggedSegment]:
    """Load tagged segments written by `write_jsonl`.

    This is how a GPU notebook gets the data: the OPP-115 corpus is not
    uploaded, only the derived tags. Offsets are re-verified on load, so a
    file damaged in transit fails here rather than training a model on
    offsets that point at the wrong words.
    """
    import json

    segments: list[TaggedSegment] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            segment = TaggedSegment(
                policy_id=record["policy_id"],
                segment_index=record["segment_index"],
                text=record["text"],
                tokens=tuple(record["tokens"]),
                offsets=tuple((a, b) for a, b in record["offsets"]),
                tags=tuple(record["tags"]),
            )
            if not segment.verify_offsets():
                raise ValueError(
                    f"{segment.policy_id}#{segment.segment_index}: offsets do "
                    "not slice out of the text. Re-export the bundle."
                )
            segments.append(segment)
    return segments


def label_set(segments: list[TaggedSegment]) -> list[str]:
    """Every tag that occurs, with O first so it keeps index 0.

    Derived from the data rather than declared, so a value that appears in
    the corpus and not in a hand-written list cannot be silently dropped.
    """
    found = {tag for segment in segments for tag in segment.tags}
    found.discard(OUTSIDE)
    return [OUTSIDE, *sorted(found)]


def split_segments(
    segments: list[TaggedSegment],
    seed: int = DEFAULT_SEED,
    proportions=DEFAULT_PROPORTIONS,
):
    """M5's policy-level split, applied to the tagged segments."""
    # `split_by_policy` reads `.policy_id`, `.segment_index` and `.labels`,
    # all of which TaggedSegment provides. Reusing it rather than writing a
    # second splitter is the point: F-12 must land on exactly the policy
    # boundaries M5 used, or the two models' held-out figures would not be
    # comparable and a test policy for one could be a training policy for
    # the other.
    return split_by_policy(segments, proportions, seed)


def write_jsonl(segments: list[TaggedSegment], path: Path | str) -> Path:
    """Write the tagged segments so a GPU notebook can train from one file."""
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for segment in segments:
            handle.write(
                json.dumps(
                    {
                        "policy_id": segment.policy_id,
                        "segment_index": segment.segment_index,
                        "text": segment.text,
                        "tokens": list(segment.tokens),
                        "offsets": [list(pair) for pair in segment.offsets],
                        "tags": list(segment.tags),
                    }
                )
                + "\n"
            )
    return path


__all__ = [
    "OUTSIDE",
    "TaggedSegment",
    "build_tagged_segments",
    "label_set",
    "read_jsonl",
    "split_segments",
    "tag_label",
    "tag_segment",
    "write_jsonl",
]
