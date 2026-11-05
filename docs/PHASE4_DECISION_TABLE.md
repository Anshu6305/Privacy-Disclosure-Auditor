# Decision Table — D-1 to D-10, DOC-1, DOC-2

Prepared: 2026-11-05
For: team review and, for DOC-1 and DOC-2, the faculty guide
Source: `docs/PHASE4_SCHEMA_BASELINE_AUDIT.md`

**Nothing in this document has been implemented.** The class E omissions were
restored on 2026-11-04; every structural deviation below is still exactly as
the audit found it.

---

## Why this is the moment to decide

Three facts have changed since the audit, and together they make this the
cheapest point at which any of these decisions can be acted on.

1. **The project database is still empty.** `privacy_auditor` has 0 tables and
   no `alembic_version`. Nothing has been persisted, so no decision below
   requires migrating data — only changing a schema definition that has never
   been applied.
2. **The baseline is frozen but unapplied.** `0001_baseline` is now explicit
   and reproducible. While it remains unapplied to the project database, a
   schema change can still be folded into it. Once it is applied, every change
   needs its own revision, which is correct practice but more work and more
   history to explain in the report.
3. **The schema is verified on PostgreSQL.** Any change made now can be
   re-verified by the same 29 tests in under a minute.

After Milestone 8 begins persisting audits, the cost of each of these rises.
This is not pressure to decide hastily; it is the reason the audit was run
before M8 rather than after.

---

## Summary

| ID | One-line issue | Recommendation | Cost if done now |
|---|---|---|---|
| D-1 | Snapshot split one row per source, not per collection event | **Keep**, amend Phase 3 §10.2 | None — code already does it |
| D-2 | `declared_practice` cannot record an explicit negative declaration | **Change** — restore the capability | Small |
| D-3 | `model_version.task` vocabulary differs from the approved strings | **Change** — adopt the approved strings | Trivial |
| D-4 | `model_version.trained_at` nullable, baseline says NOT NULL | **Keep**, record as an approved deviation | None |
| D-5 | Unique key on `(task, version_label)` not `(component, variant, trained_at)` | **Add the baseline's as well** | Small |
| D-6 | `alignment_judgement` has two nullable sides, baseline has one NOT NULL | **Keep**, amend Phase 3 | None |
| D-7 | `evidence_record.quoted_text` nullable, baseline implies NOT NULL | **Keep** — resolved by DOC-2 | None |
| D-8 | `evaluation_run` records one model, baseline records four versions | **Change** — restore all four | Small |
| D-9 | `evaluation_metric` breaks down by class label, baseline by category | **Change** — support both | Small |
| D-10 | Confidence columns FLOAT, baseline `numeric(5,4)` | **Change** — convert the remaining three | Small |
| DOC-1 | Phase 3 §10.2 and §10.3 contradict each other on the FK count | Faculty ruling | Report correction |
| DOC-2 | Phase 3 §10.2 makes `sentence_text` NOT NULL and null at once | Faculty ruling | Report correction |

Six changes, three keeps-with-amendment, one keep-as-recorded, two document
corrections.

---

## D-1 — `disclosure_snapshot` granularity

**Baseline.** One row per collection event, holding `source_url_listing` and
`source_url_policy` side by side, with one `policy_doc_path` and one hash.

**Implemented.** One row per source, discriminated by `source_type`.
`audit_run` therefore carries two snapshot foreign keys.

**Recommendation: keep the implementation and amend Phase 3 §10.2.**

The deciding argument is a failure mode Phase 1 identified as the project's
most likely: the Play Store scraper breaking while the policy fetch continues
to work, or the reverse. Under the baseline that collection event has no valid
row — one hash column, one path, and two sources that did not both arrive.
Under the implementation the successful source is stored with its own
provenance and the missing one is simply absent, which is also what F-07
requires provenance to record.

The honest cost: a reader of Phase 3 will not recognise the table. The
amendment has to be written, not just approved.

**If you decide the other way,** the revert touches `disclosure_snapshot`,
`audit_run`, and roughly fifteen tests. It is still cheap today.

**Depends on this:** D-2's wording, E-2, and DOC-1.

## D-2 — explicit negative declarations

**Baseline.** `declaration_type` plus an `is_declared` boolean.
**Implemented.** `is_collected` and `is_shared` booleans.

**Recommendation: change.** This is the one deviation I think is a genuine
loss rather than a trade.

Google's Data Safety form produces explicit negatives: a developer can present
a category and mark it as not collected. The baseline can store that — the row
exists with `is_declared` false. The implementation cannot distinguish it from
the category being absent from the declaration altogether; both read as
`false`.

That difference can change a verdict. ALG-8 step 2 resolves a decisive
SUPPORTS against the declaration state. A policy statement supporting a
practice, against a declaration that explicitly denies it, is arguably closer
to Contradictory than to In-policy-not-declared — and the system currently
cannot even see the distinction to reason about it.

**Proposed form:** add a nullable `is_declared` tri-state, or an
`explicitly_negative` boolean, keeping the existing booleans. Needs a short
decision on which, and a note in the report either way.

## D-3 — model component vocabulary

**Baseline.** `component` ∈ `classifier`, `extractor`, `aligner`.
**Implemented.** `task` ∈ `classification`, `span_extraction`, `alignment`.

**Recommendation: change to the approved strings.** The column name `task` can
stay — that is a defensible rename — but the stored values should be the
approved ones. Any query, report figure or viva answer written from Phase 3
will otherwise not match what is in the database.

Cost is trivial today because `model_version` has no rows. It stops being
trivial the moment it does.

## D-4 — `trained_at` nullable

**Baseline.** NOT NULL. **Implemented.** Nullable.

**Recommendation: keep, and record it as an approved deviation.** The zero-shot
NLI baseline chosen under decision D-01 is never trained and so has no training
date. Forcing a value would mean inventing a timestamp, which is worse than a
null that means exactly what it says.

## D-5 — model version uniqueness

**Baseline.** `UNIQUE(component, variant, trained_at)`.
**Implemented.** `UNIQUE(task, version_label)`.

**Recommendation: keep the implemented one and add the baseline's.** They
answer different questions. The implemented constraint stops two models
sharing a human-readable label. The baseline's stops the same component being
registered twice from one training run. Both are cheap and neither conflicts.

One wrinkle to decide: with `trained_at` nullable under D-4, the baseline's
constraint does not constrain untrained models, because PostgreSQL treats
nulls as distinct in a unique index. That is acceptable but should be stated
rather than discovered later.

## D-6 — judgement sides

**Baseline.** `practice_id` NOT NULL.
**Implemented.** Nullable `declared_practice_id` and `extracted_practice_id`,
with a CHECK requiring at least one.

**Recommendation: keep the implementation and amend Phase 3.**

Under the baseline every judgement must reference an extracted policy
practice. A declared category with no policy practice therefore cannot have a
judgement row at all — and that is precisely the input to a
Declared-not-in-policy verdict, the project's central finding type. The
baseline as written cannot represent the thing the system exists to find.

This is not a preference. It is a defect in the approved design that the
implementation happens to have corrected, and the report should say so.

## D-7 — `quoted_text` nullability

**Recommendation: keep.** Resolved by DOC-2: §10.2's own rule makes
`sentence_text` NOT NULL while the same row states that offsets are null for
absence records. A NOT NULL quote would force an empty string or invented text
into every absence record, and NFR-06 forbids generated evidence.

The three CHECK constraints that enforce the distinction are now verified
against PostgreSQL, so the implementation's behaviour is demonstrated rather
than asserted.

## D-8 — evaluation provenance

**Baseline.** Four version foreign keys: mapping, classifier, extractor,
aligner. **Implemented.** One `model_version_id`.

**Recommendation: change — restore all four.** This is the second most
consequential finding after the verdict confidence, and for the same kind of
reason.

F-31 evaluates the pipeline end to end against the gold set. With one model
reference, such a run cannot be recorded faithfully: it would have to be filed
against an arbitrary one of the three models, and the mapping version — which
materially affects results — would not be recorded at all. GI-05's
baseline-versus-improved comparison then cannot attribute a change to a
component.

`evaluation_run` has no rows. The change is a schema edit and a handful of
tests.

## D-9 — metric breakdown

**Baseline.** `scope` plus nullable `ds_category`: metrics per Data Safety
category and overall. **Implemented.** `class_label`: metrics per predicted
class.

**Recommendation: support both.** They are different quantities, and the
project is committed to each.

- Per **category** is what Phase 3 §10.2 asks for and what the report's results
  section needs: how the system performs on Location versus Personal info.
- Per **class** is required by safeguard 4 of decision D-01: precision, recall
  and F1 for SUPPORTS, CONTRADICTS and NO_MATCH.

`scope` was restored on 2026-11-04 but does not on its own make per-category
metrics storable; `ds_category` is still absent. Adding it alongside
`class_label`, with `scope` distinguishing the rows, satisfies both.

## D-10 — confidence column type

**Baseline.** `numeric(5,4)` on `extracted_practice`, `extracted_span`,
`alignment_judgement` and `verdict`. **Implemented.** FLOAT on the first three;
`verdict.confidence` was restored as NUMERIC on 2026-11-04.

**Recommendation: change the remaining three.**

Two arguments, one stronger than it was at the time of the audit.

- NFR-08 requires that the same application analysed twice with the same
  versions produces the same verdicts. ALG-9 sorts evidence on confidence, and
  a sort over binary-approximated floats is where instability would first
  appear.
- The schema is now **inconsistent with itself**: one confidence column is
  NUMERIC and three are FLOAT. That asymmetry was a deliberate, recorded
  consequence of restoring E-5 to its approved type, but it is not a good
  resting state.

PostgreSQL returns `NUMERIC` as `Decimal`. The engine compares and sorts these
values, so the change needs the comparison sites checked — a small, bounded
piece of work, and the existing tests cover those paths.

---

## DOC-1 — Phase 3 contradicts itself on the foreign-key count

§10.3: *"All seven foreign keys from audit_run are NOT NULL, so an audit cannot
be stored without recording the snapshot it analysed and the four versions that
produced it."*

§10.2 lists six: `app_id`, `snapshot_id`, `mapping_version_id`,
`classifier_version_id`, `extractor_version_id`, `aligner_version_id`. The
prose's own arithmetic — one snapshot, four versions, one application — also
gives six.

The implementation has seven, but only because of the D-1 split. **Deciding
D-1 resolves this:** keep the split and seven is correct, with §10.2 amended;
revert and six is correct, with §10.3 amended.

**For the faculty guide**, because it is an error in an approved document.

## DOC-2 — Phase 3 makes a column NOT NULL and nullable at once

§10.2 opens with *"Every column is NOT NULL unless marked nullable"* and then
gives `evidence_record` as `... record_type text; sentence_text text;
start_offset int (nullable); end_offset int (nullable); rank int`, with the
note *"segment_id and offsets are null for absence records"*.

`sentence_text` is unmarked, so NOT NULL by the stated rule — yet an absence
record by definition has no sentence. The two statements cannot both hold.

**Recommended correction:** mark `sentence_text` nullable in §10.2 and add
that an absence record carries a reason instead of a quote. That matches
NFR-06 and what the implementation enforces.

**For the faculty guide.**

---

## What I will not do without your decision

No structural schema change. The class E restorations are done; D-1 to D-10
are untouched and will stay untouched until you rule on them.

If you approve a subset, the order that minimises work is: **D-1 first**
(D-2's wording, E-2 and DOC-1 all follow from it), then D-3, D-5, D-8, D-9,
D-10 in any order, then D-2 last because its design question is the only one
that is not purely mechanical.
