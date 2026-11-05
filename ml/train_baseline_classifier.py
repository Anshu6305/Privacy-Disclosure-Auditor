#!/usr/bin/env python3
"""Train and evaluate the F-11 baseline classifier on OPP-115 (ALG-2).

This is the real experiment, not a fixture test. It reads the corpus already
present at ``data/raw/opp115`` — nothing is downloaded — builds segment-level
labels, splits by source policy, trains, and reports held-out results.

    python ml/train_baseline_classifier.py
    python ml/train_baseline_classifier.py --seed 7 --no-save

The test set is used **once**, for the final report. Threshold choice and any
tuning use the validation split, which is why both are reported separately and
labelled.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.models.practice_classifier import (  # noqa: E402
    DEFAULT_RANDOM_SEED,
    BaselineConfig,
    BaselinePracticeClassifier,
)
from ml.data.opp115_dataset import (  # noqa: E402
    DEFAULT_CORPUS,
    build_dataset,
    dataset_fingerprint,
    format_report,
    write_dataset,
)
from ml.data.opp115_schema import CATEGORIES  # noqa: E402
from ml.data.splits import (  # noqa: E402
    DEFAULT_PROPORTIONS,
    DEFAULT_SEED,
    format_split_report,
    split_by_policy,
)
from ml.evaluation import evaluate, format_evaluation, metrics_to_dict  # noqa: E402

DEFAULT_ARTEFACT_DIR = Path("ml/checkpoints/classifier-baseline-v1")
DEFAULT_METRICS_PATH = Path("ml/runs/classifier-baseline-v1-metrics.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--model-seed", type=int, default=DEFAULT_RANDOM_SEED)
    parser.add_argument("--min-votes", type=int, default=2)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--artefacts", type=Path, default=DEFAULT_ARTEFACT_DIR)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    # --- 1. Dataset ------------------------------------------------------
    print("\n### 1. Dataset construction\n")
    examples, dataset_report = build_dataset(args.corpus, min_votes=args.min_votes)
    print(format_report(dataset_report))
    fingerprint = dataset_fingerprint(examples)
    print(f"\nDataset fingerprint: {fingerprint}")

    if not args.no_save:
        path = write_dataset(examples)
        print(f"Training data written: {path}  (git-ignored)")

    # --- 2. Split --------------------------------------------------------
    print("\n### 2. Policy-grouped split\n")
    split = split_by_policy(examples, DEFAULT_PROPORTIONS, seed=args.seed)
    print(format_split_report(split.report))

    overlap = (split.policies_in("train") & split.policies_in("test")) | (
        split.policies_in("train") & split.policies_in("validation")
    ) | (split.policies_in("validation") & split.policies_in("test"))
    print(f"\nPolicy overlap between splits: {len(overlap)} (must be 0)")
    if overlap:
        raise SystemExit("policy leakage detected; refusing to train")

    # --- 3. Train --------------------------------------------------------
    print("\n### 3. Training\n")
    config = BaselineConfig(random_seed=args.model_seed)
    model = BaselinePracticeClassifier(config=config, categories=list(CATEGORIES))
    print(f"Config: {config}")
    model.fit([e.text for e in split.train], [e.labels for e in split.train])
    print(f"Trained on {len(split.train)} segments from "
          f"{split.report.policies['train']} policies.")
    if model.metadata.notes:
        print(f"NOTE: {model.metadata.notes}")

    # --- 4. Evaluate -----------------------------------------------------
    print("\n### 4. Results\n")
    results = {}
    for name, data in (
        ("train", split.train),
        ("validation", split.validation),
        ("test", split.test),
    ):
        scores = model.predict_scores([e.text for e in data])
        report = evaluate(
            [e.labels for e in data], scores, list(CATEGORIES), name,
            threshold=args.threshold,
        )
        results[name] = report
        print(format_evaluation(report))
        print()

    print("Training-set figures are reported to show the fit, NOT as a result.")
    print("The held-out TEST figures above are the result.\n")

    # --- 5. Artefact -----------------------------------------------------
    if not args.no_save:
        model.metadata.dataset_fingerprint = fingerprint
        model.metadata.dataset_description = (
            f"OPP-115, {dataset_report.policies} policies, "
            f"{dataset_report.segments} segments"
        )
        model.metadata.label_rule = (
            f"majority vote, at least {args.min_votes} of 3 annotators"
        )
        model.metadata.split_seed = args.seed
        model.metadata.split_policies = dict(split.report.policies)
        model.metadata.split_segments = dict(split.report.segments)
        model.metadata.metrics = {
            name: metrics_to_dict(report) for name, report in results.items()
        }

        path = model.save(args.artefacts)
        print(f"\n### 5. Artefact\n\nModel: {path}")
        print(f"Metadata: {args.artefacts / 'metadata.json'}")

        args.metrics.parent.mkdir(parents=True, exist_ok=True)
        args.metrics.write_text(
            json.dumps(
                {name: metrics_to_dict(r) for name, r in results.items()},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Metrics: {args.metrics}")
        print("\nBoth are git-ignored; the metrics are reproduced in the M5 report.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
