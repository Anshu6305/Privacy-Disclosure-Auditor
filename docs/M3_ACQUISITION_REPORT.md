# Milestone 3A — Application and Disclosure Acquisition

Date: 2026-11-05
Scope: **M3A only.** M3B, the database integration, is not started and is
blocked on the D-1 faculty decision.
Task: T1. Functions F-04, F-05, F-06, F-07 in part; F-01, F-02, F-03 deferred.

---

## 1. What this milestone did and did not do

**Did.** Built an offline-first acquisition layer and a documented corpus
format: declaration normalisation, policy loading with hash verification, a
single rate-limited and cached gateway behind a replaceable adapter,
per-source provenance, a corpus manifest, a validation tool, and a worked
manual import procedure. 70 tests, all passing.

**Did not.** Retrieve anything from Google Play. Collect any application.
Change any database model, migration or database. Implement F-01, F-02 or
F-03, which are database-backed.

**There is no operational corpus.** One invented sample record exists, under
`tests/fixtures/sample_corpus`, to demonstrate the format. The target of
300–500 applications and a ~100-application gold set remains entirely
outstanding, and the team collects it.

## 2. The two datasets are not the same thing

| | OPP-115 | Operational Android application corpus |
|---|---|---|
| What | 115 **website** privacy policies with annotated practices | **Android applications**, each with a Data Safety declaration and a privacy policy |
| Purpose | Training and evaluating the classifier (F-11, F-12) | The corpus the running system audits |
| Status | Downloaded and verified: 115 documents, 23,194 practices | **Does not exist.** One invented fixture record |
| Location | `data/raw/opp115/` | `data/corpus/` |
| Target | fixed at 115 | 300–500 apps; ~100 gold-annotated |

The corpus manifest carries this distinction in a `note` field so it cannot be
confused by someone reading the data alone.

## 3. Data sources, and what has actually been verified

| Source | Status |
|---|---|
| Google Play Data Safety — the 14 categories | **Verified** from Google Play Console Help, read 2026-11-04 |
| Data Safety entry fields — data type, collected/shared declared separately, purpose, optional flag | **Verified** from Google's user-facing Data safety documentation, read 2026-11-05 |
| Security practices, data deletion, other disclosures as published sections | **Verified**, same source |
| Whether not-collected types are published | **Not established.** Google's documentation does not say. This is why audit finding D-2 was withdrawn |
| The structure of a real Data Safety page | **Not inspected.** `play.google.com` is unreachable from the development environment and is not on the session allowlist |
| Live retrieval | **Never performed** |

The normalisation rules therefore rest on Google's published documentation,
not on a sample of real pages. **Treat them as provisional until the pilot
runs.** The first 20-application pilot is expected to require changes to the
adapter, and the design puts all such changes in one file.

## 4. Corpus directory structure

```
data/corpus/                         (git-ignored; third-party content)
  manifest.json                      index, derived from the records
  provenance.jsonl                   append-only log of every attempt
  apps/
    com.example.app/
      record.json                    one application
  raw/
    policies/
      <sha256>.html                  policy documents, never modified
  processed/                         Milestone 4 output; empty for now
```

Raw documents are named by the SHA-256 of their bytes. A document is therefore
identified by its content: two applications sharing a policy share one file,
and re-saving an unchanged page produces the same name instead of a duplicate.
Raw and processed are separate directories so extraction output can never
overwrite a source document.

## 5. Record format

`record.json`, schema version 1.0:

```json
{
  "schema_version": "1.0",
  "package_name": "com.example.sampleapp",
  "app_name": "Sample App (fixture, not a real application)",
  "developer_name": "Example Developer",
  "store_category": "Tools",
  "play_store_url": "https://play.google.com/store/apps/details?id=com.example.sampleapp",
  "policy_url": "https://example.invalid/privacy",
  "policy_path": "raw/policies/410a3d40...af0.html",
  "policy_sha256": "410a3d40...af0",
  "collected_at": "2026-11-05T10:00:00+00:00",
  "declaration": {
    "package_name": "com.example.sampleapp",
    "declares_no_data_collected": false,
    "entries": [
      {
        "category": "Personal info",
        "data_type": "Email address",
        "collected": true,
        "shared": false,
        "purposes": ["App functionality"],
        "optional": false,
        "ephemeral": null,
        "raw_label": "Email address"
      }
    ],
    "security": {
      "encrypted_in_transit": true,
      "deletion_available": false,
      "independent_security_review": null,
      "play_families_policy": null
    }
  },
  "provenances": [ ... ],
  "validation_status": "fixture"
}
```

Three points worth noting.

- **`declares_no_data_collected`** records the app-level statement Google
  publishes when a developer declares the app collects and shares nothing. It
  is a distinct state from a declaration that merely omits a category, and a
  record cannot hold both it and entries — that contradiction is rejected at
  import.
- **Unstated is not denied.** A security practice the listing does not mention
  is `null`, never `false`.
- **`raw_label`** keeps the listing's own wording so normalisation can be
  audited afterwards.

## 6. Declaration normalisation (F-04)

`acquisition/declaration.py`. Reads the documented corpus format and produces
a `DataSafetyDeclaration`. Preserves collected categories, shared categories,
purposes, the optional and ephemeral flags, security practices, and the
source and retrieval metadata through the attached provenance.

Three rules the implementation enforces rather than assumes:

1. **An unknown Data Safety category stops the import**, naming the category.
   Dropping it would produce a record that looks complete while missing a
   category, and every audit of that application would under-report.
2. **A flag that is neither boolean nor absent is an error.** Coercing a
   string such as `"no"` to `True` would invert a declaration.
3. **An entry asserting neither collection nor sharing is rejected.** The
   published section lists only positive declarations, so such an entry did
   not come from one.

Mapping a particular scraper's output into this format is an adapter's job,
kept in `acquisition/adapters.py`, because Phase 1 identified scraper
maintenance as the project's highest-probability risk.

## 7. Policy loading and hash verification (F-05)

`acquisition/policy_document.py`.

- Resolves the path, opens the file **read-only**, and never writes to it.
  A test asserts the bytes and the modification time are unchanged after a
  load.
- Hashes the bytes it read and compares them against the recorded hash. A
  mismatch raises with both hashes and says to re-acquire the document rather
  than update the record.
- Returns the text and the source URL as a `PolicyDocument`, which is the
  interface Milestone 4's F-08 will consume.
- Reports a missing file, a hash mismatch and an undecodable file as three
  distinct errors, each saying what to do.
- A file that is not valid UTF-8 is **refused**, not silently decoded with
  replacement characters: analysing damaged text would produce findings about
  characters the policy does not contain.
- PDF policies are stored but not decoded here; PDF extraction is F-08.

The hash is verified on **every** load, not only at import, because the corpus
is a frozen artefact that six people copy between machines and a re-saved file
is exactly the corruption that produces a plausible but wrong audit.

## 8. Live retrieval (F-06)

`acquisition/gateway.py` and `acquisition/adapters.py`.

**Retrieval is optional and the system never depends on it.** A gateway built
without an adapter — the default — returns a recorded failure for every
request. Audits read the frozen corpus. If Google blocks us the day before the
demonstration, nothing stops working.

| Property | How |
|---|---|
| One chokepoint (NFR-16) | Everything external goes through `AcquisitionGateway` |
| Rate limiting (NFR-15) | `RateLimiter` sleeps between requests; the interval can be lengthened but **not removed** — a floor is applied so a misconfiguration cannot turn the collector into a fast scraper |
| Caching | Content-addressed by URL. A re-run over already-collected applications makes zero requests |
| Only successes cached | A failure is a fact about one moment, not the resource; caching it would make a transient outage permanent |
| Damaged cache entry | Treated as a miss. The cache is an optimisation and must not be able to break a run |
| HTTP errors | 401/403/429 → `blocked`; 404 → `not_found`; other 4xx/5xx → `fetch_failed` |
| CAPTCHA and challenges | Detected by body content, because a challenge page returns **HTTP 200**. Parsing one as a declaration would make an application appear to declare nothing |
| Parser failure | A separate outcome from a fetch failure, because the remedy differs: a parse failure means the adapter needs updating |
| Network exceptions | Captured into provenance, never propagated. One unreachable host must not end a pass over 300 applications |
| Repeat requests | Avoided by the cache; the gateway counts `requests_made` so a pass can report how many it actually issued |
| Failures corrupt nothing | A failed retrieval returns provenance with **no content hash** and writes nothing to the corpus |

**No mass scraping has been or will be performed from this project.** The
documented pilot is ~20 applications, rate-limited, spread out.

## 9. Provenance (F-07)

`acquisition/provenance.py`. Each record carries source URL, collection
timestamp, retrieval mode (`manual_import`, `live_fetch`, `cache`), document
hash, and outcome (`success`, `not_found`, `fetch_failed`, `parse_failed`,
`blocked`), plus HTTP status, byte count, failure reason and a collector note.

Two invariants are enforced in the type:

- A **success** must carry a 64-character hash. A document that cannot be
  identified is not evidence of anything.
- A **failure** must carry a reason, so the report can distinguish "nothing
  was found" from "we could not look".

**Provenance is per source document, not per collection event.** That is the
smaller unit, and either D-1 outcome can be assembled from it: under the
per-source option each becomes a row, under the collection-event option a pair
is grouped into one. Nothing here commits to either, and **no persistent
snapshot schema was introduced**.

`provenance.jsonl` is an append-only log including failures, so a collection
pass can be audited afterwards: how many applications were attempted, how many
succeeded, and why the rest did not.

## 10. Manual import procedure

This is the **primary** acquisition path, not a fallback. Phase 1 recorded the
scraper library as unmaintained, with its author advising the parser should be
expected to break; a manually saved page with an honest record of who saved it
and when is more dependable.

1. **Create the corpus directories** (once):
   ```bash
   python -c "import sys; sys.path.insert(0,'.'); \
     from acquisition.corpus import CorpusPaths; \
     CorpusPaths('data/corpus').create()"
   ```
2. **Open the application's Play Store listing** and its Data safety page.
   Note the package name, app name, developer, store category and the privacy
   policy link.
3. **Save the privacy policy page** as HTML into `data/corpus/raw/policies/`
   under any temporary name.
4. **Rename it to its own hash**:
   ```bash
   python -c "import sys; sys.path.insert(0,'.'); \
     from acquisition.policy_document import sha256_of_file; \
     print(sha256_of_file('data/corpus/raw/policies/TEMP.html'))"
   ```
   Rename the file to `<that hash>.html`.
5. **Write the declaration** into the record's `declaration` block in the
   format of section 5, transcribing only what the Data safety page states.
   Leave anything unstated as `null`. Do not infer.
6. **Record provenance** for both sources: the Data Safety URL and the policy
   URL, the date you collected them, mode `manual_import`, and the document
   hash.
7. **Write `record.json`** into `data/corpus/apps/<package_name>/`.
8. **Validate and regenerate the manifest**:
   ```bash
   python scripts/validate_corpus.py --write-manifest
   ```

Step 8 is not optional. It is what detects duplicates, missing disclosures and
hash mismatches before they reach an audit.

## 11. Validation tool

`scripts/validate_corpus.py` checks every record and regenerates the manifest
from what is on disk, so the manifest cannot drift from reality.

Errors, which make a record unusable: duplicate package names, a record whose
directory name disagrees with its package, a missing policy file, a hash
mismatch, a malformed record, a schema version mismatch, a declaration naming
a different package.

Warnings, which do not: a missing declaration, a missing policy. A corpus with
40 incomplete records is still a usable corpus of the remainder, and the
counts say exactly how many of each there are.

Actual output against the sample:

```
--------------------------------------------------------------------
Operational Android application corpus — validation
--------------------------------------------------------------------
Corpus root        : tests/fixtures/sample_corpus
Records read       : 1
Analysable         : 1  (declaration and policy both present)
Missing declaration: 0
Missing policy     : 0
Duplicates         : 0
Hash mismatches    : 0

RESULT: usable
--------------------------------------------------------------------
```

## 12. Tests and actual results

```
$ pytest tests
267 passed, 29 skipped in 0.75s

$ pytest tests/unit/test_acquisition_declaration.py \
         tests/unit/test_acquisition_policy.py \
         tests/unit/test_acquisition_gateway.py \
         tests/unit/test_acquisition_corpus.py
70 passed

$ ruff check .
All checks passed!
```

| Required coverage | Tests |
|---|---|
| Declaration normalisation | 13 |
| Policy document loading | 10 |
| SHA-256 verification | within the above; includes a re-saved file |
| Missing and corrupt policy files | 4 |
| Provenance generation | 5 |
| Manifest validation | 3 |
| Duplicate applications | 1 |
| Incomplete application records | 4 |
| Cache hit and cache miss | 4 |
| Rate limiting | 4 |
| Network failures | 4 |
| Parser failures | 2 |
| Manual import workflow | 1 end-to-end |

**What the gateway tests do not show.** They use a stub adapter and no request
leaves the machine. They demonstrate how the gateway handles responses, not
that live retrieval works. Nothing in this project has fetched a Google Play
page.

**What the sample fixture does not show.** It is invented data.
`com.example.sampleapp` is not a real application and its policy text was
written for the fixture. It demonstrates the format; it is not evidence that
an operational corpus exists.

## 13. Traceability

| Function | Requirement | Status after M3A |
|---|---|---|
| F-01 searchApplications | FR-01 | **Not implemented** — database-backed, M3B |
| F-02 requestAudit | FR-02 | **Not implemented** — database-backed, M8 |
| F-03 handleUnknownApplication | FR-03 | **Not implemented** — database-backed, M3B |
| F-04 loadDeclaration | FR-04 | **Partially implemented** — normalisation complete and tested; loading *from the database* is M3B |
| F-05 loadPolicyDocument | FR-05 | **Partially implemented** — filesystem loading and verification complete; resolving the path *from a snapshot row* is M3B |
| F-06 fetchLiveDisclosure | FR-06 | **Partially implemented** — gateway, rate limiting, caching and error handling complete and tested; **never run against a live source** |
| F-07 recordProvenance | FR-07 | **Partially implemented** — representation complete and tested; persistence is M3B |
| NFR-15 rate limiting | — | Implemented, with a floor that cannot be removed |
| NFR-16 single acquisition chokepoint | — | Implemented |

**M3A is not the completion of F-01 to F-07.** Four of the seven are partial
and three are not started.

## 14. Dependency on D-1

D-1 — whether a disclosure snapshot is one row per collection event or one row
per source — is unresolved and awaits faculty approval. M3A was built so that
it does not need the answer:

- No SQLAlchemy model was changed.
- No Alembic migration was modified.
- No database was created, modified or read.
- Provenance is per source document, the unit from which either arrangement
  can be assembled.
- No persistent snapshot schema was introduced.

**Deferred to M3B, pending D-1:** F-01, F-02, F-03; the database side of F-04
and F-05; persisting provenance and snapshots; the repository implementations
behind those functions.

Also pending and related: finding **E-2**, `disclosure_snapshot.status`. M3A
has established that at least four states need recording — section parsed with
declarations, section parsed with an app-level no-collection declaration,
section absent, and fetch failed — which is a concrete input to that decision.

## 15. Known limitations

1. **No live retrieval has ever been performed.** The normalisation rules rest
   on Google's documentation, not on observed pages. The pilot will probably
   change them.
2. **No operational corpus exists.** One invented fixture record.
3. **`play.google.com` is unreachable from the development environment**, so
   the adapter cannot be exercised here at all. The pilot must run on a team
   machine.
4. **The declaration format is ours, not Google's.** An adapter translating a
   scraper's output into it does not yet exist, because there is nothing to
   test it against.
5. **PDF policies are stored but not readable** until F-08.
6. **Nothing is persisted.** Every object in this milestone lives in memory or
   in files.

## 16. Budget and collection safety

No paid API, service or subscription was used or is required. Everything in
this milestone is free and open source. Spend to date remains ₹0 of the
approximately ₹10,000 ceiling.

The rate limiter's floor, the cache, the offline-by-default gateway and the
~20-application pilot together implement the Phase 1 constraints: collect
slowly, freeze early, and never depend on Google Play during a demonstration.

## 17. Team

Roles remain R1 to R6 placeholders. No collection work has been performed or
assigned, and no contribution is attributed to any member. The six team
members collect and review the operational records; nothing in this report
claims any of that has begun.
