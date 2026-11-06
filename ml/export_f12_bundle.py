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

#: The module the bundle must be able to run.
ENTRY_POINT = "ml/train_span_extractor.py"

#: First-party package roots. An import outside these is a third-party
#: dependency the notebook installs with pip, not a file to carry.
LOCAL_ROOTS = frozenset({"ml", "analysis", "acquisition", "app"})


def _module_path(root: Path, dotted: str) -> str | None:
    """Resolve a dotted module name to a repository-relative path."""
    module = root / (dotted.replace(".", "/") + ".py")
    if module.is_file():
        return module.relative_to(root).as_posix()
    package = root / dotted.replace(".", "/") / "__init__.py"
    if package.is_file():
        return package.relative_to(root).as_posix()
    return None


def required_modules(root: Path = ROOT, entry: str = ENTRY_POINT) -> list[str]:
    """Every first-party module the entry point needs, found by reading it.

    Derived from the import graph rather than listed by hand. The first
    version of this script carried a hand-written list, and it silently
    omitted `ml/data/opp115_spans.py` and `ml/data/opp115_dataset.py`: the
    bundle built, uploaded and extracted without complaint and then failed on
    Colab with a ModuleNotFoundError. A list maintained by a person goes
    stale the first time an import is added; a closure does not.

    Walks `import` and `from x import` at any depth, follows only the local
    roots, and carries every ancestor package's `__init__.py` so the
    extracted tree is importable.
    """
    import ast

    found: set[str] = set()
    queue = [entry]
    while queue:
        relative = queue.pop()
        if relative in found:
            continue
        found.add(relative)

        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module)

        for name in names:
            if name.split(".")[0] not in LOCAL_ROOTS:
                continue
            parts = name.split(".")
            # The module itself, plus every package above it.
            for depth in range(1, len(parts) + 1):
                path = _module_path(root, ".".join(parts[:depth]))
                if path is not None:
                    queue.append(path)

    return sorted(found)


def main() -> int:
    segments = build_tagged_segments()
    dataset = write_jsonl(segments, ROOT / DATASET)
    print(f"dataset: {dataset} ({len(segments)} segments)")

    modules = required_modules()
    print(f"modules: {len(modules)}")
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
    print(f"\nbundle:  {bundle} ({size:.1f} MB, {len(modules) + 1} files)")
    print("Upload it to the notebook in notebooks/train_f12_colab.ipynb.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
