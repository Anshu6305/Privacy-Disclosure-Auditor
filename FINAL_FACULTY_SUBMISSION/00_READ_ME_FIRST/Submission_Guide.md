# Submission guide — read this first

**Cross-Source Privacy Disclosure Consistency Auditor for Android Applications**
B.Tech major project · Kalinga Institute of Industrial Technology · six-member team
Prepared 18 November 2026 · Repository commit `e96383f`, branch `master`

This is a **Phase 1–4 submission**. Phase 5 (academic validation and testing)
is a separate phase and has not begun; no Phase 5 report is included and none
is claimed.

---

## The system in three sentences

An Android app declares what data it collects in the Google Play Data Safety
section and describes the same thing in prose in its privacy policy; nothing
checks that the two agree. This system reads both, works out what the policy
says about each privacy-practice category using NLP and three machine-learning
components, maps both sources into one category set, and reports per category
whether they are consistent, inconsistent in one of three specific ways, or
whether it cannot tell. Every finding is anchored to the exact characters of
the policy that produced it, and when confidence is insufficient the system
abstains and records why instead of guessing.

It compares two public disclosures. It does not inspect the application binary,
does not observe runtime traffic, and makes no legal or compliance judgement.

## Where to start

| Read | For |
|---|---|
| `00_READ_ME_FIRST/Project_Continuity_Summary.md` | How Phase 1 became Phase 4, and where plan and delivery differ |
| `00_READ_ME_FIRST/Requirement_Traceability_Matrix.md` | Every FR and NFR with an honest status |
| `FINAL_PROJECT_REPORT.md` | The complete project report, 15 sections |
| `../FINAL_SUBMISSION_AUDIT.md` | Cleanup, consistency findings, faculty checklist, final verdict |

## Folder map

| Folder | Contents |
|---|---|
| `00_READ_ME_FIRST/` | This guide, the continuity summary, the traceability matrix, the runtime asset manifest and its SHA-256 list |
| `01_PHASE_1_FEASIBILITY/` | `Report_Phase-01.docx` — the approved feasibility study, unaltered |
| `02_PHASE_2_SRS/` | `Report_Phase-02.docx` — the approved IEEE-830 SRS, unaltered |
| `03_PHASE_3_SYSTEM_DESIGN/` | `Report_Phase-03.docx` unaltered, plus `Supporting_Diagrams/` (15 diagrams in `.dot`, `.mmd`, `.svg`, `.png`) and the original diagram archive |
| `04_PHASE_4_IMPLEMENTATION/` | 26 implementation documents. Start with `PHASE4_CLOSEOUT.md`; `PHASE4_CONSISTENCY_LOG.md` holds all 99 findings |
| `05_TESTING_AND_EVIDENCE/` | `Backend_Test_Results/`, `Frontend_Test_Results/`, `Model_Evaluation/`, `Real_Spotify_Audit_Evidence/` |
| `06_SOURCE_CODE/` | The complete source tree, 2.9 MB |
| `07_SUPPLEMENTARY_DOCUMENTATION/` | Object diagram, Gantt chart, database sizing, ML cost — the four items the approved reports did not cover |
| `RUNTIME_ASSETS/` | The 27 files the running system opens, 0.81 GB, SHA-256 verified. See its `SETUP.md` |
| `FINAL_PROJECT_REPORT.md` | The final report |

**The approved Phase 1–3 reports are included exactly as approved.** Nothing in
them was edited. Where they do not cover a faculty requirement, the gap is
filled by a *separate* document in `07_SUPPLEMENTARY_DOCUMENTATION/`.

## Verified results

| | |
|---|---|
| Backend tests | **818 passed, 78 skipped, 0 failed** |
| Frontend tests | **33 passed** |
| Lint and build | `ruff` clean, ESLint clean, Vite production build succeeds |
| Functional requirements | 26 of 27 implemented, 24 covered by automated tests; FR-27 not implemented |
| Non-functional requirements | 12 of 19 implemented and tested; 7 partial, unmeasured or not independently verified |
| Real applications audited end to end | **1** — `com.spotify.music`, manually collected, policy hash-verified |
| Audit 13 | `completed`, 14 verdicts (6 Consistent, 8 Undetermined), 18 evidence records, improved classifier |
| Runtime assets | 27 of 27 files verified against the SHA-256 manifest |

**The 78 skips are skips, not passes.** They are the PostgreSQL integration
suites, which refuse to guess a database and skip when `TEST_DATABASE_URL` is
unset. The team ran them separately and reported 78 passed with zero skips at
head; the logs are in `05_TESTING_AND_EVIDENCE/Backend_Test_Results/`.

## What this project does not claim

Stated here so a reviewer does not have to look for it.

* **No measured end-to-end accuracy.** The gold set of ≈100 annotated
  applications that the approved design specifies does not exist, so FR-27 is
  not implemented and the auditor's verdict accuracy has never been measured.
  No accuracy percentage for the system appears anywhere in this submission.
* **One real application**, against a design expectation of 300–500. The
  pipeline is generic and multi-application capability is unit-tested; the
  corpus is not.
* **Three of the five verdicts have never occurred on real data.**
  Contradictory, In-policy-not-declared and Declared-not-in-policy are
  exercised by 81 controlled tests only.
* **The improved classifier is not better than the baseline on every metric.**
  Macro-F1 0.6304 against 0.7489; it wins micro-F1, precision, Hamming loss and
  subset accuracy. Both figures are reported.
* **Span extraction is a prototype**, exact-match F1 0.1072.
* **OPP-115 is training data**, not the cross-source evaluation set.

## Running the system

`06_SOURCE_CODE/README.md` §8–13 covers prerequisites, environment, database,
migrations, backend, frontend and running an audit. Every command there was
checked against the repository.

Three assets are excluded from the source copy. `README.md` §9 says where each
comes from: the OPP-115 corpus (not ours to redistribute — `data/README.md`),
the Python and Node dependency trees (rebuilt from the lock files), and `.env`
(create from the included `.env.example`). The model checkpoints the system
needs at runtime **are** included, in `RUNTIME_ASSETS/`.

## Separately prepared deliverables

| Faculty requirement | Status |
|---|---|
| Presentation, ≈70–80 slides | **Not in this folder** — prepared by the team |
| One hard-copy group report | **Not in this folder** — `FINAL_PROJECT_REPORT.md` and the three phase reports are the source documents for printing |
| Every member brings a laptop | Team action on the day |

These are not claimed as complete. No other documentation gap remains: the four
that the previous audit identified are now filled in
`07_SUPPLEMENTARY_DOCUMENTATION/`.
