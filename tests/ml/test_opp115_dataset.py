"""Dataset construction from OPP-115 annotations.

Unit tests use a small controlled corpus built in a temporary directory. The
real corpus is exercised by `ml/train_baseline_classifier.py`, whose results
are recorded in docs/M5_BASELINE_CLASSIFIER_REPORT.md.
"""

from __future__ import annotations

import csv

import pytest

from ml.data.opp115_dataset import (
    ANNOTATORS_PER_POLICY,
    DatasetError,
    build_dataset,
    dataset_fingerprint,
    read_dataset,
    write_dataset,
)

SEP = "|||"


def make_corpus(tmp_path, policies: dict[str, list[str]], annotations: list[tuple]):
    """policies: stem -> segment texts. annotations: (stem, seg, cat, annotator)."""
    (tmp_path / "sanitized_policies").mkdir(parents=True)
    (tmp_path / "annotations").mkdir(parents=True)

    for stem, segments in policies.items():
        (tmp_path / "sanitized_policies" / f"{stem}.html").write_text(
            SEP.join(segments), encoding="utf-8"
        )

    rows_by_file: dict[str, list] = {stem: [] for stem in policies}
    for index, (stem, segment, category, annotator) in enumerate(annotations):
        rows_by_file.setdefault(stem, []).append(
            [index, "batch", annotator, "9999", segment, category,
             '{"Attr": {"value": "x"}}', "1/1/16", "https://example.invalid/p"]
        )
    for stem, rows in rows_by_file.items():
        with (tmp_path / "annotations" / f"{stem}.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            csv.writer(handle).writerows(rows)
    return tmp_path


FP = "First Party Collection/Use"
TP = "Third Party Sharing/Collection"
DS = "Data Security"


# ---------------------------------------------------------------------------
# Discovery and parsing
# ---------------------------------------------------------------------------


def test_missing_corpus_says_where_to_put_it(tmp_path):
    with pytest.raises(DatasetError, match="data/README.md"):
        build_dataset(tmp_path / "absent")


def test_builds_one_example_per_segment(tmp_path):
    corpus = make_corpus(
        tmp_path,
        {"1_a.com": ["First segment.", "Second segment."]},
        [("1_a.com", 0, FP, "A"), ("1_a.com", 0, FP, "B")],
    )
    examples, report = build_dataset(corpus)

    assert report.policies == 1
    assert report.segments == 2
    assert [e.segment_index for e in examples] == [0, 1]
    assert examples[0].text == "First segment."


def test_malformed_rows_are_counted_not_fatal(tmp_path):
    corpus = make_corpus(tmp_path, {"1_a.com": ["Text."]}, [("1_a.com", 0, FP, "A")])
    with (corpus / "annotations" / "1_a.com.csv").open("a", encoding="utf-8") as handle:
        handle.write("too,few,columns\n")

    _, report = build_dataset(corpus)
    assert report.malformed_rows == 1


def test_unknown_categories_are_recorded_and_excluded(tmp_path):
    corpus = make_corpus(
        tmp_path, {"1_a.com": ["Text."]},
        [("1_a.com", 0, "Telepathy", "A"), ("1_a.com", 0, "Telepathy", "B")],
    )
    examples, report = build_dataset(corpus)

    assert report.unknown_categories["Telepathy"] == 2
    assert examples[0].labels == ()


def test_policy_id_is_the_filename_stem_not_the_csv_column(tmp_path):
    """Column D carries a different internal identifier; grouping by it would
    scatter a policy across splits and leak its language."""
    corpus = make_corpus(tmp_path, {"135_instagram.com": ["Text."]},
                         [("135_instagram.com", 0, FP, "A")])
    examples, _ = build_dataset(corpus)

    assert examples[0].policy_id == "135_instagram.com"
    assert examples[0].example_id == "135_instagram.com#0"


# ---------------------------------------------------------------------------
# Label construction
# ---------------------------------------------------------------------------


def test_majority_vote_requires_two_annotators(tmp_path):
    corpus = make_corpus(
        tmp_path, {"1_a.com": ["A.", "B."]},
        [("1_a.com", 0, FP, "A"),                        # one vote only
         ("1_a.com", 1, FP, "A"), ("1_a.com", 1, FP, "B")],  # two votes
    )
    examples, _ = build_dataset(corpus, min_votes=2)

    assert examples[0].labels == ()
    assert examples[1].labels == (FP,)
    assert examples[1].votes == {FP: 2}


def test_single_vote_rule_keeps_everything(tmp_path):
    corpus = make_corpus(tmp_path, {"1_a.com": ["A."]}, [("1_a.com", 0, FP, "A")])
    examples, _ = build_dataset(corpus, min_votes=1)
    assert examples[0].labels == (FP,)


def test_multiple_labels_on_one_segment_are_all_kept(tmp_path):
    """A sentence about sharing for advertising is genuinely two practices."""
    corpus = make_corpus(
        tmp_path, {"1_a.com": ["We share data and secure it."]},
        [("1_a.com", 0, TP, "A"), ("1_a.com", 0, TP, "B"),
         ("1_a.com", 0, DS, "A"), ("1_a.com", 0, DS, "C")],
    )
    examples, _ = build_dataset(corpus)

    assert set(examples[0].labels) == {TP, DS}


def test_labels_follow_the_canonical_category_order(tmp_path):
    """Deterministic output, not dictionary order."""
    corpus = make_corpus(
        tmp_path, {"1_a.com": ["Text."]},
        [("1_a.com", 0, DS, "A"), ("1_a.com", 0, DS, "B"),
         ("1_a.com", 0, FP, "A"), ("1_a.com", 0, FP, "B")],
    )
    examples, _ = build_dataset(corpus)
    assert examples[0].labels == (FP, DS)


def test_unlabelled_segments_are_kept_as_negative_evidence(tmp_path):
    """Dropping them removes the evidence that a segment discusses nothing,
    which the classifier needs in order not to fire on boilerplate."""
    corpus = make_corpus(tmp_path, {"1_a.com": ["Boilerplate.", "We collect."]},
                         [("1_a.com", 1, FP, "A"), ("1_a.com", 1, FP, "B")])
    examples, report = build_dataset(corpus)

    assert len(examples) == 2
    assert examples[0].labels == ()
    assert report.segments_without_labels == 1


def test_no_labels_are_invented(tmp_path):
    corpus = make_corpus(tmp_path, {"1_a.com": ["Text."]}, [])
    examples, _ = build_dataset(corpus)
    assert examples[0].labels == ()


def test_empty_segments_are_skipped(tmp_path):
    corpus = make_corpus(tmp_path, {"1_a.com": ["Real text.", "   ", "More."]},
                         [("1_a.com", 0, FP, "A"), ("1_a.com", 0, FP, "B")])
    examples, _ = build_dataset(corpus)

    assert len(examples) == 2
    assert [e.segment_index for e in examples] == [0, 2]


def test_no_duplicate_examples(tmp_path):
    corpus = make_corpus(tmp_path, {"1_a.com": ["A.", "B."], "2_b.com": ["C."]}, [])
    examples, _ = build_dataset(corpus)

    ids = [e.example_id for e in examples]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("votes", [0, 4])
def test_invalid_vote_threshold_is_rejected(tmp_path, votes):
    corpus = make_corpus(tmp_path, {"1_a.com": ["Text."]}, [])
    with pytest.raises(DatasetError, match="min_votes must be between"):
        build_dataset(corpus, min_votes=votes)


def test_annotators_per_policy_constant_matches_the_corpus():
    assert ANNOTATORS_PER_POLICY == 3


# ---------------------------------------------------------------------------
# Reproducibility and round-trip
# ---------------------------------------------------------------------------


def test_construction_is_deterministic(tmp_path):
    corpus = make_corpus(
        tmp_path, {"2_b.com": ["B."], "1_a.com": ["A."]},
        [("1_a.com", 0, FP, "A"), ("1_a.com", 0, FP, "B")],
    )
    first, _ = build_dataset(corpus)
    second, _ = build_dataset(corpus)

    assert [e.example_id for e in first] == [e.example_id for e in second]
    assert dataset_fingerprint(first) == dataset_fingerprint(second)


def test_fingerprint_changes_when_labels_change(tmp_path):
    corpus = make_corpus(
        tmp_path, {"1_a.com": ["A."]},
        [("1_a.com", 0, FP, "A"), ("1_a.com", 0, FP, "B")],
    )
    strict, _ = build_dataset(corpus, min_votes=3)
    loose, _ = build_dataset(corpus, min_votes=2)

    assert dataset_fingerprint(strict) != dataset_fingerprint(loose)


def test_dataset_round_trips_through_jsonl(tmp_path):
    corpus = make_corpus(
        tmp_path, {"1_a.com": ["Some text."]},
        [("1_a.com", 0, FP, "A"), ("1_a.com", 0, FP, "B")],
    )
    examples, _ = build_dataset(corpus)
    path = write_dataset(examples, tmp_path / "out" / "data.jsonl")

    assert read_dataset(path) == examples
