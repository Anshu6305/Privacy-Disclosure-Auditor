#!/usr/bin/env python3
"""Import the offline Android application corpus into PostgreSQL.

The filesystem corpus is the system of record for acquisition. This reads it
and writes one ``application`` row and one ``disclosure_snapshot`` collection
event per record, per D-1 Option A.

    python scripts/import_corpus.py --dry-run
    python scripts/import_corpus.py
    python scripts/import_corpus.py --root data/corpus --database-url <url>

**Nothing is invented.** Records are imported exactly as collected, including
the partial ones: an application whose policy could not be fetched is stored
with the status that says so, not omitted and not completed with placeholder
values. A corpus of only the records that happened to work would misrepresent
itself, which is the same reason the acquisition gateway records failures
rather than raising them away.

**Re-importing is safe.** An application already stored is refreshed rather
than duplicated, and a new collection event supersedes the previous active one
instead of overwriting it, so history survives for F-30.

Exit codes:
    0  every record imported
    1  one or more records could not be imported; details printed
    2  the corpus or the database could not be reached
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", default="data/corpus", help="Corpus root (default: data/corpus)"
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override the configured database URL. Must name a database.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and report, write nothing. Always safe.",
    )
    arguments = parser.parse_args()

    from acquisition.corpus import CorpusPaths, iter_records

    paths = CorpusPaths(Path(arguments.root))
    if not paths.apps.is_dir():
        print(f"No corpus at {paths.apps}. Nothing to import.", file=sys.stderr)
        return 2

    records = list(iter_records(paths))
    if not records:
        print(f"The corpus at {paths.apps} holds no records.")
        return 0

    print(f"{len(records)} record(s) in {paths.apps}")

    if arguments.dry_run:
        from app.db.repositories.snapshot_repo import derive_status

        print("\n--- dry run: nothing will be written ---")
        for _path, record in records:
            print(f"  {record.package_name:<40} -> {derive_status(record)}")
        return 0

    from app.config import get_settings
    from app.db.repositories.application_repo import ApplicationRepository
    from app.db.repositories.snapshot_repo import SnapshotRepository
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    url = arguments.database_url or get_settings().database_url
    try:
        engine = create_engine(url, future=True)
        with engine.connect() as connection:
            connection.close()
    except Exception as exc:  # noqa: BLE001 - the type is the useful part
        print(f"Database not usable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    imported = 0
    created = 0
    failures: list[tuple[str, str]] = []

    with Session(engine) as session:
        applications = ApplicationRepository(session)
        snapshots = SnapshotRepository(session, policy_root=ROOT)

        for _path, record in records:
            try:
                app_id, was_created = applications.upsert_from_record(record)
                snapshot = snapshots.record_collection_event(app_id, record)
                # One record per transaction: a corpus of 300 should not lose
                # 299 good imports to one bad record.
                session.commit()
            except Exception as exc:  # noqa: BLE001 - reported, not raised away
                session.rollback()
                failures.append((record.package_name, f"{type(exc).__name__}: {exc}"))
                continue

            imported += 1
            created += int(was_created)
            print(f"  {record.package_name:<40} {snapshot.status}")

    print(
        f"\nimported {imported} of {len(records)} record(s); "
        f"{created} new application(s)"
    )
    if failures:
        print(f"\n{len(failures)} record(s) could not be imported:", file=sys.stderr)
        for package_name, reason in failures:
            print(f"  {package_name}: {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
