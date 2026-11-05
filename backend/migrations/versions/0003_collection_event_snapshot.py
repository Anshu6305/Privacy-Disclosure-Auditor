"""Restore the approved single collection-event disclosure_snapshot (D-1 Option A).

Phase 3 section 10.2 specifies **one ``disclosure_snapshot`` row per collection
event**, carrying both disclosure sources. The implementation had deviated to
one row per source, discriminated by ``source_type``, with ``audit_run``
carrying two snapshot foreign keys. The team ruled Option A on 2026-11-05: the
approved design stands and the deviation is corrected here.

**No approved requirement changes.** This revision brings the implementation
back to the approved design. DOC-1 resolves with it: ``audit_run`` now has six
NOT NULL foreign keys, so Phase 3 section 10.3's "seven" was the error.

**Why this revision refuses to run on a populated table.**

Two per-source rows cannot be merged into one collection event automatically.
Nothing in the old structure records which Data Safety row belongs with which
policy row — that pairing lived only in ``audit_run``, and an application may
have many snapshots of each source taken at different times. Any automatic
merge would be a guess, and a wrong guess would silently attribute one
application's policy to another collection event.

So ``upgrade()`` stops with an explanation if ``disclosure_snapshot`` or
``audit_run`` holds any row. The correct recovery is to re-import from the
filesystem corpus, which is the system of record for acquisition and holds
per-source provenance in full. At the time of writing every project database
is empty, so this costs nothing and prevents a class of silent corruption.

**What Option A gives up, recorded rather than hidden.**

Per-source HTTP status, byte count and failure reason no longer have a place:
one event has one of each. ``policy_http_status`` and ``policy_doc_bytes``
describe the policy document, the only body this table references. The
per-source detail survives in the filesystem corpus record's provenance, which
M3A writes. ``status`` is what keeps a partial event honest at the database
boundary.

Revision ID: 0003_collection_event
Revises: 0002_pattern_ops
Create Date: 2026-11-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_collection_event"
down_revision: str | None = "0002_pattern_ops"
branch_labels: str | None = None
depends_on: str | None = None

#: Named so the downgrade can drop exactly what the upgrade added.
SNAPSHOT_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "ck_snapshot_status",
        "status IN ('complete', 'declaration_only', 'policy_only', "
        "'declaration_absent', 'fetch_failed', 'parse_failed')",
    ),
    (
        "ck_snapshot_sha256_length",
        "policy_doc_sha256 IS NULL OR length(policy_doc_sha256) = 64",
    ),
    (
        "ck_snapshot_policy_doc_pairing",
        "(policy_doc_path IS NULL) = (policy_doc_sha256 IS NULL)",
    ),
    (
        "ck_snapshot_has_a_source",
        "source_url_listing IS NOT NULL OR source_url_policy IS NOT NULL",
    ),
    (
        "ck_snapshot_policy_doc_requires_url",
        "policy_doc_path IS NULL OR source_url_policy IS NOT NULL",
    ),
    (
        "ck_snapshot_declaration_status_has_listing",
        "status NOT IN ('complete', 'declaration_only', 'declaration_absent') "
        "OR source_url_listing IS NOT NULL",
    ),
    (
        "ck_snapshot_policy_status_has_url",
        "status NOT IN ('complete', 'policy_only') OR source_url_policy IS NOT NULL",
    ),
)

#: (old name, new name). Renames rather than drop-and-add, so a populated
#: database would keep its values if one ever reached this revision with rows.
SNAPSHOT_RENAMES: tuple[tuple[str, str], ...] = (
    ("retrieved_at", "collected_at"),
    ("retrieval_method", "retrieval_mode"),
    ("storage_path", "policy_doc_path"),
    ("content_sha256", "policy_doc_sha256"),
    ("content_bytes", "policy_doc_bytes"),
    ("http_status", "policy_http_status"),
)


def _refuse_if_populated() -> None:
    """Stop before restructuring a table whose rows cannot be migrated.

    In offline mode (``alembic ... --sql``) there is no connection to count
    rows against, so the guard cannot run. It emits a comment into the
    generated script instead of silently appearing to have checked.
    """
    if op.get_context().as_sql:
        op.execute(
            "-- NOTE: generated offline. The populated-table guard in "
            "0003_collection_event did NOT run. Before applying this script, "
            "confirm that disclosure_snapshot and audit_run are empty: this "
            "revision cannot merge per-source rows into collection events."
        )
        return

    bind = op.get_bind()
    for table in ("audit_run", "disclosure_snapshot"):
        count = bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
        if count:
            raise RuntimeError(
                f"{table} holds {count} row(s). This revision restructures "
                "disclosure_snapshot from one row per source into one row per "
                "collection event, and the old structure does not record which "
                "per-source rows belong to the same event. Merging them "
                "automatically would be a guess. Re-import from the filesystem "
                "corpus instead, which holds per-source provenance in full: "
                "see docs/M3_ACQUISITION_REPORT.md section 10."
            )


def upgrade() -> None:
    _refuse_if_populated()

    op.drop_index("ix_snapshot_app_source", table_name="disclosure_snapshot")
    op.drop_index("ix_snapshot_sha256", table_name="disclosure_snapshot")

    # Each batch is applied against the table as reflected when the batch
    # opens. A rename inside a batch is not visible to a later operation in
    # the *same* batch, so renames, type changes and constraint creation are
    # deliberately separate passes rather than one block.

    # 1. Remove what refers to the per-source columns, then the columns.
    with op.batch_alter_table("disclosure_snapshot") as batch:
        batch.drop_constraint("ck_snapshot_source_type", type_="check")
        batch.drop_constraint("ck_snapshot_sha256_length", type_="check")
        batch.drop_column("source_type")
        batch.drop_column("source_url")

    # 2. Rename the columns whose meaning narrows to the policy document.
    with op.batch_alter_table("disclosure_snapshot") as batch:
        for old_name, new_name in SNAPSHOT_RENAMES:
            batch.alter_column(old_name, new_column_name=new_name)

    # 3. Relax the hash, and add the collection-event columns.
    with op.batch_alter_table("disclosure_snapshot") as batch:
        # A policy document is no longer guaranteed: an event can capture the
        # declaration and fail on the policy.
        batch.alter_column(
            "policy_doc_sha256", existing_type=sa.String(length=64), nullable=True
        )
        batch.add_column(sa.Column("source_url_listing", sa.Text(), nullable=True))
        batch.add_column(sa.Column("source_url_policy", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("declares_no_data_collected", sa.Boolean(), nullable=True)
        )
        # server_default lets NOT NULL be added in one step; it is dropped in
        # pass 4 so the application must always state a status rather than
        # inheriting a silent default.
        batch.add_column(
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="fetch_failed",
            )
        )

    # 4. Drop the temporary default and add the constraints, which reference
    #    the new names and so could not exist before pass 2.
    with op.batch_alter_table("disclosure_snapshot") as batch:
        batch.alter_column("status", server_default=None)
        for name, condition in SNAPSHOT_CHECKS:
            batch.create_check_constraint(name, condition)

    op.create_index(
        "ix_snapshot_app_collected",
        "disclosure_snapshot",
        ["app_id", sa.text("collected_at DESC")],
    )
    op.create_index(
        "ix_snapshot_policy_sha256", "disclosure_snapshot", ["policy_doc_sha256"]
    )

    # audit_run: two snapshot foreign keys become one (DOC-1).
    with op.batch_alter_table("audit_run") as batch:
        batch.drop_constraint("ck_audit_distinct_snapshots", type_="check")
        batch.drop_column("ds_snapshot_id")
        batch.drop_column("policy_snapshot_id")
        batch.add_column(sa.Column("snapshot_id", sa.BigInteger(), nullable=True))

    with op.batch_alter_table("audit_run") as batch:
        batch.alter_column("snapshot_id", existing_type=sa.BigInteger(), nullable=False)
        batch.create_foreign_key(
            "fk_audit_run_snapshot_id",
            "disclosure_snapshot",
            ["snapshot_id"],
            ["snapshot_id"],
        )


def downgrade() -> None:
    _refuse_if_populated()

    with op.batch_alter_table("audit_run") as batch:
        batch.drop_constraint("fk_audit_run_snapshot_id", type_="foreignkey")
        batch.drop_column("snapshot_id")
        batch.add_column(sa.Column("ds_snapshot_id", sa.BigInteger(), nullable=True))
        batch.add_column(
            sa.Column("policy_snapshot_id", sa.BigInteger(), nullable=True)
        )

    with op.batch_alter_table("audit_run") as batch:
        batch.alter_column(
            "ds_snapshot_id", existing_type=sa.BigInteger(), nullable=False
        )
        batch.alter_column(
            "policy_snapshot_id", existing_type=sa.BigInteger(), nullable=False
        )
        batch.create_foreign_key(
            "fk_audit_run_ds_snapshot_id",
            "disclosure_snapshot",
            ["ds_snapshot_id"],
            ["snapshot_id"],
        )
        batch.create_foreign_key(
            "fk_audit_run_policy_snapshot_id",
            "disclosure_snapshot",
            ["policy_snapshot_id"],
            ["snapshot_id"],
        )
        batch.create_check_constraint(
            "ck_audit_distinct_snapshots", "ds_snapshot_id <> policy_snapshot_id"
        )

    op.drop_index("ix_snapshot_policy_sha256", table_name="disclosure_snapshot")
    op.drop_index("ix_snapshot_app_collected", table_name="disclosure_snapshot")

    # Mirror of the upgrade, in reverse, with the same one-concern-per-batch
    # discipline.
    with op.batch_alter_table("disclosure_snapshot") as batch:
        for name, _condition in SNAPSHOT_CHECKS:
            batch.drop_constraint(name, type_="check")
        batch.drop_column("status")
        batch.drop_column("declares_no_data_collected")
        batch.drop_column("source_url_policy")
        batch.drop_column("source_url_listing")

    with op.batch_alter_table("disclosure_snapshot") as batch:
        for old_name, new_name in SNAPSHOT_RENAMES:
            batch.alter_column(new_name, new_column_name=old_name)

    with op.batch_alter_table("disclosure_snapshot") as batch:
        batch.alter_column(
            "content_sha256", existing_type=sa.String(length=64), nullable=False
        )
        batch.add_column(
            sa.Column(
                "source_type", sa.String(length=32), nullable=False, server_default=""
            )
        )
        batch.add_column(
            sa.Column("source_url", sa.Text(), nullable=False, server_default="")
        )

    with op.batch_alter_table("disclosure_snapshot") as batch:
        batch.alter_column("source_type", server_default=None)
        batch.alter_column("source_url", server_default=None)
        batch.create_check_constraint(
            "ck_snapshot_source_type",
            "source_type IN ('data_safety', 'privacy_policy')",
        )
        batch.create_check_constraint(
            "ck_snapshot_sha256_length", "length(content_sha256) = 64"
        )

    op.create_index(
        "ix_snapshot_app_source",
        "disclosure_snapshot",
        ["app_id", "source_type", sa.text("retrieved_at DESC")],
    )
    op.create_index("ix_snapshot_sha256", "disclosure_snapshot", ["content_sha256"])
