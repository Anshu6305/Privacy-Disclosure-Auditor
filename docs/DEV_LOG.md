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
