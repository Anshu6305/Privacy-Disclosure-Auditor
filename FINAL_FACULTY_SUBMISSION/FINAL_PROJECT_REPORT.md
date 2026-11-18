# Cross-Source Privacy Disclosure Consistency Auditor for Android Applications

### Final Project Report — Phases 1 to 4

B.Tech, Computer Science and Engineering
Kalinga Institute of Industrial Technology, Bhubaneswar
Six-member team · Roles R1 to R6 (Phase 3 §13.2)

Repository commit `e96383f`, branch `master` · Report prepared 18 November 2026

> This is a **Phase 1–4 submission**. Phase 5 (academic validation and testing)
> is a separate phase and has not begun. Nothing in this report claims a
> validated accuracy for the system as a whole.

---

## 1. Abstract

An Android application discloses what personal data it collects in two
independent places. The Google Play **Data Safety** section is a structured
form the developer completes. The **privacy policy** is prose the developer
writes. Nothing in the Play Store checks that the two agree, and a reader who
wants to know whether they agree must compare them by hand, category by
category.

This project builds a system that performs that comparison automatically. It
reads a stored Data Safety declaration and the application's published privacy
policy, determines what the policy says about each privacy-practice category
using natural-language processing and three machine-learning components, maps
both sources into a single category vocabulary, and issues one of five verdicts
per Data Safety category. Every finding is anchored to the exact characters of
the policy that produced it, and where confidence is insufficient the system
abstains and records why rather than guessing.

The system was built to the approved Phase 2 SRS: 27 functional and 19
non-functional requirements, of which 26 functional requirements are
implemented and 24 are covered by automated tests. One real application,
`com.spotify.music`, has been collected and audited end to end through
PostgreSQL with trained models. **The system's end-to-end verdict accuracy has
not been measured**, because the gold set the approved design specifies does
not exist.

## 2. Problem statement and objectives

**Problem.** Two public disclosures about the same application may disagree,
and no automated check exists. Manual comparison is slow and error-prone, and
it scales linearly with the number of applications and categories.

**Objectives** — the seven implementation goals of the approved SRS:

| ID | Goal |
|---|---|
| GI-01 | Automate a comparison that is currently manual |
| GI-02 | Apply NLP to unstructured privacy-policy text |
| GI-03 | Detect inconsistency between two sources of disclosure |
| GI-04 | Make every finding traceable to the source text that produced it |
| GI-05 | Measure a baseline model against an improved model |
| GI-06 | Build a usable full-stack system, not a notebook |
| GI-07 | Keep the system honest about what it does not know |

GI-07 shaped more of the code than any other. Abstention is a first-class
outcome with its own verdict, its own evidence record type and its own
database constraint.

## 3. Feasibility and scope

Phase 1 concluded **FEASIBLE WITH CONDITIONS**. Its assessment held:

| Phase 1 assumption | Outcome |
|---|---|
| Entirely open-source stack | Held. No paid service was introduced |
| ₹8,000–₹10,000 total expenditure | Held. All model training ran on free-tier Colab T4; actual training spend **₹0** |
| 8 GB RAM development machine | Held. Encoder-scale models only; one model set resident at a time (DD-2) |
| Span extraction is the least certain learning task (§3.2) | **Correct.** F-12 exact-match F1 is 0.1072 |
| Corpus collection is a schedule risk | **Correct.** This became the project's largest shortfall |

**In scope:** comparing two supplied public disclosures for Android
applications whose policies are in English.

**Explicitly out of scope, and never claimed anywhere in the system:** legal or
regulatory compliance verification; Android binary or runtime-traffic analysis;
iOS; non-English policies; user accounts and authentication. Every report the
system generates carries its own scope sentence stating the first two.

## 4. Requirements

27 functional requirements in seven groups (search and selection; disclosure
acquisition; text processing; ML analysis; mapping and alignment; verdict and
evidence; reporting, history and offline evaluation) and 19 non-functional
requirements covering performance, evidence integrity, security, conduct and
deployment.

The complete requirement-by-requirement status is in
`00_READ_ME_FIRST/Requirement_Traceability_Matrix.md`. Summary:

| | Implemented and tested | Implemented, partially tested | Implemented, not independently verified | Partially implemented | Not implemented | Total |
|---|---:|---:|---:|---:|---:|---:|
| Functional | 24 | 2 | 0 | 0 | 1 | **27** |
| Non-functional | 12 | 2 | 3 | 2 | 0 | **19** |

## 5. System architecture and design

A **layered monolith deployed as three containers** on a single host:
`database` (PostgreSQL 16), `api` (FastAPI, which also serves the built
single-page application) and `worker`. Phase 1 excluded microservices,
orchestration platforms, vector databases, agent frameworks and
retrieval-augmented generation; none was introduced.

**The job queue is a database table.** `audit_run` is claimed with
`FOR UPDATE SKIP LOCKED`; there is no message broker. One audit runs at a time
per worker (DD-2), because the memory plan assumes one model set resident on
an 8 GB machine.

```
Data Safety declaration ──────────────► normalise ─┐
                                                   │
Privacy policy ─► extract ─► segment ─► classify ─► extract spans ─► map ─► align ─┤
                                                                                   ▼
                                                   confidence gate ─► verdict + evidence ─► report
```

Nine tasks T1–T9 decompose into functions F-01 to F-34 with algorithms ALG-1 to
ALG-11, specified in Phase 3 §4. Supporting diagrams — DFD levels 0–2, class,
sequence, activity, component, deployment, use-case and ER — are in
`03_PHASE_3_SYSTEM_DESIGN/Supporting_Diagrams/`, with an object (instance)
diagram and a Gantt chart added in `07_SUPPLEMENTARY_DOCUMENTATION/`.

## 6. Algorithms and database

**The verdict algorithm (ALG-8)** applies five outcomes in strict precedence:

1. A decisive contradiction about the same data practice → **Contradictory**
2. Decisive support, resolved against the declaration → **Consistent** if
   declared, **In-policy-not-declared** if not
3. Any abstention in play → **Undetermined**
4. Declared but nothing found in the policy → **Declared-not-in-policy**
5. Neither declared nor found → **Consistent**

Two refinements came from auditing real output rather than from design review:
a contradiction requires a declaration to contradict (C-86), and it must
concern the same data practice rather than merely the same category (C-87).

**Database.** PostgreSQL 16, 16 tables, three migrations with the baseline
frozen. Two constraints enforce an academic distinction rather than a technical
one: `verdict.verdict_value` is restricted to the five system outcomes, and
`gold_annotation.label` to the four ground-truth labels — so **Undetermined
cannot be written into a gold set**. A system abstention is not an annotation.

Raw policy documents live on the filesystem with their SHA-256 in the database;
the segmented text needed for quoting is in the database, so the pipeline never
depends on the raw file being present. Sizing arithmetic is in
`07_SUPPLEMENTARY_DOCUMENTATION/Database_Sizing_And_Connections.md`: about
553 KB of database per audited application, projecting to under 2 GB at the
NFR-19 ceiling of 1,000 applications.

## 7. Implementation

| Layer | Delivered |
|---|---|
| Backend | FastAPI 0.115.6, endpoints E1–E11, typed refusal reasons rather than exceptions |
| Worker | Database-backed queue, one audit at a time, terminal failure with a stated reason |
| Frontend | React 18.3.1 + Vite 5.4.11, seven approved screens S1–S7 plus a team-facing system page |
| Persistence | SQLAlchemy 2.0.36, Alembic 1.14.0, psycopg 3.2.3 |
| Acquisition | Isolated package; manual import working, live retrieval implemented and disabled |
| ML | scikit-learn 1.6.0 (baseline), PyTorch 2.5.1 + Transformers 4.47.1 (encoders), spaCy 3.8.3 |

**Every finding is traceable by construction.** An evidence record stores a
verbatim quote with the character offsets it was sliced from; a test asserts
that the quote equals the document slice at those offsets, so a drift that
showed a reader text the policy does not contain would fail the suite.

**99 implementation findings** are recorded in `PHASE4_CONSISTENCY_LOG.md`
(C-01 to C-99), each a point where implementation met the approved design.
Several were defects found only by running the system: the improved checkpoint
could not be loaded at all because of a tokenizer-class mismatch (C-90);
Undetermined verdicts reached the API with offsets but no words (C-91); a
worker polled a different database from the one holding the audits (C-96); a
relative checkpoint path resolved against the working directory (C-97).

## 8. ML methodology and actual results

**Data.** OPP-115 — a corpus of website privacy policies annotated with
privacy-practice categories. It is **training data for practice
classification**, not a cross-source evaluation set, and the two are never
conflated in this project. Labels are taken by majority vote of at least two of
three annotators.

**Split.** A single policy-grouped split with seed 20261105: 80 policies train,
17 validation, 18 test (2,634 / 617 / 541 segments). Grouping by policy
matters — a policy reuses its own phrasing, so a random split by segment would
measure memorisation. Both classifiers were evaluated on **the same split**, so
the comparison is between two models and not two experiments.

### Classifier results, held-out test split (541 segments)

| Metric | M5 baseline (TF-IDF + one-vs-rest LR) | F-11 improved (DistilBERT) |
|---|---:|---:|
| Macro-F1 | **0.7489** | 0.6304 |
| Micro-F1 | 0.7690 | **0.7775** |
| Precision | 0.7462 | **0.8231** |
| Recall | **0.7932** | 0.7367 |
| Hamming loss | 0.0545 | **0.0482** |
| Subset accuracy | 0.5896 | **0.6765** |

**The improved classifier is not uniformly better, and must not be described as
more accurate.** It wins five of six aggregate measures and six of the ten
categories. It loses macro-F1 by 0.119 because at the 0.5 threshold it **never
predicts Data Retention (7 positive test examples) or Do Not Track (4)** —
two zeroes in an unweighted mean over ten classes. User Access, Edit and
Deletion also regresses, F1 0.538 against 0.774. Neither rare category has
enough test examples to be a reliable measurement in **either** model, so the
baseline's apparent 0.8571 on Do Not Track is not a measurement either.

Thresholds are provisional at 0.5 and **were not tuned on the held-out split**.
The improved model's figures were independently re-derived on CPU from the
restored checkpoint and matched the training run to four decimal places.

### Span extraction (F-12)

Exact-match F1 **0.1072**, overlap F1 **0.5658**, over 1,010 gold spans. The
model usually locates roughly the right region with the right value and gets
exact boundaries about one time in ten. It is a **working prototype, not a
production extraction model**; F-14's confidence gate carries that uncertainty
forward into Undetermined verdicts rather than concealing it.

### Semantic alignment (F-18)

A zero-shot NLI cross-encoder under approved decision **D-01 Option A**. It is
**not fine-tuned** — doing so would need 300–500 labelled alignment pairs that
do not exist. All three outcomes (entailment, contradiction, neutral) were
verified; it is weak on plain entailment.

### Computational cost

No generative model and no token-billed API are used, so the marginal monetary
cost of an audit is **₹0**. One audit of the pilot policy is 1,869 encoder
forward passes over 8,176 WordPiece tokens, about two minutes on CPU. Details
in `07_SUPPLEMENTARY_DOCUMENTATION/ML_Cost_And_Scalability.md`.

## 9. Frontend and backend

**Backend.** Eleven endpoints E1–E11: health, application search and detail,
audit request, audit status, report, category evidence, history, comparison,
and the model-provenance views. Refusals are typed and explanatory — an
unknown application, a missing collection event, an unavailable model variant
each return a named reason rather than a generic error.

**Frontend.** Seven approved screens — search, application, audit status,
report, history, compare, and a team-facing system page. Every screen renders
only API data. A report produced with fixture models declares itself; a failed
audit shows the pipeline's own refusal sentence; an unavailable capability
renders as unavailable rather than as a plausible-looking result.

The report screen lists one row per Data Safety category with its verdict and
confidence. Expanding a row shows the evidence: a quotation with its character
offsets for a finding, a system-generated statement for an absence, or the
passage and reason for an abstention.

## 10. Testing evidence

Run on 18 November 2026 against commit `e96383f`. Raw output is in
`05_TESTING_AND_EVIDENCE/`.

| Check | Passed | Skipped | Failed |
|---|---:|---:|---:|
| `pytest tests -p no:warnings` | **818** | **78** | **0** |
| Frontend Vitest | **33** | 0 | 0 |
| `ruff check .` | clean | — | — |
| ESLint | clean | — | — |
| `npm run build` | 49 modules, succeeds | — | — |

**The 78 skips are skips, not passes.** They are the PostgreSQL integration
suites, which refuse to guess a database and skip when `TEST_DATABASE_URL` is
unset: `test_postgresql_schema` 32, `test_application_search_postgresql` 24,
`test_m3b_persistence_postgresql` 16, `test_m8_pipeline_postgresql` 6. The team
ran them separately through `scripts/verify_migrations.sh` and reported 78
passed with zero skips at head; those logs are included as evidence.

## 11. Results and discussion

**The real pilot.** `com.spotify.music`, manually collected: 19 Data Safety
entries, the published privacy policy stored and hash-verified
(`13089e7b…4ea8`), both provenances recorded as `manual_import`.

**Audit 13** completed on PostgreSQL with the improved classifier:

| | |
|---|---|
| Status | `completed` |
| Verdicts | 14 — **6 Consistent, 8 Undetermined** |
| Evidence records | 18 |
| Models | `f11-improved-v1`, `f12-span-extractor-v1`, `f18-zeroshot-nli-v1` |

These figures were read from the pilot database by the team. Their internal
consistency was checked and holds: 6 + 8 = 14, and since a Consistent verdict
carries no evidence record (F-23), all 18 must come from the 8 Undetermined
verdicts, which F-22 permits at 1 to 3 each — a range of 8 to 24.

**What the result means.** On the one application audited, the system found no
contradiction between Spotify's two disclosures, agreed with six categories,
and **declined to decide on eight**. The high abstention rate is the honest
output of a system built around GI-07: span extraction is weak, the aligner is
zero-shot, and where either is unconfident the verdict engine abstains rather
than asserting. A system tuned to produce more findings would look more
impressive and mean less.

**Three of the five verdicts have never occurred on real data.**
Contradictory, In-policy-not-declared and Declared-not-in-policy are exercised
by 81 controlled verdict-engine tests. That is a corpus limitation, not a code
limitation.

## 12. Known limitations

In order of how much each constrains a claim:

1. **No gold set**, so FR-27 is not implemented and **no end-to-end accuracy
   has been measured**. The approved design specified ≈100 annotated
   applications; zero exist.
2. **One application collected**, against a design expectation of 300–500. The
   pipeline is generic and multi-application capability is unit-tested; the
   corpus is not.
3. **Three of five verdicts are fixture-only** on real data.
4. **Audit 13's figures are team-reported**, corroborated against the
   implemented rules but not independently re-queried in this audit.
5. **78 PostgreSQL integration tests skip** without `TEST_DATABASE_URL`.
6. **NFR-01, NFR-02, NFR-04 and NFR-19 were never measured.**
7. **F-34 sequential model loading is not implemented** — all three models stay
   resident for a run.
8. **The Docker worker image omits the ML dependency set** by design, so it can
   claim an audit but not complete one; the verified path is the local virtual
   environment.
9. **Span extraction is weak at exact match**; the aligner is zero-shot.
10. Out of approved scope and never claimed: APK or runtime analysis, iOS,
    non-English policies, authentication, legal or compliance conclusions.

## 13. Conclusion and future work

**Conclusion.** The approved system was built. Two independent public
disclosures about an Android application can now be compared automatically,
with every finding anchored to the policy text that produced it and with
abstention as a first-class outcome. 26 of 27 functional requirements are
implemented, 24 of them tested; one real application has been audited end to
end through PostgreSQL with trained models. The single functional requirement
not implemented, FR-27, is blocked on a dataset that does not exist rather than
on code.

What this project does **not** establish is whether its verdicts are correct.
That is Phase 5's question, and it needs the gold set.

**Future work, in the order it would pay off:**

1. **Build the gold set.** ≈100 applications annotated with cross-source
   verdicts. This unblocks FR-27 and is the only route to a defensible accuracy
   figure.
2. **Collect the corpus.** 300–500 applications, which would also let the three
   unobserved verdict types appear on real data.
3. **Fine-tune F-18** on 300–500 labelled alignment pairs; the zero-shot
   aligner is the weakest link in the chain after span extraction.
4. **Improve F-12 span extraction**, whose 0.1072 exact-match F1 drives much of
   the abstention rate.
5. **Implement F-34 sequential model loading** to reduce the resident set.
6. **Tune the decision threshold on validation data**, never on test.

## 14. References

The project's reference list is maintained at `docs/REFERENCES.md`, included in
`04_PHASE_4_IMPLEMENTATION/`. The principal sources are:

* **OPP-115** — Wilson et al., *The Creation and Analysis of a Website Privacy
  Policy Corpus*, ACL 2016. Released for research, teaching and scholarship;
  **not redistributed with this submission**.
* **DistilBERT** — Sanh et al., *DistilBERT, a distilled version of BERT*,
  2019. `distilbert-base-uncased`, Apache 2.0.
* **NLI cross-encoder** — `cross-encoder/nli-distilroberta-base`, Apache 2.0.
* **spaCy** 3.8.3, model `en_core_web_sm` (pinned — a different model places
  sentence boundaries differently, which would move every evidence offset).
* **PERT** — the three-point estimation method used in Phase 3 §15.
* Google Play Data Safety: the published disclosure format being compared.

Approved Phase 1, 2 and 3 reports are the authoritative project documents and
are included unaltered in folders 01 to 03.

## 15. Team contributions

Phase 3 §13.2 assigns six roles. **The member names are placeholders in the
approved documents and are left as placeholders here** — they should be
completed by the team rather than inferred. Per-task status is in
`docs/TEAM_TRACKER.md`.

| Role | Member | Responsibility | Owns |
|---|---|---|---|
| R1 | _[Member 1]_ | Design coordination and cross-source alignment | F-15 to F-18, taxonomy mapping artefact |
| R2 | _[Member 2]_ | Data engineering and corpus collection | F-01 to F-07, Play Store corpus |
| R3 | _[Member 3]_ | NLP and classification | F-08 to F-14 |
| R4 | _[Member 4]_ | Backend and integration | F-23, F-32 to F-34, endpoints E1–E11 |
| R5 | _[Member 5]_ | Database and persistence | 16 tables, migrations, F-28 to F-30 |
| R6 | _[Member 6]_ | Frontend and evaluation | F-24 to F-27, F-31, screens S1–S7 |

No contribution is claimed here that the repository's own records do not
support.
