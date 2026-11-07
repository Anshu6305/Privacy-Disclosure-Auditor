# Phase 4 — Implementation Closeout

**Date:** 2026-11-07 (F-13 added same day) · **Scope:** Phase 4 (Coding and Implementation) only.
Phase 5, academic validation and testing, is a separate phase and has not
started.

This is a closing statement, not a summary of the other reports. Each section
points at the document that holds the detail rather than restating it.
Nothing here is claimed that is not verifiable in the repository.

## 1. Milestones

| Milestone | Status |
| --- | --- |
| M1 Repository and environment | Complete, verified on two machines |
| M2 Database and schema | Complete, 16 tables, verified on PostgreSQL 16 |
| M3A Acquisition · M3B Persistence | Complete, PostgreSQL-verified |
| M4 Text processing | Complete. The tracker's "never run on a real policy" is **superseded**: F-08 to F-10 ran on the Spotify policy in audit 6 |
| M5 Baseline classifier | Complete, evaluated, rebuilt in M10 reproducing its figures exactly |
| M6 Improved models | **Partial.** F-12 trained in M11; the improved F-11 variant was never trained |
| M7 Verdict and evidence engine | Complete. The tracker's "not verified end to end" is **superseded** by audit 6 |
| M8 Backend integration | Complete, PostgreSQL-verified |
| M9 Frontend | Complete, 32 tests |
| M10 F-15 rules, M5 rebuild, F-12 workflow | Complete |
| M11 Model integration | Complete |

Detail: `docs/M8_REPORT.md` through `docs/M11_REPORT.md`, `docs/TEAM_TRACKER.md`.

## 2. Architecture and stack, as built

Three containers, as approved: `database`, `api`, `worker`
(`docker-compose.yml`). An audit is requested through the API, queued in the
database, and claimed by the worker one at a time under
`FOR UPDATE SKIP LOCKED` (design decision DD-2).

| Layer | Actual |
| --- | --- |
| Backend | Python 3.10–3.13, FastAPI 0.115.6, SQLAlchemy 2.0.36, Alembic 1.14.0 |
| Database | PostgreSQL 16, psycopg 3.2.3, schema at `0003_collection_event` |
| Text processing | spaCy 3.8.3 with `en_core_web_sm`, no fallback splitter by design |
| ML | scikit-learn 1.6.0 (F-11); torch 2.5.1 + transformers (F-12, F-18) |
| Frontend | React 18.3.1, React Router 6.28.0, Vite 5.4.11 |

## 3. Traceability

`docs/PHASE4_COMPLETION_AND_TRACEABILITY_REPORT.md` is the authoritative
mapping of FR-01 to FR-27, NFR-01 to NFR-19, GI-01 to GI-07, F-01 to F-34,
T1 to T9 and E1 to E11 onto code and tests, and
`docs/IMPLEMENTATION_TRACEABILITY.md` is updated per milestone. Both are
current. Two statements from them carry forward here:

* **F-13 (model variant binding) is implemented and verified** (C-88). The
  approved FR-13/F-13/DD-8 text was recovered from the Phase 2 SRS and
  Phase 3 SDD, which are not stored in this repository. One variant is
  bound per audit, resolved through F-34, recorded as three
  `model_version_id`s and bound at claim time from those ids; an unknown
  variant is rejected before work begins and there is no fallback.
  **FR-13's baseline-versus-improved comparison still cannot be run**,
  because the improved classifier has no trained checkpoint. See §8.
* **F-31 (gold-set evaluation) is blocked**: the gold set does not exist.

`docs/PHASE4_CONSISTENCY_LOG.md` holds 87 numbered findings, C-01 to C-87,
each recording a defect or a decision with its reasoning. It is the record of
what went wrong during Phase 4 and why, and is more useful to a reviewer than
this document.

## 4. Verified regression results

Last full run, 2026-11-07:

| Check | Result |
| --- | --- |
| Backend `pytest tests` | **756 passed, 78 skipped, 0 failed** (735 before F-13; 21 added) |
| `ruff check .` | clean |
| Frontend Vitest | 32 passed |
| `npm run lint` / `vite build` | clean / succeeds |
| PostgreSQL integration | 78 passed, 0 skips at head (2026-11-06, `privacy_auditor_m11_20261106_test`) |

The 78 skips in the backend run are the PostgreSQL suites, which skip without
`TEST_DATABASE_URL`. They are skips, not passes; they ran separately with
zero skips through `scripts/verify_migrations.sh`.

## 5. Real pilot

**Audit 6, `com.spotify.music`, completed.** 14 Data Safety categories:
**7 Consistent, 7 Undetermined**, 15 evidence records.
`uses_fixture_models` is **false** — every model was a trained checkpoint:

| Task | Model |
| --- | --- |
| classification | `tfidf-logistic-regression/classifier-baseline-v1` |
| span_extraction | `distilbert-base-uncased/span-extractor-v1` |
| alignment | `cross-encoder/nli-distilroberta-base` (zero-shot) |

This is one application. It establishes that the pipeline runs end to end on
genuine collected sources with real models; it establishes nothing about
accuracy, and the corpus holds one record.

Earlier audits are retained unaltered as historical evidence, including the
ones whose verdicts the corrections in C-86 and C-87 changed.

## 6. Known limitations

* **F-12 is inaccurate.** Exact-match F1 **0.1072**, overlapping-match F1
  **0.5658** on the held-out test split. Span boundaries are right roughly
  one time in ten; the model usually finds about the right region with the
  right value. It is not production-ready.
* **F-18 is zero-shot and not formally evaluated.** No gold set exists, so no
  metric can be reported. Observed behaviour: reliable on denials
  (contradiction 0.977 on a negated collection statement), weak on plain
  entailment (neutral 0.637 against entailment 0.354). The 300–500 labelled
  pairs decision D-01 planned for fine-tuning were never annotated.
* **Partial taxonomy mappings.** 16 of the 30 authored F-15 rules are
  partial. On the Spotify pilot *every* App activity judgement arrived
  through a partial rule. Since C-87 a partial mapping cannot carry a
  decisive contradiction; it can still carry decisive support, so a
  Consistent verdict may rest on a correspondence the rule table itself
  calls loose. That asymmetry is deliberate and recorded in C-87, with the
  measurement behind it.
* **F-11's improved variant has never been trained.** F-13 can bind it and
  correctly refuses when it is absent, but the baseline-versus-improved
  comparison FR-13 exists to enable has not been run. Training needs
  `distilbert-base-uncased`, which cannot be downloaded in the development
  environment; `ml/export_improved_bundle.py` prepares the Colab route F-12
  used, verified by extracting the bundle and running the trainer's dry run
  with the repository off the path.
* **F-34's sequential model loading is not implemented.** It requires one
  model per stage, released before the next; the pipeline holds all three
  for a run and has since M8. Pre-existing, recorded in C-88, not a defect
  introduced by F-13.
* **F-10's analysability thresholds are provisional** — chosen by this
  project, not an approved requirement.
* **Rare classes are not measurable**: Data Retention (n=7) and Do Not Track
  (n=4) in M5; 7 of 54 F-12 labels have fewer than 10 test spans.
* **No load or performance testing** has been done, and no frontend test runs
  against a live API.
* **Corpus of one.** One real application has been collected and audited.

The system is not error-free, not production-ready, and produces no legal or
compliance conclusion. Every report it generates states that scope itself.

## 7. Implementation completion is not validation

Phase 4 delivered a working system and the evidence that it runs. It did not
establish that its findings are correct.

What Phase 4 can support: the pipeline executes end to end on real collected
sources; verdicts follow the approved ALG-8 precedence; every evidence quote
is a verbatim slice of the stored policy, verified against the stored hash;
abstention propagates so uncertainty is reported rather than resolved.

What only **Phase 5** can establish: whether the verdicts are right. That
needs the annotated gold set F-31 requires, agreement measurement against
human judgement, and evaluation of F-18. None of it exists, and no result in
this phase should be read as accuracy.

## 8. Remaining work genuinely belonging to Phase 4

1. **Train the improved classifier.** F-13 is implemented; FR-13's purpose
   — comparing the two models on the same input — is not yet achievable,
   because one of the two models does not exist. Run
   `python ml/export_improved_bundle.py`, train on Colab, and bring
   `ml/checkpoints/improved_classifier` back. The frozen split, seed 20261105
   and evaluation module are preserved in the bundle, so the result is
   directly comparable to M5's 0.7489 / 0.7690. Until then, **FR-13 is
   implemented but unsatisfied**, and that is the honest statement.
2. **Two pilot audit reports are untracked** —
   `spotify_audit_5_report.json` and `spotify_audit_6_report.json`. Audit 6
   is the evidence §5 rests on. The team should decide whether to commit
   them; untracked, they can be lost.
3. **Two tracker rows are stale**, as §1 notes: M4 and M7 predate the pilot.

Everything else named in this document belongs to Phase 5 or to the
limitations that are being reported rather than fixed.

## 9. Closure position

**Phase 4 is implementation-complete.** Every approved endpoint, screen,
database entity and design function is now implemented and tested,
including F-13, and a real application has been audited end to end with
real models.

**One requirement is implemented but unsatisfied.** FR-13 asks that the two
classifier variants be comparable on the same input. The mechanism is built
and tested; the improved model has never been trained, so the comparison
has not been made. That is a missing artefact, not a missing function, and
it is stated as such rather than counted as complete.

Whether to close Phase 4 with FR-13 in that state, or to train the model
first, is a decision for the team and the faculty. This document records
the position; it does not make the call.
