#!/usr/bin/env python3
"""Seed the authored F-15 mapping into the database.

    python scripts/seed_taxonomy_mapping.py --dry-run
    python scripts/seed_taxonomy_mapping.py

Reads `analysis/mapping/taxonomy/mapping_v1.json`, validates it against both
vocabularies, and writes one `taxonomy_mapping_version` row and one
`taxonomy_mapping_entry` per rule.

**Idempotent, and never destructive.** A version with the same label is
reported and left alone; nothing is updated in place and no row is deleted.
An audit records the mapping version it used, so editing a version's rules
after audits have cited it would silently change what those reports meant.
To change the rules, author a new version label.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.db.models import TaxonomyMappingEntry, TaxonomyMappingVersion  # noqa: E402
from app.db.session import engine_or_none  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from analysis.mapping.rule_loader import (  # noqa: E402
    DEFAULT_MAPPING_FILE,
    load_mapping_file,
)


def seed(session: Session, mapping, activate: bool) -> tuple[str, int]:
    existing = session.execute(
        select(TaxonomyMappingVersion).where(
            TaxonomyMappingVersion.version_label == mapping.version_label
        )
    ).scalar_one_or_none()
    if existing is not None:
        count = session.execute(
            select(TaxonomyMappingEntry).where(
                TaxonomyMappingEntry.taxonomy_mapping_version_id
                == existing.taxonomy_mapping_version_id
            )
        ).scalars().all()
        return "already present", len(count)

    if activate:
        # One active version at a time. Deactivating is a flag change, not a
        # deletion: the old version's rows stay, so an audit that cited it
        # can still be explained.
        for row in session.execute(
            select(TaxonomyMappingVersion).where(
                TaxonomyMappingVersion.is_active.is_(True)
            )
        ).scalars():
            row.is_active = False

    version = TaxonomyMappingVersion(
        version_label=mapping.version_label, is_active=activate
    )
    session.add(version)
    session.flush()

    for rule in mapping.rules:
        session.add(
            TaxonomyMappingEntry(
                taxonomy_mapping_version_id=version.taxonomy_mapping_version_id,
                opp115_category=rule.opp115_category,
                opp115_data_type=rule.opp115_data_type,
                ds_category=rule.ds_category,
                is_partial=rule.is_partial,
                rationale=rule.rationale,
            )
        )
    session.flush()
    return "created", len(mapping.rules)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_MAPPING_FILE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-activate",
        action="store_true",
        help="seed without making this the active version",
    )
    arguments = parser.parse_args()

    mapping = load_mapping_file(arguments.file)
    print(f"mapping file : {arguments.file}")
    print(f"version      : {mapping.version_label}")
    print(f"rules        : {len(mapping.rules)}")
    print(f"  general    : {sum(1 for r in mapping.rules if r.opp115_data_type is None)}")
    print(f"  by data type: {sum(1 for r in mapping.rules if r.opp115_data_type)}")
    print(f"  partial    : {sum(1 for r in mapping.rules if r.is_partial)}")
    print(f"unmapped data types : {len(mapping.unmapped_data_types)}")
    print(f"unmapped categories : {len(mapping.unmapped_categories)}")

    if arguments.dry_run:
        print("\n--dry-run: validated only. The database was not touched.")
        return 0

    database = engine_or_none()
    if database is None:
        print(
            "\nNo database is configured (POSTGRES_PASSWORD is unset), so "
            "nothing was written. The mapping file itself validated cleanly.",
            file=sys.stderr,
        )
        return 2

    with Session(database) as session:
        outcome, count = seed(session, mapping, activate=not arguments.no_activate)
        session.commit()
    print(f"\n{mapping.version_label}: {outcome} ({count} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
