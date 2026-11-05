"""F-11 (improved) — encoder-based multi-label practice classifier.

**The M5 baseline is not touched.** `practice_classifier.py`, its artefact,
its split, its seed and its held-out results stay exactly as committed. This
is a second implementation evaluated against the **same** policy-grouped
split, so the comparison is fair; anything else would compare two experiments
rather than two models.

**The encoder is injected.** `EncoderBackend` is a protocol, so the
multi-label decision logic, the thresholding, the abstention behaviour and the
output shape are all testable without torch or a checkpoint. The
transformers-backed implementation lives in `ml/classifier_backend.py`, the
only place that imports torch.

**Nothing here has been trained.** The architecture, the training script and
the evaluation path exist; no encoder weights have been fitted and no
improved-model metric has been produced. `ml/train_improved_classifier.py`
runs the training where a checkpoint can be downloaded.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from analysis.verdict.models import PolicyPractice, PolicySegmentRef
from ml.data.opp115_schema import CATEGORIES

#: PROVISIONAL, and the same value the baseline reports at, so the two models
#: are compared at one operating point rather than at two.
DEFAULT_DECISION_THRESHOLD = 0.50


@dataclass(frozen=True)
class ImprovedClassifierConfig:
    """Training configuration, recorded so a run can be reproduced.

    The defaults fit the approved 8 GB constraint: a small encoder, a short
    sequence, a modest batch, CPU inference for the demonstration. They are
    starting values, not tuned results.
    """

    #: A small English encoder. Named here rather than hard-coded downstream
    #: so swapping it is a configuration change with a recorded value.
    model_identifier: str = "distilbert-base-uncased"
    max_sequence_length: int = 256
    batch_size: int = 16
    learning_rate: float = 3e-5
    epochs: int = 3
    random_seed: int = 20261105
    decision_threshold: float = DEFAULT_DECISION_THRESHOLD
    categories: tuple[str, ...] = field(default=CATEGORIES)

    def as_metadata(self) -> dict:
        return {
            "model_component": "classifier",
            "model_variant": "improved",
            "model_identifier": self.model_identifier,
            "max_sequence_length": self.max_sequence_length,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "epochs": self.epochs,
            "random_seed": self.random_seed,
            "decision_threshold": self.decision_threshold,
            "threshold_is_provisional": True,
            "category_count": len(self.categories),
        }


@dataclass(frozen=True)
class CategoryScore:
    """One category's score for one segment.

    There is deliberately **no abstention flag here**. F-14 owns that
    decision, exactly as it does for the M5 baseline; setting it in two places
    would put the rule in two places. `predict_practices` returns practices
    with ``abstained=False`` for the gate to decide on.
    """

    category: str
    probability: float
    predicted: bool

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError(f"probability {self.probability} is out of range")


class EncoderBackend(Protocol):
    """Produces one probability per category per segment.

    Returns probabilities in the order of `ImprovedClassifierConfig.categories`.
    """

    def predict_proba(self, texts: Sequence[str]) -> list[list[float]]:
        ...


class ImprovedPracticeClassifier:
    """F-11's improved variant: the same contract as the M5 baseline.

    Same inputs, same output shape, same confidence and abstention semantics,
    so the verdict pipeline cannot tell which variant produced a practice —
    which is what makes the two comparable and interchangeable.
    """

    def __init__(
        self,
        backend: EncoderBackend,
        config: ImprovedClassifierConfig | None = None,
    ) -> None:
        self._backend = backend
        self.config = config or ImprovedClassifierConfig()

    @property
    def categories(self) -> tuple[str, ...]:
        return self.config.categories

    def predict(self, texts: Sequence[str]) -> list[list[CategoryScore]]:
        """Score every category for every segment.

        **Every category is returned**, predicted or not. The verdict engine
        needs the score for a category the model rejected as much as for one
        it accepted: "the classifier looked and found nothing" and "the
        classifier was never asked" are different, and only the first can be
        read off a complete score vector.
        """
        if not texts:
            return []

        rows = self._backend.predict_proba(texts)
        if len(rows) != len(texts):
            raise ValueError(
                f"the backend returned {len(rows)} rows for {len(texts)} texts"
            )

        threshold = self.config.decision_threshold
        results: list[list[CategoryScore]] = []
        for row in rows:
            if len(row) != len(self.categories):
                raise ValueError(
                    f"the backend returned {len(row)} scores for "
                    f"{len(self.categories)} categories"
                )
            results.append(
                [
                    CategoryScore(
                        category=category,
                        probability=probability,
                        predicted=probability >= threshold,
                    )
                    for category, probability in zip(self.categories, row, strict=True)
                ]
            )
        return results

    def predict_labels(self, texts: Sequence[str]) -> list[tuple[str, ...]]:
        """Just the categories above threshold, for evaluation against gold."""
        return [
            tuple(score.category for score in row if score.predicted)
            for row in self.predict(texts)
        ]

    def predict_practices(
        self,
        segment: PolicySegmentRef,
        first_practice_id: int = 1,
        minimum_score: float = 0.0,
    ) -> list[PolicyPractice]:
        """The same contract as the M5 baseline's `predict_practices`.

        ``minimum_score`` is a candidate floor, not a decision threshold, and
        every practice comes back with ``abstained=False``: what to trust is
        F-14's decision. Matching the baseline's signature exactly is what
        lets the pipeline swap the two variants without noticing.
        """
        (scores,) = self.predict([segment.text]) or [[]]
        practices: list[PolicyPractice] = []
        practice_id = first_practice_id
        for score in scores:
            if score.probability < minimum_score:
                continue
            practices.append(
                PolicyPractice(
                    practice_id=practice_id,
                    segment=segment,
                    opp115_category=score.category,
                    confidence=score.probability,
                    abstained=False,
                )
            )
            practice_id += 1
        return practices


__all__ = [
    "DEFAULT_DECISION_THRESHOLD",
    "CategoryScore",
    "EncoderBackend",
    "ImprovedClassifierConfig",
    "ImprovedPracticeClassifier",
]
