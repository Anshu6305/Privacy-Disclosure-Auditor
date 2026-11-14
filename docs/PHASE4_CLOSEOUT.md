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
| M6 Improved models | Complete. F-12 trained in M11; the improved F-11 variant trained on a Colab T4, evaluated on the frozen split, registered as `f11-improved-v1` and run end to end. It is **not uniformly better than M5** — see §4a |
| M7 Verdict and evidence engine | Complete. The tracker's "not verified end to end" is **superseded** by audit 6 |
| M8 Backend integration | Complete, PostgreSQL-verified |
| M9 Frontend | Complete, 33 tests |
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
  **FR-13's baseline-versus-improved comparison can now be run**: the
  improved classifier is trained, evaluated on the same frozen split and
  registered, and an audit bound to it completes. The comparison of held-out
  metrics is in §4a.
* **F-31 (gold-set evaluation) is blocked**: the gold set does not exist.

`docs/PHASE4_CONSISTENCY_LOG.md` holds 92 numbered findings, C-01 to C-92,
each recording a defect or a decision with its reasoning. It is the record of
what went wrong during Phase 4 and why, and is more useful to a reviewer than
this document.

## 4. Verified regression results

Last full run, 2026-11-14:

| Check | Result |
| --- | --- |
| Backend `pytest tests -p no:warnings` | **812 passed, 78 skipped, 0 failed** (756 at F-13 close; 56 added across C-89 to C-97) |
| `ruff check .` | clean (ruff 0.8.4, the pinned version) |
| Frontend Vitest | 33 passed |
| `npm run lint` / `vite build` | clean / succeeds |
| PostgreSQL integration | 78 passed, 0 skips at head (2026-11-06, `privacy_auditor_m11_20261106_test`) |

The 78 skips in the backend run are the PostgreSQL suites, which skip without
`TEST_DATABASE_URL`. They are skips, not passes; they ran separately with
zero skips through `scripts/verify_migrations.sh`.

## 4a. FR-13: the two classifier variants on the same frozen split

Both models were evaluated on the identical policy-grouped split (seed
20261105, 80/17/18 policies, 541 test segments, 619 positive labels) through
the identical evaluation module, so this compares two models and not two
experiments. The improved variant's figures were re-derived on CPU from the
restored checkpoint with `--evaluate-only` and match the Colab run to four
decimal places on every reported metric.

| Held-out test metric | M5 baseline | F-11 improved |
| --- | --- | --- |
| Macro-F1 | **0.7489** | 0.6304 |
| Micro-F1 | 0.7690 | **0.7775** |
| Micro precision | 0.7462 | **0.8231** |
| Micro recall | **0.7932** | 0.7367 |
| Hamming loss | 0.0545 | **0.0482** |
| Subset accuracy | 0.5896 | **0.6765** |

**The improved model is not uniformly better, and must not be described as
"more accurate".** It wins on five of six aggregate measures, and on six of
the ten categories, but macro-F1 falls by 0.119 because it never predicts
Data Retention (n=7) or Do Not Track (n=4) at the 0.5 threshold — two zeroes
in an unweighted mean over ten classes — and User Access, Edit and Deletion
regresses to F1 0.538 from 0.774. Neither rare category has enough test
examples to be a reliable measurement in **either** model, so the baseline's
0.4286 and 0.8571 on them are not measurements either. The 0.5 threshold is
provisional and was not tuned; no threshold or epoch count was chosen from
test results.

FR-13 is therefore **satisfied as a mechanism and as a comparison**: both
variants are registered, bindable and evaluated on one split. Which model is
preferable depends on whether macro or micro performance matters for the
task, and this phase does not settle that.

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

**The same application, bound to the improved variant.** Run in-process
against SQLite on 2026-11-10, because PostgreSQL is not reachable from an
agent session: 629 segments, 3,386 practices, 611 alignment judgements, 14
verdicts (**6 Consistent, 8 Undetermined**), 16 evidence records,
`uses_fixture_models` false, classifier bound to `f11-improved-v1`. One
category moved from Consistent to Undetermined relative to audit 6's
baseline run. This is **not** a PostgreSQL pilot audit and is not recorded as
audit 7; it is evidence that the improved variant runs through the whole
pipeline on genuine sources.

**Only two of the five verdicts appear in any real-app run.** Audit 6 and the
improved-variant run both produce Consistent and Undetermined and nothing
else. Contradictory, In-policy-not-declared and Declared-not-in-policy are
verified by controlled fixtures only (81 verdict-engine tests). That
distinction is not a defect — it reflects what one manually collected
application happens to contain — but no real-app evidence exists for three of
the five outcomes, and none should be claimed.

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
* **F-11's improved variant predicts nothing for two categories.** It is
  trained, evaluated and registered, but at the 0.5 threshold it never
  predicts Data Retention or Do Not Track, so both score 0.0 and macro-F1 is
  below the baseline's (§4a). This is a reported limitation, not a defect to
  be tuned away before submission: lowering the threshold to produce
  predictions would be choosing an operating point from test results.
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

1. **Register the improved model in PostgreSQL.** The registration is
   written and its loader probe passes, but `scripts/register_models.py`
   must be run by the team: PostgreSQL runs in Docker Desktop on the team
   Mac and is not reachable from an agent session. Dry run first, then
   `--apply`. Until that is done the improved variant exists on disk and in
   the code but not in the pilot database, so `request_audit --variant
   improved` will refuse.
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

**FR-13 is now satisfied.** Both classifier variants are trained, evaluated
on one frozen split and registered, and an audit bound to the improved
variant completes end to end. The comparison it exists to enable has been
made and is in §4a; it does not show the improved model to be uniformly
better, and that result is reported as measured rather than as hoped.

**What remains unverified on PostgreSQL.** The improved model is registered
in `privacy_auditor_pilot` with 36 metric rows, and audit 9 for
`com.spotify.music` is queued there, composed with
`--model classification=f11-improved-v1 --model
span_extraction=f12-span-extractor-v1 --model alignment=f18-zeroshot-nli-v1`.
`--variant improved` cannot be used and should not be: the variant axis
belongs to the classifier, and F-12 and F-18 have no improved model (C-93).

Audit 9 did not complete, through two configuration defects rather than any
fault in the pipeline. The worker was first started against `privacy_auditor`
rather than the pilot database and claimed nothing (C-96); once pointed at
the pilot database it claimed audit 9 and failed it, because relative
`checkpoint_path` values were resolved against the working directory instead
of the checkout, so a worker started from `backend/` could not find a
checkpoint that was present (C-97). Both are fixed: the worker now names the
database it polls, and the repository root is derived from the package's own
location.

**Audit 9 is retained unaltered** as the record of that failure, consistent
with how audits 2 to 6 were preserved. A replacement audit with identical
provenance - same snapshot, same taxonomy mapping version, same three
`model_version` ids - is to be created on the team Mac:

    python scripts/request_audit.py com.spotify.music \
        --database privacy_auditor_pilot \
        --model classification=f11-improved-v1 \
        --model span_extraction=f12-span-extractor-v1 \
        --model alignment=f18-zeroshot-nli-v1 --apply

    cd backend
    POSTGRES_DB=privacy_auditor_pilot PYTHONPATH="..:$PWD" \
        ../.venv/bin/python -m app.worker.worker

The pilot database is published on that host's loopback only, so neither can
be run from an agent session. Until that audit reaches `completed`, the
improved variant's end-to-end run on PostgreSQL is **pending**; the
equivalent run on SQLite is recorded in §5.

Whether to close Phase 4 with FR-13 in that state, or to train the model
first, is a decision for the team and the faculty. This document records
the position; it does not make the call.

## 10. Audits 9 and 11, and what they record

Both failed, both are retained unaltered, and neither failure was in the
pipeline:

| Audit | Status | Cause |
| --- | --- | --- |
| 9 | `failed` | The improved checkpoint was sought at `backend/ml/checkpoints/improved_classifier`, because a relative `checkpoint_path` was resolved against the working directory rather than the checkout (C-97) |
| 11 | `failed` | The same, from a worker process started before the C-96/C-97 fixes and still holding the old modules in memory |

Audit 11 is the more useful record: it shows that editing a file does not
change a running Python process. The diagnostic is now in the worker's own
output — a worker on current code logs
`polling <host>:<port>/<database>; N audit(s) queued there` **before**
`worker started; one audit at a time`. A first line of `worker started` with
no `polling` line above it means the process predates C-96 and must be
restarted.

The repository-root fix was verified through the production path on
2026-11-14: cwd `backend/`, `build_bound_pipeline_factory()` with no
argument, `factory(session, audit_id)` → all three registered checkpoints
resolved to absolute project-root paths and loaded
(`ImprovedPracticeClassifier`, `SpanExtractor`, `ZeroShotAligner`), and the
improved classifier returned real scores. 12 targeted tests passed.

## 11. Demonstration procedure

Five minutes, on the team Mac, with Docker Desktop running.

1. **Database.** `docker compose up -d database`, then confirm
   `docker compose ps` shows `auditor_database` healthy.
2. **API and frontend.** `uvicorn app.main:app --reload` from `backend/`
   with the venv active, and `npm run dev` in `frontend/`. The SPA lists the
   collected application, its snapshot and its audit history from the API;
   nothing on screen is fabricated, and an unavailable capability renders as
   unavailable.
3. **Model provenance.** The system page shows the three registered
   `model_version` rows with their real identifiers and variants, and the
   improved classifier's stored metrics (test macro-F1 0.6304, micro-F1
   0.7775).
4. **A report.** Open audit 6 — completed, 14 verdicts, real models,
   `uses_fixture_models` false. Expand a category to show an evidence record
   whose quote is a verbatim slice of the stored policy at the recorded
   offsets, and an Undetermined verdict whose inconclusive record now carries
   the passage it abstained on (C-91).
5. **Honesty by construction.** `python scripts/request_audit.py
   com.spotify.music --variant improved` refuses with `variant_unavailable`
   and names the task that lacks the variant — no fallback, no report whose
   provenance names a model that never ran (C-93).

What not to claim in the demonstration: any accuracy figure beyond the
held-out metrics in §4a, any legal or compliance conclusion, and any
real-app evidence for Contradictory, In-policy-not-declared or
Declared-not-in-policy — those three are verified by controlled fixtures
only.
