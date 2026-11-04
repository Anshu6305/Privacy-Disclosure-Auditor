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

### C-10 Seven NOT NULL foreign keys on audit_run

**Approved design:** every audit records both snapshots, the taxonomy mapping
version and the three model versions, plus the application.

**What happened:** Implemented and verified. `test_audit_run_has_seven_not_null_foreign_keys`
counts them and asserts none is nullable.

**Status:** consistent.

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
