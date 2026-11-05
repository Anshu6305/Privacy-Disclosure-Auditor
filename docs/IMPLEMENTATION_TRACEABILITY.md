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

Last updated: 2026-11-04 (post-M7 baseline audit)

> **Schema status.** `docs/PHASE4_SCHEMA_BASELINE_AUDIT.md` compares the
> implemented schema against the approved Phase 3 Section 10.2 data dictionary.
> The **six omissions (class E) are now restored**, except E-2 which depends on
> finding D-1. The **seven structural deviations (class D) are unchanged and
> still await the team's ruling**, as do the two contradictions found in the
> approved report itself (DOC-1, DOC-2). Rows below describing a table as
> implemented refer to the table as built; full agreement with the approved
> data dictionary depends on the outstanding D decisions.

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
| ALG-11 functional lower() indexes | `ix_application_lower_name`, `ix_application_lower_package` | `test_case_insensitive_search_indexes_exist`, `test_functional_lower_indexes_exist` | Implemented and verified. **Default `text_ops` class — serves `ORDER BY lower(app_name)`, not the prefix predicate (C-53)** |
| ALG-11 pattern-class indexes (C-53) | `ix_application_lower_name_pattern`, `ix_application_lower_package_pattern`, revision `0002_pattern_ops` | `test_pattern_ops_indexes.py` (13), `test_pattern_ops_opclass_in_catalogue`, `test_prefix_predicate_is_index_eligible`, `test_combined_f01_query_is_index_eligible` | **Tested and verified on PostgreSQL 16, 2026-11-05.** Operator classes `text_pattern_ops`, collation `en_US.utf8`, 56 passed with the revision applied, 49 passed / 7 skipped after downgrade, both baseline indexes retained, EXPLAIN eligibility asserted |
| Migration-state verification (C-56, C-57) | Alembic revision graph via `ScriptDirectory` | `test_alembic_baseline_is_in_the_applied_ancestry`, `test_applied_revision_lies_on_the_path_from_head_to_base`, `test_pattern_indexes_match_the_applied_revision`, `test_the_baseline_functional_indexes_exist_in_every_state` | **Tested and verified** on PostgreSQL 16 in both migration states, 2026-11-05 |
| Segment and span offsets ordered | `ck_*_offsets_ordered` | `test_segment_offsets_must_be_ordered`, `test_span_offsets_must_be_ordered` | Implemented and verified |
| Metrics declare abstention handling | `ck_metric_abstention_handling`, `uq_metric_unique_per_run` | `test_metric_must_declare_how_abstentions_were_handled`, `test_both_abstention_handlings_coexist_for_one_metric` | Implemented and verified |
| Cascade deletes leave no orphans | `ondelete` clauses | `test_cascade_delete_removes_dependent_rows` | Implemented and verified |
| Baseline migration | `backend/migrations/versions/0001_baseline_schema.py` | `test_migration_is_frozen.py` (10 tests); `test_postgresql_schema.py` (29) | **Frozen** — explicit operations, equivalent to the models, applied and verified on PostgreSQL 16 |
| Schema on PostgreSQL (JSONB, BIGINT, functional indexes) | same | `test_postgresql_schema.py` — **29 tests, all passing** | **Verified on PostgreSQL 16**, 2026-11-05 |

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

## Milestone 7 — Verdict and evidence engine

Implemented ahead of Milestones 3 to 6 with team approval; see C-19. Those
milestones remain outstanding.

F-18 is **not** implemented. The engine consumes alignment judgements; in the
current codebase those come only from controlled test fixtures.

| F-id | Design unit | Code | Test | Status |
|---|---|---|---|---|
| F-14 | Confidence thresholding, ALG-4 | `analysis/confidence/gate.py` | `test_pipeline_stages.py` (6 tests), `test_type_invariants.py::test_gate_rejects_a_threshold_that_is_not_a_probability` | Implemented and verified |
| F-15 | Taxonomy mapping, ALG-5 | `analysis/mapping/taxonomy_mapper.py` | `test_pipeline_stages.py` (7 tests) | **Mechanism implemented and verified; no mapping rules authored.** Cannot run on real data until the reviewed OPP-115 to Data Safety rules exist |
| F-16 | Declaration normalisation | `analysis/mapping/declaration_normaliser.py` | `test_pipeline_stages.py` (4 tests) | Implemented and verified |
| F-17 | Candidate construction, ALG-6 | `analysis/mapping/candidate_builder.py` | `test_pipeline_stages.py` (7 tests) | Implemented and verified |
| F-18 | Semantic alignment | — | — | **Not implemented** — Milestone 6, decision D-01 |
| F-19 | Verdict assignment, ALG-8 | `analysis/verdict/verdict_engine.py` | `test_verdict_engine.py` (25), `test_verdict_confidence.py` (15) | Implemented and verified — precedence **and** step 3 verdict confidence |
| F-20 | Evidence selection, ALG-9 | `analysis/verdict/evidence_selector.py` | `test_evidence_records.py` (8 tests) | Implemented and verified |
| F-21 | Absence recording | `analysis/verdict/absence_recorder.py` | `test_evidence_records.py` (4 tests) | Implemented and verified |
| F-22 | Inconclusive recording | `analysis/verdict/inconclusive_recorder.py` | `test_evidence_records.py` (4 tests) | Implemented and verified |

### ALG-8 precedence, step by step

| Step | Condition | Verdict | Test |
|---|---|---|---|
| 1 | Any trusted CONTRADICTS | Contradictory | `test_contradictory`, `test_contradiction_beats_support`, `test_contradiction_beats_support_regardless_of_confidence`, `test_contradiction_beats_abstention` |
| 2a | Trusted SUPPORTS and declared | Consistent (affirmative agreement) | `test_consistent_by_affirmative_agreement`, `test_support_beats_abstention` |
| 2b | Trusted SUPPORTS, not declared | In-policy-not-declared | `test_in_policy_not_declared` |
| 3 | Any abstained judgement | Undetermined | `test_undetermined_when_the_only_judgement_abstained`, `test_abstention_beats_the_absence_rule`, `test_abstention_beats_neither_source_mentions` |
| 4 | Declared, nothing found | Declared-not-in-policy | `test_declared_not_in_policy`, `test_declared_not_in_policy_with_no_judgements_at_all`, `test_trusted_no_match_does_not_block_the_absence_rule` |
| 5 | Not declared, nothing found | Consistent (neither source mentions) | `test_consistent_because_neither_source_mentions_the_category`, `test_every_category_receives_a_verdict` |

The distinction required under Consistent is held by
`CategoryVerdict.consistency_basis` and tested by
`test_the_two_kinds_of_consistent_are_distinguishable`. It is derived from the
`declared` and `found_in_policy` columns the schema already has, so recording
it needed no schema change.

### Abstention propagation

`AlignmentJudgement.abstained` is a property, true when the alignment model
abstained **or** when the candidate carried an abstained policy practice. The
propagation is therefore structural: no caller can build a confident-looking
judgement on an uncertain input.

| Property | Test |
|---|---|
| Upstream abstention survives a 0.99-confidence SUPPORTS | `test_upstream_abstention_propagates_even_at_high_confidence` |
| Upstream abstention also blocks a contradiction | `test_upstream_abstention_blocks_a_contradiction_too` |
| Mapping does not launder abstention | `test_mapping_preserves_abstention`, `test_map_all_keeps_abstained_practices` |
| The gate flags rather than deletes | `test_gate_flags_rather_than_deletes`, `test_gate_keeps_every_input` |
| Abstention is sticky | `test_abstention_is_sticky` |
| Candidates carry it forward | `test_candidates_carry_upstream_abstention` |
| Abstention recorded even when it changes no verdict | `test_abstention_is_recorded_even_when_it_does_not_change_the_verdict` |
| An abstained judgement never establishes policy content | `test_found_in_policy_is_false_when_only_abstained_judgements_exist` |

### Evidence integrity

| Property | Test |
|---|---|
| Quotes are verbatim policy text | `test_evidence_quotes_the_policy_text_verbatim` |
| Offsets locate the quote in the document | `test_evidence_offsets_locate_the_quote_in_the_document`, `test_evidence_offsets_point_at_the_real_text` |
| An abstained judgement cannot support evidence | `test_an_abstained_judgement_cannot_support_evidence` |
| Absence records carry no quote | `test_absence_record_has_no_quote_and_states_a_reason` |
| Absence reasons assert no wrongdoing | `test_absence_reason_does_not_assert_wrongdoing` |
| Consistent verdicts carry no records | `test_consistent_verdict_carries_no_records` |
| Record type always matches the verdict | `test_record_types_match_the_verdict_in_every_case` |
| Ordering is deterministic | `test_ties_are_broken_deterministically` |

### Measured

169 passed, 1 skipped. Statement coverage of the `analysis` package: **100%**
(383 statements).

### Still not implemented after M7

F-01 to F-13 and F-23 to F-34 remain Not implemented. Milestones 3, 4, 5, 6, 8,
9 and 10 are outstanding.

## Functions F-01 to F-34

Module targets are fixed by plan §3. All are Not implemented at the end of
Milestone 1 except F-26 above.

| F-id | Planned module | Milestone | Status |
|---|---|---|---|
| F-01 | `backend/app/db/repositories/application_repo.py` | M3B | **Implemented and PostgreSQL-verified** — ALG-11 prefix search; 43 unit + 14 integration tests passed 2026-11-05. **C-53 correction implemented** as `0002_pattern_ops`; its catalogue and EXPLAIN tests await a PostgreSQL run |
| F-02 | `backend/app/services/audit_service.py` | M8 | Not implemented |
| F-03 | `backend/app/db/repositories/application_repo.py` | M3B | **Implemented** — reports absence, never raises, never permits an audit request |
| F-04 | `acquisition/declaration.py` (normalisation, M3A); `backend/app/db/repositories/snapshot_repo.py` (loading, M3B) | M3A/M3B | **Partially implemented** — normalisation done and tested; database loading deferred pending D-1 |
| F-05 | `acquisition/policy_document.py` (M3A); snapshot path resolution (M3B) | M3A/M3B | **Partially implemented** — filesystem load and hash verification done and tested |
| F-06 | `acquisition/gateway.py`, `acquisition/adapters.py` | M3A | **Partially implemented** — gateway, rate limiting, caching, error handling done and tested. **Never run against a live source** |
| F-07 | `acquisition/provenance.py` | M3A/M3B | **Partially implemented** — representation done and tested; persistence deferred pending D-1 |
| F-08 | `analysis/text/extractor.py` | M4 | Implemented and verified |
| F-09 | `analysis/text/segmenter.py` | M4 | Implemented and verified |
| F-10 | `analysis/text/validator.py` | M4 | Implemented and verified |
| F-11 | `analysis/models/practice_classifier.py` | M5, M6 | **Baseline implemented and evaluated**; improved variant is M6 |
| F-12 | `analysis/models/span_extractor.py` | M6 | Not implemented |
| F-13 | `analysis/models/variant.py` | M6 | Not implemented |
| F-14 | `analysis/confidence/gate.py` | M7 | Implemented and verified |
| F-15 | `analysis/mapping/taxonomy_mapper.py` | M7 | Mechanism only — no rules authored |
| F-16 | `analysis/mapping/declaration_normaliser.py` | M7 | Implemented and verified |
| F-17 | `analysis/mapping/candidate_builder.py` | M7 | Implemented and verified |
| F-18 | `analysis/models/semantic_aligner.py` | M6 | Blocked — no training data; decision pending (plan §7) |
| F-19 | `analysis/verdict/verdict_engine.py` | M7 | Implemented and verified |
| F-20 | `analysis/verdict/evidence_selector.py` | M7 | Implemented and verified |
| F-21 | `analysis/verdict/absence_recorder.py` | M7 | Implemented and verified |
| F-22 | `analysis/verdict/inconclusive_recorder.py` | M7 | Implemented and verified |
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
presence means work has started on it.

| Requirement | Function | Code | Test | Status |
|---|---|---|---|---|
| **FR-01** application search | F-01 | `backend/app/db/repositories/application_repo.py` | `tests/unit/test_application_repository.py` (43), `tests/integration/test_application_search_postgresql.py` (14) | **Implemented and PostgreSQL-verified** 2026-11-05 |
| **FR-03** unknown-application handling | F-03 | same module | same unit file | **Implemented** |
| FR-02 audit request | F-02 | — | — | Not implemented — needs the D-1 snapshot design |
| FR-04 to FR-07 | F-04 to F-07 | `acquisition/` | M3A tests | Partially implemented — persistence pending D-1 |

---

## Baseline audit corrections — class E restorations

| Finding | Restored | Code | Test | Status |
|---|---|---|---|---|
| **E-5** `verdict.confidence` | Yes | `analysis/verdict/models.py`, `verdict_engine.py` (`_deciding_confidence`), `backend/app/db/models.py` | `test_verdict_confidence.py` (15), `test_schema.py::test_verdict_stores_a_nullable_confidence`, `::test_verdict_confidence_must_be_a_probability` | Implemented and verified |
| **E-4** `extracted_span.model_version_id` | Yes | `backend/app/db/models.py` | `test_schema.py::test_span_records_the_extractor_that_produced_it` | Implemented and verified |
| **E-1** `application.store_category` | Yes | `backend/app/db/models.py` | `test_schema.py::test_restored_dictionary_columns_exist` | Implemented and verified |
| **E-3** `extracted_practice.practice_type` | Column restored | `backend/app/db/models.py` | same | **Column present; value vocabulary undefined in Phase 3 and not invented.** Needs the team to define it |
| **E-6** `evaluation_metric.scope` | Yes | `backend/app/db/models.py` | same | Column restored. **Does not by itself enable per-category metrics** — that is D-9 |
| Index `gold_annotation(app_id, ds_category)` | Yes | `backend/app/db/models.py` | `test_schema.py::test_gold_annotation_index_covers_category` | Implemented and verified |
| Index `DESC` orderings | Yes, both | `backend/app/db/models.py` | covered by schema creation | Implemented |
| **E-2** `disclosure_snapshot.status` | **Not restored** | — | — | **Deferred: depends on decision D-1.** What a status means differs between one row per collection event and one row per source |

### NFR-07 — confidence visibility

| Layer | Status |
|---|---|
| Engine computes verdict confidence | Implemented and verified |
| Database stores it as `NUMERIC(5,4)` nullable | Implemented, verified on SQLite |
| API exposes it | **Not implemented** — endpoint E5, Milestone 8 |
| Interface displays it | **Not implemented** — screen S4 and F-24, Milestone 9 |

NFR-07 is **not yet satisfied end to end.** The value now exists and is
computed correctly; nothing presents it to a user. The requirement closes in
M8 and M9.

## PostgreSQL verification

| Item | Status |
|---|---|
| `tests/integration/test_postgresql_schema.py` | 29 tests |
| Executed against PostgreSQL | **Yes — 2026-11-05, PostgreSQL 16 (postgres:16-alpine). 29 passed, 1 skipped** |
| Alembic upgrade executed | Yes — `Running upgrade -> 0001_baseline` against `privacy_auditor_test` |
| Safety guards verified | Yes — a URL naming the project database is refused; a missing driver or unreachable server skips cleanly |

### What PostgreSQL verification now covers

| Property | Verified |
|---|---|
| Alembic baseline applies and stamps `0001_baseline` | Yes |
| All 16 tables created | Yes |
| `threshold_config` and `training_config` are **JSONB**, not JSON | Yes |
| 11 primary keys are **BIGINT** — the check SQLite structurally cannot make | Yes |
| Timestamps are **timestamptz**, not naive | Yes |
| `verdict.confidence` is **NUMERIC** | Yes |
| Both functional `lower()` indexes exist and are functional | Yes |
| All **28 CHECK** constraints present in `pg_constraint` | Yes |
| All **8 UNIQUE** constraints present | Yes |
| `audit_run` has 8 identifier columns and no nullable reference | Yes |
| PostgreSQL **rejects** 7 classes of invalid record | Yes |

The project database `privacy_auditor` is still empty and was not touched;
everything ran against `privacy_auditor_test`.

---

## Milestone 4 — Text processing (T2)

| Requirement | Function | Code | Test | Status |
|---|---|---|---|---|
| FR-08 | F-08 extractPolicyText | `analysis/text/extractor.py` | `test_text_extraction.py` (24) | Implemented and verified |
| FR-09 | F-09 segmentPolicyText | `analysis/text/segmenter.py` | `test_text_segmentation.py` (23) | Implemented and verified |
| FR-10 | F-10 validateAnalysability | `analysis/text/validator.py` | `test_text_analysability.py` (31) | Implemented and verified |
| ALG-1 | F-08 + F-09 | both | the above | Implemented, O(n) single pass |
| T2 end to end | F-05→F-08→F-09→F-10 | `analysis/text/pipeline.py` | 6 tests | Implemented and verified |

### The offset guarantee

Offsets index the **cleaned plain text produced by F-08**, which is the
canonical coordinate base. This follows from the approved design: Phase 3
defines F-09's input as F-08's cleaned text. No offset refers to raw HTML.

| Property | Test |
|---|---|
| Offsets locate the exact text, by slicing the real string | `test_offsets_locate_the_exact_text_by_slicing` |
| Every non-whitespace character is in exactly one segment | `test_no_sentence_is_lost_or_duplicated` |
| Segments are ordered and do not overlap | `test_segments_are_ordered_and_do_not_overlap` |
| Text is never altered | `test_text_is_never_altered` |
| A wrong offset cannot be constructed | `test_segment_rejects_offsets_that_do_not_match_its_text` |
| The offset checker catches a deliberate fault | `test_verify_segments_detects_a_broken_offset` |
| Offsets survive the whole pipeline | `test_pipeline_offsets_index_the_cleaned_text` |
| The cleaned text is stored for F-25 highlighting | `test_cleaned_text_is_written_for_later_highlighting` |

### Provisional values introduced

| Value | Setting | Status |
|---|---|---|
| `min_segments` = 1 | `MIN_POLICY_SEGMENTS` | **Provisional**, not an approved requirement |
| `min_tokens` = 50 | `MIN_POLICY_TOKENS` | **Provisional**, not an approved requirement |
| `max_segment_chars` = 1000 | per call | **Provisional**, tied to an unmade encoder choice |

Phase 2 and Phase 3 require the comparison and name the quantities but set no
numbers. Reasoning in `docs/M4_TEXT_PROCESSING_REPORT.md` section 7.

---

## Milestone 5 — Baseline classifier (T3.1)

| Requirement | Function | Code | Test | Status |
|---|---|---|---|---|
| FR-11 | F-11 (baseline) | `analysis/models/practice_classifier.py` | `test_baseline_classifier.py` (38) | **Baseline implemented and evaluated** |
| ALG-2 | TF-IDF + OvR LogReg | same | same | Implemented, O(\|v\|) per segment |
| — | Dataset construction | `ml/data/opp115_dataset.py` | `test_opp115_dataset.py` (19) | Implemented and verified |
| — | Policy-grouped split | `ml/data/splits.py` | 8 tests | Implemented and verified |
| — | Multi-label evaluation | `ml/evaluation.py` | 9 tests | Implemented and verified |
| GI-02 | practice identification | F-11 | — | Baseline evidence |
| GI-05 | baseline vs improved | F-11 baseline | — | **Half complete**; M6 supplies the improved model on the same split |
| F-14 | reused unchanged | `analysis/confidence/gate.py` | `test_f14_flags_rather_than_discards` | No second threshold mechanism |

### Measured result — held-out test split, 541 segments from 18 policies

| Metric | Value |
|---|---|
| Macro-F1 | **0.7489** |
| Micro-F1 | **0.7690** |
| Hamming loss | **0.0545** |
| Subset accuracy | 0.5896 |

Training macro-F1 was 0.9367. The 0.19 gap is overfitting and is reported as
such. **The test figure is the result; the training figure is not.**

### Categories that cannot be evaluated

| Category | Test support | Status |
|---|---|---|
| Do Not Track | 4 | **Not a measurement.** 31 positive segments exist in the whole corpus |
| Data Retention | 7 | **Not a measurement.** F1 0.429 |

Flagged automatically by `ml/evaluation.py` and recorded as `"reliable": false`
in the saved metrics. No example was moved between splits to improve these
counts.

### Not implemented in M5

F-34 model registry persistence, database writes, API endpoints, improved
models, span extraction, semantic alignment, threshold tuning. The validation
split exists and is deliberately unused so far.
