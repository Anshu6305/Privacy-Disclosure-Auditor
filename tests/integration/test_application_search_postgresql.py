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
