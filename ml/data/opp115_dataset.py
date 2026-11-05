"""Build segment-level multi-label training data from OPP-115 (FR-11).

**The labelled unit is an OPP-115 segment.** The corpus divides each policy
into segments, annotators read them one at a time, and every annotation record
names the segment it came from. Those segments are therefore the only unit the
annotations can support, and this module does not invent a different one.

That is not the same unit F-09 produces at inference time, and the difference
is a real limitation recorded in ``docs/M5_BASELINE_CLASSIFIER_REPORT.md``.

**Negative labels are justified, not assumed.** A category absent from a
segment is treated as a negative because every segment of all 115 policies was
read by all three annotators — verified directly against the corpus, with zero
uncovered segments and no segment identifier outside the range of its policy's
text. Had any segment gone unread, absence would have been ambiguous and this
construction would not have been defensible.

**Label rule: majority vote, at least two of three annotators.** Measured on
the corpus:

===================  ====================  ==================
rule                 segments with no      mean labels per
                     label                 segment
===================  ====================  ==================
any annotator (>=1)  0 (0.0%)              1.70
majority (>=2)       63 (1.7%)             1.18
unanimous (3)        909 (24.0%)           0.80
===================  ====================  ==================

Majority discards single-annotator readings that the other two did not see,
while keeping 98.3% of segments labelled. Unanimous would throw away a quarter
of the corpus; any-annotator would train on every disagreement.

Deterministic: files are read in sorted order and no randomness is involved,
so the same corpus always produces the same dataset.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ml.data.opp115_schema import (
    CATEGORIES,
    EXPECTED_COLUMN_COUNT,
    SEGMENT_SEPARATOR,
)

DEFAULT_CORPUS = Path("data/raw/opp115")
DEFAULT_OUTPUT = Path("data/processed/opp115_segments.jsonl")

#: At least this many of the three annotators must mark a category.
DEFAULT_MIN_VOTES = 2
ANNOTATORS_PER_POLICY = 3


class DatasetError(Exception):
    """The corpus on disk cannot support the dataset being built."""


@dataclass(frozen=True)
class LabelledSegment:
    """One training example.

    ``policy_id`` is the corpus **filename stem**, such as
    ``135_instagram.com``. It is deliberately not column D of the annotation
    CSV, which carries a different internal identifier — for that file, 3850.
    Grouping by the wrong one would scatter a policy's segments across splits
    and leak policy-specific language, which is exactly what the grouped split
    exists to prevent.
    """

    policy_id: str
    segment_index: int
    text: str
    labels: tuple[str, ...]
    #: How many annotators marked each label that survived the vote.
    votes: dict[str, int] = field(default_factory=dict)

    @property
    def example_id(self) -> str:
        return f"{self.policy_id}#{self.segment_index}"


@dataclass
class DatasetReport:
    """What was built, and anything that looked wrong while building it."""

    corpus_path: Path
    policies: int = 0
    segments: int = 0
    annotation_rows: int = 0
    malformed_rows: int = 0
    unknown_categories: Counter = field(default_factory=Counter)
    segments_without_labels: int = 0
    label_support: Counter = field(default_factory=Counter)
    labels_per_segment: Counter = field(default_factory=Counter)
    min_votes: int = DEFAULT_MIN_VOTES
    warnings: list[str] = field(default_factory=list)


def _read_segments(corpus: Path) -> dict[str, list[str]]:
    """Policy text split into the corpus's own segments."""
    directory = corpus / "sanitized_policies"
    if not directory.is_dir():
        raise DatasetError(
            f"{directory} not found. The OPP-115 corpus must be extracted at "
            f"{corpus}; see data/README.md. It is not downloaded automatically."
        )

    segments: dict[str, list[str]] = {}
    for path in sorted(directory.glob("*.html")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        segments[path.stem] = raw.split(SEGMENT_SEPARATOR)
    if not segments:
        raise DatasetError(f"no policy files found under {directory}")
    return segments


def _read_votes(
    corpus: Path, report: DatasetReport
) -> dict[tuple[str, int], dict[str, set[str]]]:
    """(policy, segment) -> category -> the annotators who marked it."""
    directory = corpus / "annotations"
    if not directory.is_dir():
        raise DatasetError(f"{directory} not found")

    known = set(CATEGORIES)
    votes: dict[tuple[str, int], dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )

    for path in sorted(directory.glob("*.csv")):
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.reader(handle):
                if len(row) != EXPECTED_COLUMN_COUNT:
                    report.malformed_rows += 1
                    continue
                report.annotation_rows += 1

                category = row[5].strip()
                if category not in known:
                    report.unknown_categories[category] += 1
                    continue

                try:
                    segment_index = int(row[4])
                except ValueError:
                    report.malformed_rows += 1
                    continue

                votes[(path.stem, segment_index)][category].add(row[2].strip())

    return votes


def build_dataset(
    corpus: Path | str = DEFAULT_CORPUS,
    min_votes: int = DEFAULT_MIN_VOTES,
) -> tuple[list[LabelledSegment], DatasetReport]:
    """Turn the corpus into labelled segments.

    Every segment of every policy becomes an example, including those that
    receive no label after the vote. Dropping them would remove the negative
    evidence that a segment discusses no data practice, which the classifier
    needs in order to learn not to fire on boilerplate.
    """
    if min_votes < 1 or min_votes > ANNOTATORS_PER_POLICY:
        raise DatasetError(
            f"min_votes must be between 1 and {ANNOTATORS_PER_POLICY}, got {min_votes}"
        )

    corpus = Path(corpus)
    report = DatasetReport(corpus_path=corpus, min_votes=min_votes)

    texts = _read_segments(corpus)
    votes = _read_votes(corpus, report)
    report.policies = len(texts)

    annotated_policies = {policy for policy, _ in votes}
    missing = sorted(set(texts) - annotated_policies)
    if missing:
        report.warnings.append(
            f"{len(missing)} policies have text but no annotations: {missing[:3]}"
        )

    examples: list[LabelledSegment] = []
    seen: set[tuple[str, int]] = set()

    for policy_id in sorted(texts):
        for segment_index, raw_text in enumerate(texts[policy_id]):
            text = raw_text.strip()
            if not text:
                continue

            key = (policy_id, segment_index)
            if key in seen:
                raise DatasetError(f"duplicate example {key}")
            seen.add(key)

            counted = {
                category: len(annotators)
                for category, annotators in votes.get(key, {}).items()
            }
            labels = tuple(
                category
                for category in CATEGORIES
                if counted.get(category, 0) >= min_votes
            )

            examples.append(
                LabelledSegment(
                    policy_id=policy_id,
                    segment_index=segment_index,
                    text=text,
                    labels=labels,
                    votes={c: counted[c] for c in labels},
                )
            )

            report.segments += 1
            report.labels_per_segment[len(labels)] += 1
            if not labels:
                report.segments_without_labels += 1
            for label in labels:
                report.label_support[label] += 1

    if not examples:
        raise DatasetError("the corpus produced no examples")

    return examples, report


def dataset_fingerprint(examples: list[LabelledSegment]) -> str:
    """A hash of the dataset, so a model records what it was trained on.

    Computed from the identifiers and labels rather than the full text, which
    is enough to detect a different corpus or a different label rule while
    keeping the fingerprint cheap.
    """
    digest = hashlib.sha256()
    for example in examples:
        digest.update(example.example_id.encode("utf-8"))
        digest.update("|".join(example.labels).encode("utf-8"))
    return digest.hexdigest()


def write_dataset(
    examples: list[LabelledSegment], path: Path | str = DEFAULT_OUTPUT
) -> Path:
    """Write to JSON Lines, kept apart from the untouched corpus files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(asdict(example), ensure_ascii=False) + "\n")
    return path


def read_dataset(path: Path | str = DEFAULT_OUTPUT) -> list[LabelledSegment]:
    path = Path(path)
    examples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        examples.append(
            LabelledSegment(
                policy_id=raw["policy_id"],
                segment_index=raw["segment_index"],
                text=raw["text"],
                labels=tuple(raw["labels"]),
                votes=raw.get("votes", {}),
            )
        )
    return examples


def format_report(report: DatasetReport) -> str:
    lines = [
        "-" * 68,
        "OPP-115 segment-level dataset",
        "-" * 68,
        f"Corpus            : {report.corpus_path}",
        f"Policies          : {report.policies}",
        f"Segments          : {report.segments}",
        f"Annotation rows   : {report.annotation_rows}",
        f"Label rule        : at least {report.min_votes} of "
        f"{ANNOTATORS_PER_POLICY} annotators",
        f"Unlabelled        : {report.segments_without_labels} "
        f"({100 * report.segments_without_labels / max(report.segments, 1):.1f}%)",
        "",
        "Label support (positive segments per category)",
    ]
    for category in CATEGORIES:
        count = report.label_support.get(category, 0)
        share = 100 * count / max(report.segments, 1)
        flag = "  <-- rare" if count < 100 else ""
        lines.append(f"  {count:5d}  {share:5.1f}%  {category}{flag}")

    lines += ["", "Labels per segment"]
    for n in sorted(report.labels_per_segment):
        lines.append(f"  {n} label(s): {report.labels_per_segment[n]}")

    if report.malformed_rows:
        lines.append(f"\nMalformed rows skipped: {report.malformed_rows}")
    if report.unknown_categories:
        lines.append(f"Unknown categories: {dict(report.unknown_categories)}")
    for warning in report.warnings:
        lines.append(f"WARNING: {warning}")

    lines.append("-" * 68)
    return "\n".join(lines)
