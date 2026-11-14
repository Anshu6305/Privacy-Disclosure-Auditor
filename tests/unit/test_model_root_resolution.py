"""Where a relative `checkpoint_path` is resolved from.

`model_version.checkpoint_path` is stored relative, so the checkout can move.
`load_for_model_version` defaulted its `repository_root` to ".", which is the
process's working directory, not the checkout. A worker started from
`backend/` therefore looked for `backend/ml/checkpoints/improved_classifier`
and reported the improved checkpoint missing while it sat at the real path one
level up, and audit 9 was marked failed for a model that was present (C-97).

The default is now derived from the package's own location, so it is the same
path from any cwd. Same family as C-74 (a registry pointing at a directory the
trainer never wrote) and C-85 (the policy path contract).
"""

from __future__ import annotations

import pytest
from app.config import PROJECT_ROOT
from app.db.models import ModelVersion
from app.services.model_registry import (
    DEFAULT_REPOSITORY_ROOT,
    ModelsUnavailableError,
    load_for_model_version,
)

from analysis.vocabulary import (
    TASK_CLASSIFICATION,
    VARIANT_BASELINE,
    VARIANT_IMPROVED,
)

ABSENT = "ml/checkpoints/definitely-not-here"


def model(variant: str = VARIANT_IMPROVED, path: str = ABSENT) -> ModelVersion:
    return ModelVersion(
        task=TASK_CLASSIFICATION,
        variant=variant,
        model_identifier=f"real/{variant}",
        version_label=f"{variant}-v1",
        checkpoint_path=path,
        is_active=True,
    )


def test_the_default_root_is_the_checkout_not_the_working_directory():
    assert DEFAULT_REPOSITORY_ROOT == PROJECT_ROOT
    assert DEFAULT_REPOSITORY_ROOT.is_absolute()
    # Markers that make this the checkout rather than any parent of it.
    assert (DEFAULT_REPOSITORY_ROOT / "backend").is_dir()
    assert (DEFAULT_REPOSITORY_ROOT / "ml").is_dir()


def test_a_relative_checkpoint_resolves_against_the_checkout_from_any_cwd(
    monkeypatch, tmp_path
):
    """The regression. Run from somewhere else, the loader must still name a
    path inside the repository."""
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ModelsUnavailableError) as raised:
        load_for_model_version(model())

    message = str(raised.value)
    assert str(PROJECT_ROOT) in message, (
        "the loader resolved the checkpoint against the working directory"
    )
    assert str(tmp_path) not in message


def test_the_baseline_variant_resolves_the_same_way(monkeypatch, tmp_path):
    """One default serves all three tasks, so the baseline must not keep the
    old cwd-relative behaviour."""
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ModelsUnavailableError) as raised:
        load_for_model_version(model(variant=VARIANT_BASELINE))

    assert str(PROJECT_ROOT) in str(raised.value)


def test_an_explicit_root_still_wins(tmp_path):
    """Callers that pass a root - every test that builds a fixture tree - are
    unaffected by the changed default."""
    with pytest.raises(ModelsUnavailableError) as raised:
        load_for_model_version(model(), repository_root=tmp_path)

    assert str(tmp_path) in str(raised.value)


def test_an_absolute_checkpoint_path_is_not_rerooted(tmp_path):
    """A row may record an absolute path; the root must not be prepended."""
    absolute = tmp_path / "somewhere" / "checkpoint"

    with pytest.raises(ModelsUnavailableError) as raised:
        load_for_model_version(model(path=str(absolute)))

    assert str(absolute) in str(raised.value)
    assert str(PROJECT_ROOT / str(absolute).lstrip("/")) not in str(raised.value)
