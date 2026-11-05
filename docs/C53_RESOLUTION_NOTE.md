# C-53 resolution note — ALG-11 index usability

Date: 2026-11-05 · revised 2026-11-05 after implementation
Status: **implemented and approved; PostgreSQL verification part-complete.**

**Measured on the team Mac, 2026-11-05:**

| Check | Result |
|---|---|
| `ix_application_lower_name_pattern` operator class | **`text_pattern_ops`** |
| `ix_application_lower_package_pattern` operator class | **`text_pattern_ops`** |
| `ix_application_lower_name` operator class | `text_ops`, retained |
| `ix_application_lower_package` operator class | `text_ops`, retained |
| Database collation | **`en_US.utf8`** |
| Integration tests | 52 of 53 passed; **1 failed** |

The failure was in the test suite, not the correction:
`test_alembic_baseline_has_been_applied` asserted `version_num ==
"0001_baseline"`, which was correct while the baseline was the only revision
and became wrong the moment `0002_pattern_ops` existed. A **correctly**
upgraded database failed it. Replaced by four ancestry-based tests; see §12.

**Still outstanding:** the downgrade and re-upgrade checks, the re-run that
proves the skip gate fires, and the `EXPLAIN` diagnostic. The run stopped at
the failing test before reaching them.
Approved: 2026-11-05. Implemented as the additive revision `0002_pattern_ops`.
Finding confirmed by: the C-53 diagnostic run on the team Mac against
`privacy_auditor_frozen_20261105_test`, 2026-11-05.

**What is verified and what is not.** The emitted PostgreSQL DDL, the SQLite
compatibility, the upgrade/downgrade reversal and the full unit suite were
executed and passed. **Nothing was executed against a PostgreSQL server**: the
catalogue checks and the `EXPLAIN` eligibility tests are written and skip
until a database upgraded to `0002_pattern_ops` is supplied. Section 10 has
the commands. Skips are not passes.

---

## 1. What the diagnostic established

| Predicate | Result |
|---|---|
| `lower(app_name) LIKE 'wha%'` | no useful index condition |
| `lower(package_name) LIKE 'wha%'` | no useful index condition |
| F-01 as implemented (both columns, OR) | Index Scan on the `lower(app_name)` index, **Filter only, no Index Cond** |
| `lower(package_name) >= 'wha' AND < 'whb'` | real Index Cond, index used |

C-53 is therefore **confirmed**: the two functional indexes are declared
correctly and are inert for the prefix predicate F-01 actually issues.

Alongside this, the 43 PostgreSQL integration tests passed, so F-01 and F-03
return correct results on real PostgreSQL. **This is a performance and
documentation defect, not a correctness defect.**

## 2. Collation and operator classes

### Operator classes — confirmed from source

The frozen revision declares both indexes with no operator class:

```python
op.create_index('ix_application_lower_name', 'application',
                [sa.text('lower(app_name)')], unique=False)
op.create_index('ix_application_lower_package', 'application',
                [sa.text('lower(package_name)')], unique=False)
```

With no opclass named, PostgreSQL applies the default for `text`, which is
`text_ops`. The diagnostic's `indexdef` lines confirm this from the catalogue:
they read `(lower(app_name))` with no opclass suffix. Had a pattern opclass
been used, `indexdef` would end `text_pattern_ops`.

### Collation — not confirmed, and I am not going to assert it

The diagnostic prints the database collation on its third line. That line was
not included in the report, so **I cannot state the collation**, and I will
not infer a specific locale name from the plans.

What the plans *do* establish, and this is sound: the collation is **not
`C` or `POSIX`**. Under a C collation PostgreSQL converts a prefix `LIKE` into
index bounds even with the default `text_ops` opclass, so the first two queries
would have shown an Index Cond. They did not. Some collation-aware locale is in
effect — most likely whatever `postgres:16-alpine` initialised, but that is a
guess, not a finding.

**Please paste the `collation:` line** from the diagnostic output. It changes
nothing in the recommendation below — the fix is correct under any non-C
collation — but the note should record the real value rather than a deduction.

## 3. Why the combined query shows an Index Scan with no Index Cond

Two separate things are happening, and neither is the index doing selection.

**The index is serving the `ORDER BY`, not the `WHERE`.** F-01 ends with:

```sql
ORDER BY lower(app_name), package_name LIMIT 20
```

`ix_application_lower_name` is ordered by `lower(app_name)`, which is the
query's leading sort key. The planner walks that index in order, applies the
`OR` predicate as a `Filter` to each row it fetches, and stops once the `LIMIT`
is satisfied. That is a legitimate use of an index — it avoids a sort and can
terminate early — but it is an **ordering** use, so there is no Index Cond to
report.

**An `OR` across two different columns cannot be served selectively by one
index at all.** `lower(app_name) LIKE … OR lower(package_name) LIKE …` needs
two index scans combined with a `BitmapOr`. A single index scan can only
filter, which is exactly what the plan shows.

The consequence is the opposite of a speed-up when few rows match: the plan
walks the **entire** index and fetches **every** heap row to evaluate
`lower(package_name)` in the filter, then returns nothing. That is why
PostgreSQL chooses a sequential scan when `enable_seqscan` is left on — the
seq scan is genuinely cheaper.

## 4. Recommended approach — add two `text_pattern_ops` indexes, change nothing else

A B-tree index whose opclass is `text_pattern_ops` orders text byte-wise, which
is the same semantics `LIKE` itself uses. The planner can then rewrite
`lower(col) LIKE 'wha%'` into bounds on that index.

**The decisive property: the SQL does not change.** The predicate, the
`lower()` on both sides, the `escape="\\"` and the `ORDER BY` all stay exactly
as committed. Requirement 5 — preserve case-insensitive prefix semantics and
literal wildcard escaping — is met by construction rather than by re-testing a
rewritten query.

### Expected plan afterwards

```
Limit
  -> Sort  (lower(app_name), package_name)
       -> Bitmap Heap Scan on application
            Recheck Cond: (...)
            -> BitmapOr
                 -> Bitmap Index Scan on ix_application_lower_name_pattern
                      Index Cond: ((lower(app_name) ~>=~ 'wha') AND (lower(app_name) ~<~ 'whb'))
                 -> Bitmap Index Scan on ix_application_lower_package_pattern
                      Index Cond: ((lower(package_name) ~>=~ 'wha') AND (lower(package_name) ~<~ 'whb'))
```

`~>=~` and `~<~` are the pattern-opclass comparison operators. Note that a
bitmap scan does not preserve order, so the `ORDER BY` reappears as a `Sort`.
On at most 20 rows that is free.

**Expected, not measured.** It must be confirmed by running the diagnostic
again after the migration.

### A trap found while preparing this — verified

The obvious SQLAlchemy spelling **silently produces an index with no opclass**.
Compiled against the PostgreSQL dialect:

```
sa.Index("ix", sa.text("lower(app_name) text_pattern_ops"))
  -> CREATE INDEX ix ON application (lower(app_name) text_pattern_ops)     correct

sa.Index("ix", sa.func.lower(c.package_name),
         postgresql_ops={"lower(package_name)": "text_pattern_ops"})
  -> CREATE INDEX ix ON application (lower(package_name))                  opclass dropped
```

No error, no warning. `postgresql_ops` keys match column names, not
expressions, so the second form yields a second useless index that looks right
in review and in `models.py`. **Use the `sa.text` form, and assert the opclass
in a test** rather than asserting only that the index exists — which is the
mistake C-15 and the current test already made once.

### One caveat to verify, not assume

Prefix extraction from a `LIKE` pattern happens at **plan** time and needs the
pattern as a constant. PostgreSQL substitutes bind parameters when it builds a
*custom* plan, but a *generic* plan has no value to extract a prefix from, and
psycopg3 promotes a statement to a server-side prepared statement after a few
executions.

The diagnostic gives evidence this is not currently a problem: the range query
used bind parameters too and still produced an Index Cond, so parameters were
being substituted. But the generic-plan path should be checked once F-01 is
behind an endpoint and the same statement runs repeatedly. If it bites,
`prepare_threshold=None` on the psycopg connection or a literal-bound pattern
resolves it. Recorded so it is not discovered during the demonstration.

## 5. Why not the range-based predicate

The range alternative rewrites the predicate to use the **existing** indexes:

```sql
lower(col) >= 'wha' AND lower(col) < 'whb'
```

It is tempting — the diagnostic shows it works, and it needs **no migration at
all**, which is the cheapest possible answer to a frozen-schema problem.

**It is also the wrong answer, and the reason is correctness, not cost.**

`>=` and `<` compare using the database collation. Computing the upper bound in
Python means guessing the successor string *in that collation*, and the two do
not agree. PostgreSQL has `make_greater_string` for exactly this and it is
careful; application code incrementing the last code point assumes code-point
order.

This project's data makes the hazard concrete. Package names are dot-separated
— `com.whatsapp`, `com.example.weather` — and collation-aware comparison treats
punctuation specially: several glibc locales give `.` a lower primary weight
than letters, so a range on `'com.'` can order rows in a way a code-point
successor does not predict. The failure mode is a **silently missing row**, not
an error. For a tool whose entire output is "this disclosure is inconsistent",
a search that quietly fails to find an application is worse than a slow one.

| | `text_pattern_ops` indexes | Range predicate |
|---|---|---|
| Migration needed | Yes, additive | **None** |
| F-01 SQL changes | **No** | Yes |
| Escaping behaviour | unchanged by construction | must be re-derived for the bounds |
| Correct under any collation | **Yes** — byte-wise, same as `LIKE` | **No** — depends on collation vs. Python agreeing |
| Risk if wrong | none found | silently missing results |
| Immune to generic plans | no (see caveat) | yes |

The range approach's one real advantage is the generic-plan immunity. That is
not worth a silent-wrong-answer risk on dotted identifiers.

**Recommendation: `text_pattern_ops`. Reject the range rewrite.**

## 6. Must the existing default-opclass indexes be kept?

**Yes. Keep both; the migration is purely additive.**

Three reasons, in order of weight:

1. **They are part of the frozen baseline and an approved decision (C-15).**
   Dropping them is a change to approved design, which needs its own ruling and
   is not what this note asks for.
2. **A pattern-opclass index cannot serve the `ORDER BY`.** `text_pattern_ops`
   supports the byte-wise operators and `=`, but not `<`/`>` in the default
   collation, so it cannot provide `ORDER BY lower(app_name)`. The existing
   index can. (With at most 20 rows to sort this is a convenience, not a
   requirement.)
3. **Two tests assert them by name** — `test_case_insensitive_search_indexes_exist`
   and `test_functional_lower_indexes_exist` — and so does the
   migration-equivalence test.

Cost of keeping all four: on 300–500 rows each index is a handful of pages,
on the order of 16 KB. Write amplification is irrelevant when the corpus is
imported a few hundred rows at a time.

## 7. Effect on ALG-11's complexity claim and on 300–500 applications

**Phase 3 claims O(log N + m). Today the behaviour is O(N).** The plan walks
the whole index and filters every row, so the approved complexity figure is
not what the system does. With the pattern indexes it becomes a genuine
O(log N + m) per branch, two branches combined by `BitmapOr`, plus a sort of at
most `limit` rows.

**At the target corpus size this changes nothing a user could notice, and the
note should not pretend otherwise.** 500 rows of this table is a few pages;
a sequential scan of it is sub-millisecond. After the migration PostgreSQL will
very likely **still choose a sequential scan** at this size, because it is
still the cheaper plan — so the verification must use `enable_seqscan = off`,
and any claim that "the index is used in production" would be false at 500
rows.

What the fix buys is therefore precise, and worth stating that way at the viva:

- The approved complexity claim becomes **true** rather than aspirational.
- The behaviour stays correct **if the corpus grows** beyond the pilot scale.
- NFR performance statements about search stop resting on an index that cannot
  serve the query.

It does not buy measurable speed, and no performance improvement should be
reported.

---

## 8. Exact proposed changes

Nothing below has been created. All three parts must land together, because
`test_every_index_matches_the_models` compares the models to the migration.

### 8.1 New Alembic revision — `0002_pattern_ops_search_indexes.py` (written)

Revision `0002_pattern_ops`, `down_revision = "0001_baseline"`.
`0001_baseline_schema.py` is untouched, and the assertion
`source.count("op.create_index(") == 21` in `test_migration_is_frozen.py` is on
`0001` only, so it is unaffected.

**As written, it differs from the sketch below in one way that matters:** the
operator class is attached through `postgresql_ops` keyed on a **labelled**
expression, not through `sa.text`. `sa.text("lower(app_name) text_pattern_ops")`
compiles identically for *both* dialects, so SQLite would receive PostgreSQL
syntax and reject it at execution. The labelled form is dialect-aware — see
§10.2.

```python
"""Add text_pattern_ops functional indexes for ALG-11 prefix search (C-53).

Additive. The two existing default-opclass indexes are retained: they serve
ORDER BY lower(app_name), which a pattern opclass cannot.
"""

revision = "0002_pattern_ops_search_indexes"
down_revision = "0001_baseline_schema"


def upgrade() -> None:
    op.create_index(
        "ix_application_lower_name_pattern",
        "application",
        [sa.text("lower(app_name) text_pattern_ops")],
        unique=False,
    )
    op.create_index(
        "ix_application_lower_package_pattern",
        "application",
        [sa.text("lower(package_name) text_pattern_ops")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_application_lower_package_pattern", table_name="application")
    op.drop_index("ix_application_lower_name_pattern", table_name="application")
```

Both operations are index-only. No table, column, constraint or data is
touched, and the revision is reversible.

**SQLite question, resolved.** No dialect guard is needed. `postgresql_ops` is
a dialect-specific option that other dialects ignore, so the same construct
emits `(lower(app_name) text_pattern_ops)` for PostgreSQL and
`(lower(app_name))` for SQLite. The revision therefore applies cleanly to the
in-memory databases the unit suite uses, and that is tested by actually
applying it — not by compiling it.

### 8.2 `backend/app/db/models.py` — two index declarations

Appended to `Application.__table_args__`, leaving the existing two unchanged:

```python
# C-53: the default-opclass indexes above cannot serve a prefix LIKE under a
# collation-aware collation. These can; the two are kept side by side because
# only the default opclass serves ORDER BY lower(app_name).
Index("ix_application_lower_name_pattern",
      text("lower(app_name) text_pattern_ops")),
Index("ix_application_lower_package_pattern",
      text("lower(package_name) text_pattern_ops")),
```

`sa.text`, not `postgresql_ops` — see the trap in §4.

### 8.3 Tests needed

| Test | Where | Asserts |
|---|---|---|
| `test_pattern_ops_indexes_exist` | unit, `test_schema.py` | both names present in `Application.__table_args__` |
| `test_every_index_matches_the_models` | unit, `test_migration_is_frozen.py` | **must be amended** — its hardcoded `functional` set lists only the two original names; the two new expression indexes are not reflected by SQLite either, so they must be added to that set or the test fails |
| `test_pattern_opclass_is_actually_applied` | **integration** | `pg_indexes.indexdef` for each new index **ends in `text_pattern_ops`**. This is the test that catches the silently-dropped opclass, and the one the existing tests are missing |
| `test_prefix_search_uses_an_index_condition` | **integration** | with `enable_seqscan = off`, `EXPLAIN` of the F-01 statement contains `Index Cond` and `~>=~`, and `BitmapOr` |
| `test_functional_lower_indexes_exist` | integration, existing | **failure message needs correcting** — it currently says a `lower()` index means "ALG-11's case-insensitive prefix search would not use it" otherwise, which the diagnostic has disproved. The message asserts the very thing C-53 refutes |
| existing 43 integration tests | unchanged | must still pass — results must not change, since the SQL does not |
| `test_results_are_unchanged_by_the_new_indexes` | **integration** | the regression guard: same matches, same escaping, same case-insensitivity, same limit |
| `scripts/explain_application_search.py` | re-run | the first two queries must change from "NO" to "yes" |

**The regression guard that matters most** is the existing 43: because the SQL
is unchanged, any difference in their results would mean the opclass altered
semantics, which it must not.

## 9. Known limitations

1. **No performance improvement.** At 300–500 rows PostgreSQL will still
   prefer a sequential scan with `enable_seqscan` on, and that is the correct
   plan. The correction makes the approved **O(log N + m)** claim true — the
   behaviour today is O(N), a full index walk with a filter — and keeps it true
   if the corpus grows. No speed-up should be reported.
2. **Generic plans.** Prefix extraction from a `LIKE` pattern happens at plan
   time and needs the pattern as a constant. A *generic* plan has none, and
   psycopg3 promotes a statement to a server-side prepared statement after a
   few executions. The eligibility tests inline the pattern as a literal so
   they measure the operator class rather than this. It must be re-checked once
   F-01 sits behind an endpoint; `prepare_threshold=None` resolves it if it
   bites.
3. **Prefix-only search is unchanged.** C-55 still stands: a substring query
   finds nothing. pg_trgm with GIN remains the documented upgrade path and is
   not implemented.
4. **The collation is recorded: `en_US.utf8`.** Measured on the team Mac,
   2026-11-05. It is a collation-aware locale, not `C` or `POSIX`, which is
   exactly the condition under which a default-`text_ops` index cannot serve a
   prefix `LIKE`. C-53's premise is therefore confirmed by measurement and not
   only by the absence of an index condition.
5. **`privacy_auditor` remains unmigrated**, so the correction is not applied
   to any database the project actually uses yet.

## 10. Verification — what to run

Nothing in this section has been executed. PostgreSQL runs in Docker Desktop on
the team Mac and is not reachable from where the implementation was carried
out.

### 10.1 Collation, read-only

Run against any of the existing databases; it reads catalogue tables only and
modifies nothing:

```sql
SELECT current_database(), datcollate, datctype
FROM pg_database WHERE datname = current_database();
```

The diagnostic script prints the same two values, plus `alembic_version` and
every index's operator class from `pg_opclass`:

```
TEST_DATABASE_URL="postgresql+psycopg://auditor:PASSWORD@localhost:5432/privacy_auditor_frozen_20261105_test" \
  .venv/bin/python scripts/explain_application_search.py
```

**Record the `datcollate` value in this section when it is available.** The
correction does not depend on it: `text_pattern_ops` is byte-wise under every
collation. The one case it would change is `C` or `POSIX`, where the baseline
indexes already serve a prefix `LIKE` and C-53 would not apply; the integration
test skips with that explanation rather than measuring something else.

### 10.2 PostgreSQL DDL — verified offline, no server needed

Alembic's offline mode emits the real SQL without connecting. This was run and
is the actual output:

```
$ cd backend && POSTGRES_PASSWORD=offline-dummy alembic upgrade 0001_baseline:0002_pattern_ops --sql

CREATE INDEX ix_application_lower_name_pattern ON application (lower(app_name) text_pattern_ops);
CREATE INDEX ix_application_lower_package_pattern ON application (lower(package_name) text_pattern_ops);
UPDATE alembic_version SET version_num='0002_pattern_ops' WHERE alembic_version.version_num = '0001_baseline';
```

```
$ alembic downgrade 0002_pattern_ops:0001_baseline --sql

DROP INDEX ix_application_lower_package_pattern;
DROP INDEX ix_application_lower_name_pattern;
UPDATE alembic_version SET version_num='0001_baseline' WHERE alembic_version.version_num = '0002_pattern_ops';
```

The operator class is present in the emitted DDL. That answers the
"do not assume it compiled" requirement at the DDL level; whether PostgreSQL
*stored* it is a separate question, which §10.4 settles from `pg_opclass`.

### 10.3 Disposable database — superseded

**`docs/C53_VERIFICATION_PROCEDURE.md` is the procedure to follow.** It was
written after re-reading `docker-compose.yml` and corrects two errors below:

- The Compose service is **`database`**, not `db`. Every `docker compose exec`
  in this section would have failed.
- Against the frozen database the expected result is **46 passed, 7 skipped**,
  not 45 and 8: there are 53 integration tests and **7** are gated on
  `0002_pattern_ops`.

It also removes the need to handle the password by hand, through
`scripts/test_database_url.py`.

The sketch is kept below for the record, with its errors, because the note is a
historical document.

#### Original sketch — contains the two errors above

**The three existing databases are not to be touched**: `privacy_auditor`,
`privacy_auditor_test`, `privacy_auditor_frozen_20261105_test`. None of them is
migrated, reset, truncated or dropped by anything in this correction, and no
test creates or drops a database.

Create a new, uniquely named one. Substitute today's date and your password:

```bash
# SUPERSEDED - DO NOT RUN. The service below is wrong: it is 'database', not
# 'db', so every exec here fails with "no such service". Follow
# docs/C53_VERIFICATION_PROCEDURE.md instead.

# 1. A name that cannot collide with anything that exists.
NEW_DB=privacy_auditor_c53_20261105_test

# 2. Confirm it does not already exist. If this prints a row, choose another
#    name - do not reuse it.
docker compose exec -T db psql -U auditor -d postgres \
  -c "SELECT datname FROM pg_database WHERE datname = '$NEW_DB'"

# 3. Create it. CREATE DATABASE cannot run inside a transaction, hence -c.
docker compose exec -T db psql -U auditor -d postgres \
  -c "CREATE DATABASE $NEW_DB"

# 4. Apply the baseline and then C-53's revision to it, and nothing else.
cd backend
POSTGRES_DB=$NEW_DB ../.venv/bin/alembic upgrade head
cd ..

# 5. Confirm both revisions are recorded.
docker compose exec -T db psql -U auditor -d $NEW_DB \
  -c "SELECT version_num FROM alembic_version"
```

Step 4 uses `upgrade head`, which applies `0001_baseline` then
`0002_pattern_ops` to the **new** database only. `POSTGRES_DB` is set for that
one command and does not persist.

If step 2 prints a row, or step 3 fails for any reason, **stop**. Do not fall
back to an existing database. Report the error instead.

### 10.4 The tests

Against the **disposable** database, where the C-53 tests execute:

```bash
TEST_DATABASE_URL="postgresql+psycopg://auditor:PASSWORD@localhost:5432/privacy_auditor_c53_20261105_test" \
  .venv/bin/python -m pytest tests/integration -p no:warnings -v
```

Expect **53 passed**: 29 schema + 24 search. (The note originally said "43
plus 10"; the search file holds 24 tests, of which 7 are gated.)

Against the **frozen** database, which stays at the baseline:

```bash
TEST_DATABASE_URL="postgresql+psycopg://auditor:PASSWORD@localhost:5432/privacy_auditor_frozen_20261105_test" \
  .venv/bin/python -m pytest tests/integration -p no:warnings -v
```

Expect **46 passed, 7 skipped** — corrected from "45 passed, 8 skipped". The
7 skips are the tests needing `0002_pattern_ops`. That asymmetry is
deliberate: it proves the skip guard works rather than silently passing on an
unmigrated database.

Then re-run the diagnostic from §10.1 against the disposable database. The two
prefix `LIKE` rows must change from `NO` to `yes`.

### 10.5 Downgrade, on the disposable database only

```bash
cd backend && POSTGRES_DB=privacy_auditor_c53_20261105_test ../.venv/bin/alembic downgrade 0001_baseline
```

Then re-run §10.4 against it: the eight C-53 tests should skip again, and the
43 originals must still pass. That demonstrates reversibility against a real
server rather than against SQLite alone.

Cleanup is yours to decide. `DROP DATABASE privacy_auditor_c53_20261105_test`
removes only the disposable one; nothing in the project requires it to survive,
and nothing requires it to be dropped either.

## 11. Outstanding

1. Everything in §10 — none of it has been executed.
2. The `datcollate` value, for §10.1.
3. Whether the disposable database is kept or dropped after verification.

D-1 is unaffected: nothing here touches `disclosure_snapshot`.
