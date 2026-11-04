"""OPP-115 corpus structure as it actually exists on disk.

The constants here were established by reading the corpus manual
(`documentation/manual.txt`) and then checking the real files against it. Where
the two disagree, the files win and the disagreement is recorded.
"""

from __future__ import annotations

# The ten annotation categories, with the exact spelling used in the CSV files.
# Any category string outside this set means the corpus on disk differs from
# the release this code was written against, and loading stops.
CATEGORIES: tuple[str, ...] = (
    "First Party Collection/Use",
    "Third Party Sharing/Collection",
    "User Choice/Control",
    "User Access, Edit and Deletion",
    "Data Retention",
    "Data Security",
    "Policy Change",
    "Do Not Track",
    "International and Specific Audiences",
    "Other",
)

#: Expected number of annotated policies in the v1.0 release.
EXPECTED_DOCUMENT_COUNT = 115

#: Expected number of annotators per policy.
EXPECTED_ANNOTATORS_PER_POLICY = 3

#: Segment separator inside files under ``sanitized_policies/``.
SEGMENT_SEPARATOR = "|||"

# ---------------------------------------------------------------------------
# Column layout of the annotation CSV files.
#
# DISCREPANCY WITH THE CORPUS MANUAL — verified 2026-11-04.
#
# The manual documents the last two columns as:
#     8 (H) policy URL
#     9 (I) date
#
# The released files have them the other way round. For example, the first row
# of annotations/135_instagram.com.csv ends:
#     ...,"{json}",1/19/13,https://instagram.com/about/legal/privacy/
#
# so column index 7 holds the date and column index 8 holds the URL. The loader
# therefore does not trust position for these two fields: it identifies the URL
# by its scheme prefix and treats the other as the date. The four fields the
# project actually depends on (annotator, policy, segment, category, and the
# attribute JSON) are unambiguous and are read positionally.
# ---------------------------------------------------------------------------
COL_ANNOTATION_ID = 0
COL_BATCH_ID = 1
COL_ANNOTATOR_ID = 2
COL_POLICY_ID = 3
COL_SEGMENT_ID = 4
COL_CATEGORY = 5
COL_ATTRIBUTES_JSON = 6
COL_TRAILING_A = 7  # date in the released files, documented as URL
COL_TRAILING_B = 8  # URL in the released files, documented as date

EXPECTED_COLUMN_COUNT = 9

#: Value the annotation tool writes when an attribute was left unselected.
NOT_SELECTED = "not-selected"

# ---------------------------------------------------------------------------
# Attribute values that carry no text span by design.
#
# Measured on the released corpus: of 146,926 attribute entries, 69,020 have no
# usable span, and all but roughly 150 of those carry one of the three values
# below. They are not corpus errors. "Unspecified" and "not-selected" record
# that the annotator found nothing to select, and "Does" is used for the
# affirmative side of a does / does-not attribute without a highlighted span.
#
# Separating these from genuine errata matters: counting them as damage would
# understate the span supervision available for F-12 by almost half.
# ---------------------------------------------------------------------------
SPAN_FREE_VALUES: frozenset[str] = frozenset({"Unspecified", "not-selected", "Does"})

# Per the corpus errata, a genuinely missing span appears either as an absent
# "selectedText" key or as start and end indices that are both -1 or both 0,
# on an attribute value that should have carried text. These are counted and
# excluded, never repaired by guesswork.
