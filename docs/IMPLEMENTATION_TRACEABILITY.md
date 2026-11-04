# Implementation Traceability

Requirement → design unit → code → test, with the honest status of each.

**Status values**

| Value | Meaning |
|---|---|
| Implemented and verified | The code exists **and** a test has actually run and passed |
| Partially implemented | Some code exists; behaviour is not yet fully verified |
| Not implemented | No code yet |
| Blocked | Cannot proceed; the blocker is named |

A row is never promoted to "Implemented and verified" because the code looks
finished. The test must have run. Where a status says verified, the test
identifier in the same row is the evidence.

Last updated: 2026-11-04 (Milestone 1)

---

## Milestone 1 — Repository and development environment

Milestone 1 builds no approved requirement. It establishes the environment that
later milestones are verified in, so its rows refer to project infrastructure
rather than to FR or NFR identifiers.

| Item | Code | Test | Status |
|---|---|---|---|
| Repository structure per plan §4 | whole tree | — | Implemented and verified (tree present) |
| Configuration from environment, no hard-coded credentials | `backend/app/config.py` | `test_config.py::test_no_usable_default_database_password` | Implemented and verified |
| Database URL assembly | `backend/app/config.py` | `test_config.py::test_database_url_is_assembled_from_parts` | Implemented and verified |
| ALG-4 thresholds configurable, not constants | `backend/app/config.py` | `test_config.py::test_thresholds_are_configuration_not_constants` | Implemented and verified |
| Application assembles and serves | `backend/app/main.py` | `test_health_and_scope.py::test_health_endpoint_reports_ok` | Implemented and verified |
| Database state reported truthfully | `backend/app/api/routes/health.py` | `test_health_and_scope.py::test_database_health_reports_unconfigured_without_credentials` | Implemented and verified |
| Lazy engine; import opens no connection | `backend/app/db/session.py` | covered by the suite running with no database | Implemented and verified |
| SPA mount does not shadow the API | `backend/app/main.py` | `test_static_mount.py` (3 tests) | Implemented and verified |
| OPP-115 corpus verification and manifest | `ml/data/verify_opp115.py`, `ml/data/opp115_schema.py` | `test_opp115_verification.py` (7 tests) | Implemented and verified |
| Three-container deployment definition | `docker-compose.yml`, `backend/Dockerfile` | not yet executed — Docker is unavailable in the authoring environment | Partially implemented |
| Frontend builds | `frontend/` | `npm run build` succeeded, 2026-11-04 | Implemented and verified |

## F-26 — Scope statement

The scope statement is the one approved-design element Milestone 1 implements,
because it has to exist before anything can display a finding.

| Requirement | Design unit | Code | Test | Status |
|---|---|---|---|---|
| Scope statement served from a single source | F-26 | `backend/app/main.py` (`SCOPE_STATEMENT`), `/api/meta/scope` | `test_health_and_scope.py::test_scope_statement_disclaims_legal_judgement` | Implemented and verified |
| Scope statement displayed in the interface | F-26 | `frontend/src/components/ScopeBanner.jsx` | not yet — frontend tests arrive in Milestone 9 | Partially implemented |

---

## Functions F-01 to F-34

Module targets are fixed by plan §3. All are Not implemented at the end of
Milestone 1 except F-26 above.

| F-id | Planned module | Milestone | Status |
|---|---|---|---|
| F-01 | `backend/app/db/repositories/application_repo.py` | M8 | Not implemented |
| F-02 | `backend/app/services/audit_service.py` | M8 | Not implemented |
| F-03 | `backend/app/db/repositories/application_repo.py` | M8 | Not implemented |
| F-04 | `backend/app/db/repositories/snapshot_repo.py` | M2 | Not implemented |
| F-05 | `backend/app/db/repositories/snapshot_repo.py` | M2 | Not implemented |
| F-06 | `acquisition/play_store_adapter.py` | M3 | Blocked — Play Store unreachable from the authoring environment |
| F-07 | `acquisition/provenance.py` | M3 | Not implemented |
| F-08 | `analysis/text/extractor.py` | M4 | Not implemented |
| F-09 | `analysis/text/segmenter.py` | M4 | Not implemented |
| F-10 | `analysis/text/validator.py` | M4 | Not implemented |
| F-11 | `analysis/models/practice_classifier.py` | M5, M6 | Not implemented |
| F-12 | `analysis/models/span_extractor.py` | M6 | Not implemented |
| F-13 | `analysis/models/variant.py` | M6 | Not implemented |
| F-14 | `analysis/confidence/gate.py` | M7 | Not implemented |
| F-15 | `analysis/mapping/taxonomy_mapper.py` | M7 | Not implemented |
| F-16 | `analysis/mapping/declaration_normaliser.py` | M7 | Not implemented |
| F-17 | `analysis/mapping/candidate_builder.py` | M7 | Not implemented |
| F-18 | `analysis/models/semantic_aligner.py` | M6 | Blocked — no training data; decision pending (plan §7) |
| F-19 | `analysis/verdict/verdict_engine.py` | M7 | Not implemented |
| F-20 | `analysis/verdict/evidence_selector.py` | M7 | Not implemented |
| F-21 | `analysis/verdict/absence_recorder.py` | M7 | Not implemented |
| F-22 | `analysis/verdict/inconclusive_recorder.py` | M7 | Not implemented |
| F-23 | `backend/app/services/report_assembler.py` | M8 | Not implemented |
| F-24 | `frontend/src/pages/ReportPage.jsx` | M9 | Not implemented |
| F-25 | `frontend/src/components/EvidencePanel.jsx` | M9 | Not implemented |
| F-26 | `frontend/src/components/ScopeBanner.jsx` | M1, M9 | Partially implemented |
| F-27 | `frontend/src/components/SourceLinks.jsx` | M9 | Not implemented |
| F-28 | `backend/app/db/repositories/audit_repo.py` | M2 | Not implemented |
| F-29 | `backend/app/db/repositories/audit_repo.py` | M8 | Not implemented |
| F-30 | `backend/app/services/audit_compare.py` | M8 | Not implemented |
| F-31 | `ml/evaluate_goldset.py` | M6 | Blocked — gold set does not exist yet |
| F-32 | `backend/app/services/job_queue.py` | M8 | Not implemented |
| F-33 | `backend/app/services/failure_handler.py` | M8 | Not implemented |
| F-34 | `backend/app/services/version_registry.py` | M2 | Not implemented |

## Requirements FR-01 to FR-27, NFR-01 to NFR-19, GI-01 to GI-07

Rows are added as each requirement's implementation begins, so that a row's
presence means work has started on it. No requirement is recorded as
implemented at the end of Milestone 1.
