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
| M1 Repository and environment | all | **Complete** | Verified on two machines; Python 3.12 on the team Mac. Docker not yet installed |
| M2 Database and schema | R5 | **Implemented and verified** | 16 tables. 189 tests on SQLite, **29 on PostgreSQL 16, all passing**. Class E omissions restored; **7 class D deviations against Phase 3 §10.2 still await a ruling** |
| M3A Acquisition layer and corpus format | R2 | **Complete** | 70 tests. Offline-first; **never run live**, no application collected |
| M3B Acquisition persistence | R2, R5 | **Blocked** | Needs the D-1 decision before any snapshot can be written |
| M4 Text processing | R3 | **Complete** | F-08, F-09, F-10; 78 tests. Offsets index the cleaned text and are slice-verified |
| M5 Baseline ML | R3 | **Ready, not started** | OPP-115 in place and verified: 115 policies, 23,194 practices, 77,906 usable spans |
| M6 Improved ML | R1, R3 | **Blocked** | Option A decided (D-01). Needs 300-500 labelled pairs and the gold set; neither exists |
| M7 Verdict and evidence engine | R1 | **Core complete at unit-test level** | F-14, F-16, F-17, F-20, F-21, F-22 complete. **F-19 partial** — verdict confidence missing (audit E-5). **F-15 mechanism only** — no mapping rules authored. F-18 excluded, stays in M6 |
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

## Open items requiring the team

0. **Review `docs/PHASE4_SCHEMA_BASELINE_AUDIT.md`** and rule on findings D-1
   to D-10, the class E restorations, and DOC-1 and DOC-2 which are defects in
   the approved Phase 3 report. This blocks further implementation.

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
