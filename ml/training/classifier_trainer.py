"""F-11's improved classifier: fine-tuning, and scoring a saved checkpoint.

Imports torch; kept out of `analysis/`.

Two entry points, deliberately separate:

``train_and_evaluate``   fine-tunes, saves the checkpoint, then scores it.
``evaluate_checkpoint``  scores a checkpoint that already exists, and trains
                         nothing.

The second exists because the fine-tune needs a borrowed GPU and the
evaluation does not. A run that saved its weights and then failed before
reporting can be scored from those weights rather than repeated, which is what
happened to the first Colab run. The checkpoint is opened read-only: nothing is
written into it until an evaluation has actually succeeded.

Both paths score through `predict_scores` and report through
`ml.evaluation.evaluate`, so the numbers a training run prints and the numbers a
later evaluation prints come from one implementation rather than two that could
drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path

from analysis.models.improved_classifier import ImprovedClassifierConfig
from ml.data.splits import DatasetSplit
from ml.evaluation import evaluate, format_evaluation, metrics_to_dict

#: The frozen M5 figures this model is compared against. Not recomputed here.
BASELINE_REFERENCE = "M5 TF-IDF + One-vs-Rest LR, commit 7d0ee1a"
COMPARISON_NOTE = (
    "Same policy-grouped split and seed as the M5 baseline. An improvement may "
    "be claimed only from these held-out test numbers against the baseline's."
)

#: The only tokenizer outputs the model is fed. Keeping the set explicit stops
#: a tokenizer that emits extra tensors from reaching a model whose forward
#: signature has no parameter for them.
MODEL_INPUTS = ("input_ids", "attention_mask")


def _select_device():
    import torch

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    return device


def _resolved_categories(config: ImprovedClassifierConfig) -> list[str]:
    categories = list(config.categories)
    if not categories:
        raise ValueError("No classification categories are configured.")
    if len(categories) != len(set(categories)):
        raise ValueError("Duplicate classification categories are configured.")
    return categories


def _require_splits(split: DatasetSplit, names: tuple[str, ...]) -> None:
    for name in names:
        if not getattr(split, name):
            raise ValueError(f"The {name} split is empty.")


def scores_from_probabilities(rows, categories: list[str]) -> list[dict[str, float]]:
    """Key each row of probabilities by category name. One dict per row.

    Deliberately pure: no torch, no model, no threshold. This is the piece that
    defines the contract `ml.evaluation.evaluate` consumes, so it is testable on
    any machine rather than only where a GPU and a checkpoint happen to exist.

    **No thresholding happens here.** Turning a score into a prediction is a
    reporting choice that `evaluate` owns, and that F-14 owns in the pipeline.
    Doing it here as well would apply the threshold twice and fix it at whatever
    value this module happened to be holding, and it would throw away the scores
    the evaluator needs: the earlier version returned the surviving category
    *names* as a tuple, which is why ``row.get(category, 0.0)`` raised
    ``AttributeError: 'tuple' object has no attribute 'get'``.
    """
    width = len(categories)
    scores: list[dict[str, float]] = []
    for row in rows:
        values = list(row)
        if len(values) != width:
            raise RuntimeError(
                f"The model produced {len(values)} outputs for {width} "
                "configured categories, so the scores cannot be keyed by "
                "category."
            )
        scores.append(
            {category: float(values[index]) for index, category in enumerate(categories)}
        )
    return scores


def _require_checkpoint(checkpoint: Path) -> Path:
    """Fail before any heavy import, and never substitute another model."""
    checkpoint = Path(checkpoint)
    if not checkpoint.is_dir():
        raise FileNotFoundError(
            f"There is no checkpoint directory at {checkpoint}. Train one with "
            "ml/train_improved_classifier.py, or point --output at an existing "
            "one. No other model is substituted."
        )
    return checkpoint


def predict_scores(
    model,
    tokenizer,
    examples,
    *,
    config: ImprovedClassifierConfig,
    categories: list[str],
    device=None,
) -> list[dict[str, float]]:
    """One dictionary per example, every configured category to its probability.

    **Nothing is thresholded here.** Turning a score into a prediction is a
    reporting choice that `ml.evaluation.evaluate` owns, and that F-14 owns in
    the pipeline. Doing it here as well would apply the threshold twice and fix
    it at whatever value this module happened to be holding, and it would throw
    away the scores the evaluator needs: the earlier version returned the
    surviving category *names* as a tuple, which is why the evaluator's
    ``row.get(category, 0.0)`` raised ``AttributeError: 'tuple' object has no
    attribute 'get'``.

    The returned shape is exactly what the M5 baseline's ``predict_scores``
    returns. One evaluator scoring both models is what makes the comparison a
    comparison of models rather than of two measurement paths.
    """
    import torch

    if not examples:
        return []

    model.eval()
    scores: list[dict[str, float]] = []

    with torch.no_grad():
        for start in range(0, len(examples), config.batch_size):
            batch = examples[start : start + config.batch_size]
            encoded = tokenizer(
                [example.text for example in batch],
                truncation=True,
                max_length=config.max_sequence_length,
                padding="max_length",
                return_tensors="pt",
            )
            inputs = {
                key: encoded[key] for key in MODEL_INPUTS if key in encoded
            }
            if device is not None:
                inputs = {
                    key: value.to(device, non_blocking=(device.type == "cuda"))
                    for key, value in inputs.items()
                }

            probabilities = torch.sigmoid(model(**inputs).logits).detach().cpu()
            scores.extend(scores_from_probabilities(probabilities, categories))

    if len(scores) != len(examples):
        raise RuntimeError(
            f"Scored {len(scores)} rows for {len(examples)} examples."
        )
    return scores


def load_checkpoint(checkpoint: Path, categories: list[str], device):
    """Open a saved checkpoint for scoring. Reads only; writes nothing."""
    checkpoint = _require_checkpoint(checkpoint)

    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModelForSequenceClassification.from_pretrained(checkpoint)

    # The checkpoint's own config carries its label count, so a mismatch is
    # reported against the configuration rather than silently scoring the
    # wrong columns under the right names.
    if model.config.num_labels != len(categories):
        raise ValueError(
            f"The checkpoint at {checkpoint} has {model.config.num_labels} "
            f"output labels but {len(categories)} categories are configured. "
            "Scoring it would attach category names to the wrong columns."
        )

    model.to(device)
    model.eval()
    return model, tokenizer


def _score_both_splits(
    model,
    tokenizer,
    split: DatasetSplit,
    config: ImprovedClassifierConfig,
    categories: list[str],
    device,
):
    """Validation first, then the held-out test split exactly once.

    The order is enforced by the structure of this function: the test split is
    not read until the validation report exists.
    """
    validation = evaluate(
        [example.labels for example in split.validation],
        predict_scores(
            model,
            tokenizer,
            split.validation,
            config=config,
            categories=categories,
            device=device,
        ),
        categories,
        "validation",
        threshold=config.decision_threshold,
    )
    print("\n--- Validation ---")
    print(format_evaluation(validation))

    test = evaluate(
        [example.labels for example in split.test],
        predict_scores(
            model,
            tokenizer,
            split.test,
            config=config,
            categories=categories,
            device=device,
        ),
        categories,
        "test",
        threshold=config.decision_threshold,
    )
    print("\n--- Held-out test (used once) ---")
    print(format_evaluation(test))

    return validation, test


def _metrics_payload(
    config: ImprovedClassifierConfig,
    validation,
    test,
    *,
    device_label: str,
    checkpoint: Path,
    weights_trained_in_this_run: bool,
) -> dict:
    return {
        **config.as_metadata(),
        "split_seed": config.random_seed,
        "evaluation_device": device_label,
        "checkpoint": str(checkpoint),
        "weights_trained_in_this_run": weights_trained_in_this_run,
        "validation_metrics": metrics_to_dict(validation),
        "test_metrics": metrics_to_dict(test),
        "baseline_reference": BASELINE_REFERENCE,
        "comparison_note": COMPARISON_NOTE,
    }


def _write_json(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {path}")


def evaluate_checkpoint(
    split: DatasetSplit,
    config: ImprovedClassifierConfig,
    checkpoint: Path,
    metrics: Path | None = None,
) -> int:
    """Score an existing checkpoint on validation and then held-out test.

    Trains nothing and writes nothing at all into the checkpoint directory.
    A training run's `metadata.json` records the provenance of that run, and an
    evaluation is a separate event, so overwriting it would destroy the record
    of how the weights were produced. The metrics go to `metrics` instead, and
    only once both reports exist, so a failure partway through leaves the
    checkpoint and any previous metrics exactly as they were.
    """
    categories = _resolved_categories(config)
    _require_splits(split, ("validation", "test"))
    checkpoint = _require_checkpoint(checkpoint)

    import numpy as np
    import torch

    torch.manual_seed(config.random_seed)
    np.random.seed(config.random_seed)

    device = _select_device()
    model, tokenizer = load_checkpoint(checkpoint, categories, device)
    print(f"Loaded checkpoint (no training): {checkpoint}")

    validation, test = _score_both_splits(
        model, tokenizer, split, config, categories, device
    )

    payload = _metrics_payload(
        config,
        validation,
        test,
        device_label=str(device),
        checkpoint=checkpoint,
        weights_trained_in_this_run=False,
    )
    if metrics is not None:
        _write_json(Path(metrics), payload)
    else:
        print("No --metrics path given, so no metrics file was written.")

    print(
        "\nEvaluation complete. Nothing was trained, and nothing in "
        f"{checkpoint} was modified."
    )
    return 0


def train_and_evaluate(
    split: DatasetSplit,
    config: ImprovedClassifierConfig,
    output: Path,
    metrics: Path | None = None,
) -> int:
    """Fine-tune, save, select on validation, then evaluate once on test."""
    import numpy as np
    import torch
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.manual_seed(config.random_seed)
    np.random.seed(config.random_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.random_seed)

    categories = _resolved_categories(config)
    _require_splits(split, ("train", "validation", "test"))
    index_for = {category: index for index, category in enumerate(categories)}

    device = _select_device()
    tokenizer = AutoTokenizer.from_pretrained(config.model_identifier)

    class SegmentDataset(Dataset):
        """Training examples only. Scoring goes through `predict_scores`."""

        def __init__(self, examples):
            self.examples = list(examples)

        def __len__(self):
            return len(self.examples)

        def __getitem__(self, index):
            example = self.examples[index]
            encoded = tokenizer(
                example.text,
                truncation=True,
                max_length=config.max_sequence_length,
                padding="max_length",
                return_tensors="pt",
            )
            target = torch.zeros(len(categories), dtype=torch.float32)
            for label in example.labels:
                if label in index_for:
                    target[index_for[label]] = 1.0
            return {
                "input_ids": encoded["input_ids"][0],
                "attention_mask": encoded["attention_mask"][0],
                "labels": target,
            }

    model = AutoModelForSequenceClassification.from_pretrained(
        config.model_identifier,
        num_labels=len(categories),
        problem_type="multi_label_classification",
    )
    model.to(device)

    optimiser = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    train_loader = DataLoader(
        SegmentDataset(split.train),
        batch_size=config.batch_size,
        shuffle=True,
        pin_memory=(device.type == "cuda"),
    )

    model.train()
    for epoch in range(config.epochs):
        total_loss = 0.0
        for batch in train_loader:
            batch = {
                key: value.to(device, non_blocking=(device.type == "cuda"))
                for key, value in batch.items()
            }
            optimiser.zero_grad(set_to_none=True)
            outputs = model(**batch)
            outputs.loss.backward()
            optimiser.step()
            total_loss += outputs.loss.detach().item()

        mean_loss = total_loss / max(len(train_loader), 1)
        print(f"Epoch {epoch + 1}/{config.epochs} | mean loss {mean_loss:.4f}")

    model.eval()

    # Saved before the evaluation on purpose: the weights are the expensive
    # part and a reporting failure must not cost the fine-tune. `--evaluate-only`
    # then scores what was saved here.
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    print(f"\nCheckpoint saved to {output}")

    validation, test = _score_both_splits(
        model, tokenizer, split, config, categories, device
    )

    payload = _metrics_payload(
        config,
        validation,
        test,
        device_label=str(device),
        checkpoint=output,
        weights_trained_in_this_run=True,
    )
    _write_json(output / "metadata.json", payload)
    if metrics is not None:
        _write_json(Path(metrics), payload)

    print("\nTraining and evaluation complete.")
    return 0


__all__ = [
    "evaluate_checkpoint",
    "load_checkpoint",
    "predict_scores",
    "scores_from_probabilities",
    "train_and_evaluate",
]
