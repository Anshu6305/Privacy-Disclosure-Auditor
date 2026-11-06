#!/usr/bin/env python3
"""Pack everything a GPU notebook needs to train F-12, and nothing else.

    python ml/export_f12_bundle.py

Writes `ml/runs/f12_training_bundle.zip`: the tagged dataset plus the exact
modules that built and split it, at their real paths. The notebook unzips it
and runs `ml/train_span_extractor.py`, so Colab trains with the same code and
the same seed as a local run rather than a copy that can drift from it.

The OPP-115 corpus itself is **not** included. The bundle carries only the
derived, slice-verified tags, which are the project's own artefact.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.data.span_training_data import (  # noqa: E402
    build_tagged_segments,
    write_jsonl,
)

DATASET = Path("data/processed/opp115_span_tags.jsonl")
BUNDLE = Path("ml/runs/f12_training_bundle.zip")

#: Carried verbatim so the notebook runs the same splitter and the same
#: trainer as a local run. Any copy of this logic could drift from it.
MODULES = (
    "ml/__init__.py",
    "ml/data/__init__.py",
    "ml/data/splits.py",
    "ml/data/opp115_schema.py",
    "ml/data/span_training_data.py",
    "ml/train_span_extractor.py",
)


def main() -> int:
    segments = build_tagged_segments()
    dataset = write_jsonl(segments, ROOT / DATASET)
    print(f"dataset: {dataset} ({len(segments)} segments)")

    bundle = ROOT / BUNDLE
    bundle.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(dataset, DATASET.as_posix())
        for name in MODULES:
            path = ROOT / name
            if not path.is_file():
                raise SystemExit(f"missing {name}; the bundle would not run")
            archive.write(path, name)
    size = bundle.stat().st_size / 1_000_000
    print(f"bundle:  {bundle} ({size:.1f} MB, {len(MODULES) + 1} files)")
    print("\nUpload it to the notebook in notebooks/train_f12_colab.ipynb.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
