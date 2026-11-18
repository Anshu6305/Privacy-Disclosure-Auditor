# Database size, type and connection estimates

Supplementary to the approved Phase 3 System Design Document. It adds the
explicit sizing arithmetic the faculty instructions ask for. **The approved
report is not modified**; Phase 3 §10 remains the authority on schema and
storage policy, and this document only puts numbers to it.

Prepared 18 November 2026. Every measured value is marked **[measured]** and
every assumption **[assumed]**.

---

## 1. Database type

**PostgreSQL 16**, in a Docker container, with SQLAlchemy 2.0.36 and psycopg
3.2.3. Phase 3 §16 selected it for the `CHECK` constraints that enforce the
five-verdict vocabulary and the four gold-set labels, for functional B-tree
indexes on lower-cased columns (FR-01 prefix search), and for
`FOR UPDATE SKIP LOCKED`, which makes the `audit_run` table a job queue without
a message broker.

16 tables, three migrations, the baseline frozen.

## 2. What one audited application costs

### Measured inputs

| Quantity | Value | Source |
|---|---:|---|
| Raw policy document (HTML) | 196,868 bytes | **[measured]** `com.spotify.music`, SHA-256 `13089e7b…4ea8` |
| Cleaned policy text | 43,244 characters | **[measured]** `extract_policy_text` output |
| `policy_segment` rows | 629 | **[measured]** pilot run |
| `extracted_practice` rows | 3,386 | **[measured]** pilot run |
| `alignment_judgement` rows | 611 | **[measured]** pilot run |
| `verdict` rows | 14 | **[measured]** one per Data Safety category |
| `evidence_record` rows | 18 | **[measured]** audit 13, team-reported |
| `declared_practice` rows | 19 | **[measured]** Data Safety entries in the record |

### Assumptions

* **[assumed]** PostgreSQL per-row overhead of 24 bytes (23-byte header plus
  alignment), and 4 bytes per item in the page line pointer array.
* **[assumed]** `bigint` 8 B, `integer` 4 B, `boolean` 1 B, `timestamptz` 8 B,
  `double precision` 8 B; variable text costs its own bytes plus a 1–4 byte
  length header.
* **[assumed]** Index overhead of 40 % of heap size for these tables. They
  carry one to four B-tree indexes each; 40 % is a conventional working figure
  and is not measured here.
* **[assumed]** One audit per application. Re-audits multiply the per-audit
  tables, not `application` or `disclosure_snapshot`.

### Calculation, per application, per audit

| Table | Rows | Bytes/row | Heap |
|---|---:|---:|---:|
| `policy_segment` | 629 | 24 overhead + 28 numeric + ~69 text | 75.9 KB |
| `extracted_practice` | 3,386 | 24 + 24 numeric + ~32 category text | 271.0 KB |
| `alignment_judgement` | 611 | 24 + 32 numeric + ~14 label | 42.8 KB |
| `evidence_record` | 18 | 24 + 28 + ~100 quote or reason | 2.7 KB |
| `declared_practice` | 19 | 24 + 10 + ~26 category | 1.1 KB |
| `verdict` | 14 | 24 + 26 + ~30 | 1.1 KB |
| `disclosure_snapshot` | 1 | 24 + 36 + ~340 URLs and hash | 0.4 KB |
| `application` | 1 | 24 + 8 + ~120 | 0.2 KB |
| **Heap subtotal** | | | **395.2 KB** |
| Indexes at 40 % | | | 158.1 KB |
| **Database total** | | | **≈ 553 KB** |
| Raw policy on the filesystem | | | **≈ 192 KB** |

Two tables dominate, and for a reason worth stating: `extracted_practice`
holds one row per (segment × category) pair that the classifier scored, which
is 629 × 10 minus the rows the candidate floor dropped. It is the price of
FR-14 and NFR-05 — the system keeps the score for a category it rejected, so
"the classifier looked and found nothing" stays distinguishable from "the
classifier was never asked".

## 3. Projection to the designed corpus

| Corpus | Applications | Database | Policy files | Total |
|---|---:|---:|---:|---:|
| **Current actual** | 1 | 0.5 MB | 0.2 MB | **0.7 MB** |
| Phase 3 lower bound | 300 | 162 MB | 56 MB | **218 MB** |
| Phase 3 upper bound | 500 | 270 MB | 94 MB | **364 MB** |
| NFR-19 ceiling | 1,000 | 540 MB | 188 MB | **728 MB** |
| NFR-19 ceiling, 3 audits each | 1,000 | ≈ 1.6 GB | 188 MB | **≈ 1.8 GB** |

**[measured]** the 1-application row; **[assumed]** linear scaling of the
per-application figure for the rest, which holds because no table is quadratic
in corpus size and the only cross-application table is `taxonomy_mapping_entry`
(30 rows, fixed).

At the NFR-19 ceiling the database is **under 2 GB**. That is comfortably
within a single PostgreSQL instance on the 8 GB development machine Phase 1
assumed, and it is why Phase 3 rejected `pg_trgm` and a separate search
service: at this size a sequential scan completes in milliseconds.

**The dominant disk cost of this project is not the database.** It is the
model checkpoints — 0.81 GB of runtime assets, against 0.5 MB of audit data
for the collected corpus.

## 4. Connection estimates

### Configured

`backend/app/db/session.py` calls
`create_engine(url, pool_pre_ping=True, future=True)` with **no explicit pool
size**, so SQLAlchemy's `QueuePool` defaults apply: **[measured, from the
default]** `pool_size=5`, `max_overflow=10` — at most **15 connections per
process**.

### Expected demand

| Process | Pool | Peak connections |
|---|---|---:|
| API (`uvicorn`, 1 worker process) | 5 + 10 overflow | 15 |
| Audit worker (1 process, DD-2: one audit at a time) | 5 + 10 overflow | 15 |
| Alembic, during a migration only | 1 | 1 |
| **Peak total** | | **31** |

PostgreSQL 16's default `max_connections` is 100, which the compose file does
not override. Headroom is therefore about **3×** at the configured pool sizes,
and far more against real demand: Phase 3 §16 expects **five concurrent
requests**, and the worker holds one connection for the duration of an audit
because DD-2 allows one active audit.

**[assumed]** one `uvicorn` worker process. Running N API workers multiplies
the API row by N; at four workers the peak becomes 75, still inside the
default. Beyond about six API workers, `max_connections` or a pooler such as
PgBouncer would need raising — stated here as the known scaling point, not as
a change being proposed.

### Not measured

No load test has been run. The 15-per-process figure is the configured
maximum, not an observed one; observed concurrent use has been one request at
a time. NFR-04's five-request target is **implemented by design and not
verified by measurement**, and the traceability matrix records it that way.
