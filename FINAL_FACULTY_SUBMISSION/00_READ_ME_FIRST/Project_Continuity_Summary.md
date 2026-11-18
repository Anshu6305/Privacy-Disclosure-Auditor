# Project continuity summary — Phase 1 to Phase 4

How the project moved from the approved plan to the delivered system, and
where the two differ. Prepared 18 November 2026 at commit `e96383f`.

---

## The through-line

| Phase | Produced | Carried into the next phase |
|---|---|---|
| **1 — Feasibility** | FEASIBLE WITH CONDITIONS; ₹8,000–₹10,000 budget; 8 GB machine; open-source stack; risk ranking | The technology choices and the warning that span extraction and corpus collection were the two least certain items |
| **2 — SRS** | 27 FR, 19 NFR, 7 goals GI-01 to GI-07, assumptions, constraints, explicit exclusions | Every requirement ID, unchanged, into the design and the code |
| **3 — Design / SPMP** | 9 tasks T1–T9, 34 functions F-01 to F-34, 11 algorithms, 16-table schema, data dictionary, 15 diagrams, PERT schedule of 15.17 weeks | The function numbering that the code modules still carry, and the decisions D-1 to D-8 |
| **4 — Implementation** | The running system, 818 backend and 33 frontend tests, 99 consistency findings, one real audited application | This submission |

**Identifiers never drifted.** FR-11 in the SRS is F-11 in the design is the
classifier in `analysis/models/`, registered as `f11-improved-v1`, bound to
audits by that version label. The same holds for the five verdict names, the
ten OPP-115 categories, the seven screens S1–S7 and the eleven endpoints
E1–E11. A reader can follow one identifier from the feasibility study to a row
in the database.

## What the plan got right

* **The risk ranking.** Phase 1 §3.2 rated data-type and purpose extraction the
  least certain of the three learning tasks. It is: F-12's exact-match F1 is
  0.1072, the weakest component in the delivered system.
* **The architecture.** Three containers, a database table as the job queue, no
  broker, no microservices. Nothing in implementation argued for changing it.
* **The budget.** ₹0 was spent on compute; all training used free-tier Colab.
* **The schedule shape.** The PERT critical path runs through the model chain,
  and that is where the work actually concentrated.

## What the plan did not get right

**The corpus.** Phase 3 assumed 300–500 collected applications and a gold set
of about 100. Delivered: **one application, no gold set.** This single
shortfall produces most of this submission's limitations:

* FR-27 (offline evaluation against the gold set) is **not implemented** —
  there is nothing to evaluate against;
* no end-to-end accuracy figure exists or can be defended;
* three of the five verdicts have never been observed on real data;
* NFR-19's corpus capacity was never load-tested.

It is a collection and annotation shortfall, not an implementation one. The
pipeline is generic over applications and that is unit-tested
(`tests/unit/test_multi_application.py`): lookup is by package name, two
applications keep separate snapshots and policies, each audit resolves its own
application's sources, and no module under `backend/app`, `analysis/` or
`acquisition/` evaluates a string naming a specific application.

## Decisions that changed during implementation

Recorded in full in `PHASE4_DECISION_TABLE.md` and `PHASE4_CONSISTENCY_LOG.md`.
The ones a reviewer should know about:

* **D-01 Option A** — the aligner is a zero-shot NLI cross-encoder rather than
  a fine-tuned model, because the 300–500 labelled alignment pairs that
  fine-tuning needs do not exist.
* **DD-2** — one active audit at a time, so one model set is resident on the
  8 GB machine.
* **C-86 and C-87** — a contradiction requires a declaration to contradict, and
  must concern the same data practice rather than merely the same category.
  Both came from auditing real output, and both *reduced* the number of
  findings the system reports.
* **C-93** — `--variant improved` is refused rather than silently falling back,
  because the variant axis belongs to the classifier and F-12 and F-18 have no
  improved model. A report must never name a model that did not run.

Each of these made the system claim *less*, and each is the kind of change
GI-07 asks for.

## Where the project stands

**Delivered and verified:** the full pipeline, 26 of 27 functional
requirements, one real application audited end to end on PostgreSQL with
trained models, every evidence quote a verbatim slice at stored offsets.

**Delivered but unmeasured:** report latency, analysis time, concurrency,
corpus capacity.

**Not delivered:** the gold set, FR-27, the 300–500 application corpus, F-34
sequential model loading.

**Belongs to Phase 5:** whether the verdicts are correct.
