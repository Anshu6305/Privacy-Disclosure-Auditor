"""Revision 0003 — the restored single collection-event snapshot (D-1 Option A).

Covers what SQLite can answer: that the revision applies, that it reverses,
that the resulting columns are the ones the models declare, and that the
guard against restructuring a populated table actually fires.

What SQLite cannot answer — real `timestamptz`, `BIGINT` widths, and whether
PostgreSQL enforces the seven new CHECK constraints rather than merely
accepting them — is covered in `tests/integration/test_postgresql_schema.py`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.db.models import Base
from sqlalchemy import create_engine, inspect, text

VERSIONS = Path(__file__).resolve().parents[2] / "backend" / "migrations" / "versions"

REVISION_FILES = (
    "0001_baseline_schema.py",
    "0002_pattern_ops_search_indexes.py",
    "0003_collection_event_snapshot.py",
)

#: The approved Phase 3 section 10.2 shape, as restored.
COLLECTION_EVENT_COLUMNS = {
    "snapshot_id",
    "app_id",
    "collected_at",
    "source_url_listing",
    "source_url_policy",
    "retrieval_mode",
    "policy_doc_path",
    "policy_doc_sha256",
    "policy_doc_bytes",
    "policy_http_status",
    "status",
    "declares_no_data_collected",
    "is_active",
}

#: What the deviated per-source structure had, and what a downgrade restores.
PER_SOURCE_COLUMNS = {
    "snapshot_id",
    "app_id",
    "source_type",
    "source_url",
    "retrieved_at",
    "retrieval_method",
    "storage_path",
    "content_sha256",
    "content_bytes",
    "http_status",
    "is_active",
}


def _load(filename: str):
    spec = importlib.util.spec_from_file_location(filename, VERSIONS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def revisions() -> list:
    return [_load(name) for name in REVISION_FILES]


def _apply(connection, modules) -> None:
    """Each revision in its own operations context.

    A batch operation is planned against the table as reflected when its batch
    opens, so revisions are not collapsed into one context.
    """
    for module in modules:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()


@pytest.fixture
def upgraded(revisions):
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        _apply(connection, revisions)
        connection.commit()
        yield engine, connection, revisions


def columns(engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


# ---------------------------------------------------------------------------
# Chain
# ---------------------------------------------------------------------------


def test_revision_chain(revisions):
    baseline, pattern, collection = revisions
    assert baseline.revision == "0001_baseline"
    assert pattern.down_revision == "0001_baseline"
    assert collection.revision == "0003_collection_event"
    assert collection.down_revision == "0002_pattern_ops"


def test_the_frozen_baseline_is_not_involved():
    """0003 must not edit the historical record it builds on."""
    source = (VERSIONS / "0001_baseline_schema.py").read_text(encoding="utf-8")
    for introduced in ("source_url_listing", "collection_event", "declares_no_data"):
        assert introduced not in source


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def test_snapshot_becomes_a_collection_event(upgraded):
    engine, _connection, _revisions = upgraded
    assert columns(engine, "disclosure_snapshot") == COLLECTION_EVENT_COLUMNS


def test_the_migrated_columns_are_exactly_what_the_models_declare(upgraded):
    """The migration and the ORM must not drift apart."""
    engine, _connection, _revisions = upgraded
    declared = set(Base.metadata.tables["disclosure_snapshot"].columns.keys())
    assert columns(engine, "disclosure_snapshot") == declared


def test_audit_run_references_one_snapshot(upgraded):
    engine, _connection, _revisions = upgraded
    snapshot_fks = {
        fk["constrained_columns"][0]
        for fk in inspect(engine).get_foreign_keys("audit_run")
        if fk["referred_table"] == "disclosure_snapshot"
    }
    assert snapshot_fks == {"snapshot_id"}
    assert "ds_snapshot_id" not in columns(engine, "audit_run")
    assert "policy_snapshot_id" not in columns(engine, "audit_run")


def test_indexes_follow_the_renamed_columns(upgraded):
    engine, _connection, _revisions = upgraded
    names = {index["name"] for index in inspect(engine).get_indexes("disclosure_snapshot")}
    assert "ix_snapshot_app_collected" in names
    assert "ix_snapshot_policy_sha256" in names
    assert "ix_snapshot_app_source" not in names
    assert "ix_snapshot_sha256" not in names


def test_status_has_no_default_after_the_upgrade(upgraded):
    """The NOT NULL is added with a temporary server default so it can be
    applied in one step. If that default survived, a caller could omit the
    status and silently record `fetch_failed` for a successful event."""
    engine, _connection, _revisions = upgraded
    (status,) = [
        column
        for column in inspect(engine).get_columns("disclosure_snapshot")
        if column["name"] == "status"
    ]
    assert status["nullable"] is False
    assert status["default"] is None


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def test_downgrade_restores_the_previous_structure(upgraded):
    engine, connection, revisions = upgraded
    with Operations.context(MigrationContext.configure(connection)):
        revisions[-1].downgrade()
    connection.commit()

    assert columns(engine, "disclosure_snapshot") == PER_SOURCE_COLUMNS
    snapshot_fks = {
        fk["constrained_columns"][0]
        for fk in inspect(engine).get_foreign_keys("audit_run")
        if fk["referred_table"] == "disclosure_snapshot"
    }
    assert snapshot_fks == {"ds_snapshot_id", "policy_snapshot_id"}


def test_downgrade_then_upgrade_is_stable(upgraded):
    """Reversibility is only useful if it round-trips."""
    engine, connection, revisions = upgraded
    for step in (revisions[-1].downgrade, revisions[-1].upgrade):
        with Operations.context(MigrationContext.configure(connection)):
            step()
        connection.commit()
    assert columns(engine, "disclosure_snapshot") == COLLECTION_EVENT_COLUMNS


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_upgrade_refuses_to_restructure_a_populated_table(revisions):
    """Two per-source rows cannot be merged into one collection event.

    Nothing in the old structure records which declaration row belongs with
    which policy row, so any automatic merge would be a guess. The revision
    stops instead, and this test is what proves it stops rather than guessing.
    """
    baseline, pattern, collection = revisions
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        _apply(connection, [baseline, pattern])
        connection.execute(
            text(
                "INSERT INTO application (app_id, package_name, app_name, "
                "first_seen_at) VALUES (1, 'com.example.x', 'X', '2026-11-05')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO disclosure_snapshot (snapshot_id, app_id, source_type, "
                "source_url, retrieved_at, retrieval_method, content_sha256, "
                "is_active) VALUES (1, 1, 'privacy_policy', 'https://x/p', "
                f"'2026-11-05', 'manual_import', '{'a' * 64}', 1)"
            )
        )
        connection.commit()

        with (
            pytest.raises(RuntimeError) as raised,
            Operations.context(MigrationContext.configure(connection)),
        ):
            collection.upgrade()

    # A refusal that does not say what to do instead is just an obstacle, so
    # the recovery path is part of what is asserted.
    message = str(raised.value)
    assert "disclosure_snapshot holds 1 row" in message
    assert "Re-import from the filesystem corpus" in message
    assert "M3_ACQUISITION_REPORT.md" in message


# ---------------------------------------------------------------------------
# The verification script must not hard-code a revision
# ---------------------------------------------------------------------------

VERIFY_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "verify_migrations.sh"
)


def _executable_lines(text: str) -> list[str]:
    """Lines that run, with whole-line comments removed."""
    return [
        line
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_the_verification_script_derives_head_and_base_from_the_graph(revisions):
    """Why this test exists.

    The script asserted the literal ``0002_pattern_ops`` and failed the moment
    ``0003_collection_event`` was added: a correctly migrated database was
    reported as a failure. That is the same category error as C-56 — asserting
    a fixed position that something else had moved — so it is fixed the same
    way, and locked down here so it cannot come back at revision 0004.
    """
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert '== "$HEAD_REV"' in script
    assert '== "$BASE_REV"' in script

    identifiers = {module.revision for module in revisions}
    offenders = [
        line
        for line in _executable_lines(script)
        if any(identifier in line for identifier in identifiers)
    ]
    assert not offenders, (
        "the verification script names a revision identifier in a line that "
        "runs, so it will break when the next revision is added:\n"
        + "\n".join(offenders)
    )


def test_the_verification_script_never_drops_a_database():
    """Its own safety claim, asserted rather than trusted."""
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")
    for destructive in ("DROP DATABASE", "DROP TABLE", "TRUNCATE", "down -v"):
        for line in _executable_lines(script):
            assert destructive not in line, f"{destructive!r} appears in: {line}"


def test_every_earlier_disposable_database_is_protected():
    """A re-run must never reuse a database an earlier run created."""
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")
    target = next(
        line.split("=", 1)[1].strip().strip('"')
        for line in _executable_lines(script)
        if line.startswith("DISPOSABLE_DB=")
    )
    protected_block = script[script.index("PROTECTED=(") :]
    protected_block = protected_block[: protected_block.index(")")]

    for required in (
        "privacy_auditor",
        "privacy_auditor_test",
        "privacy_auditor_frozen_20261105_test",
        "privacy_auditor_m3b_20261105_test",
    ):
        assert f'"{required}"' in protected_block, f"{required} is not protected"
    assert f'"{target}"' not in protected_block, (
        f"the target {target!r} is in PROTECTED, so the run would abort"
    )


# ---------------------------------------------------------------------------
# Revision gates must ask about ancestry, not about the current revision
# ---------------------------------------------------------------------------


def _script_directory():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend = Path(__file__).resolve().parents[2] / "backend"
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    return ScriptDirectory.from_config(config)


def test_a_revision_gate_opens_at_every_later_revision():
    """The question a skip guard must ask.

    ``alembic_version`` holds one value. Asking whether it *equals* a revision
    answers "is the database exactly here", not "has this revision been
    applied" — and the two diverge the moment anything is added on top. That
    mistake made seven C-53 tests skip on a fully migrated database, after the
    same error had already produced C-56 and C-60.

    Ancestry is the right question, and this asserts it behaves at every point
    on the chain rather than only at today's head.
    """
    scripts = _script_directory()
    head = scripts.get_current_head()
    chain = [s.revision for s in scripts.iterate_revisions(head, "base")][::-1]
    assert chain[0] == "0001_baseline"
    assert "0002_pattern_ops" in chain

    gate = "0002_pattern_ops"
    opens_at = chain[chain.index(gate) :]
    closed_at = chain[: chain.index(gate)]

    for revision in opens_at:
        ancestry = {s.revision for s in scripts.iterate_revisions(revision, "base")}
        assert gate in ancestry, (
            f"a database at {revision} has {gate} applied, so the gate must "
            "open there"
        )

    for revision in closed_at:
        ancestry = {s.revision for s in scripts.iterate_revisions(revision, "base")}
        assert gate not in ancestry, (
            f"a database at {revision} does not have {gate} applied, so the "
            "gate must stay closed"
        )


def test_the_integration_gate_uses_ancestry():
    """Locked down in the source, so it cannot regress to an equality check."""
    gate_file = (
        Path(__file__).resolve().parents[1]
        / "integration"
        / "test_application_search_postgresql.py"
    )
    source = gate_file.read_text(encoding="utf-8")
    assert "iterate_revisions" in source, (
        "the revision gate no longer consults the migration graph"
    )
