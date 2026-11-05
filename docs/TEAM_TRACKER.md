# Team Tracker

Working rules: `docs/PHASE4_DEVELOPMENT_PROTOCOL.md` — standing and mandatory
from 2026-11-05.

Member names are placeholders until the team provides them. Replace the
bracketed labels; the role identifiers R1 to R6 come from Phase 3 §13.2 and do
not change.

| Role | Member | Area | Functions owned |
|---|---|---|---|
| R1 | _[Member 1]_ | Design coordination and cross-source alignment | F-15, F-16, F-17, F-18, taxonomy mapping artefact |
| R2 | _[Member 2]_ | Data engineering and corpus collection | F-01 to F-07, Play Store corpus |
| R3 | _[Member 3]_ | NLP and classification | F-08 to F-14 |
| R4 | _[Member 4]_ | Backend and integration | F-23, F-32, F-33, F-34, endpoints E1 to E11 |
| R5 | _[Member 5]_ | Database and persistence | 16 tables, migrations, F-28, F-29, F-30 |
| R6 | _[Member 6]_ | Frontend and evaluation | F-24 to F-27, F-31, screens S1 to S7 |

Shared by all six: gold-set annotation, weekly integration testing, and
documenting their own component.

Faculty Guide: _[to be filled in]_

---

## Milestone status

Statuses follow `docs/PHASE4_DEVELOPMENT_PROTOCOL.md` §1.6 and mean exactly
what it says they mean. **Implemented** is not **Tested and verified**:
verification requires every applicable check to have actually been executed,
including the PostgreSQL and disposable-database checks, which only the team
can run (§2.2).

| Milestone | Owner | Status | Notes |
|---|---|---|---|
| M1 Repository and environment | all | **Tested and verified** | Verified on two machines; Python 3.12 on the team Mac. Docker 29.9.2 installed 2026-11-05; `postgres:16-alpine` healthy |
| M2 Database and schema | R5 | **Tested and verified** | 16 tables. **29 tests on PostgreSQL 16, all passing**, against a frozen `0001_baseline` (equivalence-tested, commits `2c5fee7`, `1c83153`). Class E omissions restored. D-2, D-6, D-7 withdrawn on re-examination; **D-1 and D-3 to D-5, D-8 to D-10 still await a ruling.** `privacy_auditor` is still empty and never migrated |
| M3A Acquisition layer and corpus format | R2 | **Tested and verified** (offline paths only) | 70 tests. Offline-first; **never run live**, no application collected |
| M3B Acquisition persistence | R2, R5 | part 1 **Tested and verified**; part 2 **Implemented** | Part 1: F-01, F-03 (`fc1a111`), PostgreSQL-verified. Part 2: D-1 Option A schema `0003` (PostgreSQL-verified, C-63), **F-02, F-04, F-05, F-07** and the corpus import, 67 unit tests. **F-06 live-retrieval wiring remains**; part 2 has no PostgreSQL integration tests yet |
| M4 Text processing | R3 | **Tested and verified** (on fixtures; never run on a real policy) | F-08, F-09, F-10; 78 tests. Offsets index the cleaned text and are slice-verified |
| M5 Baseline ML | R3 | **Tested and verified** | F-11 baseline, ALG-2. Held-out test macro-F1 0.7489, micro-F1 0.7690. Two categories unevaluable |
| M6 Improved ML | R1, R3 | **Blocked** | Option A decided (D-01). Needs 300-500 labelled pairs and the gold set; neither exists |
| M7 Verdict and evidence engine | R1 | **Implemented**, not verified end to end | ALG-8 precedence implemented with structural abstention propagation. F-14, F-16, F-17, F-19, F-20, F-21, F-22 complete; E-5 verdict confidence restored via `_deciding_confidence`. **F-15 mechanism only — no mapping rules authored.** F-18 excluded, stays in M6. **Never run on a real application:** every test uses controlled fixtures |
| M8 Backend integration and persistence | R4 | **Not started** | Verdicts are not persisted; the engine writes nothing |
| M9 Frontend | R6 | **Not started** | |
| M10 Integration and deployment | all | **Not started** | |

### Corrections in flight

| Item | Status | What is outstanding |
|---|---|---|
| **C-53** pattern-class search indexes, revision `0002_pattern_ops` | **Tested and verified** | PostgreSQL 16, 2026-11-05, `privacy_auditor_c53_20261105d_test`. Operator classes, collation `en_US.utf8`, 56 passed applied / 49 passed + 7 skipped after downgrade, baseline indexes retained, EXPLAIN eligibility asserted. **Closed** |
| **C-56** a test asserted one migration revision | **Fixed and verified** | Four ancestry-based tests from Alembic's revision graph; both migration states exercised on PostgreSQL |
| **C-57** `dict(CursorResult)` TypeError | **Fixed and verified** | `.all()` then `dict(rows)`; passed in both states |
| **C-63** full chain verified on PostgreSQL 16 | **Tested and verified** | 2026-11-06. Upgrade, operator classes, collation, 56 passed at head with no skips, downgrade, 37 passed / 19 skipped / 0 failed at baseline, re-upgrade, and EXPLAIN showing `BitmapOr` over both pattern indexes. **C-53 and C-59 closed** |
| **C-62** model-comparison tests failed at the baseline | **Fixed** | `schema_at_head` guard on the five tests that compare the live schema with the models. Three `ast`-based tests now require the guard, closing the pattern statically |
| **C-61** FK count mirror and an equality-based revision gate | **Fixed** | `audit_run` identifier columns 8 → 7 with the exact set asserted; the C-53 gate now uses ancestry, not equality with the current revision. Two tests lock the pattern down |
| **C-60** verification script hard-coded the head revision | **Fixed** | Head and base derived from the Alembic graph; four other version-bound assumptions corrected. Three tests stop it recurring at revision 0004 |
| **C-59** D-1 Option A: collection-event snapshot restored | **Tested and verified** | Revision `0003_collection_event`. 6 FKs on `audit_run` (DOC-1 resolved), 7 snapshot CHECKs, `status` (E-2) and three-state `declares_no_data_collected`. SQLite and **PostgreSQL** up/down/re-up verified 2026-11-06 (C-63) |
| **C-58** diagnostic indexed a grown result tuple | **Fixed** | Named unpacking; arity checked against the script's own SQL. Did not affect C-53's verification — the eligibility assertions are in the test suite |

### Established facts, for reference

| Fact | Status |
|---|---|
| OPP-115 downloaded and verified | 115 policies, 23,194 annotated practices, 77,906 usable spans; checksum manifest committed |
| F-18 alignment approach | **Option A**, approved 2026-11-04 with five binding safeguards (D-01) |
| Development environment | Python 3.12 required; 3.14 breaks the install (C-18) |
| Data Safety categories | 14, taken from Google's developer documentation on 2026-11-04 |
| End-to-end audit | **Never run.** No stage upstream of F-14 exists |
| Thresholds | All three provisional at 0.50, uncalibrated |

### What M1 to M7 actually amount to

Complete at **unit-test level with controlled fixtures** is not the same as
working. Recorded plainly so the viva answer is the same as the tracker:

| | Reality |
|---|---|
| Android applications collected | **0** of 300–500, 0 of the ~20 pilot |
| Live retrievals performed | **0** |
| Database rows in `privacy_auditor` | **0.** The database has never been migrated |
| End-to-end audit run | **Never.** No stage upstream of F-14 is wired to one downstream of it |
| Functions with no database path yet | F-02, F-04 to F-07 (M3B part 2), F-28 to F-34 (M8). F-01 and F-03 now have one |
| Learning tasks trained | 1 of 3. F-11 baseline only; F-12 and F-18 have no training data |
| Gold set | Does not exist |
| Taxonomy mapping rules (F-15) | **None authored.** The lookup mechanism works; it has nothing to look up |
| Thresholds | All provisional at 0.50, uncalibrated |

Tests: **461 passed, 56 skipped** on SQLite, where the 56 skips are the
PostgreSQL-only tests. **43 passed against PostgreSQL 16** on
`privacy_auditor_frozen_20261105_test`, 2026-11-05. On disposable databases upgraded to
`0002_pattern_ops`, two runs each produced one failure, and **both were
defective tests rather than the schema**: C-56 (a hard-coded revision
assertion) and C-57 (`dict(CursorResult)`). The second run reached **55 of
56**. **Verified:** migration `0001` → `0002`, the recorded revision, both
pattern indexes at `text_pattern_ops`, both originals at `text_ops`, and the
collation `en_US.utf8`. **Not yet executed:** the downgrade, the re-upgrade,
the re-run proving the skip gate fires, and the `EXPLAIN` diagnostic.

The schema now has **two migrations**: the frozen `0001_baseline` and the
additive `0002_pattern_ops`. `privacy_auditor` is still at neither.

## Open items requiring the team

0. ~~**Rule on D-1**~~ **RULED 2026-11-05: Option A** — the approved Phase 3
   §10.2 single collection-event snapshot. Option B is not implemented. M3B
   Part 2 restores it in revision `0003`; DOC-1 resolves with it (§10.3's
   "seven" foreign keys becomes six). Superseded text:

   **Rule on D-1** — one `disclosure_snapshot` per collection event (Phase 3
   §10.2 as approved) or one per source (as implemented). Both options are
   costed in `docs/M3B_IMPLEMENTATION_PLAN.md` §5 and §6. **This is the single
   item blocking M3B**, and Option B additionally needs faculty approval and a
   `REQUIREMENT_CHANGE_LOG.md` entry. D-3 to D-5 and D-8 to D-10 remain open
   but block nothing; DOC-1 is a defect in the approved Phase 3 report and is
   resolved by whichever option D-1 selects. DOC-2 was withdrawn.

1. Decide the F-18 alignment training-data approach — master plan §7.
2. Confirm encoder checkpoints for the three learning tasks.
3. Schedule the 300 to 500 app Play Store collection, rate-limited per NFR-15.
4. ~~Install Docker Desktop~~ **Done 2026-11-05.** Docker 29.9.2;
   `postgres:16-alpine` healthy; `privacy_auditor_test` created and the schema
   verified against it.
8. Build every virtual environment on Python 3.12. Python 3.14 breaks the
   install; see C-18 in the consistency log.
5. Confirm free-tier GPU access for the three training runs.
6. Check PolicyIE and PI-Extract licence terms.
7. Provide member names to replace the placeholders above.
9. Decide where `declares_no_data_collected` (Google's app-level "does not
   collect or share any user data" statement) and `SecurityPractices`
   (encryption in transit, deletion availability, independent review) are
   stored. M3A parses both; **no column in either D-1 option holds them.**
   Independent of D-1 and should not be bundled with it.
10. Approve the 20-application pilot. It does **not** depend on D-1 — the
    filesystem corpus format is already frozen and tested.

---

## Operational corpus collection — not started

This is the **Android application corpus**, not OPP-115.

| Item | Target | Actual |
|---|---|---|
| Applications collected | 300–500 | **0** |
| Pilot applications | ~20 | **0** |
| Gold-set applications annotated | ~100 | **0** |
| Live retrievals performed | — | **0** |

The format, the validation tool and the import procedure exist and are
tested. The collecting has not begun. One invented fixture record demonstrates
the format; it is not an application.

Procedure: `docs/M3_ACQUISITION_REPORT.md` section 10.
