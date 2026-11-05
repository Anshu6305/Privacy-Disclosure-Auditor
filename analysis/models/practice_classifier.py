"""F-11 baseline — multi-label data practice classification (ALG-2).

TF-IDF features with one-vs-rest logistic regression, exactly as the approved
Phase 3 design specifies for the baseline. One binary classifier per OPP-115
category, so a segment can carry several labels, which it usually must: a
sentence about sharing data with partners for advertising is both Third Party
Sharing/Collection and, often, User Choice/Control.

**On the numbers this returns.** ``predict_proba`` gives logistic regression's
output. That is a score between 0 and 1, and it is **not a calibrated
probability**: no calibration has been performed or tested, and class
weighting deliberately distorts the scores in favour of rare categories.
Treat them as rankable confidences, which is what F-14 needs, and not as
"the probability that this segment discusses retention".

**Interaction with F-14.** This module does no thresholding. It returns a
confidence for every category and lets :mod:`analysis.confidence.gate` decide
what to trust, because that is where the approved design puts the decision and
duplicating it here would create a second place for the rule to drift.

Complexity: O(|v|) per segment at inference, where |v| is the vocabulary size
touched by the segment — ALG-2's stated baseline cost.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis.verdict.models import PolicyPractice, PolicySegmentRef
from ml.data.opp115_schema import CATEGORIES

#: Fixed everywhere a seed is accepted, so a run is reproducible (NFR-08).
DEFAULT_RANDOM_SEED = 20261105


@dataclass(frozen=True)
class BaselineConfig:
    """Every tunable in one place, so a model records how it was built.

    The values are **provisional starting points**, not tuned results. Phase 3
    specifies the algorithm, not its hyperparameters.
    """

    max_features: int = 50_000
    ngram_min: int = 1
    ngram_max: int = 2
    min_df: int = 2
    sublinear_tf: bool = True
    lowercase: bool = True
    stop_words: str | None = None
    #: Inverse regularisation strength for logistic regression.
    C: float = 1.0
    max_iter: int = 2000
    #: "balanced" reweights by inverse class frequency. Without it the rare
    #: categories — Do Not Track has 31 positive segments in the whole corpus —
    #: are simply never predicted, because predicting "no" is right 99.2% of
    #: the time.
    class_weight: str | None = "balanced"
    random_seed: int = DEFAULT_RANDOM_SEED

    @property
    def ngram_range(self) -> tuple[int, int]:
        return (self.ngram_min, self.ngram_max)


@dataclass
class ModelMetadata:
    """What a saved model knows about its own provenance.

    Written beside the artefact so a result can be traced to the data, code
    and settings that produced it. Phase 3's model_version table records the
    same facts; persisting them there is F-34 and belongs to a later
    milestone.
    """

    component: str = "classifier"
    variant: str = "baseline"
    algorithm: str = "TF-IDF + OneVsRest LogisticRegression (ALG-2)"
    categories: list[str] = field(default_factory=lambda: list(CATEGORIES))
    config: dict[str, Any] = field(default_factory=dict)
    dataset_fingerprint: str | None = None
    dataset_description: str | None = None
    label_rule: str | None = None
    split_seed: int | None = None
    split_policies: dict[str, int] = field(default_factory=dict)
    split_segments: dict[str, int] = field(default_factory=dict)
    trained_at: str | None = None
    package_versions: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None


def package_versions() -> dict[str, str]:
    import sklearn

    versions = {"scikit-learn": sklearn.__version__}
    for name in ("numpy", "scipy", "joblib"):
        try:
            versions[name] = __import__(name).__version__
        except Exception:  # noqa: BLE001 - a missing version is not fatal
            versions[name] = "unknown"
    return versions


class BaselinePracticeClassifier:
    """The approved baseline for F-11."""

    def __init__(
        self,
        config: BaselineConfig | None = None,
        categories: list[str] | None = None,
    ) -> None:
        self.config = config or BaselineConfig()
        self.categories = list(categories or CATEGORIES)
        self.metadata = ModelMetadata(config=asdict(self.config))
        self._pipeline: Any | None = None

    # -- training ---------------------------------------------------------

    def _build(self) -> Any:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.multiclass import OneVsRestClassifier
        from sklearn.pipeline import Pipeline

        vectoriser = TfidfVectorizer(
            max_features=self.config.max_features,
            ngram_range=self.config.ngram_range,
            min_df=self.config.min_df,
            sublinear_tf=self.config.sublinear_tf,
            lowercase=self.config.lowercase,
            stop_words=self.config.stop_words,
        )
        classifier = OneVsRestClassifier(
            LogisticRegression(
                C=self.config.C,
                max_iter=self.config.max_iter,
                class_weight=self.config.class_weight,
                random_state=self.config.random_seed,
                solver="liblinear",
            )
        )
        return Pipeline([("tfidf", vectoriser), ("clf", classifier)])

    def fit(self, texts: list[str], label_sets: list[tuple[str, ...]]) -> None:
        """Train on segment texts and their label sets."""
        if len(texts) != len(label_sets):
            raise ValueError(
                f"{len(texts)} texts but {len(label_sets)} label sets"
            )
        if not texts:
            raise ValueError("cannot train on an empty dataset")

        unknown = {
            label
            for labels in label_sets
            for label in labels
            if label not in self.categories
        }
        if unknown:
            raise ValueError(f"labels outside the category set: {sorted(unknown)}")

        matrix = self._binarise(label_sets)

        # A category with no positive example cannot be learned. Say so rather
        # than letting scikit-learn fit a classifier that always answers no.
        absent = [
            category
            for index, category in enumerate(self.categories)
            if not any(row[index] for row in matrix)
        ]
        if absent:
            self.metadata.notes = (
                f"no positive training example for: {absent}. These categories "
                f"are present in the label space but were never learned."
            )

        self._pipeline = self._build()
        self._pipeline.fit(texts, matrix)
        self.metadata.trained_at = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        self.metadata.package_versions = package_versions()
        self.metadata.config = asdict(self.config)
        self.metadata.categories = list(self.categories)

    def _binarise(self, label_sets: list[tuple[str, ...]]) -> list[list[int]]:
        index = {category: i for i, category in enumerate(self.categories)}
        matrix = []
        for labels in label_sets:
            row = [0] * len(self.categories)
            for label in labels:
                row[index[label]] = 1
            matrix.append(row)
        return matrix

    # -- inference --------------------------------------------------------

    @property
    def is_fitted(self) -> bool:
        return self._pipeline is not None

    def _require_fitted(self) -> Any:
        if self._pipeline is None:
            raise RuntimeError(
                "the classifier has not been trained or loaded; call fit() or "
                "BaselinePracticeClassifier.load()"
            )
        return self._pipeline

    def predict_scores(self, texts: list[str]) -> list[dict[str, float]]:
        """Per-category confidence for each text.

        These are logistic-regression outputs, **not calibrated
        probabilities**. No calibration has been performed or tested.
        """
        pipeline = self._require_fitted()
        if not texts:
            return []

        probabilities = pipeline.predict_proba(texts)
        return [
            {
                category: float(row[index])
                for index, category in enumerate(self.categories)
            }
            for row in probabilities
        ]

    def predict_practices(
        self,
        segment: PolicySegmentRef,
        first_practice_id: int = 1,
        minimum_score: float = 0.0,
    ) -> list[PolicyPractice]:
        """F-11's output: practices with confidences, ready for F-14.

        ``minimum_score`` is a **candidate floor**, not a decision threshold.
        It exists only to avoid carrying ten near-zero scores per segment
        through the pipeline. The decision about what to trust is F-14's, and
        is deliberately not made here.

        Every returned practice has ``abstained=False``. Setting that flag is
        F-14's job; doing it here would put the rule in two places.
        """
        scores = self.predict_scores([segment.text])
        if not scores:
            return []

        practices = []
        practice_id = first_practice_id
        for category in self.categories:
            score = scores[0][category]
            if score < minimum_score:
                continue
            practices.append(
                PolicyPractice(
                    practice_id=practice_id,
                    segment=segment,
                    opp115_category=category,
                    confidence=score,
                    abstained=False,
                )
            )
            practice_id += 1
        return practices

    # -- persistence ------------------------------------------------------

    def save(self, directory: Path | str) -> Path:
        """Write the artefact and its metadata.

        The model loads from disk with no network access, which matters
        because a demonstration must not depend on anything being reachable.
        """
        import joblib

        pipeline = self._require_fitted()
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        model_path = directory / "model.joblib"
        joblib.dump(pipeline, model_path)

        (directory / "metadata.json").write_text(
            json.dumps(asdict(self.metadata), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return model_path

    @classmethod
    def load(cls, directory: Path | str) -> BaselinePracticeClassifier:
        import joblib

        directory = Path(directory)
        model_path = directory / "model.joblib"
        metadata_path = directory / "metadata.json"

        if not model_path.is_file():
            raise FileNotFoundError(
                f"no model at {model_path}. Train one with "
                f"ml/train_baseline_classifier.py."
            )

        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        config_fields = BaselineConfig.__dataclass_fields__
        config = BaselineConfig(
            **{k: v for k, v in raw.get("config", {}).items() if k in config_fields}
        )

        model = cls(config=config, categories=raw.get("categories"))
        model._pipeline = joblib.load(model_path)
        model.metadata = ModelMetadata(**raw)
        return model
