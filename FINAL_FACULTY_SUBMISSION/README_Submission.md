# Faculty Submission — Phase 1 to Phase 4

**Cross-Source Privacy Disclosure Consistency Auditor for Android Applications**
B.Tech major project · Kalinga Institute of Industrial Technology · six-member team
Prepared 15 November 2026 · Source repository commit `421f782`, branch `master`

This folder is a **Phase 1–4 submission**. Phase 5 (academic validation and
testing) is a separate phase and has not begun; no Phase 5 report is included
and none is claimed.

---

## What to read, in order

| # | Folder | What is in it |
|---|---|---|
| 1 | `01_Phase_1_Feasibility_Report/` | `Report_Phase-01.docx` — the approved feasibility study: objectives, technical and financial feasibility, ₹8,000–₹10,000 budget, 8 GB development environment, risks |
| 2 | `02_Phase_2_SRS/` | `Report_Phase-02.docx` — the approved SRS in IEEE-830 form: 27 functional requirements, 19 non-functional requirements, seven implementation goals, assumptions, constraints and explicit exclusions |
| 3 | `03_Phase_3_System_Design/` | `Report_Phase-03.docx` — the approved system design and project plan: nine tasks, functions F-01 to F-34, algorithms ALG-1 to ALG-11, the data dictionary (§10.2), effort and schedule estimates. Plus `diagrams/` — 15 diagrams in `.dot`, `.mmd`, `.svg` and `.png`, and the original `phase3-diagrams-final.zip` |
| 4 | `04_Phase_4_Implementation_Documentation/` | 26 Markdown documents produced during implementation. Start with `PHASE4_CLOSEOUT.md`; `PHASE4_CONSISTENCY_LOG.md` records all 99 points where the implementation met the approved design, including every defect found and how it was corrected |
| 5 | `05_Testing_Evidence/` | Raw output of every test, lint and build run on 15 November 2026; the model metric files; the five real audit reports; the collected Spotify privacy policy; and the three most recent PostgreSQL verification logs |
| 6 | `06_Project_Source_Code/` | The complete source tree, 2.9 MB |
| — | `../FINAL_SUBMISSION_AUDIT.md` | **Read this for the honest status of every requirement.** Cleanup record, Phase 1–4 consistency findings, the full 27 FR and 19 NFR traceability table with status labels, the faculty-instruction checklist with its four open gaps, and the final verdict |

## The system in three sentences

An Android app declares what data it collects in the Google Play Data Safety
section, and describes the same thing in prose in its privacy policy; nothing
checks that the two agree. This system reads both, works out what the policy
says about each data-practice category using NLP and three machine-learning
components, maps both sources into one category set, and reports per category
whether they are consistent, inconsistent in one of three specific ways, or
whether it cannot tell. Every finding is anchored to the exact characters of the
policy that produced it, and when confidence is insufficient the system abstains
and says why instead of guessing.

It compares two public disclosures. It does not inspect the application binary,
does not observe runtime traffic, and makes no legal or compliance judgement.

## Verified results, in brief

| | |
|---|---|
| Backend tests | **818 passed, 78 skipped, 0 failed** |
| Frontend tests | **33 passed** |
| Lint and build | `ruff` clean, ESLint clean, Vite production build succeeds |
| Real application audited end to end | **1** — `com.spotify.music`, manually collected, policy hash-verified |
| Real audit result | Audit 13: `completed`, 14 verdicts (6 Consistent, 8 Undetermined), 18 evidence records, on the improved classifier |
| Functional requirements | 26 of 27 implemented, 24 covered by automated tests; FR-27 not implemented |
| Non-functional requirements | 13 of 19 implemented and tested; 6 partial, unmeasured or not independently verified |

**The 78 skips are skips, not passes.** They are the PostgreSQL integration
suites, which refuse to guess a database and skip when `TEST_DATABASE_URL` is
unset. The team ran them separately and reported 78 passed with zero skips at
head; the logs are in `05_Testing_Evidence/postgresql_verification_logs/`.

## What this project does not claim

Stated here so a reviewer does not have to look for it:

* **No measured end-to-end accuracy.** The gold set of approximately 100
  annotated applications that the approved design specifies does not exist, so
  FR-27 is not implemented and the auditor's verdict accuracy has never been
  measured. No accuracy percentage for the system appears anywhere in this
  submission.
* **One real application, against a design expectation of 300–500.** The
  pipeline is generic and multi-application capability is unit-tested; the
  corpus is one application. This is the largest deviation from the approved
  design and it is a collection shortfall, not an implementation one.
* **Three of the five verdicts have never occurred on real data.**
  Contradictory, In-policy-not-declared and Declared-not-in-policy are exercised
  by 81 controlled tests only.
* **The improved classifier is not better than the baseline on every metric.**
  It wins micro-F1, precision, Hamming loss and subset accuracy; it loses
  macro-F1 (0.6304 against 0.7489) because it never predicts two rare
  categories. Both figures are reported.
* **Span extraction is a prototype**, exact-match F1 0.1072.
* **OPP-115 is training data**, not the cross-source evaluation set.

## Running the system

Full instructions, with commands checked against the repository, are in
`06_Project_Source_Code/README.md` — sections 8 to 13 cover prerequisites,
environment, database, backend, frontend and how to run an audit.

Three assets are excluded from the source copy because they are large, are not
ours to redistribute, or are secrets. `README.md` §9 says where each one comes
from: the OPP-115 corpus (`data/README.md`), the model checkpoints (rebuild
scripts provided) and `.env` (create from the included `.env.example`).

## Separately prepared deliverables

The presentation of approximately 70–80 slides and the single hard-copy group
report are prepared by the team and are not in this folder.

Four documentation gaps are open and are listed in §7 of
`FINAL_SUBMISSION_AUDIT.md`: a UML object diagram, a Gantt chart (a PERT chart
and schedule analysis are provided instead), explicit database size and
connection estimates, and a token-level ML cost estimate. None of them affects
whether the implementation runs.
