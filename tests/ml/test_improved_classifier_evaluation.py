"""F-11 improved classifier: the score contract, and the evaluation-only path.

These tests exist because of a real integration failure. The trainer's
prediction helper returned tuples of category *names*, already thresholded,
while `ml.evaluation.evaluate` expects one mapping of category to probability
per example. A three-epoch GPU run therefore trained successfully, saved its
checkpoint and then died in the evaluator with ``AttributeError: 'tuple' object
has no attribute 'get'``.

Two things are pinned here: the shape the trainer hands the evaluator, and the
fact that an existing checkpoint can be scored without training anything.

Controlled fixtures and stubs throughout. The torch-backed plumbing is covered
separately and skips where torch is not installed; the contract itself is pure
Python and runs everywhere.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from analysis.models.improved_classifier import ImprovedClassifierConfig
from ml.data.opp115_dataset import LabelledSegment
from ml.data.splits import split_by_policy
from ml.evaluation import evaluate
from ml.training.classifier_trainer import (
    evaluate_checkpoint,
    load_checkpoint,
    scores_from_probabilities,
)

FP = "First Party Collection/Use"
TP = "Third Party Sharing/Collection"
DS = "Data Security"
CATEGORIES = [FP, TP, DS]


def config(**overrides) -> ImprovedClassifierConfig:
    return ImprovedClassifierConfig(categories=tuple(CATEGORIES), **overrides)


def fake_examples(policies: int = 30, per_policy: int = 4) -> list[LabelledSegment]:
    return [
        LabelledSegment(f"policy_{p:03d}", i, f"text {p} {i}", (FP,) if i % 2 else ())
        for p in range(policies)
        for i in range(per_policy)
    ]


# ---------------------------------------------------------------------------
# The score contract
# ---------------------------------------------------------------------------


def test_one_dictionary_per_example():
    scores = scores_from_probabilities(
        [[0.9, 0.1, 0.0], [0.2, 0.8, 0.3]], CATEGORIES
    )

    assert len(scores) == 2
    assert all(isinstance(row, dict) for row in scores)


def test_every_configured_category_is_keyed():
    """`evaluate` reads `row.get(category)` for every category, so a missing
    key would silently score that class as zero."""
    scores = scores_from_probabilities([[0.9, 0.1, 0.0]], CATEGORIES)

    assert set(scores[0]) == set(CATEGORIES)


def test_columns_map_to_the_configured_category_order():
    scores = scores_from_probabilities([[0.1, 0.2, 0.3]], CATEGORIES)

    assert scores[0] == {FP: 0.1, TP: 0.2, DS: 0.3}


def test_sub_threshold_scores_are_kept_not_dropped():
    """The defect being fixed. Thresholding inside prediction discarded every
    score below the cut, which is precisely what the evaluator needs in order
    to apply a threshold of its own."""
    scores = scores_from_probabilities([[0.9, 0.49, 0.01]], CATEGORIES)

    assert scores[0][TP] == pytest.approx(0.49)
    assert scores[0][DS] == pytest.approx(0.01)


def test_scores_are_floats_not_tensors_or_names():
    scores = scores_from_probabilities([[0.9, 0.1, 0.0]], CATEGORIES)

    assert all(type(value) is float for value in scores[0].values())


def test_a_wrong_output_width_is_refused():
    """A checkpoint with a different label count would attach the right names
    to the wrong columns."""
    with pytest.raises(RuntimeError, match="outputs for 3 configured categories"):
        scores_from_probabilities([[0.9, 0.1]], CATEGORIES)


def test_no_rows_gives_no_scores():
    assert scores_from_probabilities([], CATEGORIES) == []


# ---------------------------------------------------------------------------
# Evaluator integration
# ---------------------------------------------------------------------------


def test_scores_feed_the_evaluator_unchanged():
    """The regression. This is the call that raised AttributeError."""
    gold = [(FP,), (TP,), ()]
    scores = scores_from_probabilities(
        [[0.9, 0.1, 0.0], [0.1, 0.9, 0.0], [0.1, 0.1, 0.1]], CATEGORIES
    )

    report = evaluate(gold, scores, CATEGORIES, "validation", threshold=0.5)

    assert report.examples == 3
    assert report.micro_f1 == pytest.approx(1.0)


def test_category_name_tuples_are_not_a_valid_score_row():
    """Pins the defect itself: the old return shape cannot be evaluated. If
    this ever stops raising, the evaluator's contract has been loosened."""
    with pytest.raises(AttributeError, match="has no attribute 'get'"):
        evaluate([(FP,)], [(FP,)], CATEGORIES, "validation")


def test_the_evaluator_owns_the_threshold():
    """Scores must still be live numbers when they reach `evaluate`, or its
    threshold argument does nothing."""
    gold = [(FP, TP)]
    scores = scores_from_probabilities([[0.9, 0.6, 0.0]], CATEGORIES)

    strict = evaluate(gold, scores, CATEGORIES, "validation", threshold=0.8)
    lenient = evaluate(gold, scores, CATEGORIES, "validation", threshold=0.5)

    assert strict.micro_f1 < lenient.micro_f1 == pytest.approx(1.0)


def test_the_configured_threshold_is_the_one_reported():
    gold = [(FP,)]
    scores = scores_from_probabilities([[0.9, 0.1, 0.0]], CATEGORIES)
    settings = config()

    report = evaluate(
        gold, scores, CATEGORIES, "test", threshold=settings.decision_threshold
    )

    assert report.threshold == settings.decision_threshold


# ---------------------------------------------------------------------------
# Evaluation-only path
# ---------------------------------------------------------------------------


def test_a_missing_checkpoint_is_refused_and_nothing_is_substituted(tmp_path):
    """An audit bound to the improved variant must not be scored on some other
    model, so this fails loudly rather than falling back."""
    split = split_by_policy(fake_examples())

    with pytest.raises(FileNotFoundError, match="train_improved_classifier"):
        evaluate_checkpoint(split, config(), tmp_path / "absent")


def test_load_checkpoint_refuses_a_missing_directory(tmp_path):
    with pytest.raises(FileNotFoundError, match="No other model is substituted"):
        load_checkpoint(tmp_path / "absent", CATEGORIES, device=None)


def test_an_empty_evaluation_split_is_refused(tmp_path):
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    split = split_by_policy(fake_examples())

    with pytest.raises(ValueError, match="validation split is empty"):
        evaluate_checkpoint(
            dataclasses.replace(split, validation=[]), config(), checkpoint
        )


def test_nothing_is_written_when_evaluation_cannot_start(tmp_path):
    """Metrics and metadata are written only after both reports exist."""
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    metrics = tmp_path / "runs" / "metrics.json"
    split = split_by_policy(fake_examples())

    with pytest.raises(ValueError):
        evaluate_checkpoint(
            dataclasses.replace(split, test=[]), config(), checkpoint, metrics
        )

    assert not metrics.exists()
    assert not (checkpoint / "metadata.json").exists()
    assert list(checkpoint.iterdir()) == []


# ---------------------------------------------------------------------------
# Entry-point routing
# ---------------------------------------------------------------------------


@pytest.fixture
def entry_point(monkeypatch):
    import ml.train_improved_classifier as entry
    import ml.training.classifier_trainer as trainer

    monkeypatch.setattr(entry, "read_dataset", lambda *a, **k: fake_examples())

    calls: list[str] = []
    monkeypatch.setattr(
        trainer, "train_and_evaluate", lambda *a, **k: calls.append("train") or 0
    )
    monkeypatch.setattr(
        trainer,
        "evaluate_checkpoint",
        lambda *a, **k: calls.append("evaluate") or 0,
    )
    return entry, calls


def test_evaluate_only_never_trains(entry_point, monkeypatch, tmp_path):
    entry, calls = entry_point
    monkeypatch.setattr(
        "sys.argv",
        ["train_improved_classifier.py", "--evaluate-only", "--output", str(tmp_path)],
    )

    assert entry.main() == 0
    assert calls == ["evaluate"]


def test_the_default_mode_still_trains(entry_point, monkeypatch, tmp_path):
    entry, calls = entry_point
    monkeypatch.setattr(
        "sys.argv", ["train_improved_classifier.py", "--output", str(tmp_path)]
    )

    assert entry.main() == 0
    assert calls == ["train"]


def test_dry_run_does_neither(entry_point, monkeypatch):
    entry, calls = entry_point
    monkeypatch.setattr(
        "sys.argv", ["train_improved_classifier.py", "--dry-run", "--evaluate-only"]
    )

    assert entry.main() == 0
    assert calls == []


def test_both_modes_build_the_same_split_and_seed(entry_point, monkeypatch, tmp_path):
    """An evaluation run that scored a different split from the one the weights
    were fitted on would report a meaningless number."""
    entry, _ = entry_point
    seen: list[tuple] = []

    import ml.training.classifier_trainer as trainer

    monkeypatch.setattr(
        trainer,
        "train_and_evaluate",
        lambda split, config, *a, **k: seen.append(
            (split.policies_in("test"), config.random_seed)
        )
        or 0,
    )
    monkeypatch.setattr(
        trainer,
        "evaluate_checkpoint",
        lambda split, config, *a, **k: seen.append(
            (split.policies_in("test"), config.random_seed)
        )
        or 0,
    )

    for argv in (
        ["train_improved_classifier.py", "--output", str(tmp_path)],
        ["train_improved_classifier.py", "--evaluate-only", "--output", str(tmp_path)],
    ):
        monkeypatch.setattr("sys.argv", argv)
        entry.main()

    assert len(seen) == 2
    assert seen[0] == seen[1]
    assert seen[0][1] == ImprovedClassifierConfig().random_seed


# ---------------------------------------------------------------------------
# torch-backed plumbing
# ---------------------------------------------------------------------------


class StubTokenizer:
    """Encodes a batch of texts as fixed-width integer tensors."""

    def __call__(self, texts, truncation, max_length, padding, return_tensors):
        import torch

        assert truncation is True
        assert padding == "max_length"
        width = 4
        return {
            "input_ids": torch.ones((len(texts), width), dtype=torch.long),
            "attention_mask": torch.ones((len(texts), width), dtype=torch.long),
        }


class StubModel:
    """Serves pre-set logits in input order and records how it was batched."""

    def __init__(self, logit_rows):
        self.remaining = [list(row) for row in logit_rows]
        self.batch_sizes: list[int] = []
        self.eval_calls = 0

    def eval(self):
        self.eval_calls += 1
        return self

    def __call__(self, input_ids, attention_mask):
        import torch

        size = input_ids.shape[0]
        self.batch_sizes.append(size)
        rows, self.remaining = self.remaining[:size], self.remaining[size:]
        return SimpleNamespace(logits=torch.tensor(rows, dtype=torch.float32))


def test_predict_scores_applies_sigmoid_without_thresholding():
    torch = pytest.importorskip("torch")
    from ml.training.classifier_trainer import predict_scores

    examples = fake_examples(policies=1, per_policy=3)
    logits = [[2.0, -1.0, 0.0], [-3.0, 3.0, 0.0], [0.0, 0.0, 0.0]]
    model = StubModel(logits)

    scores = predict_scores(
        model,
        StubTokenizer(),
        examples,
        config=config(batch_size=2),
        categories=CATEGORIES,
    )

    assert len(scores) == 3
    assert model.batch_sizes == [2, 1], "batches must follow config.batch_size"
    assert model.eval_calls >= 1, "scoring must not run in training mode"
    for row, expected in zip(scores, logits, strict=True):
        for index, category in enumerate(CATEGORIES):
            assert row[category] == pytest.approx(
                float(torch.sigmoid(torch.tensor(expected[index])))
            )
    assert scores[0][TP] < 0.5, "a sub-threshold score must survive prediction"


def test_predict_scores_output_is_accepted_by_the_evaluator():
    pytest.importorskip("torch")
    from ml.training.classifier_trainer import predict_scores

    examples = fake_examples(policies=1, per_policy=2)
    model = StubModel([[4.0, -4.0, -4.0], [-4.0, 4.0, -4.0]])

    scores = predict_scores(
        model, StubTokenizer(), examples, config=config(), categories=CATEGORIES
    )
    report = evaluate(
        [example.labels for example in examples], scores, CATEGORIES, "validation"
    )

    assert report.examples == 2


def test_predict_scores_on_no_examples_calls_no_model():
    pytest.importorskip("torch")
    from ml.training.classifier_trainer import predict_scores

    model = StubModel([])

    assert (
        predict_scores(
            model, StubTokenizer(), [], config=config(), categories=CATEGORIES
        )
        == []
    )
    assert model.batch_sizes == []


def test_evaluate_only_exits_nonzero_when_there_is_no_checkpoint(
    monkeypatch, tmp_path, capsys
):
    """A missing checkpoint is a clean failure, not a traceback, and not a
    silent fallback to some other model."""
    import ml.train_improved_classifier as entry

    monkeypatch.setattr(entry, "read_dataset", lambda *a, **k: fake_examples())
    monkeypatch.setattr(
        "sys.argv",
        [
            "train_improved_classifier.py",
            "--evaluate-only",
            "--output",
            str(tmp_path / "absent"),
        ],
    )

    assert entry.main() == 2
    assert "No usable checkpoint" in capsys.readouterr().err


def test_evaluation_only_never_writes_into_the_checkpoint(tmp_path, monkeypatch):
    """A training run's metadata.json is the record of how the weights were
    produced. An evaluation must not overwrite it."""
    import ml.training.classifier_trainer as trainer

    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "metadata.json").write_text('{"weights_trained_in_this_run": true}')
    (checkpoint / "model.safetensors").write_bytes(b"weights")
    before = {
        path.name: path.read_bytes() for path in sorted(checkpoint.iterdir())
    }
    metrics = tmp_path / "runs" / "metrics.json"
    split = split_by_policy(fake_examples())

    report = evaluate(
        [(FP,)], scores_from_probabilities([[0.9, 0.1, 0.0]], CATEGORIES),
        CATEGORIES, "validation",
    )
    monkeypatch.setattr(trainer, "_select_device", lambda: None)
    monkeypatch.setattr(trainer, "load_checkpoint", lambda *a, **k: (None, None))
    monkeypatch.setattr(
        trainer, "_score_both_splits", lambda *a, **k: (report, report)
    )

    assert trainer.evaluate_checkpoint(split, config(), checkpoint, metrics) == 0

    assert metrics.exists(), "the metrics file is the output of an evaluation"
    after = {path.name: path.read_bytes() for path in sorted(checkpoint.iterdir())}
    assert after == before, "the checkpoint directory must be untouched"


# ---------------------------------------------------------------------------
# Backend input filtering
# ---------------------------------------------------------------------------


def test_only_inputs_the_model_accepts_are_passed():
    """`distilbert-base-uncased` saves a tokenizer config declaring
    `BertTokenizer`, so the improved checkpoint's tokenizer emits
    `token_type_ids` that DistilBERT's forward rejects with a TypeError. The
    backend must filter against the real signature."""
    from ml.backends import model_inputs

    class DistilBertLike:
        def forward(self, input_ids=None, attention_mask=None, head_mask=None):
            raise AssertionError("not called")

    encoded = {
        "input_ids": "I",
        "attention_mask": "A",
        "token_type_ids": "T",
    }

    assert model_inputs(DistilBertLike(), encoded) == {
        "input_ids": "I",
        "attention_mask": "A",
    }


def test_inputs_a_model_does_accept_are_kept():
    """The filter must not silently drop a BERT-family model's segment ids."""
    from ml.backends import model_inputs

    class BertLike:
        def forward(self, input_ids=None, attention_mask=None, token_type_ids=None):
            raise AssertionError("not called")

    encoded = {"input_ids": "I", "attention_mask": "A", "token_type_ids": "T"}

    assert model_inputs(BertLike(), encoded) == encoded


def test_the_backend_tokenises_as_the_evaluated_run_did():
    """The probabilities the API serves are the ones the reported metrics
    describe, so the sequence length must come from one place."""
    from ml.backends import TransformersClassifierBackend

    pytest.importorskip("torch")
    checkpoint = pytest.importorskip("pathlib").Path(
        "ml/checkpoints/improved_classifier"
    )
    if not checkpoint.is_dir():
        pytest.skip("the improved checkpoint is not present on this machine")

    backend = TransformersClassifierBackend(checkpoint)

    assert backend.max_length == ImprovedClassifierConfig().max_sequence_length
