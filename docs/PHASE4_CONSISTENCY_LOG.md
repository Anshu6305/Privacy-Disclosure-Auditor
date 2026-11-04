# Phase 4 Consistency Log

Every point at which an implementation decision was checked against the
approved Phase 1 to 3 documents. Entries record agreement as well as
correction, because the agreements are what show the design was followed
rather than re-invented.

Nothing here changes an approved requirement. Changes to requirements go in
`REQUIREMENT_CHANGE_LOG.md` and need faculty approval.

---

## Milestone 1 — 2026-11-04

### C-01 Container count held at three

**Approved design:** Phase 3 deployment — three containers on one host:
web/API, worker, PostgreSQL.

**What happened:** The first draft of `docker-compose.yml` had four services,
adding an nginx container to serve the frontend. That contradicts the approved
deployment.

**Resolution:** Corrected before commit. The SPA is built in a Node stage
inside `backend/Dockerfile` and served by FastAPI from the same process, so the
web and API functions share one container exactly as the design states. The
reasoning is recorded as a comment at the top of the Dockerfile so it is not
undone by someone who sees only the file.

**Status:** consistent with the approved design.

### C-02 `analysis/` kept free of web and database dependencies

**Approved design:** Phase 3 §6.1 — the analysis pipeline is independent of the
delivery mechanism.

**What happened:** `analysis/` was placed at the repository root rather than
under `backend/`, and imports nothing from `app`.

**Status:** consistent. Enforced by a test in Milestone 4, once the first
analysis module exists.

### C-03 Confidence thresholds treated as configuration

**Approved design:** ALG-4; Phase 3 records thresholds as tunable and stored
per audit run in `audit_run.threshold_config`.

**What happened:** Thresholds are environment settings with placeholder values
of 0.50, labelled in `.env.example` and in `config.py` as untuned placeholders
rather than measured results.

**Status:** consistent. The per-run persistence arrives with the schema in
Milestone 2.

### C-04 Scope statement held in one place

**Approved design:** F-26; the system states its limits wherever it reports.

**What happened:** The wording lives in `backend/app/main.py` and is served by
`/api/meta/scope`. The frontend fetches it rather than carrying its own copy,
and a test asserts the statement still disclaims legality, intent and malice,
so weakening it fails the suite.

**Status:** consistent.

### C-05 Database health reports the real outcome

**Approved design:** Phase 4 constraint — no simulated database operations.

**What happened:** `/api/health/database` executes `SELECT 1` and reports
`unconfigured`, `unavailable` or `ok` based on what happened. A test asserts it
does not report healthy without credentials.

**Status:** consistent.

### C-06 OPP-115 not redistributed

**Approved design:** Phase 1 licence finding — research, teaching and
scholarship use, in the spirit of CC BY-NC. Phase 4 constraint — never commit
datasets that cannot legally be redistributed.

**What happened:** `.gitignore` excludes all of `data/` except its README. The
repository carries a checksum manifest (`ml/data/opp115_manifest.json`) instead
of the corpus, which gives reproducibility without redistribution. The citation
and licence note are embedded in the manifest.

**Status:** consistent.

### C-07 Corpus manual contradicted by the released files

**Approved design:** not affected. This is a dataset documentation defect, not a
design question, but it would have produced wrong provenance records if
followed.

**What happened:** `documentation/manual.txt` documents annotation CSV column 8
as the policy URL and column 9 as the date. In all 23,194 rows of the released
corpus they are the other way round: column 8 holds the date, column 9 the URL.
Measured, not assumed — the check counted every row.

**Resolution:** The loader identifies the URL by its scheme prefix rather than
by position, and the discrepancy is documented in `ml/data/opp115_schema.py`.

**Status:** handled.

### C-08 Span availability measured, not estimated

**Approved design:** Learning task 2 (F-12) depends on span supervision from
OPP-115 and PolicyIE.

**What happened:** A first pass counted 69,020 of 146,926 attribute entries as
lacking a usable span and risked the conclusion that nearly half the corpus was
damaged. On inspection, 68,758 of those carry the values `Unspecified`,
`not-selected` or `Does`, which are span-free by design. Genuine errata number
262, or 0.18%.

**Measured result:** 77,906 attribute entries (53.0%) carry usable spans with
real character offsets.

**Status:** no design impact. The figure is recorded because the ML plan in
Milestone 6 depends on it, and because the first reading of it was wrong.

---

## Decision record — 2026-11-04

### D-01 F-18 semantic alignment: training-data approach

**Approved design:** Phase 1 names cross-source semantic alignment via
constrained textual entailment as the third learning task, with fine-tuning
anticipated on a modest number of examples. Phase 3 keeps F-18 learned and
separate from the rule-based taxonomy mapping in F-15.

**Open problem:** No public corpus labels (policy statement, Data Safety claim)
pairs as Supports, Contradicts or No-match. The examples have to be produced by
the team.

**Decision, by the team:** Option A. An NLI-pretrained encoder is used
zero-shot as the baseline, then fine-tuned on 300 to 500 manually labelled
pairs, conditional on sufficient reliable annotation.

**Binding safeguards:** annotation guide written before labelling begins;
zero-shot retained as the comparison baseline; splits grouped by application,
never by individual pair; per-class precision, recall and F1 reported alongside
macro-F1, with no improvement claimed unless the held-out evaluation supports
it; and if annotation or fine-tuning falls short, the zero-shot model is kept
and the limitation is documented as a proposed deviation for faculty review.

**Consistency:** This keeps the approved three-task methodology intact. F-18
remains a learned component and F-15 remains rule-based lookup; the two are not
merged. No requirement identifier changes.

**Status:** consistent with the approved design. Implementation deferred to
Milestone 6, as instructed.

---

## Milestone 2 — 2026-11-04

### C-09 Sixteen tables, no more

**Approved design:** Phase 3 section 10 — sixteen PostgreSQL tables.

**What happened:** All sixteen are implemented in `backend/app/db/models.py`.
No table was added. In particular the 300 to 500 labelled alignment pairs from
decision D-01 are kept as a dataset file, not as a seventeenth table, because
they are training data rather than application state.

**Enforcement:** `test_exactly_sixteen_tables` asserts the count, and the
baseline migration refuses to run if the metadata holds a different number.

**Status:** consistent.

### C-10 Seven NOT NULL foreign keys on audit_run — **CORRECTED 2026-11-04**

**What this entry originally claimed:** that the seven NOT NULL foreign keys on
`audit_run` matched the approved design.

**Why that was wrong:** the claim was checked against Phase 3 Section 10.3,
which states "all seven foreign keys from audit_run are NOT NULL", and not
against Section 10.2, which lists **six**: app_id, snapshot_id,
mapping_version_id, classifier_version_id, extractor_version_id and
aligner_version_id. The two sections of the approved report disagree with each
other, and the prose's own arithmetic — one snapshot plus four versions plus the
application — also gives six.

The implementation has seven only because it splits `disclosure_snapshot` into
one row per source and therefore carries two snapshot references. That split is
itself a deviation from Section 10.2 and is recorded as finding D-1 in
`docs/PHASE4_SCHEMA_BASELINE_AUDIT.md`.

**Accurate status:** the count matches Section 10.3; the structure does not
match Section 10.2. Resolution depends on decision D-1 and on a faculty ruling
on the contradiction in the approved report, recorded as DOC-1.

### C-11 Evidence rules enforced by the database, not by convention

**Approved design:** F-20, F-21, F-22 and the F-23 correction — an `evidence`
record quotes verbatim text; an `absence` record has nothing to quote because
the finding is that nothing was found; an `inconclusive` record states why the
system abstained; a Consistent verdict carries no record at all.

**What happened:** Three CHECK constraints make these structural. An evidence
record without quoted text, a segment reference and ordered offsets is
rejected. An absence record carrying a quote is rejected. Both are tested by
attempting the write.

**Status:** consistent. This is stronger than Phase 3 required, which specified
the rule but not the mechanism.

### C-12 Four-label gold set enforced

**Approved design:** gold annotations use the four annotation labels;
Undetermined is a system abstention and never a human label.

**What happened:** CHECK constraint on `gold_annotation.label`.
`test_gold_annotation_rejects_undetermined` attempts the write and confirms the
database refuses it.

**Status:** consistent.

### C-13 Abstention stored, never dropped

**Approved design:** abstention propagates F-14 to F-15 to F-17 to F-18, and a
low-confidence prediction is flagged rather than discarded.

**What happened:** `abstained` is a NOT NULL column on `extracted_practice`,
`extracted_span` and `alignment_judgement`, and `verdict` carries
`abstention_involved`. The storage layer therefore cannot lose the flag. The
propagation logic itself is Milestone 7.

**Status:** consistent so far; the logic is verified in Milestone 7.

### C-14 Raw documents stay out of the database

**Approved design:** policy documents on the filesystem, path and SHA-256 in
the database.

**What happened:** `disclosure_snapshot` has `storage_path` and
`content_sha256` and no body column.
`test_policy_documents_are_not_stored_in_the_database` asserts that no column
named content, body, html, document_text or raw_text exists, so the shortcut
cannot be added later without the test failing.

**Status:** consistent.

### C-15 ALG-11 functional indexes present

**Approved design:** the F-01 index correction — case-insensitive prefix search
using functional indexes on `lower(...)`, with pg_trgm and GIN as the documented
upgrade path if substring search is later needed.

**What happened:** Both functional indexes are declared on `application` and
are asserted by `test_case_insensitive_search_indexes_exist`. The upgrade path
is recorded as a comment on the table.

**Status:** consistent.

### C-16 JSON NOT NULL columns were not actually enforcing NOT NULL

**Approved design:** `audit_run.threshold_config` is required, because a report
cannot be interpreted without the thresholds that produced it.

**What happened:** `test_threshold_config_is_required` failed. SQLAlchemy's JSON
type serialises Python `None` into the JSON literal `null` by default, which
satisfies a NOT NULL constraint. A run could therefore have been stored with no
usable threshold configuration while appearing valid.

**Resolution:** The shared JSON type now sets `none_as_null=True`, so `None`
becomes SQL NULL and the constraint applies. Found by the test rather than by
review.

**Status:** corrected and verified.

### C-17 Taxonomy mapping moved out of the data directory

**Approved design:** not affected. The master plan's own folder sketch placed
the F-15 mapping under `data/taxonomy/`.

**What happened:** Everything under `data/` is git-ignored, so the mapping
would not have been version-controlled. It is the team's authored artefact, not
a third-party dataset, and the report cites it.

**Resolution:** Moved to `analysis/mapping/taxonomy/`. The master plan and
`data/README.md` are corrected.

**Status:** plan corrected; no design change.

---

## Environment finding — 2026-11-04

### C-18 Supported Python version narrowed to 3.10 to 3.13

**Approved design:** Phase 3 names Python as the backend language. No version
is fixed by the approved documents, so this is an implementation constraint
rather than a design change.

**What happened:** Setup on the team machine failed. `pip install` aborted on
`scipy` with `metadata-generation-failed` and a meson error reporting OpenBLAS
and pkg-config missing. The machine runs CPython 3.14.4.

**Cause:** The pinned scientific stack — numpy 2.2.1, scipy 1.14.1,
scikit-learn 1.6.0, pandas 2.2.3 — publishes wheels for CPython 3.10 to 3.13.
On 3.14 pip finds no wheel and falls back to compiling scipy from source, which
needs a Fortran toolchain and OpenBLAS that a stock macOS does not have. The
error names scipy and OpenBLAS and never mentions the Python version, which is
what made it look like a missing system library.

**Resolution:**

- `pyproject.toml` now declares `requires-python = ">=3.10,<3.14"`, with the
  reason recorded in a comment so the upper bound is not removed as excess
  caution.
- The container image moved from `python:3.11-slim` to `python:3.12-slim`, so
  local development and the container run the same minor version and a result
  cannot differ between them.
- `README.md` states the version requirement, explains why, and tells the reader
  to check `python3 --version` before anything else.
- `tests/conftest.py` raises a clear `UsageError` on 3.14 or newer, so the next
  person meets one sentence instead of a meson build log.

**Not done:** installing OpenBLAS to make the source build work. Compiling
scipy per machine is fragile, slow, and would differ across six machines and
the grading environment. Matching the container's interpreter is the smaller
and more reproducible fix.

**Status:** resolved. No requirement or design change; recorded here because it
changes the documented development environment.

---

## Execution-order adjustment — 2026-11-04

### C-19 Milestone 7 implemented ahead of Milestones 3 to 6

**Approved design:** unaffected. The Phase 3 WBS fixes what each milestone
delivers, not the order in which they are built.

**What happened:** The team approved implementing M7, the verdict and evidence
engine, before M3 acquisition, M4 text processing, M5 baseline ML and M6
improved ML. The reason is that M7's logic is deterministic: it depends on no
dataset, no network access and no trained model, so it can be written and
tested in full while those milestones are blocked on data.

**Scope of the adjustment:** order of execution only.

- M3, M4, M5 and M6 are **not** completed, skipped, merged or reduced.
- Their functions remain Not implemented in the traceability document.
- The milestone definitions in the master plan are unchanged.

**Dependency acknowledged:** M7 consumes alignment judgements produced by F-18,
which belongs to M6. Until M6 exists, judgements come only from controlled test
fixtures. Nothing in M7 produces, approximates or simulates a model prediction,
and no upstream component is represented as implemented.

**Status:** execution order adjusted with team approval; no design change.

---

## Milestone 7 — 2026-11-04

### C-20 ALG-8 implemented as five ordered steps

**Approved design:** Phase 3 ALG-8 — contradiction first; decisive support
resolved against the declaration state; abstention; the absence rule; neither
source mentioning the category treated as Consistent.

**What happened:** `assign_category_verdict` runs the five steps in sequence,
each written out separately with the condition it tests. The order was not
simplified, reordered or collapsed into a single expression, because the order
is what the algorithm consists of.

**Verification:** one test per step plus four precedence tests that put two
conditions in conflict and assert the higher-precedence one wins.

**Status:** consistent.

### C-21 Abstention precedes the absence rule

**Approved design:** design issue DI-3, resolved in Phase 3 by ordering ALG-8 so
abstention is considered before any absence claim.

**What happened:** Step 3 sits above step 4. A declared category whose only
policy statement was abstained ends as Undetermined, not
Declared-not-in-policy. The same holds for an undeclared category: an abstained
reading yields Undetermined rather than Consistent, because the uncertain
statement might have been an In-policy-not-declared finding.

**Verification:** `test_abstention_beats_the_absence_rule` and
`test_abstention_beats_neither_source_mentions` assert both the verdict that
must be produced and the verdict that must not.

**Status:** consistent. This is the rule that satisfies the standing
requirement that an uncertain upstream judgement never becomes a confident
absence finding.

### C-22 Abstention propagation made structural

**Approved design:** `judgement.abstained <- judgement.abstained OR
sourcePractice.abstained`, propagating through F-14, F-15, F-17 and F-18.

**What happened:** `AlignmentJudgement.abstained` is a property rather than a
stored field. It reads the model's own flag **or** the candidate's upstream
flag, and the candidate reads through to the mapped practice, which reads
through to the policy practice. There is no code path that can produce a
judgement that appears confident while resting on an uncertain input, because
the propagation is in the type rather than in a step a caller could omit.

**Verification:** a judgement stated as SUPPORTS at 0.99 confidence, built on a
practice abstained at 0.3, reports `abstained is True` and `is_decisive is
False`, and the category ends Undetermined.

**Status:** consistent, and stronger than the design required. Phase 3
specified the rule; this makes it unskippable.

### C-23 Evidence is sliced from the policy, never composed

**Approved design:** F-20 — evidence is verbatim and never generated.

**What happened:** An evidence record carries the stored segment's own text and
that segment's own offsets. `PolicySegmentRef` refuses to exist unless
`char_end - char_start` equals the length of its text, and `EvidenceRecord`
refuses an evidence record whose offsets do not match its quote. A test
reconstructs the document and confirms that the text found at each record's
offsets is exactly the quoted text.

**Status:** consistent.

### C-24 The two kinds of Consistent are distinguishable, with no schema change

**Approved design:** Consistent covers both affirmative agreement and neither
source mentioning the category. Both are consistent, but they mean different
things to a reader.

**What happened:** `CategoryVerdict.consistency_basis` returns
`affirmative_agreement` or `neither_source_mentions`, derived from the
`declared` and `found_in_policy` values. Those two are already columns on the
`verdict` table, so the distinction is recoverable from stored data and **no
schema change was needed**.

**Status:** consistent. No design change requested.

### C-25 An unrecognised Data Safety category stops the audit

**Approved design:** the vocabulary deliberately has no database CHECK on
`ds_category`, so a change to Google's taxonomy surfaces as a named pipeline
failure (F-33) rather than a database rejection mid-run.

**What happened:** `normalise_declaration` raises
`UnknownDataSafetyCategoryError` naming the category. Dropping the line
silently would produce a report that looked complete while omitting a whole
category.

**Status:** consistent with the C-09 reasoning. The F-33 handler that catches
this and records it on the audit run is Milestone 8 work.

### No design or schema changes

Milestone 7 required no change to the sixteen-table schema, the API design, or
any FR, NFR, GI or function identifier. Nothing is pending the team's approval
from this milestone.

---

## Baseline audit — 2026-11-04

### C-26 Schema compared against the approved data dictionary

**What prompted it:** the team asked for a Phase 2 and Phase 3 consistency
audit before any further implementation, noting that sixteen tables does not by
itself mean the schema matches Phase 3.

**What was done:** the Phase 3 report's Section 10.2 data dictionary and
Section 10.3 constraints were read directly from `Report_Phase-03.docx`, and
every table, column, type, nullability, key, constraint and index was compared
against the committed `backend/app/db/models.py`. Results in
`docs/PHASE4_SCHEMA_BASELINE_AUDIT.md`.

**Outcome:** the schema does **not** match the approved data dictionary. Table
count, table names, the five-verdict CHECK, the four-label CHECK and the
`UNIQUE(audit_id, ds_category)` rule all match. Below that: 63 columns renamed,
38 additions, **7 structural deviations** and **6 omissions**, plus two
internal contradictions in the approved report itself.

**Status:** findings recorded. Nothing changed. Awaiting team decisions.

### C-27 F-19 verdict confidence was not implemented

**Approved design:** Phase 3 Section 4.2, F-19 processing step 3 — "Set the
verdict confidence from the judgement that determined the outcome; for an
Undetermined verdict, record the highest sub-threshold confidence instead."
Output: "One verdict record for the category, carrying value and confidence."
Section 10.2 gives `verdict.confidence numeric(5,4) (nullable)`. Phase 2 NFR-07
requires confidence values to be visible to the user.

**What happened:** the field was omitted from the ORM model, from the domain
object and from the engine. The Milestone 7 report described ALG-8 as
implemented exactly as specified; that was true of verdict *selection* and
false of F-19 as a whole. No test asserted that a verdict carries confidence,
so 169 passing tests did not reveal it. The tests verified what was built
rather than what was required.

**Effect:** NFR-07 cannot be satisfied as the system stands. Screen S4 and F-24
have no confidence to display.

**Correction proposed:** audit Part 3, changes C1 to C3, with tests. It
restores the approved design, so it needs no faculty approval and no
requirement change-log entry — only the team's go-ahead to implement.

**Status:** confirmed, unimplemented, awaiting approval.

### C-28 Milestone 7 status corrected

Two rows in `docs/IMPLEMENTATION_TRACEABILITY.md` overstated completeness and
have been corrected:

- **F-19** is Partially implemented, not Implemented and verified.
- **F-15** has a working, tested mechanism but **no mapping rules**. No OPP-115
  to Data Safety rule has been authored, and none will be invented. Until the
  team authors and reviews them, F-15 cannot run on real data.

Also restated: all three confidence thresholds remain provisional at 0.50 and
uncalibrated; persistence of verdicts is Milestone 8 and not started; no
end-to-end audit has ever been run.

---

## Audit corrections — 2026-11-04

### C-29 Class E restorations implemented

**Authorisation:** the team approved proceeding with the class E restorations.
These restore columns the approved Phase 3 data dictionary specifies, so they
are compliance with the baseline rather than departures from it and need no
requirement change-log entry.

**Implemented:**

| Finding | Restoration |
|---|---|
| E-5 | `verdict.confidence NUMERIC(5,4)` nullable, with a range CHECK; `CategoryVerdict.confidence`; F-19 step 3 in the engine |
| E-4 | `extracted_span.model_version_id` NOT NULL FK, plus its index |
| E-1 | `application.store_category` nullable |
| E-3 | `extracted_practice.practice_type` nullable |
| E-6 | `evaluation_metric.scope` NOT NULL |
| — | `gold_annotation` index extended to `(app_id, ds_category)` |
| — | `DESC` restored on the two time-ordered indexes |

**Deliberately not restored:** E-2, `disclosure_snapshot.status`. What a status
describes depends on whether a row is one collection event or one source, which
is finding D-1 and still open. Restoring it now would bake in an answer to a
question the team has not decided.

**Two columns restored without their meaning:** Phase 3 names
`extracted_practice.practice_type` and `evaluation_metric.scope` but defines no
value set for either, anywhere in the report. The columns exist so the schema
matches the dictionary; neither has a CHECK, because inventing a vocabulary
would be fabricating part of the approved design. Both are flagged for the team.

**Status:** schema now matches the approved data dictionary on every class E
point except E-2. Class D deviations are unchanged.

### C-30 F-19 completed

`assign_category_verdict` now implements processing step 3. Confidence is taken
from the highest-confidence judgement of the class that triggered the ALG-8
step that fired, and for Undetermined from the highest **sub-threshold**
confidence, as the approved design requires.

Two decisions inside that are worth recording because neither is forced by the
text:

- For Undetermined, the figure is drawn from the abstained judgements only. A
  trusted NO_MATCH in the same category may be more confident, but it is not
  what left the question open, and reporting it would overstate how close the
  system came to an answer.
- Confidence is `None` where no judgement determined anything — the category
  neither source mentions, and a declared category that produced no judgements.
  A default such as 0.0 would read as "very low confidence" rather than "not
  applicable", so the field stays null as the data dictionary permits.

Fifteen tests in `tests/unit/test_verdict_confidence.py`. These are the tests
whose absence let the omission through: the previous suite verified what had
been built rather than what the design required.

**NFR-07 is not yet satisfied end to end.** The value is computed and stored;
no endpoint returns it and no screen shows it. That closes in M8 and M9, and
the traceability document records the gap explicitly.

### C-31 PostgreSQL tests written, not executed

`tests/integration/test_postgresql_schema.py` contains 29 tests covering the
Alembic upgrade, the sixteen tables, JSONB, the eleven BIGINT primary keys,
`timestamptz`, the restored `NUMERIC` confidence, both functional `lower()`
indexes, every declared CHECK and UNIQUE constraint in the real catalogue, the
seven NOT NULL references on `audit_run`, and seven cases where PostgreSQL must
reject an invalid record.

Safety was verified rather than assumed: a `TEST_DATABASE_URL` naming
`privacy_auditor` fails with an explicit refusal instead of running, a missing
driver or unreachable server skips cleanly, and every test runs inside a
transaction that is rolled back. One defect was found and fixed in the process
— `create_engine` was outside the try block, so a missing psycopg driver
produced 29 errors rather than 29 skips.

**They have never run against PostgreSQL.** The project may not describe the
PostgreSQL schema as verified until it has.

### C-32 Migration strategy still undecided

No new Alembic revision was created. Because `0001_baseline` builds from the
model metadata, a fresh database still receives the restored columns correctly
without one — which is the single advantage of that approach and the reason the
restorations could proceed before the migration question is settled.

The question is not closed. Whether to freeze `0001` (Strategy A) or add
`0002` (Strategy B) depends on whether the baseline has been applied anywhere,
which the team has not yet confirmed. The read-only check is in audit Part 4.
