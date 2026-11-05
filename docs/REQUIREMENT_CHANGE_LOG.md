# Requirement Change Log

Any deviation from the approved Phase 2 SRS or Phase 3 design, with its
justification and approval state.

The approved documents are the baseline. Implementation does not get to change
them quietly. An entry here is a request until the faculty guide approves it.

| ID | Date | Approved baseline | Proposed change | Reason | Approval |
|---|---|---|---|---|---|

**No entries.** As of the end of Milestone 1, nothing implemented deviates from
the approved requirements or design.

---

## Known candidates for a future entry

These are not changes yet. They are places where a change may become necessary,
recorded now so they are not presented as surprises later.

1. **FR-12 span extraction scope.** If PolicyIE and PI-Extract licence terms do
   not permit our use, span supervision rests on OPP-115 alone. Phase 2
   assumption A-04 already states the project must not depend on those corpora,
   and Phase 3 records a documented fallback. Invoking that fallback would
   require an entry here and faculty approval.

2. **F-18 semantic alignment training data.** No public corpus labels
   (policy statement, Data Safety claim) pairs. Plan §7 sets out two options.
   Option A, which keeps the approved methodology, needs 300 to 500
   hand-labelled pairs. If neither option proves workable, any change to the
   approved three-task methodology would require an entry here.

3. **NFR-02 single-audit latency.** Phase 3 records design issue DI-1 as open:
   the 60-second CPU target is not yet demonstrated. It is measured in
   Milestone 6. If it cannot be met with the chosen models, the options are a
   smaller model or a revised target, and the latter would require an entry
   here.

---

## Proposed entries — awaiting team decision and faculty approval

Raised by the baseline audit on 2026-11-04. **None is approved and none is
implemented.** They are listed here so that the deviations already present in
the code are visible as pending requests rather than as settled design. Full
analysis in `docs/PHASE4_SCHEMA_BASELINE_AUDIT.md` Part 7.

| ID | Approved baseline | Deviation present in the code | Reason | Approval |
|---|---|---|---|---|
| D-1 | Phase 3 §10.2: `disclosure_snapshot` is one row per collection event holding both source URLs | One row per source, discriminated by `source_type`; `audit_run` carries two snapshot FKs | Handles a policy retrieved while the listing fetch fails, which Phase 1 identified as the highest-probability failure | **Pending** |
| D-2 | `declared_practice` has `declaration_type` + `is_declared` | Two booleans, `is_collected` and `is_shared` | Simpler, but cannot record an explicit "marked as not collected" | **Pending** |
| D-3 | `model_version.component` ∈ classifier, extractor, aligner | `task` ∈ classification, span_extraction, alignment | Clearer names, but the stored strings differ from the approved ones | **Pending** |
| D-4 | `model_version.trained_at` NOT NULL | nullable | The zero-shot NLI baseline under decision D-01 is never trained | **Pending** |
| D-5 | `UNIQUE(component, variant, trained_at)` | `UNIQUE(task, version_label)` | Human-readable version labels; changes what "the same model" means | **Pending** |
| D-6 | `alignment_judgement.practice_id` NOT NULL | Two nullable sides with a CHECK requiring one | The baseline cannot represent a declared category with no policy practice, which is the project's central finding type | **Pending** |
| D-7 | `evidence_record.sentence_text` NOT NULL by §10.2's own rule | `quoted_text` nullable with three CHECKs | NOT NULL would force empty or invented text into absence records, which NFR-06 forbids | **Pending** |
| D-8 | `evaluation_run` carries four version FKs | One `model_version_id` | Regression: an end-to-end pipeline evaluation cannot be recorded | **Pending** |
| D-9 | `evaluation_metric.ds_category` for per-category metrics | `class_label` for per-class metrics | Different quantity, not a rename. Both are needed | **Pending** |
| D-10 | Confidence columns `numeric(5,4)` | FLOAT | Affects NFR-08 reproducibility and ALG-9 ordering | **Pending** |

### Defects in the approved documents

These need a faculty ruling and a correction to the report, not a code change.

| ID | Document | Issue |
|---|---|---|
| DOC-1 | Phase 3 §10.2 vs §10.3 | §10.3 states `audit_run` has seven NOT NULL foreign keys; §10.2 lists six, and §10.3's own arithmetic gives six |
| DOC-2 | Phase 3 §10.2 | `evidence_record.sentence_text` is unmarked, so NOT NULL by the section's stated rule, while the same row's note says offsets are null for absence records |

### Not a change request

The missing `verdict.confidence` (audit E-5) is **not** listed above. Adding it
restores the approved design rather than departing from it, so it needs no
entry here. It is recorded in the consistency log as C-27.

---

## Milestone 3A — no change requested

M3A introduced **no deviation** from the approved Phase 2 SRS or Phase 3
design. No FR, NFR, GI or F-function identifier was altered, no database model
or migration was touched, and no new persistent schema was created.

Two things worth recording here even though neither is a change request:

1. **The corpus record format is a new artefact, not a change.** Phase 3
   specifies the database schema; it does not specify an on-disk corpus
   format, because the corpus is an input to the system rather than part of
   it. `record.json` schema version 1.0 is documented in
   `docs/M3_ACQUISITION_REPORT.md` section 5.

2. **The declaration normalisation rules are provisional.** They rest on
   Google's published documentation, not on an inspected page. If the pilot
   shows the published section carries fields the rules do not cover, or does
   not carry fields they assume, that correction will be made in the adapter
   and recorded here **only if** it affects an approved requirement. A change
   to the corpus format alone does not.

---

## D-1 ruled: Option A — no requirement changes

Date: 2026-11-05. **This entry records that no approved requirement changes.**

The team ruled for **Option A**: one `disclosure_snapshot` row per collection
event, exactly as approved in Phase 3 §10.2. Option B, the per-source split, is
not to be implemented.

So the approved design is unchanged, and what must change is the
**implementation**, which deviated from it. `disclosure_snapshot` currently
carries `source_type`, one `source_url` and one `content_sha256` per row, and
`audit_run` carries two snapshot foreign keys. M3B Part 2 restores the approved
structure in a new reversible revision; `0001_baseline_schema.py` and
`0002_pattern_ops` are not modified.

Two consequences recorded here because they touch approved documents:

1. **DOC-1 resolves.** Under Option A `audit_run` has **six** NOT NULL foreign
   keys, so Phase 3 §10.3's "seven" is the error and is amended to six. §10.2
   stands as approved.
2. **E-2 is satisfied by the restored design**, which includes a snapshot
   `status`. The value vocabulary still has to be defined, and will be recorded
   here when it is, because it is a new closed value set rather than an
   approved one.

Still not represented by any approved column, and **not** being added without
approval: `SecurityPractices`. See `docs/M3B_IMPLEMENTATION_PLAN.md` §7.

---

## Snapshot status vocabulary and the app-level no-collection flag

Date: 2026-11-05, with revision `0003_collection_event`.

**1. `disclosure_snapshot.status` values.** Phase 3 names the column (E-2) and
does not enumerate its values, so the set is the project's own:

`complete` · `declaration_only` · `policy_only` · `declaration_absent` ·
`fetch_failed` · `parse_failed`

`declaration_absent` is deliberately distinct from `fetch_failed`: a listing
that carries no Data Safety section is a fact about the application, while a
failed fetch is a fact about one moment. Treating them alike would let a
network problem read as an application declaring nothing.

**2. `disclosure_snapshot.declares_no_data_collected`** — a **nullable**
Boolean, added to implement the team's instruction to distinguish an explicit
app-level "this app doesn't collect or share any user data" declaration from an
absent data category. Three states: NULL (section not read), False (read, no
such statement), True (read, statement present).

This is an addition to the approved column list, not a change to any approved
requirement, and it is additive and nullable. It is recorded here rather than
applied silently. If the faculty would rather this be encoded in `status`, the
change is one migration and the vocabulary above gains a value.

**Still not represented, and not added:** `SecurityPractices` — encryption in
transit, deletion availability, independent security review. M3A parses it and
the filesystem corpus record retains it. No approved column holds it, it is not
required by FR-01 to FR-07, and it takes no part in verdict calculation.
