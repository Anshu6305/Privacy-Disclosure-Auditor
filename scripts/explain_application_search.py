#!/usr/bin/env python3
"""Diagnostic: does PostgreSQL actually use the ALG-11 functional indexes?

The question this answers, and why it needs answering separately from the
tests.

``application`` declares two functional B-tree indexes,
``ix_application_lower_name`` on ``lower(app_name)`` and
``ix_application_lower_package`` on ``lower(package_name)``. F-01 queries
them with ``lower(col) LIKE 'term%'``.

A B-tree index on an expression can serve a prefix ``LIKE`` only when the
index opclass orders text byte-wise — ``text_pattern_ops`` — or when the
database's collation is ``C``. Under a collation-aware default such as
``en_US.UTF-8``, PostgreSQL's planner cannot convert ``LIKE 'term%'`` into the
index's ordering, so it may fall back to a sequential scan however many rows
there are. The declared indexes use the default opclass.

This script reports what the planner actually does, on the actual database,
rather than reasoning about it. It is read-only: it creates nothing, writes
nothing, and runs inside a transaction it rolls back.

    TEST_DATABASE_URL=postgresql+psycopg://auditor:PASSWORD@localhost:5432/privacy_auditor_frozen_20261105_test \
        python scripts/explain_application_search.py

``enable_seqscan`` is turned off for the EXPLAIN. On a table of a few rows the
planner would choose a sequential scan whatever indexes exist, so an EXPLAIN
on a small table proves nothing on its own; disabling the sequential scan
asks the planner the question directly — *can* this predicate use the index?

Exit codes:
    0  the diagnostic ran; read the report
    2  no usable database; nothing was measured
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

TEST_URL_VAR = "TEST_DATABASE_URL"

QUERIES = {
    "lower(app_name) LIKE 'term%'": (
        "SELECT package_name FROM application "
        "WHERE lower(app_name) LIKE :pattern LIMIT 20"
    ),
    "lower(package_name) LIKE 'term%'": (
        "SELECT package_name FROM application "
        "WHERE lower(package_name) LIKE :pattern LIMIT 20"
    ),
    "F-01 as implemented (both columns, OR)": (
        "SELECT package_name, app_name, developer_name FROM application "
        "WHERE lower(app_name) LIKE :pattern OR lower(package_name) LIKE :pattern "
        "ORDER BY lower(app_name), package_name LIMIT 20"
    ),
    "range alternative: lower(col) >= x AND < y": (
        "SELECT package_name FROM application "
        "WHERE lower(package_name) >= :low AND lower(package_name) < :high LIMIT 20"
    ),
}


def main() -> int:
    url = os.environ.get(TEST_URL_VAR)
    if not url:
        print(f"{TEST_URL_VAR} is not set. Nothing was measured.")
        return 2

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    database = make_url(url).database or ""
    if not database.endswith("_test"):
        print(
            f"Refusing to run: {TEST_URL_VAR} names {database!r}, which does "
            "not end in '_test'."
        )
        return 2

    try:
        engine = create_engine(url, future=True)
        connection = engine.connect()
    except Exception as exc:  # noqa: BLE001
        print(f"No usable database: {type(exc).__name__}: {exc}")
        return 2

    transaction = connection.begin()
    try:
        meta = connection.execute(
            text(
                "SELECT current_database(), datcollate, datctype, "
                "(SELECT count(*) FROM application), "
                "(SELECT string_agg(version_num, ',' ORDER BY version_num) "
                " FROM alembic_version) "
                "FROM pg_database WHERE datname = current_database()"
            )
        ).one()

        # Unpacked into names rather than indexed. The previous version read
        # meta[2] for the row count; adding datctype to the SELECT shifted
        # every position after it, and the row-count check then compared a
        # collation string to an integer. Names cannot drift out of step with
        # the query the way positions can.
        database, collate, ctype, row_count, applied = meta

        print(f"database  : {database}")
        print(f"datcollate: {collate}")
        print(f"datctype  : {ctype}")
        print(f"rows in application: {row_count}")
        print(f"alembic_version: {applied or '(none)'}")

        if row_count == 0:
            print(
                "\nNote: the application table is EMPTY. The plans below still "
                "show whether a predicate *can* use an index, which is what "
                "this script is for, but they describe an empty relation. The "
                "authoritative eligibility evidence is "
                "test_prefix_predicate_is_index_eligible and "
                "test_combined_f01_query_is_index_eligible, which seed rows "
                "inside a rolled-back transaction and assert on the plan."
            )
        elif row_count < 1000:
            print(
                "\nNote: with few rows a sequential scan is the correct plan "
                "regardless of indexes, which is why enable_seqscan is off "
                "below. This reports index *usability*, not a measured "
                "speed-up."
            )

        print("\nindexes on application:")
        for row in connection.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE tablename = 'application' ORDER BY indexname"
            )
        ):
            print(f"  {row[0]}\n    {row[1]}")

        # indexdef omits the operator class when it is the default, so an
        # index with text_ops and one with text_pattern_ops can print
        # identically. pg_opclass is the only reliable source.
        print("\noperator classes (from pg_opclass, not parsed from DDL):")
        for row in connection.execute(
            text(
                """
                SELECT c.relname, oc.opcname
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_class tb ON tb.oid = i.indrelid
                JOIN unnest(i.indclass) WITH ORDINALITY AS u(oid, ord) ON TRUE
                JOIN pg_opclass oc ON oc.oid = u.oid
                WHERE tb.relname = 'application'
                ORDER BY c.relname, u.ord
                """
            )
        ):
            print(f"  {row[0]:<42} {row[1]}")

        connection.execute(text("SET LOCAL enable_seqscan = off"))
        params = {"pattern": "wha%", "low": "wha", "high": "whb"}

        for label, sql in QUERIES.items():
            print(f"\n--- {label} ---")
            plan = connection.execute(
                text(f"EXPLAIN {sql}"), params
            ).scalars().all()
            for line in plan:
                print(f"  {line}")
            # Keyed on Index Cond, not on the scan node's name.
            #
            # Two reasons. "Index Only Scan" does not contain the substring
            # "Index Scan", so the previous check reported NO for a plan that
            # was using an index. And a scan carrying only a Filter is doing
            # no index *selection* at all - which is precisely the C-53
            # symptom, so calling it "used" would restate the bug as a pass.
            index_condition = any("Index Cond" in line for line in plan)
            scans = [
                line.strip()
                for line in plan
                if "Index Scan" in line or "Index Only Scan" in line
                or "Bitmap Index" in line or "Seq Scan" in line
            ]
            print(f"  => selective index condition: {'yes' if index_condition else 'NO'}")
            if scans:
                print(f"     nodes: {' | '.join(scans)}")
            if scans and not index_condition:
                print(
                    "     (an index appears but only as a Filter, so it is "
                    "not narrowing the scan)"
                )

        print(
            "\nReading this output:\n"
            "  Before 0002_pattern_ops is applied, the LIKE queries report NO "
            "and the range query reports yes. That is C-53.\n"
            "  After it is applied, a LIKE query CAN use a *_pattern index "
            "with an Index Cond using ~>=~.\n"
            "\n"
            "  On an EMPTY table the plan the planner happens to choose is "
            "not stable and not meaningful: every path costs about the same, "
            "so it may pick a different index, or the same index as a filter "
            "only, from one run to the next. A 'NO' here is not evidence that "
            "the correction failed.\n"
            "\n"
            "  The authoritative evidence is the two integration tests, which "
            "seed rows in a rolled-back transaction and assert on the plan:\n"
            "    test_prefix_predicate_is_index_eligible\n"
            "    test_combined_f01_query_is_index_eligible\n"
            "\n"
            "  The planner will still prefer a sequential scan at 300-500 rows "
            "when enable_seqscan is left on. That is correct, and no "
            "performance claim should be made from this script."
        )
    finally:
        transaction.rollback()
        connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
