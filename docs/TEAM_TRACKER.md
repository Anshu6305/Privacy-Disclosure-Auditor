# Team Tracker

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

| Milestone | Owner | Status | Notes |
|---|---|---|---|
| M1 Repository and environment | all | **Complete** | Verified on two machines; Python 3.12 on the team Mac. Docker 29.9.2 installed 2026-11-05; `postgres:16-alpine` healthy |
| M2 Database and schema | R5 | **Implemented and verified** | 16 tables. **29 tests on PostgreSQL 16, all passing**, against a frozen `0001_baseline` (equivalence-tested, commits `2c5fee7`, `1c83153`). Class E omissions restored. D-2, D-6, D-7 withdrawn on re-examination; **D-1 and D-3 to D-5, D-8 to D-10 still await a ruling.** `privacy_auditor` is still empty and never migrated |
| M3A Acquisition layer and corpus format | R2 | **Complete** | 70 tests. Offline-first; **never run live**, no application collected |
| M3B Acquisition persistence | R2, R5 | **Planned, not implemented** | `docs/M3B_IMPLEMENTATION_PLAN.md` written 2026-11-05. Options A and B for D-1 are costed; **4 of 7 functions (F-02, F-04 to F-07) cannot be built until D-1 is ruled.** F-01 and F-03 do not depend on it |
| M4 Text processing | R3 | **Complete** | F-08, F-09, F-10; 78 tests. Offsets index the cleaned text and are slice-verified |
| M5 Baseline ML | R3 | **Complete** | F-11 baseline, ALG-2. Held-out test macro-F1 0.7489, micro-F1 0.7690. Two categories unevaluable |
| M6 Improved ML | R1, R3 | **Blocked** | Option A decided (D-01). Needs 300-500 labelled pairs and the gold set; neither exists |
| M7 Verdict and evidence engine | R1 | **Core complete at unit-test level** | ALG-8 precedence implemented with structural abstention propagation. F-14, F-16, F-17, F-19, F-20, F-21, F-22 complete; E-5 verdict confidence restored via `_deciding_confidence`. **F-15 mechanism only — no mapping rules authored.** F-18 excluded, stays in M6. **Never run on a real application:** every test uses controlled fixtures |
| M8 Backend integration and persistence | R4 | **Not started** | Verdicts are not persisted; the engine writes nothing |
| M9 Frontend | R6 | **Not started** | |
| M10 Integration and deployment | all | **Not started** | |

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
| Functions with no database path yet | F-01 to F-07 (M3B), F-28 to F-34 (M8) |
| Learning tasks trained | 1 of 3. F-11 baseline only; F-12 and F-18 have no training data |
| Gold set | Does not exist |
| Taxonomy mapping rules (F-15) | **None authored.** The lookup mechanism works; it has nothing to look up |
| Thresholds | All provisional at 0.50, uncalibrated |

Tests: **402 passed, 29 skipped** on SQLite; 29 passed on PostgreSQL 16. The
29 skips are the PostgreSQL-only tests, skipped when no server is reachable.

## Open items requiring the team

0. **Rule on D-1** — one `disclosure_snapshot` per collection event (Phase 3
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
