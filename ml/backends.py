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
from analysis.models.improved_classifier import ImprovedClassifierConfig
from analysis.models.span_extractor import TaggedToken

#: An NLI-pretrained encoder, used zero-shot for F-18 (decision D-01, Option
#: A). Small enough for CPU inference on the 8 GB machine.
DEFAULT_NLI_MODEL = "cross-encoder/nli-distilroberta-base"

#: Where a checkpoint downloaded elsewhere is expected, mirroring F-12's
#: `ml/checkpoints/span-extractor-v1`. Preferred over the hub identifier when
#: it exists: the project is offline-first, and an audit should not depend on
#: a network call at the moment it runs.
LOCAL_NLI_CHECKPOINT = Path("ml/checkpoints/nli-mnli-v1")

#: The order a model's NLI head emits. Checked against the loaded model's
#: `id2label` rather than assumed, because a mismatch would silently swap
#: entailment and contradiction — turning SUPPORTS into CONTRADICTS.
EXPECTED_NLI_LABELS = {"entailment", "neutral", "contradiction"}


def model_inputs(model, encoded) -> dict:
    """Keep only the tokenizer outputs this model's `forward` accepts.

    `distilbert-base-uncased` ships a tokenizer config that declares
    `BertTokenizer`, so a checkpoint saved from it loads as `BertTokenizerFast`
    and emits `token_type_ids`. DistilBERT's `forward` has no such parameter and
    raises ``TypeError: forward() got an unexpected keyword argument
    'token_type_ids'``. Filtering against the real signature keeps one backend
    working across encoder families instead of hard-coding one family's inputs.
    """
    import inspect

    accepted = inspect.signature(model.forward).parameters
    return {key: value for key, value in encoded.items() if key in accepted}


def resolve_nli_label_indices(id2label: dict) -> dict[str, int]:
    """Map each NLI class name to the output index that carries it.

    Read from the model's own configuration, never assumed. Heads differ:
    some emit contradiction first, some entailment first, and the names vary
    in case and in prefixes such as ``LABEL_``. Getting this wrong would swap
    SUPPORTS and CONTRADICTS on every pair while the system looked entirely
    healthy — a silent inversion of every verdict the aligner produces.

    Separated from the backend so it can be tested against real `id2label`
    dictionaries without downloading a model.
    """
    index_for: dict[str, int] = {}
    for index, label in id2label.items():
        name = str(label).strip().lower()
        if name in EXPECTED_NLI_LABELS:
            index_for[name] = int(index)

    missing = EXPECTED_NLI_LABELS - set(index_for)
    if missing:
        raise ValueError(
            f"the model does not expose the NLI labels {sorted(missing)}; its "
            f"head is {id2label}. F-18 needs entailment, neutral and "
            "contradiction, and will not guess which index is which."
        )
    if len(set(index_for.values())) != 3:
        raise ValueError(
            f"two NLI labels share an output index in {id2label}; the head "
            "cannot be interpreted."
        )
    return index_for


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

    def __init__(self, model_identifier: str | Path | None = None, batch_size: int = 8):
        torch, transformers = _require_transformers()
        self._torch = torch

        # A local checkpoint wins when present. The hub identifier remains
        # the fallback so a machine with network access still works, but an
        # audit on an offline machine must not fail for want of a download.
        if model_identifier is None:
            model_identifier = (
                LOCAL_NLI_CHECKPOINT
                if LOCAL_NLI_CHECKPOINT.is_dir()
                else DEFAULT_NLI_MODEL
            )
        source = str(model_identifier)

        self._tokenizer = transformers.AutoTokenizer.from_pretrained(source)
        self._model = transformers.AutoModelForSequenceClassification.from_pretrained(
            source
        )
        self._model.eval()
        self.batch_size = batch_size
        self.model_identifier = source

        self._index_for = resolve_nli_label_indices(self._model.config.id2label)

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
        # Tokenise exactly as the training and evaluation runs did, from one
        # source of truth. Dynamic padding would be mathematically equivalent
        # given the attention mask, but the probabilities this backend serves
        # are the ones the reported metrics describe, so the settings should
        # not be able to drift apart.
        self.max_length = ImprovedClassifierConfig().max_sequence_length

    def predict_proba(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        torch = self._torch
        rows: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            encoded = self._tokenizer(
                batch,
                padding="max_length",
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            )
            with torch.no_grad():
                logits = self._model(**model_inputs(self._model, encoded)).logits
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
