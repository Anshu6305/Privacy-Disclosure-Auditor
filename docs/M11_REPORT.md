# M11 — Model Integration, End-to-End Verification and Phase Closure

**Date:** 2026-11-06 · **Status:** implementation complete and verified; **Phase 4 not yet ready
for closure.** One blocker remains: no real application has been audited.
F-18 and PostgreSQL were both resolved after the first draft of this report
and the sections below record the actual results.

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

## 4. F-18 — implemented and verified

The zero-shot path is complete. M11 extracted `resolve_nli_label_indices()`
so the head's label order is read from the model's own `id2label` and can be
tested without downloading one — six tests over the three orders published
NLI models actually use. `cross-encoder` puts entailment at index 1 and
`roberta-large-mnli` at index 2; a fixed order would invert SUPPORTS and
CONTRADICTS for one of them while every other test still passed.

`TransformersNliBackend` now prefers a local `ml/checkpoints/nli-mnli-v1`
over the hub identifier, mirroring F-12.

**Real inference verified.** The checkpoint was downloaded on the networked
machine into `ml/checkpoints/nli-mnli-v1` and loads through the registry.
Seven tests cover all three outcomes.

**The label order was not the common one.** This checkpoint reports
`{contradiction: 0, entailment: 1, neutral: 2}` — entailment at index 1,
where most MNLI heads put neutral. Code assuming the usual order would have
read entailment probabilities out of the neutral slot on every pair while
every other test still passed. The config-driven resolution is why that did
not happen.

| Premise | Hypothesis | Result |
| --- | --- | --- |
| "We do not collect any location information from users." | collects location | **contradiction 0.977** |
| "We use cookies to remember your display preferences." | collects financial info | neutral 0.846 |
| "We collect your precise location to show nearby results." | collects location | neutral 0.637, entailment 0.354 |

The first justifies semantic alignment over keyword matching: that sentence
contains every keyword "we collect location" does.

**The third is a real weakness.** Zero-shot, the model does not strongly
entail a plain matching statement. That is what D-01 expected fine-tuning on
300 to 500 pairs to fix, and those pairs do not exist. The test for this case
asserts only that the model leans away from contradiction, because asserting
entailment would assert something the model does not do.

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

## 6. Real-model pipeline run — all three models real

`scripts/demo_real_models.py` runs F-08 → F-22 over a genuine published
privacy policy from OPP-115 with **F-11, F-12 and F-18 all loading trained
weights** and the 30 authored F-15 rules.

Result on `1017_sci-news.com.html`: 20 segments, 199 practices, 32
judgements, 14 verdicts, 6 evidence records, **every quote an exact slice of
the stored document**, and `uses_fixture_models` **False**.

Real alignment changed the verdicts, which is the evidence it does work
rather than pass through: Personal info became **Contradictory**, driven by
"Sci-News.com does not sell, trade or rent your personal information to third
parties", and App activity became **Undetermined** through abstention. Under
the stub both had been In-policy-not-declared.

One defect found by reading that output: the first real-model run still
printed `fixture models used: True`, because the script registered its
`model_version` rows with a test helper. Understating a real run is the same
class of error as overstating a stubbed one, so it now registers the
checkpoint that actually ran (C-84).

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
| Backend `pytest tests` | **697 passed, 78 skipped, 0 failed** |
| Skip reason | **all 78 are PostgreSQL** (`TEST_DATABASE_URL` unset). No ML test skipped here |
| `ruff check .` | clean |
| Frontend Vitest | **32 passed** |
| `npm run lint` / `vite build` | clean / succeeds |
| PostgreSQL integration | **78 passed, 0 skips at head**; downgrade guards fired (37 passed, 41 skipped); re-upgrade restored the schema |

Tests using **real models and real weights**: `test_f12_real_inference.py`
(7), `test_f18_real_inference.py` (7) and the demonstration script. Tests using **fixtures or mocks**:
everything else, including all 32 frontend tests.

**Environment caveat.** torch 2.5.1 and transformers 4.46.3 were installed in
the development environment during M11, so the `ml`-marked tests run here. On
a machine without them those tests **skip**, and a skip is not a pass.

**PostgreSQL was re-verified** on 2026-11-06 against
`privacy_auditor_m11_20261106_test`: full chain, 78 integration tests with
zero skips at head, downgrade guards firing, re-upgrade restoring the schema.
The three protected databases were untouched (C-83).

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

## 9. What remains to be run

PostgreSQL and the F-18 checkpoint are both done. The one outstanding task
needs a browser, not a command:

```
cd "/Users/anshu/Documents/Major Project"
.venv/bin/python scripts/manual_collect.py --template > myapp.json
# fill it in from a real Play Store listing, save that app's privacy policy
# page from the browser, then:
.venv/bin/python scripts/manual_collect.py --input myapp.json \
    --policy-file ~/Downloads/policy.html
.venv/bin/python scripts/import_corpus.py --dry-run
```

Three to five applications is enough for a pilot.

## 10. Conclusion

**Phase 4 is not yet ready for closure**, and it is now one step away.

Every component works with real weights. F-11, F-12 and F-18 all load trained
models, F-15's rules are authored and tested, the pipeline runs end to end on
real policy text producing verdicts and verbatim evidence, PostgreSQL is
verified, and the frontend is tested.

**One thing remains: no real Android application has been audited.**
`data/corpus/apps/` is empty, so the system has never compared two real
disclosures — the thing the project exists to do. Every result so far comes
from OPP-115 research text with the declaration side absent.

This is not a code defect and no test can close it. It needs three to five
applications collected through `scripts/manual_collect.py`, which refuses to
invent any part of them. Closing Phase 4 before that would be closing it on
research text and fixtures.

Phase 5 is the separate academic validation and testing phase and is not
started.
