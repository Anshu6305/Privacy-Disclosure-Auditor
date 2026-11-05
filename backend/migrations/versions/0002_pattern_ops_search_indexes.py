"""Add text_pattern_ops functional indexes for ALG-11 prefix search.

Resolves C-53. See docs/C53_RESOLUTION_NOTE.md.

**Why.** The baseline declares two functional indexes on ``lower(app_name)``
and ``lower(package_name)`` with the default ``text_ops`` operator class.
A diagnostic run against PostgreSQL 16 on 2026-11-05 showed that F-01's
``lower(col) LIKE 'term%'`` predicate produced **no index condition** against
either of them: a B-tree index on an expression can serve a prefix ``LIKE``
only when its operator class orders text byte-wise, or when the database
collation is ``C``. Neither held.

**What this does.** Adds two more functional indexes over the same two
expressions, with the ``text_pattern_ops`` operator class, whose ordering is
byte-wise and therefore matches ``LIKE``'s own semantics.

**What this deliberately does not do.**

*It does not drop the existing indexes.* Only the default operator class can
serve ``ORDER BY lower(app_name)``, which F-01 also issues, and the existing
pair is part of the approved design (C-15).

*It does not change the F-01 query.* The predicate, the ``lower()`` on both
sides, the ``escape`` character, the ordering and the result limit are all
untouched, so the case-insensitive prefix semantics and the literal wildcard
escaping are preserved by construction rather than by re-deriving them.

*It does not touch the frozen baseline.* ``0001_baseline_schema.py`` is not
modified, regenerated or renamed.

**Operator class declaration.** The expression is **labelled** and the operator
class is attached through ``postgresql_ops`` keyed on that label. This matters
more than it looks: keying ``postgresql_ops`` on the column name instead, which
is the obvious spelling, compiles without error or warning and **silently
drops the operator class**, producing an index that looks correct in review and
cannot serve the query. Verified by compiling both forms; asserted by
``test_pattern_ops_opclass_is_emitted_for_postgresql`` and, against the real
catalogue, by ``test_pattern_ops_opclass_in_catalogue``.

**SQLite.** The same construct compiles to ``(lower(app_name))`` under SQLite,
which is valid there, so this revision applies cleanly to the in-memory
databases the unit suite uses. The operator class is a PostgreSQL concept and
its absence under SQLite is expected, not a defect.

Revision ID: 0002_pattern_ops
Revises: 0001_baseline
Create Date: 2026-11-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002_pattern_ops"
down_revision: str | None = "0001_baseline"
branch_labels: str | None = None
depends_on: str | None = None

#: (index name, indexed column, label for the postgresql_ops key)
PATTERN_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_application_lower_name_pattern", "app_name", "lower_app_name"),
    ("ix_application_lower_package_pattern", "package_name", "lower_package_name"),
)


def upgrade() -> None:
    for index_name, column_name, label in PATTERN_INDEXES:
        op.create_index(
            index_name,
            "application",
            [sa.func.lower(sa.column(column_name)).label(label)],
            unique=False,
            postgresql_ops={label: "text_pattern_ops"},
        )


def downgrade() -> None:
    for index_name, _column_name, _label in reversed(PATTERN_INDEXES):
        op.drop_index(index_name, table_name="application")
