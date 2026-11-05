"""Application configuration.

Every value is read from the environment. Nothing is hard-coded, and no
credential has a usable default — a missing database password is a startup
error rather than a silent fallback.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: The repository root, derived from this file's location rather than from the
#: current working directory.
#:
#: This matters. ``.env`` lives at the repository root, but Alembic must be run
#: from ``backend/`` because that is where ``alembic.ini`` is. A relative
#: ``env_file=".env"`` therefore resolved to ``backend/.env``, which does not
#: exist, so no password was loaded and migrations failed before touching the
#: database. Anchoring the path here makes configuration independent of where a
#: command happens to be run from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Database ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "privacy_auditor"
    postgres_user: str = "auditor"
    postgres_password: str = Field(
        default="",
        description="Required in any non-test environment. No default is provided.",
    )

    # --- Application ---
    app_env: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    policy_storage_dir: Path = Path("./data/policies/raw")

    # Directory holding the built single-page application. Set in the container
    # image; absent during development, where Vite serves the SPA on port 5173.
    static_dir: Path | None = None

    # --- Analysis thresholds (ALG-4) ---
    # Placeholders until tuned on the gold set in Milestone 6. They are
    # configuration, not measured results, and are recorded per audit run in
    # audit_run.threshold_config so any report can be reproduced.
    classifier_confidence_threshold: float = 0.50
    span_confidence_threshold: float = 0.50
    alignment_confidence_threshold: float = 0.50

    # --- Worker ---
    worker_poll_interval_seconds: int = 2
    worker_claim_timeout_seconds: int = 900

    # --- Acquisition (NFR-15 rate limiting) ---
    acquisition_request_delay_seconds: float = 3.0
    acquisition_user_agent: str = "KIIT-MajorProject-Research/1.0"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production_like(self) -> bool:
        return self.app_env not in {"development", "test"}


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Used as a FastAPI dependency."""
    return Settings()
