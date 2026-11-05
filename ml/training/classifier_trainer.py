"""The F-11 improved training loop. Imports torch; kept out of `analysis/`."""

from __future__ import annotations

import json
from pathlib import Path

from analysis.models.improved_classifier import ImprovedClassifierConfig
from ml.data.splits import DatasetSplit
from ml.evaluation import evaluate, format_evaluation, metrics_to_dict


def train_and_evaluate(
    split: DatasetSplit, config: ImprovedClassifierConfig, output: Path
) -> int:
    """Fine-tune, select on validation, evaluate once on test.

    The order matters and is enforced by the structure: the test split is not
    touched until after the model is chosen.
    """
    import numpy as np
    import torch
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.manual_seed(config.random_seed)
    np.random.seed(config.random_seed)

    categories = list(config.categories)
    index_for = {category: index for index, category in enumerate(categories)}
    tokenizer = AutoTokenizer.from_pretrained(config.model_identifier)

    class SegmentDataset(Dataset):
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
            target = torch.zeros(len(categories))
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
    optimiser = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    train_loader = DataLoader(
        SegmentDataset(split.train), batch_size=config.batch_size, shuffle=True
    )

    model.train()
    for epoch in range(config.epochs):
        total = 0.0
        for batch in train_loader:
            optimiser.zero_grad()
            outputs = model(**batch)
            outputs.loss.backward()
            optimiser.step()
            total += float(outputs.loss)
        print(f"epoch {epoch + 1}/{config.epochs}  mean loss {total / max(len(train_loader), 1):.4f}")

    model.eval()

    def predict(examples) -> list[tuple[str, ...]]:
        predicted: list[tuple[str, ...]] = []
        loader = DataLoader(SegmentDataset(examples), batch_size=config.batch_size)
        with torch.no_grad():
            for batch in loader:
                batch.pop("labels")
                probabilities = torch.sigmoid(model(**batch).logits)
                for row in probabilities:
                    predicted.append(
                        tuple(
                            categories[index]
                            for index, value in enumerate(row)
                            if float(value) >= config.decision_threshold
                        )
                    )
        return predicted

    # Validation first. Anything chosen from the test split would make the
    # reported number meaningless.
    validation = evaluate(
        [example.labels for example in split.validation],
        predict(split.validation),
        categories,
    )
    print("\n--- validation ---")
    print(format_evaluation(validation))

    test = evaluate(
        [example.labels for example in split.test], predict(split.test), categories
    )
    print("\n--- held-out test (used once) ---")
    print(format_evaluation(test))

    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    (output / "metadata.json").write_text(
        json.dumps(
            {
                **config.as_metadata(),
                "split_seed": config.random_seed,
                "validation_metrics": metrics_to_dict(validation),
                "test_metrics": metrics_to_dict(test),
                "baseline_reference": "M5 TF-IDF + One-vs-Rest LR, commit 7d0ee1a",
                "comparison_note": (
                    "Same policy-grouped split and seed as the M5 baseline. "
                    "An improvement may be claimed only from these held-out "
                    "test numbers against the baseline's."
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nsaved to {output}")
    return 0


__all__ = ["train_and_evaluate"]
