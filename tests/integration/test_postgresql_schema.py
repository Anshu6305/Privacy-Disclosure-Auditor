"""Real PostgreSQL verification.

Everything else in this suite runs on SQLite, which cannot check the things
that matter most about the production schema: JSONB, BIGINT, functional
indexes, and whether PostgreSQL itself enforces the 28 CHECK constraints rather
than merely accepting their declaration.

**Safety.** These tests touch only a database the caller names explicitly in
``TEST_DATABASE_URL``, and only one whose name ends in ``_test``. With the
variable unset every test skips. There is no fallback to ``.env`` and no
default, so the project database cannot be reached by accident. Nothing here
drops or truncates a table: each test runs inside a transaction that is rolled
back, and ``drop_all`` appears nowhere in this file.

To run them, see docs/PHASE4_SCHEMA_BASELINE_AUDIT.md Part 5.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db.models import Base
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from analysis.vocabulary import VERDICT_UNDETERMINED

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2] / "backend"

#: The revision that must be in every applied database's ancestry. Asserting
#: the *ancestry* rather than equality is what lets this file run against a
#: database at any point on the migration path: at head, or at the baseline
#: after a downgrade.
BASELINE_REVISION = "0001_baseline"

PATTERN_INDEX_OPCLASSES = {
    "ix_application_lower_name_pattern": "text_pattern_ops",
    "ix_application_lower_package_pattern": "text_pattern_ops",
}
#: The revision that introduces the indexes above (C-53).
PATTERN_REVISION = "0002_pattern_ops"

TEST_URL_VAR = "TEST_DATABASE_URL"

#: The eleven tables whose primary key must be BIGINT in production. SQLite
#: reports INTEGER for all of them because of the dialect variant, so this is
#: checkable only here.
BIGINT_PRIMARY_KEYS = {
    "disclosure_snapshot": "snapshot_id",
    "declared_practice": "declared_practice_id",
    "policy_segment": "segment_id",
    "extracted_practice": "extracted_practice_id",
    "extracted_span": "span_id",
    "audit_run": "audit_id",
    "alignment_judgement": "judgement_id",
    "verdict": "verdict_id",
    "evidence_record": "evidence_record_id",
    "gold_annotation": "gold_annotation_id",
    "evaluation_metric": "evaluation_metric_id",
}


@pytest.fixture(scope="session")
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


@pytest.fixture(scope="session")
def pg_engine(pg_url: str):
    """An engine, or a skip.

    ``create_engine`` is inside the try because it raises when the psycopg
    driver is absent, which is the normal state for anyone who has not
    installed the full requirements. That should skip like an unreachable
    server, not produce an error for every test in the file.
    """
    try:
        engine = create_engine(pg_url, future=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - the type is the useful part
        pytest.skip(f"PostgreSQL not usable here: {type(exc).__name__}: {exc}")
    return engine


@pytest.fixture(scope="session", autouse=True)
def require_migrated_schema(pg_engine):
    """Fail once, clearly, if the schema was never applied.

    Without this, an unmigrated database produces 28 failures that each look
    like a different defect — missing types, missing indexes, missing
    constraints — when the single cause is that no table exists. The first run
    of this suite did exactly that.
    """
    tables = set(inspect(pg_engine).get_table_names())
    if "application" not in tables:
        pytest.fail(
            "The test database has no schema: found "
            f"{len(tables)} tables. Apply the baseline first:\n"
            "    cd backend && POSTGRES_DB=<your _test database> "
            "../.venv/bin/alembic upgrade head\n"
            "If that command fails, read its error before running these tests."
        )


@pytest.fixture
def pg_session(pg_engine):
    """A session whose work is always rolled back.

    Even the dedicated test database is left exactly as it was found.
    """
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# 1. The migration ran and the schema is present
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def revision_graph() -> ScriptDirectory:
    """Alembic's own view of the migration graph, read from the versions dir.

    The graph is the authority on ancestry. Hard-coding a list of revision
    identifiers in a test means the test has to be edited every time a
    migration is added, which is how the previous version of this file came to
    assert a single revision and then fail once C-53 added a second.
    """
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    return ScriptDirectory.from_config(config)


@pytest.fixture(scope="module")
def applied_revision(pg_engine) -> str:
    """The single revision recorded in the database."""
    tables = set(inspect(pg_engine).get_table_names())
    assert "alembic_version" in tables, (
        "alembic_version is missing: run 'alembic upgrade head' against the "
        "test database first"
    )
    with pg_engine.connect() as connection:
        recorded = [
            row[0]
            for row in connection.execute(text("SELECT version_num FROM alembic_version"))
        ]

    assert len(recorded) == 1, (
        f"alembic_version holds {len(recorded)} rows ({recorded}). More than "
        "one means a branched or partially applied history, which this suite "
        "cannot reason about."
    )
    return recorded[0]


def test_alembic_baseline_is_in_the_applied_ancestry(
    applied_revision: str, revision_graph: ScriptDirectory
):
    """The baseline has been applied, whatever revision the database is at.

    Replaces an equality check against ``0001_baseline``, which was correct
    while that was the only revision and became wrong the moment C-53 added
    ``0002_pattern_ops``: a correctly upgraded database then failed a test
    whose real subject is "was the schema ever created".

    Ancestry is the right question. A database at ``0002_pattern_ops`` has the
    baseline in its history; a database at the baseline is its own ancestor.
    Both states pass, and a database at some unrelated revision does not.
    """
    ancestry = {
        script.revision
        for script in revision_graph.iterate_revisions(applied_revision, "base")
    }
    assert BASELINE_REVISION in ancestry, (
        f"the database is at {applied_revision!r}, whose ancestry is "
        f"{sorted(ancestry)}. {BASELINE_REVISION!r} is not among them, so the "
        "approved baseline schema was never applied to this database."
    )


def test_applied_revision_lies_on_the_path_from_head_to_base(
    applied_revision: str, revision_graph: ScriptDirectory
):
    """The recorded revision is one this repository actually knows about.

    Guards the case the ancestry test cannot: a revision identifier that no
    longer exists in ``versions/``, or one on a branch that is not reachable
    from the current head. Either means the database and the repository have
    diverged, and every other assertion in this file would be measuring an
    unknown schema.
    """
    head = revision_graph.get_current_head()
    assert head is not None, "the migration graph has no head"

    reachable = {
        script.revision for script in revision_graph.iterate_revisions(head, "base")
    }
    assert applied_revision in reachable, (
        f"the database is at {applied_revision!r}, which is not on the path "
        f"from head {head!r} to base. Known revisions: {sorted(reachable)}."
    )


def test_pattern_indexes_match_the_applied_revision(pg_engine, applied_revision, revision_graph):
    """The catalogue agrees with ``alembic_version``, in **both** states.

    This is the test that covers the downgrade path. It makes no assumption
    about which revision the database is at: it derives the expectation from
    the recorded revision and then checks the real catalogue.

    - At ``0002_pattern_ops`` or later: both C-53 indexes exist, and their
      operator classes are ``text_pattern_ops``. Read from ``pg_opclass``,
      because ``pg_indexes.indexdef`` omits the operator class when it is the
      default and a dropped class would therefore be invisible.
    - At the baseline: neither index exists.

    A mismatch either way means a migration was applied or reverted without
    its DDL taking effect.
    """
    ancestry = {
        script.revision
        for script in revision_graph.iterate_revisions(applied_revision, "base")
    }
    expected_present = PATTERN_REVISION in ancestry

    with pg_engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT c.relname, oc.opcname
                  FROM pg_index i
                  JOIN pg_class c  ON c.oid = i.indexrelid
                  JOIN pg_class tb ON tb.oid = i.indrelid
                  JOIN unnest(i.indclass) WITH ORDINALITY AS u(oid, ord) ON TRUE
                  JOIN pg_opclass oc ON oc.oid = u.oid
                 WHERE tb.relname = 'application'
                   AND c.relname = ANY(:names)
                """
            ),
            {"names": sorted(PATTERN_INDEX_OPCLASSES)},
        ).all()

    # The `.all()` above is load-bearing. Do not remove it.
    #
    # dict() looks for a .keys() method first and takes the mapping protocol
    # when it finds one. CursorResult HAS .keys() - the column names - so
    # dict(result) then tries to subscript the result object and raises
    # "'CursorResult' object is not subscriptable", an error that names dict's
    # fallback path rather than the real mistake and so reads like a driver
    # fault. `.all()` returns a list of Row tuples, which dict() consumes
    # pairwise as intended.
    found = dict(rows)

    if expected_present:
        assert found == PATTERN_INDEX_OPCLASSES, (
            f"the database is at {applied_revision!r}, which includes "
            f"{PATTERN_REVISION}, so both pattern indexes should exist with "
            f"text_pattern_ops. Found: {found or 'none'}."
        )
    else:
        assert found == {}, (
            f"the database is at {applied_revision!r}, which does not include "
            f"{PATTERN_REVISION}, so neither pattern index should exist. "
            f"Found: {found}."
        )


def test_the_baseline_functional_indexes_exist_in_every_state(pg_engine):
    """C-53 is additive, so these two are present at every revision."""
    with pg_engine.connect() as connection:
        found = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE tablename = "
                    "'application' AND indexname IN "
                    "('ix_application_lower_name', 'ix_application_lower_package')"
                )
            )
        }
    assert found == {"ix_application_lower_name", "ix_application_lower_package"}, (
        f"a baseline functional index is missing; found {sorted(found)}"
    )


def test_all_sixteen_tables_exist(pg_engine):
    present = set(inspect(pg_engine).get_table_names()) - {"alembic_version"}
    assert present == set(Base.metadata.tables)
    assert len(present) == 16


# ---------------------------------------------------------------------------
# 2. PostgreSQL-specific types, which SQLite cannot verify
# ---------------------------------------------------------------------------


def _udt_name(engine, table: str, column: str) -> str:
    """The PostgreSQL type of one column.

    Fails explicitly when the column is absent rather than returning None,
    which would surface as ``assert None == 'jsonb'`` and read like a type
    mismatch instead of a missing column.
    """
    with engine.connect() as connection:
        value = connection.execute(
            text(
                "SELECT udt_name FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()

    if value is None:
        pytest.fail(f"{table}.{column} does not exist in the database")
    return value


@pytest.mark.parametrize(
    "table,column",
    [("audit_run", "threshold_config"), ("model_version", "training_config")],
)
def test_json_columns_are_jsonb(pg_engine, table, column):
    """JSON would work but would lose indexing and containment operators."""
    assert _udt_name(pg_engine, table, column) == "jsonb"


@pytest.mark.parametrize("table,column", sorted(BIGINT_PRIMARY_KEYS.items()))
def test_high_volume_primary_keys_are_bigint(pg_engine, table, column):
    """SQLite reports INTEGER for these because of the dialect variant, so
    this is the only place the production width is checked."""
    assert _udt_name(pg_engine, table, column) == "int8"


def test_timestamps_carry_a_time_zone(pg_engine):
    """A naive timestamp would make retrieval times ambiguous across the
    team's machines."""
    assert _udt_name(pg_engine, "audit_run", "requested_at") == "timestamptz"
    assert _udt_name(pg_engine, "disclosure_snapshot", "collected_at") == "timestamptz"


def test_verdict_confidence_is_numeric(pg_engine):
    """Restored by audit finding E-5, with the approved numeric(5,4) type."""
    assert _udt_name(pg_engine, "verdict", "confidence") == "numeric"


# ---------------------------------------------------------------------------
# 3. Functional indexes (ALG-11)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "index_name", ["ix_application_lower_name", "ix_application_lower_package"]
)
def test_functional_lower_indexes_exist(pg_engine, index_name):
    """The baseline pair exists and indexes lower().

    **Three separate properties, and this test covers the first two.** The
    original failure message conflated them and asserted something C-53 has
    since disproved, so it is corrected here rather than left to mislead:

    1. *Existence* — the index is in the catalogue. Asserted below.
    2. *Expression correctness* — it indexes ``lower(col)``, not ``col``, so a
       case-insensitive comparison can match it. Asserted below.
    3. *Operator-class correctness* — whether a prefix ``LIKE`` can actually
       use it. **These two indexes use the default ``text_ops`` class and
       cannot** (C-53, confirmed against PostgreSQL 16 on 2026-11-05). They are
       retained because only the default class serves
       ``ORDER BY lower(app_name)``, which F-01 also issues. The pattern-class
       indexes that do serve the predicate are checked in
       ``test_application_search_postgresql.py::test_pattern_ops_opclass_in_catalogue``.

    So passing this test means the index exists and is functional. It does
    **not** mean ALG-11's prefix search uses it.
    """
    with pg_engine.connect() as connection:
        definition = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"),
            {"n": index_name},
        ).scalar()

    assert definition is not None, (
        f"{index_name} is missing from the catalogue: the index does not "
        "exist at all"
    )
    assert "lower" in definition.lower(), (
        f"{index_name} exists but does not index lower(): a case-insensitive "
        f"comparison cannot match it. Definition: {definition}"
    )


# ---------------------------------------------------------------------------
# 4. Constraints are present in the real catalogue
# ---------------------------------------------------------------------------


def _constraint_names(engine, contype: str) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT con.conname FROM pg_constraint con "
                "JOIN pg_class rel ON rel.oid = con.conrelid "
                "JOIN pg_namespace ns ON ns.oid = rel.relnamespace "
                "WHERE con.contype = :t AND ns.nspname = 'public'"
            ),
            {"t": contype},
        )
        return {row[0] for row in rows}


def test_every_declared_check_constraint_exists(pg_engine):
    from sqlalchemy import CheckConstraint

    expected = {
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name
    }
    actual = _constraint_names(pg_engine, "c")
    assert actual, "no CHECK constraints at all; the schema is not applied"
    missing = expected - actual
    assert not missing, f"CHECK constraints missing from PostgreSQL: {sorted(missing)}"


def test_every_declared_unique_constraint_exists(pg_engine):
    from sqlalchemy import UniqueConstraint

    expected = {
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint) and constraint.name
    }
    actual = _constraint_names(pg_engine, "u")
    assert actual, "no UNIQUE constraints at all; the schema is not applied"
    missing = expected - actual
    assert not missing, f"UNIQUE constraints missing: {sorted(missing)}"


def test_audit_run_foreign_keys_are_all_not_null(pg_engine):
    """Every reference recorded on an audit must be present.

    The row count is asserted before the nullability. Without it this test
    passed on an empty database, because "no column is nullable" is trivially
    true when there are no columns. It did exactly that on the first run.
    """
    with pg_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'audit_run' AND column_name LIKE '%_id'"
            )
        ).all()

    assert rows, "audit_run has no identifier columns; the table is missing"
    # audit_id plus the seven foreign keys.
    assert len(rows) == 8, f"expected 8 identifier columns, found {len(rows)}"

    nullable = [name for name, is_nullable in rows if is_nullable == "YES"]
    assert nullable == ["audit_id"] or not nullable, (
        f"these audit_run references are nullable: "
        f"{[n for n in nullable if n != 'audit_id']}"
    )


# ---------------------------------------------------------------------------
# 5. PostgreSQL actually rejects invalid records
#
# The SQLite suite proves the constraints are declared. These prove the
# database the system will run on enforces them.
# ---------------------------------------------------------------------------


def _seed(session: Session) -> dict:
    """A minimal valid graph for the constraint tests.

    **Skips when the database is behind revision 0003_collection_event.** The
    graph is built from the current models, which describe the restored
    collection-event snapshot (D-1 Option A); at an earlier revision
    ``disclosure_snapshot`` still has the per-source columns and this insert
    would fail. A skip is the honest outcome there: the test is not applicable
    to that schema, as against a defect in it. The downgrade stage of
    scripts/verify_migrations.sh relies on this.
    """
    from app.db.models import (
        Application,
        AuditRun,
        DisclosureSnapshot,
        ModelVersion,
        TaxonomyMappingVersion,
    )

    present = {
        column["name"]
        for column in inspect(session.get_bind()).get_columns("disclosure_snapshot")
    }
    missing = {"status", "source_url_listing", "source_url_policy"} - present
    if missing:
        pytest.skip(
            "disclosure_snapshot is at a pre-0003 revision (missing "
            f"{sorted(missing)}), so the collection-event graph these tests "
            "need cannot be built. Apply 0003_collection_event."
        )

    suffix = os.urandom(4).hex()
    app = Application(
        package_name=f"com.test.{suffix}", app_name="Integration Test App"
    )
    session.add(app)
    session.flush()

    # One collection event covering both sources, per D-1 Option A.
    snapshot = DisclosureSnapshot(
        app_id=app.app_id,
        source_url_listing="https://example.invalid/listing",
        source_url_policy="https://example.invalid/privacy",
        retrieval_mode="test",
        policy_doc_path=f"data/policies/raw/{suffix}.html",
        policy_doc_sha256="b" * 64,
        status="complete",
        declares_no_data_collected=False,
    )
    mapping = TaxonomyMappingVersion(version_label=f"test-{suffix}")
    models = [
        ModelVersion(
            task=task,
            variant="baseline",
            model_identifier="stub",
            version_label=f"{task}-{suffix}",
        )
        for task in ("classification", "span_extraction", "alignment")
    ]
    session.add_all([snapshot, mapping, *models])
    session.flush()

    audit = AuditRun(
        app_id=app.app_id,
        snapshot_id=snapshot.snapshot_id,
        taxonomy_mapping_version_id=mapping.taxonomy_mapping_version_id,
        classification_model_id=models[0].model_version_id,
        span_model_id=models[1].model_version_id,
        alignment_model_id=models[2].model_version_id,
        status="queued",
        threshold_config={"classifier": 0.5},
    )
    session.add(audit)
    session.flush()
    return {"app": app, "audit": audit}


def test_postgresql_rejects_a_sixth_verdict_value(pg_session: Session):
    from app.db.models import Verdict

    seed = _seed(pg_session)
    pg_session.add(
        Verdict(
            audit_id=seed["audit"].audit_id,
            ds_category="Location",
            verdict_value="Probably Fine",
            declared=True,
            found_in_policy=True,
        )
    )
    with pytest.raises(IntegrityError):
        pg_session.flush()


def test_postgresql_rejects_undetermined_in_the_gold_set(pg_session: Session):
    from app.db.models import GoldAnnotation

    seed = _seed(pg_session)
    pg_session.add(
        GoldAnnotation(
            app_id=seed["app"].app_id,
            ds_category="Location",
            label=VERDICT_UNDETERMINED,
            annotator_code="R1",
        )
    )
    with pytest.raises(IntegrityError):
        pg_session.flush()


def test_postgresql_rejects_evidence_without_a_quote(pg_session: Session):
    from app.db.models import EvidenceRecord, Verdict

    seed = _seed(pg_session)
    verdict = Verdict(
        audit_id=seed["audit"].audit_id,
        ds_category="Personal info",
        verdict_value="Contradictory",
        declared=True,
        found_in_policy=True,
    )
    pg_session.add(verdict)
    pg_session.flush()

    pg_session.add(
        EvidenceRecord(
            verdict_id=verdict.verdict_id,
            record_type="evidence",
            reason="the policy says so",
        )
    )
    with pytest.raises(IntegrityError):
        pg_session.flush()


def test_postgresql_rejects_an_absence_record_carrying_a_quote(pg_session: Session):
    from app.db.models import EvidenceRecord, Verdict

    seed = _seed(pg_session)
    verdict = Verdict(
        audit_id=seed["audit"].audit_id,
        ds_category="Calendar",
        verdict_value="Declared-not-in-policy",
        declared=True,
        found_in_policy=False,
    )
    pg_session.add(verdict)
    pg_session.flush()

    pg_session.add(
        EvidenceRecord(
            verdict_id=verdict.verdict_id,
            record_type="absence",
            reason="nothing found",
            quoted_text="no mention of the calendar anywhere",
        )
    )
    with pytest.raises(IntegrityError):
        pg_session.flush()


def test_postgresql_rejects_two_verdicts_for_one_category(pg_session: Session):
    from app.db.models import Verdict

    seed = _seed(pg_session)
    for value in ("Consistent", "Contradictory"):
        pg_session.add(
            Verdict(
                audit_id=seed["audit"].audit_id,
                ds_category="Messages",
                verdict_value=value,
                declared=True,
                found_in_policy=True,
            )
        )
    with pytest.raises(IntegrityError):
        pg_session.flush()


def test_postgresql_rejects_a_failed_audit_without_a_reason(pg_session: Session):
    seed = _seed(pg_session)
    seed["audit"].status = "failed"
    seed["audit"].failure_reason = None
    with pytest.raises(IntegrityError):
        pg_session.flush()


def test_postgresql_rejects_an_out_of_range_verdict_confidence(pg_session: Session):
    """Audit finding E-5's CHECK, enforced by the real database."""
    from app.db.models import Verdict

    seed = _seed(pg_session)
    pg_session.add(
        Verdict(
            audit_id=seed["audit"].audit_id,
            ds_category="Contacts",
            verdict_value="Contradictory",
            declared=True,
            found_in_policy=True,
            confidence=1.5,
        )
    )
    with pytest.raises(IntegrityError):
        pg_session.flush()
