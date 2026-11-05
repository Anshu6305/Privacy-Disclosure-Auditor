# Milestone 5 — Baseline Multi-Label Practice Classifier

Date: 2026-11-05
Function: F-11 `classifyDataPractices` (baseline variant)
Algorithm: ALG-2 — TF-IDF + One-vs-Rest Logistic Regression
Requirements: FR-11, GI-02, GI-05. Task T3.1.

---

## 1. Headline result, stated plainly

| Split | Macro-F1 | Micro-F1 | Hamming loss |
|---|---|---|---|
| train | 0.9367 | 0.9237 | 0.0189 |
| validation | 0.7717 | 0.7734 | 0.0546 |
| **test (held out)** | **0.7489** | **0.7690** | **0.0545** |

**The test figures are the result.** The training figures are shown only to
expose the fit: a macro-F1 of 0.94 on training against 0.75 on held-out data
is a gap of 0.19, which is overfitting and is reported as such rather than
smoothed over.

Two of the ten categories cannot be measured reliably, and the aggregate above
conceals that. Section 8 gives the per-class breakdown, which is the number
that should be quoted.

## 2. Dataset

Full inspection in `docs/M5_OPP115_DATASET_INSPECTION.md`. The findings that
determine this experiment:

- 115 policies, **3,792 segments**, 23,194 annotation records. The training
  unit is the segment, so there are 3,792 examples — not 23,194.
- **Every segment of every policy was read by all three annotators**, verified
  with zero uncovered segments. This is what makes an absent category a
  defensible negative rather than an assumption.
- Labels by **majority vote, at least 2 of 3 annotators**, leaving 1.7% of
  segments unlabelled. Unanimous would have discarded 24%.
- **Do Not Track has 31 positive segments in the entire corpus** (0.8%);
  Data Retention has 78 (2.1%).

Generated data is written to `data/processed/opp115_segments.jsonl`, separate
from the untouched corpus and excluded from Git. Construction is deterministic
and fingerprinted: `b6a9b98addde18a7…`.

## 3. Label construction and categories

The ten OPP-115 categories, unchanged. A segment carries every category that
two or more annotators marked. Segments with no surviving label are **kept**,
because they are the evidence that a passage discusses no data practice — the
classifier needs them in order not to fire on boilerplate.

No label is invented, and no category is inferred from another.

## 4. Model and parameters

```
TfidfVectorizer(max_features=50000, ngram_range=(1,2), min_df=2,
                sublinear_tf=True, lowercase=True, stop_words=None)
OneVsRestClassifier(
    LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced",
                       solver="liblinear", random_state=20261105))
```

scikit-learn 1.6.0 only. No neural model, no transformer, no LLM — those are
Milestone 6.

**Hyperparameters are provisional.** Phase 3 specifies the algorithm, not its
settings. Nothing here has been tuned; these are defensible starting points
and the validation split exists so that tuning, when it happens, does not
touch the test set.

**`class_weight="balanced"` is doing real work.** Without it, a category with
31 positive examples in 3,792 is never predicted, because answering "no" is
right 99.2% of the time. It reweights by inverse class frequency — and it also
distorts the output scores, which is one reason those scores must not be
called calibrated probabilities.

## 5. Policy-grouped split

Segments from one policy never cross a split boundary. A policy reuses its own
phrasing throughout, so a random split by segment would place near-duplicates
of test segments into training and report memorisation as generalisation.

Seed **20261105**. Proportions apply to policies, not segments.

| Split | Policies | Segments |
|---|---|---|
| train | 80 | 2,634 |
| validation | 17 | 617 |
| test | 18 | 541 |

**Policy overlap between any two splits: 0**, asserted by the training script,
which refuses to train if it finds any.

### Per-class support

| Category | train | val | test | |
|---|---|---|---|---|
| First Party Collection/Use | 856 | 205 | 148 | |
| Third Party Sharing/Collection | 670 | 140 | 135 | |
| Other | 699 | 183 | 176 | |
| User Choice/Control | 241 | 55 | 62 | |
| International and Specific Audiences | 239 | 34 | 28 | |
| Data Security | 140 | 43 | 27 | |
| User Access, Edit and Deletion | 100 | 32 | 17 | |
| Policy Change | 81 | 23 | 15 | |
| **Data Retention** | 60 | 11 | **7** | **unreliable** |
| **Do Not Track** | 24 | 3 | **4** | **unreliable** |

A category with fewer than 10 positive test examples is flagged automatically.
**No example was moved between splits to improve these counts.** Doing so
would rig the evaluation; the shortage is reported instead.

## 6. Training procedure

```bash
python ml/train_baseline_classifier.py
```

Reads the corpus already at `data/raw/opp115` — nothing is downloaded. Builds
the dataset, splits by policy, asserts no leakage, trains on the training
split only, then evaluates all three splits separately and labels each result
with the split it came from.

**The test split was used once**, for the figures below. It was not used for
threshold selection or any tuning.

## 7. Held-out test results

541 segments from 18 policies, decision threshold 0.5.

| Category | Precision | Recall | F1 | Support | Predicted |
|---|---|---|---|---|---|
| International and Specific Audiences | 0.893 | 0.893 | **0.893** | 28 | 28 |
| Third Party Sharing/Collection | 0.821 | 0.815 | **0.818** | 135 | 134 |
| First Party Collection/Use | 0.720 | 0.905 | **0.802** | 148 | 186 |
| User Access, Edit and Deletion | 0.857 | 0.706 | **0.774** | 17 | 14 |
| Policy Change | 0.650 | 0.867 | **0.743** | 15 | 20 |
| Data Security | 0.657 | 0.852 | **0.742** | 27 | 35 |
| Other | 0.780 | 0.665 | **0.718** | 176 | 150 |
| User Choice/Control | 0.630 | 0.823 | **0.713** | 62 | 81 |
| *Do Not Track* | *1.000* | *0.750* | *0.857* | *4* | *3* |
| *Data Retention* | *0.429* | *0.429* | *0.429* | *7* | *7* |

| Aggregate | Value |
|---|---|
| Macro-F1 | **0.7489** |
| Micro-F1 | **0.7690** (precision 0.7462, recall 0.7932) |
| Hamming loss | **0.0545** |
| Subset accuracy | 0.5896 |
| Total positive labels | 619 |

The two italicised rows are **not measurements**. See section 8.

### Confusion pattern

Precision below recall on First Party Collection/Use (0.720 vs 0.905), Data
Security (0.657 vs 0.852), Policy Change (0.650 vs 0.867) and User
Choice/Control (0.630 vs 0.823): the model over-predicts these, which is the
expected effect of `class_weight="balanced"` pushing the decision boundary
toward the positive class. `Other` runs the opposite way (0.780 vs 0.665),
which is unsurprising for a catch-all category with no coherent vocabulary.

## 8. Rare categories — do not read these as results

**Do Not Track: F1 0.857 on 4 test examples.** This number should not be
quoted. The model predicted the category three times, all correct, and missed
one. Getting three of four right produces an impressive-looking F1 from a
sample too small to distinguish skill from luck: one different prediction
would move the F1 between roughly 0.57 and 1.00. The corpus contains 31
positive segments in total and 24 reached training.

**Data Retention: F1 0.429 on 7 test examples.** Genuinely poor, and also too
small to be stable.

Both are flagged automatically by the evaluation code, printed as `unreliable`
in the output, and recorded in the saved metrics with `"reliable": false`.

**What would be needed.** For a stable per-class estimate, on the order of
50–100 positive test examples per category — which for Do Not Track means
roughly 300–600 positive segments in the corpus, against the 31 that exist.
OPP-115 cannot provide that. The options are: accept that the system cannot
report on these categories; annotate additional policies specifically for
them; or merge them into a coarser category, which would change the approved
taxonomy and need faculty approval.

**The honest summary for the viva:** this baseline is usable for the four
categories with three-figure support and defensible for the four with
two-figure support. It is not evaluated for Do Not Track or Data Retention,
and the aggregate macro-F1 of 0.7489 is flattered by including two categories
whose scores are noise.

## 9. Confidence and abstention

F-11 returns a confidence for **every** category and performs no thresholding.
The decision is F-14's, which already exists and is reused unchanged —
`analysis/confidence/gate.py`. No second threshold mechanism was introduced.

`predict_practices()` returns `PolicyPractice` objects with `abstained=False`;
setting that flag is F-14's job. A test asserts F-11 never sets it.

Demonstrated on unseen text:

```
F-11 output (controlled example, unseen text)
  0.896  User Choice/Control
  0.476  Third Party Sharing/Collection
  0.414  User Access, Edit and Deletion
  ... 6 more categories

F-14 gating at threshold 0.50
  practices in: 9    practices out: 9   (none discarded)
  accepted   0.896  User Choice/Control
  ABSTAINED  0.476  Third Party Sharing/Collection
  ABSTAINED  0.414  User Access, Edit and Deletion
  ...
  abstention rate: 0.89
```

Nothing is discarded; low-confidence predictions are retained and flagged, so
uncertainty cannot become a confident absence.

### These are not calibrated probabilities

No calibration has been performed or tested, and `class_weight="balanced"`
deliberately distorts the scores. They are **rankable confidences**, which is
what F-14 needs. The module docstring and this report both say so, and no
calibration claim is made anywhere.

The example above is instructive: Third Party Sharing/Collection scores 0.476
on a sentence that plainly describes sharing with advertising partners. At the
provisional 0.50 threshold it abstains. The threshold has not been tuned —
that is validation-split work, not yet done — and it is **provisional**.

## 10. Artefact and reproducibility

```
ml/checkpoints/classifier-baseline-v1/model.joblib     (git-ignored)
ml/checkpoints/classifier-baseline-v1/metadata.json    (git-ignored)
ml/runs/classifier-baseline-v1-metrics.json            (git-ignored)
```

Metadata records: component `classifier`; variant `baseline`; the ALG-2
algorithm string; the category list; the full configuration; the dataset
fingerprint and description; the label rule; the split seed and per-split
policy and segment counts; the training timestamp; package versions; and the
metrics for all three splits.

**Loads offline.** Demonstrated: reload from disk reproduces identical
predictions, with no network access.

Model binaries and generated data are excluded from Git, verified with
`git check-ignore`. **No change was made to the PostgreSQL schema, and F-34
registry persistence was not implemented** — that is a later milestone.

## 11. Tests

```
$ pytest tests/ml/test_opp115_dataset.py       19 passed
$ pytest tests/ml/test_baseline_classifier.py  38 passed
$ pytest tests                                402 passed, 29 skipped
$ ruff check .                                All checks passed!
```

57 tests added, none skipped. The 29 skips are the PostgreSQL suite without
`TEST_DATABASE_URL`.

Unit tests use small controlled fixtures. **The real OPP-115 experiment is the
training script**, not a test, and its output is what section 7 reports. The
two are kept distinct deliberately: a test that trained on the full corpus
would be slow, and a report that quoted fixture results would be meaningless.

## 12. Traceability

| Identifier | Where |
|---|---|
| **FR-11** | `analysis/models/practice_classifier.py` |
| **F-11** | `BaselinePracticeClassifier.predict_practices` |
| **ALG-2** | TF-IDF + OvR logistic regression; O(\|v\|) per segment as specified |
| **GI-02** | the classifier identifies data practices in policy text |
| **GI-05** | this is the baseline half of the baseline-versus-improved comparison; M6 supplies the other half, evaluated on the same split |
| **F-14** | reused unchanged for thresholding; not reimplemented |
| **T3.1** | this milestone |

## 13. Limitations

1. **OPP-115 is a corpus of website privacy policies from 2016.** This project
   audits Android applications in 2026. Nothing here measures how the
   classifier performs on the real target, and the operational corpus still
   does not exist.
2. **Train–inference segmentation mismatch.** The model is trained on
   OPP-115's segments and will be applied to F-09's, which have different
   boundaries and sizes. The held-out score does not account for this.
3. **Overfitting.** Macro-F1 0.94 train versus 0.75 test. Regularisation and
   feature limits have not been tuned.
4. **Two categories unevaluable**, as set out in section 8.
5. **Scores are not calibrated**, and the 0.50 threshold is provisional and
   untuned.
6. **Validation split unused so far.** It exists for tuning and threshold
   selection, neither of which has been done.
7. **`Other` is a catch-all** with 1,058 positive segments and no coherent
   vocabulary; its F1 of 0.718 is hard to interpret.

## 14. Dependencies on other milestones

**Not blocked by M3B.** M5 reads files and writes files; no database, no API.

**Provides to M6:** the same dataset builder, the same policy-grouped split
and the same evaluation module, so the improved model is measured on identical
data. That comparability is what GI-05 asks for and is the reason the split
seed is recorded in the metadata.

**Provides to M8:** `predict_practices` returns `PolicyPractice` objects that
F-14 already accepts and F-15 already consumes, so the classifier drops into
the existing pipeline without an adapter.

**Still outstanding:** D-1 and the class D findings, M3B persistence, the
operational corpus, threshold tuning on the validation split, and F-34 model
registry persistence.
