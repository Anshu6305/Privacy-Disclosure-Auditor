# Project instructions

**Cross-Source Privacy Disclosure Consistency Auditor for Android
Applications** — B.Tech major project, KIIT, six-member team, Phase 4
(implementation).

## Read first

`docs/PHASE4_DEVELOPMENT_PROTOCOL.md` is a **standing, mandatory protocol**
for every implementation step, bug fix, database change, API change and
integration step. Read it before writing code. It governs testing, reporting
and approval gates.

The non-negotiables from it:

- **Implement only what has been explicitly approved.** On completion: test,
  document, commit, report, then **stop and wait for review.** Never continue
  to the next milestone automatically.
- **Skipped is not passed.** Report "new passed", "existing passed", "failed",
  "skipped" and "not executed because of environment limitations" separately.
- **Never remove an assertion or weaken a test to make the suite green.**
- Use three statuses exactly: **Implemented** · **Tested and verified** ·
  **Pending or blocked**. Implementation is not verification.
- **These databases are protected** and must not be dropped, reset, truncated
  or migrated without explicit authorisation: `privacy_auditor`,
  `privacy_auditor_test`, `privacy_auditor_frozen_20261105_test`.
- **Preserve the frozen baseline migration** `0001_baseline_schema.py`.
  Schema changes are additive revisions, approved first.
- **Preserve the M5 baseline** — model, split, seed and held-out results. It
  is the reference experiment and is never retrained to improve a number.
- **Never fabricate** predictions, metrics, collected application records or
  claims of live retrieval.
- A change to an approved requirement, database structure or architecture
  needs an explanation and approval **before** it is made.

## Environment

- Python **3.12** for every virtual environment. 3.14 breaks the install.
- `pytest tests -p no:warnings` · `ruff check .`
- **PostgreSQL runs in Docker Desktop on the team Mac and is not reachable
  from an agent session.** PostgreSQL integration tests, disposable-database
  upgrade/downgrade checks and catalogue checks must be run by the team and
  their output reported. Alembic offline mode (`alembic upgrade a:b --sql`)
  emits real DDL with no server and can be run in-session.

## Orientation

| Document | Holds |
|---|---|
| `docs/PHASE4_MASTER_PLAN.md` | F-01 to F-34 module mapping, milestone order |
| `docs/TEAM_TRACKER.md` | actual milestone status; what does not exist yet |
| `docs/PHASE4_CONSISTENCY_LOG.md` | C-01 onwards: every deviation from approved design |
| `docs/IMPLEMENTATION_TRACEABILITY.md` | requirement and function traceability |
| `docs/DEV_LOG.md` | chronological record, including defects found |
| `docs/PHASE4_DECISION_TABLE.md` | open decisions, D-1 onwards |

Approved Phase 1, 2 and 3 identifiers (FR, NFR, GI, F, T, ALG, E) are fixed
and must not be renamed or renumbered.
