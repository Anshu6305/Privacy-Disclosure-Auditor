"""The baseline migration is frozen and equivalent to the models.

Two different things are checked here, and both matter.

**Frozen.** The revision must build the schema from explicit operations, not
from ``Base.metadata.create_all()``. A metadata build is not a historical
record: it produces whatever the models say when it runs, so two databases
stamped with the same revision can have different schemas.

**Equivalent.** Running the revision against an empty database must produce
the schema the models currently describe. If someone changes a model without
adding a new revision, these tests fail — which is exactly the drift that a
frozen baseline is meant to make visible.

These run on SQLite, which is enough to compare tables, columns, nullability,
indexes and constraint names. The authoritative check is
``tests/integration/test_postgresql_schema.py`` against a real server.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.db.models import Base
from sqlalchemy import create_engine, inspect

REVISION_PATH = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "migrations"
    / "versions"
    / "0001_baseline_schema.py"
)


@pytest.fixture(scope="module")
def revision():
    spec = importlib.util.spec_from_file_location("baseline_revision", REVISION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def migrated_engine(revision):
    """An empty database with the frozen revision applied to it."""
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
        connection.commit()
        yield engine


# ---------------------------------------------------------------------------
# Frozen
# ---------------------------------------------------------------------------


def test_revision_does_not_build_from_metadata():
    """The defect this freeze exists to remove.

    The check is on the function bodies, not the whole file: the module
    docstring legitimately names create_all while explaining why it is gone,
    and a naive substring search on the source would flag that prose.
    """
    import ast

    source = REVISION_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    bodies = [
        ast.get_source_segment(source, node) or ""
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in {"upgrade", "downgrade"}
    ]
    assert len(bodies) == 2, "upgrade and downgrade must both be defined"

    for body in bodies:
        assert "create_all" not in body, (
            "the baseline builds from model metadata again; it is no longer a "
            "fixed historical record"
        )
        assert "drop_all" not in body


def test_revision_uses_explicit_operations():
    source = REVISION_PATH.read_text(encoding="utf-8")
    assert source.count("op.create_table(") == 16
    assert source.count("op.create_index(") == 21
    assert source.count("op.drop_table(") == 16


def test_revision_identity_is_unchanged(revision):
    """Rewriting the body is safe only because nothing had been stamped with
    it. The identity must stay the same so no history is invalidated."""
    assert revision.revision == "0001_baseline"
    assert revision.down_revision is None
    assert revision.EXPECTED_TABLE_COUNT == 16


# ---------------------------------------------------------------------------
# Equivalent to the models
# ---------------------------------------------------------------------------


def test_migration_creates_exactly_the_model_tables(migrated_engine):
    created = set(inspect(migrated_engine).get_table_names())
    assert created == set(Base.metadata.tables)
    assert len(created) == 16


def test_every_column_matches_the_models(migrated_engine):
    """Name and nullability, table by table.

    This is what catches a model change that was never given a revision.
    """
    inspector = inspect(migrated_engine)
    mismatches: list[str] = []

    for name, table in sorted(Base.metadata.tables.items()):
        migrated = {c["name"]: c for c in inspector.get_columns(name)}
        expected = {c.name: c for c in table.columns}

        only_in_models = sorted(set(expected) - set(migrated))
        only_in_migration = sorted(set(migrated) - set(expected))
        if only_in_models:
            mismatches.append(f"{name}: in models, not in migration: {only_in_models}")
        if only_in_migration:
            mismatches.append(f"{name}: in migration, not in models: {only_in_migration}")

        for column in sorted(set(expected) & set(migrated)):
            if bool(migrated[column]["nullable"]) != bool(expected[column].nullable):
                mismatches.append(
                    f"{name}.{column}: nullable differs "
                    f"(migration {migrated[column]['nullable']}, "
                    f"models {expected[column].nullable})"
                )

    assert not mismatches, "schema drift between the migration and the models:\n" + "\n".join(
        mismatches
    )


def test_every_index_matches_the_models(migrated_engine):
    inspector = inspect(migrated_engine)

    migrated: set[str] = set()
    for name in Base.metadata.tables:
        migrated.update(ix["name"] for ix in inspector.get_indexes(name))

    expected = {
        ix.name for table in Base.metadata.tables.values() for ix in table.indexes
    }

    # SQLite does not reflect expression-based indexes, so the two functional
    # lower() indexes are checked in the migration source instead. They are
    # verified for real against PostgreSQL in the integration suite.
    functional = {"ix_application_lower_name", "ix_application_lower_package"}
    source = REVISION_PATH.read_text(encoding="utf-8")
    for index_name in functional:
        assert index_name in source
        assert "lower(" in source

    assert (expected - functional) == migrated


def test_unique_constraints_match_the_models(migrated_engine):
    from sqlalchemy import UniqueConstraint

    inspector = inspect(migrated_engine)
    migrated: set[str] = set()
    for name in Base.metadata.tables:
        migrated.update(
            uc["name"] for uc in inspector.get_unique_constraints(name) if uc["name"]
        )

    expected = {
        c.name
        for table in Base.metadata.tables.values()
        for c in table.constraints
        if isinstance(c, UniqueConstraint) and c.name
    }
    assert migrated == expected
    assert len(expected) == 8


def test_check_constraints_match_the_models(migrated_engine):
    from sqlalchemy import CheckConstraint

    inspector = inspect(migrated_engine)
    migrated: set[str] = set()
    for name in Base.metadata.tables:
        migrated.update(
            cc["name"] for cc in inspector.get_check_constraints(name) if cc["name"]
        )

    expected = {
        c.name
        for table in Base.metadata.tables.values()
        for c in table.constraints
        if isinstance(c, CheckConstraint) and c.name
    }
    assert migrated == expected
    assert len(expected) == 28


def test_foreign_keys_match_the_models(migrated_engine):
    inspector = inspect(migrated_engine)
    migrated = sum(
        len(inspector.get_foreign_keys(name)) for name in Base.metadata.tables
    )
    expected = sum(len(t.foreign_keys) for t in Base.metadata.tables.values())
    assert migrated == expected == 27


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def test_downgrade_removes_everything(revision):
    """A rollback that leaves tables behind is not a rollback."""
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            connection.commit()
            assert len(inspect(engine).get_table_names()) == 16

            revision.downgrade()
            connection.commit()
            assert inspect(engine).get_table_names() == []
