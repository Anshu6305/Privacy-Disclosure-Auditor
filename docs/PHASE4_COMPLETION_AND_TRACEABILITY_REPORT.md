# Phase 4 — Completion and Traceability Report

**Date:** 2026-11-06 · **Verdict: Phase 4 is NOT closed**, and is one step from it. §8 gives the
single remaining reason.

This maps every approved identifier to real code and real tests. Statuses are
used strictly:

* **Implemented and verified** — code exists and automated tests exercise it.
* **Implemented, partially verified** — code exists; some behaviour is tested
  only with fixtures, or only on SQLite.
* **Partially implemented** — some of the specified behaviour is missing.
* **Blocked by an external dependency** — code is complete and cannot run here.
* **Not implemented.**

A passing test suite is not evidence that a requirement is met in the field.
Where the only evidence is a fixture, the row says so.

## 1. Milestones

| Milestone | Status |
| --- | --- |
| M1 scaffold, M2 schema, M3A acquisition, M3B persistence | Complete, PostgreSQL-verified |
| M4 text processing | Complete |
| M5 baseline classifier | Complete, evaluated, rebuilt and reproduced exactly in M10 |
| M6 improved models | Implemented; improved classifier **not trained** |
| M7 verdict engine | Complete |
| M8 backend integration | Complete, PostgreSQL-verified (78 tests, 0 skips at head) |
| M9 frontend | Complete, 32 tests |
| M10 F-15 rules, M5 rebuild, F-12 workflow | Complete |
| M11 model integration | Implementation complete; **Phase 4 not closed** |

## 2. Design functions F-01 to F-34

| Function | Location | Status |
| --- | --- | --- |
| F-01 search | `backend/app/db/repositories/application_repo.py` | Implemented and verified (PostgreSQL) |
| F-02 audit request | `backend/app/services/audit_service.py` | Implemented and verified (PostgreSQL) |
| F-03 unknown application | `application_repo.py`, E2 route | Implemented and verified |
| F-04 declaration load | `acquisition/`, `snapshot_repo.py` | Implemented and verified (PostgreSQL) |
| F-05 policy load | `backend/app/db/repositories/snapshot_repo.py` | Implemented and verified (hash-checked) |
| F-06, F-07 corpus and provenance | `acquisition/corpus.py`, `scripts/import_corpus.py`, `scripts/manual_collect.py` | Implemented and verified; **no real records collected** |
| F-08 extraction | `analysis/text/extractor.py` | Implemented and verified, incl. on real policy text |
| F-09 segmentation | `analysis/text/segmenter.py` | Implemented and verified (spaCy, no fallback by design) |
| F-10 analysability | `analysis/text/validator.py` | Implemented and verified; thresholds **provisional** |
| F-11 classification | `analysis/models/practice_classifier.py` | Implemented, evaluated, rebuilt. Macro-F1 0.7489 / Micro-F1 0.7690 |
| F-11 improved | `analysis/models/improved_classifier.py` | Implemented, **not trained, not evaluated** |
| F-12 span extraction | `analysis/models/span_extractor.py`, `ml/span_backend.py`, `ml/train_span_extractor.py` | **Implemented, trained, evaluated.** Exact F1 0.1072, overlapping 0.5658. **Low accuracy** |
| F-13 variant selection | `analysis/models/variant.py` | **Not implemented** |
| F-14 confidence gate | `analysis/confidence/gate.py` | Implemented and verified |
| F-15 taxonomy mapping | `analysis/mapping/taxonomy_mapper.py`, `rule_loader.py`, `taxonomy/mapping_v1.json` | Implemented and verified — 30 rules, 11 documented refusals |
| F-16, F-17 normalise and candidates | `analysis/mapping/` | Implemented and verified |
| F-18 semantic alignment | `analysis/alignment/nli.py`, `ml/backends.py` | **Implemented and verified** — real inference over all three outcomes. **Not fine-tuned**; weak on plain entailment |
| F-19 ALG-8 verdicts | `analysis/verdict/verdict_engine.py` | Implemented and verified |
| F-20, F-21, F-22 evidence records | `analysis/verdict/` | Implemented and verified |
| F-23 report assembly | `backend/app/api/routes/audits.py` | Implemented and verified |
| F-24 to F-27 frontend | `frontend/src/pages/`, `frontend/src/components/` | Implemented and verified (32 tests, fixtures) |
| F-28 to F-30 audit lifecycle, history, comparison | `audit_service.py`, `audits.py` | Implemented and verified |
| F-31 gold-set evaluation | `ml/evaluate_goldset.py` | **Blocked** — the gold set does not exist |
| F-32 job queue | `audit_pipeline.py`, `worker/worker.py` | Implemented and verified (`FOR UPDATE SKIP LOCKED` on PostgreSQL) |
| F-33 failure handling | `audit_pipeline.py` | Implemented and verified — three refusals |
| F-34 version registry | `model_registry.py`, E10 | Implemented and verified |

**F-13 is the one unimplemented function.** Variant selection presupposes two
trained classifiers to choose between, and the improved variant was never
trained.

## 3. Endpoints E1 to E11

All eleven implemented in `backend/app/api/routes/audits.py`, covered by
`tests/api/test_audit_endpoints.py` (20 tests) and exercised against
PostgreSQL in `tests/integration/test_m8_pipeline_postgresql.py`.
**Implemented and verified.**

## 4. Screens S1 to S7

All seven implemented, 32 Vitest tests. **Implemented, partially verified:**
every test mocks `fetch`, so no screen has been exercised against a live API
or against real audit data.

## 5. Database

Sixteen tables at revision `0003_collection_event`, D-1 Option A (one
collection event per snapshot). Migration chain verified on PostgreSQL 16
with a full upgrade / downgrade / re-upgrade cycle. **Implemented and
verified.** No migration was modified after freezing.

## 6. ML components

| Component | Training | Evaluation | Inference verified |
| --- | --- | --- | --- |
| F-11 baseline (M5) | Real, reproducible | Macro-F1 0.7489, Micro-F1 0.7690 | Yes |
| F-11 improved (M6) | **Never trained** | None | No |
| F-12 span extractor | Real, Colab T4, 4 epochs | Exact F1 0.1072, overlap F1 0.5658 | Yes |
| F-18 aligner | Zero-shot, no fine-tuning | Not evaluated on a gold set (none exists) | **Yes** — all three outcomes, 7 tests |

**Honest reading of F-12.** Exact F1 0.107 is poor. The model finds roughly
the right region with the right value about half the time (overlap F1 0.566)
and gets the exact boundary right about one time in ten. It is usable as a
signal into F-15 and is not a reliable extractor. The abstention gate is what
keeps that from becoming a false finding.

## 7. Requirements

FR-01 to FR-27, NFR-01 to NFR-19 and GI-01 to GI-07 map onto the functions
above and are traced row by row in `docs/IMPLEMENTATION_TRACEABILITY.md`,
which is the authoritative table and is updated per milestone. The
requirement-level summary:

* **Functional requirements** covering search, retrieval, processing,
  classification, mapping, verdicts, evidence, reporting and history are
  implemented and verified.
* Those depending on **semantic alignment** are implemented but unverified in
  the field, because F-18 has never run.
* Those depending on a **real corpus** — the end-to-end audit of an actual
  application — are **not demonstrated**.
* **NFRs** for the 8 GB constraint, sequential model loading, offline-first
  operation and the three-container architecture are implemented;
  performance NFRs have not been measured under load, which belongs to
  Phase 5.
* **GI-01 to GI-07**, the integrity guarantees — verbatim evidence, no
  fabricated quotations, abstention preserved, scope stated, provenance
  retained, refusal over guessing — are implemented and are the most heavily
  tested part of the system.

## 8. Why Phase 4 is not closed

**One thing, and it is not a code defect: no real Android application has
been audited.** `data/corpus/apps/` is empty. Every result in this project
comes from OPP-115 research text or controlled fixtures, and in every case
the Data Safety declaration side is absent — so the system has never done the
one thing it exists to do, which is compare two real disclosures.

Everything that could be verified has been. F-11, F-12 and F-18 all load
trained weights and perform real inference. F-15's rules are authored and
tested. The pipeline runs end to end on a real published privacy policy and
produces verdicts with verbatim evidence, every quote an exact slice.
PostgreSQL is verified across the full migration chain. The frontend is
tested.

**What closing Phase 4 now would mean.** A green suite of 697 tests would be
evidence about research text and fixtures. The remaining step needs three to
five applications collected through `scripts/manual_collect.py`, which
refuses to invent any part of them. No test can substitute for it.

## 9. Known limitations

* **F-12 is inaccurate at exact boundaries** (F1 0.107) and must not be
  presented otherwise.
* **F-11's improved variant was never trained**, so F-13 has nothing to
  select between and M6's comparison was never made.
* **F-18 is zero-shot and weak on plain entailment.** It scores a matching
  statement as neutral (0.637) rather than entailment (0.354); it is reliable
  on contradictions (0.977) and on irrelevance. The 300–500 labelled pairs
  D-01 planned for fine-tuning were never annotated, and neither was the
  ~100-application gold set F-31 needs.
* **F-10's analysability thresholds are provisional**, chosen by this project
  and not an approved requirement.
* **Rare classes are not measurable.** Data Retention (n=7) and Do Not Track
  (n=4) in M5; 7 of 54 F-12 labels have fewer than 10 test spans.
* **M5's train/test gap** (0.94 vs 0.75 macro-F1) is unaddressed.
* **No frontend test runs against a live API**, and no load or performance
  testing has been done.
* **30 mapping rules are not taxonomy coverage** — 14 of 17 data types, 2 of
  10 categories, the rest refused with reasons.

Phase 5, academic validation and testing, is a separate phase and has not
started.
