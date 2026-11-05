# Phase 4 development and testing protocol

Adopted: 2026-11-05. **Standing and mandatory** for every remaining
implementation milestone, sub-milestone, coding task, bug fix, database change,
API change and integration step.

This document is the authority. Section 1 records the protocol as approved;
section 2 records how it is carried out in this repository, including one
environment limitation that changes who runs certain checks.

---

## 1. The protocol as approved

### 1.1 Test every implementation step

Do not wait until the end of a milestone. After each logically complete
component:

1. Run its focused unit tests.
2. Run relevant edge-case and failure-case tests.
3. Run affected integration tests.
4. Run the existing regression suite.
5. Run Ruff and the other configured code-quality checks.
6. Verify compatibility with the approved architecture and existing components.

**Fix failures before proceeding to the next step.**

### 1.2 Full regression testing after every milestone

Run the full available suite, and report these five categories **separately**:

- New tests passed
- Existing tests passed
- Failed tests
- Skipped tests
- **Tests not executed because of environment limitations**

**Never describe skipped tests as passed.** Never remove an existing assertion
or weaken a test to make the suite green.

### 1.3 Database safeguards

Whenever a model, migration, repository or query changes:

- Test with the SQLAlchemy and SQLite tests.
- Test against real PostgreSQL where applicable.
- Verify migration **upgrade and downgrade on a disposable database**.
- Verify schema constraints, indexes and foreign keys.
- Preserve the approved baseline migration.
- Never delete or reset existing project databases.
- **`privacy_auditor`, `privacy_auditor_test` and
  `privacy_auditor_frozen_20261105_test` are protected** unless an operation
  involving them is explicitly authorised.

### 1.4 ML safeguards

Whenever an ML component changes:

- Test preprocessing and label construction.
- Verify splits and prevent leakage.
- Record model configuration and versions.
- Run actual evaluation on the correct held-out data.
- Report per-class metrics and class imbalance.
- Distinguish training, validation and test results.
- **Never fabricate predictions, metrics or training results.**
- **Preserve the original M5 baseline as the comparison reference.**

### 1.5 Integration safeguards

Whenever components are connected:

- Test the actual interfaces between them.
- Test successful execution.
- Test missing and invalid inputs.
- Test failure propagation and **abstention propagation**.
- Verify evidence and provenance remain traceable.
- **Do not claim end-to-end functionality from isolated unit tests.**

### 1.6 Milestone reporting

Every completion report contains: scope completed · files created and modified ·
functions and requirements implemented · exact test commands executed · actual
results · failures and skips · regression results · code-quality results · known
limitations · updated traceability · Git commit identifier · completion
checklist.

Three distinct statuses, used exactly:

| Status | Meaning |
|---|---|
| **Implemented** | The code exists and the unit tests pass |
| **Tested and verified** | Every applicable check in §1.1 to §1.5 has actually been executed, including the PostgreSQL and disposable-database checks where they apply |
| **Pending or blocked** | Not done, or waiting on a decision or data |

**Implementation alone does not mean a feature is verified.**

### 1.7 Approval gates

Implement only the milestone or sub-milestone explicitly approved. On
completion: finish the applicable tests, update the documentation, commit,
present the results, **stop and wait for review.** Do not continue
automatically.

### 1.8 Project-wide consistency

Preserve the approved Phase 1 feasibility constraints; the Phase 2 FR, NFR and
GI identifiers; the Phase 3 F-function identifiers, tasks, algorithms, API and
database design; existing milestone traceability; and honest reporting of what
the six-member team actually completed.

A change to an approved requirement, database structure or architecture
requires an explanation and approval **before** it is made.

**A green suite is necessary but not sufficient.** The implementation must also
match the approved design and the intended behaviour.

---

## 2. How this is carried out here

### 2.1 The commands

| Step | Command |
|---|---|
| Focused unit tests | `pytest tests/unit/test_<component>.py -q` |
| Full regression | `pytest tests -p no:warnings` |
| Code quality | `ruff check .` |
| PostgreSQL integration | `TEST_DATABASE_URL=... pytest tests/integration -p no:warnings -v` |
| Migration DDL, no server | `cd backend && POSTGRES_PASSWORD=offline-dummy alembic upgrade <from>:<to> --sql` |
| Index diagnostics | `TEST_DATABASE_URL=... python scripts/explain_application_search.py` |

Every virtual environment is built on **Python 3.12**; 3.14 breaks the install
(C-18), and `conftest.py` fails early with the reason.

### 2.2 The environment limitation — who runs what

**PostgreSQL is not reachable from the development session.** It runs in Docker
Desktop on the team Mac, on that machine's own loopback interface. This is a
permanent property of the setup, not a transient fault.

The consequence for §1.3, and it is load-bearing:

| Check | Who can run it |
|---|---|
| Unit and SQLite tests, Ruff | the session |
| Migration DDL, via Alembic offline mode | the session — emits real SQL with no server |
| Migration upgrade/downgrade on SQLite | the session |
| **PostgreSQL integration tests** | **the team, on the Mac** |
| **Upgrade/downgrade on a disposable PostgreSQL database** | **the team, on the Mac** |
| **Catalogue checks: operator classes, collation, constraints** | **the team, on the Mac** |

So a database change reaches **Implemented** in the session and **Tested and
verified** only after the team runs the PostgreSQL half and reports the output.
Any milestone report written in the session must put those checks under
"not executed because of environment limitations" — never under skipped, and
never under passed.

Integration tests are written so this cannot be papered over: they `skip` when
`TEST_DATABASE_URL` is unset, `fail` if it names a database whose name does not
end in `_test`, and the C-53 tests skip unless `alembic_version` shows the
revision they need. A skip guard that fires is evidence the test cannot pass
vacuously.

### 2.3 Disposable databases

A disposable database is created per verification, with a unique name
(`privacy_auditor_<purpose>_<date>_test`), after a pre-check that refuses to
reuse an existing name. The exact steps are in
`docs/C53_RESOLUTION_NOTE.md` §10.3 and are the template for every future
migration.

**No test creates or drops a database.** No destructive command — `drop_all`,
`DROP TABLE`, `DROP DATABASE`, `TRUNCATE`, `docker compose down -v` — appears
anywhere in `tests/` or `scripts/`. Creation is a manual step the team takes
deliberately.

### 2.4 Where each safeguard already has teeth

Recorded so a future session does not have to rediscover it:

| Safeguard | Enforced by |
|---|---|
| Baseline migration preserved | `test_revision_does_not_build_from_metadata`, `test_revision_uses_explicit_operations` (21 index calls), `test_baseline_does_not_contain_the_c53_correction` |
| Models and migrations agree | `test_every_index_matches_the_models`, `test_unique_constraints_match_the_models`, `test_check_constraints_match_the_models` |
| Protected databases | the `_test` suffix guard in both integration files; no DDL or destructive verb in `tests/` |
| Abstention propagation | `AlignmentJudgement.abstained` is a **property**, not a field, so no caller can produce a confident judgement from an uncertain input |
| M5 baseline preserved | model binary, metrics and processed data are git-ignored; the split seed is fixed at 20261105; the test split has been used once |
| No fabricated metrics | rare-class results carry `"reliable": false`; Do Not Track's F1 of 0.857 on n=4 is reported as not a measurement |
| Honest team reporting | R1 to R6 remain placeholders; no contribution is attributed and no collection progress is claimed |

### 2.5 Standing limitations to restate in every report

1. **No Android application has been collected.** 0 of 300–500, 0 of the ~20
   pilot, 0 live retrievals.
2. **No end-to-end audit has ever run.** No stage upstream of F-14 is wired to
   one downstream of it.
3. **`privacy_auditor` is at no revision.** It has never been migrated.
4. **F-15 has no mapping rules authored.** The lookup mechanism works and has
   nothing to look up.
5. **All thresholds are provisional at 0.50**, uncalibrated.
6. **One of three learning tasks is trained.** F-12 and F-18 have no training
   data.
7. **The gold set does not exist.**

### 2.6 Open items under §1.8

Changes to approved design still awaiting a ruling: **D-1** (blocking M3B part
2), D-3 to D-5, D-8 to D-10, DOC-1, E-2 reconsideration, the `practice_type`
and `scope` vocabularies, and where `declares_no_data_collected` and
`SecurityPractices` are stored. **C-55** (prefix-only search) is open and
blocks nothing.
