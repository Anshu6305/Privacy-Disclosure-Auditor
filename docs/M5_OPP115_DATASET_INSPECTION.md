# OPP-115 Dataset Inspection

Date: 2026-11-05
Purpose: establish what the corpus actually contains before training, and
whether it can support the segment-level multi-label task FR-11 requires.

Everything below was measured against the copy at `data/raw/opp115`. Nothing
is taken from memory or from published descriptions of the corpus.

---

## 1. Licence and permitted use

From the corpus's own `readme.txt`:

> (C) Copyright 2016, all rights reserved. This dataset was developed by
> Carnegie Mellon University under the Usable Privacy Policy Project. … The
> annotations are made available for research, teaching, and scholarship
> purposes only, with further parameters in the spirit of a Creative Commons
> Attribution-NonCommercial License.

Citation is a condition of use:

> Wilson, S., Schaub, F., Dara, A. A., Liu, F., Cherivirala, S., Leon, P. G.,
> Andersen, M. S., Zimmeck, S., Sathyendra, K. M., Russell, N. C., Norton,
> T. B., Hovy, E., Reidenberg, J., and Sadeh, N. The creation and analysis of
> a website privacy policy corpus. *Proceedings of the 54th Annual Meeting of
> the ACL*, Berlin, Germany, August 2016.

**Compliance in this project:** academic use only; no commercial use; the raw
corpus is excluded from Git by `.gitignore`; the files are never modified; the
citation is in `docs/REFERENCES.md`; the repository carries only a checksum
manifest (`ml/data/opp115_manifest.json`), not the data.

## 2. Structure as found on disk

| Directory | Contents |
|---|---|
| `annotations/` | 115 CSV files, one per policy, all three annotators in the same file |
| `sanitized_policies/` | 115 HTML files, segments separated by `\|\|\|` |
| `consolidation/` | the same annotations with redundancy removed, at three thresholds |
| `documentation/` | corpus manual, category scheme, errant span index |
| `original_policies/` | 228 entries — raw web pages as downloaded |
| `pretty_print/`, `pretty_print_uniquified/` | human-readable renderings |

## 3. Annotation CSV format

Nine columns. Verified against the files, not the manual:

| # | Column | Used by this project |
|---|---|---|
| 0 | annotation ID | no |
| 1 | batch ID | no |
| 2 | **annotator ID** | **yes** — the majority vote |
| 3 | policy ID (internal UID) | **no — see below** |
| 4 | **segment ID** (0-indexed) | **yes** — joins to the policy text |
| 5 | **category name** | **yes** — the label |
| 6 | attribute-value JSON | not in M5; F-12 will use the spans |
| 7 | date | no |
| 8 | policy URL | no |

### Two discrepancies found

**The manual documents columns 8 and 9 in the wrong order.** It states column
8 is the policy URL and 9 the date. In all 23,194 released rows they are the
other way round. Measured, not assumed. Recorded in
`ml/data/opp115_schema.py`; no column this project depends on is affected.

**The filename prefix is not the CSV's policy ID.** `135_instagram.com.csv`
carries policy ID `3850` in column D. The filename stem is the identifier used
across the other directories, so **it** is what this project groups by.
Grouping by column D instead would still group correctly, but mixing the two
anywhere would scatter a policy across splits and leak its language into the
test set. The dataset builder uses the stem exclusively, and a test asserts it.

## 4. The question that decides whether FR-11 is supportable

FR-11 needs multi-label examples at segment level, with absence of a category
meaning "this segment does not discuss it". That reading is only defensible if
**every segment was actually read by annotators**. A segment that was never
shown to anyone would have no annotations for an entirely different reason,
and treating its absence as a negative would teach the classifier from silence.

Measured directly:

| Check | Result |
|---|---|
| Policies with text | 115 |
| Policies where annotations cover **every** segment | **115** |
| Policies with any uncovered segment | **0** |
| Total uncovered segments | **0** |
| Segment IDs outside the range of their policy's text | **0** |
| Policies with exactly 3 distinct annotators | **115** |

**Every segment of every policy was read by all three annotators.** Absence of
a category is therefore informative, and the segment-level multi-label
construction FR-11 requires is supported by the data.

Had any segment been uncovered, the correct response would have been to stop
and report the limitation, as the milestone instruction requires. That did not
arise.

## 5. Units

| Quantity | Count |
|---|---|
| Policies | 115 |
| Segments (non-empty, across all policies) | **3,792** |
| Annotation rows | 23,194 |

The 23,194 figure is **annotation records**, not examples: three annotators
each recording zero or more practices per segment. The training unit is the
segment, so the dataset has 3,792 examples, not 23,194. Conflating the two
would overstate the corpus by a factor of six.

## 6. Label construction

Each `(policy, segment)` is labelled with the categories at least *k* of the
three annotators marked. All three rules were measured:

| Rule | Segments with no label | Mean labels per segment |
|---|---|---|
| any annotator (k=1) | 0 (0.0%) | 1.70 |
| **majority (k=2)** | **63 (1.7%)** | **1.18** |
| unanimous (k=3) | 909 (24.0%) | 0.80 |

**Majority was chosen.** It discards single-annotator readings the other two
did not see, while keeping 98.3% of segments labelled. Unanimous would discard
a quarter of the corpus; any-annotator would train on every disagreement.

### Class support under the majority rule

| Category | Positive segments | Share |
|---|---|---|
| First Party Collection/Use | 1,209 | 31.9% |
| Other | 1,058 | 27.9% |
| Third Party Sharing/Collection | 945 | 24.9% |
| User Choice/Control | 358 | 9.4% |
| International and Specific Audiences | 301 | 7.9% |
| Data Security | 210 | 5.5% |
| User Access, Edit and Deletion | 149 | 3.9% |
| Policy Change | 119 | 3.1% |
| **Data Retention** | **78** | **2.1%** |
| **Do Not Track** | **31** | **0.8%** |

Labels per segment: 63 have none, 3,063 have one, 612 have two, 46 have three,
7 have four, 1 has five. The task is genuinely multi-label, but most segments
carry a single label.

**Do Not Track has 31 positive segments in the entire corpus.** That is the
single most consequential fact for the baseline experiment and is treated at
length in `docs/M5_BASELINE_CLASSIFIER_REPORT.md`.

## 7. How annotations relate to the source text

An annotation names a `(policy, segment)` pair. The policy text file splits on
`|||` into exactly the segments those IDs index, and the join was verified:
3,792 segments in the texts, 3,792 reachable from annotations, no index out of
range.

Column 6 carries attribute–value JSON with character offsets into the segment,
which is what F-12 span extraction will need in Milestone 6. M5 uses only the
category, so span quality does not affect this milestone. The relevant
measurement from Milestone 1 stands: of 146,926 attribute entries, 77,906
(53.0%) carry usable spans; most of the remainder are span-free by design
rather than damaged, and genuine errata number 262 (0.18%).

## 8. Relationship to the F-09 segments

**The corpus's segments are not the segments this system produces.** OPP-115
was segmented by its own authors for annotation; F-09 segments by paragraph
and sentence from cleaned HTML. The units differ in size and boundaries.

This is a genuine train–inference mismatch, not a detail: the classifier is
trained on one notion of a segment and applied to another. It is recorded as a
limitation in the M5 report, and it is a reason not to read the held-out score
as a prediction of real-world performance.

The milestone instruction asked how annotation records are associated with
F-09 segments. The honest answer is that they are **not**: the annotations
index OPP-115's segments and nothing in the corpus maps them onto ours. M5
trains on the units the labels describe, which is the only defensible choice;
any mapping would have to be invented.

## 9. What this supports, and what it does not

**Supports:** segment-level multi-label classification over the ten OPP-115
categories, with justified negatives, grouped by source policy.

**Does not support:** reliable evaluation of Do Not Track or Data Retention;
any claim about Android application policies, since OPP-115 is a corpus of
**website** policies from 2016; any claim that performance transfers to F-09
segments.
