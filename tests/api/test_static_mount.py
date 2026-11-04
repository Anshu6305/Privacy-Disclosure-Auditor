"""The SPA mount must not shadow the API.

Serving the frontend from the same FastAPI process is what keeps the
deployment at three containers. The risk that buys is a catch-all mount at "/"
swallowing API routes. These tests pin the precedence so a future change to
the mount cannot silently break every endpoint.
"""

import pytest
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def built_spa(tmp_path, monkeypatch):
    """A directory standing in for a real Vite build output."""
    (tmp_path / "index.html").write_text("<!doctype html><title>spa</title>", encoding="utf-8")

    import app.config as config_module

    def settings_with_static() -> Settings:
        return Settings(static_dir=tmp_path, app_env="test")

    monkeypatch.setattr(config_module, "get_settings", settings_with_static)
    monkeypatch.setattr("app.main.get_settings", settings_with_static)
    return tmp_path


def test_api_routes_win_over_the_static_mount(built_spa):
    with TestClient(create_app()) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_spa_is_served_at_the_root(built_spa):
    with TestClient(create_app()) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "spa" in response.text


def test_missing_build_directory_is_recorded_not_ignored(tmp_path, monkeypatch):
    """A STATIC_DIR pointing nowhere means the build stage produced nothing.

    The application still starts, so the API remains usable, but the condition
    is recorded rather than passed over in silence.
    """
    missing = tmp_path / "never_built"

    def settings_with_missing_static() -> Settings:
        return Settings(static_dir=missing, app_env="test")

    monkeypatch.setattr("app.main.get_settings", settings_with_missing_static)

    application = create_app()
    assert "does not exist" in application.state.static_warning

    with TestClient(application) as client:
        assert client.get("/api/health").status_code == 200
