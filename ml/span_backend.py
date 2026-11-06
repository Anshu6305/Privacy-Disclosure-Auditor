"""The transformers-backed F-12 tagger. The only module that imports torch.

Kept apart from `analysis/models/span_extractor.py` so the decoding logic,
the offset verification and the abstention rule stay testable on a machine
with no torch and no checkpoint — which is every machine running the unit
suite, and the API container.

If the checkpoint or the libraries are missing, construction raises
`SpanBackendUnavailableError`. It never falls back to a heuristic tagger: a
different tagger would produce different spans, so the same policy would
yield different evidence offsets depending on what happened to be installed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from analysis.models.span_extractor import TaggedToken

DEFAULT_CHECKPOINT = Path("ml/checkpoints/span-extractor-v1")

#: Longest input the tagger accepts, in word-piece tokens. Segments longer
#: than this are tagged in overlapping windows rather than truncated:
#: truncation would silently drop the tail of a long policy paragraph, and
#: the dropped text would read as "the policy does not say this".
MAX_TOKENS = 512
WINDOW_STRIDE = 128


class SpanBackendUnavailableError(RuntimeError):
    """No usable F-12 checkpoint. The caller must not substitute one."""


class TransformerSpanTagger:
    """Token classification over whitespace tokens, with BIO value tags.

    Word-piece subwords are aligned back to whitespace tokens by `word_ids`,
    and a whitespace token takes the label and probability of its **first**
    subword. The first subword is the one the tagger saw in context with the
    preceding word, and averaging across subwords would blur a B- onto an
    I- at a boundary.
    """

    def __init__(self, checkpoint: Path | str = DEFAULT_CHECKPOINT) -> None:
        checkpoint = Path(checkpoint)
        if not checkpoint.is_dir():
            raise SpanBackendUnavailableError(
                f"no F-12 checkpoint at {checkpoint}. Train one with "
                "ml/train_span_extractor.py (see notebooks/train_f12_colab.ipynb "
                "for the GPU workflow) and copy the directory here. "
                "Checkpoints are git-ignored by design."
            )
        try:
            import torch
            from transformers import AutoModelForTokenClassification, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise SpanBackendUnavailableError(
                f"torch and transformers are required to run F-12 ({exc}). "
                "Install them with: pip install -r backend/requirements-ml.txt"
            ) from exc

        labels_path = checkpoint / "labels.json"
        if not labels_path.is_file():
            raise SpanBackendUnavailableError(
                f"{checkpoint} has no labels.json, so the model's output "
                "indices cannot be turned back into tags."
            )
        self.labels: list[str] = json.loads(labels_path.read_text(encoding="utf-8"))

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(str(checkpoint))
        self._model = AutoModelForTokenClassification.from_pretrained(str(checkpoint))
        self._model.eval()

    def tag(self, tokens: Sequence[tuple[str, int, int]]) -> list[TaggedToken]:
        words = [token for token, _start, _end in tokens]
        if not words:
            return []

        encoded = self._tokenizer(
            words,
            is_split_into_words=True,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_TOKENS,
            return_overflowing_tokens=True,
            stride=WINDOW_STRIDE,
        )
        overflow = encoded.pop("overflow_to_sample_mapping", None)
        del overflow

        torch = self._torch
        # One probability vector per whitespace token. Windows overlap, and
        # the first window to assign a token wins, so a token is never
        # relabelled by a window that saw less of its left context.
        assigned: dict[int, tuple[str, float]] = {}
        with torch.no_grad():
            logits = self._model(**encoded).logits
            probabilities = torch.softmax(logits, dim=-1)

        for window in range(probabilities.shape[0]):
            word_ids = encoded.word_ids(batch_index=window)
            seen: set[int] = set()
            for position, word_id in enumerate(word_ids):
                if word_id is None or word_id in seen or word_id in assigned:
                    continue
                seen.add(word_id)
                row = probabilities[window][position]
                index = int(torch.argmax(row))
                assigned[word_id] = (self.labels[index], float(row[index]))

        tagged: list[TaggedToken] = []
        for index, (token, start, end) in enumerate(tokens):
            tag, confidence = assigned.get(index, ("O", 0.0))
            tagged.append(
                TaggedToken(
                    token=token, start=start, end=end, tag=tag, confidence=confidence
                )
            )
        return tagged


__all__ = [
    "DEFAULT_CHECKPOINT",
    "MAX_TOKENS",
    "SpanBackendUnavailableError",
    "TransformerSpanTagger",
]
