# Decision Table — D-1 to D-10, DOC-1, DOC-2

Prepared: 2026-11-05
Revised: 2026-11-05 after team challenge to D-2, D-6, D-7 and DOC-2
For: team review; DOC-1 and DOC-2 for the faculty guide
Source: `docs/PHASE4_SCHEMA_BASELINE_AUDIT.md`

**Nothing in this document has been implemented.** No model, migration,
database or application code was changed in producing this revision.

---

## Revisions in this edition

The team challenged three findings. All three challenges were correct, and my
earlier recommendations were wrong. The reasoning and the evidence are in the
sections below.

| Finding | Earlier recommendation | Revised recommendation | Why it changed |
|---|---|---|---|
| **D-6** | Keep the nullable two-sided judgement; amend Phase 3 | **Restore the approved NOT NULL structure** | Demonstrated: all five verdicts are reachable with practice-backed judgements only. A declared category with no policy practice needs an *empty judgement list*, not a one-sided judgement row |
| **D-7** | Keep `quoted_text` nullable | **Restore `sentence_text` NOT NULL**, content by record type | F-21 requires a fixed system-generated absence statement *stored in the record*. The null is the segment reference, not the text |
| **DOC-2** | A contradiction in Phase 3 | **Not a contradiction. Withdrawn** | §10.2's note nulls `segment_id` and the offsets, never `sentence_text`. The two statements are consistent |
| **D-2** | Change — add an explicit-negative capability | **Withdrawn as stated.** The premise is unverified and probably false | The published Data Safety section is positive-only. No per-category negative exists in acquirable data |

Four of my twelve positions were wrong in the same direction: I treated the
approved design as defective where it was not, and credited the
implementation with corrections it had not made.

---

## Classification used throughout

| Class | Meaning | Who decides |
|---|---|---|
| **Compliance restoration** | The implementation departs from the approved design with no justification. Restoring it is conformance, not change | Team go-ahead only. No faculty approval, no change-log entry |
| **Implementation deviation** | The implementation departs from the approved design for a stated reason, and keeping it means amending the approved design | **Faculty approval** and a `REQUIREMENT_CHANGE_LOG.md` entry |
| **Document correction** | The approved report is internally inconsistent or wrong | **Faculty ruling**; the report is corrected, not the code |

---

## Summary

| ID | Issue | Revised recommendation | Class |
|---|---|---|---|
| D-1 | Snapshot granularity: per source, not per collection event | Keep the split | **Implementation deviation** |
| D-2 | Explicit negative declarations | **Withdrawn.** No schema change | — |
| D-3 | `model_version` task vocabulary | Adopt the approved values | **Compliance restoration** |
| D-4 | `trained_at` nullable | Keep | **Implementation deviation** |
| D-5 | Model-version uniqueness | Add the baseline's constraint as well | **Compliance restoration** (additive) |
| D-6 | Judgement references | **Restore NOT NULL; drop `declared_practice_id`** | **Compliance restoration** |
| D-7 | Evidence text nullability | **Restore `sentence_text` NOT NULL** | **Compliance restoration** |
| D-8 | `evaluation_run` records one model, not four versions | Restore all four | **Compliance restoration** |
| D-9 | Metric breakdown by class, not category | Support both | **Compliance restoration** plus an addition |
| D-10 | Confidence columns FLOAT, not `numeric(5,4)` | Convert the remaining three | **Compliance restoration** |
| DOC-1 | §10.2 and §10.3 disagree on the FK count | Amend whichever section D-1 does not support | **Document correction** |
| DOC-2 | `sentence_text` NOT NULL vs null offsets | **Withdrawn — not a contradiction** | — |

Seven compliance restorations, two implementation deviations, one document
correction, two withdrawals. That is a very different picture from the first
edition, which claimed six changes and three amendments to the approved design.

---

# D-6 — Judgement references (REVISED: recommendation reversed)

## What I claimed

That `practice_id NOT NULL` makes a Declared-not-in-policy verdict
unrepresentable, and that this was a defect in the approved design which the
implementation had corrected.

## What the code actually does

Phase 3 F-19 takes *"the list of alignment judgements belonging to [the
category] with their abstention flags, and whether the category is declared in
the normalised declaration."* The declaration state is a **separate input**. It
does not travel inside a judgement.

So a declared category with no policy practice does not need a judgement at
all. It needs an empty list.

Run against the committed implementation:

```
D-6 EXPERIMENT 1: declared category, EMPTY judgement list
verdict           : Declared-not-in-policy
declared          : True
found_in_policy   : False
confidence        : None
records           : 1 -> absence
record has quote  : False
```

ALG-8 step 4 fires on the empty list and F-21 produces its absence record.
This is already covered by an existing passing test,
`test_declared_not_in_policy_with_no_judgements_at_all`, which I wrote and
then argued against.

The second experiment is the decisive one. Every judgement below references a
policy practice and **none carries a `declared_practice_id`** — the approved
Phase 3 structure:

```
scenario                       verdict                      conf  record
------------------------------------------------------------------------
Consistent (agreement)         Consistent                   0.93  -none-
Consistent (neither)           Consistent                   None  -none-
Declared-not-in-policy         Declared-not-in-policy       None  absence
Declared-not-in-policy (NM)    Declared-not-in-policy       0.95  absence
In-policy-not-declared         In-policy-not-declared       0.77  evidence
Contradictory                  Contradictory                0.84  evidence
Undetermined                   Undetermined                 0.31  inconclusive

distinct verdicts produced: 5 of 5
all five reachable: True
```

**All five verdicts are reachable under the approved structure.** The nullable
reference buys nothing.

## The argument against my own design

A declaration-only candidate is worse than unnecessary. F-18 performs
constrained textual entailment: it needs a premise, and a candidate with no
policy practice has no text to read. Building such a candidate invites the
aligner to emit a label for a pair with nothing to compare, and that label
would then flow into ALG-8 as though it meant something. The current fixture
`declaration_only_judgement()` carries `NO_MATCH` at confidence 0.95, a number
with no basis.

The approved design avoids this by construction: no practice, no judgement,
empty list, absence rule.

## Recommendation

**Restore the approved structure. Compliance restoration.**

| Change | Detail |
|---|---|
| `alignment_judgement.extracted_practice_id` | nullable → **NOT NULL** |
| `alignment_judgement.declared_practice_id` | **remove** — Phase 3 has no such column, and the declaration state reaches F-19 separately |
| `ck_judgement_has_at_least_one_side` | **remove** — made redundant by NOT NULL |
| `AlignmentCandidate` | require `mapped_practice`; `declared_item` becomes optional context for the aligner's prompt, not a stored reference |
| F-17 `_build_for_category` | stop emitting declaration-only candidates; a declared category with no practices yields no candidates |
| Tests | `declaration_only_judgement()` fixture removed; three tests that use it re-expressed against an empty judgement list |

**One consequence to accept knowingly.** Declared-not-in-policy will carry
`confidence = None` when there are no judgements, where today a
declaration-only judgement supplies a fabricated 0.95. The None is more
honest: F-19 step 3 sets confidence "from the judgement that determined the
outcome", and when no judgement determined it there is nothing to report. The
case where trusted NO_MATCH judgements exist still carries their confidence,
as the second experiment shows.

**Retained as additions (class C, no approval needed):**
`alignment_judgement.model_version_id`, which parallels the
`model_version_id` Phase 3 itself puts on `extracted_practice` and
`extracted_span`; and `threshold_applied`. `segment_id` is redundant once
`extracted_practice_id` is NOT NULL, since the segment is reachable through
the practice — worth removing for cleanliness, but harmless either way.

---

# D-7 and DOC-2 — Evidence text (REVISED: recommendation reversed, DOC-2 withdrawn)

## What I claimed

That §10.2 makes `sentence_text` NOT NULL while the same row says offsets are
null for absence records, and that these cannot both hold.

## What Phase 3 actually says

F-21 — recordAbsence, Processing:

> 1. Generate a fixed absence statement from a constant template naming the
>    category.
> 2. Store it as an evidence record of type "absence", **with no segment
>    reference**.
> 3. Optionally attach the highest-scoring sub-threshold candidates, clearly
>    marked as not accepted.

And its error handling:

> The absence statement is system-generated constant text and never model
> output (NFR-06).

F-22 — recordInconclusive:

> Collect the highest-confidence sub-threshold candidates with their
> confidence values; store with record type "inconclusive" ... If no
> candidates exist at all, the record states that no relevant statement was
> found above the candidate floor.

Both functions **always produce text**. What an absence record lacks is a
segment reference and offsets — exactly what §10.2's note says is null. The
note never mentions `sentence_text`.

**There is no contradiction. DOC-2 is withdrawn.** I misread a note about
`segment_id` and offsets as though it were about the text.

## The design the approved report describes

One text column whose content is determined by `record_type`:

| `record_type` | `sentence_text` | `segment_id`, offsets |
|---|---|---|
| `evidence` | verbatim policy sentence | present |
| `absence` | fixed system-generated statement from a constant template | null |
| `inconclusive` | sub-threshold candidate text, or a statement that nothing was found above the floor | present or null |

This is coherent, and NFR-06 is satisfied by `record_type` itself: a reader
and the interface both know, from the discriminator, whether the text came
from the policy or from a template. The team is right that a system-generated
absence statement is not fabricated evidence, and that NFR-06 already draws
that line.

## What the implementation does instead

Two columns: `quoted_text`, nullable, for verbatim policy text only; and
`reason`, for system-generated explanation. Three CHECK constraints enforce
that an evidence record has a quote with offsets and that an absence record
has no quote.

**The one genuine advantage** of the split, stated so the team can weigh it:
`quoted_text` can be guaranteed structurally to contain nothing but verbatim
policy text. Under the single-column design that guarantee rests on
`record_type` being read correctly everywhere it is consumed, rather than on
the column itself.

That is a real but modest benefit, and it is not what the approved design
specifies.

## Recommendation

**Restore the approved single-column design. Compliance restoration.**

| Change | Detail |
|---|---|
| `evidence_record.sentence_text` | one **NOT NULL** text column replacing `quoted_text` + `reason` |
| CHECK, evidence | `record_type <> 'evidence' OR (segment_id IS NOT NULL AND char_start IS NOT NULL AND char_end IS NOT NULL AND char_end > char_start AND char_end - char_start = length(sentence_text))` |
| CHECK, absence | `record_type <> 'absence' OR (segment_id IS NULL AND char_start IS NULL AND char_end IS NULL)` |
| F-20 | writes the verbatim segment text into `sentence_text` |
| F-21 | writes the fixed template statement into `sentence_text`, no segment reference |
| F-22 | writes candidate text, or the no-candidates statement |
| Tests | `test_evidence_records.py` and `test_schema.py` updated; the offset-matching guarantee is preserved by the evidence CHECK |

The verbatim guarantee is kept where it matters: the evidence CHECK still ties
the text length to the offsets, so an evidence record's text must be exactly
the span it points at.

**If the team prefers the two-column split**, it becomes an implementation
deviation needing faculty approval and a change-log entry. I no longer
recommend it.

---

# D-2 — Explicit negative declarations (REVISED: withdrawn)

## What I claimed

That Google's Data Safety form produces explicit negatives, that the baseline's
`is_declared` boolean can record them, and that the implementation's two
booleans cannot — so a capability was lost.

## What I did not do

Check whether an explicit per-category negative reaches us at all. The team
asked for a concrete example of three states. Establishing them requires
knowing what our acquisition layer returns.

**Our acquisition layer does not exist.** `acquisition/` contains one empty
`__init__.py`. Nothing in this project has ever parsed a Data Safety
declaration. I cannot show its output, and the first edition of this table
should not have reasoned as though I could.

What can be established is what the published Data Safety section contains,
since that is what any acquisition layer will read.

## What the published section contains

Google's developer documentation describes the section as showing *"what user
data your app collects or shares"*, and gives three whole-app presentations:
apps that collect or share nothing, apps that collect but do not share, and
apps that share. It does not state that per-category negatives are displayed.

A third-party Data Safety scraper's documented output is positive-only:
`collectedDataTypes`, `sharedDataTypes`, `dataCollectedPurposes`,
`dataSharedPurposes`, `dataCollectedItemCount`. There is no not-collected
list. Its documentation also warns that a missing field means the page gave no
usable value, **not** that a practice is absent.

## The three states, as far as they can be established

| State | Representable in the published section? | In our schema today |
|---|---|---|
| **A** Category absent from the declaration | Yes — the category is simply not in the collected or shared lists | `is_collected = false`, `is_shared = false`, or no row |
| **B** Category explicitly declared as not collected | **Not established, and probably not published.** The developer form asks per data type, but the published section appears to list only positives | Indistinguishable from A |
| **C** Category declared as collected or shared | Yes — appears in `collectedDataTypes` or `sharedDataTypes` | `is_collected` or `is_shared` true |

States A and B are therefore **not known to be distinct in our input data**.
A schema change to separate them would be solving a problem that has not been
shown to exist.

## Recommendation

**Withdrawn. No schema change.** My recommendation rested on an unverified
assumption about Google's published output, and the team was right to ask for
the evidence before the change.

## What the evidence does suggest, which is different

Two distinctions **are** real and neither is currently recordable.

1. **App-level explicit negative.** Google does publish *"the developer says
   this app doesn't collect or share any user data"* as a whole-app statement.
   That is meaningfully different from an app with a declaration that happens
   to omit a category, and it matters to ALG-8: an app declaring no collection
   at all, whose policy describes collecting email, is arguably closer to
   Contradictory than to In-policy-not-declared.

2. **Parse status.** "No Data Safety section could be read" is not the same as
   "a section was read and declared nothing." The scraper documentation warns
   about exactly this conflation, and F-33 needs the distinction to report a
   pipeline failure rather than a finding.

Both belong on `disclosure_snapshot`, and both are what the approved
`status text` column — audit finding **E-2** — is for. E-2 was deferred
pending D-1. **It should be reconsidered on its own merits**, with its value
set defined to cover at least: section parsed with declarations; section
parsed, app declares no collection; section absent; fetch failed.

That is a smaller change than the one I first proposed, it is a compliance
restoration rather than a deviation, and it addresses the distinction that
actually exists.

---

# Retained recommendations, with precise impact

## D-1 — `disclosure_snapshot` granularity

**Class: implementation deviation. Faculty approval and change-log entry.**

| | |
|---|---|
| Approved | One row per collection event: `source_url_listing`, `source_url_policy`, one `policy_doc_path`, one `policy_doc_sha256`, `status` |
| Implemented | One row per source, discriminated by `source_type`; `audit_run` holds `ds_snapshot_id` and `policy_snapshot_id` |
| Recommendation | **Keep**, amend Phase 3 §10.2 |
| Reason | Phase 1 identified scraper breakage as the project's highest-probability risk. One source succeeding while the other fails has no valid row under the approved shape: one hash column, one path, two sources that did not both arrive |
| Impact on the approved design | §10.2's `disclosure_snapshot` row is rewritten; §10.2's `audit_run` row gains a second snapshot FK; the ER diagram's snapshot cardinality changes from 1 per event to 1 per source |
| Change required if kept | None in code. A written amendment to §10.2 and Figure 14 |
| Change required if reverted | `disclosure_snapshot` merged to one row per event; `audit_run` loses one FK; `acquisition/` must then handle partial retrieval some other way; roughly 15 tests touched |
| Depends on it | E-2's value set, DOC-1 |

## D-3 — Model component vocabulary

**Class: compliance restoration.**

| | |
|---|---|
| Approved | `component` ∈ `classifier`, `extractor`, `aligner` |
| Implemented | `task` ∈ `classification`, `span_extraction`, `alignment` |
| Recommendation | Adopt the approved **values**; the column name `task` may stay as a rename |
| Impact on the approved design | None. This restores it |
| Change required | `analysis/vocabulary.py` `MODEL_TASKS`; the `ck_model_task` CHECK; the frozen migration; fixtures in four test files |
| Cost | Trivial today — `model_version` has no rows. Non-trivial once it does |

## D-4 — `trained_at` nullable

**Class: implementation deviation. Faculty approval and change-log entry.**

| | |
|---|---|
| Approved | NOT NULL |
| Implemented | Nullable |
| Recommendation | **Keep** |
| Reason | The zero-shot NLI baseline approved under decision D-01 is never trained and has no training date. A NOT NULL column would require inventing a timestamp |
| Impact on the approved design | §10.2 marks `trained_at` nullable, with a sentence explaining that an untrained zero-shot baseline is a legitimate model version |
| Change required | None in code |

## D-5 — Model-version uniqueness

**Class: compliance restoration (additive).**

| | |
|---|---|
| Approved | `UNIQUE(component, variant, trained_at)` |
| Implemented | `UNIQUE(task, version_label)` |
| Recommendation | **Keep the implemented constraint and add the approved one** |
| Reason | They answer different questions: one stops two models sharing a label, the other stops one component being registered twice from a single training run |
| Impact on the approved design | None. §10.2 may note the additional constraint |
| Change required | One `UniqueConstraint` on `ModelVersion`; the frozen migration; one test |
| Known limitation to state | With `trained_at` nullable under D-4, PostgreSQL treats nulls as distinct, so the approved constraint does not constrain untrained models. Worth stating in the report rather than discovering later |

## D-8 — Evaluation provenance

**Class: compliance restoration.**

| | |
|---|---|
| Approved | Four FKs: `mapping_version_id`, `classifier_version_id`, `extractor_version_id`, `aligner_version_id` |
| Implemented | One `model_version_id` |
| Recommendation | **Restore all four** |
| Reason | F-31 evaluates the pipeline end to end. With one reference, a run must be filed against an arbitrary model and the mapping version — which materially affects results — is not recorded at all. GI-05 cannot then attribute a change to a component |
| Impact on the approved design | None. This restores it |
| Change required | `EvaluationRun` gains three FKs and renames one; `ix_evaluation_model` becomes a composite or is supplemented; the frozen migration; two tests |
| Cost | Small. `evaluation_run` has no rows |

## D-9 — Metric breakdown

**Class: compliance restoration plus a retained addition.**

| | |
|---|---|
| Approved | `scope` plus nullable `ds_category`: per-category and overall metrics |
| Implemented | `scope` (restored 2026-11-04) plus `class_label`: per-predicted-class metrics |
| Recommendation | **Add `ds_category`; keep `class_label`** |
| Reason | They are different quantities and the project needs both. Per-category is what §10.2 asks for and what the results section reports; per-class is required by safeguard 4 of decision D-01 — precision, recall and F1 for SUPPORTS, CONTRADICTS and NO_MATCH |
| Impact on the approved design | §10.2 notes the additional `class_label` column |
| Change required | One nullable column; extend `uq_metric_unique_per_run` to include it; define the `scope` value set; the frozen migration; two tests |
| Note | Restoring `scope` alone did **not** make per-category metrics storable. That was stated when E-6 was implemented and remains true |

## D-10 — Confidence column type

**Class: compliance restoration.**

| | |
|---|---|
| Approved | `numeric(5,4)` on `extracted_practice`, `extracted_span`, `alignment_judgement`, `verdict` |
| Implemented | `verdict.confidence` is NUMERIC (restored 2026-11-04); the other three are FLOAT |
| Recommendation | **Convert the remaining three** |
| Reason | NFR-08 requires the same application analysed twice with the same versions to produce the same verdicts. ALG-9 sorts evidence on confidence, and a sort over binary-approximated floats is where instability appears first. The schema is also currently inconsistent with itself |
| Impact on the approved design | None. This restores it |
| Change required | Three column types; the frozen migration; PostgreSQL returns NUMERIC as `Decimal`, so every comparison and sort site in `gate.py`, `evidence_selector.py` and `verdict_engine.py` must be checked. Existing tests cover those paths |
| Cost | Small but not trivial — this is the only retained item with a code-behaviour component |

---

# DOC-1 — Foreign-key count (with both alternatives counted)

## The inconsistency

§10.3: *"All seven foreign keys from audit_run are NOT NULL, so an audit
cannot be stored without recording the snapshot it analysed and the four
versions that produced it."*

§10.2 lists six.

## The count under each D-1 outcome

**If D-1 is decided (a): keep the per-source split — 7 foreign keys**

| # | Column |
|---|---|
| 1 | `app_id` |
| 2 | `ds_snapshot_id` |
| 3 | `policy_snapshot_id` |
| 4 | `taxonomy_mapping_version_id` |
| 5 | `classification_model_id` |
| 6 | `span_model_id` |
| 7 | `alignment_model_id` |

§10.3's "seven" is correct. **§10.2 must be amended** to list two snapshot
foreign keys, and its prose should read "both snapshots it analysed and the
four versions".

**If D-1 is decided (b): revert to one row per collection event — 6 foreign keys**

| # | Column |
|---|---|
| 1 | `app_id` |
| 2 | `snapshot_id` |
| 3 | `mapping_version_id` |
| 4 | `classifier_version_id` |
| 5 | `extractor_version_id` |
| 6 | `aligner_version_id` |

§10.2 is correct. **§10.3 must be amended** from "seven" to "six".

## Proposed correction to Phase 3

Amend whichever section the D-1 decision does not support, and in either case
make the prose state the count arithmetically so it cannot drift again:
"*the application, the N snapshot(s) it analysed, the taxonomy mapping version
and the three model versions — N + 5 foreign keys, all NOT NULL*".

**For the faculty guide**, because it is an error in an approved document.

## Correction to our own record

Consistency log entry **C-10** claimed the seven NOT NULL foreign keys matched
the approved design. It was checked against §10.3's count and not §10.2's
structure. That entry was already corrected on 2026-11-04 and the correction
stands.

---

# DOC-2 — Withdrawn

Not a contradiction. §10.2's note nulls `segment_id` and the offsets for
absence records; it says nothing about `sentence_text`, and F-21 requires that
column to hold a generated statement. See D-7 above. No faculty ruling needed
on this point.

---

# What implementing all of this would involve

Not a request to proceed — a scope estimate, so the team can decide how much
to take at once.

| Item | Code | Migration | Tests touched |
|---|---|---|---|
| D-6 restore | `models.py`, `candidate_builder.py`, `verdict/models.py` | yes | ~8 |
| D-7 restore | `models.py`, `evidence_selector.py`, `absence_recorder.py`, `inconclusive_recorder.py`, `verdict/models.py` | yes | ~15 |
| D-3 | `vocabulary.py`, `models.py` | yes | ~4 |
| D-5 | `models.py` | yes | 1 |
| D-8 | `models.py` | yes | 2 |
| D-9 | `models.py` | yes | 2 |
| D-10 | `models.py`, comparison sites in three analysis modules | yes | ~6 |
| E-2 reconsidered | `models.py`, `vocabulary.py` | yes | 2 |

All of them share one migration. Because the project database is still empty
and the frozen baseline has not been applied to it, the whole set can go into
a re-freeze of `0001_baseline` rather than a chain of revisions — but only
while that remains true.

---

# Awaiting

1. Ruling on D-1, the only remaining decision with a genuine design trade-off.
2. Go-ahead on the compliance restorations: D-3, D-5, D-6, D-7, D-8, D-9, D-10.
3. Whether to reconsider **E-2** on the grounds set out under D-2.
4. DOC-1 to the faculty guide, with the count under whichever D-1 outcome is chosen.
5. Confirmation that **DOC-2 and D-2 are withdrawn**.

No database model, migration file, database content or application code has
been changed.
