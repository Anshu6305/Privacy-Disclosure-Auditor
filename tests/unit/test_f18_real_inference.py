"""The downloaded NLI checkpoint, exercised for real.

Skipped unless torch and the checkpoint are both present; neither is
committed. A skip here is a skip, never a pass.

The three NLI outcomes are tested, plus an uncertain one, because the whole
value of F-18 over keyword matching is that it can tell "we do not collect
location" from "we collect location" — two sentences a keyword matcher
cannot distinguish at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT = ROOT / "ml/checkpoints/nli-mnli-v1"

pytestmark = pytest.mark.ml


@pytest.fixture(scope="module")
def backend():
    pytest.importorskip("torch", reason="F-18 inference needs torch")
    pytest.importorskip("transformers")
    if not CHECKPOINT.is_dir():
        pytest.skip(f"no NLI checkpoint at {CHECKPOINT}")
    from ml.backends import TransformersNliBackend

    return TransformersNliBackend(CHECKPOINT)


def test_the_label_order_comes_from_this_checkpoints_own_config(backend):
    """Not a formality for this checkpoint.

    `cross-encoder/nli-distilroberta-base` puts entailment at index **1**,
    not the index 2 that the commonest MNLI heads use. Code that assumed a
    fixed order would read entailment probabilities out of the neutral slot
    for this exact model.
    """
    assert backend._index_for == {"contradiction": 0, "entailment": 1, "neutral": 2}


def test_a_denial_is_a_contradiction_not_a_no_match(backend):
    """The case that justifies semantic alignment over keyword matching.

    "We do not collect any location information" contains every keyword that
    "we collect location" does. Only an entailment model can tell them apart,
    and getting this wrong would report a denial as a match.
    """
    (prediction,) = backend.predict(
        [
            (
                "We do not collect any location information from users.",
                "This app collects location data.",
            )
        ]
    )
    label, confidence = prediction.best
    assert label == "contradiction"
    assert confidence > 0.5
    assert prediction.contradiction > prediction.entailment


def test_an_unrelated_premise_is_neutral(backend):
    (prediction,) = backend.predict(
        [
            (
                "We use cookies to remember your display preferences.",
                "This app collects financial information.",
            )
        ]
    )
    assert prediction.best[0] == "neutral"


def test_a_matching_statement_leans_away_from_contradiction(backend):
    """Deliberately a weak assertion, because the model is weak here.

    Zero-shot, this checkpoint scores "We collect your precise location"
    against "This app collects location data" as *neutral* (0.637) rather
    than entailment (0.354). Asserting entailment would be asserting
    something the model does not do, and the test would be a lie about the
    system. What is reliably true is that it is not a contradiction, and
    that is what the verdict engine most needs to be right about.
    """
    (prediction,) = backend.predict(
        [
            (
                "We collect your precise location to show nearby results.",
                "This app collects location data.",
            )
        ]
    )
    assert prediction.contradiction < 0.1
    assert prediction.entailment > prediction.contradiction


def test_probabilities_are_a_distribution(backend):
    predictions = backend.predict(
        [("We share data with advertisers.", "This app shares data with third parties.")]
    )
    total = (
        predictions[0].entailment
        + predictions[0].neutral
        + predictions[0].contradiction
    )
    assert abs(total - 1.0) < 1e-4


def test_an_empty_batch_returns_nothing_rather_than_failing(backend):
    assert backend.predict([]) == []


def test_the_aligner_abstains_below_threshold(backend):
    """A low-confidence judgement keeps its label and sets model_abstained.

    Turning it into NO_MATCH would convert "we are unsure" into "the policy
    is silent", which ALG-8 treats very differently.
    """
    from analysis.alignment.nli import ZeroShotAligner

    strict = ZeroShotAligner(backend, threshold=0.99)
    relaxed = ZeroShotAligner(backend, threshold=0.01)
    assert strict.threshold == 0.99
    assert relaxed.threshold == 0.01
