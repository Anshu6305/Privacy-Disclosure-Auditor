# Cross-Source Privacy Disclosure Consistency Auditor for Android Applications

B.Tech major project · Kalinga Institute of Industrial Technology · six-member team
Phase 1–4 submission. Phase 5 (academic validation and testing) is a separate phase and has not begun.

---

## 1. Abstract

An Android application tells you what data it collects in two different places.
The Google Play Data Safety section is a structured form the developer fills in.
The privacy policy is prose the developer writes. Nothing checks that the two
agree.

This system compares them. It reads a stored Data Safety declaration and the
application's published privacy policy, works out what the policy actually says
about each data-practice category, maps both sources into one category set, and
reports where they agree, where they disagree, and where it cannot tell. Every
finding is anchored to the exact characters of the policy that produced it.

It is a comparison of two public disclosures. It does not inspect the
application binary, it does not observe runtime traffic, and it does not decide
whether an application is lawful.

## 2. Problem statement and objectives

A reader who wants to know whether an app's two disclosures agree has to read
both and compare them by hand, for every data category. That is slow, and it is
the kind of comparison that is easy to get wrong.

The seven approved implementation goals (Phase 2, GI-01 to GI-07):

1. **GI-01** Automate a comparison that is currently manual.
2. **GI-02** Apply NLP to unstructured privacy-policy text.
3. **GI-03** Detect inconsistency between two sources of disclosure.
4. **GI-04** Make every finding traceable to the source text that produced it.
5. **GI-05** Measure a baseline model against an improved model on one split.
6. **GI-06** Build a usable full-stack system, not a notebook.
7. **GI-07** Keep the system honest about what it does not know.

GI-07 is the one that shaped the most code: the system abstains rather than
guessing, and says so.

## 3. Main features

* **Application search** over the stored corpus by name or package identifier.
* **Audit request** per application, queued and processed asynchronously.
* **Policy text processing** — extraction, sentence segmentation with character
  offsets preserved, and an analysability check that fails loudly rather than
  analysing a 404 page.
* **Privacy-practice classification** over the ten OPP-115 categories, with two
  interchangeable models (a TF-IDF baseline and a fine-tuned DistilBERT).
* **Data-type and purpose extraction** as labelled spans.
* **Semantic alignment** between a policy statement and a declared claim, using
  a zero-shot NLI model.
* **Taxonomy mapping** from OPP-115 categories to Play Data Safety categories,
  configurable and versioned, with partial mappings flagged as partial.
* **Five-outcome verdict engine** — Consistent, Declared-not-in-policy,
  In-policy-not-declared, Contradictory, Undetermined.
* **Evidence records** — a verbatim quote with its character offsets, or a
  system-generated absence statement, or an abstention with its reason.
* **Audit history and comparison** of two audits of the same application.
* **Abstention everywhere** — low confidence produces Undetermined with a
  stated cause, never a manufactured finding.

## 4. Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 18.3.1, Vite 5.4.11 |
| Backend | Python 3.12, FastAPI 0.115.6, Uvicorn |
| Database | PostgreSQL 16, SQLAlchemy 2.0.36, Alembic 1.14.0, psycopg 3.2.3 |
| Classical ML | scikit-learn 1.6.0, NumPy, SciPy |
| Neural ML | PyTorch 2.5.1, Hugging Face Transformers 4.47.1 |
| NLP | spaCy 3.8.3 with `en_core_web_sm` (pinned) |
| Testing | pytest, Vitest, ESLint, Ruff |
| Deployment | Docker Compose — three containers |

No microservices, vector database, orchestration platform, agent framework or
retrieval-augmented generation. Phase 1 excluded them and nothing since has
justified adding them.

## 5. Architecture and workflow

A layered monolith deployed as three containers on one host: `database`, `api`
(which also serves the built single-page application) and `worker`. The job
queue is the `audit_run` table, claimed with `FOR UPDATE SKIP LOCKED`. There is
no message broker.

```
Data Safety declaration ─┐
                         ├─► normalise ─┐
Privacy policy ─► extract ─► segment ─► classify ─► extract spans ─┤
                                                                   ├─► map to DS categories
                                                                   ├─► align (NLI)
                                                                   ├─► confidence gate
                                                                   └─► verdict + evidence ─► report
```

One audit at a time per worker (design decision DD-2): the memory plan assumes
one model set resident on an 8 GB machine, so audits queue rather than compete.

Each audit records the three model versions it used, the taxonomy mapping
version and the thresholds, so a report can be reproduced and can never name a
model that did not run.

## 6. ML components and their roles

| Component | Role | Model | Measured performance |
|---|---|---|---|
| F-11 baseline classifier | Multi-label privacy-practice classification over 10 OPP-115 categories | TF-IDF + one-vs-rest logistic regression | Test macro-F1 **0.7489**, micro-F1 0.7690 |
| F-11 improved classifier | The same task, encoder-based | `distilbert-base-uncased`, fine-tuned 3 epochs on a Colab T4 | Test macro-F1 **0.6304**, micro-F1 **0.7775** |
| F-12 span extractor | Data-type and purpose spans | DistilBERT token classification, 55 BIO labels | Exact-match F1 **0.1072**, overlap F1 0.5658 |
| F-18 aligner | Does this policy statement support, contradict or not address this declared claim | `cross-encoder/nli-distilroberta-base`, **zero-shot**, not fine-tuned | Verified on all three outcomes; weak on plain entailment |

Both classifiers were evaluated on the **same** policy-grouped split with seed
20261105, so the comparison is between two models and not two experiments.

**The improved classifier is not uniformly better than the baseline.** It wins
micro-F1, precision, Hamming loss and subset accuracy; it loses macro-F1 by
0.119, because at the 0.5 threshold it never predicts Data Retention (7 positive
test examples) or Do Not Track (4). Neither category has enough test examples to
be a reliable measurement in either model. Thresholds are provisional and were
not tuned on the held-out split.

The span extractor is a **working prototype**: it usually finds roughly the
right region with the right value, and gets exact boundaries about one time in
ten. The confidence gate carries that uncertainty into Undetermined verdicts
rather than hiding it.

OPP-115 is **training data for practice classification**. It is not a
cross-source evaluation set, and the system's end-to-end verdict accuracy has
not been measured — see §16.

## 7. Database overview

PostgreSQL 16, 16 tables, three migrations
(`0001_baseline_schema`, `0002_pattern_ops_search_indexes`,
`0003_collection_event_snapshot`). `0001` is frozen; schema changes are additive
revisions.

Principal entities: `application`, `disclosure_snapshot` (one row per collection
event, carrying the policy path and its SHA-256), `declared_practice`,
`policy_segment`, `extracted_practice`, `alignment_judgement`, `verdict`,
`evidence_record`, `audit_run`, `model_version`, `evaluation_run`,
`evaluation_metric`, `taxonomy_mapping_version`, `taxonomy_mapping_entry`,
`gold_annotation`.

Two constraints are worth knowing about, because they enforce an academic
distinction rather than a technical one: `verdict.verdict_value` is restricted
to the five system outcomes, and `gold_annotation.label` is restricted to the
four ground-truth labels — so **Undetermined cannot be written into a gold set**.
A system abstention is not an annotation.

Raw policy documents live on the filesystem with their hash in the database.
The segmented text needed for quoting is in the database, so the pipeline never
depends on the raw file being present.

## 8. Installation prerequisites

* **Python 3.12.** Not 3.14 — the dependency set does not build on it.
* Node.js 20 or newer, and npm.
* Docker Desktop, for PostgreSQL 16.
* About 50 GB free disk if you train models; far less to run the system.
* A GPU is **not** needed to run an audit. The two fine-tunes were done on a
  free Colab T4 and their checkpoints are reused.

```bash
python3 --version          # must report 3.12.x
brew install python@3.12   # macOS, if it does not
```

## 9. Environment configuration

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
python -m spacy download en_core_web_sm

cp .env.example .env
# then edit .env and set POSTGRES_PASSWORD to a local password
```

`.env` is never committed. `POSTGRES_DB` in `.env` selects the database the API
and worker use; the maintainer scripts default to `privacy_auditor_pilot`.

**Assets that are not in the repository, and where they come from:**

| Asset | Where it comes from |
|---|---|
| OPP-115 corpus | `data/README.md`. Released for research and teaching; not ours to redistribute. Verify with `python ml/data/verify_opp115.py --write-manifest` |
| Model checkpoints (`ml/checkpoints/`) | Rebuild the baseline with `python ml/train_baseline_classifier.py`; the two fine-tunes run on Colab via `python ml/export_improved_bundle.py` and `python ml/export_f12_bundle.py` |
| Collected application corpus (`data/corpus/`) | Collected with `python scripts/manual_collect.py`; see `myapp.json` for the template |
| ML dependencies for neural inference | `pip install -r backend/requirements-ml.txt` (about 2 GB) |

## 10. Database startup and migrations

```bash
docker compose up -d database
docker compose ps                     # auditor_database should report healthy

cd backend
POSTGRES_DB=privacy_auditor_pilot ../.venv/bin/alembic upgrade head
cd ..
```

To see the DDL without a running server:

```bash
cd backend && POSTGRES_PASSWORD=offline-dummy alembic upgrade 0001:0003 --sql
```

The team's safe verification procedure, which uses a disposable database and
never touches a protected one, is `scripts/verify_migrations.sh`.

**Protected databases — never drop, reset or truncate these:**
`privacy_auditor`, `privacy_auditor_test`, `privacy_auditor_frozen_20261105_test`.

## 11. Backend startup

The whole stack in Docker, as the compose file defines it:

```bash
docker compose up --build
```

Or the API alone against the pilot database, which is the path used for the
demonstration:

```bash
cd backend
POSTGRES_DB=privacy_auditor_pilot PYTHONPATH="..:$PWD" \
    ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health check: `curl http://127.0.0.1:8000/api/health`

The worker is a separate process. It needs the neural dependencies, so run it
from the virtual environment rather than the container image:

```bash
cd backend
POSTGRES_DB=privacy_auditor_pilot PYTHONPATH="..:$PWD" \
    ../.venv/bin/python -m app.worker.worker
```

Its first line names the database it is polling and how many audits are queued
there. If that line is missing, the process is running stale code — restart it.

## 12. Frontend startup

```bash
cd frontend
npm install        # first time only
npm run dev        # http://localhost:5173
```

Vite proxies `/api` to `http://127.0.0.1:8000`, so the frontend code calls
relative paths and the same code works in development and inside the container,
where FastAPI serves the built SPA itself.

## 13. Searching for an application and running an audit

In the interface: search by name or package identifier, open the application,
and request an audit. The audit is queued and the worker claims it; the status
page polls until it reaches a terminal state.

From the command line, which is how a Corpus Maintainer compares two models
(end users never choose a model variant):

```bash
# Dry run first — nothing is written without --apply
python scripts/request_audit.py com.spotify.music \
    --database privacy_auditor_pilot \
    --model classification=f11-improved-v1 \
    --model span_extraction=f12-span-extractor-v1 \
    --model alignment=f18-zeroshot-nli-v1

# Then the same command with --apply
```

`--variant improved` is refused, and the refusal names the task that has no
improved model. That is deliberate: the variant axis belongs to the classifier,
and running a different model than the one a report names would make the report
untrue.

## 14. Where reports and audit history are displayed

| Screen | Shows |
|---|---|
| Search | matching applications by name or package |
| Application | the stored snapshot, its collection date and source links |
| Audit status | a queued or running audit, polled to completion |
| Report | one row per Data Safety category with its verdict and confidence; expanding a row shows the evidence |
| History | every audit of that application, with its models |
| Compare | two audits of the same application, side by side |
| System | the registered model versions, their metrics and the active taxonomy mapping |

Every report carries its scope sentence, and a report produced with fixture
models says so rather than passing as real.

## 15. Testing evidence

```bash
pytest tests -p no:warnings     # 818 passed, 78 skipped, 0 failed
pytest tests/unit               # fast, SQLite in memory, no services
pytest -m integration           # requires a running PostgreSQL
ruff check .                    # clean

cd frontend && npm test         # 33 passed
cd frontend && npm run lint     # clean
cd frontend && npm run build    # succeeds
```

**The 78 skips are skips, not passes.** They are the PostgreSQL integration
suites, which refuse to guess a database and skip when `TEST_DATABASE_URL` is
unset. The team runs them separately through `scripts/verify_migrations.sh`;
the most recent logs are in `FINAL_FACULTY_SUBMISSION/05_Testing_Evidence/`.

Raw output for every check above, the model metric files, the real audit reports
and the collected policy are in
`FINAL_FACULTY_SUBMISSION/05_Testing_Evidence/`.

## 16. Known limitations and project boundaries

These are stated plainly because GI-07 asks for it, and because a reviewer
should not have to find them.

**What has actually been validated**

* **One real application.** `com.spotify.music`, manually collected, 19 Data
  Safety entries, policy hash-verified. The design expected a corpus of 300–500
  applications; one has been collected. The pipeline is generic and
  multi-application capability is unit-tested, but the corpus is one application.
* **Three of the five verdicts have never occurred on real data.**
  Contradictory, In-policy-not-declared and Declared-not-in-policy are exercised
  by 81 controlled verdict-engine tests only. The real audit produced Consistent
  and Undetermined.
* **No gold set exists**, so FR-27 (offline evaluation) is not implemented and
  **the system's end-to-end accuracy has never been measured**. No accuracy
  percentage for the auditor appears anywhere in this project, because none
  would be defensible.

**What is implemented but unmeasured or partial**

* NFR-01 (report retrieval time), NFR-02 (analysis completion time), NFR-04
  (five concurrent requests) and NFR-19 (corpus capacity ~1,000) were never
  timed or load-tested.
* F-34's sequential model loading is not implemented: all three models stay
  resident for a run.
* Live retrieval (FR-06) is implemented and **disabled**; it has only been
  exercised against recorded responses, never the live Play Store.
* The Docker worker image deliberately omits the 2 GB neural dependency set, so
  it can claim an audit but not complete one. The verified run path is the local
  virtual environment.

**Outside the approved scope, and never claimed**

No Android binary or runtime-traffic analysis. No iOS. No non-English policies.
No user accounts or authentication. **No legal or regulatory compliance
judgement**, and no statement that an application is malicious or compliant.
Every report says so itself.

## 17. Team contributions

Phase 3 §13.2 assigns six roles. The member names are placeholders in the
approved documents and are **deliberately left as placeholders here** — they
should be filled in by the team, not inferred.

| Role | Member | Responsibility | Owns |
|---|---|---|---|
| R1 | _[Member 1]_ | Design coordination and cross-source alignment | F-15 to F-18, the taxonomy mapping artefact |
| R2 | _[Member 2]_ | Data engineering and corpus collection | F-01 to F-07, the Play Store corpus |
| R3 | _[Member 3]_ | NLP and classification | F-08 to F-14 |
| R4 | _[Member 4]_ | Backend and integration | F-23, F-32 to F-34, endpoints E1 to E11 |
| R5 | _[Member 5]_ | Database and persistence | 16 tables, migrations, F-28 to F-30 |
| R6 | _[Member 6]_ | Frontend and evaluation | F-24 to F-27, F-31, screens S1 to S7 |

Per-task status is in `docs/TEAM_TRACKER.md`.

---

## Documentation

| File | Contents |
|---|---|
| `FINAL_SUBMISSION_AUDIT.md` | Cleanup, cross-phase consistency, full FR/NFR traceability, faculty checklist, final verdict |
| `docs/PHASE4_CLOSEOUT.md` | Phase 4 closure position, model comparison, real pilot results, demonstration procedure |
| `docs/PHASE4_CONSISTENCY_LOG.md` | C-01 to C-99: every point where implementation met the approved design, and every defect found |
| `docs/IMPLEMENTATION_TRACEABILITY.md` | Requirement → design → code → test |
| `docs/PHASE4_MASTER_PLAN.md` | The approved implementation plan, F-01 to F-34 |
| `docs/PHASE4_DECISION_TABLE.md` | Open design decisions, D-1 onwards |
| `docs/DEV_LOG.md` | Dated record of what was built and verified |
| `docs/REQUIREMENT_CHANGE_LOG.md` | Any deviation from the approved SRS, with justification |

The approved Phase 1, 2 and 3 reports and the Phase 3 diagram set are in
`FINAL_FACULTY_SUBMISSION/`.
