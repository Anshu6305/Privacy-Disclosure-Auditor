#!/usr/bin/env python3
"""Evaluate a trained F-12 checkpoint on the held-out test split.

    python ml/evaluate_span_extractor.py

Exists because the training run happened on Colab and its metrics file was
not brought back with the checkpoint. Rather than transcribe figures from a
notebook's console, this re-derives them from the checkpoint and the same
test split, and writes `ml/runs/span-extractor-v1-metrics.json`.

It reuses the trainer's own `score_segments`, so the definition of a correct
span is the one the training run used and not a second implementation that
could disagree with it.

**The test split is read here, as it was at the end of training.** No
threshold or any other choice is made from what this prints.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from ml.data.span_training_data import (  # noqa: E402
    OUTSIDE,
    build_tagged_segments,
    read_jsonl,
    split_segments,
)
from ml.train_span_extractor import (  # noqa: E402
    DEFAULT_METRICS_PATH,
    format_scores,
    score_segments,
)

DEFAULT_CHECKPOINT = Path("ml/checkpoints/span-extractor-v1")
DATASET = Path("data/processed/opp115_span_tags.jsonl")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--split", default="test", choices=["validation", "test"])
    arguments = parser.parse_args()

    from ml.span_backend import SpanBackendUnavailableError, TransformerSpanTagger

    try:
        backend = TransformerSpanTagger(arguments.checkpoint)
    except SpanBackendUnavailableError as exc:
        print(f"No usable checkpoint: {exc}", file=sys.stderr)
        return 2

    segments = (
        read_jsonl(DATASET) if (ROOT / DATASET).is_file() else build_tagged_segments()
    )
    split = split_segments(segments)
    held_out = list(getattr(split, arguments.split))
    print(f"checkpoint : {arguments.checkpoint}")
    print(f"split      : {arguments.split} ({len(held_out)} segments)")

    predictions: list[list[str]] = []
    for index, segment in enumerate(held_out, start=1):
        tokens = [
            (token, start, end)
            for token, (start, end) in zip(
                segment.tokens, segment.offsets, strict=True
            )
        ]
        tagged = backend.tag(tokens)
        predictions.append([token.tag for token in tagged] or [OUTSIDE] * len(tokens))
        if index % 50 == 0:
            print(f"  {index}/{len(held_out)}")

    scores = score_segments(held_out, predictions)
    print(format_scores(arguments.split, scores))

    exact_p, exact_r, exact_f = scores.exact()
    over_p, over_r, over_f = scores.overlapping()
    payload = {
        "split": arguments.split,
        "checkpoint": str(arguments.checkpoint),
        "gold_spans": scores.gold,
        "predicted_spans": scores.predicted,
        "exact": {"precision": exact_p, "recall": exact_r, "f1": exact_f},
        "overlapping": {"precision": over_p, "recall": over_r, "f1": over_f},
        "unverifiable_spans": scores.unverifiable,
        "per_type": scores.per_type,
    }
    metrics = Path(arguments.metrics)
    metrics.parent.mkdir(parents=True, exist_ok=True)
    metrics.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nmetrics: {metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
