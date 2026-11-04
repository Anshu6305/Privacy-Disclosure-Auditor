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
