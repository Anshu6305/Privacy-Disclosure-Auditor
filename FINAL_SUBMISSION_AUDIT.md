# Final Submission Audit

**Cross-Source Privacy Disclosure Consistency Auditor for Android Applications**
B.Tech major project, KIIT · six-member team · Phase 1–4 submission
Audit date: 18 November 2026 · Branch `master`

This document records what was inspected, what was removed, what was
deliberately kept, how the implementation compares with the approved Phase 1–3
documents, and what remains incomplete. Every figure was produced by a command
run against this repository on the date above, except where the text names a
different source.

---

## 1. Project size and file count

| | Files (excluding `.git`) | Size |
|---|---:|---:|
| **Before this audit** | 63,394 | **5.2 GB** |
| **After this audit** | 63,450 | **6.0 GB** |

The project grew. That is intentional: the submission folder now carries a
complete, SHA-256-verified runtime asset package of 843 MB so the system can
actually be run from the submission, which the previous version could not.

### What accounts for the size

| Directory | Size | What it is |
|---|---:|---|
| `ml/` | 3.5 GB | Model checkpoints |
| `.venv/` | 1.2 GB | Python environment, dominated by PyTorch (`libtorch_cpu.dylib` alone is 169 MB) |
| `FINAL_FACULTY_SUBMISSION/` | 858 MB | This submission, including the runtime assets |
| `data/` | 356 MB | OPP-115 raw 339 MB, processed 18 MB, collected corpus 206 KB |
| `frontend/node_modules/` | 113 MB | Node dependencies |
| `.git/` | 8.8 MB | History |
| Everything else (source, tests, docs) | ≈ 5 MB | The actual project code |

**The single largest finding: about 2.7 GB of `ml/` is redundant.** The F-18
NLI checkpoint was cloned from its upstream repository with every
serialisation format it publishes:

| Inside `ml/checkpoints/nli-mnli-v1/` | Size | Used by this project |
|---|---:|---|
| `model.safetensors` | 313 MB | **Yes** — this is what `transformers` loads |
| `onnx/` (5 variants) | 1.7 GB | No |
| `openvino/` | 393 MB | No |
| `flax_model.msgpack` | 313 MB | No |
| `pytorch_model.bin` | 313 MB | No — superseded by safetensors |

**Verified, not assumed:** a search of `backend/`, `analysis/`, `acquisition/`,
`ml/`, `scripts/`, `tests/` and `pyproject.toml` for `onnx`, `openvino`,
`flax`, `jax` and `tensorflow` returns **no match in any code or requirements
file**. The only hits are the strings "jax" and "ajax" inside a BERT vocabulary
file.

**These files were not deleted.** The working rules say never to delete a model
because it is large, and to preserve when in doubt. They are alternative
encodings of weights the project does use, so the judgement is not clear-cut
and the decision belongs to the team. If the team wants the space back:

```bash
rm -rf ml/checkpoints/nli-mnli-v1/{onnx,openvino} \
       ml/checkpoints/nli-mnli-v1/{flax_model.msgpack,pytorch_model.bin}
```

This is reversible — the files are re-downloadable from the upstream model
repository — and it would take `ml/` from 3.5 GB to about 0.8 GB with no effect
on the running system. The complete runtime asset set is **0.81 GB**, which is
the measured proof that the other 2.7 GB is not needed to run anything.

## 2. Cleanup performed, and why each file was safe

Only regenerable artefacts were removed. No source file, document, dataset,
checkpoint, migration, database record or commit was touched, and the Git
working tree was clean before and after — which is the check that nothing
tracked was affected.

| Removed | Count | Why safe |
|---|---:|---|
| `__pycache__` directories | 27 | Python bytecode, regenerated on import; `.gitignore`d |
| `*.pyc` files | 292 | Same |
| `.DS_Store` | 7 | macOS Finder metadata; `.gitignore`d |
| `frontend/vite.config.js.timestamp-*.mjs` | 9 | Vitest rewrites the config per run and cannot always remove it; `.gitignore`d build scratch |
| `.pytest_cache/`, `.ruff_cache/` | 2 | Tool caches |
| `.coverage` | 1 | Coverage database |
| Superseded duplicate folders inside `FINAL_FACULTY_SUBMISSION/` | 4 paths | Earlier layout, fully replaced; one definitive structure is now maintained as required |

No file was removed for being large, old or unfamiliar. **No file was found
whose purpose could not be established**, so nothing is listed for manual
review.

`.gitignore` was reviewed and extended only to stop the submission folder's
*derived* parts being committed twice. It already covered datasets,
checkpoints, `.env`, caches, logs, OS clutter and the Vitest timestamps. No
secret is tracked; `.env.example` is present and sanitised.

## 3. Files deliberately retained

Several look like clutter and are not.

| Retained | Why |
|---|---|
| `spotify_policy.html` (192 KB, tracked) | SHA-256 `13089e7b…4ea8`, **identical to the policy hash in `data/corpus/apps/com.spotify.music/record.json`**. Because `data/*` is git-ignored, this is the only committed copy of the pilot's real privacy policy — primary source evidence |
| `spotify_audit_2…6_report.json` | The audit history the consistency log cites, including runs whose verdicts changed under C-86 and C-87. Deleting them would destroy the evidence that those corrections were needed |
| `myapp.json` | Referenced by `scripts/manual_collect.py` and `M11_REPORT.md`; it is the manual-collection template |
| 15 `*_verification_*.log` at the root | PostgreSQL verification output from `scripts/verify_migrations.sh`. The project protocol requires PostgreSQL results to be team-run and reported; these are that record. Git-ignored, so local evidence only. The three most recent are copied into the submission |
| `.env` | Required by the local setup. Not committed, not copied into the submission |
| `ml/checkpoints/nli-mnli-v1/{onnx,openvino,flax,bin}` | Unused but not deleted — see §1 |
| `.venv/`, `node_modules/`, `data/`, `ml/` | Required local assets, retained in the working directory and excluded from the source copy |

## 4. Test and build results

Run 18 November 2026. Raw output in `05_TESTING_AND_EVIDENCE/`.

| Check | Command | Passed | Skipped | Failed |
|---|---|---:|---:|---:|
| Backend | `pytest tests -p no:warnings` | **818** | **78** | **0** |
| Frontend | `npm test` (Vitest) | **33** | 0 | 0 |
| Python lint | `ruff check .` (pinned 0.8.4) | clean | — | — |
| Frontend lint | `npm run lint` (ESLint) | clean | — | — |
| Frontend build | `npm run build` (Vite) | 49 modules, succeeds | — | — |
| Import check | `cd backend && python -c "import app.main, app.worker.worker"` | OK, checkpoint resolves | — | — |

**The 78 skips are skips, not passes:**

| Suite | Skipped | Reason |
|---|---:|---|
| `test_postgresql_schema.py` | 32 | `TEST_DATABASE_URL` unset |
| `test_application_search_postgresql.py` | 24 | Same |
| `test_m3b_persistence_postgresql.py` | 16 | Same |
| `test_m8_pipeline_postgresql.py` | 6 | Same |

**Not executed because of environment limitations.** PostgreSQL runs in Docker
Desktop on the team Mac, published on that host's loopback only, and is not
reachable from the agent session that produced this audit. The team ran those
suites separately through `scripts/verify_migrations.sh` and reported 78 passed
with zero skips at head on 2026-11-06; the logs are included. That is a
team-reported result, not an in-session one.

## 5. Phase 1–4 consistency findings

The approved reports were read directly (`Report_Phase-01/02/03.docx`). They
are the academic baseline and were **not** edited to match the implementation.

### Phase 1 — Feasibility: consistent

Open-source stack, ₹8,000–₹10,000 budget (actual training spend ₹0 on free
Colab T4), 8 GB development machine with encoder-scale models only, and the
verdict FEASIBLE WITH CONDITIONS. Phase 1's risk ranking was **correct**: it
named span extraction (§3.2) and corpus collection as least certain, and both
became the project's real constraints.

### Phase 2 — SRS: consistent

All 27 FR, 19 NFR and 7 goals traced in §6. The approved exclusions hold —
nothing in code, API response or interface claims legal or regulatory
compliance verification, Android binary or runtime analysis, iOS support,
multilingual analysis, or user accounts. Every report carries its own scope
sentence.

### Phase 3 — Design/SPMP: consistent except the corpus

Architecture (three containers, database-table queue, no broker), the single
snapshot design D-1 Option A, the five-verdict `CHECK` constraint, the
four-label gold-set constraint, the data dictionary §10.2, prefix search
without `pg_trgm`, 34 functions and 11 algorithms — all as designed.

**Two major deviations, both disclosed:**

| Phase 3 | Delivered | |
|---|---|---|
| Corpus of **300–500 applications** | **1** | Collection shortfall |
| Gold set of **≈100 applications** | **0** | Annotation shortfall |

These are not implementation defects. The pipeline is generic over
applications and that is now tested
(`tests/unit/test_multi_application.py`, 6 tests). Their consequence is firm:
**FR-27 cannot be satisfied and no system-level accuracy is defensible.**

### Phase 4 — the eleven stated limitations, each re-verified

| # | Claim | Verified |
|---|---|---|
| 1 | Spotify the only real application | **Confirmed** — `data/corpus/apps/` contains exactly `com.spotify.music`, `manually_collected`, 19 Data Safety entries |
| 2 | Audit 13: 14 verdicts, 6 Consistent, 8 Undetermined, 18 evidence | **Team-reported, not independently verified** — PostgreSQL unreachable. Internally consistent: 6+8=14; F-23 gives Consistent no record, so all 18 come from the 8 Undetermined verdicts; F-22 permits 1–3 each, a range of 8–24 |
| 3 | Three verdicts fixture-only | **Confirmed** |
| 4 | Multi-application is unit-tested, corpus is one app | **Confirmed** |
| 5 | OPP-115 is training data, not the gold set | **Confirmed** — different unit, different task; never conflated |
| 6 | Gold set not completed | **Confirmed** — zero annotations |
| 7 | FR-27 must not be claimed complete | **Confirmed** — no `analysis/evaluation/` module exists; the only `GoldAnnotation(` match in production code is the class definition itself |
| 8 | Improved classifier not uniformly better | **Confirmed** — macro-F1 0.6304 vs 0.7489; micro-F1 0.7775 vs 0.7690; never predicts Data Retention or Do Not Track |
| 9 | Span extraction limited | **Confirmed** — exact F1 0.1072, overlap 0.5658, over 1,010 gold spans |
| 10 | 78 skips are not passes | **Confirmed** — itemised in §4 |
| 11 | F-34 sequential loading incomplete | **Still the case** — `build_bound_pipeline_factory` constructs `AuditPipeline` with classifier, aligner and mapper bound simultaneously |

## 6. Requirement traceability counts

Full matrix: `00_READ_ME_FIRST/Requirement_Traceability_Matrix.md`.

| Status | FR | NFR |
|---|---:|---:|
| Implemented and tested | 24 | **12** |
| Implemented, partially tested | 2 | 2 |
| Implemented, not independently verified | 0 | 3 |
| Partially implemented | 0 | 2 |
| Not implemented | 1 | 0 |
| Not applicable / outside scope | 0 | 0 |
| **Total** | **27** ✔ | **19** ✔ |

**Correction to the previous audit.** It printed 13 in the NFR column of the
first row, giving a column total of 20 against 19 requirements. The row-level
assignments were always correct — every ID appears exactly once, none
duplicated, none missing — but the summary was wrong by one. The correct figure
is **12**, and a sixth label used previously ("implemented, not measured") has
been folded into "implemented, not independently verified", which is the
sanctioned label for NFR-02. Both columns now reconcile exactly.

FR not implemented: **FR-27** only.
NFR partially implemented: **NFR-04** (concurrency never load-tested),
**NFR-18** (image build not completed; verified path is the local virtual
environment).
NFR not independently verified: **NFR-01**, **NFR-02**, **NFR-19** — all
timing or capacity targets that were never measured.

## 7. Faculty documentation checklist

| Requirement | Status | Where |
|---|---|---|
| Feasibility report | ✔ | `01_PHASE_1_FEASIBILITY/Report_Phase-01.docx` |
| IEEE-830 SRS | ✔ | `02_PHASE_2_SRS/Report_Phase-02.docx` |
| Design document | ✔ | `03_PHASE_3_SYSTEM_DESIGN/Report_Phase-03.docx` |
| Detailed algorithms per FR | ✔ | Phase 3 §4 — F-01 to F-34, ALG-1 to ALG-11 |
| Data dictionary | ✔ | Phase 3 §10.2, PostgreSQL types per column |
| DFDs for functions | ✔ | `Supporting_Diagrams/dfd0`, `dfd1`, `dfd2` |
| UML class diagrams | ✔ | `class_domain`, `class_analysis_a`, `class_analysis_b`, `class_orchestration` |
| **UML object diagram** | ✔ **now supplied** | `07_SUPPLEMENTARY_DOCUMENTATION/Object_Diagram.md` — instance snapshot of audit 6 with real values |
| Sequence, activity, component, deployment, use-case, ER | ✔ | 15 diagrams in `Supporting_Diagrams/` |
| Project cost and time estimation | ✔ | Phase 1 ₹8,000–₹10,000; Phase 3 §13–15, 850 person-hours, 15.17 weeks, COCOMO cross-check |
| **Gantt chart** | ✔ **now supplied** | `07_SUPPLEMENTARY_DOCUMENTATION/Gantt_Chart.md` — derived from Phase 3's own PERT expected times; the computed finish reproduces their 15.17 weeks exactly |
| Database type and schema | ✔ | PostgreSQL 16, 16 tables, ER diagram, data dictionary |
| **Database size and connection estimates** | ✔ **now supplied** | `07_SUPPLEMENTARY_DOCUMENTATION/Database_Sizing_And_Connections.md` — 553 KB per audited application, under 2 GB at the NFR-19 ceiling; pool and `max_connections` arithmetic |
| Frontend component explanations | ✔ | Phase 3 frontend design, screens S1–S7, component docstrings |
| **ML token-level cost and scalability** | ✔ **now supplied** | `07_SUPPLEMENTARY_DOCUMENTATION/ML_Cost_And_Scalability.md` — 8,176 tokens and 1,869 forward passes per audit; **no token billing exists**, so computational cost is given instead |
| Global and local variable declarations | **Partial** | Phase 3 §10.2 is the data dictionary for persisted state, and module docstrings describe module-level constants. There is no separate variable-declaration listing, and one was not fabricated |
| Presentation ≈70–80 slides | **Separate** | Prepared by the team; not in this repository |
| Hard-copy group report | **Separate** | `FINAL_PROJECT_REPORT.md` and the three phase reports are the source documents |
| Each member brings a laptop | **Separate** | Team action |

The four gaps the previous audit identified are **now filled**. One partial
item remains (global/local variable declarations) and three deliverables are
prepared outside this repository. Nothing was invented to close a gap: the
Gantt is derived arithmetic from the approved PERT table, the object diagram
uses values from a committed audit report, and the ML cost document states
plainly that no token charge exists rather than estimating one.

## 8. Outstanding limitations

1. **No gold set**, so FR-27 is not implemented and **no end-to-end accuracy
   has been measured**. Phase 5.
2. **One application collected** against a design expectation of 300–500.
3. **Three of five verdicts never observed on real data.**
4. **Audit 13 is team-reported**, corroborated but not re-queried here.
5. **78 PostgreSQL tests skip** without `TEST_DATABASE_URL`.
6. **NFR-01, NFR-02, NFR-04, NFR-19 never measured.**
7. **F-34 sequential model loading not implemented.**
8. **The Docker worker image omits the ML dependency set** by design; the
   verified run path is the local virtual environment.
9. **Span extraction weak at exact match** (0.1072); the aligner is zero-shot.
10. **About 2.7 GB of unused model serialisations retained** (§1), pending a
    team decision.
11. Out of approved scope and never claimed: APK or runtime analysis, iOS,
    non-English policies, authentication, legal or compliance conclusions.

## 9. Runtime assets and setup

A complete runtime package is included at
`FINAL_FACULTY_SUBMISSION/RUNTIME_ASSETS/` — **27 files, 843 MB**, covering
every file the running system opens that is not in the source tree.

| Asset | Size | Licence |
|---|---:|---|
| F-11 baseline classifier (M5) | 2.6 MB | Ours |
| F-11 improved classifier | 255 MB | Ours, fine-tuned from `distilbert-base-uncased` (Apache 2.0) |
| F-12 span extractor | 253 MB | Ours, same base |
| F-18 zero-shot NLI aligner | 318 MB | `cross-encoder/nli-distilroberta-base`, **Apache 2.0** |
| Model evaluation metrics | 17 KB | Ours |
| Collected application corpus | 206 KB | Spotify policy is third-party content, included as audit evidence |

**Verification: 27 of 27 files matched the SHA-256 manifest, zero mismatches,
zero missing.** The manifest is
`00_READ_ME_FIRST/Runtime_Assets_Manifest.md` with a checkable digest list at
`00_READ_ME_FIRST/runtime_assets.sha256`:

```bash
shasum -a 256 -c FINAL_FACULTY_SUBMISSION/00_READ_ME_FIRST/runtime_assets.sha256
```

Installation instructions are in `RUNTIME_ASSETS/SETUP.md`.

**Deliberately excluded:** OPP-115, which is released for research and teaching
and is **not ours to redistribute**. It is needed only to retrain the
classifiers, not to run the system; `data/README.md` gives the obtain-and-verify
procedure. Also excluded: `.venv` and `node_modules`, rebuilt from the lock
files, and the 2.7 GB of unused model serialisations.

## 10. Submission folder location

`FINAL_FACULTY_SUBMISSION/` at the repository root — **858 MB, 388 files**.

```
FINAL_FACULTY_SUBMISSION/
├── 00_READ_ME_FIRST/            Submission_Guide, Project_Continuity_Summary,
│                                Requirement_Traceability_Matrix,
│                                Runtime_Assets_Manifest, runtime_assets.sha256
├── 01_PHASE_1_FEASIBILITY/      Report_Phase-01.docx          (unaltered)
├── 02_PHASE_2_SRS/              Report_Phase-02.docx          (unaltered)
├── 03_PHASE_3_SYSTEM_DESIGN/    Report_Phase-03.docx          (unaltered)
│   └── Supporting_Diagrams/     15 diagrams, .dot/.mmd/.svg/.png
├── 04_PHASE_4_IMPLEMENTATION/   26 implementation documents
├── 05_TESTING_AND_EVIDENCE/     Backend_Test_Results/ Frontend_Test_Results/
│                                Model_Evaluation/ Real_Spotify_Audit_Evidence/
├── 06_SOURCE_CODE/              complete source tree, 3.0 MB
├── 07_SUPPLEMENTARY_DOCUMENTATION/  object diagram, Gantt, DB sizing, ML cost
├── RUNTIME_ASSETS/              27 files, 843 MB, SHA-256 verified
└── FINAL_PROJECT_REPORT.md
```

**On the source-code layout.** The faculty structure names
`Backend/ Frontend/ ML/ Scripts/ Tests/ Configuration_Templates/`. The copy
keeps the repository's own lowercase directory names, because
`docker-compose.yml`, `PYTHONPATH` and the Alembic configuration reference
those paths; renaming them would produce a submission that cannot be run.
Preserving functionality was the stated absolute priority, so the mapping is
documented rather than applied: `backend/` → Backend, `frontend/` → Frontend,
`ml/` + `analysis/` + `acquisition/` → ML, `scripts/` → Scripts, `tests/` →
Tests, and `.env.example` + `pyproject.toml` + `docker-compose.yml` +
`alembic.ini` → Configuration Templates.

No secret is present: a search of the folder for `.env`, `*.key` and `*.pem`
returns nothing. The original working directory is untouched — no file was
moved or renamed outside the submission folder.

## 11. Git status

| | |
|---|---|
| Branch | `master` |
| Commit at audit start | `e96383f` |
| Working tree | clean before and after the cleanup |
| Repository size | 8.8 MB |

Commits in this submission sequence:

* `e96383f` — Phase 1–4 audit, faculty submission folder, README
* `421f782` — Phase 4 closeout: audit 13 recorded, multi-application tested
* `8291ca0` — F-11 improved classifier integration, six defects found by running it

No `.env`, checkpoint, raw dataset or database file is in the history. The
submission folder's derived parts (the Phase 4 document copy, the source copy,
the extracted diagrams, the test captures and the 843 MB runtime package) are
git-ignored rather than committed twice; the approved Phase 1–3 reports, the
diagram archive and all written documentation are committed.

---

## Verdict

# READY FOR FACULTY REVIEW

As a **Phase 1–4 submission** with the limitations in §8 stated in the open.

The reasons this is defensible:

* All 27 functional requirements accounted for — 26 implemented, 24 covered by
  automated tests, one (FR-27) honestly not implemented because its input
  dataset does not exist. All 19 non-functional requirements accounted for,
  with both columns reconciling exactly.
* 818 backend tests pass, zero fail, and the 78 skips are identified by suite
  and reason rather than counted as passes. Frontend 33 pass, lint clean,
  production build succeeds.
* One genuine real-world application collected and audited end to end through
  PostgreSQL with trained models, with the real policy and its verified hash
  included as primary evidence.
* A complete, licence-checked, SHA-256-verified runtime package, so the system
  can be run from the submission rather than merely read.
* The approved Phase 1–3 reports are included **unaltered**, and every gap
  between them and the delivered system is stated rather than smoothed over.
* The four documentation gaps identified previously are filled with derived or
  measured content — nothing fabricated.

What this submission nowhere claims: a measured system accuracy, that all five
verdicts have been seen on real applications, that the improved model beats the
baseline, that the gold set exists, or that Phase 5 has begun.
