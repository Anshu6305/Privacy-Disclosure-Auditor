# Cross-Source Privacy Disclosure Consistency Auditor for Android Applications

An Android application states what personal data it collects in two independent
places: the **Google Play Data Safety** section, which is a structured form, and
its **privacy policy**, which is prose. Nothing checks that the two agree.

This system compares them. It reads a stored Data Safety declaration and the
application's privacy policy, determines what the policy says about each
privacy-practice category using NLP and three ML components, maps both sources
into one category vocabulary, and issues one of five verdicts per Data Safety
category — with every finding anchored to the exact characters of the policy
that produced it.

It compares two public disclosures. It does **not** inspect the application
binary, does not observe runtime traffic, and makes no legal or compliance
judgement. Every report it generates says so itself.

B.Tech major project, School of Computer Engineering, KIIT — Phase 4
(implementation).

---

## 1. Features

* **Application search** over the stored corpus by name or package identifier.
* **Asynchronous audits** — a request returns a job id; a worker processes one
  audit at a time.
* **Policy text processing** — extraction, sentence segmentation with character
  offsets preserved, and an analysability check that fails loudly rather than
  analysing an error page.
* **Privacy-practice classification** over the ten OPP-115 categories, with two
  interchangeable models.
* **Data-type and purpose extraction** as labelled spans.
* **Semantic alignment** between a policy statement and a declared claim.
* **Versioned taxonomy mapping** from OPP-115 categories to Data Safety
  categories, with partial mappings flagged as partial.
* **Five-outcome verdict engine** — Consistent, Declared-not-in-policy,
  In-policy-not-declared, Contradictory, Undetermined.
* **Evidence records** — a verbatim quote with character offsets, a
  system-generated absence statement, or an abstention with its reason.
* **Audit history** per application and **comparison** of two audits.
* **Abstention as a first-class outcome** — low confidence yields Undetermined
  with a stated cause, never a manufactured finding.

## 2. Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 18.3.1, React Router 6.28.0, Vite 5.4.11 |
| Backend | Python 3.12, FastAPI 0.115.6, Uvicorn |
| Database | PostgreSQL 16, SQLAlchemy 2.0.36, Alembic 1.14.0, psycopg 3.2.3 |
| Classical ML | scikit-learn 1.6.0, NumPy, SciPy |
| Neural ML | PyTorch 2.5.1, Hugging Face Transformers 4.47.1 |
| NLP | spaCy 3.8.3 with `en_core_web_sm` |
| Testing | pytest, Vitest 2, ESLint 8.57.1, Ruff 0.8.4 |
| Deployment | Docker Compose — three services |

## 3. Architecture

A layered monolith deployed as three containers: `database`, `api` (which also
serves the built SPA) and `worker`. **The job queue is the `audit_run` table**,
claimed with `FOR UPDATE SKIP LOCKED` — there is no message broker. One audit
runs at a time per worker, because the memory plan assumes one model set
resident.

```
Data Safety declaration ──────────────────────────► normalise ─┐
                                                               │
privacy policy ─► extract ─► segment ─► classify ─► spans ─► map ─► align ─┤
                                                                           ▼
                                        confidence gate ─► verdict + evidence ─► report
```

Each audit records the three model versions it used, the taxonomy mapping
version and the thresholds, so a report is reproducible and can never name a
model that did not run.

## 4. Directory structure

```
Major Project/
├── README.md                 this file
├── FINAL_PROJECT_AUDIT.md    organisation, assets, test results, git status
├── CLAUDE.md                 development protocol for contributors
├── docker-compose.yml        three services: database, api, worker
├── pyproject.toml            ruff and pytest configuration
├── myapp.json                manual-collection template
├── .env.example              environment template; copy to .env
│
├── acquisition/              disclosure acquisition, isolated from analysis
├── analysis/                 text processing, models, mapping, verdict engine
│   ├── text/                 extraction, segmentation, analysability
│   ├── models/               classifier and span-extractor interfaces
│   ├── mapping/              OPP-115 → Data Safety rules, mapping_v1.json
│   ├── alignment/            NLI alignment
│   ├── confidence/           F-14 abstention gate
│   └── verdict/              ALG-8 verdict engine, evidence records
├── backend/                  FastAPI application
│   ├── app/api/              routes and schemas
│   ├── app/db/               SQLAlchemy models and repositories
│   ├── app/services/         audit service, pipeline, model registry
│   ├── app/worker/           the queue worker
│   ├── migrations/           Alembic revisions (0001 frozen)
│   └── requirements*.txt     runtime, dev and ML dependency sets
├── frontend/                 React + Vite single-page application
├── ml/                       training, evaluation and inference backends
│   ├── checkpoints/          four trained model checkpoints (832 MB)
│   ├── data/                 OPP-115 loading and split logic
│   ├── runs/                 model metrics and Colab training bundles
│   └── training/             the fine-tuning loops
├── data/                     corpora — see data/README.md
│   ├── corpus/               collected applications and their policy documents
│   ├── raw/                  OPP-115 (obtained locally, never committed)
│   ├── processed/            derived training files
│   ├── policies/             POLICY_STORAGE_DIR; Docker volume mount
│   ├── goldset/              reserved for FR-27; empty, no gold set exists
│   └── taxonomy/             reserved; the active mapping lives in analysis/
├── scripts/                  operational command-line tooling
├── tests/                    unit, api, integration and ml suites
├── notebooks/                Colab training notebooks
├── docs/                     engineering records and milestone reports
└── artifacts/
    ├── audit_exports/        real audit reports, the collected policy
    └── test_evidence/        PostgreSQL verification logs (local only)
```

## 5. Component responsibilities

**Backend** (`backend/app/`) — thirteen HTTP routes: two health checks,
acquisition status, application search and detail, source links, audit request,
audit status, report, per-category evidence, per-application history, audit
comparison and model provenance. Refusals are typed and explanatory: an unknown
application, a missing collection event or an unavailable model variant each
return a named reason rather than a generic error.

**Worker** (`backend/app/worker/`) — claims one queued audit, builds a pipeline
bound to that audit's recorded model versions, runs the pipeline stages and
commits. A failure is terminal with a stated reason; the worker survives and
the queue is not wedged.

**Frontend** (`frontend/src/`) — seven pages: search, application, audit
status, report, history, compare and a system page showing registered models.
Every page renders only API data. A report produced with fixture models
declares itself; an unavailable capability renders as unavailable rather than
as a plausible result.

**Analysis** (`analysis/`) — the pipeline logic, with no FastAPI and no
database imports, so each stage is testable on its own.

**ML** (`ml/`) —

| Component | Model | Held-out test result |
|---|---|---|
| F-11 baseline | TF-IDF + one-vs-rest logistic regression | macro-F1 **0.7489**, micro-F1 0.7690 |
| F-11 improved | `distilbert-base-uncased`, fine-tuned 3 epochs | macro-F1 **0.6304**, micro-F1 **0.7775** |
| F-12 span extractor | DistilBERT token classification, 55 BIO labels | exact-match F1 **0.1072**, overlap F1 0.5658 |
| F-18 aligner | `cross-encoder/nli-distilroberta-base`, zero-shot | verified on all three outcomes, not fine-tuned |

Both classifiers were evaluated on the same policy-grouped split (seed
20261105; 80/17/18 policies = 2634/617/541 segments). **The improved classifier
is not uniformly better**: it wins micro-F1 (0.7775 vs 0.7690), precision,
Hamming loss (0.0482 vs 0.0545) and subset accuracy (0.6765 vs 0.5896), and
loses macro-F1 because at the 0.5 threshold it never predicts Data Retention
(7 test examples) or Do Not Track (4). The span extractor is a working
prototype, not a production extraction model.

## 6. Database

PostgreSQL 16, 16 tables, three Alembic revisions (`0001_baseline_schema` is
frozen; changes are additive revisions).

```
application · disclosure_snapshot · declared_practice · policy_segment
extracted_practice · extracted_span · alignment_judgement
verdict · evidence_record · audit_run
model_version · evaluation_run · evaluation_metric
taxonomy_mapping_version · taxonomy_mapping_entry · gold_annotation
```

Two constraints enforce a distinction that matters: `verdict.verdict_value` is
restricted to the five system outcomes, and `gold_annotation.label` to four
ground-truth labels — so **Undetermined cannot be written into a gold set**. A
system abstention is not an annotation.

Raw policy documents live on the filesystem with their SHA-256 in the database;
the segmented text used for quoting is in the database.

**Protected databases — never drop, reset or truncate:** `privacy_auditor`,
`privacy_auditor_test`, `privacy_auditor_frozen_20261105_test`. The pilot data
used below is in `privacy_auditor_pilot`.

## 7. Prerequisites

* **Python 3.12** — not 3.14; the dependency set does not build on it
* Node.js 20+ and npm
* Docker Desktop, for PostgreSQL 16
* A GPU is **not** needed. Inference runs on CPU; the two fine-tunes used a
  free Colab T4 and their checkpoints are reused

```bash
python3.12 --version          # must report 3.12.x
```

## 8. Environment setup

```bash
cd "/Users/anshu/Documents/Major Project"

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
pip install -r backend/requirements-ml.txt      # torch + transformers, large
python -m spacy download en_core_web_sm

cp .env.example .env
# edit .env and set POSTGRES_PASSWORD

cd frontend && npm install && cd ..
```

`POSTGRES_DB` in `.env` selects the database the API and worker use. The pilot
data is in `privacy_auditor_pilot`, so the commands below set it explicitly on
the command line rather than editing `.env`.

Model checkpoints are in `ml/checkpoints/` (832 MB, four models) and are not
committed. The OPP-115 corpus is **not** redistributed — `data/README.md` gives
the obtain-and-verify procedure; it is needed only to retrain, not to run.

## 9. Database startup and migrations

```bash
docker compose up -d database
docker compose ps                    # the database service should be healthy

cd backend
POSTGRES_DB=privacy_auditor_pilot ../.venv/bin/alembic upgrade head
cd ..
```

To emit the DDL without a running server (useful for review):

```bash
cd backend && POSTGRES_PASSWORD=offline-dummy \
    ../.venv/bin/alembic upgrade 0001:0003 --sql
```

## 10. Running the system

**Backend API** — first terminal:

```bash
cd backend
POSTGRES_DB=privacy_auditor_pilot PYTHONPATH="..:$PWD" \
    ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Check it: `curl http://127.0.0.1:8000/api/health`

**Worker** — second terminal, needed only to run a *new* audit; completed
audits are served by the API alone:

```bash
cd backend
POSTGRES_DB=privacy_auditor_pilot PYTHONPATH="..:$PWD" \
    ../.venv/bin/python -m app.worker.worker
```

Its first line names the database it is polling and how many audits are queued
there. If that line is missing, the process is running stale code — restart it.

**Frontend** — third terminal:

```bash
cd frontend
npm run dev                          # http://localhost:5173
```

Vite proxies `/api` to `http://127.0.0.1:8000`, so the same frontend code works
in development and inside the container, where FastAPI serves the built SPA.

**All three in Docker** (the worker image deliberately omits the ML dependency
set, so it can claim an audit but not complete one — see §12):

```bash
docker compose up -d
```

## 11. Viewing the Spotify audit

1. Open **http://localhost:5173**.
2. Search for `Spotify` or `com.spotify.music`. The application appears with
   its developer and package identifier.
3. Open it. The application page shows the collection event — when it was
   collected, its source URLs, and that both the declaration and the policy are
   present.
4. Open **History**. Completed audits are listed with the models each used.
5. Open **audit 13** — completed, 14 verdicts (6 Consistent, 8 Undetermined),
   18 evidence records, run on the improved classifier.
6. On the report, each row is one Data Safety category with its verdict and
   confidence. **Expand a row** to see the evidence: a verbatim quotation with
   its character offsets for a finding, or the passage and the reason for an
   abstention.

Earlier exported reports are in `artifacts/audit_exports/` if the UI is not
running.

From the command line, a new audit with explicit model versions:

```bash
# dry run — nothing is written without --apply
python scripts/request_audit.py com.spotify.music \
    --database privacy_auditor_pilot \
    --model classification=f11-improved-v1 \
    --model span_extraction=f12-span-extractor-v1 \
    --model alignment=f18-zeroshot-nli-v1
```

`--variant improved` is deliberately refused, naming the task that has no
improved model: the variant axis belongs to the classifier, and running a
different model than the one a report names would make the report untrue.

## 12. Tests and checks

```bash
pytest tests -p no:warnings          # 818 passed, 78 skipped
ruff check .                         # All checks passed

cd frontend
npm test                             # 33 passed in 7 files
npm run lint                         # clean
npm run build                        # production build
```

**The 78 skips are skips, not passes.** Every one is a PostgreSQL integration
test gated on `TEST_DATABASE_URL`, which the suite refuses to guess. Run them
through the project's safe procedure, which creates a disposable database and
never touches a protected one:

```bash
./scripts/verify_migrations.sh
```

Its output is kept in `artifacts/test_evidence/`.

## 13. Known limitations

* **One application collected** — `com.spotify.music`. The pipeline is generic
  over applications and that is unit-tested; the corpus is not.
* **No gold set**, so FR-27 (offline evaluation) is not implemented and **the
  system's end-to-end verdict accuracy has never been measured**. No accuracy
  figure for the auditor appears anywhere in this project.
* **Three of the five verdicts have never occurred on real data** —
  Contradictory, In-policy-not-declared and Declared-not-in-policy are
  exercised by controlled tests only.
* **NFR-01, NFR-02, NFR-04 and NFR-19** (latency, analysis time, concurrency,
  corpus capacity) were never measured.
* **F-34 sequential model loading is not implemented**; all three models stay
  resident for a run.
* **The Docker worker image omits the ML dependency set** by design, to keep
  the image small. It can claim an audit but not complete one; the verified
  end-to-end path is the local virtual environment in §10.
* Out of scope and never claimed: APK or runtime-traffic analysis, iOS,
  non-English policies, authentication, legal or compliance conclusions.

## 14. Further documentation

| File | Contents |
|---|---|
| `FINAL_PROJECT_AUDIT.md` | Organisation, preserved assets, test results, git status |
| `docs/PHASE4_CLOSEOUT.md` | Implementation closure position and the real pilot results |
| `docs/PHASE4_CONSISTENCY_LOG.md` | C-01 onwards: every defect found and how it was corrected |
| `docs/IMPLEMENTATION_TRACEABILITY.md` | Requirement → design → code → test |
| `docs/PHASE4_MASTER_PLAN.md` | F-01 to F-34 module mapping and milestone order |
| `docs/TEAM_TRACKER.md` | Milestone status; what does not exist yet |
| `docs/DEV_LOG.md` | Dated record of what was built and verified |
| `data/README.md` | How to obtain and verify the datasets |
