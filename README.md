# Cross-Source Privacy Disclosure Consistency Auditor for Android Applications

A software system that compares what an Android application **declares** in its
Google Play Data Safety section against what its **privacy policy** says, and
reports where the two disclosures disagree — with the exact policy text as
evidence.

B.Tech Computer Science and Engineering major project (5 credits)
Kalinga Institute of Industrial Technology, Bhubaneswar

| | |
|---|---|
| Faculty Guide | _[to be filled in]_ |
| Team | _[Member 1]_, _[Member 2]_, _[Member 3]_, _[Member 4]_, _[Member 5]_, _[Member 6]_ |
| Phase | 4 — Coding and Implementation |

---

## Scope of this system

This tool reports **disclosure inconsistency between two sources**. That is the
whole claim and the limit of it.

The system does **not** determine whether an application is lawful, whether it
violates any regulation, whether a developer acted deliberately, or whether an
application is malicious. An inconsistency between a Data Safety declaration
and a privacy policy has many innocent explanations — an outdated policy, a
third-party SDK documented in one place and not the other, ambiguous wording, or
a mistake. The output is a starting point for a human reader, not a judgement.

Every finding is shown with the verbatim policy text it came from. The system
never generates, paraphrases or summarises evidence.

## Verdicts

For each Data Safety category the system produces one of five outcomes:

| Verdict | Meaning |
|---|---|
| Consistent | Both sources agree, or neither source mentions the category |
| Declared-not-in-policy | Declared in Data Safety, not found in the policy |
| In-policy-not-declared | Described in the policy, not declared in Data Safety |
| Contradictory | The two sources make opposing statements |
| Undetermined | The system is not confident enough to decide |

**Undetermined is an abstention, not a finding.** It is produced by the system
when confidence is below threshold; it is never a human annotation label. The
gold set uses only the first four labels.

## Architecture

Layered monolith, three containers on one host.

```
React + Vite SPA  ──HTTP/JSON──▶  FastAPI  ──▶  PostgreSQL
                                     │              ▲
                                     │ job queue    │
                                     ▼              │
                             Background worker ─────┘
                                     │
                                     ▼
                     analysis/  (text → ML/NLP → mapping → verdict)
```

`analysis/` has no dependency on FastAPI or on the database layer. It is plain
Python that takes text and returns structured results, so it can be tested and
evaluated on its own.

## Repository layout

```
backend/      FastAPI application, database models, services, worker
analysis/     Text processing, ML/NLP models, taxonomy mapping, verdict engine
acquisition/  Data Safety and privacy policy retrieval, provenance recording
ml/           Training, evaluation and dataset verification scripts
frontend/     React + Vite single-page application
tests/        unit / api / ml / integration
docs/         Plan, traceability, logs
data/         Datasets and corpora — never committed, see data/README.md
```

## Setup

Requires Python 3.10+, Node 18+, Docker Desktop and PostgreSQL 15+.

```bash
# 1. Backend environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# 2. Configuration
cp .env.example .env
# edit .env and set a local database password

# 3. Datasets — see data/README.md, nothing is downloaded automatically
python ml/data/verify_opp115.py

# 4. Frontend
cd frontend && npm install && cd ..

# 5. Run the stack
docker compose up --build
```

The virtual environment and `node_modules` are not committed. Each team member
creates them locally.

## Tests

```bash
pytest                      # all tests
pytest tests/unit           # fast, no database required
pytest -m integration       # requires a running PostgreSQL
```

Unit tests use SQLite in memory and require no services. Integration tests
require PostgreSQL and are marked so they can be skipped.

## Documentation

| File | Contents |
|---|---|
| `docs/PHASE4_MASTER_PLAN.md` | The approved implementation plan |
| `docs/IMPLEMENTATION_TRACEABILITY.md` | Requirement → design → code → test, with honest status |
| `docs/PHASE4_CONSISTENCY_LOG.md` | Every point where implementation met the approved design |
| `docs/REQUIREMENT_CHANGE_LOG.md` | Any deviation from the approved SRS, with justification |
| `docs/DEV_LOG.md` | Dated record of what was built and verified |
| `docs/TEAM_TRACKER.md` | Role ownership and task status |
| `docs/EXPENDITURE.md` | Actual money spent (target: zero) |

A feature is marked complete in the traceability document only when its test has
actually run and passed. Code existing is not completion.

## Datasets and attribution

The OPP-115 corpus (Wilson et al., ACL 2016, Usable Privacy Policy Project,
Carnegie Mellon University) is used under its research, teaching and scholarship
terms. It is not redistributed in this repository. Full citation in
`docs/REFERENCES.md`.

Privacy policy documents and Play Store records are third-party content,
retrieved for analysis and not redistributed.
