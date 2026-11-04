"""Shared test configuration.

Unit tests run without any external service. The database password is left
unset so that `engine_or_none()` returns None and any code path that assumes a
live database fails loudly instead of silently connecting somewhere.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("APP_ENV", "test")


@pytest.fixture
def api_client():
    """TestClient for the FastAPI application."""
    from app.main import create_app
    from fastapi.testclient import TestClient

    with TestClient(create_app()) as client:
        yield client


def pytest_configure(config):
    """Fail early and clearly on an unsupported Python version.

    The pinned scientific stack publishes wheels for CPython 3.10 to 3.13. On
    3.14 or newer, pip compiles scipy from source and the install fails with a
    meson/OpenBLAS error that says nothing about the Python version. Catching
    it here turns a confusing build failure into one sentence.
    """
    if sys.version_info >= (3, 14):
        raise pytest.UsageError(
            f"Python {sys.version_info.major}.{sys.version_info.minor} is not "
            "supported. The pinned dependencies publish wheels for 3.10 to 3.13; "
            "on 3.14 pip builds scipy from source and fails. Recreate the "
            "virtual environment with Python 3.12, which is also what the "
            "container runs:\n"
            "    brew install python@3.12\n"
            "    rm -rf .venv && python3.12 -m venv .venv\n"
            "    .venv/bin/pip install -r backend/requirements.txt "
            "-r backend/requirements-dev.txt"
        )
