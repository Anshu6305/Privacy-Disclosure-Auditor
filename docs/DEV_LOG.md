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
