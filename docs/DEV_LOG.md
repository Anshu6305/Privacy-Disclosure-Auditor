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
