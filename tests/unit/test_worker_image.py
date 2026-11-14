"""The API/worker image's build contract.

`backend/Dockerfile` is one image serving the API and the worker. Two of its
properties are easy to break and expensive to discover, because they only
show up during a build or on the first audit a container claims:

* a compiler must be installed before the requirements layer - spaCy is
  pinned at 3.8.3, which publishes no Linux wheel for aarch64, so pip builds
  it from source and the build fails without gcc (C-95);
* the ML dependency set must stay out, because it is over 2 GB.

These assertions read the Dockerfile. They cannot replace a real build, and
the build has to be run on a host with Docker.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCKERFILE = Path("backend/Dockerfile")


@pytest.fixture(scope="module")
def lines() -> list[str]:
    return DOCKERFILE.read_text(encoding="utf-8").splitlines()


def index_of(lines: list[str], pattern: str) -> int:
    for number, line in enumerate(lines):
        if re.search(pattern, line) and not line.lstrip().startswith("#"):
            return number
    raise AssertionError(f"no uncommented line matching {pattern!r}")


def test_a_compiler_is_installed_before_the_requirements_are_built(lines):
    """The build failure this guards: spaCy 3.8.3 has no aarch64 wheel, so on
    an arm64 host pip compiles it and needs gcc and g++."""
    compiler = index_of(lines, r"apt-get install.*build-essential")
    requirements = index_of(lines, r"pip install -r backend/requirements\.txt")

    assert compiler < requirements, (
        "build-essential must be installed before the pip layer that builds "
        "spaCy from source"
    )


def test_the_runtime_library_psycopg_needs_is_still_installed(lines):
    assert index_of(lines, r"apt-get install.*libpq5") >= 0


def test_the_spacy_model_f09_needs_is_installed(lines):
    """pip does not install it; without it segmentation raises
    SegmenterUnavailableError on every audit."""
    model = index_of(lines, r"spacy download en_core_web_sm")
    requirements = index_of(lines, r"pip install -r backend/requirements\.txt")

    assert requirements < model, "spaCy itself must be installed first"


def test_the_multi_gigabyte_ml_set_is_not_installed(lines):
    """Over 2 GB, and the approved image does not carry it. If this ever has
    to change it should be a decision, not a drifted line."""
    with pytest.raises(AssertionError):
        index_of(lines, r"pip install -r backend/requirements-ml\.txt")
