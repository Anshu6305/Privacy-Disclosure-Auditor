#!/usr/bin/env python3
"""Train F-11's improved encoder classifier, on the M5 split.

    python ml/train_improved_classifier.py --dry-run
    python ml/train_improved_classifier.py

**Same split, same seed, same evaluation as M5.** It loads the identical
policy-grouped split (`ml/data/splits.py`, seed 20261105) and reports through
the identical evaluation module, so the comparison against the baseline is
between two models and not between two experiments.

**The test set is used once, at the end, and never for tuning.** The
validation split exists for that. Any threshold or epoch chosen from test
results would make the reported number meaningless.

Needs torch, transformers and network access for the checkpoint:
``pip install -r backend/requirements-ml.txt``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.models.improved_classifier import ImprovedClassifierConfig  # noqa: E402
from ml.data.opp115_dataset import read_dataset  # noqa: E402
from ml.data.splits import format_split_report, split_by_policy  # noqa: E402

DEFAULT_OUTPUT = Path("ml/checkpoints/improved_classifier")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report the split and configuration, train nothing.")
    arguments = parser.parse_args()

    config = ImprovedClassifierConfig()
    if arguments.epochs is not None:
        config = ImprovedClassifierConfig(**{**config.__dict__, "epochs": arguments.epochs})

    examples = read_dataset()
    split = split_by_policy(examples, seed=config.random_seed)
    print(format_split_report(split.report))
    print("\nconfiguration:")
    print(json.dumps(config.as_metadata(), indent=2))

    if arguments.dry_run:
        print(
            "\nDry run: nothing was trained and no metric was produced.\n"
            "The split above is the same one the M5 baseline used, so the two "
            "models are comparable."
        )
        return 0

    from ml.training.classifier_trainer import train_and_evaluate  # noqa: PLC0415

    return train_and_evaluate(split, config, Path(arguments.output))


if __name__ == "__main__":
    raise SystemExit(main())
