# Milestone 3B — Database-backed Acquisition: implementation plan

Date: 2026-11-05 · revised 2026-11-05 after M3B part 1
Scope: F-01 to F-07, requirements FR-01 to FR-07, task T1.

## 0. Status at a glance

| State | Items |
|---|---|
| **Completed** | F-01 `searchApplications`, F-03 `handleUnknownApplication`, `ApplicationRepository`. Commit `fc1a111`. 43 unit tests |
| **Verified** | **43 PostgreSQL integration tests passed** on `privacy_auditor_frozen_20261105_test`, 2026-11-05 — 29 schema + 14 F-01 search. Results are correct on real PostgreSQL, not only on SQLite |
| **Pending** | F-02 `requestAudit`, F-04 `loadDeclaration`, F-05 `loadPolicyDocument`, F-06 `fetchLiveDisclosure` persistence, F-07 `recordProvenance` persistence, the corpus import command |
| **Blocked** | All five pending functions, on the **D-1 faculty decision**. Nothing else blocks them |

Two findings are open but block nothing: **C-53** (the ALG-11 functional
indexes are inert for the prefix predicate — confirmed by diagnostic;
resolution proposed in `docs/C53_RESOLUTION_NOTE.md`, awaiting approval) and
**C-55** (search is prefix-only, so a substring query finds nothing).

C-53 is a performance and documentation defect. The 43 passing integration
tests establish that F-01 returns **correct** results; what the diagnostic
disproved is the claim that it does so using the indexes.

---

## 1. Where things actually stand

| Milestone | Status |
|---|---|
| M1 Repository and environment | Complete, verified on two machines |
| M2 Database schema | Complete; 16 tables verified on PostgreSQL 16 |
| M3A Acquisition layer | Complete; **never run live**, no application collected |
| M3B part 1 (F-01, F-03, repository) | **Complete and PostgreSQL-verified**, commit `fc1a111` |
| M3B part 2 (F-02, F-04 to F-07) | **Blocked on D-1** |
| M4 Text processing | Complete; fixtures only |
| M5 Baseline classifier | Complete; test macro-F1 0.7489 |
| M6 Improved models | Not started; blocked on labelled alignment pairs |
| M7 Verdict and evidence engine | Complete at unit-test level |

The baseline model from M5 is the project's **reference experiment**. This
plan does not retrain it, change its split, or touch its held-out test set.

## 2. What M3A already produces

Plain frozen dataclasses in `acquisition/models.py`, with no database
dependency — which is what allowed M3A to finish while D-1 stayed open.

| Object | Carries |
|---|---|
| `Provenance` | source_type, source_url, retrieved_at, retrieval_mode, outcome, content_sha256, content_bytes, http_status, failure_reason, collector_note |
| `DataSafetyDeclaration` | package_name, entries, security, declares_no_data_collected, provenance |
| `DeclaredDataEntry` | ds_category, data_type, is_collected, is_shared, purposes, is_optional, is_ephemeral, raw_label |
| `SecurityPractices` | encrypted_in_transit, deletion_available, independent_security_review, play_families_policy |
| `PolicyDocument` | package_name, source_url, content, content_sha256, storage_path, media_type, provenance |
| `ApplicationRecord` | package_name, app_name, developer_name, store_category, play_store_url, policy_url, declaration, policy_path, policy_sha256, collected_at, provenances, validation_status |

**Provenance is deliberately per source document**, the smaller unit, so
either D-1 outcome can be assembled from it without rewriting M3A.

## 3. Mapping M3A to the 16 tables

Columns below are the schema as it stands today.

### `application` — direct, no decision needed

| M3A field | Column | Note |
|---|---|---|
| `package_name` | `package_name` | UNIQUE; the natural key |
| `app_name` | `app_name` | |
| `developer_name` | `developer_name` | nullable |
| `store_category` | `store_category` | restored by audit finding E-1 |
| `play_store_url` | `play_store_url` | |
| — | `first_seen_at`, `last_seen_at` | set by the repository, not by M3A |

### `declared_practice` — direct, one row per entry

| M3A field | Column |
|---|---|
| `DeclaredDataEntry.ds_category` | `ds_category` |
| `.data_type` | `ds_data_type` |
| `.is_collected`, `.is_shared` | same |
| `.is_optional`, `.is_ephemeral` | same |
| `.purposes` | `purpose` — **see note** |
| `.raw_label` | `raw_label` |

**Note.** M3A holds `purposes` as a tuple; the column is a single `TEXT`.
Three options: join with a separator, store the first, or widen the column.
Joining loses structure, storing the first loses data. Recommended: join with
`"; "` for M3B and raise widening it as a separate question, since it is not
part of D-1 and should not be bundled with it.

**Not representable today:** `declares_no_data_collected` and
`SecurityPractices`. Both are real parts of a declaration that the schema has
nowhere to put — see §7.

### `policy_segment` — direct, from M4

| M4 `PolicySegment` | Column |
|---|---|
| `sequence_number` | `segment_index` |
| `text` | `segment_text` |
| `char_start`, `char_end` | same |
| `heading` | `heading` |

Offsets index the cleaned text, as M4 established. The cleaned text itself
lives at `data/corpus/processed/<source-sha256>.txt`; the database stores the
segment text, so quoting never needs the file, only highlighting does.

### `disclosure_snapshot` — **this is the D-1 decision**

The mapping differs between the two options and is set out in §5 and §6.

## 4. Functions: ready, versus needing the database

### Ready now, no database involved

| Function | Where | Status |
|---|---|---|
| F-08, F-09, F-10 | `analysis/text/` | Complete, M4 |
| F-11 baseline | `analysis/models/practice_classifier.py` | Complete, M5 |
| F-14 | `analysis/confidence/gate.py` | Complete, M7 |
| F-15, F-16, F-17 | `analysis/mapping/` | Mechanism complete; **F-15 has no authored rules** |
| F-19 to F-22 | `analysis/verdict/` | Complete, M7 |

### Needs the database — M3B

| Function | Requirement | What is missing | Depends on D-1 |
|---|---|---|---|
| ~~**F-01** searchApplications~~ | FR-01 | **Done.** `application_repo.search`, ALG-11 prefix search. Index usability is C-53 | No |
| **F-02** requestAudit | FR-02 | Creating an `audit_run` row; needs the snapshot references | **Yes** |
| ~~**F-03** handleUnknownApplication~~ | FR-03 | **Done.** `handle_unknown_application`. Reports absence; inserts nothing, because the import path needs D-1 | No |
| **F-04** loadDeclaration | FR-04 | Reading `declared_practice` back into a `DataSafetyDeclaration` | **Yes** — which snapshot |
| **F-05** loadPolicyDocument | FR-05 | Resolving `storage_path` from a snapshot row | **Yes** — which snapshot |
| **F-06** fetchLiveDisclosure | FR-06 | Writing results into snapshots | **Yes** |
| **F-07** recordProvenance | FR-07 | Persisting provenance | **Yes** — one row or two |

**Three of seven do not depend on D-1 at all.** F-01, F-03 and the import path
could be built first if the team wants progress while the decision is
pending. They are flagged in §9.

### Still later

F-23 to F-34 are M8. F-12 and F-18 are M6.

---

## 5. Option A — restore the single collection-event snapshot

The originally approved Phase 3 §10.2 design: **one row per collection
event**, holding both source URLs.

```
disclosure_snapshot
  snapshot_id          bigserial PK
  app_id               bigint FK
  collected_at         timestamptz
  source_url_listing   text        -- the Play Store page
  source_url_policy    text        -- the privacy policy
  retrieval_mode       text
  policy_doc_path      text
  policy_doc_sha256    char(64)
  status               text
```

`audit_run` then carries **one** `snapshot_id`, giving six NOT NULL foreign
keys.

### How each operation works under Option A

**Application search (F-01).** Unaffected by D-1. Case-insensitive prefix
match over the functional `lower(package_name)` and `lower(app_name)` indexes,
ALG-11, O(log N + m).

**Declaration loading (F-04).** `application → latest active snapshot →
declared_practice rows → DataSafetyDeclaration`. One join. Simple, because a
snapshot *is* the collection event.

**Policy loading (F-05).** `snapshot.policy_doc_path` and
`policy_doc_sha256` feed M3A's existing loader unchanged. One row carries
both.

**Partial retrieval failure.** **This is Option A's real difficulty.** A
collection event where the policy was fetched but the Play Store listing
failed has: one hash column, one path, and only one of its two sources. The
row is either written with a NULL-ish listing URL and a `status` saying so, or
not written at all. Two sub-options:

- *A1:* make `source_url_listing` nullable and encode the outcome in `status`
  (for example `policy_only`, `listing_only`, `complete`, `fetch_failed`).
  Workable, but `status` then carries a compound meaning and the per-source
  HTTP status and failure reason have nowhere to live.
- *A2:* add a side table for per-source retrieval attempts. That is a
  seventeenth table and a larger departure from the approved design than
  Option B.

Phase 1 named scraper breakage the project's highest-probability risk, so this
is not a corner case; it is expected to be common.

**Provenance (F-07).** One row per collection event. M3A produces two
`Provenance` objects per event, so the repository merges them. The merge loses
per-source `http_status`, `content_bytes` and `failure_reason` unless A2 is
adopted.

**Audit history (F-29, F-30).** Clean: one snapshot per collection event means
`audit_run → snapshot → collected_at` orders history directly, and FR-25's
"snapshots over time" reads naturally.

**SHA-256 verification.** One hash, for the policy document. The Data Safety
declaration is parsed into rows rather than stored as a document, so it has no
hash — meaning a change in the declaration can only be detected by comparing
parsed rows, not by comparing a digest.

### Schema and migration implications

- Rewrite `disclosure_snapshot` columns.
- `audit_run`: two snapshot FKs become one. Six NOT NULL FKs.
- `declared_practice.snapshot_id` and `policy_segment.snapshot_id` keep
  pointing at the same table, now meaning "the collection event".
- **DOC-1 resolves by amending §10.3** from "seven foreign keys" to six.
- The project database `privacy_auditor` is still **empty and never
  migrated**, so this can be folded into a re-freeze of `0001_baseline`
  rather than becoming a second revision. The two existing test databases
  would be superseded; new ones can be created alongside them without
  dropping anything.
- Audit finding **E-2** (`status`) is satisfied by this design, since `status`
  is part of it.

---

## 6. Option B — retain source-specific snapshots

The schema as implemented: **one row per source**, discriminated by
`source_type ∈ {data_safety, privacy_policy}`. `audit_run` carries
`ds_snapshot_id` and `policy_snapshot_id`, giving seven NOT NULL foreign keys.

**Requires explicit faculty approval**, because it departs from §10.2 and
needs a recorded `REQUIREMENT_CHANGE_LOG.md` entry.

### How each operation works under Option B

**Application search (F-01).** Identical to Option A. Unaffected.

**Declaration loading (F-04).** `application → latest active snapshot WHERE
source_type = 'data_safety' → declared_practice rows`. One extra predicate.

**Policy loading (F-05).** `latest active snapshot WHERE source_type =
'privacy_policy' → storage_path, content_sha256`. Feeds M3A's loader
unchanged.

**Partial retrieval failure.** Handled naturally. The successful source gets
its row with its own hash, HTTP status and byte count; the failed one gets no
row, or a row recording the failure. No column has to mean two things, and
M3A's five `Provenance.outcome` values map straight through.

**Provenance (F-07).** One row per source document, which is exactly what M3A
produces. No merge, no information lost.

**Audit history (F-29, F-30).** Slightly harder. "The history of this
application" means pairing a Data Safety snapshot with a policy snapshot, and
the two sources can be collected at different times. Two approaches:

- *B1:* `audit_run` is the pairing. History is the sequence of audits, which
  is what FR-25 and FR-26 actually compare. Recommended — the comparison in
  F-30 is between **audits**, not between snapshots.
- *B2:* add a nullable `collection_event_id` grouping the two rows. Restores
  the event concept without losing per-source detail, at the cost of one more
  column.

**SHA-256 verification.** **Stronger than Option A.** Both sources are hashed,
so a changed Data Safety page is detectable by digest rather than by diffing
parsed rows, and `content_sha256` is NOT NULL on every snapshot.

### Schema and migration implications

- **No schema change at all.** The tables as frozen in `0001_baseline` and
  verified on PostgreSQL 16 already implement this.
- **DOC-1 resolves by amending §10.2** to list two snapshot foreign keys, and
  §10.3's "seven" becomes correct.
- **E-2 still outstanding.** A `status` column is needed, and M3A established
  the value set it requires: section parsed with declarations; section parsed
  with an app-level no-collection declaration; section absent; fetch failed.
- Needs a faculty-approved change-log entry before implementation.

---

## 7. Comparison, and what each option costs

| | Option A | Option B |
|---|---|---|
| Matches approved §10.2 | **Yes** | No — needs approval |
| Schema change required | Yes, moderate | **None** |
| Re-freeze of `0001_baseline` | Yes | No |
| Partial retrieval | Awkward; needs A1 or A2 | **Natural** |
| Per-source HTTP status, bytes, failure reason | Lost unless A2 | **Kept** |
| Declaration change detectable by hash | No | **Yes** |
| Provenance mapping from M3A | Merge, lossy | **One to one** |
| Audit history | **Direct** | Via `audit_run`, or B2 |
| `audit_run` NOT NULL FKs | 6 | 7 |
| DOC-1 resolved by | amending §10.3 | amending §10.2 |
| E-2 `status` | included | still needed |

**Neither option is blocked by anything technical.** The decision is about
which document gets amended and whether the partial-retrieval case is handled
by the schema or around it.

### Two things the schema cannot represent under *either* option

Both surfaced in M3A and are independent of D-1:

1. **`declares_no_data_collected`** — Google publishes an app-level "this app
   doesn't collect or share any user data" statement. It is distinct from a
   declaration that omits a category, and ALG-8 could reasonably treat it
   differently. No column holds it.
2. **`SecurityPractices`** — encryption in transit, deletion availability,
   independent security review. Part of the published section; no column.

Neither is required by FR-01 to FR-07, so M3B can proceed without them. They
should be raised as their own question rather than folded into D-1.

---

## 8. Proposed implementation sequence for M3B

Once D-1 is decided.

| Step | Work | Depends on D-1 |
|---|---|---|
| ~~B1~~ | `ApplicationRepository`, prefix search, unknown-application report (F-01, F-03) — **complete, `fc1a111`** | No |
| B2 | `SnapshotRepository`: write and read snapshots (F-07 persistence) | **Yes** |
| B3 | Declaration persistence and reload (F-04) | **Yes** |
| B4 | Policy path resolution into M3A's loader (F-05) | **Yes** |
| B5 | Corpus import command: filesystem corpus → database | **Yes** |
| B6 | Live retrieval writing through the gateway (F-06) | **Yes** |
| B7 | Integration tests against `privacy_auditor_*_test` | **Yes** |

Every repository gets an interface so the analysis layer never imports
SQLAlchemy, preserving the separation M4, M5 and M7 rely on.

**B1 is complete.** B2 to B7 remain blocked on D-1.

What B1 did *not* include, and still needs the D-1 ruling: inserting an
application row. F-03 reports that a package is absent; it cannot add it,
because the corpus import path writes snapshots.

---

## 9. Proposed pilot — approximately 20 applications

**Nothing has been collected. The operational corpus contains zero
applications.** The one record in `tests/fixtures/sample_corpus` is invented
and `com.example.sampleapp` is not a real application. This section proposes
how collection would be done; it does not report that any has happened.

### Selection, 20 applications

Chosen to exercise the pipeline rather than to be representative — a
20-application pilot cannot be representative of anything.

| Group | Count | Why |
|---|---|---|
| Popular Indian consumer apps | 6 | The project's stated context |
| Apps declaring extensive collection | 4 | Exercises multi-category declarations |
| Apps declaring **no** data collected | 3 | Tests the app-level negative and `declares_no_data_collected` |
| Apps with short policies | 3 | Tests F-10's analysability floor |
| Apps with long or PDF policies | 2 | Tests segmentation limits and the PDF path |
| Apps whose policy is in a non-English language | 2 | Establishes whether the project must scope to English |

The last group matters: if a substantial share of Indian Play Store apps
publish non-English policies, that is a scoping question for the faculty
guide, not something to discover during the final demonstration.

### Procedure per application

Follows `docs/M3_ACQUISITION_REPORT.md` §10, which is already written and
tested:

1. Record package name, app name, developer, store category.
2. Save the privacy policy page as HTML.
3. Rename it to its SHA-256.
4. Transcribe the Data Safety declaration into the documented format,
   recording only what the page states and leaving anything unstated null.
5. Record provenance for both sources with the collection date.
6. Write `record.json`.
7. Run `python scripts/validate_corpus.py --write-manifest`.

### Division of work

Roles R1 to R6 remain placeholders; **no work is assigned and no contribution
is attributed.** A reasonable division would be three or four applications per
member, with a second member re-checking each declaration against the live
page, since transcription is the step most likely to introduce error.

### Acceptance criteria

The pilot succeeds when:

- 20 records validate with zero errors.
- Every policy hash verifies.
- Every record carries provenance for both sources.
- Each of the six groups above has at least one usable record.
- The M4 pipeline runs over all 20 and reports its analysability outcomes.
- The M5 baseline produces predictions on real segments — **as a smoke test,
  not an evaluation.** There are no gold labels for these 20 applications, so
  no accuracy figure can be computed from them, and none will be reported.

### What the pilot will probably reveal

Recorded in advance so the findings are not presented later as successes:

- **The declaration normalisation rules will need changing.** They were
  written from Google's documentation, never from an inspected page.
- **Extraction will need adjustment.** M4 has only ever processed invented
  fixtures; real policies carry consent banners, cookie tables and navigation
  that the conservative cleaner deliberately keeps.
- **Some policies will not be retrievable** — dead links, PDF-only, or
  script-rendered pages the project does not execute.
- **The F-10 thresholds are provisional** and were chosen against OPP-115
  website policies, not Android ones.

### Budget and safety

Manual collection, no scraping, no paid service. Spend remains ₹0.

---

## 10. Explicitly out of scope for this plan

No model, migration, database or application code was modified. M4 and M5 are
untouched; the baseline model, its split, its seed and its held-out test
results are unchanged and will not be regenerated to produce a better number.

M3B is not implemented. M6 is not started.

## 11. What is needed to proceed

1. **The D-1 decision.** Everything in §8 except B1 waits on it.
2. If Option B: **faculty approval** and a `REQUIREMENT_CHANGE_LOG.md` entry.
3. **DOC-1**: amend §10.3 under Option A, §10.2 under Option B.
4. **E-2** `status`: included in Option A, still outstanding under Option B.
5. A decision on `declares_no_data_collected` and `SecurityPractices`, which
   neither option currently stores.
6. Approval to begin the 20-application pilot, which can start **before** D-1
   is settled, since the filesystem corpus does not depend on it.
