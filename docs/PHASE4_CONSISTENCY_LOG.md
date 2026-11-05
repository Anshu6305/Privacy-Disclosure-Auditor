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

---

## 2026-11-05

### C-33 Configuration was not locatable from the Alembic working directory

**What happened:** `Settings` used a relative `env_file=".env"`, resolved
against the current working directory. Alembic must run from `backend/`, where
that path does not exist, so no credentials loaded and migrations could never
run. Found when the first PostgreSQL integration run produced 28 failures, all
caused by an absent schema.

**Fixed:** the env file path is now derived from the location of `config.py`,
so configuration resolves identically from the repository root, from
`backend/`, and from inside a container.

**Follow-on:** with `.env` discoverable, the unit suite began reading the
developer's real credentials. `conftest.py` now forces an empty password so
unit tests are hermetic and behave the same on every machine.

**Status:** resolved. No design change; this was an implementation defect.

### C-34 A PostgreSQL test passed vacuously

`test_audit_run_foreign_keys_are_all_not_null` asserted that no column of
`audit_run` was nullable. On an empty database there are no columns, so the
assertion held and the test passed while the table did not exist. It was the
single passing test in a run where nothing worked.

Corrected to assert the expected eight identifier columns exist first. The two
constraint-catalogue tests carried the same weakness and now require a
non-empty catalogue. A session-scoped gate also fails once with the cause and
the fixing command, rather than letting an unmigrated database produce 28
unrelated-looking failures.

**Why this is recorded:** a test that passes when the thing it checks is absent
is worse than no test, because it reports confidence that was never earned.

### C-35 PostgreSQL schema verified

**What was claimed before:** nothing. Every previous entry recorded the
PostgreSQL schema as unverified, and the traceability document carried the gap
as an explicit open row.

**What happened on 2026-11-05:** the baseline was applied to
`privacy_auditor_test` on PostgreSQL 16 and all 29 integration tests passed.
JSONB, the eleven BIGINT primary keys, `timestamptz`, the NUMERIC verdict
confidence, both functional `lower()` indexes, all 28 CHECK and 8 UNIQUE
constraints, and seven classes of invalid record that PostgreSQL must reject.

**Why it matters for the design claims:** the SQLite suite showed the
constraints were declared. This shows the production database enforces them.
In particular the four-label gold-set CHECK, the five-verdict CHECK and the
evidence and absence record rules — the constraints that carry the approved
design's distinction between a system abstention and a human annotation — are
now known to hold in PostgreSQL and not only in the ORM metadata.

**Scope of the claim:** the schema is verified. The application is not. No
endpoint, worker or pipeline stage has run against this database.

**Status:** the longest-standing open verification gap in Phase 4 is closed.

### C-36 Alembic baseline frozen

**Approved:** Strategy A from audit Part 4, with seven safeguards.

**What happened:** `0001_baseline` was rewritten from a metadata build into 16
explicit `op.create_table` calls and 21 `op.create_index` calls carrying all
28 CHECK constraints, 8 UNIQUE constraints and 27 foreign keys, with a matching
downgrade. Rendered by Alembic's own renderer against the PostgreSQL dialect,
not hand-written; the generator is kept for reproducibility.

**Why rewriting an existing revision was safe:** the read-only check on
2026-11-05 confirmed the project database had never been migrated. The only
database stamped with the old definition is `privacy_auditor_test`, which was
left untouched per safeguard 1 and is now superseded.

**Equivalence:** `tests/unit/test_migration_is_frozen.py` applies the revision
to an empty database and compares every table, column, nullability, index,
unique constraint, check constraint and foreign key against `Base.metadata`.
Ten tests, all passing. A model change made without a new revision now fails
the suite.

**Obsolete placeholder removed:** the unconditional skip that marked the
unverified-PostgreSQL gap served its purpose and was deleted along with its
file, whose other two tests are superseded by the equivalence suite.

**Verified on PostgreSQL, 2026-11-05.** The frozen revision was applied to a
newly created database, `privacy_auditor_frozen_20261105_test`, and all 29
integration tests passed against it. The frozen revision therefore produces
the same schema the metadata build produced and that was verified the same
day, which is what Strategy A had to demonstrate.

**Status:** frozen, equivalent to the models, and verified on PostgreSQL 16.
The baseline is now a fixed historical record.

---

## Decision-table revision — 2026-11-05

### C-37 Three audit findings withdrawn or reversed after team challenge

The team challenged D-2, D-6, D-7 and DOC-2, asking for each to be
demonstrated against the actual implementation and the actual sources rather
than argued. All three challenges were correct.

**D-6 reversed.** I claimed `practice_id NOT NULL` made a
Declared-not-in-policy verdict unrepresentable. It does not. F-19 takes the
declaration state as a separate input, so a declared category with no policy
practice needs an empty judgement list. Run against the committed code, an
empty list yields Declared-not-in-policy with its F-21 absence record, and all
five verdicts are reachable using only practice-backed judgements with no
`declared_practice_id`. An existing passing test,
`test_declared_not_in_policy_with_no_judgements_at_all`, already demonstrated
this; I wrote it and then argued against it. Revised recommendation: restore
the approved NOT NULL structure. Reclassified from implementation deviation to
**compliance restoration**.

**D-7 reversed and DOC-2 withdrawn.** I claimed §10.2 made
`evidence_record.sentence_text` NOT NULL while the same row required it to be
null for absence records. The note nulls `segment_id` and the offsets, not the
text. F-21 requires an absence record to store a fixed system-generated
statement and F-22 requires an inconclusive record to store candidate text, so
every record type carries text and a NOT NULL column is coherent. There is no
contradiction in the approved report on this point. Revised recommendation:
restore the single NOT NULL `sentence_text` column with content determined by
`record_type`. Reclassified to **compliance restoration**.

**D-2 withdrawn.** I asserted that Google's Data Safety form produces explicit
per-category negatives. I did not check whether any reach us. The published
section appears to be positive-only, and our acquisition layer does not exist,
so nothing in this project has ever read a declaration. The recommendation is
withdrawn. The distinctions that do appear to exist — an app-level "declares
no collection" statement, and a parsed-but-empty versus could-not-parse
status — are both app-level and belong with finding **E-2**, which should be
reconsidered on its own merits.

**Pattern worth recording.** Four of twelve positions were wrong in the same
direction: I read the approved design as defective where it was not, and
credited the implementation with corrections it had not made. The common cause
was arguing from the data dictionary alone without reading the function
specifications in §4.2 that govern the same structures.

**Effect on the balance of findings:** the revised table has seven compliance
restorations, two implementation deviations, one document correction and two
withdrawals, where the first edition claimed six changes and three amendments
to the approved design.

---

## Milestone 3A — 2026-11-05

### C-38 Acquisition built without touching the database

**Constraint:** D-1 is unresolved, so M3A had to proceed without choosing
between a per-collection-event and a per-source snapshot.

**What happened:** No SQLAlchemy model, Alembic migration or database was
touched. The acquisition layer produces plain frozen dataclasses with no
database dependency, and **provenance is recorded per source document** — the
smaller unit, from which either D-1 arrangement can be assembled. No
persistent snapshot schema was introduced.

**Status:** consistent. F-01, F-02, F-03 and the database halves of F-04, F-05
and F-07 are deferred to M3B.

### C-39 Retrieval is optional, and the system does not depend on it

**Approved design:** NFR-16 requires a single acquisition chokepoint; Phase 1
requires a frozen offline corpus and names Play Store access the least
reliable dependency.

**What happened:** `AcquisitionGateway` with no adapter is the default and
returns a recorded failure for every request. Audits read the corpus from
disk. The rate limiter has a floor that cannot be configured away, only
successes are cached, and a damaged cache entry is treated as a miss so the
cache cannot break a run.

**Status:** consistent.

### C-40 Normalisation rules are provisional and labelled as such

**What happened:** The Data Safety entry fields were taken from Google's own
documentation — data type, collected and shared declared separately, purpose,
optional flag, plus security and deletion statements. **No real page was
inspected**: `play.google.com` is unreachable from the development environment
and is not on the session allowlist.

**Recorded honestly** rather than presented as settled. The report states the
rules are provisional until a pilot runs, and the design confines any required
change to one adapter file, per the Phase 1 risk finding.

**Status:** consistent, with a stated limitation.

### C-41 M3A produces input to the open E-2 decision

Acquisition established that at least four states must be distinguishable for
a disclosure source: section parsed with declarations; section parsed with an
app-level no-collection declaration; section absent; fetch failed. The scraper
documentation consulted warns specifically against conflating the last two.

That is a concrete input to finding **E-2**, `disclosure_snapshot.status`,
which was deferred pending D-1. The domain layer already distinguishes all
four through `Provenance.outcome` and
`DataSafetyDeclaration.declares_no_data_collected`; only the persistent column
is outstanding.

---

## Milestone 4 — 2026-11-05

### C-42 Offsets index the cleaned text, as the approved design implies

**Approved design:** Phase 3 defines F-09's input as the cleaned text F-08
produces, and §10.4 records that the segmented text is stored so the pipeline
never depends on the raw files.

**What happened:** Offsets index F-08's cleaned plain text. That is the
canonical coordinate base and is stated in the module docstrings, the
traceability document and the M4 report. **No offset refers to raw HTML**, and
nothing was changed about what an offset means.

Offsets into the raw document were considered and rejected: they would require
a character-level map maintained through tag stripping, entity decoding,
Unicode normalisation and whitespace collapsing, which the approved design
does not call for.

**Enforcement:** `PolicySegment` refuses construction unless its offsets span
exactly its text, and every offset test verifies by slicing the real string
rather than by trusting an arithmetic relation.

**Status:** consistent.

### C-43 Extraction is conservative by design

**Approved design:** F-08 strips markup, navigation, scripts and boilerplate.

**What happened:** Only structural chrome is removed — scripts, styles,
navigation, headers, footers, forms and comments — with a count returned so
the discarding can be audited. **Nothing is removed for looking repetitive.**

Privacy policies repeat themselves by nature, and a cleaner that judged
content by similarity would delete the clauses the audit exists to find. A
test asserts six identical sentences all survive. Headings, definitions,
exceptions and list items are retained because each can carry a data practice.

The consequence is accepted and recorded: cookie-banner and consent text
inside ordinary paragraphs is retained, because distinguishing it from policy
prose reliably would need the classifier that has not been built.

**Status:** consistent, with the trade-off stated.

### C-44 No fallback sentence splitter

**Approved design:** F-09 uses spaCy sentence boundaries.

**What happened:** When spaCy or its model is absent, F-09 raises with
installation instructions instead of falling back to a simpler splitter.

**Why:** a fallback would place sentence boundaries differently, so the same
policy would segment differently depending on what happened to be installed.
Two team members would then get different evidence offsets for the same
document, which NFR-08 does not permit. The model is pinned for the same
reason.

**Status:** consistent, and stronger than the design required.

### C-45 spaCy moved to the base requirements

**What happened:** spaCy was in `backend/requirements-ml.txt`, the ~2 GB set,
but F-09 needs it for the **baseline** pipeline — text must be segmented
before any classifier runs — so a baseline-only install could not have
segmented a policy. Moved to `backend/requirements.txt`. The 2 GB in the ML
file is torch, not spaCy.

**Status:** dependency correction. No design or requirement change.

### C-46 Analysability thresholds are provisional and labelled

**Approved design:** F-10 compares segment count and total token count
"against a configured minimum". Phase 2 and Phase 3 set no numbers.

**What happened:** `min_segments = 1` and `min_tokens = 50` are proposed as
**provisional**, labelled as such in the dataclass docstring, in
`config.py`, in `.env.example`, in the traceability document and in the M4
report. They are not reported as approved requirements anywhere.

They are never applied silently: `validate_analysability` raises when no
thresholds are given, and the provisional values require an explicit
`allow_provisional=True`. A configuration that is missing a key, carries a
non-integer or sets a value below 1 is rejected, because a threshold of zero
would accept an empty document.

**Basis for the numbers:** the shortest genuine policy in OPP-115 is
`988_solarviews.com`, 703 characters in one segment, inspected directly during
Milestone 1. The thresholds sit below it so a real short policy is still
analysed while an error page is not. They should be revisited once the
operational corpus exists.

**Status:** consistent, with the provisional status recorded everywhere the
values appear.

---

## Milestone 5 — 2026-11-05

### C-47 Segment-level labels are supported by the corpus, and this was checked

**Approved design:** FR-11 requires multi-label classification of policy
segments over the OPP-115 category set.

**The question that had to be answered first:** absence of a category can only
mean "this segment does not discuss it" if every segment was actually read.

**Measured:** all 115 policies, every segment covered by annotations, zero
uncovered segments, zero segment identifiers outside the range of their
policy's text, and exactly three distinct annotators on all 115. The
construction is therefore supported by the data.

Had any segment been uncovered, the milestone instruction required stopping
and reporting the limitation. That did not arise, but the check was run rather
than assumed.

**Status:** consistent.

### C-48 Majority-vote labels, with the alternatives measured

All three rules were computed before choosing: any annotator leaves 0%
unlabelled at 1.70 labels per segment; majority leaves 1.7% at 1.18;
unanimous leaves 24.0% at 0.80. Majority was chosen because it discards
single-annotator readings while keeping 98.3% of segments.

Recorded with the numbers so the choice can be defended rather than asserted.

### C-49 Split grouped by source policy

**Methodological requirement.** Segments from one policy never cross a split
boundary; a policy reuses its own phrasing, so a random split by segment would
report memorisation as generalisation. 80 / 17 / 18 policies, seed 20261105,
deterministic and independent of input order. The training script asserts zero
policy overlap and refuses to train otherwise.

**No example was moved between splits** to improve a rare class's support. The
shortage is reported instead.

### C-50 Rare categories reported honestly, not hidden in the aggregate

Do Not Track has 4 positive test examples and Data Retention 7. Both produce
per-class F1 scores — 0.857 and 0.429 — and **neither is a measurement.** The
evaluation code flags any category below 10 positive test examples, prints it
as unreliable, and records `"reliable": false` in the saved metrics.

The macro-F1 of 0.7489 includes both and is therefore flattered by two scores
that are noise. The report says so in its first section rather than leaving a
reader to discover it.

**What would be needed** is recorded: roughly 300–600 positive segments for a
stable estimate on Do Not Track, against the 31 the corpus contains.

### C-51 F-14 reused, not reimplemented

**Approved design:** F-14 performs confidence thresholding and abstention.

**What happened:** F-11 returns a confidence for every category and performs
no thresholding. `analysis/confidence/gate.py` is used unchanged. A test
asserts F-11 never sets the abstention flag, and another asserts the gate
retains every practice rather than discarding low-confidence ones.

**Status:** consistent. No second threshold mechanism exists.

### C-52 No calibration claim

Logistic regression outputs are returned as **rankable confidences**, not
calibrated probabilities. No calibration has been performed or tested, and
`class_weight="balanced"` deliberately distorts the scores. The module
docstring, the report and the metadata all say so. The 0.50 decision threshold
used for reporting is provisional and has not been tuned; the validation split
exists for that and remains unused.

### C-53 ALG-11 index opclass — declared correctly, usability unverified

**Approved design:** F-01 performs case-insensitive prefix search over the two
functional indexes `ix_application_lower_name` on `lower(app_name)` and
`ix_application_lower_package` on `lower(package_name)`, with pg_trgm and GIN
as the documented upgrade path if substring search is later required (C-15).

**What happened:** F-01 is implemented as
`lower(col) LIKE 'term%'`, which returns the correct rows. Whether PostgreSQL's
planner can *use* those indexes for that predicate is a separate question and
has **not been verified**.

A B-tree index on an expression serves a prefix `LIKE` only when its opclass
orders text byte-wise — `text_pattern_ops` — or when the database collation is
`C`. Both indexes use the default opclass. Under a collation-aware default
such as `en_US.UTF-8` the planner may therefore fall back to a sequential scan
regardless of row count, which would make the indexes correct but inert for
this query.

**Not resolved here, deliberately.** Confirming it needs an `EXPLAIN` against
the real database, and fixing it would change the frozen schema, which this
milestone is forbidden to touch. `scripts/explain_application_search.py`
performs the measurement read-only and reports the answer, including the
collation and whether a range predicate on `lower(col)` is index-usable where
the `LIKE` is not.

**Consequence if it is inert:** correctness is unaffected; only the cost of a
search changes, and on a corpus of 300 to 500 applications a sequential scan is
not noticeable. It matters for NFR performance claims, not for results.

**Status:** **RESOLVED — tested and verified on PostgreSQL 16, 2026-11-05.**

**Measured on PostgreSQL 16, team Mac, 2026-11-05:** both pattern indexes
report `text_pattern_ops`; both baseline indexes retain `text_ops`; the
database collation is **`en_US.utf8`**. That collation is the condition C-53
depends on — collation-aware, not `C` — so the premise is now confirmed by
measurement rather than inferred from a missing index condition.

**Verified end to end** on `privacy_auditor_c53_20261105d_test`, log
`c53_verification_20261105_232120.log`:

| Stage | Result |
|---|---|
| Compose service identified from the configuration | `database` |
| Upgrade `-> 0001_baseline -> 0002_pattern_ops` | succeeded; recorded as `0002_pattern_ops` |
| Operator classes, from `pg_opclass` | both `_pattern` indexes **`text_pattern_ops`**; both originals `text_ops` |
| Index definitions | `lower((app_name)::text) text_pattern_ops` and `lower((package_name)::text) text_pattern_ops` |
| Collation | **`en_US.utf8`** — collation-aware, which is the condition C-53 depends on |
| Integration tests, revision applied | **56 passed, 0 skipped** |
| Downgrade to `0001_baseline` | both pattern indexes removed; **both baseline indexes retained** |
| Integration tests, revision removed | **49 passed, 7 skipped** — the gate fires |
| Re-upgrade | back at `0002_pattern_ops` |

**Index eligibility is verified by assertion, not by inspection.**
`test_prefix_predicate_is_index_eligible` and
`test_combined_f01_query_is_index_eligible` are among the 56 that passed. They
seed rows inside a rolled-back transaction, run `EXPLAIN` with
`enable_seqscan = off`, and assert an `Index Cond` using `~>=~` on a
`*_pattern` index. That is stronger evidence than reading a plan by eye.

**No performance claim.** `enable_seqscan = off` establishes eligibility only.
At 300 to 500 rows PostgreSQL will still prefer a sequential scan, and that is
the correct plan.

Three defects were found and fixed during verification, **all of them in the
verification code rather than in the correction**: C-56, C-57 and C-58. The
schema change itself was right on the first run.

The diagnostic was run on the team Mac on 2026-11-05 against
`privacy_auditor_frozen_20261105_test`. Both prefix `LIKE` queries produced no
useful index condition; the combined F-01 query produced an Index Scan with a
Filter and no Index Cond — the index was serving the `ORDER BY`, not the
`WHERE`; the range-based alternative produced a real Index Cond. The
collation is therefore not `C`, and both indexes use the default `text_ops`
opclass, which is confirmed from the frozen revision source.

Recommended fix, set out in full in `docs/C53_RESOLUTION_NOTE.md`: a second
Alembic revision adding two `text_pattern_ops` functional indexes, **retaining**
the existing two, and **no change to the F-01 SQL** — so the case-insensitive
prefix semantics and the literal wildcard escaping are preserved by
construction. The range-based rewrite is **rejected**: it depends on the
database collation and Python agreeing on string successors, and this project's
dotted package names make a silently-missing result a real risk.

Correctness was never affected, and the 43 integration tests that passed on
2026-11-05 show F-01 returning correct results. At 300 to 500 applications the
fix buys no measurable speed; it makes the approved O(log N + m) claim true.

**Implemented 2026-11-05**, on approval, as revision `0002_pattern_ops` —
`down_revision = "0001_baseline"`, two `op.create_index` calls, a reversing
downgrade, and nothing else. The frozen baseline is untouched and still
contains neither `text_pattern_ops` nor the two new index names, which is now
asserted by `test_baseline_does_not_contain_the_c53_correction`.

The operator class is attached through `postgresql_ops` keyed on a **labelled**
expression. This is the detail the correction turns on: `postgresql_ops` keyed
on the column name — the obvious spelling — compiles with no error and
silently drops the operator class, and `sa.text("lower(x) text_pattern_ops")`
compiles for SQLite too and is then rejected at execution. The labelled form
emits `(lower(app_name) text_pattern_ops)` for PostgreSQL and
`(lower(app_name))` for SQLite, so no dialect guard is needed and the unit
suite's in-memory databases still build.

Verified: the emitted PostgreSQL DDL, via Alembic offline mode, which needs no
server; the revision applying **and reversing** on SQLite; 461 passed, 53
skipped; ruff clean. **Not verified:** anything requiring a PostgreSQL server.
The catalogue and `EXPLAIN` tests are written and skip until a database
upgraded to `0002_pattern_ops` is supplied; commands are in
`docs/C53_RESOLUTION_NOTE.md` §10. Skips are not passes.

Phase 3's **O(log N + m)** claim is retained unchanged. The additional indexes
are what make it true: with a byte-wise operator class each branch of the `OR`
becomes an index range scan of m matches, combined by `BitmapOr`, in place of
today's full index walk with a filter, which is O(N). At 300 to 500
applications the planner will still choose a sequential scan, and no
performance improvement is claimed.

### C-54 F-01 result limit and minimum query length are provisional

**Approved design:** Phase 3 requires F-01 to apply a configured result limit.
It names the limit but sets no number, and says nothing about a minimum query
length.

**What happened:** `application_search_limit = 20` and
`application_search_min_query_length = 2` are in `Settings`, labelled
PROVISIONAL in the same words as the F-10 thresholds (C-33), with the reasoning
recorded beside them. They are the project's own proposal, not an approved
requirement.

**Status:** consistent — the requirement for a *configured* limit is met, and
the values are not presented as approved.

### C-55 Search is prefix-only, and substring queries find nothing

**Approved design:** prefix search, chosen so the functional B-tree indexes can
serve it.

**What happened:** `search("app")` returns no results even though four fixture
applications contain "app" inside their names. This is the design working as
approved, not a defect, but it is a behaviour a user will notice: typing the
middle of an application's name finds nothing.

A test asserts it explicitly so the limitation is recorded rather than
discovered. pg_trgm with a GIN index remains the documented upgrade path and is
not implemented.

**Status:** consistent. Flagged for the team in case FR-01 was intended to mean
substring search, which would be a requirement change, not a code fix.

### C-56 A test asserted one migration revision and broke when a second arrived

**Approved design:** the integration suite verifies that the approved schema
has been applied to the database under test.

**What happened:** `test_alembic_baseline_has_been_applied` asserted
`version_num == "0001_baseline"`. That was correct while the baseline was the
only revision. Once C-53 added `0002_pattern_ops`, a **correctly** upgraded
database failed it — 52 of 53 tests passed and the one failure was the test,
not the schema.

The defect is that the test asserted an exact migration state when its real
subject is "was the approved schema ever applied". Those are different
questions, and only the second is stable as migrations accumulate.

**Fix:** four tests derived from Alembic's own revision graph via
`ScriptDirectory`, so no revision identifier is hard-coded beyond the baseline
itself:

1. `test_alembic_baseline_is_in_the_applied_ancestry` — `0001_baseline` is in
   the ancestry of whatever revision is recorded. Passes at the baseline, at
   `0002_pattern_ops`, and at any later revision; fails if the baseline was
   never applied.
2. `test_applied_revision_lies_on_the_path_from_head_to_base` — the recorded
   revision is one this repository knows and is reachable from head. Catches a
   database and a checkout that have diverged, which the ancestry test alone
   cannot.
3. `test_pattern_indexes_match_the_applied_revision` — **covers both migration
   states.** It derives the expectation from the recorded revision and then
   checks `pg_opclass`: at `0002_pattern_ops` both indexes must exist with
   `text_pattern_ops`; at the baseline neither may exist. A migration applied
   or reverted without its DDL taking effect fails here.
4. `test_the_baseline_functional_indexes_exist_in_every_state` — C-53 is
   additive, so the original pair is present at every revision.

Also added: `applied_revision` asserts `alembic_version` holds **exactly one**
row, so a branched or partially applied history is reported rather than
silently taking the first value.

**No assertion was removed or weakened.** The replacement is strictly stronger:
the old test checked one string, the new set checks ancestry, reachability,
single-headedness, and agreement between `alembic_version` and the real
catalogue in both directions.

The graph logic was exercised without a database, since `ScriptDirectory`
needs none: ancestry of `0002_pattern_ops` is
`['0001_baseline', '0002_pattern_ops']`, ancestry of `0001_baseline` is
`['0001_baseline']`, head is `0002_pattern_ops`, and an unknown identifier is
not reachable.

**Status:** resolved.

### C-57 `dict(CursorResult)` raised a misleading TypeError

**Approved design:** unaffected. A defect in a test I added for C-56.

**What happened:** `test_pattern_indexes_match_the_applied_revision` built its
expected-versus-actual map with `dict(connection.execute(...))` and failed on
PostgreSQL with `TypeError: 'CursorResult' object is not subscriptable`. 55 of
56 integration tests passed; the operator classes, the collation and the
migration state were all confirmed in the same run.

**Cause.** `dict()` looks for a `.keys()` method and takes the mapping protocol
when it finds one. `CursorResult` **has** `.keys()` — the column names — so
`dict()` then tried to subscript the result object, which it cannot. The error
therefore names `dict`'s fallback path rather than the real mistake, which is
why it reads like a driver fault and not a two-character omission.

Reproduced on SQLite before fixing, because the bug is in how the result is
consumed and not in the SQL or the backend:

```
has .keys():            True
dict(result)         -> TypeError: 'CursorResult' object is not subscriptable
dict(result.all())   -> {'ix_a': 'text_pattern_ops', 'ix_b': 'text_pattern_ops'}
```

**Fix:** `.all()` first, then `dict(rows)`. `.all()` returns a list of `Row`
tuples, which `dict()` consumes pairwise as intended. The empty case returns
`{}`, which is what the baseline-state branch of the assertion needs.

The `.all()` is load-bearing and the code looks almost identical without it, so
a comment above the line says so explicitly rather than leaving the next reader
to rediscover this.

**No assertion was changed.** Both branches — both indexes with
`text_pattern_ops` at `0002_pattern_ops`, neither index at the baseline — are
exactly as written for C-56. Only the construction of `found` changed.

**Status:** resolved.

### C-58 Diagnostic script indexed a result tuple that had grown

**Approved design:** unaffected. A defect in `scripts/explain_application_search.py`.

**What happened:** the final stage of C-53 verification failed with
`TypeError: '<' not supported between instances of 'str' and 'int'`. Every
other stage had passed.

**Cause.** When `datctype` and `alembic_version` were added to the script's
metadata query, every column position after `datcollate` shifted. The print
statements were updated; a row-count comparison further down still read
`meta[2]`, which had become the collation string. The error surfaced three
lines of output after the real mistake.

**Fix:** unpack into names — `database, collate, ctype, row_count, applied =
meta` — so positions cannot drift out of step with the query again. Verified by
parsing the script's own SQL, counting its top-level columns and confirming the
count matches the number of unpack targets.

Also added: the script now says explicitly when `application` is **empty**, as
it was in that run, and points at the two eligibility tests as the
authoritative evidence rather than implying its own plans prove anything about
a relation with no rows.

**This did not affect C-53's verification.** The eligibility assertions live in
the test suite and passed in stage 9. The script is a convenience
pretty-printer; its output was never the evidence.

**Status:** resolved.

### C-59 D-1 Option A implemented: the collection-event snapshot restored

**Approved design:** Phase 3 section 10.2 — one `disclosure_snapshot` row per
**collection event**, carrying both disclosure sources.

**What happened:** the implementation had deviated to one row per source,
discriminated by `source_type`, with `audit_run` carrying two snapshot foreign
keys. The team ruled Option A on 2026-11-05 and revision
`0003_collection_event` brings the implementation back to the approved design.
`0001_baseline_schema.py` and `0002_pattern_ops` are unmodified.

| Was | Now |
|---|---|
| `source_type`, `source_url` | `source_url_listing`, `source_url_policy`, both nullable |
| `retrieved_at` | `collected_at` |
| `retrieval_method` | `retrieval_mode` |
| `storage_path`, `content_sha256` NOT NULL | `policy_doc_path`, `policy_doc_sha256` **nullable** |
| `content_bytes`, `http_status` | `policy_doc_bytes`, `policy_http_status` |
| — | `status` NOT NULL, `declares_no_data_collected` nullable |
| `audit_run`: 2 snapshot FKs, 7 total | **1 snapshot FK, 6 total** |
| 2 snapshot CHECKs, 28 total | **7 snapshot CHECKs, 32 total** |

**DOC-1 resolves.** `audit_run` has six NOT NULL foreign keys, so section
10.3's "seven" was the error; section 10.2 stands as approved.

**E-2 satisfied.** `status` exists, with the closed value set in
`analysis.vocabulary.SNAPSHOT_STATUSES`, recorded in the requirement change
log because Phase 3 names the column without enumerating its values.

**Partial collection events are the point.** Phase 1 named scraper breakage the
highest-probability risk, so an event capturing one source and failing the
other is expected. Both URLs are nullable, and six CHECK constraints stop a
partial event from looking complete: the status vocabulary, the nullable hash
length, the path/hash pairing, at-least-one-source, a stored document implying
its URL, and two status-to-URL agreements. A status of `complete` cannot be
recorded without both URLs.

**`declares_no_data_collected` is three-state, deliberately.** NULL means the
Data Safety section was never read; False means it was read and carries no
app-level no-collection statement; True means it does. Collapsing NULL into
False would turn a retrieval failure into an explicit negative declaration,
which is the single thing the column exists to prevent. Asserted by
`test_declares_no_data_collected_is_three_state`.

**What Option A gives up, recorded rather than hidden.** One event has one
timestamp, one hash, one HTTP status and one byte count. Per-source values
stop at the database boundary and survive in the filesystem corpus record's
provenance, which M3A writes. `SecurityPractices` still has no column and none
was added.

**The revision refuses to run on a populated table.** Two per-source rows
cannot be merged into one event: nothing in the old structure records which
declaration row belongs with which policy row, and a wrong guess would
attribute one application's policy to the wrong event. `upgrade()` stops with
the recovery path named — re-import from the filesystem corpus. Asserted by
`test_upgrade_refuses_to_restructure_a_populated_table`, which inserts a row
and requires the refusal.

**Tests changed, none weakened.** `test_audit_run_has_seven_not_null_foreign_keys`
became `..._six_...` and now asserts the exact set of six as well as the count.
`test_audit_cannot_compare_a_snapshot_with_itself` became
`test_an_audit_references_exactly_one_collection_event`: the old CHECK has no
subject under Option A, so the invariant moved from a constraint that could be
dropped into a structure where the error cannot be expressed, and that
structure is what is now asserted. `test_snapshot_source_type_is_restricted`
became `test_snapshot_status_is_restricted`, the same closed-vocabulary
assertion on the column that now carries one. Seven new constraint tests were
added.

Model-to-migration equivalence now compares the models against the **whole
chain** rather than the baseline alone, in `migrated_engine`; a `baseline_engine`
fixture remains for the tests that genuinely mean the frozen record. Comparing
current models to 0001 only would fail for a correct schema — the same category
error as C-56.

**Status:** implemented and SQLite-verified. **PostgreSQL verification
outstanding**, by `scripts/verify_migrations.sh` (renamed from
`verify_c53.sh`, since it now verifies the whole chain).

### C-60 The verification script hard-coded the head revision

**What happened:** the M3B verification run applied `0001_baseline` →
`0002_pattern_ops` → `0003_collection_event` correctly and then failed, because
`scripts/verify_migrations.sh` asserted `alembic_version == '0002_pattern_ops'`.

**Cause:** the same category error as C-56 — asserting a fixed identifier that
a later change had moved — this time in a shell script rather than a test.

**Fix:** head and base are derived from Alembic's `ScriptDirectory`, which also
refuses a branched history rather than guessing. Four further version-bound
assumptions were found in the same review and corrected: step 9 now asserts
**no skips at head** rather than a test total; step 10b asserts the run is
green **and** contains skips, since at the baseline skips are the evidence the
revision guards fired; step 10c re-checks the operator classes and
`disclosure_snapshot.status` so a round trip that restored the version row but
not the schema cannot pass; and the downgrade target is the derived base.

Three tests now lock this down: no revision identifier may appear in an
executable line of the script, no destructive verb may appear in one, and every
earlier disposable database must be in `PROTECTED` while the current target
must not be.

**Status:** resolved. Option A and all three migrations unchanged.

### C-61 Two defects the M3B verification run exposed

The run reached the integration suite and reported **1 failed, 48 passed, 7
skipped** at head `0003_collection_event`. Both numbers were wrong, for
different reasons.

**The failure: `test_audit_run_foreign_keys_are_all_not_null` expected eight
identifier columns.** `audit_id` plus seven foreign keys. Under D-1 Option A
there are six foreign keys, so seven columns. This is the PostgreSQL mirror of
the unit test corrected with C-59; the mirror was missed. Now it asserts the
exact **set** of seven names as well as the count, so a renamed column is
reported by name rather than as an off-by-one.

**The seven skips: the C-53 revision gate asked the wrong question.** It
tested whether `"0002_pattern_ops"` was in the set read from
`alembic_version` — but that table holds **one** value, the current revision.
At head `0003_collection_event` the membership test failed, so seven tests
that should have run skipped on a fully migrated database.

Equality with the current revision answers "is the database exactly here".
The gate needs "has this revision been applied", which is ancestry. The
fixture now derives the applied set from `ScriptDirectory.iterate_revisions`.

**Third occurrence of one mistake.** C-56 hard-coded a revision in a test,
C-60 hard-coded one in the verification script, and C-61 compares against the
current revision instead of the ancestry. All three assert a fixed point in a
chain that grows. Two tests now lock the pattern down: one checks the gate
opens at every revision from `0002_pattern_ops` onward and stays closed before
it, the other asserts the integration gate still consults the migration graph.

The failure masked the skips — the script aborts on a failing suite before
reaching the no-skips assertion that would have caught them. The assertion was
right; it just never ran.

**Status:** resolved. Option A and all three migrations unchanged.

### C-62 Model-comparison tests failed at the baseline instead of skipping

**The run that found it:** head passed completely — **56 passed, 0 skipped** at
`0003_collection_event`, with both pattern operator classes, the collation, the
upgrade and the downgrade all verified. The baseline stage then reported
**3 failed, 39 passed, 14 skipped**.

**The three failures were correct observations reported as defects:**

| Test | At `0001_baseline` |
|---|---|
| `test_timestamps_carry_a_time_zone` | names `collected_at`, which is `retrieved_at` before 0003 |
| `test_every_declared_check_constraint_exists` | expects the models' 32 CHECKs; the baseline has 28 |
| `test_audit_run_foreign_keys_are_all_not_null` | expects Option A's six FKs; the baseline has seven |

Each compares the **live database** with the **current models**. Those agree
only at head. At an earlier revision they legitimately differ, so a failure
there reports a correct database as broken.

**Fix:** a `schema_at_head` fixture that skips when the applied revision is not
the graph's head, applied to the five tests that derive their expectation from
the models. Tests asserting something true of *every* revision — the baseline
functional indexes, the JSONB and BIGINT types, the constraint *enforcement*
tests — carry no guard and keep running everywhere.

**Fourth occurrence of one mistake, so it is now closed statically.** C-56
hard-coded a revision in a test, C-60 in the verification script, C-61
compared against the current revision rather than the ancestry, and C-62
compared against the models without requiring head. Three tests parse the
integration file with `ast` and fail if a test reads `Base.metadata`, or names
a column introduced by 0003, without taking the `schema_at_head` fixture. The
next such test cannot be written without the guard.

**Status:** resolved. Option A and all three migrations unchanged.

### C-63 Full migration-chain verification passed on PostgreSQL 16

Log `migration_verification_20261106_000146.log`, database
`privacy_auditor_m3b_20261105d_test`, 2026-11-06. **Every stage passed.**

| Stage | Result |
|---|---|
| Chain and head, from the graph | `0001_baseline -> 0002_pattern_ops -> 0003_collection_event` |
| Upgrade | recorded at head |
| Operator classes, from `pg_opclass` | both `_pattern` **`text_pattern_ops`**, both originals `text_ops` |
| Collation | `en_US.utf8` |
| Integration tests at head | **56 passed, 0 skipped** |
| Downgrade to baseline | both pattern indexes removed, both baseline indexes retained |
| Integration tests at baseline | **37 passed, 19 skipped, 0 failed** — guards fired |
| Re-upgrade | head restored, operator classes re-checked, collection-event columns present |
| ALG-11 diagnostic | **index used: yes** on both prefix predicates |

**The predicted plans were observed, not assumed.** C-53's note predicted
`Index Cond` using the pattern operators and a `BitmapOr` for the combined
query. What PostgreSQL produced:

```
lower(app_name) LIKE 'wha%'
  Index Scan using ix_application_lower_name_pattern
    Index Cond: lower(app_name) ~>=~ 'wha' AND lower(app_name) ~<~ 'whb'

F-01 as implemented (both columns, OR)
  Sort (lower(app_name), package_name)
    Bitmap Heap Scan
      BitmapOr
        Bitmap Index Scan on ix_application_lower_name_pattern
        Bitmap Index Scan on ix_application_lower_package_pattern
```

The `Sort` reappearing above the bitmap scan was predicted too: a bitmap scan
does not preserve order. On at most 20 rows it is free.

**No performance claim.** `enable_seqscan` was off, which establishes
eligibility. At 300 to 500 rows PostgreSQL will still prefer a sequential
scan, and that is the correct plan. What the correction buys is that the
approved **O(log N + m)** claim is now true rather than aspirational.

**C-53 and C-59 are closed.** The ALG-11 index correction and the D-1 Option A
collection-event restoration are both **Tested and verified** on PostgreSQL 16,
including upgrade, downgrade and re-upgrade.

Five defects were found and fixed across the verification runs — C-56, C-57,
C-58, C-60, C-61, C-62 — **every one of them in verification code, none in the
schema changes themselves.** Both migrations were correct on their first
application.
