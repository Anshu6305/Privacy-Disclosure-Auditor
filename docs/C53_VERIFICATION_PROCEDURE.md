# C-53 — PostgreSQL verification procedure

For execution on the team Mac. Prepared 2026-11-05 against the repository at
commit `3c780da`.

**None of this has been run.** PostgreSQL runs in Docker Desktop on the Mac and
is not reachable from a development session
(`docs/PHASE4_DEVELOPMENT_PROTOCOL.md` §2.2), so these steps must be executed
locally and their output reported back. Until then C-53 is **Implemented**, not
**Tested and verified**.

**`bash scripts/verify_c53.sh` now runs all of this.** This document remains
the explanation of what each step checks and why; the script is what to
execute. Run either from the repository root.

---

## What this verifies

| # | Claim | Step |
|---|---|---|
| 1 | Both pattern indexes exist in the catalogue | 7 |
| 0 | `0001_baseline` is in the applied ancestry, in **either** migration state | 9 |
| 2 | Their expressions are `lower(app_name)` and `lower(package_name)` | 7 |
| 3 | Their operator classes are actually `text_pattern_ops` | 7, 9 |
| 4 | The two baseline indexes still exist, with `text_ops` | 7, 9 |
| 5 | The migration is recorded as `0002_pattern_ops` | 6 |
| 6 | Upgrade and downgrade both work on a real server | 6, 10 |
| 7 | The prefix predicates are index-**eligible** | 9, 11 |
| 8 | The actual database collation | 8 |
| 9 | F-01's results are unchanged by the new indexes | 9 |

## Two corrections to the earlier note

`docs/C53_RESOLUTION_NOTE.md` §10 was written before the Compose file was
re-read, and had two errors that this document supersedes:

- The service is **`database`**, not `db`. Every `docker compose exec` in the
  note would have failed. Step 1 confirms the name from the configuration
  rather than trusting either document.
- Against a database at the baseline the expected result is **49 passed, 7
  skipped**. There are **56** integration tests (32 schema + 24 search), and
  **7** are gated on revision `0002_pattern_ops`.

## Safety

- **Protected, untouched by every command below:** `privacy_auditor`,
  `privacy_auditor_test`, `privacy_auditor_frozen_20261105_test`. Nothing here
  migrates, resets, truncates or drops any of them.
- Only one database is created: `privacy_auditor_c53_20261105_test`. Step 4
  refuses to continue if that name already exists.
- **No password is typed, pasted or printed.** Inside the container the
  password comes from the container's own environment; on the host it is read
  from `.env` by `scripts/test_database_url.py`, which prints only the finished
  URL and is used through command substitution.
- Every `psql` command is a `SELECT` or a single `CREATE DATABASE`. No `DROP`,
  `TRUNCATE` or `ALTER` appears anywhere in this procedure.

---

## Step 1 — Confirm the Compose service name

Do not assume it. Read it from the configuration:

```bash
cd "$HOME/mnt/Major Project"    # or wherever the repository is
docker compose config --services
```

Expected: `database`, `api`, `worker`. **The database service is `database`**
and its container is `auditor_database`. If the output differs, stop and report
it — the rest of this procedure uses `database`.

## Step 2 — Confirm Docker Desktop is running

```bash
docker info --format '{{.ServerVersion}}'
```

A version number means the daemon is up. An error means Docker Desktop is not
running; start it from Applications and wait for the whale icon to settle.

## Step 3 — Confirm the PostgreSQL container is healthy

```bash
docker compose ps database
docker inspect --format '{{.State.Health.Status}}' auditor_database
```

Expected: `healthy`. If it is `starting`, wait ten seconds and repeat. If the
container is not running:

```bash
docker compose up -d database
```

That starts only the database service. It does not touch the data volume and
does not run any migration.

## Step 4 — Check the disposable name is unused

```bash
NEW_DB=privacy_auditor_c53_20261105_test

docker compose exec -T database sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d postgres -tAc \
   "SELECT datname FROM pg_database ORDER BY datname"'
```

Expected output: the existing databases, **without**
`privacy_auditor_c53_20261105_test`.

**If that name appears, stop.** Do not drop it and do not reuse it. Report it,
and the name becomes `privacy_auditor_c53_20261105b_test` after the same check
is repeated for the new name.

## Step 5 — Create the disposable database

```bash
docker compose exec -T database sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d postgres -c \
   "CREATE DATABASE privacy_auditor_c53_20261105_test"'
```

Expected: `CREATE DATABASE`. `CREATE DATABASE` cannot run inside a
transaction, which is why it is a single `-c` and not part of a script.

## Step 6 — Apply both migrations to the disposable database only

```bash
cd backend
POSTGRES_DB=privacy_auditor_c53_20261105_test ../.venv/bin/alembic upgrade head
cd ..
```

`POSTGRES_DB` is set for that one command and does not persist. Environment
variables take precedence over `.env`, so this reaches the new database and
only the new database.

Expected: two `Running upgrade` lines — `-> 0001_baseline`, then
`0001_baseline -> 0002_pattern_ops`.

Confirm what was recorded:

```bash
docker compose exec -T database sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" \
   -d privacy_auditor_c53_20261105_test -tAc \
   "SELECT version_num FROM alembic_version"'
```

Expected: `0002_pattern_ops`.

## Step 7 — Read the indexes and their real operator classes

This is the step the whole correction rests on. `pg_indexes.indexdef` **omits
the operator class when it is the default**, so a `text_ops` index and a
`text_pattern_ops` index can print identically. The class comes from
`pg_opclass`.

```bash
docker compose exec -T database sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" \
   -d privacy_auditor_c53_20261105_test -c \
   "SELECT c.relname AS index_name, oc.opcname AS operator_class,
           pg_get_indexdef(i.indexrelid) AS definition
      FROM pg_index i
      JOIN pg_class c  ON c.oid = i.indexrelid
      JOIN pg_class tb ON tb.oid = i.indrelid
      JOIN unnest(i.indclass) WITH ORDINALITY AS u(oid, ord) ON TRUE
      JOIN pg_opclass oc ON oc.oid = u.oid
     WHERE tb.relname = ''application''
     ORDER BY c.relname, u.ord"'
```

Expected, four functional indexes among the rows:

| index_name | operator_class |
|---|---|
| `ix_application_lower_name` | `text_ops` |
| `ix_application_lower_name_pattern` | **`text_pattern_ops`** |
| `ix_application_lower_package` | `text_ops` |
| `ix_application_lower_package_pattern` | **`text_pattern_ops`** |

and the definitions showing `lower(app_name)` / `lower(package_name)`.

**If either `_pattern` index reports `text_ops`, the correction has failed** —
the operator class was dropped silently, which is the exact failure mode C-53's
note warns about. Report it and change nothing.

## Step 8 — The actual database collation

Still unrecorded, and not to be guessed:

```bash
docker compose exec -T database sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d postgres -c \
   "SELECT datname, datcollate, datctype FROM pg_database
      WHERE datname LIKE ''privacy_auditor%'' ORDER BY datname"'
```

Report the `datcollate` value. The correction does not depend on it —
`text_pattern_ops` is byte-wise under every collation — but the note has an
empty field waiting for it. If it reads `C` or `POSIX`, say so: on such a
database the baseline indexes would already serve a prefix `LIKE` and C-53
would not apply there.

## Step 9 — The 53 integration tests, against the disposable database

```bash
export TEST_DATABASE_URL="$(.venv/bin/python scripts/test_database_url.py privacy_auditor_c53_20261105_test)"
.venv/bin/python -m pytest tests/integration -p no:warnings -v
```

The first line prints nothing: the URL, password included, goes straight into
the variable. The helper refuses any name that is protected or does not end in
`_test`.

**Expected: 56 passed, 0 skipped.** 32 schema + 24 search, the 7 gated tests
now among them.

A skip here means the URL did not reach the server, or `alembic_version` does
not show `0002_pattern_ops`. The skip message says which. **Skips are not
passes.**

The frozen database needs no re-run. Nothing in this correction changed it,
and the helper refuses its name by design — it is one of the three protected
databases. The evidence that the gate genuinely gates comes from step 10
instead, on the disposable database, where the same 7 tests must start
skipping once the revision is removed.

## Step 10 — Downgrade, on the disposable database only

```bash
cd backend
POSTGRES_DB=privacy_auditor_c53_20261105_test ../.venv/bin/alembic downgrade 0001_baseline
cd ..
```

Expected: one `Running downgrade 0002_pattern_ops -> 0001_baseline`.

Confirm the two pattern indexes are gone and the two baseline indexes remain —
re-run **step 7**. Expected: two functional indexes, both `text_ops`.

Then re-run **step 9** against the disposable database. Expected now:
**49 passed, 7 skipped**. The 7 skip because the revision is no longer applied.

Finally put it back:

```bash
cd backend
POSTGRES_DB=privacy_auditor_c53_20261105_test ../.venv/bin/alembic upgrade head
cd ..
```

## Step 11 — The search diagnostic

```bash
TEST_DATABASE_URL="$(.venv/bin/python scripts/test_database_url.py privacy_auditor_c53_20261105_test)" \
  .venv/bin/python scripts/explain_application_search.py
```

Expected change from the earlier run: the two prefix `LIKE` rows move from
`NO (sequential scan)` to `index used: yes`, with an `Index Cond` using `~>=~`
on a `*_pattern` index. The combined F-01 query should show a `BitmapOr` over
both pattern indexes.

**What this does not show.** The script sets `enable_seqscan = off`, which asks
the planner whether the index is *eligible*. On a table of a few rows
PostgreSQL will still choose a sequential scan when that setting is left
alone, and that is the correct plan. **No performance improvement should be
read from this output**, and none is claimed.

## Step 12 — Report

Paste back, as text rather than a screenshot where possible:

1. Step 1 service list.
2. Step 6 `alembic upgrade` lines and the `alembic_version` value.
3. **Step 7 table in full** — index names, operator classes, definitions.
4. Step 8 `datcollate`.
5. Step 9 pytest summary line, and any skip reasons.
6. Step 10 downgrade output and the re-run summary.
7. Step 11 diagnostic output.

With that, `docs/C53_RESOLUTION_NOTE.md` gets its collation field filled, C-53
moves from **Implemented** to **Tested and verified**, and the traceability
matrix is updated.

## Cleanup — your call

The disposable database can stay or go. Nothing depends on it. To remove it:

```bash
docker compose exec -T database sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d postgres -c \
   "DROP DATABASE privacy_auditor_c53_20261105_test"'
```

This is the only `DROP` in this document, it names the disposable database
explicitly, and it is optional. Do not adapt it to any other name.
