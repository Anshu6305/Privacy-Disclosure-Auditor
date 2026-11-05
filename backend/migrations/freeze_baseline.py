#!/usr/bin/env python3
"""Regenerate the frozen baseline migration from the model metadata.

This exists so the derivation of ``versions/0001_baseline_schema.py`` is
reproducible and reviewable rather than a one-off edit. It is **not** run as
part of any migration.

Only use it to regenerate the baseline while the baseline is still unapplied
anywhere that matters. Once a database has been migrated, a schema change gets
its own new revision; rewriting an applied revision makes a migration history
untrustworthy.

    python backend/migrations/freeze_baseline.py --check   # diff only
    python backend/migrations/freeze_baseline.py --write   # rewrite the file
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from alembic.autogenerate import render_python_code  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
from alembic.operations import ops  # noqa: E402
from app.db.models import Base  # noqa: E402

TARGET = ROOT / "backend" / "migrations" / "versions" / "0001_baseline_schema.py"


def render() -> tuple[str, str]:
    """Render the upgrade and downgrade bodies for the PostgreSQL dialect."""
    upgrade = ops.UpgradeOps(ops=[])
    for table in Base.metadata.sorted_tables:
        upgrade.ops.append(ops.CreateTableOp.from_table(table))
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            upgrade.ops.append(ops.CreateIndexOp.from_index(index))

    context = MigrationContext.configure(dialect_name="postgresql")
    return (
        render_python_code(upgrade, migration_context=context),
        render_python_code(upgrade.reverse(), migration_context=context),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    up, down = render()
    print(f"rendered {len(up.splitlines())} upgrade lines, "
          f"{len(down.splitlines())} downgrade lines")

    if args.write:
        print(
            "Refusing to overwrite automatically. The frozen file carries a "
            "written rationale that this generator does not reproduce. Copy "
            "the rendered bodies in by hand after reviewing the diff."
        )
        return 1

    if args.check:
        current = TARGET.read_text(encoding="utf-8")
        missing = [
            line.strip()
            for line in up.splitlines()
            if line.strip().startswith("op.") and line.strip() not in current
        ]
        if missing:
            print(f"{len(missing)} rendered operations are not in the frozen file:")
            for line in missing[:10]:
                print("  ", line[:110])
            return 1
        print("every rendered operation is present in the frozen migration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
