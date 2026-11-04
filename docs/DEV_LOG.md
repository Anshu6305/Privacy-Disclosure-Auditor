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
