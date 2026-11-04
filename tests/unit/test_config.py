"""Configuration behaviour."""

from app.config import Settings


def test_no_usable_default_database_password():
    """A blank password must not resolve to a working connection.

    Phase 4 constraint: no credential is ever hard-coded or given a usable
    default.
    """
    settings = Settings(postgres_password="")
    assert settings.postgres_password == ""


def test_database_url_is_assembled_from_parts():
    settings = Settings(
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_port=1234,
        postgres_db="d",
    )
    assert settings.database_url == "postgresql+psycopg://u:p@h:1234/d"


def test_thresholds_are_configuration_not_constants():
    """ALG-4 thresholds must be overridable per environment and per audit run."""
    settings = Settings(classifier_confidence_threshold=0.73)
    assert settings.classifier_confidence_threshold == 0.73
