# M8 — Backend Integration

**Date:** 2026-11-06 · **Owner:** R4 · **Status:** implemented; the queue
claim is verified on PostgreSQL 16, the four pipeline tests are pending a
spaCy install on the host.

M8 built the component the project did not have: the thing that turns a row in
`audit_run` into a finished report. Acquisition, text processing, the models,
the mapping and the verdict engine all existed and all worked in isolation.
Nothing connected them.

## 1. What runs

`AuditPipeline.run(audit_id)` takes one queued audit to `completed`, in the
approved order, persisting at every stage:

| Step | Function | Persisted to |
| --- | --- | --- |
| Load the collection event and its policy | F-04, F-05 | — |
| Extract, segment, check analysability | F-08, F-09, F-10 | `policy_segment` |
| Classify practices | F-11 | `extracted_practice` |
| Confidence gate | F-14 | `extracted_practice.abstained` |
| Taxonomy mapping | F-15 | — |
| Normalise the declaration, build candidates | F-16, F-17 | — |
| Semantic alignment | F-18 | `alignment_judgement` |
| ALG-8 verdicts | F-19 | `verdict` |
| Evidence, absence, inconclusive records | F-20, F-21, F-22 | `evidence_record` |
| Report assembly | F-23 | E5 response |

`AuditWorker` claims one audit at a time through `claim_next_audit`, which
takes the oldest queued row under `FOR UPDATE SKIP LOCKED` on PostgreSQL and
returns nothing while another audit is `running` — design decision DD-2, one
resident model set. The claim commits before the work begins, so a crash
mid-audit leaves the row `running` with a `claimed_at` rather than silently
back in the queue. `stop()` finishes the audit in hand.

E1–E11 are implemented in one route module; see
`docs/IMPLEMENTATION_TRACEABILITY.md` for the endpoint table.

Three containers, unchanged in number: `database`, `api`, `worker`.

## 2. Three refusals

Each exists so a report never claims more than the data supports.

1. **An unanalysable policy fails the audit** with F-10's own reason. Verdicts
   drawn from an error page would describe the error page.
2. **A missing model fails at construction.** The classifier and the aligner
   are injected Protocols. There is no default, no fallback and no stub inside
   the pipeline module.
3. **An empty F-15 rule table fails the audit.** This is the project's current
   state and the refusal is load-bearing — see §6.

## 3. Fixtures are allowed and never disguised

`register_fixture_models` writes `model_version` rows whose
`model_identifier` begins `fixture:` and whose notes say "Not a trained
model". The pipeline reads those identifiers back into
`AuditOutcome.uses_fixture_models`, and `ReportOut.uses_fixture_models`
carries it to the client. A stub-backed report therefore declares itself in
its own provenance rather than only in a test docstring. Two tests assert
exactly that, so the distinction cannot quietly regress.

Every report also carries a `scope_note`: the system compares two *stated*
disclosures, does not observe what the application does, and produces no legal
compliance finding.

## 4. Tests

| Suite | Result |
| --- | --- |
| Full suite | **625 passed, 78 skipped** |
| New in M8 | 38 — 20 API (E1–E11), 18 pipeline, queue and worker |
| New PostgreSQL integration tests | 6, **all skipped here** (no `TEST_DATABASE_URL`) |
| `ruff check .` | clean |

The 78 skips are not passes. 72 are the pre-existing PostgreSQL and
model-dependent suites; 6 are the new M8 integration tests. They are gated on
`0003_collection_event` by **ancestry**, not head equality — the defect class
C-56, C-60, C-61 and C-62 all belonged to, now closed statically.

## 5. What a fixture-backed run actually produces

Verified on SQLite with injected stubs: five segments, two practices (one
above and one below the 0.50 gate), two judgements, 14 verdicts — ALG-8 gives
every Data Safety category one, including those neither source mentions — and
evidence records whose `quoted_text` equals the stored segment's text at the
stored offsets, which a test re-derives by slicing the freshly extracted
document.

Two approved behaviours are now locked by tests: a Consistent verdict carries
no evidence record (F-23), and a sub-threshold practice is stored and flagged
rather than discarded, so the uncertainty reaches ALG-8 and can become
Undetermined.

## 6. A real-model audit does not run

Checked by calling each loader, not assumed:

| Loader | Result |
| --- | --- |
| `load_baseline_classifier` | **Unavailable** — the M5 artefact is not at `ml/checkpoints/baseline_classifier` in this environment; git-ignored by design, rebuilt with `python ml/train_baseline_classifier.py` |
| `load_aligner` | **Unavailable** — F-18 needs torch and transformers (not installed here) and a downloadable zero-shot checkpoint (403-blocked) |
| `load_mapper` | Returns a mapper holding **zero rules**; the pipeline refuses |

The first two lift on the Mac. The third does not: **authoring the F-15
mapping rules is the single piece of project work between this backend and a
real audit.** Until they exist, a real run would arrive at ALG-8 with the
declaration side only and report *Declared-not-in-policy* against every
category the application declared — findings manufactured by a missing table.
The pipeline refuses instead. See C-69 defect 6.

## 7. PostgreSQL: what the first run settled, and what it did not

Run 2026-11-06 against `privacy_auditor_m8_20261106_test`, PostgreSQL 16,
Python 3.12.16: **74 passed, 4 failed** (C-71).

**Verified:** `FOR UPDATE SKIP LOCKED`. Both queue tests passed — a second
worker on its own connection could not claim an audit the first had locked
but not committed, and an aborted claim left the audit claimable. This is
untestable anywhere else: SQLite ignores the clause, so the unit suite proves
nothing about it, and DD-2 rests on it. The chain also applied cleanly to a
fresh database and all 68 pre-existing integration tests passed at head.

**Not a defect:** the four failures are all
`SegmenterUnavailableError: spaCy is not installed` — exactly the four M8
tests that run the pipeline. spaCy is pinned in `backend/requirements.txt`
and the host virtual environment lacked it and the model. F-09 has no
fallback splitter on purpose: another splitter moves sentence boundaries, so
the same policy would yield different evidence offsets on different machines.

**Still unverified:** the CHECK constraints under a complete run, `jsonb`
threshold round-tripping, evidence offsets and non-ASCII quotes through real
columns, and E5 assembling a report from PostgreSQL-validated rows. Steps 10
to 12 of the script — downgrade, guard skips, re-upgrade, ALG-11 diagnostic —
were not reached either, since the run stops at step 9.

Install the dependency once, then re-run:

```
cd "/Users/anshu/Documents/Major Project"
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python -m spacy download en_core_web_sm
bash scripts/verify_migrations.sh
```

A new step 0c checks for spaCy and the model before touching Docker, so a
missing dependency now fails in two seconds instead of ninety.

It creates one new database, `privacy_auditor_m8_20261106b_test`, runs the
whole chain up, the integration suite at head, down to the baseline to prove
the guards skip, and up again. It issues no `DROP` anywhere, aborts if that
name already exists, and never names `privacy_auditor`,
`privacy_auditor_test` or `privacy_auditor_frozen_20261105_test`. No password
is printed or typed.

## 8. Files

**New**

* `backend/app/services/audit_pipeline.py` — the pipeline, `claim_next_audit`
* `backend/app/worker/worker.py` — `AuditWorker`, the process entry point
* `backend/app/services/model_registry.py` — loaders, `register_fixture_models`
* `backend/app/api/routes/audits.py` — E1–E11
* `backend/app/api/schemas/audit.py` — request and response models
* `tests/unit/test_audit_pipeline.py`, `tests/api/test_audit_endpoints.py`,
  `tests/integration/test_m8_pipeline_postgresql.py`

**Changed**

* `backend/app/main.py` — router registered
* `analysis/mapping/taxonomy_mapper.py` — `rule_count` (read-only, additive)
* `docker-compose.yml` — worker `restart: on-failure:3`
* `scripts/verify_migrations.sh` — fresh disposable database; the previous one
  protected
* `pyproject.toml` — ruff `extend-immutable-calls` for FastAPI's `Depends`

**No migration was added or modified.** The schema is unchanged at
`0003_collection_event`.

## 9. Next

**M9 — frontend.** F-24 to F-27 against E1–E11.

Running in parallel, and not blocked by M9: authoring the F-15 mapping rules,
and rebuilding the M5 checkpoint on the Mac so a real classifier can be
attached to the pipeline that is now waiting for one.
