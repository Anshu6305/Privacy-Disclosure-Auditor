"""C-53 — the text_pattern_ops functional indexes.

Three things are checked here, and they are deliberately separate because the
failure modes are different:

1. **The models declare the two indexes.** A missing declaration makes the
   migration and the ORM disagree.
2. **PostgreSQL DDL carries the operator class.** This is the one that matters.
   Keying ``postgresql_ops`` on the column name rather than on the expression's
   label compiles with no error and no warning, and silently produces an index
   with the default operator class — one that looks correct in review and
   cannot serve F-01's predicate. Asserting only that the index exists would
   not catch it; C-15's test made exactly that mistake.
3. **SQLite receives valid DDL.** The operator class is a PostgreSQL concept.
   Under SQLite the same construct must compile to a plain functional index so
   the unit suite's in-memory databases still build.

What these tests cannot establish is whether PostgreSQL's planner *uses* the
indexes. That needs a server and lives in
``tests/integration/test_application_search_postgresql.py``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.db.models import Base
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex

VERSIONS = Path(__file__).resolve().parents[2] / "backend" / "migrations" / "versions"

PATTERN_INDEXES = {
    "ix_application_lower_name_pattern": "app_name",
    "ix_application_lower_package_pattern": "package_name",
}


def _load(filename: str):
    spec = importlib.util.spec_from_file_location(filename, VERSIONS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def baseline():
    return _load("0001_baseline_schema.py")


@pytest.fixture(scope="module")
def pattern_revision():
    return _load("0002_pattern_ops_search_indexes.py")


def _index(name: str):
    for index in Base.metadata.tables["application"].indexes:
        if index.name == name:
            return index
    raise AssertionError(f"{name} is not declared on the application table")


# ---------------------------------------------------------------------------
# 1. Declared in the models
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("index_name", sorted(PATTERN_INDEXES))
def test_pattern_index_is_declared_on_the_model(index_name: str):
    assert _index(index_name) is not None


def test_the_original_functional_indexes_are_retained():
    """C-53 is additive. Only the default operator class can serve
    ORDER BY lower(app_name), which F-01 issues alongside the predicate."""
    names = {ix.name for ix in Base.metadata.tables["application"].indexes}
    assert "ix_application_lower_name" in names
    assert "ix_application_lower_package" in names
    assert len(names & set(PATTERN_INDEXES)) == 2


# ---------------------------------------------------------------------------
# 2. The operator class actually reaches the PostgreSQL DDL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("index_name,column", sorted(PATTERN_INDEXES.items()))
def test_pattern_ops_opclass_is_emitted_for_postgresql(index_name: str, column: str):
    ddl = str(CreateIndex(_index(index_name)).compile(dialect=postgresql.dialect()))
    assert f"lower({column}) text_pattern_ops" in ddl, (
        f"{index_name} compiled to:\n    {ddl}\n"
        "The operator class is missing. postgresql_ops must be keyed on the "
        "expression's label, not on the column name: the latter is dropped "
        "silently and yields a default-opclass index that cannot serve a "
        "prefix LIKE."
    )


@pytest.mark.parametrize("index_name,column", sorted(PATTERN_INDEXES.items()))
def test_sqlite_receives_a_plain_functional_index(index_name: str, column: str):
    ddl = str(CreateIndex(_index(index_name)).compile(dialect=sqlite.dialect()))
    assert f"lower({column})" in ddl
    assert "text_pattern_ops" not in ddl


def test_the_baseline_indexes_carry_no_operator_class():
    """Evidence for C-53's premise, not a preference.

    If these ever compiled with an operator class the finding would be void,
    so the premise is asserted rather than assumed.
    """
    for name in ("ix_application_lower_name", "ix_application_lower_package"):
        ddl = str(CreateIndex(_index(name)).compile(dialect=postgresql.dialect()))
        assert "text_pattern_ops" not in ddl


# ---------------------------------------------------------------------------
# 3. The revision applies, and reverses, on SQLite
# ---------------------------------------------------------------------------


def _sqlite_index_sql(engine) -> dict[str, str]:
    with engine.connect() as connection:
        return {
            row[0]: row[1] or ""
            for row in connection.execute(
                text(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type = 'index' AND tbl_name = 'application'"
                )
            )
        }


@pytest.fixture
def upgraded_sqlite(baseline, pattern_revision):
    """Baseline then C-53's revision, applied to in-memory SQLite.

    This is the test that would have caught `sa.text("... text_pattern_ops")`,
    which compiles for both dialects and is rejected by SQLite at execution.
    """
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            baseline.upgrade()
            pattern_revision.upgrade()
        connection.commit()
        yield engine


def test_revision_applies_on_sqlite(upgraded_sqlite):
    present = _sqlite_index_sql(upgraded_sqlite)
    for index_name in PATTERN_INDEXES:
        assert index_name in present, (
            f"{index_name} was not created on SQLite. Present: "
            f"{sorted(present)}"
        )


def test_no_operator_class_syntax_reaches_sqlite(upgraded_sqlite):
    for index_name, sql in _sqlite_index_sql(upgraded_sqlite).items():
        assert "text_pattern_ops" not in sql, (
            f"{index_name} was created on SQLite carrying PostgreSQL operator "
            "class syntax"
        )


def test_the_baseline_indexes_survive_the_upgrade(upgraded_sqlite):
    present = _sqlite_index_sql(upgraded_sqlite)
    assert "ix_application_lower_name" in present
    assert "ix_application_lower_package" in present


def test_downgrade_removes_only_the_two_new_indexes(baseline, pattern_revision):
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            baseline.upgrade()
            before = set(_sqlite_index_sql(engine))
            pattern_revision.upgrade()
            after_upgrade = set(_sqlite_index_sql(engine))
            pattern_revision.downgrade()
            after_downgrade = set(_sqlite_index_sql(engine))
        connection.commit()

    assert after_upgrade - before == set(PATTERN_INDEXES)
    assert after_downgrade == before


def test_revision_chain(baseline, pattern_revision):
    assert baseline.revision == "0001_baseline"
    assert baseline.down_revision is None
    assert pattern_revision.revision == "0002_pattern_ops"
    assert pattern_revision.down_revision == "0001_baseline"
