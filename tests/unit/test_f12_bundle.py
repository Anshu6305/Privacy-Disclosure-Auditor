"""The F-12 training bundle must actually run once extracted.

The first version of `ml/export_f12_bundle.py` carried a hand-written module
list that omitted `ml/data/opp115_spans.py` and `ml/data/opp115_dataset.py`.
The bundle built, uploaded and extracted without complaint, and failed on
Colab with `ModuleNotFoundError`. Nothing in the repository could have caught
it, because every module imports fine from a full checkout.

These tests therefore check the bundle as a GPU notebook sees it: extracted
on its own, with the repository not on the path.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from ml.export_f12_bundle import (
    DATASET,
    ENTRY_POINT,
    LOCAL_ROOTS,
    required_modules,
)

ROOT = Path(__file__).resolve().parents[2]

#: The two the hand-written list missed. Named explicitly so the regression
#: is legible in the test output rather than implied by a count.
PREVIOUSLY_MISSING = ("ml/data/opp115_spans.py", "ml/data/opp115_dataset.py")


def test_the_closure_includes_the_modules_the_hand_written_list_missed():
    modules = required_modules(ROOT)
    for name in PREVIOUSLY_MISSING:
        assert name in modules, f"{name} is missing from the bundle again"


def test_the_closure_contains_the_entry_point_and_its_packages():
    modules = required_modules(ROOT)
    assert ENTRY_POINT in modules
    assert "ml/__init__.py" in modules, "ml is not importable as a package"
    assert "ml/data/__init__.py" in modules, "ml.data is not importable"


def test_every_module_in_the_closure_exists_on_disk():
    for name in required_modules(ROOT):
        assert (ROOT / name).is_file(), name


def test_the_closure_is_closed_under_its_own_imports():
    """No module in the bundle may import a first-party module outside it.

    This is the property the hand-written list violated, stated directly:
    walking the imports of everything carried must reach nothing new.
    """
    modules = set(required_modules(ROOT))
    for name in sorted(modules):
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module)

        for dotted in imported:
            if dotted.split(".")[0] not in LOCAL_ROOTS:
                continue
            candidates = {
                (ROOT / (dotted.replace(".", "/") + ".py")),
                (ROOT / dotted.replace(".", "/") / "__init__.py"),
            }
            resolved = {
                path.relative_to(ROOT).as_posix() for path in candidates if path.is_file()
            }
            assert resolved, f"{name} imports {dotted}, which does not resolve"
            assert resolved & modules, (
                f"{name} imports {dotted}, which the bundle does not carry"
            )


@pytest.mark.slow
def test_the_extracted_bundle_imports_with_the_repository_off_the_path(tmp_path):
    """The end-to-end check, and the one that would have caught the defect.

    The bundle is extracted into an empty directory and the entry point is
    imported in a subprocess whose working directory is that directory and
    whose PYTHONPATH does not include the repository. An import that only
    works from a full checkout fails here.
    """
    from ml.data.span_training_data import build_tagged_segments, write_jsonl

    bundle = tmp_path / "bundle.zip"
    dataset = write_jsonl(build_tagged_segments(), tmp_path / "tags.jsonl")
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(dataset, DATASET.as_posix())
        for name in required_modules(ROOT):
            archive.write(ROOT / name, name)

    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(extracted)

    result = subprocess.run(
        [sys.executable, "-c", "import ml.train_span_extractor as m; print(m.ENTRY_POINT if hasattr(m, 'ENTRY_POINT') else 'ok')"],
        cwd=extracted,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ""},
        timeout=120,
    )
    assert result.returncode == 0, (
        f"the extracted bundle does not import:\n{result.stderr}"
    )


@pytest.mark.slow
def test_the_extracted_bundle_runs_the_dry_run(tmp_path):
    """Not only importable: it must reproduce the split from the tags alone,
    with no OPP-115 corpus present."""
    from ml.data.span_training_data import build_tagged_segments, write_jsonl

    extracted = tmp_path / "extracted"
    extracted.mkdir()
    write_jsonl(build_tagged_segments(), extracted / DATASET)
    for name in required_modules(ROOT):
        target = extracted / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())

    result = subprocess.run(
        [sys.executable, ENTRY_POINT, "--dry-run"],
        cwd=extracted,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ""},
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert "2466" in result.stdout, "the extracted bundle saw a different dataset"
    # The approved split must survive the round trip through the bundle.
    assert "train               80" in result.stdout, result.stdout
    assert "offset verification" in result.stdout
