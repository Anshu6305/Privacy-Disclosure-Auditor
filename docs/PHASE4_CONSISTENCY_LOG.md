# Phase 4 Consistency Log

Every point at which an implementation decision was checked against the
approved Phase 1 to 3 documents. Entries record agreement as well as
correction, because the agreements are what show the design was followed
rather than re-invented.

Nothing here changes an approved requirement. Changes to requirements go in
`REQUIREMENT_CHANGE_LOG.md` and need faculty approval.

---

## Milestone 1 — 2026-11-04

### C-01 Container count held at three

**Approved design:** Phase 3 deployment — three containers on one host:
web/API, worker, PostgreSQL.

**What happened:** The first draft of `docker-compose.yml` had four services,
adding an nginx container to serve the frontend. That contradicts the approved
deployment.

**Resolution:** Corrected before commit. The SPA is built in a Node stage
inside `backend/Dockerfile` and served by FastAPI from the same process, so the
web and API functions share one container exactly as the design states. The
reasoning is recorded as a comment at the top of the Dockerfile so it is not
undone by someone who sees only the file.

**Status:** consistent with the approved design.

### C-02 `analysis/` kept free of web and database dependencies

**Approved design:** Phase 3 §6.1 — the analysis pipeline is independent of the
delivery mechanism.

**What happened:** `analysis/` was placed at the repository root rather than
under `backend/`, and imports nothing from `app`.

**Status:** consistent. Enforced by a test in Milestone 4, once the first
analysis module exists.

### C-03 Confidence thresholds treated as configuration

**Approved design:** ALG-4; Phase 3 records thresholds as tunable and stored
per audit run in `audit_run.threshold_config`.

**What happened:** Thresholds are environment settings with placeholder values
of 0.50, labelled in `.env.example` and in `config.py` as untuned placeholders
rather than measured results.

**Status:** consistent. The per-run persistence arrives with the schema in
Milestone 2.

### C-04 Scope statement held in one place

**Approved design:** F-26; the system states its limits wherever it reports.

**What happened:** The wording lives in `backend/app/main.py` and is served by
`/api/meta/scope`. The frontend fetches it rather than carrying its own copy,
and a test asserts the statement still disclaims legality, intent and malice,
so weakening it fails the suite.

**Status:** consistent.

### C-05 Database health reports the real outcome

**Approved design:** Phase 4 constraint — no simulated database operations.

**What happened:** `/api/health/database` executes `SELECT 1` and reports
`unconfigured`, `unavailable` or `ok` based on what happened. A test asserts it
does not report healthy without credentials.

**Status:** consistent.

### C-06 OPP-115 not redistributed

**Approved design:** Phase 1 licence finding — research, teaching and
scholarship use, in the spirit of CC BY-NC. Phase 4 constraint — never commit
datasets that cannot legally be redistributed.

**What happened:** `.gitignore` excludes all of `data/` except its README. The
repository carries a checksum manifest (`ml/data/opp115_manifest.json`) instead
of the corpus, which gives reproducibility without redistribution. The citation
and licence note are embedded in the manifest.

**Status:** consistent.

### C-07 Corpus manual contradicted by the released files

**Approved design:** not affected. This is a dataset documentation defect, not a
design question, but it would have produced wrong provenance records if
followed.

**What happened:** `documentation/manual.txt` documents annotation CSV column 8
as the policy URL and column 9 as the date. In all 23,194 rows of the released
corpus they are the other way round: column 8 holds the date, column 9 the URL.
Measured, not assumed — the check counted every row.

**Resolution:** The loader identifies the URL by its scheme prefix rather than
by position, and the discrepancy is documented in `ml/data/opp115_schema.py`.

**Status:** handled.

### C-08 Span availability measured, not estimated

**Approved design:** Learning task 2 (F-12) depends on span supervision from
OPP-115 and PolicyIE.

**What happened:** A first pass counted 69,020 of 146,926 attribute entries as
lacking a usable span and risked the conclusion that nearly half the corpus was
damaged. On inspection, 68,758 of those carry the values `Unspecified`,
`not-selected` or `Does`, which are span-free by design. Genuine errata number
262, or 0.18%.

**Measured result:** 77,906 attribute entries (53.0%) carry usable spans with
real character offsets.

**Status:** no design impact. The figure is recorded because the ML plan in
Milestone 6 depends on it, and because the first reading of it was wrong.
