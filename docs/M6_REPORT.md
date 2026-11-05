# Milestone 6 — Improved ML/NLP

Date: 2026-11-06 · Commit: see below
Scope: F-11 improved classifier, F-12 span extraction, F-18 semantic alignment
(decision D-01, Option A).

## 1. Status in one table

| Part | Implemented | Tested | Trained | Evaluated |
|---|---|---|---|---|
| F-12 span **dataset** from OPP-115 | yes | **yes, on the real corpus** | n/a | n/a |
| F-12 BIO encoding, offsets, decoder | yes | yes | n/a | n/a |
| F-12 tagger | interface + backend | logic only | **no** | **no** |
| F-11 improved classifier | yes | logic only | **no** | **no** |
| F-18 zero-shot alignment | yes | logic only | n/a (zero-shot) | **no** |
| F-18 fine-tuning | **not started** | — | — | — |

**No model has been trained and no model metric exists.** Nothing in this
milestone may be compared against the M5 baseline yet. The baseline remains
the only evaluated classifier in the project.

## 2. Why nothing is trained

The session that wrote this code can reach PyPI but **not** the Hugging Face
hub (`huggingface.co` returns 403 through the network proxy), so no pretrained
encoder can be downloaded here. `torch` itself installs; checkpoints do not.

This is the arrangement the approved plan already anticipated —
`backend/requirements-ml.txt` says GPU training happens in Colab or Kaggle. The
training scripts run wherever the hub is reachable: the team Mac, Colab, or
Kaggle.

```
pip install -r backend/requirements-ml.txt
python ml/train_improved_classifier.py          # F-11 improved
python ml/train_span_extractor.py --dry-run     # F-12 dataset + split report
```

Both accept `--dry-run`, which reports the split and configuration and trains
nothing. Both dry runs have been executed and their output is real.

## 3. F-12 — the span dataset is the solid part

Extracted from the released OPP-115 annotations and **verified by slicing**:

```
annotation rows read         23194
policies                       115
span-bearing attributes      32260
spans kept                   23150
    data_type                11913
    purpose                  11237
segments with >=1 span        2466

not supervision, by design:
    span-free values          8816
rejected:
    missing offsets             67
    slice mismatch             227
    total rejected             294   (0.9% of span-bearing attributes)
```

Only two OPP-115 attributes carry F-12's supervision: `Personal Information
Type` → data type, and `Purpose` → purpose. Named explicitly so an attribute
added to the corpus cannot silently become training data.

A span is kept only when `segment_text[start:end]` equals the annotator's
highlighted text after whitespace normalisation. **A span that does not slice
back is dropped and counted, never adjusted** — a corrected offset would be a
guess at which words the annotator meant.

**Offsets.** OPP-115 indexes one segment; M4 fixed the canonical base as the
cleaned policy document. `to_document_offsets` translates, and the translation
is tested by slicing on both sides. Every `ExtractedSpan` carries document
coordinates and a `verify_against` that re-slices before the span may be
quoted as evidence.

### What is trained, rule-based or provisional

| Part | Status |
|---|---|
| BIO scheme, token alignment, overlap resolution | rule-based, deterministic, tested |
| Offset translation to M4 coordinates | rule-based, slice-verified |
| Span decoding from a tag sequence | rule-based, deterministic, tested |
| The tagger producing the tags | **to be trained** |
| Span confidence threshold 0.50 | **provisional**, never tuned |

## 4. F-11 improved — comparable by construction

Same contract as the M5 baseline: same `predict_practices` signature, same
`PolicyPractice` output, and `abstained=False` on every practice because
**F-14 owns that decision**. Setting abstention in the model as well would put
one rule in two places, which the M5 authorisation forbade.

The training script loads the **identical** policy-grouped split, seed
20261105, and reports through the identical evaluation module — so a future
comparison is between two models, not two experiments. The dry run confirms
it reproduces M5's split, including the warning that Data Retention and Do Not
Track have fewer than 10 positive test examples.

Configuration recorded for reproducibility: `distilbert-base-uncased`, max
length 256, batch 16, lr 3e-5, 3 epochs, seed 20261105, threshold 0.50
(provisional). Chosen for the 8 GB constraint and CPU inference; they are
starting values, not tuned results.

**The test split is used once, at the end.** The validation split exists for
selection.

## 5. F-18 — zero-shot, as approved

Option A's zero-shot path, implemented and tested:

* **premise** — the policy sentence, verbatim from F-09;
* **hypothesis** — a declarative sentence stating the Data Safety claim;
* entailment → `SUPPORTS`, contradiction → `CONTRADICTS`, neutral → `NO_MATCH`.

A declaration that denies both collection and sharing is phrased as a denial
(`This app does not collect or share X.`) rather than positively, because
relying on `CONTRADICTS` to invert it would invert the judgement.

**Abstention is not a fourth label.** A judgement below threshold keeps its
label and sets `model_abstained`; `AlignmentJudgement.abstained` then ORs that
with the candidate's upstream uncertainty. Rewriting a low confidence as
`NO_MATCH` would turn "we are unsure" into "the policy is silent", which ALG-8
treats very differently. A candidate with no policy premise is returned as
`NO_MATCH` with confidence 0.0 **and** `model_abstained=True`: the model was
never consulted, so a confident `NO_MATCH` would be a claim nobody made.

The backend reads the model's own `id2label` and refuses a checkpoint that
does not expose all three NLI classes. Assuming the order would silently swap
entailment and contradiction — inverting every verdict while looking healthy.

## 6. What depends on manual annotation

| Needed | Size | Unit | Exists |
|---|---|---|---|
| F-18 fine-tuning pairs | **300–500** | policy statement / Data Safety claim pair | **no** |
| Gold set for evaluation | **~100** | application | **no** |

These are different units and must not be conflated. **Neither has been
created, and nothing here invents either.** Under D-01's safeguards the
zero-shot path stands as the approved baseline until enough reliable
annotations exist; if they never do, zero-shot is the documented outcome and
the limitation is reported rather than worked around.

Fine-tuning is **not started**. No pair file exists, no annotation guide has
been filled in with real pairs, and no fine-tuned checkpoint exists.

## 7. Files

| File | Purpose |
|---|---|
| `ml/data/opp115_spans.py` | F-12 span dataset, BIO encoding, offset translation |
| `analysis/models/span_extractor.py` | F-12 decoding and verification |
| `analysis/models/improved_classifier.py` | F-11 improved |
| `analysis/alignment/nli.py` | F-18 zero-shot aligner |
| `ml/backends.py` | the only module importing torch/transformers |
| `ml/training/classifier_trainer.py` | F-11 improved training loop |
| `ml/train_improved_classifier.py`, `ml/train_span_extractor.py` | entry points |
| `tests/unit/test_m6_components.py` (30), `tests/unit/test_opp115_spans.py` (6) | tests |

`data/processed/opp115_spans.jsonl` is generated and git-ignored.

## 8. Test results

| Check | Result |
|---|---|
| `pytest tests/unit/test_m6_components.py` | **30 passed** |
| `pytest tests/unit/test_opp115_spans.py` | **6 passed** (real corpus) |
| `pytest tests -p no:warnings` | **587 passed, 72 skipped** |
| `ruff check .` | All checks passed |
| `ml/train_span_extractor.py --dry-run` | 23,150 spans, 115 policies |
| `ml/train_improved_classifier.py --dry-run` | reproduces the M5 split |

The 72 skips are PostgreSQL-only tests, all of which passed on PostgreSQL 16
on 2026-11-06 (C-66).

**Every M6 test uses a deterministic stub backend.** They establish that the
decision logic, the offsets, the abstention behaviour and the label mapping
are correct. They say nothing about accuracy.

## 9. Limitations

1. **No model trained, no metric produced.** No improvement over M5 is claimed
   or claimable yet.
2. **F-12's tagger training loop is not written.** The dataset, encoding,
   offsets and decoder are complete and tested; the token-classification loop
   is the remaining piece.
3. **F-18 is zero-shot only**, and has never been run against a real NLI
   checkpoint — only against stubs.
4. **All thresholds remain provisional** at 0.50, uncalibrated.
5. **The M5 baseline is unchanged**: model, split, seed and held-out results
   exactly as committed at `7d0ee1a`.
