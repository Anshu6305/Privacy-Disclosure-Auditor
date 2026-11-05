# Development Log

Dated record of what was built and what was actually verified. "Verified" means
a command was run and its result observed, not that the code looked right.

---

## 2026-11-04 — Milestone 1: Repository and development environment

### Built

- Repository tree per master plan §4. `analysis/` sits outside `backend/` so
  the pipeline carries no web or database dependency.
- `backend/app/config.py` — environment-driven settings, no usable credential
  defaults, ALG-4 thresholds as configuration.
- `backend/app/main.py` — FastAPI application, single-source scope statement,
  SPA mount added last so API routes keep precedence.
- `backend/app/api/routes/health.py` — liveness, and a database readiness check
  that runs a real query.
- `backend/app/db/session.py` — lazily created engine; importing opens no
  connection.
- `docker-compose.yml` and `backend/Dockerfile` — three services, SPA built in
  a Node stage and served by FastAPI.
- `frontend/` — Vite + React shell, API client that surfaces errors rather than
  swallowing them, scope banner, development service-status panel.
- `ml/data/opp115_schema.py` and `ml/data/verify_opp115.py` — corpus structure
  and a verification script that writes a checksum manifest.
- `.gitignore`, `.dockerignore`, `.env.example`, `pyproject.toml`,
  `data/README.md`, `README.md`.
- Documentation: master plan, traceability, consistency log, requirement change
  log, this log, team tracker, expenditure, references.

### Verified

| Check | Command | Result |
|---|---|---|
| Test suite | `pytest tests` | 17 passed |
| Lint | `ruff check .` | All checks passed |
| Frontend build | `npm install && npm run build` | 34 modules, built in 318 ms |
| OPP-115 corpus | `python ml/data/verify_opp115.py --write-manifest` | 115/115 files, structurally consistent, 230 files hashed |

### Measured from the corpus

- 115 annotation files, 115 policy texts, 23,194 annotated practices.
- Category distribution: First Party Collection/Use 38.5%, Third Party
  Sharing/Collection 22.5%, Other 15.3%, User Choice/Control 7.7%, Data
  Security 4.3%, International and Specific Audiences 4.0%, User Access, Edit
  and Deletion 3.2%, Policy Change 2.4%, Data Retention 1.6%, Do Not Track 0.4%.
- 146,926 attribute entries, of which 77,906 (53.0%) carry usable spans with
  real character offsets.
- Segments per policy: minimum 1, maximum 104, mean 33.0. The one-segment
  document is `988_solarviews.com`, a 703-byte policy — inspected directly to
  confirm it is a genuinely short document and not a parsing failure. It is
  relevant to F-10 analysability validation.

### Found and corrected

- The compose file briefly had four services, which contradicted the approved
  three-container deployment. Corrected before commit; recorded as C-01.
- The OPP-115 manual documents the last two annotation columns in the wrong
  order. Confirmed across all 23,194 rows. The loader now identifies the URL by
  content; recorded as C-07.
- An initial span count implied nearly half the corpus was damaged. The
  majority of absences are span-free by design; genuine errata are 0.18%.
  Recorded as C-08.

### Not verified in this environment

- `docker compose up` — Docker is not installed in the authoring environment.
  Must be run on a team machine before the deployment can be called working.
- PostgreSQL connectivity — no server in the authoring environment. Unit tests
  deliberately run with no database.

---

## 2026-11-04 — Decision D-01: F-18 training-data approach

Team chose **Option A**: NLI-pretrained encoder used zero-shot as the baseline,
then fine-tuned on 300 to 500 manually labelled pairs, conditional on
sufficient reliable annotation. Five safeguards are binding and recorded in the
master plan and the consistency log.

Written in support of safeguard 1: `docs/ANNOTATION_GUIDELINES_ALIGNMENT.md`
(v1.0-draft) — label definitions, ordered decision rules, hard rules,
double annotation with third-annotator adjudication, Cohen's kappa, and
application-grouped splits. Documentation only. No F-18 code was written;
implementation stays in Milestone 6.

---

## 2026-11-04 — Milestone 2: Database implementation

### Built

- `analysis/vocabulary.py` — every closed value set in one place: 5 verdicts,
  4 gold labels, 3 alignment labels, 3 record types, 4 queue states, 2 source
  types, 3 model tasks, 2 variants, 2 span types, the 14 Data Safety categories
  and a lazy accessor for the 10 OPP-115 categories. Placed in `analysis/` so
  the database layer depends on it and not the reverse.
- `backend/app/db/models.py` — all sixteen tables.
- `backend/alembic.ini`, `backend/migrations/env.py`,
  `backend/migrations/script.py.mako` — Alembic, with the database URL read
  from the environment so no credential is committed.
- `backend/migrations/versions/0001_baseline_schema.py` — baseline revision,
  built from the model metadata with a guard that refuses to run if the table
  count is not sixteen.
- `tests/unit/test_schema.py` — 49 tests.
- `tests/integration/test_migration_baseline.py` — 3 tests, one skipped.
- `analysis/mapping/taxonomy/README.md` — where the F-15 rules will live.

### Measured

| Property | Count |
|---|---|
| Tables | 16 |
| CHECK constraints | 27 |
| UNIQUE constraints | 8 |
| Foreign keys | 26 |
| NOT NULL foreign keys on `audit_run` | 7 |
| Indexes (plus 2 functional) | 18 |

### Verified

| Check | Command | Result |
|---|---|---|
| Full suite | `pytest tests` | 68 passed, 1 skipped |
| Schema constraints | `pytest tests/unit/test_schema.py` | 49 passed |
| Lint | `ruff check .` | All checks passed |
| Alembic discovers the revision | `ScriptDirectory.walk_revisions()` | 1 revision, head `0001_baseline` |

The Data Safety category list was taken from Google Play Console Help on
2026-11-04 rather than from memory: fourteen categories, reproduced exactly.

### Found and corrected

- **BIGINT primary keys did not autoincrement on SQLite.** Every insert failed
  with `NOT NULL constraint failed`. SQLite aliases the rowid only for a column
  declared exactly `INTEGER`. Fixed with a dialect variant: PostgreSQL keeps
  BIGINT, SQLite gets INTEGER, and the tests exercise the real schema.
- **A NOT NULL JSON column was not enforcing NOT NULL.** `test_threshold_config_is_required`
  failed because SQLAlchemy serialises Python `None` into the JSON literal
  `null`, which satisfies the constraint. An audit could have been stored with
  no usable threshold configuration while looking valid. Fixed with
  `none_as_null=True`. Recorded as C-16. Found by the test, not by review.
- **The taxonomy mapping was planned under a git-ignored directory.** Moved to
  `analysis/mapping/taxonomy/`; recorded as C-17.

### Deliberately not done

- No seventeenth table for the alignment training pairs. They are training
  data, kept as a dataset file.
- No repository or service functions. The tables exist; F-04, F-05, F-28 and
  F-34 are not implemented and move with Milestone 8.
- No Milestone 3 or later work.

### Not verified in this environment

`docker compose up` and the schema against a real PostgreSQL server. JSONB,
BIGINT and the two functional `lower()` indexes have not been exercised against
the PostgreSQL dialect. `test_postgresql_schema_is_not_verified_here` is
collected and skipped so the gap stays visible. To close it on a team machine:

```bash
docker compose up -d database
cd backend && alembic upgrade head
pytest -m integration
```

---

## 2026-11-04 — Environment: Python version constraint

First setup attempt on the team machine (macOS, Apple Silicon, CPython 3.14.4)
failed. `pip install -r backend/requirements.txt -r backend/requirements-dev.txt`
aborted while generating metadata for scipy:

```
../scipy/meson.build:216:9: ERROR: Dependency lookup for OpenBLAS with method
'pkg-config' failed: Pkg-config for machine host machine not found. Giving up.
error: metadata-generation-failed
```

pip installs all requirements as one transaction, so nothing was installed and
both `pytest` and `alembic` remained absent — which is what the earlier
"command not found" messages were.

The cause was the Python version, not a missing system library. Resolved by
narrowing the supported range to 3.10 to 3.13, moving the container to
`python:3.12-slim` so development and container agree, documenting the
requirement in the README, and adding a `conftest.py` guard that reports the
problem in one sentence. Recorded as C-18.

Verified after the change: 68 passed, 1 skipped; `ruff check .` clean. These
runs are on the authoring environment's CPython 3.10.12. **The suite has not
yet been run on the team machine** — that is the next step, on Python 3.12.

---

## 2026-11-04 — Verified on the team machine

Environment rebuilt on CPython 3.12 (Homebrew `python@3.12`) on macOS, Apple
Silicon. All dependencies installed from wheels; scipy 1.14.1 downloaded rather
than compiled, confirming C-18's diagnosis.

```
68 passed, 1 skipped, 1 warning in 1.16s
```

Installed set recorded from the run: SQLAlchemy 2.0.36, alembic 1.14.0,
fastapi 0.115.6, pydantic 2.10.4, numpy 2.2.1, scipy 1.14.1,
scikit-learn 1.6.0, pandas 2.2.3, psycopg 3.2.3, pytest 8.3.4, ruff 0.8.4 —
matching the pinned requirements.

The suite now passes on two independent machines and two Python versions
(3.10.12 in the authoring environment, 3.12 on the team machine). The one
skipped test remains the PostgreSQL schema check, which still has no server to
run against.

Cleared the `pytest-asyncio` deprecation warning by setting
`asyncio_default_fixture_loop_scope = "function"` in `pyproject.toml`, so the
suite will not change behaviour when that default changes upstream.

---

## 2026-11-04 — Milestone 7: Verdict and evidence engine

Implemented ahead of M3 to M6 with team approval (C-19). Those milestones
remain outstanding and nothing in them is complete.

### Built

| Function | Module |
|---|---|
| F-14 confidence gate, ALG-4 | `analysis/confidence/gate.py` |
| F-15 taxonomy mapping, ALG-5 | `analysis/mapping/taxonomy_mapper.py` |
| F-16 declaration normalisation | `analysis/mapping/declaration_normaliser.py` |
| F-17 candidate construction, ALG-6 | `analysis/mapping/candidate_builder.py` |
| F-19 verdict assignment, ALG-8 | `analysis/verdict/verdict_engine.py` |
| F-20 evidence selection, ALG-9 | `analysis/verdict/evidence_selector.py` |
| F-21 absence recording | `analysis/verdict/absence_recorder.py` |
| F-22 inconclusive recording | `analysis/verdict/inconclusive_recorder.py` |
| Domain types | `analysis/verdict/models.py` |

Tests: `tests/unit/test_verdict_engine.py` (25),
`test_evidence_records.py` (27), `test_pipeline_stages.py` (24),
`test_type_invariants.py` (22), `test_verdict_pipeline.py` (3), and
`tests/unit/fixtures_verdict.py` for the controlled inputs.

### Verified

| Check | Command | Result |
|---|---|---|
| Full suite | `pytest tests` | 169 passed, 1 skipped |
| M7 tests only | `pytest tests/unit/test_verdict_engine.py tests/unit/test_evidence_records.py tests/unit/test_pipeline_stages.py tests/unit/test_type_invariants.py tests/unit/test_verdict_pipeline.py` | 101 passed |
| Coverage | `pytest tests --cov=analysis` | **100%** of 383 statements |
| Lint | `ruff check .` | All checks passed |

Coverage reaching 100% was not the goal and is not by itself evidence of
correctness. It is reported because the uncovered lines at 95% were all guard
clauses, and a guard that never runs in a test is not a guarantee.

### Notes on the implementation

- **F-18 is not implemented.** The engine consumes alignment judgements. Every
  judgement in the test suite is written by hand with a stated label and
  confidence. No model is called, approximated or simulated.
- **Abstention propagation is in the type, not in a function.**
  `AlignmentJudgement.abstained` is a property reading the model's flag or the
  candidate's upstream flag. A judgement stated as SUPPORTS at 0.99 built on a
  practice abstained at 0.34 still reports abstained and is not decisive.
- **No schema or API change.** `consistency_basis` is derived from the
  `declared` and `found_in_policy` columns the `verdict` table already carries.

### Found while writing the tests

- The `PolicySegmentRef` offset invariant caught an off-by-one in a test
  string before any production code used it — a 22-character sentence was
  given a 21-character span. That is the class of error the invariant exists
  to stop, since every evidence quote taken from a segment depends on it.

### Deliberately out of scope

F-18, and all of Milestones 3, 4, 5, 6, 8, 9 and 10. Persisting verdicts to the
database is F-28 and belongs to Milestone 8; the engine returns domain objects
and writes nothing.

---

## 2026-11-04 — Phase 2 and Phase 3 baseline audit

No code changed. No database was created, reset or dropped. 169 tests still
pass.

### What was done

The approved Phase 3 report was read directly from `Report_Phase-03.docx` —
Section 10.2 data dictionary, Section 10.3 constraints and indexes, and the
Section 4.2 specification of F-19 — and Phase 2 was read for NFR-07. The
implemented schema was dumped from the SQLAlchemy metadata and compared column
by column. Result: `docs/PHASE4_SCHEMA_BASELINE_AUDIT.md`.

### Principal findings

- **The schema does not match the approved data dictionary.** 63 renamed
  columns, 38 additions, 7 structural deviations, 6 omissions. Sixteen tables
  and the headline constraints match; the detail does not.
- **`verdict.confidence` is missing.** Required by Phase 3 §10.2, by F-19
  processing step 3, and by NFR-07. Absent from the ORM model, the domain
  object and the engine. The Milestone 7 report's claim that ALG-8 was
  implemented exactly as specified was true of verdict selection and false of
  F-19 as a whole. No test asserted it, so the suite did not catch it.
- **`evaluation_run` records one model instead of four versions**, so an
  end-to-end pipeline evaluation cannot be recorded at all.
- **`extracted_span` has no `model_version_id`**, so spans cannot be attributed
  to the extractor that produced them.
- **Two contradictions inside the approved report**: §10.3 says `audit_run` has
  seven NOT NULL foreign keys while §10.2 lists six; and
  `evidence_record.sentence_text` is NOT NULL by §10.2's own rule while the
  same row says offsets are null for absence records.
- **Consistency log entry C-10 was wrong** and has been corrected. It checked
  the FK count against §10.3 and not the structure against §10.2.

### Status corrections made to the documentation

- F-19: Implemented and verified → **Partially implemented**.
- F-15: Implemented and verified → **Mechanism only; no mapping rules authored**.
- M2: Implemented and verified → **Implemented, PostgreSQL unverified**.

### PostgreSQL

Still never contacted. The authoring environment is a Linux VM with only the
project folder mounted and cannot reach services on the Mac. A read-only
command for the team to run is given in audit Part 4, and a genuine integration
test is proposed in Part 5 — proposed, not written, pending approval.

### Not done, deliberately

No correction from the audit was implemented. No milestone was started. The
team asked for findings only.

---

## 2026-11-04 — Audit corrections: class E restorations

Team approved proceeding with the class E restorations. Class D deviations were
**not** touched and still await a ruling.

### Changed

- `analysis/verdict/models.py` — `CategoryVerdict.confidence`, nullable, range-checked.
- `analysis/verdict/verdict_engine.py` — `_deciding_confidence` helper; all five
  ALG-8 steps now set confidence per F-19 step 3.
- `backend/app/db/models.py` — `verdict.confidence NUMERIC(5,4)` + CHECK;
  `extracted_span.model_version_id` NOT NULL FK + index;
  `application.store_category`; `extracted_practice.practice_type`;
  `evaluation_metric.scope`; `gold_annotation` index extended to
  `(app_id, ds_category)`; `DESC` restored on two time-ordered indexes.
- `tests/unit/test_verdict_confidence.py` — new, 15 tests.
- `tests/unit/test_schema.py` — 5 tests added; 4 fixtures updated for the new
  NOT NULL columns.
- `tests/integration/test_postgresql_schema.py` — new, 29 tests.

### Verified

| Check | Command | Result |
|---|---|---|
| Full suite | `pytest tests` | **189 passed, 30 skipped** |
| Verdict confidence | `pytest tests/unit/test_verdict_confidence.py` | 15 passed |
| Lint | `ruff check .` | All checks passed |
| Safety guard, project database | `TEST_DATABASE_URL=...privacy_auditor pytest tests/integration/test_postgresql_schema.py` | **Refused**, as designed |
| Safety guard, `_test` database with no server | same with `..._test` | 29 skipped cleanly |

### Found while doing this

- The new NOT NULL `scope` and `extracted_span.model_version_id` broke four
  existing fixtures, which is the schema tests doing their job.
- `create_engine` sat outside the try block in the PostgreSQL fixture, so a
  missing psycopg driver produced 29 errors instead of 29 skips. Fixed. Anyone
  who has not installed the full requirements now gets skips.

### Still outstanding

- **Class D findings D-1 to D-10** — unchanged, awaiting the team.
- **DOC-1 and DOC-2** — contradictions inside the approved Phase 3 report,
  needing a faculty ruling.
- **E-2** — deferred until D-1 is decided.
- **`practice_type` and `scope` have no defined vocabulary.** The columns exist;
  Phase 3 defines no values for either. Not invented.
- **PostgreSQL still never contacted.** 29 tests ready; none has run.
- **Migration strategy undecided** — the read-only check in audit Part 4 has not
  been run.

---

## 2026-11-05 — Docker up; first PostgreSQL run exposed three defects

Docker Desktop 29.9.2 installed on the team Mac. `postgres:16-alpine` pulled,
`auditor_database` healthy on 127.0.0.1:5432. `privacy_auditor_test` created
alongside the project database.

The read-only check reported `tables: 0`, `alembic_version present: False`,
confirming the baseline had never been applied anywhere. **Strategy A** from
audit Part 4 therefore applies: `0001_baseline` can be frozen safely because
nothing depends on it yet.

### First integration run: 28 failed, 1 passed, 1 skipped

Every failure traced to one cause: `relation "application" does not exist`. The
schema had never been created in the test database, because
`alembic upgrade head` failed before touching it.

Three defects found, all mine, all fixed.

**1. Configuration could not be found from the directory Alembic runs in.**

`Settings` declared `env_file=".env"`, which pydantic-settings resolves against
the current working directory. `.env` is at the repository root, but
`alembic.ini` is in `backend/`, so Alembic must run from there — where the
path resolved to `backend/.env`, which does not exist. No password was loaded,
`env.py` raised its "no database password configured" error, and the migration
never ran.

Fixed by anchoring the path to the repository root, derived from the location
of `config.py` rather than from the working directory. Verified by loading
settings from inside `backend/` and confirming the password resolves.

**2. A test passed on an empty database.**

`test_audit_run_foreign_keys_are_all_not_null` queried
`information_schema.columns` for `audit_run`, got no rows, and asserted that
none of those zero rows was nullable — which is trivially true. It was the one
test that passed, and it passed for the worst possible reason. It now asserts
that eight identifier columns exist before checking their nullability. The two
constraint-catalogue tests had the same weakness and now assert a non-empty
catalogue first.

**3. 28 failures for one cause.**

An unmigrated database produced 28 separate failures that each read like a
different defect. A session-scoped gate now fails once, naming the cause and
the command to fix it. `_udt_name` also fails explicitly when a column is
absent, instead of returning None and surfacing as `assert None == 'jsonb'`,
which reads like a type mismatch rather than a missing column.

**4. Tests were about to start reading the developer's own `.env`.**

A consequence of fixing defect 1: with `.env` now discoverable from anywhere,
the unit suite picked up the real database password and
`test_database_health_reports_unconfigured_without_credentials` failed. The
suite would have behaved differently on a machine with a `.env` than on one
without. `conftest.py` now sets an empty password explicitly, which takes
precedence over the file and keeps the unit tests hermetic. The PostgreSQL
tests are unaffected; they never use `Settings`.

### Verified after the fixes

| Check | Result |
|---|---|
| `pytest tests` | 189 passed, 30 skipped |
| `ruff check .` | All checks passed |
| PostgreSQL tests with no server | 29 skipped cleanly |

**PostgreSQL verification has still not been achieved.** The migration has not
yet been applied and the 29 tests have not yet passed. The next run is the
first real attempt.

---

## 2026-11-05 — PostgreSQL verified

The baseline applied cleanly after the configuration fix:

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_baseline,
      Baseline schema: the sixteen tables of the approved Phase 3 design.
```

```
$ .venv/bin/pytest -m integration -v
platform darwin -- Python 3.12.16, pytest-8.3.4
collected 219 items / 189 deselected / 30 selected
tests/integration/test_migration_baseline.py s
tests/integration/test_postgresql_schema.py .............................
                29 passed, 1 skipped, 189 deselected in 0.44s
```

**This is the first time any part of this project has run against PostgreSQL.**

### Now verified on PostgreSQL 16 (postgres:16-alpine)

| Property | Result |
|---|---|
| Alembic upgrade executes and stamps `0001_baseline` | Pass |
| 16 tables created | Pass |
| `threshold_config`, `training_config` are JSONB | Pass |
| 11 primary keys are BIGINT | Pass — SQLite reports INTEGER for these, so this was unverifiable until now |
| Timestamps are `timestamptz` | Pass |
| `verdict.confidence` is NUMERIC | Pass |
| Both functional `lower()` indexes exist | Pass |
| 28 CHECK constraints present in `pg_constraint` | Pass |
| 8 UNIQUE constraints present | Pass |
| `audit_run`: 8 identifier columns, no nullable reference | Pass |
| PostgreSQL rejects a sixth verdict value | Pass |
| PostgreSQL rejects `Undetermined` in the gold set | Pass |
| PostgreSQL rejects evidence with no quote | Pass |
| PostgreSQL rejects an absence record carrying a quote | Pass |
| PostgreSQL rejects two verdicts for one category | Pass |
| PostgreSQL rejects a failed audit with no reason | Pass |
| PostgreSQL rejects an out-of-range verdict confidence | Pass |

The last seven matter most. The SQLite suite proved the constraints were
*declared*; these prove the database the system will actually run on
*enforces* them.

### Two predictions that were wrong

Before the run I said I expected failures from `NUMERIC` returning `Decimal`
rather than `float`, and from the functional-index assertion being written
from documentation rather than from a real `pg_indexes` row. Neither failed.
The type tests read `information_schema.columns.udt_name` rather than a Python
value, so the Decimal question never arises, and the index definition does
contain `lower` as written. Recorded because the caution was published and
should not be left standing as though it had been borne out.

### State of the databases

| Database | State |
|---|---|
| `privacy_auditor` | **Empty. 0 tables. Never migrated.** Untouched throughout |
| `privacy_auditor_test` | Schema applied, stamped `0001_baseline`, used by the 29 tests |

Every test ran inside a transaction that was rolled back, so even the test
database holds no rows from the run.

### Still outstanding

- `0001_baseline` is still a metadata build, not a frozen migration. Strategy A
  from audit Part 4 is now the confirmed path.
- Class D findings D-1 to D-10, and DOC-1 and DOC-2, still await rulings.
- `practice_type` and `scope` still have no defined vocabulary.

---

## 2026-11-05 — Alembic baseline frozen (Strategy A)

Team approved Strategy A with seven safeguards. No existing database was
dropped, reset, recreated or modified; no `docker compose down -v`; no
`DROP DATABASE`.

### What was done

`0001_baseline_schema.py` no longer calls `Base.metadata.create_all()`. It now
contains 16 explicit `op.create_table` calls and 21 `op.create_index` calls,
with all 28 CHECK constraints, 8 UNIQUE constraints and 27 foreign keys
written out, plus a matching downgrade.

The body was **rendered by Alembic's own `render_python_code`** against the
PostgreSQL dialect rather than written by hand or transcribed. The generator
is kept at `backend/migrations/freeze_baseline.py` so the derivation is
reproducible. The revision id is unchanged at `0001_baseline`.

**One deliberate edit to the rendered output.** Alembic rendered `func.now()`
as `sa.text('now()')` because it was asked to render for PostgreSQL, and
`now()` is not a SQLite function, so the revision could not run on SQLite at
all. The models declare `func.now()`, which every dialect understands, so the
rendered text was replaced with `sa.func.now()`. Seven occurrences. Recorded in
the migration's own docstring.

### Equivalence verified

`tests/unit/test_migration_is_frozen.py`, 10 tests, all passing. It applies the
revision to an empty database and compares the result against `Base.metadata`:

| Checked | Result |
|---|---|
| Revision contains no `create_all` or `drop_all` in its function bodies | Pass |
| 16 `create_table`, 21 `create_index`, 16 `drop_table` | Pass |
| Revision id, down_revision and expected table count unchanged | Pass |
| Created tables equal the model tables | Pass |
| Every column name and nullability matches, table by table | Pass |
| Indexes match, with the two functional ones checked in source | Pass |
| 8 UNIQUE constraints match | Pass |
| 28 CHECK constraints match | Pass |
| 27 foreign keys match | Pass |
| Downgrade leaves no tables behind | Pass |

The frozen-check test inspects the `upgrade` and `downgrade` function bodies
via `ast` rather than searching the whole file, because the module docstring
legitimately names `create_all` while explaining why it is gone. A naive
substring search flagged the prose, which is how that was found.

### The skipped test, identified

Safeguard 6. The single skip in the 29-passed run was
`tests/integration/test_migration_baseline.py::test_postgresql_schema_is_not_verified_here`.

It was a placeholder written during Milestone 2, an unconditional
`pytest.skip` whose only purpose was to keep the unverified-PostgreSQL gap
visible in the test report rather than letting it be forgotten. It asserted
nothing. The gap it marked was closed on 2026-11-05 by the 29 real tests, so
the placeholder is obsolete and has been removed along with its file. The
file's other two tests were superseded: `test_baseline_creates_exactly_the_sixteen_tables`
and `test_schema_round_trips_create_and_drop` are both covered, more strictly,
by `test_migration_is_frozen.py`.

### Verified

| Check | Result |
|---|---|
| `pytest tests` | **197 passed, 29 skipped** |
| `ruff check .` | All checks passed |
| Frozen-migration equivalence | 10 passed |

The 29 skips are the PostgreSQL suite, which skips without `TEST_DATABASE_URL`.
There is no longer any unconditional skip in the suite.

### Outstanding for the team to run

The frozen migration has **not** yet been applied to a PostgreSQL database.
Verification against a newly created, uniquely named database is the next step
and requires commands on the team machine; it creates a new database and
touches neither `privacy_auditor` nor `privacy_auditor_test`.

### Note on `privacy_auditor_test`

That database remains stamped `0001_baseline` from the **previous**,
metadata-built version of the revision. It was not modified, per safeguard 1.
It should now be treated as superseded: the authoritative verification is the
new database created for the frozen revision.

### Frozen baseline verified on PostgreSQL

A new database was created for the purpose and neither existing database was
touched:

```
$ docker exec -i auditor_database psql -U auditor -d privacy_auditor \
    -c "CREATE DATABASE privacy_auditor_frozen_20261105_test OWNER auditor;"
CREATE DATABASE

$ cd backend && POSTGRES_DB=privacy_auditor_frozen_20261105_test \
    ../.venv/bin/alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_baseline,
      Baseline schema: the sixteen tables of the approved Phase 3 design.

$ .venv/bin/pytest -m integration -v
collected 226 items / 197 deselected / 29 selected
tests/integration/test_postgresql_schema.py .............................
                29 passed, 197 deselected in 0.45s
```

**29 passed, nothing skipped.** The frozen revision produces the same schema
the metadata build produced and that was verified earlier the same day. That
is the result Strategy A had to demonstrate: the migration is now a fixed
historical record rather than a snapshot of whatever the models happen to say.

The run also confirms the obsolete placeholder is gone — the previous
integration run reported "29 passed, 1 skipped" and this one reports no skip.

### Databases on the team machine, after this task

| Database | State | Touched? |
|---|---|---|
| `privacy_auditor` | Empty, 0 tables, never migrated | **No** |
| `privacy_auditor_test` | Stamped `0001_baseline` from the **old** metadata build; superseded | **No** |
| `privacy_auditor_frozen_20261105_test` | Created for this verification; stamped `0001_baseline` from the frozen revision | Created, then verified |

No database was dropped, reset or recreated. No `docker compose down -v`, no
`DROP DATABASE`.

---

## 2026-11-05 — Decision table revised after team challenge

No code, model, migration or database changed. 197 passed, 29 skipped.

The team challenged D-2, D-6, D-7 and DOC-2 and asked for each to be
demonstrated rather than argued. All three challenges were correct.

**D-6.** Ran the committed `assign_category_verdict` against an empty
judgement list: it returns Declared-not-in-policy with an F-21 absence record.
Then ran all five verdict scenarios using only practice-backed judgements
carrying no `declared_practice_id` — all five reachable. The approved NOT NULL
structure is sufficient and my nullable two-sided design was unnecessary.
Worse, a declaration-only candidate has no policy text for F-18 to read, so it
invites a label for a pair with nothing to compare; the existing fixture emits
`NO_MATCH` at 0.95, a number with no basis. Recommendation reversed to
restore.

**D-7 and DOC-2.** Read F-21 and F-22 in full. F-21 requires a fixed
system-generated absence statement *stored in the record*, with no segment
reference. §10.2's note nulls `segment_id` and the offsets, not the text.
There is no contradiction; DOC-2 withdrawn and D-7 reversed to restore the
single NOT NULL `sentence_text` column.

**D-2.** Checked Google's developer documentation and a third-party Data
Safety scraper's documented output. Both are positive-only: collected and
shared lists, no not-collected list. Also confirmed `acquisition/` holds one
empty `__init__.py`, so this project has never parsed a declaration and I had
no basis for the claim. Withdrawn. The real distinctions — an app-level
"declares no collection" statement, and parsed-but-empty versus
could-not-parse — belong with E-2.

**Revised balance:** seven compliance restorations, two implementation
deviations, one document correction, two withdrawals. The first edition
claimed six changes and three amendments to the approved design, which
overstated how often the approved design was at fault.

Deliverable: `docs/PHASE4_DECISION_TABLE.md`, rewritten. The three superseded
entries in `docs/PHASE4_SCHEMA_BASELINE_AUDIT.md` are annotated in place
rather than deleted, so the original reasoning and its correction both remain
on the record.

---

## 2026-11-05 — Milestone 3A: acquisition layer and offline corpus

Built the acquisition layer and corpus format. **No database model, migration
or database was touched.** No application was collected and no live retrieval
was performed.

### Built

| File | Purpose |
|---|---|
| `acquisition/models.py` | Domain objects, no database dependency |
| `acquisition/declaration.py` | F-04 normalisation |
| `acquisition/policy_document.py` | F-05 loading and SHA-256 verification |
| `acquisition/gateway.py` | F-06 gateway, rate limiter, cache |
| `acquisition/adapters.py` | F-06 replaceable transports |
| `acquisition/provenance.py` | F-07 provenance and append-only log |
| `acquisition/corpus.py` | Corpus layout, manifest, validation |
| `scripts/validate_corpus.py` | Validation CLI |
| `tests/fixtures/sample_corpus/` | One **invented** sample record |
| `docs/M3_ACQUISITION_REPORT.md` | The milestone report |

Tests: `test_acquisition_declaration.py` (13), `test_acquisition_policy.py`
(10), `test_acquisition_gateway.py` (21), `test_acquisition_corpus.py` (26).

### Verified

| Check | Result |
|---|---|
| `pytest tests` | **267 passed, 29 skipped** |
| M3A tests only | **70 passed** |
| `ruff check .` | All checks passed |
| `scripts/validate_corpus.py --root tests/fixtures/sample_corpus` | RESULT: usable — 1 record, 1 analysable, 0 duplicates, 0 hash mismatches |

### Found while building

- **ruff was linting at py312 while `requires-python` allows 3.10.** It
  suggested `datetime.UTC`, which is 3.11+ and would have broken the floor of
  our own supported range. Target corrected to `py310`, the oldest supported
  version.
- **`record_from_dict` crashed with `AttributeError` on a JSON array**
  instead of reporting a format error. Caught by a test written for exactly
  that case; now raises `CorpusFormatError`.

### Deliberately not done

- No live retrieval. `play.google.com` is unreachable here and is not on the
  session allowlist, so the adapter has never been exercised against a real
  page. The normalisation rules rest on Google's documentation and are
  labelled provisional.
- No application collected. The sample record is invented;
  `com.example.sampleapp` is not a real application.
- No database work. F-01, F-02, F-03 and the database halves of F-04, F-05
  and F-07 are M3B, pending D-1.
- M4, M5, M6 not started.

---

## 2026-11-05 — Milestone 4: policy text processing (T2)

F-08, F-09 and F-10. No database, no API, no M3A interface changed.

### Built

`analysis/text/` — `models.py`, `extractor.py` (F-08), `segmenter.py` (F-09),
`validator.py` (F-10), `pipeline.py` (T2 end to end). Tests:
`test_text_extraction.py` (24), `test_text_segmentation.py` (23),
`test_text_analysability.py` (31).

### Verified

| Check | Result |
|---|---|
| `pytest tests` | **345 passed, 29 skipped** |
| M4 tests only | **78 passed, 0 skipped** |
| `ruff check .` | All checks passed |
| Sample pipeline run | 628-byte fixture → 495 chars cleaned → 12 segments, all slice-verified → analysable, 85 tokens |

The 29 skips are the PostgreSQL suite, which skips without
`TEST_DATABASE_URL`. Nothing in M4 was skipped.

### Decisions worth recording

- **Offsets index F-08's cleaned text**, which follows from Phase 3 defining
  F-09's input as that text. Raw-HTML offsets were considered and rejected;
  they would need a character map through tag stripping, entity decoding,
  normalisation and whitespace collapsing, which the approved design does not
  call for.
- **The cleaned text is stored** at `processed/<source-sha256>.txt`, because
  an offset is worthless without the document it counts characters in, and
  F-25 needs one to highlight.
- **No fallback sentence splitter.** A different splitter would move sentence
  boundaries, so the same policy would produce different evidence offsets on
  different machines.
- **spaCy moved to the base requirements.** F-09 needs it for the baseline
  pipeline, and a baseline-only install could not previously segment a policy.

### Found while building

- **Single newlines survived into segment text.** In HTML a source newline
  renders as a space, so one surviving into a quoted sentence would be a line
  break the policy never had. Found by reading the extractor's actual output
  on the fixture rather than by a failing test. Now collapsed to a space,
  while paragraph breaks are preserved.
- **spaCy 3.8.3 needed `click`** which did not arrive with the pinned install
  in this environment. Noted in case a team member hits the same.

### Deliberately not done

No database persistence, no new tables, no migration, no API endpoint, no
worker integration, no scraping, no classifier, no span extraction, no
alignment, no verdict-engine change, no frontend. M5, M6 and M3B not started.

### Limitation that matters most

**No real privacy policy has ever been processed.** Every document in the
suite is an invented fixture, and the operational corpus is still 0 of 300–500.
Real policies are far messier, and extraction will need adjustment once some
exist.

---

## 2026-11-05 — Milestone 5: baseline practice classifier (T3.1)

F-11 baseline, ALG-2. No database, no API, no improved model.

### Built

`analysis/models/practice_classifier.py` (F-11 baseline),
`ml/data/opp115_dataset.py`, `ml/data/splits.py`, `ml/evaluation.py`,
`ml/train_baseline_classifier.py`. Tests: `test_opp115_dataset.py` (19),
`test_baseline_classifier.py` (38). Reports:
`docs/M5_OPP115_DATASET_INSPECTION.md`,
`docs/M5_BASELINE_CLASSIFIER_REPORT.md`.

### Dataset inspection, before any training

- 115 policies, **3,792 segments**, 23,194 annotation records. The unit is the
  segment, so 3,792 examples — not 23,194.
- **Every segment of every policy was read by all three annotators.** Verified
  with zero uncovered segments. This is what makes an absent category a
  defensible negative; without it the whole construction would have been
  unsound and the milestone instruction required stopping.
- The filename stem is **not** the CSV's policy ID: `135_instagram.com.csv`
  carries `3850` in column D. Grouping by the wrong one would scatter a policy
  across splits.
- Label rule chosen by measuring all three: majority (2 of 3) leaves 1.7%
  unlabelled; unanimous would have discarded 24%.

### Measured result

| Split | Macro-F1 | Micro-F1 | Hamming |
|---|---|---|---|
| train | 0.9367 | 0.9237 | 0.0189 |
| validation | 0.7717 | 0.7734 | 0.0546 |
| **test** | **0.7489** | **0.7690** | **0.0545** |

80 / 17 / 18 policies, 2,634 / 617 / 541 segments, seed 20261105, **zero
policy overlap**. Test split used once.

The 0.19 train-to-test gap is overfitting and is reported as such.

### The result that must not be quoted

**Do Not Track: F1 0.857 on 4 test examples.** Three predictions, all correct,
one miss. One different prediction moves the F1 between roughly 0.57 and 1.00.
The corpus has 31 positive segments in total. **Data Retention: F1 0.429 on
7.** Both are flagged automatically and recorded as `"reliable": false`.

The macro-F1 of 0.7489 includes both, so it is flattered by two scores that
are noise. The report says this in its opening section.

### Verified

| Check | Result |
|---|---|
| `pytest tests` | **402 passed, 29 skipped** |
| M5 tests only | 57 passed, none skipped |
| `ruff check .` | All checks passed |
| Model reload, offline | Identical predictions |
| F-14 integration | 9 practices in, 9 out, 8 flagged abstained |
| `git check-ignore` | model, metrics and processed data all ignored |

### Deliberately not done

No improved model, span extraction, alignment, taxonomy change, verdict
change, schema change, migration, endpoint, worker or frontend. F-34 registry
persistence not implemented. The validation split is unused — it exists for
tuning that has not been done.

### Limitation that matters most

OPP-115 is a corpus of **website** policies from 2016; this project audits
**Android applications** in 2026, and the operational corpus still does not
exist. The model is also trained on OPP-115's segments and will be applied to
F-09's, which have different boundaries. The held-out score measures neither
of those gaps.

---

## 2026-11-05 — Milestone 3B: planning only, no implementation

Authorised as planning. **No model, migration, database or application code
was touched.** `git status` before the commit showed exactly two documentation
files changed and one added.

### What was produced

`docs/M3B_IMPLEMENTATION_PLAN.md` — F-01 to F-07, FR-01 to FR-07, task T1.

The substance of it:

**M3A maps cleanly onto three of the four tables it needs.** `application`,
`declared_practice` and `policy_segment` are direct field-for-field mappings.
`disclosure_snapshot` is the one that depends on D-1, which is why M3A was
built with `Provenance` as a **per source document** record — the smaller
unit, from which either arrangement can be assembled without rewriting it.

**Three of seven functions do not depend on D-1 at all.** F-01
(searchApplications), F-03 (handleUnknownApplication) and the application
repository could be built today. F-02, F-04, F-05, F-06 and F-07 all need to
know what a snapshot is first.

### Where the two options genuinely differ

Not in difficulty. In which approved document gets amended, and in one
behaviour:

**Partial retrieval failure.** Phase 1 named scraper breakage the project's
highest-probability risk, so a collection event where one source succeeds and
the other fails is expected to be common, not a corner case.

- Option A (one row per collection event) has one hash column, one path and
  one `status` for two sources. The per-source HTTP status, byte count and
  failure reason have nowhere to live unless a seventeenth table is added.
- Option B (one row per source) handles it with no special case: the
  successful source gets its row and its own hash, the failed one gets a
  failure row. M3A's five `Provenance.outcome` values map straight through.

Option B also makes a changed Data Safety page detectable **by digest**;
under Option A the declaration is parsed into rows and never hashed, so a
change can only be found by diffing parsed rows.

Option A's advantage is that it is the design already approved, needs no
change-log entry, and reads audit history directly. Option B needs faculty
approval and reads history through `audit_run` — which, on inspection, is
what FR-25 and FR-26 actually compare anyway.

Both are written up without a recommendation, because D-1 is the faculty's
ruling to make.

### Two things neither option can store

Found in M3A, independent of D-1, and raised separately rather than folded in:

1. **`declares_no_data_collected`** — Google's app-level "this app doesn't
   collect or share any user data". Distinct from a declaration that merely
   omits a category, and ALG-8 could reasonably treat it differently.
2. **`SecurityPractices`** — encryption in transit, deletion availability,
   independent security review.

Neither is required by FR-01 to FR-07, so M3B is not blocked by them.

### The pilot, proposed and not performed

~20 applications in six deliberately chosen groups — including three that
declare **no** data collected, two with non-English policies, and three with
very short policies to test F-10's analysability floor. Chosen to exercise the
pipeline, not to be representative; 20 applications cannot be representative
of anything, and the plan says so.

Four likely findings are recorded **in advance**, so they cannot later be
presented as successes: the declaration normalisation rules were written from
Google's documentation and never from an inspected page; M4's extractor has
only processed invented fixtures; some policies will not be retrievable at
all; and F-10's thresholds were chosen against OPP-115 website policies, not
Android ones.

The M5 baseline will be run over the pilot segments as a **smoke test only**.
There are no gold labels for those 20 applications, so no accuracy figure can
be computed from them and none will be reported.

### Tracker corrected

`docs/TEAM_TRACKER.md` now records Docker as installed, the frozen Alembic
baseline, D-2/D-6/D-7 as withdrawn, E-5 as restored, and a new block spelling
out what M1 to M7 amount to: 0 applications, 0 live retrievals, 0 rows in
`privacy_auditor`, no end-to-end run, 1 of 3 learning tasks trained, no gold
set, and no F-15 mapping rules authored. Complete at unit-test level with
controlled fixtures is not the same as working, and the tracker now says so
rather than leaving it to be discovered at the viva.

### Unchanged, deliberately

M4 and M5 implementations, the M5 baseline artefact, its policy-grouped split,
its seed and its held-out test results. The baseline stays the reference
experiment; it was not retrained and the test set was not touched.

### Still blocked

M3B implementation on D-1. M6 on labelled alignment pairs and the gold set.
M8, M9, M10 not started.

---

## 2026-11-05 — Milestone 3B part 1: application repository, F-01, F-03

Authorised as the D-1-independent slice of M3B. F-02 and F-04 to F-07 remain
untouched and unimplemented.

### Files

| File | Change |
|---|---|
| `backend/app/db/repositories/application_repo.py` | New. `ApplicationRepository`, F-01, F-03 |
| `backend/app/db/repositories/__init__.py` | New exports; was empty |
| `backend/app/config.py` | Two settings added, both marked PROVISIONAL |
| `tests/unit/test_application_repository.py` | New, 43 tests |
| `tests/integration/test_application_search_postgresql.py` | New, 14 tests |
| `scripts/explain_application_search.py` | New, read-only diagnostic |

No model, migration or database change. `app/db/models.py`,
`backend/migrations/` and the `analysis/`, `ml/` and `acquisition/` packages
are byte-identical to commit `e469189`.

### Design

**Search returns dataclasses, not ORM rows.** `ApplicationSummary` carries
exactly the three fields FR-01 names — app name, developer name, package name
— and **deliberately omits `app_id`**. The surrogate key is an internal
detail; package name is the identifier everything else in the system uses.
`ApplicationDetail` carries `app_id` because F-02 will need the foreign key,
and nothing in F-01's response shape includes it.

**`get_by_package` is case-sensitive, and the search is not.** Android package
names are case-sensitive identifiers under a UNIQUE constraint; folding case
on exact lookup would let two distinct identifiers resolve to one row. The
prefix search folds case on both sides, which is what ALG-11 specifies.

**LIKE metacharacters are escaped.** Without it, a query of `%` matches the
entire corpus and `_` becomes a single-character wildcard. Three tests cover
it, including the fixture application literally named "100% Battery".

**Ordering is explicit.** `ORDER BY lower(app_name), package_name`. Without
it the same query can return the same rows in a different order on a different
plan, which makes both a paged interface and a test unreliable.

### Two numbers that are not approved requirements

Phase 3 requires F-01 to apply a *configured* result limit and sets no number;
it says nothing about a minimum query length. Both are now in `Settings`,
labelled PROVISIONAL in the same words as the F-10 thresholds:

- `application_search_limit = 20`
- `application_search_min_query_length = 2`

A query below the minimum returns an empty list, not an exception: FR-01
describes an as-you-type box, and one keystroke is not a query. Recorded as
C-54.

### F-03: the distinction the implementation exists to protect

An adapter being configured means a fetch **can be attempted**. It does not
mean one would succeed, and `AcquisitionGateway` returns recorded failures
rather than raising. So the two messages differ and the configured one says,
in those words, that attempting is "not the same as obtaining the data".
A test asserts the strings "has been retrieved", "was collected" and "now
available" appear nowhere in it.

`can_request_audit` is **False in both branches**. An audit needs two
disclosure snapshots; an application absent from the corpus has none. That is
what "avoid creating an invalid audit request" means here, and it is asserted
for both values of `live_retrieval_configured`.

`live_retrieval_configured` is passed in by the caller rather than read from
the gateway, so the backend keeps no dependency on the acquisition package.

### Found and recorded, not fixed — C-53

**The two ALG-11 functional indexes may be inert for this query.** A B-tree
index on an expression serves a prefix `LIKE` only when its opclass orders
text byte-wise (`text_pattern_ops`) or the database collation is `C`. Both
indexes use the default opclass, so under a collation-aware default the
planner may sequential-scan regardless of row count.

This is **not verified**, and I could not verify it: PostgreSQL runs in Docker
Desktop on the Mac and is not reachable from where these commands ran.
`scripts/explain_application_search.py` measures it read-only — it reports the
collation, the index definitions, and whether each predicate can use an index
with `enable_seqscan` off, because on a four-row table a sequential scan is
the correct plan whatever indexes exist.

Correctness is unaffected either way; only search cost changes, and on 300 to
500 applications a sequential scan is not noticeable. Fixing it would alter
the frozen schema, which this milestone may not touch, so it is an open
finding awaiting a ruling.

### Also flagged — C-55

`search("app")` returns **nothing**, though four fixtures contain "app" inside
their names. Prefix search working as approved, but a user typing the middle
of a name will find nothing. A test asserts it so the limitation is recorded
rather than discovered. If FR-01 was meant to mean substring search, that is a
requirement change, not a code fix; pg_trgm with GIN stays the documented
upgrade path.

### Verified

| Check | Command | Result |
|---|---|---|
| New unit tests | `pytest tests/unit/test_application_repository.py -q` | **43 passed** |
| Full suite | `pytest tests -p no:warnings` | **445 passed, 43 skipped** |
| Lint | `ruff check .` | All checks passed |
| F-01 and F-03 demonstration | ad-hoc script over 6 invented fixtures | Output in the completion report |

Before this milestone: 402 passed, 29 skipped. The arithmetic is 402 + 43 =
445 and 29 + 14 = 43.

### Not verified — stated as not verified

**The 14 PostgreSQL integration tests did not run.** They skipped, because no
PostgreSQL was reachable: Docker Desktop runs on the Mac and these commands
ran where it is not. Skips are not passes. To run them:

```
cd backend && TEST_DATABASE_URL=postgresql+psycopg://auditor:PASSWORD@localhost:5432/privacy_auditor_frozen_20261105_test \
  ../.venv/bin/python -m pytest ../tests/integration -q
```

and for C-53:

```
TEST_DATABASE_URL=... .venv/bin/python scripts/explain_application_search.py
```

### Untouched, confirmed

D-1 unresolved and unresolved-by-implication: nothing here reads or writes
`disclosure_snapshot`. `privacy_auditor` still has **zero tables and no
`alembic_version`** — it was not migrated, as instructed. The frozen
`0001_baseline_schema.py` is unchanged. M4, M5, the baseline artefact, its
split, its seed and its held-out results are untouched.

Also untouched: `declares_no_data_collected` and `SecurityPractices` remain
unrepresentable, and no column was added for them.

---

## 2026-11-05 — C-53 confirmed on real PostgreSQL; resolution proposed

Diagnostic run by the team on the Mac against
`privacy_auditor_frozen_20261105_test`. **43 PostgreSQL integration tests
passed** (29 schema + 14 F-01 search), so F-01 and F-03 return correct results
on real PostgreSQL. Separately, the index diagnostic confirmed C-53.

### What was measured

| Predicate | Result |
|---|---|
| `lower(app_name) LIKE 'wha%'` | no useful index condition |
| `lower(package_name) LIKE 'wha%'` | no useful index condition |
| F-01 as implemented (OR over both) | Index Scan, **Filter only, no Index Cond** |
| range: `lower(col) >= … AND < …` | real Index Cond, index used |

### Why the combined plan shows an Index Scan with no Index Cond

Two things, neither of them the index doing selection.

**It is serving the `ORDER BY`.** `ix_application_lower_name` is ordered by
`lower(app_name)`, the query's leading sort key, so the planner walks it in
order, applies the `OR` as a Filter, and stops at the `LIMIT`. An ordering use
has no Index Cond to report.

**An `OR` across two columns cannot be served selectively by one index.** It
needs two index scans combined by `BitmapOr`; a single scan can only filter.

When few rows match this is worse than a sequential scan — it walks the whole
index and fetches every heap row to evaluate `lower(package_name)`. Which is
precisely why PostgreSQL picks a seq scan with `enable_seqscan` on.

### Recommended: two `text_pattern_ops` indexes, SQL unchanged

Full note in `docs/C53_RESOLUTION_NOTE.md`. The decisive property is that
**the F-01 query does not change at all** — predicate, `lower()` on both
sides, `escape="\\"` and `ORDER BY` all stay as committed — so the
case-insensitive prefix semantics and the literal wildcard escaping are
preserved by construction, not by re-testing a rewrite.

### The range rewrite was rejected, on correctness

It needs no migration, which made it the tempting answer. But `>=` and `<`
compare in the **database collation**, and computing the upper bound in Python
assumes code-point order. The two do not agree, and this project's data makes
it concrete: package names are dot-separated, and several glibc locales give
`.` a lower primary weight than letters, so a range on `'com.'` can order rows
in a way a code-point successor does not predict. The failure mode is a
**silently missing row**. For a tool whose output is "this disclosure is
inconsistent", a search that quietly fails to find an application is worse than
a slow one.

### A trap found while preparing the proposal — verified by compiling the DDL

```
sa.Index("ix", sa.text("lower(app_name) text_pattern_ops"))
  -> CREATE INDEX ix ON application (lower(app_name) text_pattern_ops)   correct

sa.Index("ix", sa.func.lower(c.package_name),
         postgresql_ops={"lower(package_name)": "text_pattern_ops"})
  -> CREATE INDEX ix ON application (lower(package_name))                opclass dropped
```

No error, no warning: `postgresql_ops` keys match column names, not
expressions. The obvious spelling produces a second useless index that looks
right in review. The proposal therefore requires a test asserting
`indexdef` **ends in** `text_pattern_ops` — not merely that the index exists,
which is the mistake C-15 and the current test already made once.

### Honest on the benefit

**At 300 to 500 applications this buys no measurable speed, and after the
migration PostgreSQL will very likely still choose a sequential scan**, because
on a few pages that remains the cheaper plan. Verification must use
`enable_seqscan = off`, and no performance improvement should be reported.

What it buys: the approved **O(log N + m)** complexity claim becomes true
rather than aspirational — today the behaviour is O(N) — and it stays true if
the corpus grows.

### Not asserted

**The database collation.** The diagnostic prints it; that line was not
included in the report, so the note records that it is *not* `C` — deduced
soundly from the absence of an Index Cond, since a C collation yields index
bounds even with the default opclass — and asks for the actual value rather
than naming a locale I did not see.

### Also recorded

`test_functional_lower_indexes_exist` fails with the message that otherwise
"ALG-11's case-insensitive prefix search would not use it". The diagnostic has
disproved that: the index exists, is functional, and the search does not use
it. The message asserts the very thing C-53 refutes and needs correcting.

### Changed in this entry

Documentation only. `docs/C53_RESOLUTION_NOTE.md` added; the M3B plan now
separates Completed / Verified / Pending / Blocked; C-53's status, the tracker
and the traceability matrix updated. **No migration, index, model, query or
database was changed**, and no second Alembic revision was created — it is
specified in the note and awaits approval, because moving past the frozen
baseline for the first time is a precedent worth ruling on deliberately.

---

## 2026-11-05 — C-53 corrected: additive revision 0002_pattern_ops

Approved and implemented. First time the schema moves past the frozen
baseline, and it does so additively: two indexes, nothing else.

### Files

| File | Change |
|---|---|
| `backend/migrations/versions/0002_pattern_ops_search_indexes.py` | New revision |
| `backend/app/db/models.py` | Two `Index` declarations added to `Application`; existing two untouched |
| `tests/unit/test_pattern_ops_indexes.py` | New, 13 tests |
| `tests/unit/test_migration_is_frozen.py` | Index-equivalence test restructured; three new tests |
| `tests/integration/test_application_search_postgresql.py` | +10 C-53 tests |
| `tests/integration/test_postgresql_schema.py` | Failure message corrected; no assertion removed |
| `scripts/explain_application_search.py` | Now prints `datctype`, `alembic_version`, and operator classes from `pg_opclass` |

### The detail the whole correction turns on

Three ways to attach an operator class, two of which fail silently. Compiled
against both dialects before choosing:

```
sa.text("lower(app_name) text_pattern_ops")
   postgresql  (lower(app_name) text_pattern_ops)
   sqlite      (lower(app_name) text_pattern_ops)     <- SQLite rejects this at execution

func.lower(c).  postgresql_ops={"app_name": ...}
   postgresql  (lower(app_name))                      <- operator class silently dropped

func.lower(c).label("lower_app_name"), postgresql_ops={"lower_app_name": ...}
   postgresql  (lower(app_name) text_pattern_ops)
   sqlite      (lower(app_name))                      <- correct for both
```

`postgresql_ops` keys match column names or an expression's **label**, not the
expression. Keyed on the column it compiles with no error and no warning and
produces a default-class index that looks right in review and cannot serve the
query. The third form needs no dialect guard, because `postgresql_ops` is
ignored by other dialects.

So the SQLite question raised in the proposal does not need answering: no
guard, and the revision applies to in-memory SQLite as it stands. That is
tested by **applying and reversing it**, not by compiling it.

### Tests, and what they distinguish

The old `test_functional_lower_indexes_exist` failed with "ALG-11's
case-insensitive prefix search would not use it", which C-53 disproved — the
index exists, is functional, and the search does not use it. Corrected to
separate three properties, with no assertion removed:

1. **existence** — in the catalogue at all;
2. **expression correctness** — indexes `lower(col)`, not `col`;
3. **operator-class correctness** — whether a prefix `LIKE` can use it. The
   baseline pair **cannot**, by design, and that now lives in the docstring
   rather than in a misleading message.

`test_pattern_ops_opclass_in_catalogue` reads `pg_opclass` rather than parsing
`pg_indexes.indexdef`, because `indexdef` **omits the operator class when it is
the default** — a `text_ops` index and a `text_pattern_ops` index can print
identically. That is the only check that catches the silently-dropped class,
and it is the one C-15's original test was missing.

`test_baseline_does_not_contain_the_c53_correction` asserts the frozen revision
contains neither `text_pattern_ops` nor the two new names, so the fix cannot
drift backwards into the historical record.

### Verified — executed here

| Check | Result |
|---|---|
| PostgreSQL DDL, Alembic offline mode | `CREATE INDEX ... (lower(app_name) text_pattern_ops)` for both |
| Downgrade DDL, offline | drops exactly the two, reverses `alembic_version` |
| Revision applies on SQLite | both indexes in `sqlite_master`, **no** `text_pattern_ops` in the stored SQL |
| Downgrade on SQLite | `after_upgrade - before == {the two}`; `after_downgrade == before` |
| New unit tests | 13 + 3 passed |
| Full suite | **461 passed, 53 skipped** |
| `ruff check .` | All checks passed |

Offline mode is worth noting: it emits the real PostgreSQL SQL without a
server, so "do not assume the operator class compiled" is answered at the DDL
level by observation rather than argument.

### Not verified — and I could not verify it

**Nothing was executed against a PostgreSQL server.** Docker Desktop runs on
the team Mac; it is not reachable from where these commands ran. The 10 C-53
integration tests **skip** until a database upgraded to `0002_pattern_ops` is
supplied, guarded on `alembic_version`. Skips are not passes.

Outstanding, with commands in `docs/C53_RESOLUTION_NOTE.md` §10: the catalogue
operator classes, the `EXPLAIN` eligibility of both prefix predicates, the
combined-query plan and its `BitmapOr`, the upgrade/downgrade against a real
server, and the database collation.

### Databases

`privacy_auditor`, `privacy_auditor_test` and
`privacy_auditor_frozen_20261105_test` were not touched — not migrated, reset,
truncated or dropped. **No test creates or drops a database.** Verification
needs a new disposable one, and §10.3 gives the exact steps including a
pre-check that refuses to reuse an existing name.

Deliberate asymmetry worth knowing: run against the frozen database the suite
gives **45 passed, 8 skipped** rather than 53 passed, because that database
stays at the baseline. The skip guard working is itself the evidence that these
tests cannot pass vacuously on an unmigrated database.

### The complexity claim, kept as approved

Phase 3's **O(log N + m)** is unchanged. The new indexes are what make it
true: each branch of the `OR` becomes an index range scan of m matches,
combined by `BitmapOr`, instead of today's full index walk with a filter, which
is O(N).

**No performance improvement is claimed.** At 300 to 500 rows PostgreSQL will
still choose a sequential scan with `enable_seqscan` on, and that is correct.
`enable_seqscan = off` is used only to ask the planner whether the index is
*eligible*, and every test that uses it says so.

### Carried forward

C-55 unchanged — prefix-only search, so a substring query finds nothing.
The generic-plan caveat stands and must be re-checked once F-01 sits behind an
endpoint. D-1 untouched; `privacy_auditor` still at no revision.

---

## 2026-11-05 — Standing development and testing protocol adopted

Not an implementation. The team issued a permanent protocol covering every
remaining milestone, bug fix, database change, API change and integration
step. Recorded as `docs/PHASE4_DEVELOPMENT_PROTOCOL.md` so it governs future
sessions rather than living in one conversation, and summarised in a new
`CLAUDE.md` at the repository root so it is picked up before any code is
written.

### The part that changes how work is reported

Three statuses, used strictly: **Implemented** · **Tested and verified** ·
**Pending or blocked**. Implementation is not verification.

Under that rule, two entries in the tracker were overstated and are corrected:

- **M7** was "core complete at unit-test level". It is **Implemented**, not
  verified: every test uses controlled fixtures and it has never run on a real
  application.
- **M4** and **M3A** are verified only on the paths that were actually
  exercised — fixtures, and offline retrieval. Both now say so in the row
  rather than in a footnote.

**C-53 is Implemented, not verified.** Its PostgreSQL catalogue and `EXPLAIN`
checks have not been executed. A new "corrections in flight" table in the
tracker records that under *not executed because of environment limitations* —
the protocol's fifth reporting category, which is neither skipped nor passed.

### The environment limitation, written down rather than rediscovered

The protocol requires PostgreSQL and disposable-database verification for every
database change. **PostgreSQL is not reachable from a development session** — it
runs in Docker Desktop on the team Mac, on that machine's own loopback. That is
permanent, not a fault.

So §2.2 of the protocol document splits the work by who can run it: unit and
SQLite tests, Ruff, Alembic offline DDL and SQLite upgrade/downgrade in the
session; PostgreSQL integration, disposable-database upgrade/downgrade and
catalogue checks by the team, with the output reported back. A database change
therefore reaches **Implemented** in a session and **Tested and verified** only
afterwards.

Alembic offline mode is the one thing that genuinely narrows the gap: it emits
the real PostgreSQL DDL with no server, which is how the C-53 operator class
was confirmed rather than assumed.

### Where the safeguards already have teeth

§2.4 lists them, so a future session does not have to rediscover which tests
are load-bearing: the frozen-baseline tests, the model-to-migration
equivalence tests, the `_test` suffix guards, `AlignmentJudgement.abstained`
being a **property** rather than a field so abstention cannot be dropped by a
caller, the git-ignored M5 artefacts, the `"reliable": false` flag on rare-class
metrics, and the R1 to R6 placeholders that keep contributions unattributed.

### Verified

Documentation only. `pytest tests -p no:warnings` → **461 passed, 53 skipped**,
unchanged. `ruff check .` → all checks passed. No code, model, migration or
database touched.

---

## 2026-11-05 — C-53 verification procedure prepared; two errors in my own note found

No implementation. Authorised task: prepare the exact local procedure for the
team to run on the Mac. **Nothing was executed against PostgreSQL** — it is
unreachable from a development session, which is the whole reason this document
exists.

### Two errors in `docs/C53_RESOLUTION_NOTE.md` §10, found by re-reading the repository

The instruction not to guess the Compose service name was well placed.

1. **The service is `database`, not `db`.** The note's §10.3 used
   `docker compose exec -T db psql ...` throughout. `docker-compose.yml`
   declares `database`, container `auditor_database`. Every one of those
   commands would have failed with "no such service". I had written them from
   habit rather than from the file.
2. **The expected skip counts were wrong.** The note said "45 passed, 8
   skipped" against the frozen database. Counted properly: 53 integration
   tests — 29 schema plus **24** search, not 14 — and **7** gated on
   `0002_pattern_ops`, not 8. So **46 passed, 7 skipped**.

Both corrected. The superseded sketch is kept in the note, because it is a
historical document, but its code block now opens with a DO NOT RUN warning
naming the wrong service — and a copy-paste of it fails harmlessly with "no
such service" rather than touching anything.

### `scripts/test_database_url.py`

New. Composes `TEST_DATABASE_URL` from the project's own settings and prints
only the finished URL, for use as
`export TEST_DATABASE_URL="$(... privacy_auditor_c53_20261105_test)"`.

Three reasons it is worth a script rather than a typed string:

- The password never enters shell history or the terminal.
- A password containing `@`, `:`, `/` or `#` silently breaks a hand-written
  URL, because those are URL syntax. `quote(..., safe="")` handles it.
- It **refuses** the three protected database names outright, and refuses any
  name not ending in `_test`. Verified: all four refusals exit 2 and print no
  URL.

Inside the container no password is handled at all — `psql` reads
`$POSTGRES_PASSWORD` from the container's own environment, so it is never
typed, pasted or printed on the host either.

### `docs/C53_VERIFICATION_PROCEDURE.md`

Twelve steps: confirm the service name from the configuration rather than
trusting any document, confirm Docker and container health, check the
disposable name is unused and **stop if it exists**, create it, migrate only
it, read the operator classes from `pg_opclass`, read the collation, run the 53
tests, downgrade, re-run, run the diagnostic, report.

Two design points worth recording:

**Operator classes come from `pg_opclass`, not `pg_indexes.indexdef`.**
`indexdef` omits the operator class when it is the default, so a `text_ops` and
a `text_pattern_ops` index print identically. Verifying the correction by
reading `indexdef` would prove nothing — which is the trap C-15's original test
fell into.

**The frozen database is not re-run.** An earlier draft had the team re-running
the suite against it to prove the skip gate works, which was muddled: the
helper refuses that name by design. The evidence comes from step 10 instead —
downgrade the disposable database and the same 7 tests must start skipping.
Same proof, and the protected database is not involved at all.

### Honest about what the diagnostic can show

`enable_seqscan = off` establishes index **eligibility**. At 300 to 500 rows
PostgreSQL will still choose a sequential scan when the setting is left alone,
and that is correct. The procedure says so at step 11, and no performance
improvement is claimed from it.

### Verified

Documentation and one script. `ruff check .` → all checks passed.
`pytest tests -p no:warnings` → **461 passed, 53 skipped**, unchanged. No
model, migration, query or database touched. C-53 remains **Implemented**, not
verified.

---

## 2026-11-05 — D-1 ruled Option A; C-53 verification reduced to one script

### D-1: Option A

The approved Phase 3 §10.2 design stands — one `disclosure_snapshot` per
collection event. Option B is not implemented.

**No approved requirement changes.** What changes is the implementation, which
deviated: `disclosure_snapshot` carries `source_type`, one `source_url` and one
`content_sha256` per row, and `audit_run` carries two snapshot foreign keys.
M3B Part 2 restores the approved structure in a new reversible revision
`0003`; `0001_baseline_schema.py` and `0002_pattern_ops` are not modified.

**DOC-1 resolves with it.** Under Option A `audit_run` has six NOT NULL foreign
keys, so §10.3's "seven" is the error and becomes six. §10.2 stands as
approved. **E-2 is satisfied** by the restored design's `status` column, whose
value vocabulary still has to be defined and will be recorded in the change log
when it is.

Recorded in the decision table, the requirement change log, the M3B plan and
the tracker.

**One sub-decision follows, and I am not stopping to ask it.** Option A has to
handle a collection event where one source was retrieved and the other failed.
§5 of the M3B plan set out A1 against A2. **A1 will be implemented unless the
team objects:** `source_url_listing` nullable, with the snapshot `status`
recording the outcome. A2 — a per-source retrieval side table — is rejected
because it adds a seventeenth table no approved document contains, a larger
departure than the deviation being corrected.

A1's cost is recorded rather than hidden: per-source HTTP status, byte count
and failure reason have nowhere to live, so M3A's two `Provenance` objects are
merged on persistence and that detail stops at the database boundary. It
survives in the filesystem corpus record. Phase 1 named scraper breakage the
highest-probability risk, so partial events are expected to be common, and
`status` is what stops a failed source reading as an absent declaration.

### C-53: one script instead of twelve manual steps

`scripts/verify_c53.sh`. Discovers the Compose service from the configuration,
checks the daemon and container health, refuses to continue if the disposable
name exists, creates it, migrates only it, verifies `alembic_version`, reads
operator classes from `pg_opclass`, reads the collation, runs the 53
integration tests, downgrades, asserts both pattern indexes are gone and both
baseline indexes remain, re-runs the tests to prove the skip gate fires,
re-upgrades, and runs the diagnostic. Everything is tee'd to a timestamped log
so the output can be pasted back in full.

Safety is enforced rather than described: the three protected database names
are checked against the target and the script aborts on a match; it aborts if
the disposable database already exists; **there is no `DROP` anywhere in the
file**; and no password is typed, printed or passed on a command line — inside
the container `psql` reads the container's own `$POSTGRES_PASSWORD`, and on the
host the URL comes from `scripts/test_database_url.py` into a variable.

### A bug in my own helper, found by testing it

The first version of the in-container `psql` wrapper was:

```sh
sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" exec psql -U "$POSTGRES_USER" -d "$1" "$@"' _ "$@"
```

`"$@"` still contains `$1`, so the database name was passed **twice** — psql
reads the second as another dbname. Demonstrated rather than reasoned about:

```
$ sh -c 'echo "db=[$1] args=[$*]"' _ mydb -tAc "SELECT 1"
db=[mydb] args=[mydb -tAc SELECT 1]          # wrong

$ sh -c 'db="$1"; shift; echo "db=[$db] args=[$*]"' _ mydb -tAc "SELECT 1"
db=[mydb] args=[-tAc SELECT 1]               # fixed
```

The service-discovery parser was also tested against compose-shaped JSON,
including the two-postgres-services case, which it rejects rather than guessing.

### Verified

`bash -n` clean. `ruff check .` → all checks passed. `pytest tests
-p no:warnings` → **461 passed, 53 skipped**, unchanged. The verification log
pattern is git-ignored.

**C-53 is still Implemented, not verified.** Nothing in this entry ran against
PostgreSQL.

---

## 2026-11-05 — C-53 partly verified on PostgreSQL; C-56: a test that broke on its own success

### Verified on PostgreSQL 16, team Mac

| Check | Result |
|---|---|
| `ix_application_lower_name_pattern` | **`text_pattern_ops`** |
| `ix_application_lower_package_pattern` | **`text_pattern_ops`** |
| `ix_application_lower_name` | `text_ops`, retained |
| `ix_application_lower_package` | `text_ops`, retained |
| Collation | **`en_US.utf8`** |

The collation matters more than it looks. C-53's premise was that the database
is not `C` or `POSIX`, which I had **deduced** from the absence of an index
condition rather than measured. `en_US.utf8` confirms it directly, so the
finding now rests on a measurement.

The correction itself is confirmed at the catalogue level: the operator class
reached the index, which is the failure mode the note warned about.

### C-56 — the one failing test was the test

52 of 53 passed. `test_alembic_baseline_has_been_applied` asserted
`version_num == "0001_baseline"`, so a **correctly** upgraded database at
`0002_pattern_ops` failed it.

The defect is a category error I wrote in M2: the test asserted an exact
migration state when its subject is "was the approved schema ever applied".
Those are different questions, and only the second stays true as migrations
accumulate. It was guaranteed to break the first time the schema moved, which
is exactly what happened.

**Fixed with four tests derived from Alembic's own revision graph**
(`ScriptDirectory`), so no revision identifier is hard-coded beyond the
baseline:

1. `test_alembic_baseline_is_in_the_applied_ancestry` — `0001_baseline` is in
   the ancestry of whatever is recorded. True at the baseline, at
   `0002_pattern_ops`, and at any later revision.
2. `test_applied_revision_lies_on_the_path_from_head_to_base` — the recorded
   revision is known here and reachable from head. Catches a database and a
   checkout that have diverged, which ancestry alone cannot.
3. `test_pattern_indexes_match_the_applied_revision` — **the both-states
   coverage.** It derives the expectation from the recorded revision, then
   reads `pg_opclass`: at `0002_pattern_ops` both indexes must exist with
   `text_pattern_ops`; at the baseline neither may exist. A migration applied
   or reverted without its DDL taking effect fails here.
4. `test_the_baseline_functional_indexes_exist_in_every_state` — C-53 is
   additive, so the original pair is present at every revision.

Plus `applied_revision`, which asserts `alembic_version` holds **exactly one**
row rather than silently taking the first of several.

**Nothing was removed or weakened.** The old test checked one string; the
replacement checks ancestry, reachability, single-headedness, and agreement
between `alembic_version` and the real catalogue **in both directions**.

The graph logic needs no database, so it was exercised here rather than
assumed: ancestry of `0002_pattern_ops` is
`['0001_baseline', '0002_pattern_ops']`; ancestry of `0001_baseline` is
`['0001_baseline']`; head is `0002_pattern_ops`; an unknown identifier is not
reachable.

### Counts changed

Integration tests: 53 → **56** (32 schema + 24 search). Expected at
`0002_pattern_ops`: **56 passed, 0 skipped**. After downgrade: **49 passed, 7
skipped** — the 7 gated on the revision. The script's expectations were
updated to match; stale numbers in a script are how a wrong result gets
reported as right.

### Databases

Both earlier verification databases are preserved and **added to the script's
`PROTECTED` list**, so neither can be targeted again:
`privacy_auditor_c53_20261105_test` (hit the collision guard) and
`privacy_auditor_c53_20261105b_test` (carried the measurements above). The new
target is `privacy_auditor_c53_20261105c_test`. The guard was dry-run against a
protected name and aborted as designed.

Still no `DROP` anywhere in the script, and the three project databases remain
untouched.

### A slip of my own, worth recording

While editing the script I used a string replacement without asserting that it
matched, and it silently did nothing — the team had already changed
`DISPOSABLE_DB` to `b_test` locally, so my pattern missed. I only noticed by
re-reading the file afterwards. Re-applied with an assertion. Every edit script
in this repository asserts its match before writing; this one did not, and that
is the second time an unasserted assumption has cost a correction.

### Verified

`bash -n` clean. `ruff check .` → all checks passed. `pytest tests
-p no:warnings` → **461 passed, 56 skipped**.

**C-53 is still not fully verified.** Outstanding: the downgrade and
re-upgrade, the re-run proving the skip gate fires, and the `EXPLAIN`
eligibility diagnostic. The earlier run stopped at the failing test before
reaching them.

---

## 2026-11-05 — C-57: `dict(CursorResult)`, and what the Mac run did confirm

Second PostgreSQL run: **55 of 56 passed**. Confirmed in that run — migration
`0001` → `0002`, the revision recorded as `0002_pattern_ops`, both pattern
indexes at `text_pattern_ops`, both originals at `text_ops`, collation
`en_US.utf8`.

Two runs, two failures, **both of them my tests rather than the schema**. That
pattern is worth naming: the correction itself has been right each time, and
the verification code around it has not.

### C-57

`test_pattern_indexes_match_the_applied_revision` built its map with
`dict(connection.execute(...))` and failed with
`TypeError: 'CursorResult' object is not subscriptable`.

`dict()` looks for `.keys()` and takes the mapping protocol when it finds one.
`CursorResult` **has** `.keys()` — the column names — so `dict()` then tried to
subscript the result object. The error names `dict`'s fallback path, not the
real mistake, which is why it reads like a driver fault instead of a missing
`.all()`.

Reproduced on SQLite first, because the bug is in consuming the result and has
nothing to do with the backend:

```
has .keys():            True
dict(result)         -> TypeError: 'CursorResult' object is not subscriptable
dict(result.all())   -> {'ix_a': 'text_pattern_ops', 'ix_b': 'text_pattern_ops'}
empty result         -> {}
```

The empty case matters: the baseline-state branch asserts `found == {}`.

**Fix:** `.all()`, then `dict(rows)`. Ruff rejected the dict comprehension I
first wrote (C416, correctly — `rows` is a list by then), so the final form is
`dict(rows)`, which looks almost identical to the bug. The `.all()` is
load-bearing, so the comment above it says exactly that rather than leaving the
next reader to rediscover it.

**The assertion is unchanged.** Both branches are as written for C-56: both
indexes with `text_pattern_ops` at `0002_pattern_ops`, neither at the
baseline. Only the construction of `found` changed.

### Databases

`privacy_auditor_c53_20261105c_test` preserved and added to `PROTECTED`,
alongside `_test` and `b_test`. Six names are now guarded. New target:
`privacy_auditor_c53_20261105d_test`.

### Counts

Unchanged at **56** integration tests — no test was added or removed. Expected
**56 passed, 0 skipped** at `0002_pattern_ops`, and **49 passed, 7 skipped**
after the downgrade.

### Verified

Focused test, all integration, full regression: **461 passed, 56 skipped**.
`ruff check .` all checks passed. `bash -n` clean.

**C-53 still not fully verified.** Outstanding: the downgrade, the re-upgrade,
the re-run proving the skip gate fires, and the `EXPLAIN` eligibility
diagnostic — no run has reached them yet.

---

## 2026-11-05 — C-53 CLOSED: tested and verified on PostgreSQL 16

Log: `c53_verification_20261105_232120.log`, database
`privacy_auditor_c53_20261105d_test`.

| Stage | Result |
|---|---|
| Compose service, from the configuration | `database` |
| Upgrade `-> 0001_baseline -> 0002_pattern_ops` | recorded as `0002_pattern_ops` |
| Operator classes, from `pg_opclass` | both `_pattern` **`text_pattern_ops`**; both originals `text_ops` |
| Definitions | `lower((app_name)::text) text_pattern_ops`, `lower((package_name)::text) text_pattern_ops` |
| Collation | **`en_US.utf8`** |
| Integration tests, applied | **56 passed, 0 skipped** |
| Downgrade | both pattern indexes removed, **both baseline indexes retained** |
| Integration tests, removed | **49 passed, 7 skipped** — the gate fires |
| Re-upgrade | back at `0002_pattern_ops` |

**Eligibility is verified by assertion, not by reading a plan.**
`test_prefix_predicate_is_index_eligible` and
`test_combined_f01_query_is_index_eligible` are among the 56: they seed rows in
a rolled-back transaction, `EXPLAIN` with `enable_seqscan = off`, and assert an
`Index Cond` using `~>=~` on a `*_pattern` index.

No performance claim. At 300 to 500 rows a sequential scan remains the right
plan; the correction makes the approved O(log N + m) claim true, nothing more.

### C-58 — the one stage that failed, and it was mine again

Stage 11, the diagnostic script:
`TypeError: '<' not supported between instances of 'str' and 'int'`.

When I added `datctype` and `alembic_version` to its metadata query, every
column after `datcollate` shifted. I updated the print statements and missed a
row-count comparison three lines below that still read `meta[2]` — by then the
collation string.

Fixed by unpacking into names, `database, collate, ctype, row_count, applied =
meta`, so positions cannot drift out of step with the query again. Verified by
parsing the script's own SQL, counting its top-level columns, and confirming
five columns against five unpack targets.

The run also showed `rows in application: 0`, so the script now says explicitly
when the table is empty and points at the two eligibility tests as the real
evidence, instead of implying its plans prove something about an empty
relation.

**This did not affect the verification.** The assertions that matter are in the
test suite and passed at stage 9. The script is a pretty-printer.

### The pattern across three runs

Three defects during verification — C-56 (a hard-coded revision), C-57
(`dict(CursorResult)`), C-58 (a shifted tuple index) — **every one of them in
my verification code, none in the correction.** The schema change was right on
the first run. Worth stating because the opposite impression would be easy to
take from three failed runs, and because the lesson is specific: each defect
came from asserting or indexing a fixed position that something else had since
moved.

### Closed

C-53 is **Tested and verified** in the consistency log, master plan,
traceability matrix, tracker and resolution note.
`scripts/verify_c53.sh` is kept as the template for verifying future
migrations; `d_test` is added to its `PROTECTED` list and the target is now
`e_test`, so six database names are guarded and none can be reused.

Verified here: `ruff check .` all checks passed; `pytest tests -p no:warnings`
→ **461 passed, 56 skipped**; `bash -n` clean.

---

## 2026-11-05 — M3B Part 2, step 1: D-1 Option A implemented (revision 0003)

The approved Phase 3 section 10.2 structure is restored. `disclosure_snapshot`
is one row per **collection event** again, and `audit_run` references one
snapshot instead of two. `0001_baseline_schema.py` and `0002_pattern_ops` are
untouched.

| Was | Now |
|---|---|
| `source_type`, `source_url` NOT NULL | `source_url_listing`, `source_url_policy`, both nullable |
| `retrieved_at` / `retrieval_method` | `collected_at` / `retrieval_mode` |
| `storage_path`, `content_sha256` NOT NULL | `policy_doc_path`, `policy_doc_sha256` **nullable** |
| `content_bytes`, `http_status` | `policy_doc_bytes`, `policy_http_status` |
| — | `status` NOT NULL, `declares_no_data_collected` nullable |
| 7 FKs on `audit_run` | **6** — DOC-1 resolved |
| 28 CHECKs | **32** — six new ones hold a partial event together |

### The two decisions worth defending

**Partial events are the normal case, so the schema says so.** Both URLs are
nullable and `status` records the outcome. Six CHECKs stop a partial event
looking complete: the status vocabulary, the nullable hash length, the
path/hash pairing, at-least-one-source, a stored document implying its URL, and
two status-to-URL agreements. `complete` cannot be recorded without both URLs —
that is a constraint, not a convention.

**`declares_no_data_collected` is three-state.** NULL = the section was never
read. False = read, carries no app-level no-collection statement. True = read,
carries it. Collapsing NULL into False would turn a retrieval failure into an
explicit negative declaration, which is the one thing the column exists to
prevent. It is a nullable addition to the approved column list, recorded in the
requirement change log rather than applied silently.

`SecurityPractices` still has no column and none was added. It stays in the
filesystem corpus record and takes no part in verdicts.

### The revision refuses to restructure a populated table

Two per-source rows cannot be merged into one collection event: nothing in the
old structure records which declaration row belongs with which policy row, and
an application may have many snapshots of each source. A wrong guess would
attribute one application's policy to the wrong event. `upgrade()` counts rows
in `disclosure_snapshot` and `audit_run` and stops with the recovery named —
re-import from the filesystem corpus, which holds per-source provenance in
full. Every project database is empty, so this costs nothing and removes a
class of silent corruption.

Offline mode has no connection to count against, so the guard emits a comment
into the generated script rather than appearing to have checked. Found by
running `alembic upgrade --sql`, which crashed on `bind.execute(...)` returning
None.

### Batch ordering, learned the hard way

The first version failed with `KeyError: 'policy_doc_sha256'`. A batch
operation is planned against the table as **reflected when the batch opens**,
so a rename inside a batch is invisible to a later operation in the same batch.
The revision is now four sequential passes — drop, rename, add, constrain — with
a comment saying why, and the downgrade mirrors it.

### Tests changed, none weakened

- `test_audit_run_has_seven_not_null_foreign_keys` → `..._six_...`, and it now
  asserts the exact **set** of six as well as the count.
- `test_audit_cannot_compare_a_snapshot_with_itself` →
  `test_an_audit_references_exactly_one_collection_event`. The old CHECK has no
  subject under Option A: an audit cannot compare a snapshot with itself when
  there is only one. The invariant moved from a constraint that could be
  dropped into a structure where the error cannot be expressed, and the
  structure is what is asserted.
- `test_snapshot_source_type_is_restricted` →
  `test_snapshot_status_is_restricted`: the same closed-vocabulary assertion,
  on the column that now carries one.
- Seven new constraint tests, including the three-state flag.
- `test_collection_event_migration.py`: 10 tests covering the chain, the
  upgrade, the column set against the models, the downgrade, a
  downgrade/upgrade round trip, that `status` keeps no server default, and the
  populated-table refusal with its message.

**Model-to-migration equivalence now compares against the whole chain.**
`migrated_engine` applies 0001 → 0002 → 0003; a new `baseline_engine` serves
the tests that genuinely mean the frozen record. Comparing current models to
0001 alone would fail for a correct schema — the same category error as C-56,
and it would have recurred at every future migration.

Integration tests whose fixture needs the collection-event schema now **skip**
when the database is at a pre-0003 revision, rather than failing. The downgrade
stage of the verification script depends on that distinction.

### Renamed

`scripts/verify_c53.sh` → `scripts/verify_migrations.sh` via `git mv`, since it
verifies the whole revision chain rather than C-53 alone. Six earlier
disposable databases remain in `PROTECTED`; the next target is
`privacy_auditor_m3b_20261105_test`.

### Verified

| Check | Result |
|---|---|
| Migration up and down on SQLite | both clean; downgrade restores the exact prior column set |
| Offline PostgreSQL DDL | correct, including `ALTER COLUMN policy_doc_sha256 DROP NOT NULL` and all seven CHECKs |
| New migration tests | 10 passed |
| `tests/unit/test_schema.py` | 60 passed |
| Full suite | **477 passed, 56 skipped** |
| `ruff check .` | All checks passed |

**Not verified:** anything on PostgreSQL. F-02 and F-04 to F-07 are not
implemented yet — this step restored the schema they need.

---

## 2026-11-05 — C-60: the verification script hard-coded a head revision

The M3B run created `privacy_auditor_m3b_20261105_test`, applied all three
migrations correctly, and then failed because step 6 asserted the literal
`0002_pattern_ops`. The database was right; the script was wrong.

**Same category error as C-56, in a shell script instead of a test:** asserting
a fixed identifier that something else had moved. Fixed the same way — ask the
graph.

### What changed, beyond the one string

The instruction not to replace a version string without reviewing the whole
procedure was the right call; four other things were version-bound.

**Head and base are now derived.** A new step 0b reads Alembic's
`ScriptDirectory`, requires exactly one head (a branched history is reported,
not guessed at), and prints the chain. Steps 6, 10 and 10c assert against
`$HEAD_REV` and `$BASE_REV`.

**Step 9 no longer counts tests.** At head the meaningful assertion is that
**nothing skips** — every integration test should be applicable to the fully
migrated schema, and a skip there would mean a guard fired when it should not
have. The script now fails if the summary contains "skipped" and prints the
summary either way. A total like "56 passed" would have gone stale at the next
test added.

**Step 10b inverts that.** At the baseline, skips are the *evidence*: the
pattern-index checks need 0002 and the collection-event fixture needs 0003. The
script requires the run to be green **and** to contain skips, so a test that
quietly assumed a schema it had not checked for would be caught. The number is
not asserted.

**Step 10c now verifies the round trip restored the schema, not just the
version row.** It re-checks both pattern operator classes and that
`disclosure_snapshot.status` exists. A downgrade/upgrade that left the version
row right and the schema wrong would previously have passed.

### Locked down

Three new tests in `test_collection_event_migration.py`:

- the script must contain `== "$HEAD_REV"` and `== "$BASE_REV"`, and **no
  revision identifier may appear in any line that runs** (comments excepted),
  so revision 0004 cannot break it the same way;
- no `DROP DATABASE`, `DROP TABLE`, `TRUNCATE` or `down -v` in any executable
  line — the script's own safety claim, asserted rather than trusted;
- every earlier disposable database is in `PROTECTED`, and the current target
  is not.

### Databases

`privacy_auditor_m3b_20261105_test` is preserved and added to `PROTECTED`,
joining the three project databases and the four C-53 runs — eight guarded
names. The next target is `privacy_auditor_m3b_20261105b_test`.

### Verified

Unit tests, migration tests and the full suite: **480 passed, 56 skipped**.
`ruff check .` all checks passed. `bash -n` clean, and the graph-derivation
block was executed exactly as written rather than only parsed.

Option A and all three migrations are unchanged.

---

## 2026-11-05 — C-61: the run exposed two defects, and one masked the other

`1 failed, 48 passed, 7 skipped` at head `0003_collection_event`. Both numbers
were wrong.

**The failure.** `test_audit_run_foreign_keys_are_all_not_null` expected eight
identifier columns — `audit_id` plus seven foreign keys. Option A has six, so
seven columns. This is the PostgreSQL mirror of the unit test I corrected with
C-59, and I missed the mirror. It now asserts the exact **set** of seven names
as well as the count, so a rename is reported by name rather than as an
off-by-one.

**The seven skips, which should have been zero.** The C-53 gate asked whether
`"0002_pattern_ops"` was in the set read from `alembic_version`. That table
holds **one** value: the current revision. At `0003_collection_event` the
membership test failed, so seven tests that should have run skipped on a fully
migrated database — quietly reporting less coverage than existed.

Equality with the current revision answers "is the database exactly here". The
gate needs "has this revision been applied", which is ancestry. The fixture now
derives the applied set from `ScriptDirectory.iterate_revisions`.

**Third time for one mistake.** C-56 hard-coded a revision in a test, C-60 in
the verification script, C-61 compared against the current revision instead of
the ancestry. Each asserts a fixed point in a chain that grows. Two tests now
hold the line: one checks the gate opens at every revision from
`0002_pattern_ops` onward and stays closed before it — at every point on the
chain, not just today's head — and one asserts the integration gate still
consults the graph.

**The failure hid the skips.** The script aborts on a failing suite before
reaching its no-skips-at-head assertion, which is exactly what would have
caught them. The assertion was right; it never ran. Worth remembering when
reading a green-looking partial run.

### Verified

**482 passed, 56 skipped**; ruff clean. Next disposable database:
`privacy_auditor_m3b_20261105c_test`. `privacy_auditor_m3b_20261105b_test` is
preserved and protected — nine guarded names.

Expected on the next run: step 9 **56 passed, 0 skipped**; step 10b green with
skips.

---

## 2026-11-05 — C-62: head verified; the baseline stage found the last gap

**Head passed completely.** 56 passed, 0 skipped at `0003_collection_event`,
with the operator classes, the collation `en_US.utf8`, the upgrade and the
downgrade all confirmed on PostgreSQL 16. The C-61 fixes worked: the seven
tests that had skipped now run.

The baseline stage then reported **3 failed, 39 passed, 14 skipped**, and the
three failures were correct observations reported as defects:

| Test | At `0001_baseline` |
|---|---|
| `test_timestamps_carry_a_time_zone` | names `collected_at`; it is `retrieved_at` before 0003 |
| `test_every_declared_check_constraint_exists` | expects the models' 32 CHECKs; the baseline has 28 |
| `test_audit_run_foreign_keys_are_all_not_null` | expects six FKs; the baseline has seven |

Each compares the **live database** with the **current models**, and those
agree only at head. At an earlier revision they legitimately differ, so
failing there reports a correct database as broken.

`schema_at_head` now skips those five tests unless the applied revision is the
graph's head. Tests that assert something true of every revision — the
baseline functional indexes, JSONB and BIGINT types, the constraint
*enforcement* tests — carry no guard and keep running everywhere.

### Fourth time, so it is closed statically

C-56 hard-coded a revision in a test. C-60 hard-coded one in the script. C-61
compared against the current revision instead of the ancestry. C-62 compared
against the models without requiring head. One mistake in four costumes: an
assertion that assumes a migration state it never checked.

Three tests now parse the integration file with `ast` and fail if a test reads
`Base.metadata`, or names a column 0003 introduced, without taking
`schema_at_head`. The second check exists because
`test_timestamps_carry_a_time_zone` names `collected_at` without touching
`Base.metadata` — the first check alone would have missed it, which is exactly
how it reached the Mac.

### Verified

**482 passed, 56 skipped**; the new guards add 3 tests to the unit suite; ruff
clean; `bash -n` clean.

Next disposable database: `privacy_auditor_m3b_20261105d_test`. The `c`
database is preserved and protected — it was left at `0001_baseline` when the
run aborted before step 10c, which is another reason not to reuse it. Ten
guarded names.

Expected next run: step 9 **56 passed, 0 skipped**; step 10b green with skips
and **no failures**; step 10c head and schema restored.

---

## 2026-11-06 — C-63: the whole chain verified on PostgreSQL 16

Every stage passed. `privacy_auditor_m3b_20261105d_test`, log
`migration_verification_20261106_000146.log`.

- Upgrade `0001_baseline -> 0002_pattern_ops -> 0003_collection_event`
- Operator classes: both `_pattern` indexes `text_pattern_ops`, both originals
  `text_ops`; collation `en_US.utf8`
- **56 passed, 0 skipped** at head
- Downgrade: both pattern indexes removed, both baseline indexes retained
- **37 passed, 19 skipped, 0 failed** at the baseline — the guards fired
  instead of the three failures the previous run produced
- Re-upgrade restored the head revision, the operator classes **and** the
  collection-event columns

### The predicted plans were observed, not assumed

C-53's note predicted an `Index Cond` using the pattern operators and a
`BitmapOr` for the combined query. PostgreSQL produced exactly that:

```
Bitmap Heap Scan
  BitmapOr
    Bitmap Index Scan on ix_application_lower_name_pattern
      Index Cond: lower(app_name) ~>=~ 'wha' AND lower(app_name) ~<~ 'whb'
    Bitmap Index Scan on ix_application_lower_package_pattern
```

The `Sort` above the bitmap scan was predicted too — a bitmap scan does not
preserve order — and on at most 20 rows it is free. `enable_seqscan` was off,
so this is eligibility; at 300 to 500 rows a sequential scan remains the
correct plan and no performance improvement is claimed.

### Closed

**C-53** and **C-59** are both **Tested and verified**. The ALG-11 index
correction and the D-1 Option A collection-event schema are confirmed on the
database the system will run on, including a full down-and-up round trip.

### The pattern across six defects

C-56, C-57, C-58, C-60, C-61, C-62 — **every one in verification code, none in
the schema changes.** Both migrations were correct on first application. Five
of the six were the same mistake wearing different clothes: an assertion that
assumed a migration state it had not checked. That class is now closed
statically by three `ast`-based tests.

Worth carrying into M3B Part 2: the risk in this project is not the change,
it is the code that claims to check the change.

---

## 2026-11-06 — M3B Part 2: F-02, F-04, F-05, F-07 and the corpus import

Built on the Option A schema verified in C-63. 67 new unit tests; full suite
**528 passed, 56 skipped**; ruff clean.

| File | What |
|---|---|
| `backend/app/db/repositories/snapshot_repo.py` | New. F-04, F-05, F-07 |
| `backend/app/services/audit_service.py` | New. F-02 |
| `backend/app/db/repositories/application_repo.py` | `upsert_from_record` |
| `scripts/import_corpus.py` | New. Filesystem corpus → PostgreSQL |
| `tests/unit/test_snapshot_repository.py` | New, 28 tests |
| `tests/unit/test_audit_service.py` | New, 15 tests |

### Three distinctions the code exists to keep

**Absent category against declared-not-collected.** `_write_declared_practices`
writes a row only for entries the declaration actually contains. Writing a row
per known category with `is_collected = false` would turn "not mentioned" into
"declared not collected" — a different disclosure and a different ALG-8
verdict.

**Unknown against declared-no-collection.** `declares_no_data_collected` is
set to `None` when the Data Safety section was never read. Returning `False`
there would assert the application was checked and makes no such statement.
Three tests cover the three states.

**Failure against absence.** `derive_status` distinguishes
`declaration_absent` — the listing was reached and carries no Data Safety
section, a fact about the application — from `fetch_failed` and
`parse_failed`, which are facts about one moment. The remedies differ too: a
parse failure means the adapter needs updating.

### F-02 refuses first

Creating an `audit_run` row commits the system to producing a report. A report
built from one source would compare something against nothing, and ALG-8 would
have to call that either agreement or absence — both wrong. So the
preconditions are checked **before** the row exists, and a partial collection
event is refused with the reason rather than queued and failed later. Seven
distinct refusal reasons, each with its own remedy; a test asserts a refusal
creates no row.

Thresholds are pinned onto the run and carry `"provisional": true`, because
they have not been tuned on a gold set.

### F-05 re-verifies on every load

The hash is checked each time the document is read, not only at collection. A
file that has changed since collection raises rather than returning text,
because evidence quoted from it would not be the text that was audited. A
missing file raises too — the row claims a document and the filesystem
disagrees, which is a corpus fault, not a disclosure fact. "This event has no
policy" is different and returns `None`.

### Import is additive and honest

`upsert_from_record` refreshes rather than replaces: a later record missing a
field does not blank it, because a collector who could not read the developer
name has not discovered the application has none. A new collection event
supersedes the previous active one instead of overwriting it, so history
survives for F-30. Partial records import **with the status that says so**
rather than being skipped — a corpus of only the records that worked would
misrepresent itself. One record per transaction, so 299 good imports are not
lost to one bad record.

Run against the real corpus it reports honestly: *"No corpus at
data/corpus/apps. Nothing to import."* **Zero applications have been
collected.**

### What is not done

**F-06 live-retrieval wiring** — the gateway exists and is tested offline, but
nothing yet writes a live retrieval through it into a snapshot.

**No PostgreSQL integration tests for part 2.** Everything here is verified on
SQLite with the same metadata. The repositories and the service need the same
treatment the schema got in C-63, and that needs the Mac.

`SecurityPractices` still has no column. `load_declaration` rebuilds a
declaration with the default all-unknown instance rather than inventing four
`False` values the database never stored.

---

## 2026-11-06 — M3B Part 2 completed: F-06 wired, PostgreSQL tests written

**546 passed, 72 skipped**; ruff clean. New: `services/acquisition_service.py`
(F-06), `tests/unit/test_live_acquisition.py` (18),
`tests/integration/test_m3b_persistence_postgresql.py` (16).

### F-06, and the thing it refuses to invent

Live retrieval goes through the existing gateway, so the rate limiter
(NFR-15), the cache and the failure classification apply unchanged. This
module adds no transport — and **no scraper**.

The project has no parser for Google's Data Safety markup. A fetched page with
no parser is therefore recorded as **`parse_failed`** — reached and not
understood — which is deliberately not the same as the application declaring
nothing. A stub parser returning an empty declaration would have manufactured
a disclosure, so the parser is an injected protocol with no implementation
here. The honest consequence: a live collection today produces a partial
event, and the tests assert exactly that.

Offline-first is enforced rather than assumed. With no adapter, `collect`
returns `LiveRetrievalUnavailable` and **persists nothing**; a test asserts
the database stays empty. A missing policy URL is recorded with its reason
rather than guessed, because a guessed URL could attribute another
application's document to this one.

A test asserts only two URLs are requested per application — no crawling —
and another asserts the rate limiter is applied to both requests, so the
limiter cannot be bypassed by routing through this service.

### PostgreSQL integration tests

16, covering F-02, F-04, F-05, F-06, F-07: persistence, the three states of
`declares_no_data_collected` through a real boolean column, JSONB threshold
round-trip, duplicate handling, supersession, hash re-verification, partial
events, and two that assert **PostgreSQL itself** rejects a status outside the
vocabulary and a `complete` status without both URLs.

They skip unless `0003_collection_event` is in the applied ancestry — the C-61
lesson applied from the start rather than after a failed run.

### Not verified

**The 16 integration tests have not been executed.** They skip here; a skip is
not a pass. One command on the Mac runs them.

Still true, and stated in the M3B plan's completion report: zero applications
collected, live retrieval never reached Google, no Data Safety parser,
`SecurityPractices` has no column, and no end-to-end audit has run.

---

## 2026-11-06 — C-64: the first PostgreSQL run of M3B found a real bug

71 passed, 1 failed. **This time the failure was the code, not the test.**

`test_a_live_stored_document_verifies_when_loaded_back` stored a policy via
F-06 and asked F-05 to load it back. It got `None`.

`SNAPSHOT_HAS_POLICY` listed only `complete` and `policy_only`. But
`declaration_absent` and `parse_failed` describe what happened to the
**declaration** — `derive_status` returns either of them only when a policy
document *is* present. `load_policy_document` gated on that set, so for those
two statuses it refused to read a document the row was holding, and refused
**silently**: it returned `None`, which reads as "this event has no policy".

A successful retrieval presented as an absence. That is the precise failure
mode this milestone exists to prevent, turned on itself.

### Fixed in two parts, the second mattering more

1. The set now includes both statuses.
2. The loaders stopped asking a derived set. `load_policy_document` keys on
   `policy_doc_path` — the row holding a path is the authoritative fact that a
   document exists, and a CHECK already ties path to hash.
   `load_declaration` keys on `declares_no_data_collected` being NULL, which
   is exactly "the section was never read". Both questions are now answered by
   the column that records the fact, not by a summary one step away from it.

### Why the SQLite suite missed it

It was green with the bug present. Every F-05 test used a `complete` or
`policy_only` event; nothing exercised a policy stored alongside a failed
declaration. The integration test that caught it was the first to combine
F-06's realistic output — no parser, so `declaration_absent` — with an F-05
load.

Three guards added: two parametrised tests for the statuses directly, and a
structural one that enumerates every status `derive_status` can return for a
record holding a policy and asserts all of them are in `SNAPSHOT_HAS_POLICY`.
**Verified by reintroducing the bug** — the guards fail, which is the only
evidence worth having that a regression test works.

### Verified

**551 passed, 72 skipped**; ruff clean. Next disposable database:
`privacy_auditor_m3b_20261106b_test`; the failed run's database is preserved
and protected — twelve guarded names.
