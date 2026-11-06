# M11 — Model Integration, End-to-End Verification and Phase Closure

**Date:** 2026-11-06 · **Status:** implementation complete; **Phase 4 not yet
ready for closure.** One blocker is external and one is data collection.
Both are named precisely in §7.

Four statuses are kept apart throughout: **implemented**, **tested**,
**PostgreSQL-verified**, and **demonstrated on real data**.

## 1. F-12 — trained checkpoint integrated and independently re-evaluated

The Colab checkpoint (`distilbert-base-uncased`, 4 epochs, Tesla T4) was
verified complete and readable, loads through the registry, and performs real
inference. Its `metadata.json` matches the approved configuration exactly:
seed 20261105, 55 labels, 1,713 / 401 / 352 segments.

**The metrics file was not downloaded with the weights.** Rather than
transcribe figures from a notebook console, `ml/evaluate_span_extractor.py`
re-derives them from the checkpoint and the same held-out split, reusing the
trainer's own `score_segments` so the definition of a correct span cannot
differ between the two runs.

| Test split, 352 segments | Value |
| --- | --- |
| Gold spans | 1,010 |
| Predicted spans | 1,415 |
| **Exact** precision / recall / F1 | **0.0919 / 0.1287 / 0.1072** |
| Overlapping precision / recall / F1 | 0.4848 / 0.6792 / 0.5658 |
| Spans that did not slice back out | **0** |

These match the reported Colab run to four decimal places, which is the
evidence that the integrated checkpoint is the one that was trained.
`ml/runs/span-extractor-v1-metrics.json` has been regenerated locally.

**What the numbers mean.** Exact F1 0.107 means the span boundaries are right
roughly one time in ten. Overlap F1 0.566 means the model usually finds about
the right region with the right value. The gap between them is the boundary
error, and it is large. Observed directly: given "We collect your precise
location", the model returns `Location` over "your precise location to" — the
right value, one word too far.

**This model is not accurate and is not production-ready.** No threshold was
lowered to make the pipeline produce more verdicts. The abstention gate works:
in a six-span real example, four fell below 0.50 and were flagged. They stay
uncertain and cannot become confident absence findings, which matters more
here than the F1 does.

The 0 unverifiable spans is the one unambiguously good figure — every span
sliced back out of its segment exactly, so no quote the model produces can be
text the policy does not contain.

## 2. F-11 — verified

The rebuilt M5 baseline loads through the registry and is the model the
inference path uses. Split, seed, label rule and evaluation are unchanged;
Macro-F1 0.7489 / Micro-F1 0.7690 stand from M10's exact reproduction. **No
improvement is claimed.**

## 3. F-15 — verified

30 authored rules, 16 partial, 11 documented refusals to map, each with a
rationale the loader requires. 28 tests cover valid mappings, the
Contact/Contacts trap, the ambiguous `User online activities` case, unmapped
data types, unmapped categories and four loader validations.

**30 rules is not taxonomy coverage.** They cover 14 of the 17 data-type
values that occur in the corpus and 2 of the 10 OPP-115 categories, by
design; the other 8 categories describe practices *about* data and are
refused. Partial mappings remain flagged partial and ambiguity is emitted as
two partial rules rather than resolved into one confident match.

An empty or unfirable rule table causes the pipeline to refuse (C-69, C-76).

## 4. F-18 — implemented, blocked by an external dependency

The zero-shot path is complete. M11 extracted `resolve_nli_label_indices()`
so the head's label order is read from the model's own `id2label` and can be
tested without downloading one — six tests over the three orders published
NLI models actually use. `cross-encoder` puts entailment at index 1 and
`roberta-large-mnli` at index 2; a fixed order would invert SUPPORTS and
CONTRADICTS for one of them while every other test still passed.

`TransformersNliBackend` now prefers a local `ml/checkpoints/nli-mnli-v1`
over the hub identifier, mirroring F-12.

**No inference has been run.** `huggingface.co` returns 403 at this
environment's proxy — confirmed by attempting the download, not assumed. The
safe refusal is intact: `load_aligner` raises `ModelsUnavailableError` and
`AuditPipeline` cannot be constructed without an aligner. Nothing was
substituted and no architecture was changed to work around it.

## 5. Corpus — tooling complete, collection outstanding

`play.google.com` is not on this environment's allowlist, confirmed by
attempting a fetch; mass scraping was forbidden by the approved design in any
case. `scripts/manual_collect.py` is the documented manual path. It writes
the same record an automated collector would, with the same provenance, and
refuses to invent: an omitted declaration stores **no declaration**;
`declares_no_data_collected` stays null when unset, because *not read* is a
third state; a category outside the approved fourteen is refused; the policy
file is stored byte for byte and hashed as-is.

**`data/corpus/apps/` is still empty. No real Android application has been
audited.**

## 6. Real-model pipeline run

`scripts/demo_real_models.py` runs F-08 → F-22 over a genuine published
privacy policy from OPP-115 with the **real rebuilt M5 classifier**, the
**real trained F-12 checkpoint**, the **30 authored F-15 rules**, and a
fixture aligner.

Result on `1017_sci-news.com.html`: 20 segments, 199 practices, 32
judgements, 14 verdicts, 9 evidence records, and **every quote an exact slice
of the stored document**. Four categories carry `abstention_involved`.

**It is a demonstration, not an audit, and the script says so.** An audit
compares two disclosures; no Data Safety declaration exists, so the
declaration side is empty by fact rather than by finding. Every
In-policy-not-declared means "the policy says this and nothing was collected
to compare it against" — not that a developer failed to declare something.
`uses_fixture_models` is true because F-18 was stubbed.

One input artefact: OPP-115's `sanitized_policies` files use `|||` as a
segment separator and it appears in the quoted evidence. That is a property
of this stand-in input, not of the pipeline; a real audit reads a saved HTML
page.

## 7. Test results

| Suite | Result |
| --- | --- |
| Backend `pytest tests` | **690 passed, 78 skipped, 0 failed** |
| Skip reason | **all 78 are PostgreSQL** (`TEST_DATABASE_URL` unset). No ML test skipped here |
| `ruff check .` | clean |
| Frontend Vitest | **32 passed** |
| `npm run lint` / `vite build` | clean / succeeds |
| PostgreSQL integration | **not re-run — see below** |

Tests using **real models and real weights**: `test_f12_real_inference.py`
(7) and the demonstration script. Tests using **fixtures or mocks**:
everything else, including all 32 frontend tests.

**Environment caveat.** torch 2.5.1 and transformers 4.46.3 were installed in
the development environment during M11, so the `ml`-marked tests run here. On
a machine without them those tests **skip**, and a skip is not a pass.

**PostgreSQL was not re-run.** It is unreachable from the development
session; the command is in §9. No schema or migration changed in M11, but
`ml/backends.py`, `model_registry.py` and the span extractor did.

## 8. Files changed

**New:** `ml/evaluate_span_extractor.py`, `scripts/manual_collect.py`,
`scripts/demo_real_models.py`, `tests/unit/test_f18_label_resolution.py`,
`tests/unit/test_f12_real_inference.py`, `docs/M11_REPORT.md`,
`docs/PHASE4_COMPLETION_AND_TRACEABILITY_REPORT.md`.

**Changed:** `ml/backends.py` (local checkpoint preference,
`resolve_nli_label_indices`), `docs/IMPLEMENTATION_TRACEABILITY.md`,
`docs/PHASE4_CONSISTENCY_LOG.md` (C-79 to C-82),
`docs/REQUIREMENT_CHANGE_LOG.md`, `docs/TEAM_TRACKER.md`,
`scripts/verify_migrations.sh` (fresh disposable database).

No schema, migration, API contract, requirement identifier or frontend screen
changed.

## 9. What you need to run

```
cd "/Users/anshu/Documents/Major Project"

# 1. PostgreSQL re-verification
bash scripts/verify_migrations.sh

# 2. F-18 checkpoint, on any machine with network access
.venv/bin/pip install -r backend/requirements-ml.txt
.venv/bin/python -c "
from huggingface_hub import snapshot_download
snapshot_download('cross-encoder/nli-distilroberta-base',
                  local_dir='ml/checkpoints/nli-mnli-v1')
"
```

Fresh disposable database `privacy_auditor_m11_20261106_test`.

## 10. Conclusion

**Phase 4 is not yet ready for closure.** Every implementation and
integration task that could be completed has been, and the pipeline now runs
end to end on real policy text with two of three models real. Two things
genuinely remain:

1. **F-18 has never performed inference.** The code is complete; the
   checkpoint cannot be downloaded from this environment. One command on a
   networked machine resolves it.
2. **No real application has been audited.** `data/corpus/apps/` is empty.
   The manual collection tool is written and the collection itself needs a
   person with a browser.

Until both are done, the system has never compared two real disclosures,
which is the thing the project exists to do. Closing Phase 4 on a green test
suite would be closing it on fixtures.

Phase 5 is the separate academic validation and testing phase and is not
started.
