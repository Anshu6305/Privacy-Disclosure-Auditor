# Requirement traceability matrix

**Cross-Source Privacy Disclosure Consistency Auditor for Android Applications**
All 27 functional and all 19 non-functional requirements of the approved
Phase 2 SRS. Prepared 18 November 2026 against repository commit `e96383f`.

Status labels are used exactly as defined, and every requirement carries
exactly one. **A file or function existing is not a status** — each row was
checked against the code and the tests that execute it.

"Implemented and tested" means automated tests exercise the behaviour. It does
**not** mean validated against human judgement; that is Phase 5.

---

## Functional requirements

| ID | Approved requirement | Phase 3 design | Phase 4 implementation | Evidence | Status | Gap |
|---|---|---|---|---|---|---|
| FR-01 | Search applications | F-01, T1 | `application_repo.search`, `/api/applications`, SearchPage | `test_application_repository.py`, `SearchPage.test.jsx`, PostgreSQL index suite | Implemented and tested | — |
| FR-02 | Select application for audit | F-02 | `AuditService.request_audit`, audit POST endpoint | `test_audit_service.py`, `test_audit_endpoints.py` | Implemented and tested | — |
| FR-03 | Handle unavailable application | F-03 | `REASON_UNKNOWN_APPLICATION`; UI unavailable state | `test_multi_application.py`, `test_audit_endpoints.py` | Implemented and tested | — |
| FR-04 | Load Data Safety declaration | F-04 | `acquisition/`, `declared_practice`, snapshot repository | `test_acquisition_declaration.py` | Implemented and tested | — |
| FR-05 | Load privacy policy document | F-05 | `snapshot_repo.load_policy_document` with SHA-256 verification | `test_snapshot_repository.py`, `test_policy_path_contract.py` | Implemented and tested | — |
| FR-06 | Optional live retrieval | F-06 | `acquisition/adapters.py` and gateway, rate-limited; **disabled for this run** | `test_acquisition_gateway.py`, `test_live_acquisition.py` (recorded responses) | Implemented, partially tested | Never exercised against the live Play Store; the corpus is `manual_import`. Phase 2 rates FR-06 Medium and requires only that its failure not block stored audits, which holds |
| FR-07 | Record provenance | F-07 | `provenances`, `source_url_*`, `collected_at`, shown in the report | `test_acquisition_corpus.py`, audit report JSON | Implemented and tested | — |
| FR-08 | Extract policy text | F-08 | `analysis/text/extractor.py` | `test_text_extraction.py` | Implemented and tested | — |
| FR-09 | Segment policy text | F-09 | `analysis/text/segmenter.py`, spaCy `en_core_web_sm` pinned | `test_text_segmentation.py` | Implemented and tested | — |
| FR-10 | Handle extraction failure | F-10 | Analysability thresholds; audit fails with a stated reason | `test_text_analysability.py`, `test_audit_pipeline.py` | Implemented and tested | — |
| FR-11 | Classify data practices | F-11 | M5 baseline and improved DistilBERT, both registered | `test_baseline_classifier.py`, `test_improved_classifier_evaluation.py` | Implemented and tested | — |
| FR-12 | Extract data types and purposes | F-12 | DistilBERT token classifier, 55 BIO labels | `test_f12_real_inference.py`, `test_opp115_spans.py` | Implemented, partially tested | Exact-match F1 0.1072. Functional prototype; Phase 1 §3.2 rated this the least certain learning task |
| FR-13 | Support model comparison | F-13 | Variant binding per audit, plus explicit version-set composition | `test_f13_variant_binding.py` (29 tests) | Implemented and tested | — |
| FR-14 | Abstain under low confidence | F-14 | `analysis/confidence/gate.py`; abstention propagates structurally | `test_verdict_confidence.py`, `test_m6_components.py` | Implemented and tested | — |
| FR-15 | Apply taxonomy mapping | F-15 | `analysis/mapping/`, 30 seeded rules, partial mappings flagged | `test_taxonomy_mapping_rules.py` | Implemented and tested | — |
| FR-16 | Normalise declaration | F-16 | Declaration normalisation stage | `test_pipeline_stages.py` | Implemented and tested | — |
| FR-17 | Semantic alignment | F-17, F-18 | Zero-shot NLI under D-01 Option A; label indices checked against `id2label` | `test_f18_real_inference.py`, `test_f18_label_resolution.py` | Implemented and tested | — |
| FR-18 | Assign verdicts | F-19 | ALG-8 precedence, five verdicts, `CHECK` constrained | `test_verdict_engine.py` plus 81 verdict tests | Implemented and tested | Three of the five have never occurred on real data — fixture-exercised only |
| FR-19 | Record evidence or absence | F-20 to F-22 | evidence / absence / inconclusive records with offsets and reasons | `test_evidence_records.py`, `test_audit_pipeline.py` | Implemented and tested | — |
| FR-20 | Generate audit report | F-23 | Report assembly, `/api/audits/{id}/report` | `test_audit_endpoints.py` | Implemented and tested | — |
| FR-21 | Display report with evidence | F-24, F-25 | ReportPage, EvidencePanel | `ReportPage.test.jsx` (11 tests) | Implemented and tested | — |
| FR-22 | Display scope statement | F-26 | `scope_note` on every report, rendered in the UI | `test_health_and_scope.py` | Implemented and tested | — |
| FR-23 | Link to sources | F-27 | `source_url_listing`, `source_url_policy` in the report | audit report JSON, `ReportPage.test.jsx` | Implemented and tested | — |
| FR-24 | Persist audit runs | F-28 | `audit_run` plus all six persisted stages | `test_audit_pipeline.py` | Implemented and tested | — |
| FR-25 | Retrieve audit history | F-29 | History endpoint, HistoryPage | `HistoryPage.test.jsx`, `test_audit_endpoints.py` | Implemented and tested | — |
| FR-26 | Compare two audits | F-30 | `/audits/{earlier}/compare/{later}`, ComparePage | `ComparePage.test.jsx` | Implemented and tested | — |
| FR-27 | Offline evaluation against gold set | F-31 | **Only the `gold_annotation` table exists.** No evaluation module; nothing in production code constructs a gold annotation | Schema tests only | **Not implemented** | The gold set of ≈100 applications that Phase 3 specifies does not exist, so there is nothing to evaluate against |

### Functional requirement counts

| Status | Count | IDs |
|---|---:|---|
| Implemented and tested | **24** | FR-01 to FR-05, FR-07 to FR-11, FR-13 to FR-26 |
| Implemented, partially tested | **2** | FR-06, FR-12 |
| Implemented, not independently verified | 0 | — |
| Partially implemented | 0 | — |
| **Not implemented** | **1** | FR-27 |
| Not applicable / outside scope | 0 | — |
| **Total** | **27** | ✔ reconciles |

---

## Non-functional requirements

| ID | Approved requirement | Phase 4 implementation | Evidence | Status | Gap |
|---|---|---|---|---|---|
| NFR-01 | Stored report retrieval time | Report served from persisted, indexed rows | `test_audit_endpoints.py` | Implemented, not independently verified | No timing was measured |
| NFR-02 | Analysis completion time | Encoder-scale models, CPU inference | — | Implemented, not independently verified | Not measured against the target. An observed run over 629 segments took about two minutes on CPU — an observation, not a benchmark |
| NFR-03 | Asynchronous processing | Worker process, database-backed queue, job id returned | `test_audit_pipeline.py` | Implemented and tested | — |
| NFR-04 | Concurrency | One active audit by design (DD-2); later requests queue | `test_audit_pipeline.py` claim tests | Partially implemented | The queue is correct; the five-request target was never load-tested |
| NFR-05 | No finding without a stated basis | F-23 decision table: a Consistent verdict carries no record by design, every other verdict carries one | `test_evidence_records.py` | Implemented and tested | — |
| NFR-06 | Evidence must be genuine | Quotes are verbatim slices at stored offsets; policy hash verified on load; absence text is a template, discriminated by `record_type` | `test_audit_pipeline.py` (quote equals the document slice) | Implemented and tested | — |
| NFR-07 | Confidence visibility | Confidence on verdicts and judgements, surfaced in the UI | `ReportPage.test.jsx` | Implemented and tested | — |
| NFR-08 | Reproducibility | Seed 20261105 pinned; three `model_version_id`s and `threshold_config` recorded per audit | `test_register_models.py`, `test_f13_variant_binding.py` | Implemented and tested | — |
| NFR-09 | Interpretable without ML knowledge | Plain-language verdict labels, abstention reasons in prose | Frontend tests | Implemented, partially tested | No user study was conducted |
| NFR-10 | Scope statement visible | `scope_note` on every report and in the UI | `test_health_and_scope.py` | Implemented and tested | — |
| NFR-11 | Failure isolation | A failed audit is terminal with a reason; the worker survives, the queue is not wedged | `test_audit_pipeline.py` | Implemented and tested | — |
| NFR-12 | Independence from external sources | Offline-first: local checkpoints, corpus from disk, live retrieval optional and off | `test_live_acquisition.py` | Implemented and tested | — |
| NFR-13 | No end-user personal data | No user table, no authentication, no personal data stored | Schema | Implemented and tested | Satisfied by construction |
| NFR-14 | Input validation | Pydantic request models; typed refusal reasons rather than exceptions | `test_audit_endpoints.py` | Implemented and tested | — |
| NFR-15 | Collection conduct | 3-second request delay, declared research user agent | `test_acquisition_gateway.py` | Implemented, partially tested | Never exercised against live sites |
| NFR-16 | Isolated acquisition layer | `acquisition/` is a separate package; analysis never fetches | `test_acquisition_*.py` | Implemented and tested | — |
| NFR-17 | Configurable mapping and thresholds | Active `taxonomy_mapping_version`; thresholds in settings, pinned per audit | `test_config.py`, `test_taxonomy_mapping_rules.py` | Implemented and tested | — |
| NFR-18 | Deployment environment | Three containers defined; image build corrected for the spaCy source build on arm64 | `test_worker_image.py` | Partially implemented | The image build has not been run to completion, and the worker image deliberately excludes the ML dependency set, so the verified run path is the local virtual environment |
| NFR-19 | Corpus capacity | Prefix indexes sized for ≈1,000 applications | PostgreSQL index suite | Implemented, not independently verified | One application stored; capacity never load-tested |

### Non-functional requirement counts

| Status | Count | IDs |
|---|---:|---|
| Implemented and tested | **12** | NFR-03, NFR-05, NFR-06, NFR-07, NFR-08, NFR-10, NFR-11, NFR-12, NFR-13, NFR-14, NFR-16, NFR-17 |
| Implemented, partially tested | **2** | NFR-09, NFR-15 |
| Implemented, not independently verified | **3** | NFR-01, NFR-02, NFR-19 |
| Partially implemented | **2** | NFR-04, NFR-18 |
| Not implemented | 0 | — |
| Not applicable / outside scope | 0 | — |
| **Total** | **19** | ✔ reconciles |

> **Correction.** An earlier version of this audit printed 13 in the first row
> of this table. The row-by-row assignments were correct — all 19 appear
> exactly once, with no duplicate and none missing — but the summary total was
> wrong by one. The correct figure is **12**, and the six statuses now sum to
> exactly 19. An earlier sixth label, "implemented, not measured", has been
> folded into "implemented, not independently verified", which is the
> sanctioned label for NFR-02.

---

## Implementation goals

| ID | Goal | Status |
|---|---|---|
| GI-01 | Automate a manual comparison | Met |
| GI-02 | Apply NLP to unstructured policy text | Met |
| GI-03 | Detect cross-source inconsistency | Met — on one application; three of five verdict types fixture-only |
| GI-04 | Make every finding traceable to the source text | Met — quotes are verbatim slices at stored offsets, hash-verified |
| GI-05 | Measure a baseline against an improved model | Met as a measurement. The improved model did **not** win on every metric |
| GI-06 | Build a usable full-stack system | Met |
| GI-07 | Keep the system honest about its limits | Met — abstention is a first-class outcome; every report carries its scope statement |

## Reconciliation

* Functional: 24 + 2 + 0 + 0 + 1 + 0 = **27** ✔
* Non-functional: 12 + 2 + 3 + 2 + 0 + 0 = **19** ✔
* Every ID FR-01…FR-27 and NFR-01…NFR-19 appears exactly once, with no
  duplicate and no omission.
