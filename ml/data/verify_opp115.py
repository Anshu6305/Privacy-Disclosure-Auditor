#!/usr/bin/env python3
"""Verify the local OPP-115 corpus and write a reproducibility manifest.

This script reports what is actually on disk. It downloads nothing, modifies
nothing inside the corpus, and makes no claim it has not checked.

Why it exists: the corpus is licensed for research, teaching and scholarship
use and is not redistributed in this repository, so the repository cannot
contain the data itself. What it can contain is a manifest of file checksums
and counts, which lets anyone confirm they are working from the same corpus
without us republishing it.

Usage:
    python ml/data/verify_opp115.py
    python ml/data/verify_opp115.py --corpus data/raw/opp115 --write-manifest

Exit codes:
    0  corpus found and structurally consistent with the v1.0 release
    1  corpus missing, or a structural problem that must be resolved
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml.data.opp115_schema import (  # noqa: E402
    CATEGORIES,
    COL_ANNOTATOR_ID,
    COL_ATTRIBUTES_JSON,
    COL_CATEGORY,
    COL_POLICY_ID,
    COL_SEGMENT_ID,
    COL_TRAILING_A,
    COL_TRAILING_B,
    EXPECTED_ANNOTATORS_PER_POLICY,
    EXPECTED_COLUMN_COUNT,
    EXPECTED_DOCUMENT_COUNT,
    SEGMENT_SEPARATOR,
    SPAN_FREE_VALUES,
)

DEFAULT_CORPUS = Path("data/raw/opp115")
MANIFEST_PATH = Path("ml/data/opp115_manifest.json")

REQUIRED_SUBDIRS = ("annotations", "sanitized_policies", "documentation")
OPTIONAL_SUBDIRS = (
    "consolidation",
    "original_policies",
    "pretty_print",
    "pretty_print_uniquified",
)


@dataclass
class Report:
    """Everything observed. Problems and observations are kept apart: a
    problem blocks use of the corpus, an observation is merely worth knowing."""

    corpus_path: Path
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    annotation_files: int = 0
    policy_files: int = 0
    practice_rows: int = 0
    malformed_rows: int = 0

    categories: Counter[str] = field(default_factory=Counter)
    unknown_categories: Counter[str] = field(default_factory=Counter)
    annotators_per_policy: dict[str, int] = field(default_factory=dict)
    segments_per_policy: dict[str, int] = field(default_factory=dict)

    attribute_json_failures: int = 0
    spans_total: int = 0
    spans_usable: int = 0
    spans_absent_by_design: int = 0
    spans_missing_text: int = 0
    spans_degenerate_offsets: int = 0
    span_errata: Counter[str] = field(default_factory=Counter)

    trailing_columns_swapped: int = 0
    trailing_columns_as_documented: int = 0

    checksums: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_layout(corpus: Path, report: Report) -> None:
    if not corpus.is_dir():
        report.problems.append(
            f"Corpus directory not found: {corpus}\n"
            f"  Place the extracted OPP-115 corpus there. See data/README.md."
        )
        return

    for name in REQUIRED_SUBDIRS:
        if not (corpus / name).is_dir():
            report.problems.append(
                f"Required subdirectory missing: {name}/\n"
                f"  Extract the corpus so its own folders sit directly inside "
                f"{corpus}, without an extra wrapping folder."
            )

    for name in OPTIONAL_SUBDIRS:
        if not (corpus / name).is_dir():
            report.notes.append(f"Optional subdirectory absent: {name}/")


def read_annotations(corpus: Path, report: Report) -> None:
    directory = corpus / "annotations"
    if not directory.is_dir():
        return

    files = sorted(p for p in directory.glob("*.csv"))
    report.annotation_files = len(files)

    known = set(CATEGORIES)

    for path in files:
        annotators: set[str] = set()
        segments: set[str] = set()

        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.reader(handle):
                if len(row) != EXPECTED_COLUMN_COUNT:
                    report.malformed_rows += 1
                    continue

                report.practice_rows += 1

                category = row[COL_CATEGORY].strip()
                if category in known:
                    report.categories[category] += 1
                else:
                    report.unknown_categories[category] += 1

                annotators.add(row[COL_ANNOTATOR_ID].strip())
                segments.add(row[COL_SEGMENT_ID].strip())

                # Which of the last two columns is the URL? Decide by content.
                a, b = row[COL_TRAILING_A].strip(), row[COL_TRAILING_B].strip()
                if b.startswith(("http://", "https://")):
                    report.trailing_columns_swapped += 1
                elif a.startswith(("http://", "https://")):
                    report.trailing_columns_as_documented += 1

                inspect_attributes(row[COL_ATTRIBUTES_JSON], report)

        key = path.stem
        report.annotators_per_policy[key] = len(annotators)
        report.segments_per_policy[key] = len(segments)
        report.checksums[f"annotations/{path.name}"] = sha256_of(path)

    if report.annotation_files != EXPECTED_DOCUMENT_COUNT:
        report.problems.append(
            f"Expected {EXPECTED_DOCUMENT_COUNT} annotation files, found "
            f"{report.annotation_files}."
        )

    if report.unknown_categories:
        listed = ", ".join(sorted(report.unknown_categories))
        report.problems.append(
            f"Category labels not in the known set: {listed}. The corpus on "
            f"disk differs from the release this code targets."
        )

    off_count = {
        name: n
        for name, n in report.annotators_per_policy.items()
        if n != EXPECTED_ANNOTATORS_PER_POLICY
    }
    if off_count:
        report.notes.append(
            f"{len(off_count)} policies do not have exactly "
            f"{EXPECTED_ANNOTATORS_PER_POLICY} distinct annotator IDs "
            f"(e.g. {sorted(off_count)[:3]})."
        )


def inspect_attributes(raw: str, report: Report) -> None:
    """Count spans and the unusable ones, per the corpus errata.

    A span is unusable for supervision when 'selectedText' is absent, or when
    its start and end offsets are both -1 or both 0. These are counted, never
    repaired by guesswork.
    """
    try:
        attributes = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        report.attribute_json_failures += 1
        return

    if not isinstance(attributes, dict):
        report.attribute_json_failures += 1
        return

    for entry in attributes.values():
        if not isinstance(entry, dict):
            continue
        report.spans_total += 1

        selected_value = str(entry.get("value", ""))
        span_free = selected_value in SPAN_FREE_VALUES

        if "selectedText" not in entry:
            report.spans_missing_text += 1
            if span_free:
                report.spans_absent_by_design += 1
            else:
                report.span_errata[selected_value] += 1
            continue

        start = entry.get("startIndexInSegment")
        end = entry.get("endIndexInSegment")
        if (start == end == -1) or (start == end == 0):
            report.spans_degenerate_offsets += 1
            if span_free:
                report.spans_absent_by_design += 1
            else:
                report.span_errata[selected_value] += 1
            continue

        report.spans_usable += 1


def read_policies(corpus: Path, report: Report) -> None:
    directory = corpus / "sanitized_policies"
    if not directory.is_dir():
        return

    files = sorted(directory.glob("*.html"))
    report.policy_files = len(files)

    empty_segments = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        segments = [s for s in text.split(SEGMENT_SEPARATOR)]
        if any(not s.strip() for s in segments):
            empty_segments += 1
        report.checksums[f"sanitized_policies/{path.name}"] = sha256_of(path)

    if report.policy_files != EXPECTED_DOCUMENT_COUNT:
        report.problems.append(
            f"Expected {EXPECTED_DOCUMENT_COUNT} sanitized policy files, found "
            f"{report.policy_files}."
        )

    if empty_segments:
        report.notes.append(
            f"{empty_segments} policy files contain at least one empty segment "
            f"after splitting on '{SEGMENT_SEPARATOR}'."
        )

    annotated = set(report.annotators_per_policy)
    present = {p.stem for p in files}
    only_annotations = sorted(annotated - present)
    only_policies = sorted(present - annotated)
    if only_annotations:
        report.problems.append(
            f"Annotation files with no matching policy text: {only_annotations[:5]}"
        )
    if only_policies:
        report.problems.append(
            f"Policy texts with no matching annotation file: {only_policies[:5]}"
        )


def print_report(report: Report) -> None:
    line = "-" * 68
    print(line)
    print("OPP-115 corpus verification")
    print(line)
    print(f"Corpus path          : {report.corpus_path}")
    print(f"Annotation files     : {report.annotation_files}")
    print(f"Policy text files    : {report.policy_files}")
    print(f"Annotated practices  : {report.practice_rows}")
    if report.malformed_rows:
        print(f"Malformed rows       : {report.malformed_rows}")

    print()
    print("Category distribution (all three annotators, unconsolidated)")
    total = sum(report.categories.values()) or 1
    for category in CATEGORIES:
        count = report.categories.get(category, 0)
        print(f"  {count:7d}  {100 * count / total:5.1f}%  {category}")

    print()
    print("Text spans (attribute entries)")
    pct = (100 * report.spans_usable / report.spans_total) if report.spans_total else 0.0
    print(f"  total entries              : {report.spans_total}")
    print(f"  usable for supervision     : {report.spans_usable}  ({pct:.1f}%)")
    print(f"  span-free by design        : {report.spans_absent_by_design}")
    print(f"    (values: {', '.join(sorted(SPAN_FREE_VALUES))})")
    print(f"  unexpected absences        : {sum(report.span_errata.values())}  (corpus errata)")
    if report.span_errata:
        for value, count in report.span_errata.most_common(5):
            print(f"      {count:5d}  value={value!r}")
    print(f"  of which missing text      : {report.spans_missing_text}")
    print(f"  of which 0/-1 offsets      : {report.spans_degenerate_offsets}")
    if report.attribute_json_failures:
        print(f"  unparseable attribute JSON : {report.attribute_json_failures}")

    segs = list(report.segments_per_policy.values())
    if segs:
        print()
        print("Segments per policy")
        print(f"  min {min(segs)}   max {max(segs)}   mean {sum(segs) / len(segs):.1f}")

    print()
    print("Trailing column order (manual says URL then date)")
    print(f"  date then URL (as released) : {report.trailing_columns_swapped}")
    print(f"  URL then date (as manual)   : {report.trailing_columns_as_documented}")

    if report.notes:
        print()
        print("Observations")
        for note in report.notes:
            print(f"  - {note}")

    print()
    if report.ok:
        print("RESULT: corpus is present and structurally consistent.")
    else:
        print("RESULT: problems found.")
        for problem in report.problems:
            print(f"  ! {problem}")
    print(line)


def write_manifest(report: Report, path: Path) -> None:
    payload = {
        "corpus": "OPP-115",
        "source": "Usable Privacy Policy Project, Carnegie Mellon University",
        "citation": (
            "Wilson, S., Schaub, F., Dara, A. A., Liu, F., Cherivirala, S., "
            "Leon, P. G., Andersen, M. S., Zimmeck, S., Sathyendra, K. M., "
            "Russell, N. C., Norton, T. B., Hovy, E., Reidenberg, J., and "
            "Sadeh, N. The creation and analysis of a website privacy policy "
            "corpus. In Proceedings of the 54th Annual Meeting of the "
            "Association for Computational Linguistics, Berlin, Germany, "
            "August 2016."
        ),
        "licence_note": (
            "Made available for research, teaching and scholarship purposes "
            "only, in the spirit of a Creative Commons "
            "Attribution-NonCommercial licence. Not redistributed in this "
            "repository."
        ),
        "verified_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {
            "annotation_files": report.annotation_files,
            "policy_files": report.policy_files,
            "annotated_practices": report.practice_rows,
            "attribute_entries_total": report.spans_total,
            "spans_usable_for_supervision": report.spans_usable,
            "spans_absent_by_design": report.spans_absent_by_design,
            "spans_unexpected_absences": sum(report.span_errata.values()),
        },
        "category_distribution": {c: report.categories.get(c, 0) for c in CATEGORIES},
        "file_checksums_sha256": dict(sorted(report.checksums.items())),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest written: {path}  ({len(report.checksums)} files hashed)")


def verify(corpus: Path) -> Report:
    report = Report(corpus_path=corpus)
    check_layout(corpus, report)
    if report.problems:
        return report
    read_annotations(corpus, report)
    read_policies(corpus, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="Write the checksum manifest (committed; the data is not).",
    )
    args = parser.parse_args()

    report = verify(args.corpus)
    print_report(report)

    if args.write_manifest:
        if report.ok:
            write_manifest(report, args.manifest)
        else:
            print("Manifest not written: resolve the problems above first.")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
