# M10 — End-to-End Demonstration and Evaluation

**Date:** 2026-11-06 · **Status:** three of four parts complete. One
genuinely blocking dependency remains, and it is named precisely rather than
worked around.

Statuses are kept apart on purpose: **implemented**, **tested**,
**PostgreSQL-verified** and **demonstrated on real data** are four different
claims, and only the first three are made below.

## 1. F-15 — taxonomy mapping rules · implemented and tested

`analysis/mapping/taxonomy/mapping_v1.json`, version `opp115-to-ds-v1`.
**30 rules, 16 of them partial, covering 14 of the 17 data-type values that
actually occur in the corpus.** The 17 values were counted across all 115
annotated policies before any rule was written, rather than recalled.

**11 explicit refusals to map**, each with a reason in the file:

* **8 of the 10 OPP-115 categories.** User Choice/Control, User Access,
  Data Retention, Data Security, Policy Change, Do Not Track, International
  and Specific Audiences, and Other describe practices *about* data. A Data
  Safety category states what data is handled. Mapping Data Security to a
  data category would report "we encrypt your data" as a declaration that
  the data is collected.
* **3 data types.** `Unspecified` above all — the corpus's own "nothing to
  select" value and the commonest in the attribute. Mapping it would
  manufacture a declaration out of an annotator's abstention 4,299 times.
  `Other` and `Survey data` have no defensible counterpart either.

**The distinction the table is built around:** OPP-115 `Contact` is the
user's own contact details and maps to Data Safety **Personal info**. Data
Safety `Contacts` is the user's address book — other people's details.
Conflating them would make every policy mentioning an email address look like
a declaration about the user's contact list. That one line has its own test.

**Ambiguity is emitted, not resolved.** `User online activities` maps to both
App activity and Web browsing, both flagged partial, because the source value
does not distinguish them.

28 tests in `tests/unit/test_taxonomy_mapping_rules.py` cover valid mappings,
the Contact/Contacts trap, the ambiguous case, unmapped data types, unmapped
categories, an unknown value, and four loader validations.
`scripts/seed_taxonomy_mapping.py` writes the version into the database and
is idempotent and non-destructive: a version is never edited in place,
because audits cite the version they used.

## 2. M5 baseline · rebuilt, reproduced exactly

`python ml/train_baseline_classifier.py`, same corpus, same seed (20261105),
same policy-level split, same label rule (majority vote, ≥2 of 3 annotators).

| Test split | M5 recorded | M10 rebuild |
| --- | --- | --- |
| Macro-F1 | 0.7489 | **0.7489** |
| Micro-F1 | 0.7690 | **0.7690** |
| Precision / recall | 0.7462 / 0.7932 | **0.7462 / 0.7932** |

Figure for figure. **No improvement is claimed and none was attempted.** M5's
limitations stand unchanged: Data Retention (n=7) and Do Not Track (n=4) are
reported as not measurable, and the train/test gap (0.94 vs 0.75 macro-F1)
is unaddressed.

The rebuild also exposed C-74: the registry looked for the checkpoint in
`ml/checkpoints/baseline_classifier`, which the trainer has never written. It
would have reported the model unavailable on a machine that had just built
it. Fixed; **F-11 now loads through the registry**, confirmed by calling it.

## 3. F-12 — span extractor · implemented, dry-run verified, not trained

Written to the approved design: token classification producing data-type
**and** purpose spans with verifiable offsets.

**Labels carry the attribute value** — `B-data_type:Contact`, not
`B-data_type` — giving 55 labels. Without this, F-12's spans could never key
an F-15 rule. `ExtractedSpan.value` and the compound-tag decode are additive;
a plain tag still decodes, to a span with no value.

| Dataset | |
| --- | --- |
| Tagged segments | 2,466 |
| Tokens | 204,092, of which 41.3% inside a span |
| Labels | 55 (54 plus O) |
| Split | 80 / 17 / 18 policies — M5's split, M5's seed |
| Offsets | every token verified to slice out of its segment |
| Thin classes | 7 of 54 labels have fewer than 10 test spans and are reported as not measurable |

Evaluation is **span-level and exact**: a predicted span counts only when its
type, its value and both offsets match. Overlapping scores print beside the
exact ones so the boundary error rate is visible rather than hidden behind
whichever definition flatters more.

**Training has not happened.** `--dry-run` is verified, including against a
freshly extracted bundle with the repository off `PYTHONPATH`; the GPU run is
`notebooks/train_f12_colab.ipynb`, which unzips the bundle from
`python ml/export_f12_bundle.py` (1.7 MB, 9 files) and runs the repository's
own trainer, so Colab uses the same split, seed and evaluation code as a
local run rather than a copy that can drift. **No F-12 metric exists and none
is reported.**

The bundle's contents are derived from the import graph, not listed by hand.
The first version carried a hand-written list, omitted two modules and failed
on Colab at the first import (C-78); six tests now check the bundle as a
notebook sees it.

## 4. End-to-end integration

| Link | State |
| --- | --- |
| F-11 classifier → pipeline | **Loads** (rebuilt M5) |
| F-12 → F-15 data type | Wired; needs the checkpoint |
| F-15 rules → pipeline | **Authored, seeded, tested** |
| F-18 aligner | Needs torch + a downloadable checkpoint |
| Pipeline → persistence → E1–E11 → frontend | Working, verified in M8 and M9 |

The whole chain **F-11 → F-14 → F-12 → F-15 → F-18 → ALG-8 → evidence** runs
against the real authored rule table in
`test_the_authored_rules_fire_once_f12_supplies_a_data_type`, with stubs
standing in only for the models.

### The corpus: still empty

`data/corpus/apps/` **does not exist**. There are no collected applications,
no Data Safety declarations and no stored privacy policies. Every test in
this project uses OPP-115 (a research corpus of policy text, not Play Store
data) or controlled fixtures. **No real application has ever been audited,
and nothing in the interface has been seen against real collected data.**

### C-76: the guard that was not enough

Every authored rule is keyed on a data type, so with the table seeded and no
F-12 checkpoint, `rule_count` is 30 and the M8 guard would have let an audit
proceed — mapping nothing, and reporting every declared category as
**Declared-not-in-policy**. That is precisely the manufactured-findings
failure the guard was written to prevent, arriving through the one door it
did not cover. Verified by running the mapper, not by reading it.

The pipeline now also refuses when the mapper has no general rules and no
span extractor is loaded, naming both facts.

## 5. Tests

| Suite | Result |
| --- | --- |
| Backend `pytest tests` | **669 passed, 78 skipped** (was 625/78; 44 new) |
| `ruff check .` | clean |
| Frontend Vitest | **32 passed** |
| `npm run lint` / `vite build` | clean / succeeds |
| PostgreSQL integration | **not re-run since M9** — see below |

The 78 skips are the PostgreSQL and model-dependent suites; they are not
passes. No earlier milestone regressed.

**PostgreSQL re-verification is outstanding.** M10 changed no schema and no
migration, but it did change `audit_pipeline.py`, so the integration suite
should run again:

```
cd "/Users/anshu/Documents/Major Project"
bash scripts/verify_migrations.sh
```

Fresh database `privacy_auditor_m10_20261106_test`;
`privacy_auditor_m8_20261106b_test` added to the protected list.

## 6. What blocks a real audit, in order

1. **Train F-12** on Colab (`notebooks/train_f12_colab.ipynb`). Everything
   for it is written and dry-run verified. This is the only blocker that is
   purely mechanical.
2. **F-18 semantic alignment** needs torch, transformers and a downloadable
   zero-shot checkpoint. Its fine-tuning pairs and the gold set still do not
   exist and were not invented.
3. **Collect real applications.** `data/corpus/apps/` is empty. Until it
   holds genuine Play Store declarations and policies, the system can be
   demonstrated only on fixtures, however complete the pipeline becomes.

## 7. Next

**M11 — train F-12, then the first real audit.** Run the notebook, copy the
printed metrics into this report, drop the checkpoint into
`ml/checkpoints/span-extractor-v1/`, re-run the PostgreSQL verification, and
collect a first small set of real applications. Phase 4 is not complete, and
the three items above are why.
