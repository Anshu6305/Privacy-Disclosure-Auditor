#!/usr/bin/env python3
"""Pack everything a GPU notebook needs to train F-11's improved variant.

    python ml/export_improved_bundle.py

The same route F-12 took, and for the same reason: `distilbert-base-uncased`
cannot be downloaded in the development environment, so training happens
where Hugging Face is reachable.

Writes `ml/runs/improved_classifier_bundle_v3.zip`: the segment dataset plus
the exact modules that read, split and train on it, at their real paths. The
notebook unzips it and runs this repository's own
`ml/train_improved_classifier.py`, so Colab uses the same frozen OPP-115
split, the same seed (20261105) and the same evaluation module as a local
run rather than a copy that can drift from them.

The module list is the import closure of the trainer, computed by
`required_modules` — the same function the F-12 bundle uses, after a
hand-written list there silently omitted two modules (C-78).
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.export_f12_bundle import required_modules  # noqa: E402

ENTRY_POINT = "ml/train_improved_classifier.py"
DATASET = Path("data/processed/opp115_segments.jsonl")
BUNDLE = Path("ml/runs/improved_classifier_bundle_v3.zip")


def main() -> int:
    dataset = ROOT / DATASET
    if not dataset.is_file():
        raise SystemExit(
            f"{DATASET} is missing. Build it first with:\n"
            "    python ml/data/opp115_dataset.py\n"
            "Nothing was written."
        )

    modules = required_modules(ROOT, ENTRY_POINT)
    print(f"entry point : {ENTRY_POINT}")
    print(f"modules     : {len(modules)}")
    for name in modules:
        print(f"  {name}")

    bundle = ROOT / BUNDLE
    bundle.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(dataset, DATASET.as_posix())
        for name in modules:
            path = ROOT / name
            if not path.is_file():
                raise SystemExit(f"missing {name}; the bundle would not run")
            archive.write(path, name)

    size = bundle.stat().st_size / 1_000_000
    print(f"\nbundle: {bundle} ({size:.1f} MB, {len(modules) + 1} files)")
    print(
        "\nUpload it to a GPU notebook, unzip, then run:\n"
        "    python ml/train_improved_classifier.py --dry-run\n"
        "\nIf ml/checkpoints/improved_classifier from the earlier run is still\n"
        "there, score it without paying for the fine-tune again:\n"
        "    python ml/train_improved_classifier.py --evaluate-only\n"
        "\nOtherwise train, which saves the checkpoint and then scores it:\n"
        "    python ml/train_improved_classifier.py\n"
        "\nBring back ml/checkpoints/improved_classifier and\n"
        "ml/runs/improved-classifier-v1-metrics.json. Record only the metrics\n"
        "the run actually prints."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
