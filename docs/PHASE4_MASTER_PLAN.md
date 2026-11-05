# Phase 4 — Master Implementation Plan

Project: Cross-Source Privacy Disclosure Consistency Auditor for Android Applications
Baseline documents: Report_Phase-01, Report_Phase-02 (SRS v1.0), Report_Phase-03 (Design v1.0)
Status: plan for team approval. No application code written yet.

---

## 1. Baseline audit — what the three approved reports fix

Nothing below is a new decision. It is the set of constraints Phase 4 must implement.

| Area | Fixed by the approved reports |
|---|---|
| Objective | Compare an app's Play Store Data Safety declaration against its privacy policy; report inconsistency only, never legality, malice or developer intent |
| Requirements | FR-01 to FR-27, NFR-01 to NFR-19, GI-01 to GI-07 |
| Design units | Tasks T1 to T9, functions F-01 to F-34, algorithms ALG-1 to ALG-11 |
| API | Endpoints E1 to E11; HTTP/JSON only; E11 is the single external-facing path |
| Database | 16 tables, PostgreSQL, raw policy documents on disk with SHA-256 reference |
| Architecture | React+Vite SPA, FastAPI, background worker, PostgreSQL; three Docker containers on one host |
| ML/NLP | Three learning tasks: practice classification (F-11), data-type and purpose extraction (F-12), semantic alignment (F-18). Taxonomy mapping (F-15) is rule-based, not learned |
| Verdicts | Five outcomes via ALG-8 precedence; four ground-truth annotation labels; Undetermined is abstention only |
| Evidence | Consistent needs no record; all other verdicts need evidence, absence or inconclusive records; evidence is copied verbatim, never generated |
| Memory | One model resident per pipeline stage; one audit per worker; extra requests queue |
| Budget | ~Rs 10,000 cash ceiling; free and open-source resources preferred |

---

## 2. Development environment — findings

Checked on 2026-11-04 in the workspace attached to this folder.

| Item | Result | Consequence |
|---|---|---|
| Workspace | Linux VM (Ubuntu 22.04, aarch64), 3 GB RAM, 4 cores, ~8 GB free disk | Code can be written and unit-tested here. Transformer fine-tuning cannot. |
| Python / Node / git | 3.10.12 / v22.23.4 / 2.34.1 | Sufficient for all source code and tests |
| Docker | NOT installed in this workspace | Docker config will be authored here; it must be built and run on the team's own machine |
| PostgreSQL | NOT installed in this workspace | Schema and migrations authored here; SQLite used for unit tests; real Postgres runs on the team's machine |
| Network: pypi.org, github.com | Reachable | pip install and git work |
| Network: usableprivacy.org, huggingface.co, play.google.com | NOT reachable | Datasets, pretrained models and the Play Store corpus cannot be fetched from here. The team must download them on their own machine into this folder. |

This does not block Phase 4. It splits the work: all source code, schema, tests and documentation are produced here; dataset download, model download, corpus collection, GPU training and Docker execution happen on the team's machine.

---

## 3. Function-to-module mapping (F-01 to F-34)

| F-id | Responsibility | Planned module |
|---|---|---|
| F-01 | Application search | `backend/app/db/repositories/application_repo.py` — **implemented, M3B part 1** |
| F-02 | Audit request | `backend/app/services/audit_service.py` |
| F-03 | Unknown-application handling | `backend/app/db/repositories/application_repo.py` — **implemented, M3B part 1** |
| F-04 | Declaration loading | `backend/app/db/repositories/snapshot_repo.py` |
| F-05 | Policy document loading | `backend/app/db/repositories/snapshot_repo.py` |
| F-06 | Optional live retrieval | `acquisition/play_store_adapter.py` |
| F-07 | Provenance recording | `acquisition/provenance.py` |
| F-08 | Policy text extraction | `analysis/text/extractor.py` |
| F-09 | Segmentation with offsets | `analysis/text/segmenter.py` |
| F-10 | Analysability validation | `analysis/text/validator.py` |
| F-11 | Practice classification | `analysis/models/practice_classifier.py` |
| F-12 | Data-type and purpose extraction | `analysis/models/span_extractor.py` |
| F-13 | Model variant binding | `analysis/models/variant.py` |
| F-14 | Confidence thresholding (ALG-4) | `analysis/confidence/gate.py` |
| F-15 | Taxonomy mapping (ALG-5) | `analysis/mapping/taxonomy_mapper.py` (rules in `analysis/mapping/taxonomy/`) |
| F-16 | Declaration normalisation | `analysis/mapping/declaration_normaliser.py` |
| F-17 | Candidate construction (ALG-6) | `analysis/mapping/candidate_builder.py` |
| F-18 | Semantic alignment (ALG-7) | `analysis/models/semantic_aligner.py` |
| F-19 | Verdict assignment (ALG-8) | `analysis/verdict/verdict_engine.py` |
| F-20 | Evidence selection (ALG-9) | `analysis/verdict/evidence_selector.py` |
| F-21 | Absence recording | `analysis/verdict/absence_recorder.py` |
| F-22 | Inconclusive recording | `analysis/verdict/inconclusive_recorder.py` |
| F-23 | Report assembly | `backend/app/services/report_assembler.py` |
| F-24 | Report rendering | `frontend/src/pages/ReportPage.jsx` |
| F-25 | Evidence detail | `frontend/src/components/EvidencePanel.jsx` |
| F-26 | Scope statement | `frontend/src/components/ScopeBanner.jsx` |
| F-27 | Source links | `frontend/src/components/SourceLinks.jsx` |
| F-28 | Audit persistence | `backend/app/db/repositories/audit_repo.py` |
| F-29 | History retrieval | `backend/app/db/repositories/audit_repo.py` |
| F-30 | Audit comparison (ALG-10) | `backend/app/services/audit_compare.py` |
| F-31 | Gold-set evaluation | `ml/evaluate_goldset.py` |
| F-32 | Job queue | `backend/app/services/job_queue.py` |
| F-33 | Failure handling | `backend/app/services/failure_handler.py` |
| F-34 | Version registry and model loading | `backend/app/services/version_registry.py`, `analysis/models/model_loader.py` |

API routes map to E1-E11 in `backend/app/api/`. ALG-11 (prefix search) lives with F-01.

---

## 4. Repository structure

```
Major Project/
  README.md
  .gitignore
  .env.example
  docker-compose.yml
  backend/
    Dockerfile
    requirements.txt
    alembic.ini
    migrations/
    app/
      main.py  config.py
      api/         routes for E1-E11, schemas
      db/          models.py, session.py, repositories/
      services/    audit_service, job_queue, failure_handler,
                   version_registry, report_assembler, audit_compare
      worker/      worker.py
  analysis/        text/ models/ confidence/ mapping/ verdict/
  acquisition/     gateway.py play_store_adapter.py provenance.py
  ml/              data/ train_*.py evaluate_goldset.py configs/
  frontend/        Dockerfile  package.json  src/pages src/components src/api
  data/            raw/ corpus/ policies/ goldset/   (git-ignored, see data/README.md)
  tests/           unit/ api/ ml/ integration/
  docs/            PHASE4_MASTER_PLAN.md
                   IMPLEMENTATION_TRACEABILITY.md
                   PHASE4_CONSISTENCY_LOG.md
                   REQUIREMENT_CHANGE_LOG.md
                   TEAM_TRACKER.md  DEV_LOG.md
                   ANNOTATION_GUIDELINES.md  EXPENDITURE.md
```

`analysis/` is deliberately outside `backend/` so the ML code has no dependency on FastAPI, as Phase 3 Section 6.1 requires.

---

## 5. Implementation order and dependencies

Milestones follow the approved Phase 3 WBS. Dependencies are real, not arbitrary.

| Milestone | Needs | Blocked by external data? |
|---|---|---|
| M1 Repository and environment | — | No |
| M2 Database and backend foundation | M1 | No |
| M3A Acquisition layer and corpus format | M2 | No — offline-first by design |
| M3B Acquisition persistence | M3A, **D-1 decision** | **Part 1 complete** — F-01, F-03 and the application repository need no snapshot design. F-02 and F-04 to F-07 still need D-1 |
| M4 Text processing (F-08 to F-10) | M2 | No — complete, on fixtures only |
| M5 Baseline ML (F-11 baseline) | M4 | Complete — OPP-115 present |
| M6 Improved ML (F-11, F-12, F-18) | M5 | Yes — models, OPP-115, PolicyIE, alignment labels |
| M7 Verdict and evidence engine (F-15 to F-22) | M4 | No — pure logic, fully testable now |
| M8 Backend integration (E1-E11, F-32 to F-34) | M2, M7 | No |
| M9 React frontend (S1-S7) | M8 | No |
| M10 Integration and Docker deployment | M8, M9 | Docker on team machine |

M1, M2, M4, M7, M8 and M9 can be built without waiting for any dataset. That is most of the system. M3, M5 and M6 need the team to supply data.

### Execution-order adjustment — approved 2026-11-04

Milestone 7 is being implemented **before** Milestones 3, 4, 5 and 6, on the
team's approval, because its logic is deterministic and can be developed and
tested in isolation from acquisition and from any model.

This changes the **order** of execution only. M3, M4, M5 and M6 remain
outstanding work and are **not** completed, skipped or reduced in scope by
this. The milestone table above still governs what each of them must deliver,
and the traceability document continues to show their functions as Not
implemented.

Dependency note: M7 consumes alignment judgements as inputs. Those judgements
are produced by F-18, which belongs to M6. Until M6 exists, the only
judgements in the system come from controlled test fixtures. No part of M7
produces or simulates a model prediction.

---

## 6. Database implementation sequence

1. SQLAlchemy models for all 16 tables with the Phase 3 column names and types.
2. CHECK constraints: `verdict.verdict_value` (5 values), `gold_annotation.label` (4 values), `evidence_record.record_type` (3 values).
3. UNIQUE constraints: `application.package_name`, `verdict(audit_id, ds_category)`, `gold_annotation(app_id, ds_category, annotator_code)`.
4. Seven NOT NULL foreign keys on `audit_run` (snapshot + four version references).
5. Indexes listed in Phase 3 Section 10.3, including the functional lower() indexes for ALG-11.
6. Alembic baseline migration.
7. Schema tests asserting each constraint actually rejects bad data.

---

## 7. Dataset plan — availability, licensing, and what is genuinely missing

| Dataset | Supports | Availability | Action needed |
|---|---|---|---|
| OPP-115 | F-11 classification | Phase 1 verified it as a free download for research and teaching. Not reachable from this workspace. | Team downloads into `data/` on their machine |
| APP-350 | F-11 (mobile domain) | Licence unverified in Phase 1 and Phase 3 | Team checks terms before use; project does not depend on it |
| PolicyIE / PI-Extract | F-12 span extraction | Licence unverified; both corpora are small (31 and 30 documents) | Team checks terms. If unusable, the FR-12 fallback applies and needs a recorded change plus faculty approval |
| Play Store corpus, 300-500 apps | Operational input | Must be collected by the team, rate-limited per NFR-15 | Team runs the collector on their machine |
| Gold set, ~100 apps | F-31 evaluation | Does not exist; the team creates it | Annotation guidelines will be written in M3 |

### The one genuine gap

**F-18 semantic alignment has no public training data.** No corpus labels a (policy statement, Data Safety claim) pair as Supports, Contradicts or No-match. Phase 1 anticipated fine-tuning "on a modest number of examples" but those examples have to come from us. Two workable options:

- **Option A (recommended).** Start from an encoder already fine-tuned on a public natural-language-inference corpus and use it zero-shot, then fine-tune on 300-500 pairs the team labels while building the gold set. Entailment maps to Supports, contradiction to Contradicts, neutral to No-match.
- **Option B.** Zero-shot NLI only, with the threshold tuned on the gold set, and no fine-tuning.

### DECISION — Option A, approved by the team on 2026-11-04

Fine-tuning proceeds **only if** sufficient reliable annotations can be
produced. The following safeguards are binding on Milestone 6.

1. **Annotation guide first.** Supports, Contradicts and No-match are defined
   with decision rules and worked examples before any labelling starts. See
   `docs/ANNOTATION_GUIDELINES_ALIGNMENT.md`.
2. **Zero-shot stays the baseline.** The zero-shot NLI model is retained and
   evaluated on the same held-out test set, so the fine-tuned model is always
   compared against it rather than against nothing.
3. **Split by application, never by pair.** Training, validation and test
   splits are grouped by application. Two pairs from the same app, or from the
   same policy document, never land on opposite sides of a split.
4. **Per-class precision, recall and F1, plus macro-F1.** Reported for both
   models. No improvement is claimed unless the held-out evaluation supports
   it. Accuracy alone is never reported.
5. **Fall back honestly.** If annotation volume or inter-annotator agreement is
   insufficient, or if the fine-tuned model does not beat zero-shot on the
   held-out set, the zero-shot model is retained, the limitation is documented,
   and the deviation is recorded in `REQUIREMENT_CHANGE_LOG.md` for faculty
   review.

Implementation belongs to Milestone 6 and is not begun early.

---

## 8. ML/NLP plan

| Task | Baseline | Improved | Trained where |
|---|---|---|---|
| F-11 classification | TF-IDF + one-vs-rest logistic regression, scikit-learn | Fine-tuned encoder, PyTorch + Transformers | Baseline: CPU, minutes. Improved: free-tier GPU |
| F-12 span extraction | — | Token classification with BIO decoding, character offsets preserved | Free-tier GPU |
| F-18 alignment | NLI model zero-shot | Fine-tuned on team-labelled pairs (Option A) | Free-tier GPU |

Rules carried from the reports: fixed random seeds; document-level and developer-level splits to prevent leakage; macro-F1 and per-class F1 reported, not accuracy; abstention rate reported alongside; metrics computed twice (non-abstained cases, and all cases with abstentions as errors); every result stored with the config that produced it. No accuracy target is set in advance and no result will be written down before it is measured.

Model sizes will be chosen to fit CPU inference within the NFR-02 target. Candidates are base or distilled encoders in the 60-140 M parameter range. Exact checkpoints need team confirmation (Section 12, Q3).

---

## 9. Backend and frontend integration milestones

- **M8.1** E1, E2, E9 — search, detail, source links. Verified against a seeded corpus.
- **M8.2** E3, E4 plus F-32 job queue and the worker loop. Verified by submitting an audit and watching status change without the API blocking.
- **M8.3** E5, E6 — report and evidence retrieval, with all three record types.
- **M8.4** E7, E8 — history and comparison. E10 version metadata. E11 kept isolated.
- **M9.1** S1-S3 search, detail, processing with real polling.
- **M9.2** S4-S5 report and evidence panel with the three-branch display.
- **M9.3** S6-S7 history and comparison.

---

## 10. Traceability structure

`docs/IMPLEMENTATION_TRACEABILITY.md` will carry one row per FR, NFR, GI and F-id:

| Requirement | Goal | Phase 3 Task/Function | Code File/Module | API/Database | Test ID | Status |

Status is one of: Implemented and verified / Partially implemented, awaiting verification / Not implemented or blocked. A row moves to "Implemented and verified" only when its test has actually run and passed, and the real test output is kept.

Test identifiers follow `test_FR_<nn>_<behaviour>`. Module docstrings carry their design ids, for example `F-19 / FR-18 — verdict assignment, ALG-8`.

---

## 11. Six-member responsibility framework

Names stay as placeholders until the team supplies them. Roles follow Phase 3 Section 13.2.

| Role | Area | Functions owned |
|---|---|---|
| R1 [Member] | Design coordination and alignment | F-15 to F-18, taxonomy artefact |
| R2 [Member] | Data engineering and corpus | F-01 to F-07, corpus collection (M3A built; collection not started) |
| R3 [Member] | NLP and classification | F-08 to F-14 |
| R4 [Member] | Backend and integration | F-23, F-32 to F-34, E1-E11 |
| R5 [Member] | Database and persistence | 16 tables, migrations, F-28 to F-30 |
| R6 [Member] | Frontend and evaluation | F-24 to F-27, F-31, screens S1-S7 |

Shared by all six: gold-set annotation, weekly integration testing, and documenting their own component.

---

## 12. Open decisions and risks

### Blocking — needed before M3, M5, M6

- **Q1 Datasets.** Can the team download OPP-115 into `data/` on their machine? Have PolicyIE and PI-Extract licence terms been checked yet?
- **Q2 Alignment labels.** Option A or Option B from Section 7?
- **Q3 Model checkpoints.** Confirm the encoder family for the improved classifier, the span extractor and the NLI aligner, given CPU inference and an 8 GB machine.
- **Q4 Corpus collection.** Who runs the Play Store collector, and when? It must be rate-limited and spread over weeks per NFR-15.

### Non-blocking — can be decided later

- **Q5 Runtime host.** Docker and PostgreSQL are not installed in the workspace reachable from here. Confirm the team will install Docker Desktop and run the stack on their own machine; the compose file and Dockerfiles will be authored here regardless.
- **Q6 GPU.** Confirm free-tier Colab or Kaggle for the three training runs, with checkpoints copied back into `ml/`.

### Risks carried from Phase 3

| Risk | Handling |
|---|---|
| Play Store scraper breaks (highest-probability risk in Phase 1) | All retrieval behind the single acquisition gateway (NFR-16); corpus frozen early so a break never stops development or a demo |
| F-12 training data unusable | Documented FR-12 fallback; requires a recorded change and faculty approval, not a silent drop |
| NFR-02 60-second target on CPU | Issue DI-1 is open in Phase 3; measured in M6, not assumed |
| Memory on 8 GB machine | One model resident per stage (DD-2); measured during M6 |

### What proceeds without waiting

M1, M2, M4, M7, M8 and M9 need no external dataset. On approval, work starts at M1 and continues through M2, M4 and M7, which includes the complete verdict engine and its ALG-8 tests.
