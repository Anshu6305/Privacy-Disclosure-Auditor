#!/usr/bin/env python3
"""Validate the operational Android application corpus.

Checks every record for duplicates, missing disclosures and document hash
mismatches, and regenerates the manifest from what is actually on disk.

    python scripts/validate_corpus.py
    python scripts/validate_corpus.py --root data/corpus --write-manifest

Exit codes:
    0  no errors; the corpus is usable
    1  errors found, listed in the output

Warnings do not fail the run. A corpus with incomplete records is still a
usable corpus of the complete ones, and the counts say exactly how many of
each there are.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acquisition.corpus import (  # noqa: E402
    DEFAULT_CORPUS_ROOT,
    CorpusPaths,
    format_report,
    validate_corpus,
    write_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="regenerate manifest.json from the records on disk",
    )
    args = parser.parse_args()

    report = validate_corpus(args.root)
    print(format_report(report))

    if args.write_manifest:
        if report.ok:
            path = write_manifest(CorpusPaths(args.root))
            print(f"Manifest written: {path}")
        else:
            print("Manifest not written: resolve the errors above first.")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
