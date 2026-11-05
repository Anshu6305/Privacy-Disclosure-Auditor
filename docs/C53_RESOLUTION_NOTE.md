# C-53 resolution note — ALG-11 index usability

Date: 2026-11-05
Status: **proposal awaiting approval.** No migration, index, model, query or
database was changed in producing this note.
Finding confirmed by: the C-53 diagnostic run on the team Mac against
`privacy_auditor_frozen_20261105_test`, 2026-11-05.

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

### 8.1 New Alembic revision — `0002_pattern_ops_search_indexes.py`

A **new** revision. `0001_baseline_schema.py` is not touched, and the
assertion `source.count("op.create_index(") == 21` in
`test_migration_is_frozen.py` is on `0001` only, so it is unaffected.

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

**SQLite note.** The unit suite applies the baseline to in-memory SQLite, which
rejects `text_pattern_ops`. Either the revision guards on
`op.get_bind().dialect.name == "postgresql"`, or the unit tests continue to
apply `0001` only. The second is simpler and matches what the suite does
today; it should be decided before the revision is written.

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
| `scripts/explain_application_search.py` | re-run | the first two queries must change from "NO" to "yes" |

**The regression guard that matters most** is the existing 43: because the SQL
is unchanged, any difference in their results would mean the opclass altered
semantics, which it must not.

## 9. What is needed to proceed

1. The `collation:` line from the diagnostic output, for the record (§2).
2. Approval to add a **second** Alembic revision — this is the first time the
   schema moves past the frozen baseline, and it is a precedent worth ruling on
   deliberately rather than by implication.
3. A decision on the SQLite guard in §8.1.
4. Confirmation that correcting the misleading failure message in
   `test_functional_lower_indexes_exist` is in scope.

D-1 is unaffected: nothing here touches `disclosure_snapshot`.
