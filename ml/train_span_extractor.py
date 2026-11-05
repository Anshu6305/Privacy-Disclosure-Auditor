#!/usr/bin/env python3
"""Train F-12's BIO span tagger on the OPP-115 highlights.

    python ml/train_span_extractor.py --dry-run
    python ml/train_span_extractor.py

Supervision: 23,150 spans verified by slicing — 11,913 data type, 11,237
purpose — from `ml/data/opp115_spans.py`. Split by **source policy**, with the
same seed as M5, so a policy's segments never cross a split boundary.

Needs torch, transformers and network access for the checkpoint.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.data.opp115_spans import (  # noqa: E402
    SPAN_TYPES,
    build_span_dataset,
    format_span_report,
)
from ml.data.splits import DEFAULT_SEED  # noqa: E402

DEFAULT_OUTPUT = Path("ml/checkpoints/span_extractor")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    spans, report = build_span_dataset()
    print(format_span_report(report))

    policies = sorted({span.policy_id for span in spans})
    per_policy = Counter(span.policy_id for span in spans)
    print(f"\npolicies with spans: {len(policies)}")
    print(f"median spans per policy: {sorted(per_policy.values())[len(per_policy) // 2]}")
    print(f"split seed: {DEFAULT_SEED}")
    print(f"span types: {', '.join(SPAN_TYPES)}")

    if arguments.dry_run:
        print(
            "\nDry run: nothing was trained and no metric was produced.\n"
            "Span-level precision, recall and F1 are reported only after a "
            "real training run."
        )
        return 0

    print(
        "\nTraining is not implemented in this script yet. The dataset, the "
        "BIO encoding, the offset translation and the decoder are complete "
        "and tested; the token-classification loop is the remaining piece "
        "and needs a downloadable checkpoint. See docs/M6_REPORT.md.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
