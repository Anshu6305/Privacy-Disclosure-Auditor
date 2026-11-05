"""Transformers-backed implementations of the three M6 model protocols.

**This is the only module that imports torch or transformers**, and it does so
inside functions. Everything in `analysis/` works against the protocols, so
the suite runs — and the decision logic is tested — without the 2 GB
dependency set installed.

Install with ``pip install -r backend/requirements-ml.txt``. The checkpoints
are downloaded from the Hugging Face hub on first use, which needs network
access; see `docs/M6_REPORT.md` for where that can and cannot be done.

Memory: the defaults are chosen for the approved 8 GB constraint — small
encoders, short sequences, CPU inference, and models loaded one at a time.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from analysis.alignment.nli import NliPrediction
from analysis.models.span_extractor import TaggedToken

#: An NLI-pretrained encoder, used zero-shot for F-18 (decision D-01, Option
#: A). Small enough for CPU inference on the 8 GB machine.
DEFAULT_NLI_MODEL = "cross-encoder/nli-distilroberta-base"

#: The order a model's NLI head emits. Checked against the loaded model's
#: `id2label` rather than assumed, because a mismatch would silently swap
#: entailment and contradiction — turning SUPPORTS into CONTRADICTS.
EXPECTED_NLI_LABELS = {"entailment", "neutral", "contradiction"}


def _require_transformers():
    try:
        import torch
        import transformers
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "The improved models need torch and transformers, which are not "
            "installed. Run: pip install -r backend/requirements-ml.txt\n"
            "The baseline classifier, the verdict engine, the API and the "
            "database all run without them."
        ) from exc
    return torch, transformers


class TransformersNliBackend:
    """F-18's zero-shot NLI scorer."""

    def __init__(self, model_identifier: str = DEFAULT_NLI_MODEL, batch_size: int = 8):
        torch, transformers = _require_transformers()
        self._torch = torch
        self._tokenizer = transformers.AutoTokenizer.from_pretrained(model_identifier)
        self._model = transformers.AutoModelForSequenceClassification.from_pretrained(
            model_identifier
        )
        self._model.eval()
        self.batch_size = batch_size
        self.model_identifier = model_identifier

        # The label order is read from the model, never assumed. Swapping
        # entailment and contradiction would invert every verdict while
        # looking entirely healthy.
        self._index_for = {
            label.lower(): index
            for index, label in self._model.config.id2label.items()
        }
        missing = EXPECTED_NLI_LABELS - set(self._index_for)
        if missing:
            raise ValueError(
                f"{model_identifier} does not expose the NLI labels "
                f"{sorted(missing)}; its head is {self._model.config.id2label}. "
                "F-18 needs entailment, neutral and contradiction."
            )

    def predict(self, pairs: Sequence[tuple[str, str]]) -> list[NliPrediction]:
        if not pairs:
            return []
        torch = self._torch
        predictions: list[NliPrediction] = []
        for start in range(0, len(pairs), self.batch_size):
            batch = pairs[start : start + self.batch_size]
            encoded = self._tokenizer(
                [premise for premise, _ in batch],
                [hypothesis for _, hypothesis in batch],
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="pt",
            )
            with torch.no_grad():
                logits = self._model(**encoded).logits
            probabilities = torch.softmax(logits, dim=-1)
            for row in probabilities:
                predictions.append(
                    NliPrediction(
                        entailment=float(row[self._index_for["entailment"]]),
                        neutral=float(row[self._index_for["neutral"]]),
                        contradiction=float(row[self._index_for["contradiction"]]),
                    )
                )
        return predictions


class TransformersClassifierBackend:
    """F-11 improved: a fine-tuned multi-label encoder."""

    def __init__(self, checkpoint: Path | str, batch_size: int = 16):
        torch, transformers = _require_transformers()
        self._torch = torch
        checkpoint = Path(checkpoint)
        if not checkpoint.is_dir():
            raise FileNotFoundError(
                f"{checkpoint} does not exist. Train the improved classifier "
                "first: python ml/train_improved_classifier.py"
            )
        self._tokenizer = transformers.AutoTokenizer.from_pretrained(str(checkpoint))
        self._model = transformers.AutoModelForSequenceClassification.from_pretrained(
            str(checkpoint)
        )
        self._model.eval()
        self.batch_size = batch_size

    def predict_proba(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        torch = self._torch
        rows: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            encoded = self._tokenizer(
                batch, padding=True, truncation=True, max_length=256, return_tensors="pt"
            )
            with torch.no_grad():
                logits = self._model(**encoded).logits
            # Sigmoid, not softmax: the task is multi-label, so a segment can
            # describe several practices at once.
            for row in torch.sigmoid(logits):
                rows.append([float(value) for value in row])
        return rows


class TransformersSpanBackend:
    """F-12: a fine-tuned token classifier emitting BIO tags."""

    def __init__(self, checkpoint: Path | str, batch_size: int = 8):
        torch, transformers = _require_transformers()
        self._torch = torch
        checkpoint = Path(checkpoint)
        if not checkpoint.is_dir():
            raise FileNotFoundError(
                f"{checkpoint} does not exist. Train the span extractor "
                "first: python ml/train_span_extractor.py"
            )
        self._tokenizer = transformers.AutoTokenizer.from_pretrained(str(checkpoint))
        self._model = transformers.AutoModelForTokenClassification.from_pretrained(
            str(checkpoint)
        )
        self._model.eval()
        self.batch_size = batch_size
        self._label_for = self._model.config.id2label

    def tag(self, tokens: Sequence[tuple[str, int, int]]) -> list[TaggedToken]:
        if not tokens:
            return []
        torch = self._torch
        words = [token for token, _start, _end in tokens]
        encoded = self._tokenizer(
            [words],
            is_split_into_words=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = self._model(**encoded).logits
        probabilities = torch.softmax(logits, dim=-1)[0]
        word_ids = encoded.word_ids(0)

        # The first sub-token of each word carries the word's tag. Averaging
        # across sub-tokens would blur a B- into an I-.
        tagged: list[TaggedToken] = []
        seen: set[int] = set()
        for position, word_index in enumerate(word_ids):
            if word_index is None or word_index in seen:
                continue
            seen.add(word_index)
            row = probabilities[position]
            best = int(torch.argmax(row))
            token, start, end = tokens[word_index]
            tagged.append(
                TaggedToken(
                    token=token,
                    start=start,
                    end=end,
                    tag=self._label_for[best],
                    confidence=float(row[best]),
                )
            )

        # Words truncated away keep a token each, tagged O with zero
        # confidence, so the caller still gets one tag per token rather than a
        # silently shortened sequence.
        for index in range(len(tagged), len(tokens)):
            token, start, end = tokens[index]
            tagged.append(TaggedToken(token, start, end, "O", 0.0))
        return tagged


__all__ = [
    "DEFAULT_NLI_MODEL",
    "TransformersClassifierBackend",
    "TransformersNliBackend",
    "TransformersSpanBackend",
]
