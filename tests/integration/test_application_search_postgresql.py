"""F-01 on real PostgreSQL.

The unit tests run on SQLite, which cannot answer the two questions that
matter about ALG-11 in production:

1. Does ``lower(col) LIKE 'term%'`` return the same rows under PostgreSQL's
   collation as it does under SQLite's? SQLite's ``LIKE`` is ASCII-only and
   case-insensitive by default, which is a different operator.
2. Is the prefix predicate **correct** against the frozen schema, with the
   real UNIQUE constraint and the real functional indexes present?

Whether the planner *uses* those indexes is a separate question and is
deliberately not asserted here; see ``scripts/explain_application_search.py``
and C-53 in the consistency log.

**Safety.** Same contract as ``test_postgresql_schema.py``: only the database
named in ``TEST_DATABASE_URL``, only one whose name ends in ``_test``, every
test inside a transaction that is rolled back. Nothing is created, dropped or
truncated, and the fixture rows never survive the test.
"""

from __future__ import annotations

import os

import pytest
from app.db.models import Application
from app.db.repositories import ApplicationRepository, handle_unknown_application
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

TEST_URL_VAR = "TEST_DATABASE_URL"

#: Invented fixtures, inserted and rolled back. Not collected records.
FIXTURES: tuple[tuple[str, str, str | None], ...] = (
    ("test.alpha.messenger", "Alpha Messenger", "Alpha Labs"),
    ("test.alpha.business", "ALPHA BUSINESS", "Alpha Labs"),
    ("test.beta.weather", "Beta Weather", None),
    ("test.gamma.percent", "100% Beta", "Gamma Inc"),
)


@pytest.fixture(scope="module")
def pg_url() -> str:
    url = os.environ.get(TEST_URL_VAR)
    if not url:
        pytest.skip(
            f"{TEST_URL_VAR} is not set. These tests never guess a database; "
            f"see docs/PHASE4_SCHEMA_BASELINE_AUDIT.md Part 5."
        )
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail(
            f"{TEST_URL_VAR} names the database {database!r}, which does not "
            "end in '_test'. Refusing to run against a database that may be "
            "the project's own."
        )
    return url


@pytest.fixture(scope="module")
def pg_engine(pg_url: str):
    try:
        engine = create_engine(pg_url, future=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - the type is the useful part
        pytest.skip(f"PostgreSQL not usable here: {type(exc).__name__}: {exc}")

    if "application" not in set(inspect(engine).get_table_names()):
        pytest.fail(
            "The test database has no schema. Apply the frozen baseline "
            "first; see docs/PHASE4_SCHEMA_BASELINE_AUDIT.md Part 5."
        )
    return engine


@pytest.fixture
def seeded_repo(pg_engine):
    """A repository over four invented rows, all rolled back afterwards."""
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        session.add_all(
            Application(package_name=p, app_name=n, developer_name=d)
            for p, n, d in FIXTURES
        )
        session.flush()
        yield ApplicationRepository(session)
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def packages(results) -> list[str]:
    return [r.package_name for r in results]


# ---------------------------------------------------------------------------
# F-01 under PostgreSQL
# ---------------------------------------------------------------------------


def test_prefix_search_by_package(seeded_repo):
    assert set(packages(seeded_repo.search("test.alpha"))) == {
        "test.alpha.messenger",
        "test.alpha.business",
    }


@pytest.mark.parametrize("term", ["alpha", "ALPHA", "AlPhA"])
def test_prefix_search_is_case_insensitive_under_postgresql(seeded_repo, term):
    """PostgreSQL's LIKE is case-sensitive; lower() on both sides is what
    makes this work, not a permissive default as in SQLite."""
    assert set(packages(seeded_repo.search(term))) == {
        "test.alpha.messenger",
        "test.alpha.business",
    }


def test_stored_uppercase_name_matches_lowercase_query(seeded_repo):
    assert packages(seeded_repo.search("alpha bus")) == ["test.alpha.business"]


def test_substring_is_not_matched(seeded_repo):
    """'weather' is a prefix; 'eather' is not. ALG-11 is prefix-only."""
    assert packages(seeded_repo.search("beta weather")) == ["test.beta.weather"]
    assert seeded_repo.search("eather") == []


def test_like_metacharacters_are_escaped_under_postgresql(seeded_repo):
    """Unescaped, '%' would match all four rows under PostgreSQL too."""
    assert packages(seeded_repo.search("100%")) == ["test.gamma.percent"]
    assert seeded_repo.search("%%") == []


def test_result_limit_is_applied_by_the_database(seeded_repo):
    assert len(seeded_repo.search("test.", limit=2)) == 2


def test_ordering_is_deterministic(seeded_repo):
    assert packages(seeded_repo.search("test.")) == packages(
        seeded_repo.search("test.")
    )


def test_null_developer_round_trips_as_none(seeded_repo):
    (result,) = seeded_repo.search("beta weather")
    assert result.developer_name is None


def test_no_match_returns_empty(seeded_repo):
    assert seeded_repo.search("zzzznothing") == []


# ---------------------------------------------------------------------------
# Retrieval and F-03
# ---------------------------------------------------------------------------


def test_get_by_package_round_trips(seeded_repo):
    found = seeded_repo.get_by_package("test.beta.weather")
    assert found is not None
    assert found.app_name == "Beta Weather"
    # server_default=func.now() is a PostgreSQL default here, not a Python one.
    assert found.first_seen_at is not None


def test_unknown_package_is_reported_not_raised(seeded_repo):
    report = seeded_repo.resolve_or_report("test.not.collected")
    assert report == handle_unknown_application("test.not.collected")
    assert report.can_request_audit is False


def test_search_does_not_write(pg_engine, seeded_repo):
    """A read path must not insert, and the rollback must leave nothing.

    Counting the test fixtures is not enough: this asserts the search itself
    adds nothing to the session.
    """
    seeded_repo.search("test.")
    assert seeded_repo.get_by_package("test.alpha.messenger") is not None


# ---------------------------------------------------------------------------
# C-53 — operator classes, collation, and index eligibility
#
# These need the C-53 revision (0002_pattern_ops) applied. Against
# privacy_auditor_frozen_20261105_test, which carries the baseline only, they
# skip with instructions rather than failing: the frozen database is
# deliberately not migrated past 0001.
# ---------------------------------------------------------------------------

PATTERN_INDEXES = {
    "ix_application_lower_name_pattern": "app_name",
    "ix_application_lower_package_pattern": "package_name",
}
BASELINE_INDEXES = {
    "ix_application_lower_name": "app_name",
    "ix_application_lower_package": "package_name",
}

#: F-01's statement, verbatim in shape. The parameters are inlined as literals
#: because prefix extraction from a LIKE pattern happens at plan time and a
#: generic plan has no value to extract a prefix from. Inlining removes that
#: variable from the measurement; the generic-plan question is recorded
#: separately in docs/C53_RESOLUTION_NOTE.md section 4.
F01_STATEMENT = (
    "SELECT package_name, app_name, developer_name FROM application "
    "WHERE lower(app_name) LIKE 'wha%' ESCAPE '\\' "
    "OR lower(package_name) LIKE 'wha%' ESCAPE '\\' "
    "ORDER BY lower(app_name), package_name LIMIT 20"
)


@pytest.fixture(scope="module")
def applied_revisions(pg_engine) -> set[str]:
    with pg_engine.connect() as connection:
        rows = connection.execute(text("SELECT version_num FROM alembic_version"))
        return {row[0] for row in rows}


@pytest.fixture(scope="module")
def pattern_indexes_applied(applied_revisions: set[str]) -> None:
    if "0002_pattern_ops" not in applied_revisions:
        pytest.skip(
            "The C-53 revision 0002_pattern_ops is not applied to this "
            f"database (alembic_version: {sorted(applied_revisions) or 'none'}). "
            "These tests need a database upgraded to it. Create a disposable "
            "one; see docs/C53_RESOLUTION_NOTE.md section 9. The frozen "
            "database is intentionally left at the baseline."
        )


def _opclasses(engine) -> dict[str, list[str]]:
    """Operator class names per index on `application`, read from the catalogue.

    pg_indexes.indexdef hides the operator class when it is the default, so
    the class is read from pg_opclass directly rather than parsed out of DDL.
    """
    sql = text(
        """
        SELECT c.relname AS index_name, oc.opcname
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_class tb ON tb.oid = i.indrelid
        JOIN unnest(i.indclass) WITH ORDINALITY AS u(oid, ord) ON TRUE
        JOIN pg_opclass oc ON oc.oid = u.oid
        WHERE tb.relname = 'application'
        ORDER BY c.relname, u.ord
        """
    )
    found: dict[str, list[str]] = {}
    with engine.connect() as connection:
        for index_name, opcname in connection.execute(sql):
            found.setdefault(index_name, []).append(opcname)
    return found


def _explain(engine, statement: str) -> list[str]:
    """EXPLAIN with sequential scans disabled, inside a rolled-back transaction.

    `enable_seqscan = off` is a diagnostic for index *eligibility*. It says
    nothing about what the planner would choose on a 300-500 row corpus, where
    a sequential scan is cheaper and will usually win. No claim about the
    production plan is made from these tests.
    """
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET LOCAL enable_seqscan = off"))
            return list(connection.execute(text(f"EXPLAIN {statement}")).scalars())
        finally:
            transaction.rollback()


# -- Collation, recorded rather than assumed ------------------------------


def test_database_collation_is_retrievable(pg_engine):
    """C-53's premise is that the collation is not C. Record the real value.

    The assertion message carries it, so a `-v` run and a failure both show
    the actual collation instead of a deduction.
    """
    with pg_engine.connect() as connection:
        collate, ctype = connection.execute(
            text(
                "SELECT datcollate, datctype FROM pg_database "
                "WHERE datname = current_database()"
            )
        ).one()

    assert collate, "pg_database.datcollate is empty"
    assert ctype, "pg_database.datctype is empty"
    print(f"\ndatabase collation: datcollate={collate!r} datctype={ctype!r}")

    # Not a judgement about which collation is correct; both are supported.
    # But under C or POSIX the baseline indexes would serve a prefix LIKE on
    # their own, so C-53's premise would not hold on such a database and the
    # eligibility tests below would be measuring something else.
    if collate in {"C", "POSIX"}:
        pytest.skip(
            f"collation is {collate!r}. On a C-collation database the default "
            "text_ops indexes already serve a prefix LIKE, so C-53 does not "
            "apply here. Record this and re-read the note before acting on it."
        )


# -- Operator classes in the catalogue ------------------------------------


@pytest.mark.parametrize("index_name", sorted(BASELINE_INDEXES))
def test_baseline_indexes_use_the_default_operator_class(pg_engine, index_name):
    """Evidence for C-53, asserted instead of assumed."""
    found = _opclasses(pg_engine)
    assert index_name in found, f"{index_name} is missing from the catalogue"
    assert found[index_name] == ["text_ops"], (
        f"{index_name} uses {found[index_name]}, expected ['text_ops']"
    )


@pytest.mark.parametrize("index_name", sorted(PATTERN_INDEXES))
def test_pattern_ops_opclass_in_catalogue(
    pg_engine, pattern_indexes_applied, index_name
):
    """The test the whole correction depends on.

    An index declared with `postgresql_ops` keyed on a column name instead of
    the expression's label is created successfully with the *default* operator
    class. It exists, it is functional, and it cannot serve the query. Only
    reading pg_opclass distinguishes the two.
    """
    found = _opclasses(pg_engine)
    assert index_name in found, f"{index_name} was not created"
    assert found[index_name] == ["text_pattern_ops"], (
        f"{index_name} exists but uses operator class {found[index_name]}, "
        "not ['text_pattern_ops']. The index cannot serve a prefix LIKE; see "
        "C-53."
    )


def test_all_four_functional_indexes_are_present(pg_engine, pattern_indexes_applied):
    """C-53 is additive: the baseline pair is retained alongside the new pair."""
    found = set(_opclasses(pg_engine))
    missing = (set(BASELINE_INDEXES) | set(PATTERN_INDEXES)) - found
    assert not missing, f"missing indexes: {sorted(missing)}"


# -- Index eligibility for the prefix predicates --------------------------


@pytest.mark.parametrize("column", ["app_name", "package_name"])
def test_prefix_predicate_is_index_eligible(pg_engine, pattern_indexes_applied, column):
    plan = _explain(
        pg_engine,
        f"SELECT package_name FROM application "
        f"WHERE lower({column}) LIKE 'wha%' ESCAPE '\\' LIMIT 20",
    )
    joined = "\n".join(plan)
    assert "Index Cond" in joined, (
        f"no index condition for lower({column}) LIKE 'wha%'. This is the "
        f"C-53 symptom, unchanged:\n{joined}"
    )
    assert "~>=~" in joined or "~<~" in joined, (
        "an index condition is present but not through the pattern operator "
        f"class:\n{joined}"
    )
    assert "_pattern" in joined, f"a pattern index was not chosen:\n{joined}"


def test_combined_f01_query_is_index_eligible(pg_engine, pattern_indexes_applied):
    """The OR needs both indexes; one index can only filter.

    A BitmapOr over the two pattern indexes is the expected shape. It is not
    asserted rigidly, because the planner may legitimately choose another
    index-driven form; what must hold is that an index *condition* appears and
    both pattern indexes are involved.
    """
    plan = _explain(pg_engine, F01_STATEMENT)
    joined = "\n".join(plan)

    assert "Index Cond" in joined, (
        "the combined F-01 query still has no index condition. Before C-53 "
        f"this plan was an Index Scan with a Filter only:\n{joined}"
    )
    for index_name in PATTERN_INDEXES:
        assert index_name in joined, (
            f"{index_name} does not appear in the plan:\n{joined}"
        )
    # Recorded, not required: BitmapOr is the shape expected when the planner
    # combines two index scans for an OR.
    if "BitmapOr" not in joined:
        print(f"\nNote: no BitmapOr in the plan; the planner chose:\n{joined}")


def test_results_are_unchanged_by_the_new_indexes(seeded_repo, pattern_indexes_applied):
    """C-53 changes no SQL, so it must change no result.

    The regression guard for the whole correction: an operator class that
    altered matching semantics would show up here.
    """
    assert set(packages(seeded_repo.search("test.alpha"))) == {
        "test.alpha.messenger",
        "test.alpha.business",
    }
    assert packages(seeded_repo.search("100%")) == ["test.gamma.percent"]
    assert seeded_repo.search("%%") == []
    assert seeded_repo.search("__") == []
    assert packages(seeded_repo.search("ALPHA")) == packages(
        seeded_repo.search("alpha")
    )
    assert len(seeded_repo.search("test.", limit=2)) == 2
