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
| M1 Repository and environment | all | Complete | 17 tests passing; Docker not yet executed |
| M2 Database and backend foundation | R5 | Not started | |
| M3 Acquisition and offline corpus | R2 | Blocked | Needs Play Store collection on a team machine |
| M4 Text processing | R3 | Not started | |
| M5 Baseline ML | R3 | Ready | OPP-115 is in place and verified |
| M6 Improved ML | R1, R3 | Blocked | Alignment training-data decision pending |
| M7 Verdict and evidence engine | R1 | Not started | No external dependency; can run in parallel |
| M8 Backend integration | R4 | Not started | |
| M9 Frontend | R6 | Not started | |
| M10 Integration and deployment | all | Not started | |

## Open items requiring the team

1. Decide the F-18 alignment training-data approach — master plan §7.
2. Confirm encoder checkpoints for the three learning tasks.
3. Schedule the 300 to 500 app Play Store collection, rate-limited per NFR-15.
4. Install Docker Desktop on at least one machine and run
   `docker compose up --build`. PostgreSQL runs in a container and does not
   need a separate install.
8. Build every virtual environment on Python 3.12. Python 3.14 breaks the
   install; see C-18 in the consistency log.
5. Confirm free-tier GPU access for the three training runs.
6. Check PolicyIE and PI-Extract licence terms.
7. Provide member names to replace the placeholders above.
