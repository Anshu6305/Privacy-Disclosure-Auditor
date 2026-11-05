"""The F-11 baseline classifier, its split, and multi-label evaluation.

Controlled fixtures throughout. The real OPP-115 experiment is run by
`ml/train_baseline_classifier.py`; its results are in
docs/M5_BASELINE_CLASSIFIER_REPORT.md and are not reproduced by these tests.
"""

from __future__ import annotations

import pytest

from analysis.confidence.gate import apply_threshold_to_all
from analysis.models.practice_classifier import (
    BaselineConfig,
    BaselinePracticeClassifier,
)
from analysis.verdict.models import PolicySegmentRef
from ml.data.opp115_dataset import LabelledSegment
from ml.data.splits import MINIMUM_RELIABLE_TEST_SUPPORT, split_by_policy
from ml.evaluation import evaluate, metrics_to_dict

FP = "First Party Collection/Use"
TP = "Third Party Sharing/Collection"
DS = "Data Security"
CATEGORIES = [FP, TP, DS]


def tiny_training_set() -> tuple[list[str], list[tuple[str, ...]]]:
    """Deliberately separable, so a failure means the wiring is broken."""
    texts, labels = [], []
    for _ in range(12):
        texts.append("we collect your email address and your name on signup")
        labels.append((FP,))
        texts.append("we share your data with advertising partners and vendors")
        labels.append((TP,))
        texts.append("we encrypt your data in transit using industry standards")
        labels.append((DS,))
        texts.append("we collect your email and share it with partners")
        labels.append((FP, TP))
    return texts, labels


@pytest.fixture(scope="module")
def trained() -> BaselinePracticeClassifier:
    texts, labels = tiny_training_set()
    model = BaselinePracticeClassifier(
        config=BaselineConfig(min_df=1, max_features=500), categories=CATEGORIES
    )
    model.fit(texts, labels)
    return model


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def test_trains_on_a_small_controlled_dataset(trained):
    assert trained.is_fitted
    assert trained.metadata.trained_at is not None
    assert trained.metadata.package_versions["scikit-learn"]


def test_untrained_model_refuses_to_predict():
    model = BaselinePracticeClassifier(categories=CATEGORIES)
    with pytest.raises(RuntimeError, match="has not been trained"):
        model.predict_scores(["some text"])


def test_empty_training_data_is_rejected():
    with pytest.raises(ValueError, match="empty dataset"):
        BaselinePracticeClassifier(categories=CATEGORIES).fit([], [])


def test_mismatched_texts_and_labels_are_rejected():
    with pytest.raises(ValueError, match="label sets"):
        BaselinePracticeClassifier(categories=CATEGORIES).fit(["a", "b"], [(FP,)])


def test_labels_outside_the_category_set_are_rejected():
    """A label the model has no column for would be silently dropped."""
    with pytest.raises(ValueError, match="outside the category set"):
        BaselinePracticeClassifier(categories=CATEGORIES).fit(
            ["text"] * 2, [("Telepathy",), (FP,)]
        )


def test_a_category_with_no_positive_example_is_recorded(trained):
    texts, labels = tiny_training_set()
    model = BaselinePracticeClassifier(
        config=BaselineConfig(min_df=1), categories=[*CATEGORIES, "Do Not Track"]
    )
    model.fit(texts, labels)

    assert "Do Not Track" in model.metadata.notes
    assert "never learned" in model.metadata.notes


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


def test_predicts_multiple_labels_for_one_segment(trained):
    scores = trained.predict_scores(["we collect your email and share it with partners"])

    assert scores[0][FP] > 0.5
    assert scores[0][TP] > 0.5


def test_every_category_gets_a_confidence(trained):
    scores = trained.predict_scores(["unrelated sentence about weather"])

    assert set(scores[0]) == set(CATEGORIES)
    assert all(0.0 <= v <= 1.0 for v in scores[0].values())


def test_empty_input_returns_nothing(trained):
    assert trained.predict_scores([]) == []


def test_unseen_vocabulary_does_not_crash(trained):
    """Real policies contain words no training document had."""
    scores = trained.predict_scores(["zzzz qqqq xyzzy plugh"])
    assert set(scores[0]) == set(CATEGORIES)


def test_inference_is_deterministic(trained):
    text = "we share your data with advertising partners"
    assert trained.predict_scores([text]) == trained.predict_scores([text])


# ---------------------------------------------------------------------------
# F-14 compatibility
# ---------------------------------------------------------------------------


def test_predictions_are_policy_practices_ready_for_f14(trained):
    text = "we collect your email address on signup"
    segment = PolicySegmentRef(1, text, 0, len(text))
    practices = trained.predict_practices(segment)

    assert len(practices) == len(CATEGORIES)
    assert all(p.segment is segment for p in practices)
    assert all(p.abstained is False for p in practices), (
        "F-11 must not set the abstention flag; that decision is F-14's"
    )


def test_f14_flags_rather_than_discards(trained):
    """The existing gate is reused, not reimplemented."""
    text = "we collect your email address on signup"
    segment = PolicySegmentRef(1, text, 0, len(text))
    practices = trained.predict_practices(segment)

    gated = apply_threshold_to_all(practices, 0.5)

    assert len(gated) == len(practices), "nothing may be discarded"
    assert any(p.abstained for p in gated), "low-confidence ones must be flagged"


def test_candidate_floor_is_not_a_decision_threshold(trained):
    text = "we collect your email address on signup"
    segment = PolicySegmentRef(1, text, 0, len(text))

    everything = trained.predict_practices(segment, minimum_score=0.0)
    trimmed = trained.predict_practices(segment, minimum_score=0.99)

    assert len(everything) == len(CATEGORIES)
    assert len(trimmed) < len(everything)


def test_practice_ids_are_unique_within_a_segment(trained):
    text = "we collect data"
    segment = PolicySegmentRef(1, text, 0, len(text))
    practices = trained.predict_practices(segment)

    assert len({p.practice_id for p in practices}) == len(practices)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_model_saves_and_reloads_with_identical_predictions(trained, tmp_path):
    text = "we share your data with advertising partners"
    before = trained.predict_scores([text])

    trained.save(tmp_path / "model")
    reloaded = BaselinePracticeClassifier.load(tmp_path / "model")

    assert reloaded.predict_scores([text]) == before
    assert reloaded.categories == trained.categories
    assert reloaded.config == trained.config


def test_metadata_records_provenance(trained, tmp_path):
    trained.metadata.dataset_fingerprint = "abc123"
    trained.metadata.label_rule = "majority, 2 of 3"
    trained.save(tmp_path / "model")

    reloaded = BaselinePracticeClassifier.load(tmp_path / "model")
    assert reloaded.metadata.component == "classifier"
    assert reloaded.metadata.variant == "baseline"
    assert reloaded.metadata.dataset_fingerprint == "abc123"
    assert reloaded.metadata.label_rule == "majority, 2 of 3"
    assert "ALG-2" in reloaded.metadata.algorithm


def test_loading_a_missing_model_says_how_to_make_one(tmp_path):
    with pytest.raises(FileNotFoundError, match="train_baseline_classifier"):
        BaselinePracticeClassifier.load(tmp_path / "absent")


# ---------------------------------------------------------------------------
# Policy-grouped split
# ---------------------------------------------------------------------------


def fake_examples(policies: int, per_policy: int = 10) -> list[LabelledSegment]:
    return [
        LabelledSegment(f"policy_{p:03d}", i, f"text {p} {i}", (FP,) if i % 2 else ())
        for p in range(policies)
        for i in range(per_policy)
    ]


def test_no_policy_appears_in_two_splits():
    """The methodological requirement. A policy reuses its own phrasing, so a
    random split by segment would measure memorisation."""
    split = split_by_policy(fake_examples(30))

    train = split.policies_in("train")
    validation = split.policies_in("validation")
    test = split.policies_in("test")

    assert not train & validation
    assert not train & test
    assert not validation & test
    assert len(train | validation | test) == 30


def test_split_is_reproducible_from_the_seed():
    first = split_by_policy(fake_examples(30), seed=42)
    second = split_by_policy(fake_examples(30), seed=42)

    assert first.policies_in("test") == second.policies_in("test")


def test_a_different_seed_gives_a_different_split():
    a = split_by_policy(fake_examples(30), seed=1)
    b = split_by_policy(fake_examples(30), seed=2)
    assert a.policies_in("test") != b.policies_in("test")


def test_split_does_not_depend_on_input_order():
    examples = fake_examples(30)
    forward = split_by_policy(examples, seed=7)
    backward = split_by_policy(list(reversed(examples)), seed=7)

    assert forward.policies_in("test") == backward.policies_in("test")


def test_every_policy_is_assigned_somewhere():
    split = split_by_policy(fake_examples(17))
    total = sum(split.report.policies.values())
    assert total == 17


def test_split_reports_per_class_support():
    split = split_by_policy(fake_examples(30))
    assert split.report.support["test"][FP] > 0
    assert set(split.report.segments) == {"train", "validation", "test"}


def test_rare_category_is_flagged_rather_than_moved():
    """Moving examples between splits to prop up a rare class would be
    silently rigging the evaluation."""
    examples = fake_examples(20)
    examples.append(LabelledSegment("policy_000", 99, "rare text", (DS,)))

    split = split_by_policy(examples, seed=3)
    rare = split.report.support["test"].get(DS, 0)

    assert rare < MINIMUM_RELIABLE_TEST_SUPPORT
    assert DS in split.report.unreliable_categories + split.report.absent_from_test


def test_proportions_must_sum_to_one():
    with pytest.raises(ValueError, match="sum to 1.0"):
        split_by_policy(fake_examples(10), (0.5, 0.2, 0.2))


def test_too_few_policies_to_split():
    with pytest.raises(ValueError, match="at least 3 policies"):
        split_by_policy(fake_examples(2))


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def test_per_class_metrics_are_computed_correctly():
    gold = [(FP,), (FP,), (TP,), ()]
    scores = [
        {FP: 0.9, TP: 0.1, DS: 0.0},   # correct
        {FP: 0.2, TP: 0.1, DS: 0.0},   # missed  -> FN for FP
        {FP: 0.8, TP: 0.9, DS: 0.0},   # TP right, FP wrong -> FP for FP
        {FP: 0.1, TP: 0.1, DS: 0.0},   # correct empty
    ]
    report = evaluate(gold, scores, CATEGORIES, "test")
    fp_metrics = next(m for m in report.per_class if m.category == FP)

    assert fp_metrics.true_positives == 1
    assert fp_metrics.false_positives == 1
    assert fp_metrics.false_negatives == 1
    assert fp_metrics.support == 2
    assert fp_metrics.precision == pytest.approx(0.5)
    assert fp_metrics.recall == pytest.approx(0.5)
    assert fp_metrics.f1 == pytest.approx(0.5)


def test_macro_f1_is_the_unweighted_mean():
    gold = [(FP,), (TP,)]
    scores = [{FP: 0.9, TP: 0.1, DS: 0.0}, {FP: 0.1, TP: 0.9, DS: 0.0}]
    report = evaluate(gold, scores, CATEGORIES, "test")

    f1s = [m.f1 for m in report.per_class]
    assert report.macro_f1 == pytest.approx(sum(f1s) / len(f1s))


def test_micro_f1_pools_across_categories():
    gold = [(FP, TP), (DS,)]
    scores = [{FP: 0.9, TP: 0.9, DS: 0.0}, {FP: 0.0, TP: 0.0, DS: 0.9}]
    report = evaluate(gold, scores, CATEGORIES, "test")

    assert report.micro_f1 == pytest.approx(1.0)
    assert report.macro_f1 == pytest.approx(1.0)


def test_hamming_loss_counts_wrong_cells():
    gold = [(FP,)]
    scores = [{FP: 0.1, TP: 0.9, DS: 0.0}]   # one FN and one FP of three cells
    report = evaluate(gold, scores, CATEGORIES, "test")

    assert report.hamming_loss == pytest.approx(2 / 3)


def test_support_counts_match_the_gold_labels():
    gold = [(FP,), (FP, TP), (DS,)]
    scores = [{c: 0.0 for c in CATEGORIES}] * 3
    report = evaluate(gold, scores, CATEGORIES, "test")

    support = {m.category: m.support for m in report.per_class}
    assert support == {FP: 2, TP: 1, DS: 1}
    assert report.total_support == 4


def test_low_support_categories_are_marked_unreliable():
    gold = [(FP,)] * 30 + [(DS,)] * 3
    scores = [{FP: 0.9, TP: 0.0, DS: 0.0}] * 30 + [{FP: 0.0, TP: 0.0, DS: 0.9}] * 3
    report = evaluate(gold, scores, CATEGORIES, "test")

    assert DS in report.unreliable
    assert FP not in report.unreliable


def test_a_never_predicted_category_is_named():
    gold = [(FP,), (DS,)]
    scores = [{FP: 0.9, TP: 0.0, DS: 0.0}, {FP: 0.9, TP: 0.0, DS: 0.0}]
    report = evaluate(gold, scores, CATEGORIES, "test")

    assert DS in report.never_predicted


def test_evaluation_refuses_mismatched_inputs():
    with pytest.raises(ValueError, match="gold rows"):
        evaluate([(FP,)], [], CATEGORIES, "test")


def test_evaluation_refuses_an_empty_set():
    with pytest.raises(ValueError, match="empty set"):
        evaluate([], [], CATEGORIES, "test")


def test_report_records_which_split_it_came_from():
    """So a training figure can never be mistaken for a test figure."""
    gold = [(FP,)]
    scores = [{FP: 0.9, TP: 0.0, DS: 0.0}]

    assert evaluate(gold, scores, CATEGORIES, "train").split_name == "train"
    assert metrics_to_dict(evaluate(gold, scores, CATEGORIES, "test"))["split"] == "test"


def test_held_out_evaluation_is_separate_from_training(trained):
    """Train and test scores must be computed from different data."""
    texts, labels = tiny_training_set()
    held_out_texts = ["we encrypt your data in transit", "we collect your name"]
    held_out_labels = [(DS,), (FP,)]

    train_report = evaluate(
        labels, trained.predict_scores(texts), CATEGORIES, "train"
    )
    test_report = evaluate(
        held_out_labels, trained.predict_scores(held_out_texts), CATEGORIES, "test"
    )

    assert train_report.examples == len(texts)
    assert test_report.examples == 2
    assert train_report.split_name != test_report.split_name
