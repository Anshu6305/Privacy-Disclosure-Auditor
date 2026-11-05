# Phase 4 Schema and Baseline Audit

Date: 2026-11-04
Status: **findings only.** No schema, model or migration was changed to produce
this document, and no database was created, reset or dropped.

## Method

The baseline is the approved Phase 3 report, Section 10.2 Data Dictionary and
Section 10.3 Constraints and Indexes, read directly from
`Report_Phase-03.docx` rather than from recollection. The implementation side
is `backend/app/db/models.py` as committed at `5f094a6`, dumped
programmatically from the SQLAlchemy metadata.

Phase 3 §10.2 states: *"Types are given as PostgreSQL types. Every column is
NOT NULL unless marked nullable."* Nullability findings below are judged
against that rule.

## Classification

| Class | Meaning | Approval needed |
|---|---|---|
| **A** Exact match | Same name, type, nullability and constraints | — |
| **B** Naming or implementation adaptation | Same meaning, different identifier or equivalent type | No. Record the mapping |
| **C** Additional field or constraint | Implementation adds something the baseline does not forbid | No. Record as additive |
| **D** Structural design deviation | The shape, cardinality or meaning differs from the baseline | **Yes** — faculty approval and a change-log entry |
| **E** Omission | The baseline specifies it and the implementation lacks it | No approval to restore; it is the approved design |

## Headline result

**Having sixteen tables does not mean the schema matches Phase 3.** It does
not. The table count, the table names and the five-verdict and four-label
constraints match. Below that level there are substantial differences.

| Class | Count |
|---|---|
| A — exact match | 11 columns |
| B — naming or type adaptation | 63 columns |
| C — additional field or constraint | 38 items |
| D — structural deviation | **7 findings** |
| E — omission | **6 findings** |

The seven D findings and six E findings are itemised in the register at the end
and are the subject of the approval request. One of them, the missing
`verdict.confidence`, breaks an approved non-functional requirement.

---

# Part 1 — Table by table

Each table shows the Phase 3 §10.2 specification verbatim, then the
implementation, then the differences.

## 1. `application`

**Phase 3:** `app_id bigserial PK; package_name text UNIQUE; app_name text;
developer_name text; store_category text`

**Implemented:** `app_id INTEGER PK; package_name VARCHAR(255) NOT NULL UNIQUE;
app_name VARCHAR(500) NOT NULL; developer_name VARCHAR(500) nullable;
play_store_url TEXT nullable; first_seen_at NOT NULL; last_seen_at nullable`

| Item | Baseline | Implemented | Class |
|---|---|---|---|
| `app_id` | bigserial (bigint) | INTEGER | **B** — narrower, but 2.1 billion rows is far beyond NFR-19's ceiling of ~1,000 applications |
| `package_name` | text UNIQUE | VARCHAR(255) UNIQUE | B — length cap added |
| `app_name` | text | VARCHAR(500) | B |
| `developer_name` | text, NOT NULL by the §10.2 rule | nullable | **B** — justified: the scraper cannot always obtain it, and a NOT NULL would force a placeholder |
| `store_category` | text | **absent** | **E-1** |
| `play_store_url` | — | TEXT nullable | C |
| `first_seen_at`, `last_seen_at` | — | timestamps | C |
| Functional indexes on `lower()` | §10.3 requires both | both present | **A** |

## 2. `disclosure_snapshot` — the two-source question

**Phase 3:** `snapshot_id bigserial PK; app_id bigint FK; collected_at
timestamptz; source_url_listing text; source_url_policy text; retrieval_mode
text; policy_doc_path text; policy_doc_sha256 char(64); status text`
Purpose note: *"One row per collection event."*

**Implemented:** `snapshot_id BIGINT PK; app_id FK; source_type VARCHAR(32);
source_url TEXT; retrieved_at; retrieval_method VARCHAR(64); storage_path
nullable; content_sha256 VARCHAR(64); content_bytes nullable; http_status
nullable; is_active`

**This is the most consequential difference in the schema.**

Phase 3 models **one row per collection event**, holding *both* source URLs
side by side: `source_url_listing` for the Play Store page and
`source_url_policy` for the privacy policy, with a single `policy_doc_path` and
a single hash. One snapshot therefore represents one moment at which both
disclosures were captured together.

The implementation models **one row per source**, discriminated by
`source_type` ∈ {`data_safety`, `privacy_policy`}. One collection event becomes
two rows, and `audit_run` references both of them.

| Item | Baseline | Implemented | Class |
|---|---|---|---|
| Row granularity | one per collection event, both sources | one per source | **D-1** |
| `source_url_listing` + `source_url_policy` | two columns | one `source_url` + `source_type` | D-1 |
| `policy_doc_sha256 char(64)` | one hash for the policy document | `content_sha256` per row | D-1 |
| `collected_at` → `retrieved_at` | rename | rename | B |
| `retrieval_mode` → `retrieval_method` | rename | rename | B |
| `policy_doc_path` → `storage_path` | rename; nullable in implementation | | B |
| `status text` | present | **absent**; `is_active` + `http_status` instead | **E-2** |
| `char(64)` vs `VARCHAR(64)` | char | varchar | B — the length CHECK makes them equivalent in effect |
| `content_bytes` | — | added | C |
| Index `(app_id, collected_at DESC)` | §10.3 | `(app_id, source_type, retrieved_at)`, no DESC | **B/D** — see index section |

**Which is better is a real question, and it is the team's to answer.** The
per-source design handles a case the baseline cannot: a policy document
retrieved successfully while the Play Store listing fetch fails, which Phase 1
identified as the highest-probability failure in the project. Under the
baseline that collection event has no valid row. Against it, the baseline is
simpler to explain and keeps one collection event as one record, and FR-25's
history is naturally "snapshots over time".

## 3. `declared_practice`

**Phase 3:** `declared_id bigserial PK; snapshot_id bigint FK; ds_category
text; declaration_type text; is_declared boolean`
Note: *"declaration_type distinguishes collected from shared"*

**Implemented:** `declared_practice_id BIGINT PK; snapshot_id FK; ds_category
VARCHAR(128); ds_data_type nullable; is_collected BOOLEAN; is_shared BOOLEAN;
is_optional nullable; is_ephemeral nullable; purpose nullable; raw_label
nullable`

| Item | Baseline | Implemented | Class |
|---|---|---|---|
| `declared_id` → `declared_practice_id` | rename | | B |
| `declaration_type` + `is_declared` | one row per (category, type) with an explicit boolean | two booleans in one row | **D-2** |
| `ds_data_type`, `is_optional`, `is_ephemeral`, `purpose`, `raw_label` | — | added | C |

**D-2 — SUPERSEDED 2026-11-05.** This entry asserted that Google's Data Safety
form produces explicit per-category negatives which the implementation cannot
record.

The assertion was never checked. The published Data Safety section appears to
be positive-only: Google's own documentation describes it as showing what an
app "collects or shares", and a third-party Data Safety scraper's documented
output has `collectedDataTypes` and `sharedDataTypes` with no not-collected
list. Our own acquisition layer does not exist — `acquisition/` holds one
empty `__init__.py` — so nothing in this project has ever read a declaration.

The revised assessment is in `docs/PHASE4_DECISION_TABLE.md`: the
recommendation is **withdrawn**, and the distinctions that do appear to exist
are app-level rather than per-category and belong with finding E-2.

## 4. `policy_segment`

**Phase 3:** `segment_id bigserial PK; snapshot_id bigint FK; seq_no int;
start_offset int; end_offset int; segment_text text`

**Implemented:** `segment_id BIGINT PK; snapshot_id FK; segment_index INTEGER;
segment_text TEXT; char_start INTEGER; char_end INTEGER; heading nullable`

| Item | Class |
|---|---|
| `seq_no` → `segment_index`, `start_offset` → `char_start`, `end_offset` → `char_end` | B |
| `heading` added | C |
| `UNIQUE(snapshot_id, segment_index)` added | C |
| `CHECK char_end > char_start`, `CHECK char_start >= 0` added | C |
| Index `(snapshot_id, seq_no)` required by §10.3 | **A** |

## 5. `extracted_practice`

**Phase 3:** `practice_id bigserial PK; segment_id bigint FK; model_version_id
bigint FK; opp_category text; practice_type text; confidence numeric(5,4);
abstained boolean`

**Implemented:** `extracted_practice_id BIGINT PK; segment_id FK;
model_version_id FK; opp115_category VARCHAR(128); confidence FLOAT; abstained
BOOLEAN; threshold_applied FLOAT`

| Item | Baseline | Implemented | Class |
|---|---|---|---|
| `practice_id` → `extracted_practice_id`, `opp_category` → `opp115_category` | rename | | B |
| `practice_type` | text | **absent** | **E-3** |
| `confidence` | numeric(5,4) | FLOAT | **B/D** — see type section |
| `threshold_applied` | — | added | C |
| `model_version_id` FK | required | present | **A** |
| `abstained` | boolean | present | **A** |

## 6. `extracted_span`

**Phase 3:** `span_id bigserial PK; practice_id bigint FK; model_version_id
bigint FK; span_type text; span_text text; start_offset int; end_offset int;
confidence numeric(5,4); abstained boolean`
Note: *"model_version_id records the extractor used"*

**Implemented:** `span_id BIGINT PK; extracted_practice_id FK; span_type
VARCHAR(32); span_text TEXT; char_start; char_end; normalised_value nullable;
confidence FLOAT; abstained BOOLEAN`

| Item | Baseline | Implemented | Class |
|---|---|---|---|
| `model_version_id` FK | **required, with an explicit note** | **absent** | **E-4** |
| offsets renamed | | | B |
| `normalised_value` | — | added | C |
| `CHECK` on offsets, span_type, confidence | — | added | C |

**Why E-4 matters.** F-12's span extractor is a different model from F-11's
classifier. Without `model_version_id` on this table, a span cannot be
attributed to the extractor that produced it; it inherits only the classifier
recorded on the parent practice. That weakens NFR-08 reproducibility and makes
the baseline-versus-improved comparison of GI-05 unattributable for spans.

## 7. `taxonomy_mapping_version`

**Phase 3:** `mapping_version_id bigserial PK; version_label text UNIQUE;
created_at timestamptz; notes text (nullable)`

**Implemented:** `taxonomy_mapping_version_id INTEGER PK; version_label
VARCHAR(64) UNIQUE; created_at; author_role nullable; source_file nullable;
is_active BOOLEAN; notes nullable`

All differences are B (renames, length caps) or C (`author_role`,
`source_file`, `is_active`, plus an index on `is_active`). `version_label
UNIQUE` and nullable `notes` are **A**.

## 8. `taxonomy_mapping_entry`

**Phase 3:** `entry_id bigserial PK; mapping_version_id bigint FK; opp_category
text; data_type_token text (nullable); ds_category text`
Note: *"A null data_type_token is the category-only fallback entry"*

**Implemented:** `taxonomy_mapping_entry_id INTEGER PK;
taxonomy_mapping_version_id FK; opp115_category VARCHAR(128); opp115_data_type
nullable; ds_category VARCHAR(128); is_partial BOOLEAN; rationale nullable`

Renames are B. `is_partial`, `rationale` and the unique constraint are C. The
nullable data-type fallback semantics are implemented as specified and
exercised by `test_a_more_specific_rule_wins` — **A**.

## 9. `model_version`

**Phase 3:** `model_version_id bigserial PK; component text; variant text;
artefact_path text; trained_at timestamptz; UNIQUE(component, variant,
trained_at)`
Note: *"component is classifier, extractor or aligner; variant is baseline or
improved"*

**Implemented:** `model_version_id INTEGER PK; task VARCHAR(32); variant
VARCHAR(16); model_identifier VARCHAR(255); version_label VARCHAR(64);
checkpoint_path nullable; trained_at nullable; created_at NOT NULL; random_seed
nullable; training_config JSON nullable; is_active BOOLEAN; notes nullable;
UNIQUE(task, version_label)`

| Item | Baseline | Implemented | Class |
|---|---|---|---|
| `component` → `task` | rename | | B |
| Value vocabulary | `classifier`, `extractor`, `aligner` | `classification`, `span_extraction`, `alignment` | **D-3** |
| `artefact_path` → `checkpoint_path`, nullable | | | B |
| `trained_at` | NOT NULL | **nullable** | **D-4** |
| UNIQUE | `(component, variant, trained_at)` | `(task, version_label)` | **D-5** |
| `model_identifier`, `version_label`, `random_seed`, `training_config`, `is_active`, `notes` | — | added | C |
| CHECK on task and variant | — | added | C |

**D-3** is a vocabulary difference, not just a rename: the stored strings
differ from the approved ones, so any query or report written against the
Phase 3 names will not match. **D-4** was deliberate — the zero-shot NLI
baseline under decision D-01 is never trained, so it has no training date — but
it is still a departure from a NOT NULL column in the baseline. **D-5** changes
what "the same model" means: the baseline keys on the training timestamp, the
implementation on a human-assigned label.

## 10. `audit_run`

**Phase 3:** `audit_id bigserial PK; app_id bigint FK; snapshot_id bigint FK;
mapping_version_id bigint FK; classifier_version_id bigint FK;
extractor_version_id bigint FK; aligner_version_id bigint FK; status text;
threshold_config jsonb; started_at timestamptz; claimed_at timestamptz
(nullable); completed_at timestamptz (nullable); failure_reason text (nullable)`

**Implemented:** `audit_id BIGINT PK; app_id FK; ds_snapshot_id FK;
policy_snapshot_id FK; taxonomy_mapping_version_id FK; classification_model_id
FK; span_model_id FK; alignment_model_id FK; status VARCHAR(16); requested_at;
claimed_at nullable; completed_at nullable; failure_reason nullable;
threshold_config JSON NOT NULL`

| Item | Baseline | Implemented | Class |
|---|---|---|---|
| Snapshot references | one `snapshot_id` | two: `ds_snapshot_id`, `policy_snapshot_id` | **D-1** consequence |
| Version FK names | `classifier_/extractor_/aligner_version_id` | `classification_/span_/alignment_model_id` | B |
| `started_at` → `requested_at` | rename | | B |
| `threshold_config jsonb` | present | JSON→JSONB on PostgreSQL, NOT NULL | **A** |
| Queue states | queued/running/completed/failed | same, with a CHECK | A + C |
| `CHECK` failed-has-reason, completed-has-timestamp, distinct-snapshots | — | added | C |

### An internal inconsistency in the approved document

Phase 3 §10.3 states: *"All seven foreign keys from audit_run are NOT NULL, so
an audit cannot be stored without recording the snapshot it analysed and the
four versions that produced it."*

§10.2 lists **six** foreign keys on `audit_run`: `app_id`, `snapshot_id`,
`mapping_version_id`, `classifier_version_id`, `extractor_version_id`,
`aligner_version_id`. The prose's own arithmetic — one snapshot plus four
versions plus the application — also gives six.

So **§10.2 and §10.3 of the approved report disagree with each other.** The
implementation has exactly seven NOT NULL foreign keys, but reaches that number
by splitting the snapshot into two, which is not what §10.2 describes. The
earlier claim in `docs/PHASE4_CONSISTENCY_LOG.md` entry C-10 that this matched
the approved design was therefore **too confident**: it matched the count in
§10.3 and not the structure in §10.2. C-10 is corrected by this audit.

This needs the faculty guide's decision, because it is an error in an approved
document rather than in the code.

## 11. `alignment_judgement`

**Phase 3:** `judgement_id bigserial PK; audit_id bigint FK; practice_id bigint
FK; ds_category text; relation text; confidence numeric(5,4); abstained
boolean`

**Implemented:** `judgement_id BIGINT PK; audit_id FK; ds_category
VARCHAR(128); declared_practice_id nullable FK; extracted_practice_id nullable
FK; segment_id nullable FK; label VARCHAR(16); confidence FLOAT; abstained
BOOLEAN; threshold_applied FLOAT; model_version_id FK`

| Item | Baseline | Implemented | Class |
|---|---|---|---|
| Practice reference | `practice_id` NOT NULL | `extracted_practice_id` **nullable**, plus nullable `declared_practice_id`, plus a CHECK requiring at least one | **D-6** |
| `relation` → `label` | rename | | B |
| `threshold_applied`, `model_version_id` | — | added | C |
| `abstained` retained, not discarded | required | present | **A** |

**D-6 — SUPERSEDED 2026-11-05.** This entry claimed the baseline could not
represent a Declared-not-in-policy verdict because `practice_id NOT NULL`
prevents a judgement row for a declared category with no policy practice.

That was wrong. F-19 takes the declaration state as a separate input, so such
a category needs an **empty judgement list**, not a one-sided judgement row.
Demonstrated against the committed implementation: an empty list yields
Declared-not-in-policy with its F-21 absence record, and all five verdicts are
reachable using only practice-backed judgements carrying no
`declared_practice_id`.

The revised assessment is in `docs/PHASE4_DECISION_TABLE.md`: restore the
approved NOT NULL structure and drop `declared_practice_id`. This is a
compliance restoration, not a deviation needing approval.

## 12. `verdict` — the confidence omission

**Phase 3:** `verdict_id bigserial PK; audit_id bigint FK; ds_category text;
verdict_value text; confidence numeric(5,4) (nullable); UNIQUE(audit_id,
ds_category)`

**Implemented:** `verdict_id BIGINT PK; audit_id FK; ds_category VARCHAR(128);
verdict_value VARCHAR(32); declared BOOLEAN; found_in_policy BOOLEAN;
abstention_involved BOOLEAN; UNIQUE(audit_id, ds_category)`

| Item | Baseline | Implemented | Class |
|---|---|---|---|
| `confidence numeric(5,4) nullable` | **required** | **absent** | **E-5 — confirmed** |
| `UNIQUE(audit_id, ds_category)` | required | present | **A** |
| CHECK on the five verdicts | §10.3 | present | **A** |
| `declared`, `found_in_policy`, `abstention_involved` | — | added | C |

Treated in full in Part 2.

## 13. `evidence_record`

**Phase 3:** `evidence_id bigserial PK; verdict_id bigint FK; segment_id bigint
FK (nullable); record_type text; sentence_text text; start_offset int
(nullable); end_offset int (nullable); rank int`
Note: *"segment_id and offsets are null for absence records"*

**Implemented:** `evidence_record_id BIGINT PK; verdict_id FK; record_type
VARCHAR(16); segment_id nullable FK; judgement_id nullable FK; quoted_text
nullable; char_start nullable; char_end nullable; reason nullable;
display_order INTEGER`

| Item | Baseline | Implemented | Class |
|---|---|---|---|
| `sentence_text` | text, **NOT NULL** by the §10.2 rule | `quoted_text` **nullable** | **D-7** |
| `rank` → `display_order` | rename | | B |
| `judgement_id`, `reason` | — | added | C |
| Three CHECK constraints | — | added | C |
| CHECK on record_type | §10.3 | present | **A** |
| segment_id and offsets nullable | required | present | **A** |

**D-7 — SUPERSEDED 2026-11-05.** This entry argued that §10.2 contradicted
itself by leaving `sentence_text` unmarked, and therefore NOT NULL, while the
same row's note says offsets are null for absence records.

That reading was wrong. The note nulls `segment_id` and the offsets; it says
nothing about `sentence_text`. F-21 requires an absence record to store a
fixed system-generated statement, and F-22 requires an inconclusive record to
store candidate text or a no-candidates statement. Every record type carries
text, so a NOT NULL text column is coherent and the approved design holds
together.

The revised assessment is in `docs/PHASE4_DECISION_TABLE.md`:
`sentence_text` should be restored as a single NOT NULL column whose content
is determined by `record_type`. DOC-2 is withdrawn.

## 14. `gold_annotation`

**Phase 3:** `gold_id bigserial PK; app_id bigint FK; ds_category text; label
text; annotator_code text; evidence_text text (nullable); annotated_at
timestamptz; UNIQUE(app_id, ds_category, annotator_code)`

**Implemented:** adds `is_adjudicated`, `annotator_notes`, `guideline_version`;
renames `evidence_text` → `supporting_quote`; same unique constraint and the
four-label CHECK.

All B or C. The unique constraint and the four-label CHECK are **A**, and the
constraint's stated purpose — permitting double annotation by different
annotators — is verified by `test_two_annotators_may_disagree_on_the_same_category`.

**Index deviation:** §10.3 requires `gold_annotation(app_id, ds_category)`. The
implementation has `ix_gold_app(app_id)` only.

## 15. `evaluation_run`

**Phase 3:** `eval_id bigserial PK; mapping_version_id bigint FK;
classifier_version_id bigint FK; extractor_version_id bigint FK;
aligner_version_id bigint FK; run_at timestamptz; notes text (nullable)`

**Implemented:** `evaluation_run_id INTEGER PK; model_version_id FK **(one)**;
run_at; split_name VARCHAR(32); gold_set_version nullable; item_count;
abstention_count; config JSON nullable; notes nullable`

| Item | Baseline | Implemented | Class |
|---|---|---|---|
| Version references | **four**: mapping, classifier, extractor, aligner | **one**: `model_version_id` | **D-8** |
| `split_name`, `gold_set_version`, `item_count`, `abstention_count`, `config` | — | added | C |

**Why D-8 matters.** In the baseline an evaluation run records the full
pipeline configuration it measured — the mapping version and all three models.
That is what makes F-31's gold-set evaluation reproducible and what lets GI-05
attribute a change to a specific component. The implementation records a single
model, so an end-to-end evaluation of the whole pipeline cannot be represented
at all: it would have to be filed against one arbitrary model.

This is the second most consequential finding after the verdict confidence.

## 16. `evaluation_metric`

**Phase 3:** `metric_id bigserial PK; eval_id bigint FK; scope text;
ds_category text (nullable); metric_name text; metric_value numeric`
Note: *"Per-category and overall metrics, including the abstention rate.
ds_category is null for overall metrics"*

**Implemented:** `evaluation_metric_id BIGINT PK; evaluation_run_id FK;
metric_name VARCHAR(64); class_label VARCHAR(64) nullable; metric_value FLOAT;
support nullable; abstention_handling VARCHAR(32) NOT NULL; UNIQUE(run,
metric_name, class_label, abstention_handling)`

| Item | Baseline | Implemented | Class |
|---|---|---|---|
| `scope` | text | **absent** | **E-6** |
| `ds_category` nullable | a **Data Safety category** | `class_label` — a **class label** such as SUPPORTS | **D-9** |
| `support`, `abstention_handling`, UNIQUE | — | added | C |
| `metric_value numeric` | numeric | FLOAT | B/D |

**D-9 is a semantic drift, not a rename.** The baseline breaks metrics down by
*Data Safety category* — precision and recall for Location, for Personal info,
and so on. The implementation breaks them down by *predicted class label* —
SUPPORTS, CONTRADICTS, NO_MATCH. Both are useful and the project needs both,
but the implementation silently replaced one with the other, and the
per-category breakdown Phase 3 asks for cannot currently be stored. `scope`,
which distinguished per-category from overall rows, went with it.

---

# Part 2 — Cross-cutting findings

## Confidence column type: `numeric(5,4)` versus `FLOAT`

Phase 3 specifies `numeric(5,4)` for every confidence column:
`extracted_practice`, `extracted_span`, `alignment_judgement` and `verdict`.
The implementation uses `FLOAT` (double precision) throughout.

This is more than cosmetic. NFR-08 requires that *"the same application
analysed twice with the same model version and mapping version shall produce
the same verdicts"*. `numeric(5,4)` stores exactly four decimal places with no
representation error; `FLOAT` stores a binary approximation. Two confidences
that should compare equal can differ in the last bits, and ALG-8 and ALG-9 both
compare and sort on confidence. In practice the risk to a *verdict* is small,
because ALG-8 branches on threshold comparisons rather than equality, but
evidence *ordering* under ALG-9 sorts on these values and a tie-break on
near-equal floats is exactly where instability would appear.

**Classification: D-10.** Affects four tables.

## Primary key widths

Phase 3 specifies `bigserial` for every primary key. The implementation uses
`INTEGER` on `application`, `model_version`, `taxonomy_mapping_version`,
`taxonomy_mapping_entry` and `evaluation_run`, and `BIGINT` elsewhere.

At NFR-19's ceiling of about 1,000 applications this has no practical
consequence. **Classification: B**, recorded for completeness.

## Index comparison against §10.3

| §10.3 requires | Implemented | Status |
|---|---|---|
| `lower(application.package_name)` | `ix_application_lower_package` | **A** |
| `lower(application.app_name)` | `ix_application_lower_name` | **A** |
| `disclosure_snapshot(app_id, collected_at DESC)` | `ix_snapshot_app_source(app_id, source_type, retrieved_at)` | B/D — extra column, **no DESC** |
| `policy_segment(snapshot_id, seq_no)` | `ix_segment_snapshot` | **A** |
| `extracted_practice(segment_id)` | `ix_practice_segment_category` | A (superset) |
| `extracted_span(practice_id)` | `ix_span_practice` | A (superset) |
| `alignment_judgement(audit_id, ds_category)` | `ix_judgement_audit_category` | **A** |
| `verdict(audit_id)` | `ix_verdict_audit` | **A** |
| `evidence_record(verdict_id)` | `ix_record_verdict` | A (superset) |
| `audit_run(status)` | `ix_audit_queue(status, requested_at)` | A (superset) |
| `audit_run(app_id, started_at DESC)` | `ix_audit_app_history(app_id, requested_at)` | B/D — **no DESC** |
| `gold_annotation(app_id, ds_category)` | `ix_gold_app(app_id)` only | **E — ds_category missing** |

Additional indexes not in §10.3, all class C: `ix_snapshot_sha256`,
`ix_model_active`, `ix_declared_snapshot_category`,
`ix_taxonomy_version_active`, `ix_taxonomy_entry_lookup`, `ix_practice_model`,
`ix_evaluation_model`, `ix_metric_run`.

The two missing `DESC` orderings matter for the history queries of FR-25 and
FR-26, which read newest-first. PostgreSQL can scan a B-tree backwards, so the
effect is small, but the baseline asked for them explicitly.

## Naming convention

The implementation renamed most primary keys to `<table>_id` in full
(`declared_practice_id` for `declared_id`) and all offset columns to
`char_start` / `char_end`. These are consistent and defensible, but there are
**63 columns** whose names differ from the approved data dictionary. Anyone
reading Phase 3 alongside the code needs the mapping, which is why it is
tabulated per table above.

**Recommendation:** keep the implementation names and add an appendix to the
Phase 3 report, or to the Phase 4 report, carrying this mapping. Renaming 63
columns now would invalidate the 169 passing tests for no functional gain.

---

# Part 3 — The verdict confidence omission (audit item 2)

## Confirmed

The omission is real. Three approved sources require it.

**Phase 3 §10.2, `verdict` table:**
> `verdict_id bigserial PK; audit_id bigint FK; ds_category text; verdict_value
> text; confidence numeric(5,4) (nullable); UNIQUE(audit_id, ds_category)`

**Phase 3 §4.2, F-19 — assignCategoryVerdict, Processing step 3:**
> "Set the verdict confidence from the judgement that determined the outcome;
> for an Undetermined verdict, record the highest sub-threshold confidence
> instead."

**Phase 3 §4.2, F-19, Output:**
> "One verdict record for the category, carrying value and confidence."

**Phase 2, NFR-07 — Confidence visibility:**
> "Confidence values and Undetermined outcomes shall be visible to the user
> rather than hidden behind a binary result."

The implementation has it in neither place:

- `backend/app/db/models.py`, class `Verdict` — no `confidence` column.
- `analysis/verdict/models.py`, class `CategoryVerdict` — no `confidence` field.
- `analysis/verdict/verdict_engine.py`, `assign_category_verdict` — computes no
  confidence.

**This is my error, not a baseline ambiguity.** The Milestone 7 report stated
that ALG-8 was implemented exactly as specified. It was implemented exactly as
specified *for verdict selection*, and step 3 of F-19's processing was missed
entirely. The 169 passing tests did not catch it because no test asserted that
a verdict carries a confidence — the tests verified what was built rather than
what was required. A traceability row saying "Implemented and verified" against
F-19 is currently wrong, and is corrected in Part 6.

## Consequence

NFR-07 cannot be met as the system stands. The frontend has nothing to display:
a report would show five verdict names with no indication of how strongly each
is held, which is the "binary result" NFR-07 exists to prevent. Screen S4 and
the F-24 report view both depend on it.

## Proposed correction

Three changes, in this order. **Not implemented — awaiting approval.**

### C1. Domain object

Add to `CategoryVerdict` in `analysis/verdict/models.py`:

```
confidence: float | None = None
```

Nullable, matching the baseline. It is None exactly when the category's verdict
rests on no judgement at all — the step 5 case where neither source mentions
the category, and the step 4 case where a declared category produced no
judgements. There is no confidence to report in those cases and inventing one
would be fabrication.

### C2. Engine

In `assign_category_verdict`, set confidence per the F-19 rule:

| Verdict | Source of confidence |
|---|---|
| Contradictory | the highest-confidence decisive CONTRADICTS judgement |
| Consistent, affirmative agreement | the highest-confidence decisive SUPPORTS judgement |
| In-policy-not-declared | the highest-confidence decisive SUPPORTS judgement |
| Declared-not-in-policy | the highest-confidence decisive NO_MATCH judgement, or None when there were no judgements at all |
| Undetermined | **the highest sub-threshold confidence**, per F-19 step 3 |
| Consistent, neither source mentions | None |

"The judgement that determined the outcome" is the highest-confidence judgement
in the class that triggered the ALG-8 step. For Undetermined the baseline is
explicit that the value is the highest *sub-threshold* confidence, which is the
strongest thing the system saw without being able to trust it.

### C3. ORM column

Add to `Verdict` in `backend/app/db/models.py`:

```
confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
```

With `CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))`,
consistent with the other confidence columns.

### Tests to add

- Each verdict carries the confidence of the judgement that decided it.
- Undetermined carries the highest sub-threshold confidence, not the highest
  confidence overall, and not None.
- Confidence is None only in the two no-judgement cases.
- A confidence is never invented for a Consistent-by-silence verdict.

### Approval status

| Question | Answer |
|---|---|
| Does this need faculty approval? | **No.** It restores the approved design. Approval is needed to *deviate*, not to comply |
| Does it need a REQUIREMENT_CHANGE_LOG entry? | **No** — nothing changes. It needs a CONSISTENCY_LOG entry recording the omission and its correction |
| Does it change the schema? | Yes — one nullable column plus one CHECK on `verdict`. It is additive and cannot invalidate existing rows |
| Does it need your approval before I write it? | **Yes**, per your gate. It is ready to implement on your word |

---

# Part 4 — Alembic migration strategy (audit item 3)

## Has `0001_baseline` been applied?

**I cannot determine this from here, and I will not guess.**

The shell available to me in this session runs in a Linux virtual machine with
only your project folder mounted. It cannot see processes, services or
databases on macOS. What I can report is circumstantial:

| Evidence | Observation |
|---|---|
| `docker` on your Mac | Reported `command not found` at 15:19 today |
| `.env` in the project folder | **Does not exist** |
| `docker-compose.yml` behaviour without it | Refuses to start: `POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set in .env` |
| Alembic artefacts in the repository | None |

Taken together these make it very likely that no database exists and the
baseline has never been applied. **Confirm with this, which only reads:**

```bash
cd "/Users/anshu/Documents/Major Project"
.venv/bin/python -c "
import os, sys
os.environ.setdefault('POSTGRES_PASSWORD', 'x')
sys.path[:0] = ['.', 'backend']
from sqlalchemy import create_engine, inspect, text
from app.config import Settings
s = Settings(postgres_password=os.environ['POSTGRES_PASSWORD'])
try:
    e = create_engine(s.database_url)
    with e.connect() as c:
        names = inspect(e).get_table_names()
        print('connected. tables:', len(names))
        print('alembic_version present:', 'alembic_version' in names)
        if 'alembic_version' in names:
            print('stamped revision:', c.execute(text('SELECT version_num FROM alembic_version')).scalar())
except Exception as ex:
    print('no database reachable:', type(ex).__name__)
"
```

It opens a connection, lists table names and reads one row. It creates nothing,
drops nothing and writes nothing.

## What `create_all()` in a migration costs

`0001_baseline_schema.py` calls `Base.metadata.create_all(op.get_bind())`. The
reasoning recorded at the time — one source of truth, no transcription drift —
still holds for a *first* revision. The cost appears from the second revision
onward.

**What breaks:**

1. **The baseline is not frozen.** A normal migration is a fixed historical
   record: revision 0001 creates exactly the columns that existed when it was
   written. This one creates whatever the models say *at the moment it runs*. If
   the verdict confidence column is added tomorrow, a teammate running
   `alembic upgrade head` on a fresh database gets a schema **with** confidence
   from revision 0001, while a teammate who already ran it yesterday has one
   **without** it and no revision to carry them forward. The two databases
   differ while both report `0001_baseline`.

2. **Autogenerate has no reference point.** `alembic revision --autogenerate`
   compares the live database against the models. If the live database was
   built from today's models, the diff is empty and no second revision is
   produced, even though the schema changed.

3. **Downgrade is destructive.** `Base.metadata.drop_all` drops every table,
   not the ones this revision created. On a baseline that happens to be the
   only revision the effect is the same; after a second revision it is not.

**What does not break:** a single developer on a single fresh database. The
defect is invisible until the schema changes or a second person runs it — which
is to say, it is invisible until exactly now.

## Two strategies, and the difference between them

### Strategy A — if the baseline has **not** been applied anywhere (most likely)

Freeze it. Replace the `create_all` body with explicit `op.create_table`,
`op.create_index` and `op.create_check_constraint` calls that spell out the
schema as it is today, including the verdict confidence correction if you
approve it. Nothing has been stamped, so nothing needs migrating; the revision
id stays `0001_baseline` and the file simply becomes honest about what it
builds.

Because autogenerate needs a live connection, the explicit body is produced by
bringing up PostgreSQL on your Mac against an **empty** database and running
`alembic revision --autogenerate`, then transplanting the generated body into
`0001_baseline_schema.py` and discarding the generated file. That reads an
empty database and writes nothing to your project database.

- Risk: none. No data exists.
- Effort: one session.
- Result: a conventional, reproducible migration history from the first
  revision.

### Strategy B — if the baseline **has** been applied

Leave revision 0001 exactly as it is. Do not rewrite an applied revision: any
database already stamped `0001_baseline` would silently diverge from its
recorded history, and rewriting applied migrations is how migration histories
become untrustworthy.

Instead add `0002_freeze_and_corrections`, which:

- is written explicitly, with `op.add_column` for the verdict confidence and
  any other approved correction;
- is guarded so it is idempotent where a column may already exist;
- carries a comment stating that 0001 was a metadata build and that 0002 is the
  first explicit revision.

From 0002 onward the history is conventional. 0001 stays as an acknowledged
soft baseline.

- Risk: low. Forward-only, additive.
- Effort: one session.
- Result: history preserved, no existing database disturbed.

**The difference in one sentence:** Strategy A rewrites a revision nobody has
run, which is safe and tidy; Strategy B never touches what has run and adds a
step on top, which is safe but leaves 0001 permanently imprecise. Which applies
is decided by the command above, not by preference.

**No database will be dropped, reset or recreated under either strategy.**

---

# Part 5 — Real PostgreSQL verification (audit item 4)

## The current state, stated plainly

`tests/integration/test_migration_baseline.py::test_postgresql_schema_is_not_verified_here`
is an unconditional `pytest.skip`. It documents the gap; it verifies nothing. No
part of this project has ever run against PostgreSQL. JSONB, BIGINT, the
functional `lower()` indexes, and all 27 CHECK constraints are verified against
SQLite only.

## Proposed test — not yet written

A new file, `tests/integration/test_postgresql_schema.py`, marked
`@pytest.mark.integration` and **skipped unless an explicit environment
variable names a test database**. It never falls back to the project database.

### Safety design, which matters more than the assertions

1. The connection URL comes from `TEST_DATABASE_URL` only. If it is unset,
   every test skips. There is no default and no fallback to `.env`.
2. The test refuses to run unless the database name ends in `_test`. A URL
   pointing at `privacy_auditor` aborts with a clear message instead of
   touching it.
3. Each test runs inside a transaction that is **rolled back**, so even the
   test database is left unchanged.
4. `drop_all` appears nowhere in the file.

```python
# sketch, not committed
TEST_URL_VAR = "TEST_DATABASE_URL"

@pytest.fixture(scope="session")
def pg_engine():
    url = os.environ.get(TEST_URL_VAR)
    if not url:
        pytest.skip(f"{TEST_URL_VAR} is not set")
    if not make_url(url).database.endswith("_test"):
        pytest.fail(
            f"{TEST_URL_VAR} must name a database ending in _test. "
            "Refusing to touch a database that may be the project's."
        )
    ...
```

### What it would verify

| # | Check | How |
|---|---|---|
| 1 | Alembic upgrade executes | run `alembic upgrade head` against the test database and assert `alembic_version` holds `0001_baseline` |
| 2 | Sixteen tables exist with the right names | `inspect(engine).get_table_names()` |
| 3 | **JSONB**, not JSON | query `information_schema.columns` for `audit_run.threshold_config` and assert `udt_name = 'jsonb'` |
| 4 | **BIGINT** primary keys | assert `data_type = 'bigint'` on the eleven BIGINT keys — this is the check SQLite can never make, since it sees INTEGER |
| 5 | **Functional indexes** | query `pg_indexes.indexdef` for `ix_application_lower_name` and assert the definition contains `lower` |
| 6 | All 27 CHECK constraints present | `pg_constraint` where `contype = 'c'`, compared against the names in the metadata |
| 7 | All 8 UNIQUE constraints present | `pg_constraint` where `contype = 'u'` |
| 8 | NOT NULL where required, especially the seven on `audit_run` | `information_schema.columns.is_nullable` |
| 9 | **Invalid records are rejected by PostgreSQL** | re-run the critical insert attempts from `test_schema.py` — the sixth verdict value, `Undetermined` in the gold set, an evidence record with no quote, an absence record with a quote — and assert `IntegrityError` from the real engine |
| 10 | `timestamptz` not naive timestamp | assert `udt_name = 'timestamptz'` on the datetime columns |

Item 9 is the one that matters most: the SQLite suite proves the constraints are
*declared*, and only PostgreSQL proves they are *enforced by the database the
system will actually run on*.

### Exact steps to execute it

On your Mac, after Docker Desktop is installed:

```bash
cd "/Users/anshu/Documents/Major Project"

# 1. Configuration, if not already present
cp .env.example .env
#    edit .env and set POSTGRES_PASSWORD

# 2. Start only the database container
docker compose up -d database

# 3. Create a SEPARATE test database. The project database is untouched.
docker exec -i auditor_database psql -U auditor -d privacy_auditor \
  -c "CREATE DATABASE privacy_auditor_test OWNER auditor;"

# 4. Point the tests at it
export TEST_DATABASE_URL="postgresql+psycopg://auditor:<password>@127.0.0.1:5432/privacy_auditor_test"

# 5. Apply the baseline to the TEST database only
cd backend
POSTGRES_DB=privacy_auditor_test ../.venv/bin/alembic upgrade head
cd ..

# 6. Run the integration tests
.venv/bin/pytest -m integration -v
```

Step 3 creates a second database alongside yours. Nothing in this sequence
drops, resets or modifies `privacy_auditor`.

**Until step 6 has run and its output is in hand, nothing in this project may
describe the PostgreSQL schema as verified.** The traceability document already
carries that row as "Not verified" and it stays that way.

---

# Part 6 — Corrected implementation status (audit item 5)

The Milestone 7 report overstated completeness in two places. Both are
corrected here and in `docs/IMPLEMENTATION_TRACEABILITY.md`.

| Component | Previously reported | Accurate status |
|---|---|---|
| F-19 verdict assignment | "Implemented and verified" | **Partially implemented.** The ALG-8 precedence is implemented and tested. F-19 processing step 3, verdict confidence, is **not implemented** |
| F-15 taxonomy mapping | "Implemented and verified" | **Mechanism implemented and tested. No mapping rules exist.** `TaxonomyMapper` performs versioned lookup correctly against rules supplied in tests. The reviewed OPP-115 to Data Safety rules have not been authored. Until they are, F-15 cannot run on real data |
| F-14, F-16, F-17, F-20, F-21, F-22 | Implemented and verified | Unchanged — accurate |
| F-18 semantic alignment | Not implemented, M6 | Unchanged — accurate. Option A decided; no code |
| Confidence thresholds | "placeholders" | **Provisional.** All three are 0.50 and uncalibrated. Calibration requires the gold set, which does not exist. No threshold in this system has been justified by evidence |
| Persistence of verdicts | Not implemented, M8 | Unchanged — accurate. The engine returns domain objects and writes nothing to the sixteen tables |
| End-to-end audit | — | **Does not exist.** No audit has ever been run. The engine has never received input from a model |
| M2 schema | "Implemented and verified" | **Implemented and verified on SQLite only.** PostgreSQL unverified; see Part 5 |

## What the project can honestly claim today

- A repository, dependency set and test environment that work on two machines
  and two Python versions.
- Sixteen tables whose constraints are declared and exercised on SQLite.
- A verdict and evidence engine whose precedence logic, abstention propagation
  and evidence integrity are unit-tested, missing one specified output field.
- A verified local copy of OPP-115: 115 policies, 23,194 annotated practices,
  77,906 usable spans, checksum manifest committed.

## What it must not claim

- That the database schema matches Phase 3. It does not; see Part 1.
- That PostgreSQL has been verified. It has not been contacted.
- That F-15 can map anything. It has no rules.
- That any threshold is appropriate. None is calibrated.
- That the pipeline works end to end. No stage upstream of F-14 exists.

---

# Part 7 — Finding register and approval request

## Findings requiring restoration (class E) — no faculty approval needed

These restore the approved design. They need your go-ahead to implement, not a
change-log entry.

| ID | Finding | Proposed correction | Effort |
|---|---|---|---|
| **E-5** | `verdict.confidence` missing; breaks F-19 step 3 and NFR-07 | Part 3, changes C1 to C3 plus tests | Small |
| **E-4** | `extracted_span.model_version_id` missing; spans unattributable to the extractor | Add the NOT NULL FK | Small |
| **E-6** | `evaluation_metric.scope` missing | Add the column | Small |
| **E-1** | `application.store_category` missing | Add nullable; the scraper may not always supply it | Small |
| **E-2** | `disclosure_snapshot.status` missing | Resolve together with D-1, since the per-source split changes what a status means | Small |
| **E-3** | `extracted_practice.practice_type` missing | Add; needs the team to confirm its value vocabulary from Phase 3 §4.2 | Small |
| — | `gold_annotation` index missing `ds_category` | Extend the index | Trivial |
| — | Two indexes missing `DESC` | Add `.desc()` to both | Trivial |

## Findings requiring a decision (class D) — faculty approval and a change-log entry

| ID | Deviation | Options | My recommendation |
|---|---|---|---|
| **D-1** | `disclosure_snapshot` split per source; `audit_run` holds two snapshot FKs | (a) keep the split and amend Phase 3 §10.2 (b) revert to one row with two URL columns | **(a) Keep.** It handles the partial-retrieval case Phase 1 called the highest-probability failure. But this is a design decision, not mine to settle |
| **D-2** | `declared_practice` uses two booleans instead of `declaration_type` + `is_declared` | (a) keep (b) restore, enabling explicit negative declarations | **(b) Restore the capability.** An explicit "marked as not collected" can change an ALG-8 verdict and is currently unrepresentable |
| **D-3** | `model_version` task vocabulary differs from Phase 3's `classifier`/`extractor`/`aligner` | (a) keep (b) adopt the approved strings | **(b) Adopt the approved strings.** No cost now; growing cost later |
| **D-4** | `model_version.trained_at` nullable | (a) keep (b) restore NOT NULL | **(a) Keep.** The zero-shot baseline under D-01 is never trained. Record as an approved deviation |
| **D-5** | `UNIQUE(task, version_label)` instead of `UNIQUE(component, variant, trained_at)` | (a) keep (b) restore (c) both | **(c) Both.** They answer different questions and neither is expensive |
| **D-6** | `alignment_judgement` has two nullable sides instead of one NOT NULL `practice_id` | (a) keep (b) revert | **(a) Keep.** The baseline as written cannot represent a declared category with no policy practice, which is the project's central finding type |
| **D-7** | `evidence_record.quoted_text` nullable | (a) keep (b) revert to NOT NULL | **(a) Keep.** A NOT NULL would force invented or empty text into absence records, which NFR-06 forbids |
| **D-8** | `evaluation_run` records one model instead of four versions | (a) keep (b) restore all four | **(b) Restore.** Without it F-31 cannot record an end-to-end evaluation at all |
| **D-9** | `evaluation_metric.class_label` replaced the baseline's `ds_category` | (a) keep (b) restore `ds_category` (c) both | **(c) Both.** Per-category metrics are required by Phase 3; per-class metrics are required by safeguard 4 of decision D-01 |
| **D-10** | Confidence columns are FLOAT, not `numeric(5,4)` | (a) keep (b) change to NUMERIC | **(b) Change.** NFR-08 asks for reproducibility and ALG-9 sorts on these values |

## Findings in the approved documents themselves

These are errors in Phase 3, not in the code. They need the faculty guide's
ruling and a correction to the report, not a code change.

| ID | Issue | Effect |
|---|---|---|
| **DOC-1** | §10.3 says `audit_run` has "seven foreign keys"; §10.2 lists six, and the prose's own arithmetic gives six | The implementation has seven only because of D-1. Resolving D-1 settles this |
| ~~**DOC-2**~~ | ~~§10.2 leaves `evidence_record.sentence_text` unmarked, which by its own rule means NOT NULL, while the same row's note says offsets are null for absence records~~ | **WITHDRAWN 2026-11-05.** The note nulls `segment_id` and the offsets, not the text. F-21 requires the absence record to store a generated statement, so NOT NULL is coherent and there is no contradiction |

## Consistency log correction

Entry **C-10** in `docs/PHASE4_CONSISTENCY_LOG.md` claimed the seven NOT NULL
foreign keys on `audit_run` matched the approved design. That was verified
against §10.3's count and not against §10.2's structure. The entry is corrected
by this audit and annotated in the log.

## Nothing has been changed

No model, migration, schema or database was modified in producing this
document. The 169 tests still pass and the working tree carries only this file
and documentation updates.

## What I need from you

1. Run the read-only command in Part 4 and tell me what it prints, so the
   Alembic strategy is chosen on fact.
2. Approve the class E restorations, individually or as a block.
3. Decide D-1 first. It is the largest, and D-2, DOC-1 and E-2 all depend on it.
4. Rule on D-2 through D-10, or defer any of them with a recorded reason.
5. Take DOC-1 to the faculty guide, since it is a defect in an approved
   report. DOC-2 was withdrawn on 2026-11-05 and needs no ruling.

**Note, 2026-11-05.** This register is superseded by
`docs/PHASE4_DECISION_TABLE.md`, which carries the revised assessment after
the team challenged D-2, D-6, D-7 and DOC-2. The entries above are annotated
in place rather than deleted so the original reasoning and its correction both
remain on the record.

I will implement nothing from this document until you say so.
