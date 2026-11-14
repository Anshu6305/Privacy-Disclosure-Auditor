"""The `scripts/request_audit.py` output block.

The CLI printed `result.status`, which `AuditRequested` does not have, so a
successful resolution crashed with `AttributeError` at the first line of
output — after the row had been inserted in the session but before the
apply/rollback branch. Nothing persisted, because the `Session` context
manager closes without committing, but the operator saw a traceback instead
of the resolved version set.

These tests drive `main()` end to end against SQLite, so any attribute the
output block names has to exist, and they pin which of the two branches
writes.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from app.db.models import (
    Application,
    AuditRun,
    Base,
    DisclosureSnapshot,
    ModelVersion,
    TaxonomyMappingVersion,
)
from app.services.audit_service import AuditRequested
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from analysis.vocabulary import (
    SNAPSHOT_COMPLETE,
    TASK_ALIGNMENT,
    TASK_CLASSIFICATION,
    TASK_SPAN_EXTRACTION,
    VARIANT_BASELINE,
    VARIANT_IMPROVED,
)

PACKAGE = "com.example.cli"
SET = [
    "--model",
    f"{TASK_CLASSIFICATION}=improved-classifier-v1",
    "--model",
    f"{TASK_SPAN_EXTRACTION}=span-extractor-v1",
    "--model",
    f"{TASK_ALIGNMENT}=zeroshot-nli-v1",
]


@pytest.fixture
def database(tmp_path) -> str:
    """A registry shaped like the pilot's: improved exists for the classifier
    only, which is why the set is stated explicitly."""
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        application = Application(package_name=PACKAGE, app_name="CLI App")
        session.add(application)
        session.flush()
        session.add(
            DisclosureSnapshot(
                app_id=application.app_id,
                collected_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
                source_url_listing="https://play.google.com/x",
                source_url_policy="https://example.invalid/p",
                retrieval_mode="manual_import",
                policy_doc_path="data/policies/raw/p.html",
                policy_doc_sha256="a" * 64,
                status=SNAPSHOT_COMPLETE,
                declares_no_data_collected=False,
            )
        )
        session.add(TaxonomyMappingVersion(version_label="map-v1", is_active=True))
        for task, variant, label in (
            (TASK_CLASSIFICATION, VARIANT_IMPROVED, "improved-classifier-v1"),
            (TASK_SPAN_EXTRACTION, VARIANT_BASELINE, "span-extractor-v1"),
            (TASK_ALIGNMENT, VARIANT_BASELINE, "zeroshot-nli-v1"),
        ):
            session.add(
                ModelVersion(
                    task=task,
                    variant=variant,
                    model_identifier=f"real/{label}",
                    version_label=label,
                    checkpoint_path=f"ml/checkpoints/{label}",
                    is_active=True,
                )
            )
        session.commit()
    return url


def run_cli(monkeypatch, url: str, *extra: str) -> int:
    import scripts.request_audit as cli

    monkeypatch.setattr(
        "sys.argv",
        ["request_audit.py", PACKAGE, "--database-url", url, *SET, *extra],
    )
    return cli.main()


def audits(url: str) -> list[AuditRun]:
    with Session(create_engine(url)) as session:
        return list(session.execute(select(AuditRun)).scalars().all())


def test_the_dry_run_prints_the_resolved_set_without_crashing(
    monkeypatch, database, capsys
):
    """The regression. Before the fix this raised AttributeError here."""
    assert run_cli(monkeypatch, database) == 0

    out = capsys.readouterr().out
    assert "audit 1" in out
    assert "improved-classifier-v1" in out
    assert "rolled back, no audit was created" in out


def test_the_dry_run_creates_no_audit(monkeypatch, database):
    run_cli(monkeypatch, database)

    assert audits(database) == []


def test_apply_commits_one_queued_audit(monkeypatch, database, capsys):
    assert run_cli(monkeypatch, database, "--apply") == 0
    assert "Committed" in capsys.readouterr().out

    rows = audits(database)
    assert len(rows) == 1
    assert rows[0].status == "queued"


def test_every_result_attribute_the_output_names_exists():
    """Structural guard, so a typo cannot reach an operator as a traceback.

    The crash was not that the status was wrong; it was that the field did
    not exist. Reading the source rather than the output catches that for
    every attribute, including ones a happy-path test never prints.
    """
    source = Path("scripts/request_audit.py").read_text(encoding="utf-8")
    fields = {field.name for field in dataclasses.fields(AuditRequested)}

    named = set(re.findall(r"\bresult\.([a-zA-Z_][a-zA-Z0-9_]*)", source))
    # `reason` and `detail` belong to the refusal branch, not to this class.
    named -= {"reason", "detail"}

    assert named, "the output block reads nothing from the result"
    assert named <= fields, (
        f"the CLI reads {sorted(named - fields)} from AuditRequested, which "
        f"has {sorted(fields)}"
    )
