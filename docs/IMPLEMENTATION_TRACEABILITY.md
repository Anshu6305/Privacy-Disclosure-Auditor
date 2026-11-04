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

Last updated: 2026-11-04 (Milestone 2)

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

## Milestone 2 — Database implementation

All sixteen tables of the approved design, their constraints and the baseline
migration. Every constraint row below was verified by attempting a write the
design forbids and confirming the database refused it.

| Design element | Code | Test | Status |
|---|---|---|---|
| Sixteen tables, no more | `backend/app/db/models.py` | `test_schema.py::test_exactly_sixteen_tables` | Implemented and verified |
| Seven NOT NULL FKs on `audit_run` | `AuditRun` | `test_audit_run_has_seven_not_null_foreign_keys` | Implemented and verified |
| Five verdict values only | `Verdict`, `ck_verdict_value` | `test_verdict_accepts_all_five_approved_values`, `test_verdict_rejects_an_invented_value` | Implemented and verified |
| One verdict per category per audit | `uq_verdict_audit_category` | `test_one_verdict_per_category_per_audit` | Implemented and verified |
| Four gold labels; Undetermined excluded | `ck_gold_label_is_annotation_label` | `test_gold_annotation_rejects_undetermined`, `test_gold_annotation_accepts_the_four_annotation_labels` | Implemented and verified |
| Annotator disagreement recordable | `uq_gold_app_category_annotator` | `test_two_annotators_may_disagree_on_the_same_category`, `test_one_annotation_per_annotator_per_category` | Implemented and verified |
| Evidence record requires a verbatim quote with offsets | `ck_record_evidence_requires_quote` | `test_evidence_record_requires_a_real_quote_with_offsets`, `test_evidence_record_rejects_an_empty_quote`, `test_evidence_record_rejects_reversed_offsets`, `test_valid_evidence_record_is_accepted` | Implemented and verified |
| Absence record carries no quote | `ck_record_absence_has_no_quote` | `test_absence_record_may_not_carry_a_quote`, `test_absence_record_requires_a_reason`, `test_valid_absence_record_is_accepted` | Implemented and verified |
| Inconclusive record states a reason | `ck_record_inconclusive_has_reason` | `test_inconclusive_record_requires_a_reason` | Implemented and verified |
| Consistent verdict needs no record (F-23) | no NOT NULL link from verdict | `test_consistent_verdict_needs_no_record` | Implemented and verified |
| Three alignment labels only | `ck_judgement_label` | `test_judgement_label_is_restricted_to_three_values` | Implemented and verified |
| Judgement needs at least one side | `ck_judgement_has_at_least_one_side` | `test_judgement_requires_at_least_one_side`, `test_judgement_accepts_a_declaration_with_no_policy_side` | Implemented and verified |
| Confidence is a probability | `ck_*_confidence_range` | `test_confidence_must_be_a_probability` (2 cases) | Implemented and verified |
| Abstention stored at every stage | `abstained` columns | `test_abstention_is_a_column_on_every_stage`, `test_abstained_practice_is_stored_not_discarded` | Implemented and verified |
| Queue states and their invariants (F-32) | `ck_audit_status`, `ck_audit_failed_has_reason`, `ck_audit_completed_has_timestamp` | `test_audit_status_is_restricted`, `test_failed_audit_must_record_why`, `test_completed_audit_must_have_a_completion_time` | Implemented and verified |
| Thresholds recorded per run | `threshold_config` NOT NULL | `test_threshold_config_is_required` | Implemented and verified |
| Snapshots in an audit must differ | `ck_audit_distinct_snapshots` | `test_audit_cannot_compare_a_snapshot_with_itself` | Implemented and verified |
| Documents on disk, not in the database | `storage_path`, `content_sha256` | `test_policy_documents_are_not_stored_in_the_database`, `test_snapshot_hash_must_be_a_full_sha256` | Implemented and verified |
| ALG-11 functional lower() indexes | `ix_application_lower_name`, `ix_application_lower_package` | `test_case_insensitive_search_indexes_exist` | Implemented and verified |
| Segment and span offsets ordered | `ck_*_offsets_ordered` | `test_segment_offsets_must_be_ordered`, `test_span_offsets_must_be_ordered` | Implemented and verified |
| Metrics declare abstention handling | `ck_metric_abstention_handling`, `uq_metric_unique_per_run` | `test_metric_must_declare_how_abstentions_were_handled`, `test_both_abstention_handlings_coexist_for_one_metric` | Implemented and verified |
| Cascade deletes leave no orphans | `ondelete` clauses | `test_cascade_delete_removes_dependent_rows` | Implemented and verified |
| Baseline migration | `backend/migrations/versions/0001_baseline_schema.py` | `test_migration_baseline.py` (2 tests) | Implemented and verified on SQLite |
| Schema on PostgreSQL (JSONB, BIGINT, functional indexes) | same | `test_postgresql_schema_is_not_verified_here` — skipped | **Not verified** — no PostgreSQL in this environment |

### Repositories and persistence functions

The tables exist; the functions that read and write them do not. F-04, F-05,
F-28 and F-34 were listed against Milestone 2 in the plan, but only their
storage is in place. They remain Not implemented and move with Milestone 8.

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
