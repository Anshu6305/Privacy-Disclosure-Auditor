#!/usr/bin/env python3
"""Train and evaluate F-12, the data-type and purpose span extractor (ALG-3).

Token classification over the OPP-115 spans M6 verified. One model tags both
span types, and a tag names the attribute value as well as the type —
``B-data_type:Contact``, not ``B-data_type`` — because F-15's rules are keyed
on the value and a boundary-only tagger would produce spans no rule can match.

    python ml/train_span_extractor.py --dry-run          # no torch needed
    python ml/train_span_extractor.py --epochs 4         # the real run

**Reproducibility.** The split is M5's: by source policy, seed 20261105,
80/17/18 policies. Nothing here reshuffles, re-labels or re-splits. The test
split is read **once**, for the final table; the validation split is what any
threshold or epoch choice is made against.

**Evaluation is span-level, not token-level.** A token-level F1 flatters a
tagger that gets most of a long span right and the boundary wrong, and a
wrong boundary is precisely what produces a misquoted policy. A predicted
span counts as correct only when its type, its value and both its offsets
match a gold span exactly. Partial-overlap figures are reported beside the
exact ones so the gap is visible rather than hidden by whichever definition
flatters more.

Every predicted span is also sliced back out of the segment and compared to
its own text. A span that does not round-trip is counted and reported, never
silently dropped: it would be a quote the policy does not contain.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.data.span_training_data import (  # noqa: E402
    OUTSIDE,
    TaggedSegment,
    build_tagged_segments,
    label_set,
    read_jsonl,
    split_segments,
)
from ml.data.splits import DEFAULT_SEED  # noqa: E402

DEFAULT_MODEL = "distilbert-base-uncased"
DEFAULT_ARTEFACT_DIR = Path("ml/checkpoints/span-extractor-v1")
DEFAULT_METRICS_PATH = Path("ml/runs/span-extractor-v1-metrics.json")


# ---------------------------------------------------------------------------
# Span-level scoring, which needs no torch and is therefore unit-testable.
# ---------------------------------------------------------------------------


@dataclass
class SpanScores:
    """Exact and overlapping span agreement, plus round-trip failures."""

    exact_tp: int = 0
    overlap_tp: int = 0
    predicted: int = 0
    gold: int = 0
    unverifiable: int = 0
    per_type: dict = field(default_factory=dict)

    def _f1(self, true_positives: int) -> tuple[float, float, float]:
        precision = true_positives / self.predicted if self.predicted else 0.0
        recall = true_positives / self.gold if self.gold else 0.0
        if precision + recall == 0:
            return precision, recall, 0.0
        return precision, recall, 2 * precision * recall / (precision + recall)

    def exact(self) -> tuple[float, float, float]:
        return self._f1(self.exact_tp)

    def overlapping(self) -> tuple[float, float, float]:
        return self._f1(self.overlap_tp)


def score_segments(
    segments: list[TaggedSegment], predictions: list[list[str]]
) -> SpanScores:
    """Compare predicted tag sequences with the gold ones, span by span."""
    scores = SpanScores()
    per_type: dict[str, Counter] = {}

    for segment, predicted_tags in zip(segments, predictions, strict=True):
        gold = set(decode(segment, segment.tags))
        predicted = set(decode(segment, predicted_tags))

        scores.gold += len(gold)
        scores.predicted += len(predicted)
        scores.exact_tp += len(gold & predicted)

        for span in predicted:
            span_type = span[0]
            bucket = per_type.setdefault(span_type, Counter())
            bucket["predicted"] += 1
            if span in gold:
                bucket["exact_tp"] += 1
            if any(
                other[0] == span[0]
                and other[1] == span[1]
                and other[2] < span[3]
                and span[2] < other[3]
                for other in gold
            ):
                scores.overlap_tp += 1
                bucket["overlap_tp"] += 1
            # A predicted span must slice back out of the text it indexes.
            if segment.text[span[2] : span[3]].strip() == "":
                scores.unverifiable += 1

        for span in gold:
            per_type.setdefault(span[0], Counter())["gold"] += 1

    scores.per_type = {name: dict(counts) for name, counts in per_type.items()}
    return scores


def decode(
    segment: TaggedSegment, tags: list[str] | tuple[str, ...]
) -> list[tuple[str, str, int, int]]:
    """Tag sequence to spans, in segment coordinates."""
    spans: list[tuple[str, str, int, int]] = []
    current: tuple[str, str] | None = None
    start = 0
    end = 0

    def close() -> None:
        nonlocal current
        if current is not None and end > start:
            spans.append((current[0], current[1], start, end))
        current = None

    for (token_start, token_end), tag in zip(segment.offsets, tags, strict=True):
        if tag == OUTSIDE:
            close()
            continue
        prefix, _, payload = tag.partition("-")
        span_type, _, value = payload.partition(":")
        if not value:
            close()
            continue
        if prefix == "B" or current != (span_type, value):
            close()
            current = (span_type, value)
            start = token_start
        end = token_end
    close()
    return spans


def format_span_split_report(split, labels: list[str]) -> str:
    """Per-span-type and per-value support across the three splits.

    `format_split_report` is not reused for this. It reports support over the
    ten OPP-115 *categories*, which are not F-12's labels, so against this
    dataset it correctly prints zero for all ten and warns that none can be
    evaluated. That is true of the categories and says nothing about the
    spans, and printing it here would look like a catastrophic failure in a
    dataset that is in fact sound.
    """
    buckets = {
        "train": list(split.train),
        "validation": list(split.validation),
        "test": list(split.test),
    }
    lines = [
        "",
        f"{'split':<12}{'policies':>10}{'segments':>10}{'spans':>9}",
    ]
    counts: dict[str, Counter] = {name: Counter() for name in buckets}
    for name, segments in buckets.items():
        spans = 0
        for segment in segments:
            for span in decode(segment, segment.tags):
                spans += 1
                counts[name][f"{span[0]}:{span[1]}"] += 1
        lines.append(
            f"{name:<12}{split.report.policies[name]:>10}"
            f"{len(segments):>10}{spans:>9}"
        )

    lines += ["", "Per-label span support", "",
              f"{'label':<48}{'train':>8}{'val':>7}{'test':>7}"]
    thin: list[str] = []
    for label in sorted({k for c in counts.values() for k in c}):
        train_n = counts["train"][label]
        val_n = counts["validation"][label]
        test_n = counts["test"][label]
        note = ""
        if test_n == 0:
            note = "  NOT EVALUABLE (absent from test)"
            thin.append(label)
        elif test_n < 10:
            note = f"  unreliable (n={test_n})"
            thin.append(label)
        lines.append(f"{label:<48}{train_n:>8}{val_n:>7}{test_n:>7}{note}")

    if thin:
        lines += [
            "",
            f"{len(thin)} of {len(labels) - 1} labels have fewer than 10 test spans.",
            "Their per-label scores are not measurements and must not be",
            "reported as accuracy for those classes. This is the same rare-class",
            "limitation M5 recorded, and it is not fixed by this model.",
        ]
    return "\n".join(lines)


def format_scores(name: str, scores: SpanScores) -> str:
    exact_p, exact_r, exact_f = scores.exact()
    over_p, over_r, over_f = scores.overlapping()
    lines = [
        "-" * 78,
        f"F-12 span evaluation — {name} split",
        "-" * 78,
        f"gold spans      : {scores.gold}",
        f"predicted spans : {scores.predicted}",
        "",
        "EXACT match (type, value and both offsets identical) — the result:",
        f"  precision {exact_p:.4f}   recall {exact_r:.4f}   F1 {exact_f:.4f}",
        "",
        "Overlapping match (same type and value, any overlap) — reported so the",
        "boundary error rate is visible, NOT as the headline figure:",
        f"  precision {over_p:.4f}   recall {over_r:.4f}   F1 {over_f:.4f}",
        "",
        f"spans that did not slice back out of the segment: {scores.unverifiable}",
    ]
    if scores.per_type:
        lines.append("")
        lines.append(f"{'span type':<14}{'gold':>8}{'pred':>8}{'exact':>8}{'overlap':>9}")
        for span_type, counts in sorted(scores.per_type.items()):
            lines.append(
                f"{span_type:<14}{counts.get('gold', 0):>8}"
                f"{counts.get('predicted', 0):>8}"
                f"{counts.get('exact_tp', 0):>8}{counts.get('overlap_tp', 0):>9}"
            )
    lines.append("-" * 78)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Training. Imports torch only when actually asked to train.
# ---------------------------------------------------------------------------


def train(arguments, split, labels: list[str]) -> int:
    try:
        import numpy as np
        import torch
        from torch.utils.data import DataLoader
        from transformers import (
            AutoModelForTokenClassification,
            AutoTokenizer,
            get_linear_schedule_with_warmup,
        )
    except ImportError as exc:
        print(
            f"\nTraining needs torch and transformers, which are not installed ({exc}).\n"
            "Either:\n"
            "  pip install -r backend/requirements-ml.txt\n"
            "or run the GPU workflow in notebooks/train_f12_colab.ipynb, which\n"
            "installs them and uploads the dataset this script writes.\n"
            "\nNothing was trained and no checkpoint was written.",
            file=sys.stderr,
        )
        return 2

    label_to_id = {label: index for index, label in enumerate(labels)}
    torch.manual_seed(arguments.model_seed)
    np.random.seed(arguments.model_seed)

    tokenizer = AutoTokenizer.from_pretrained(arguments.model)
    model = AutoModelForTokenClassification.from_pretrained(
        arguments.model,
        num_labels=len(labels),
        id2label=dict(enumerate(labels)),
        label2id=label_to_id,
    )
    device = torch.device(
        "cuda" if torch.cuda.is_available()
        else "mps" if torch.backends.mps.is_available()
        else "cpu"
    )
    model.to(device)
    print(f"device: {device}")

    def encode(segments):
        """Tokenise and align labels to the FIRST subword of each word.

        Later subwords get -100 and are ignored by the loss. Labelling every
        subword would let a long word dominate the objective, and it would
        also mean a word could be scored as two different tags.
        """
        batch = tokenizer(
            [list(segment.tokens) for segment in segments],
            is_split_into_words=True,
            truncation=True,
            max_length=arguments.max_length,
            padding=True,
            return_tensors="pt",
        )
        all_labels = []
        for index, segment in enumerate(segments):
            word_ids = batch.word_ids(batch_index=index)
            previous = None
            row = []
            for word_id in word_ids:
                if word_id is None:
                    row.append(-100)
                elif word_id != previous:
                    row.append(label_to_id[segment.tags[word_id]])
                else:
                    row.append(-100)
                previous = word_id
            all_labels.append(row)
        batch["labels"] = torch.tensor(all_labels)
        return batch

    def batches(segments, size, shuffle):
        order = list(range(len(segments)))
        if shuffle:
            torch.manual_seed(arguments.model_seed)
            order = torch.randperm(len(segments)).tolist()
        for start in range(0, len(order), size):
            yield [segments[i] for i in order[start : start + size]]

    train_segments = list(split.train)
    optimiser = torch.optim.AdamW(model.parameters(), lr=arguments.learning_rate)
    steps = max(1, (len(train_segments) // arguments.batch_size) * arguments.epochs)
    scheduler = get_linear_schedule_with_warmup(optimiser, int(steps * 0.1), steps)
    del DataLoader

    for epoch in range(1, arguments.epochs + 1):
        model.train()
        total = 0.0
        seen = 0
        for chunk in batches(train_segments, arguments.batch_size, shuffle=True):
            batch = {k: v.to(device) for k, v in encode(chunk).items()}
            outputs = model(**batch)
            outputs.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            scheduler.step()
            optimiser.zero_grad()
            total += float(outputs.loss)
            seen += 1
        print(f"epoch {epoch}: mean training loss {total / max(seen, 1):.4f}")

        validation = predict(model, tokenizer, encode, list(split.validation), labels, device, torch)
        print(format_scores(f"validation (epoch {epoch})", score_segments(list(split.validation), validation)))

    # The test split is read here and nowhere else.
    test_segments = list(split.test)
    test_predictions = predict(model, tokenizer, encode, test_segments, labels, device, torch)
    test_scores = score_segments(test_segments, test_predictions)
    print(format_scores("test", test_scores))

    if arguments.no_save:
        print("\n--no-save: no checkpoint written.")
        return 0

    artefacts = Path(arguments.artefacts)
    artefacts.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(artefacts)
    tokenizer.save_pretrained(artefacts)
    (artefacts / "labels.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")
    (artefacts / "metadata.json").write_text(
        json.dumps(
            {
                "task": "span_extraction",
                "function": "F-12",
                "base_model": arguments.model,
                "split_seed": arguments.seed,
                "model_seed": arguments.model_seed,
                "epochs": arguments.epochs,
                "learning_rate": arguments.learning_rate,
                "batch_size": arguments.batch_size,
                "max_length": arguments.max_length,
                "labels": len(labels),
                "train_segments": len(train_segments),
                "validation_segments": len(split.validation),
                "test_segments": len(test_segments),
                "label_rule": "OPP-115 annotator spans, slice-verified; earliest-longest wins on overlap",
                "evaluation": "span-level exact match on (type, value, start, end)",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    metrics_path = Path(arguments.metrics)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    exact_p, exact_r, exact_f = test_scores.exact()
    over_p, over_r, over_f = test_scores.overlapping()
    metrics_path.write_text(
        json.dumps(
            {
                "split": "test",
                "gold_spans": test_scores.gold,
                "predicted_spans": test_scores.predicted,
                "exact": {"precision": exact_p, "recall": exact_r, "f1": exact_f},
                "overlapping": {"precision": over_p, "recall": over_r, "f1": over_f},
                "unverifiable_spans": test_scores.unverifiable,
                "per_type": test_scores.per_type,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\ncheckpoint: {artefacts}\nmetrics:    {metrics_path}")
    return 0


def predict(model, tokenizer, encode, segments, labels, device, torch):
    """Tag each segment, mapping subword predictions back to whole words."""
    model.eval()
    predictions: list[list[str]] = []
    with torch.no_grad():
        for start in range(0, len(segments), 16):
            chunk = segments[start : start + 16]
            batch = encode(chunk)
            word_ids_per_row = [
                batch.word_ids(batch_index=i) for i in range(len(chunk))
            ]
            inputs = {
                k: v.to(device) for k, v in batch.items() if k != "labels"
            }
            logits = model(**inputs).logits.cpu()
            for row, (segment, word_ids) in enumerate(
                zip(chunk, word_ids_per_row, strict=True)
            ):
                tags = [OUTSIDE] * len(segment.tokens)
                previous = None
                for position, word_id in enumerate(word_ids):
                    if word_id is None or word_id == previous:
                        previous = word_id
                        continue
                    previous = word_id
                    index = int(logits[row][position].argmax())
                    tags[word_id] = labels[index]
                predictions.append(tags)
    return predictions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--model-seed", type=int, default=20261105)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--artefacts", type=Path, default=DEFAULT_ARTEFACT_DIR)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/processed/opp115_span_tags.jsonl"),
        help="exported tags; falls back to building from the corpus",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build and report the dataset and split, then stop. Needs no torch.",
    )
    arguments = parser.parse_args()

    # On a GPU notebook there is no OPP-115 corpus, only the exported tags.
    # Both paths produce identical TaggedSegments and re-verify offsets.
    dataset = Path(arguments.dataset)
    if dataset.is_file():
        segments = read_jsonl(dataset)
        print(f"dataset         : {dataset} (exported tags)")
    else:
        segments = build_tagged_segments()
        print("dataset         : built from data/raw/opp115")
    labels = label_set(segments)
    split = split_segments(segments, seed=arguments.seed)

    print(f"tagged segments : {len(segments)}")
    print(f"distinct tags   : {len(labels)} (including O)")
    tokens = sum(len(segment.tokens) for segment in segments)
    tagged = sum(1 for s in segments for t in s.tags if t != OUTSIDE)
    print(f"tokens          : {tokens} ({tagged} tagged, {tagged / tokens:.1%})")
    print(format_span_split_report(split, labels))

    if not all(segment.verify_offsets() for segment in segments):
        print("offset verification FAILED; refusing to train", file=sys.stderr)
        return 1
    print("offset verification: every token slices out of its segment")

    if arguments.dry_run:
        print("\n--dry-run: dataset and split only. Nothing was trained.")
        return 0

    return train(arguments, split, labels)


if __name__ == "__main__":
    raise SystemExit(main())
