"""F-18 — zero-shot semantic alignment, the approved Option A path.

Decision D-01 approved Option A: an **NLI-pretrained encoder used zero-shot**
as the baseline, with fine-tuning on 300 to 500 manually labelled
policy-statement / Data Safety-claim pairs *if and when* those annotations
exist. They do not. Nothing here is fine-tuned, and nothing here pretends to
be.

**The framing.** Natural language inference asks whether a hypothesis follows
from a premise. The approved mapping is:

* **premise** — the policy sentence, verbatim, as F-09 segmented it;
* **hypothesis** — a sentence stating the Data Safety claim for one category.

The three NLI outputs map onto the three approved alignment labels:

======================  ==================  ====================================
NLI                     Alignment           Meaning
======================  ==================  ====================================
entailment              ``SUPPORTS``        the policy says what the app declares
contradiction           ``CONTRADICTS``     the policy says the opposite
neutral                 ``NO_MATCH``        the policy does not address it
======================  ==================  ====================================

**Abstention is not a fourth label.** A judgement below the configured
threshold keeps its label and sets ``model_abstained``; `AlignmentJudgement`
then ORs that with the candidate's upstream uncertainty. Turning a low
confidence into ``NO_MATCH`` would convert "we are unsure" into "the policy is
silent", which ALG-8 treats very differently.

**The model is injected.** `NliBackend` is a protocol so the alignment logic is
testable without a checkpoint, and so the encoder can be swapped without
touching this file. The transformers-backed implementation lives in
`ml/alignment_backend.py`, which is the only place that imports torch.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from analysis.verdict.models import AlignmentCandidate, AlignmentJudgement
from analysis.vocabulary import ALIGN_CONTRADICTS, ALIGN_NO_MATCH, ALIGN_SUPPORTS

#: NLI class -> approved alignment label. Fixed by the Phase 3 design; a model
#: whose head uses different names is adapted in its backend, not here.
NLI_TO_ALIGNMENT: dict[str, str] = {
    "entailment": ALIGN_SUPPORTS,
    "contradiction": ALIGN_CONTRADICTS,
    "neutral": ALIGN_NO_MATCH,
}

NLI_CLASSES: tuple[str, ...] = ("entailment", "neutral", "contradiction")


@dataclass(frozen=True)
class NliPrediction:
    """One premise/hypothesis scoring. Probabilities over :data:`NLI_CLASSES`."""

    entailment: float
    neutral: float
    contradiction: float

    def __post_init__(self) -> None:
        for name in NLI_CLASSES:
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} probability {value} is out of range")

    @property
    def best(self) -> tuple[str, float]:
        scored = ((name, getattr(self, name)) for name in NLI_CLASSES)
        return max(scored, key=lambda pair: pair[1])


class NliBackend(Protocol):
    """Scores premise/hypothesis pairs. Implemented in `ml/alignment_backend.py`."""

    def predict(self, pairs: Sequence[tuple[str, str]]) -> list[NliPrediction]:
        ...


# ---------------------------------------------------------------------------
# Hypothesis construction
# ---------------------------------------------------------------------------


def build_hypothesis(ds_category: str, *, collected: bool, shared: bool) -> str:
    """State one Data Safety claim as a sentence an NLI model can judge.

    Plain declaratives, because that is what NLI models are trained on. The
    category name is inserted verbatim rather than reworded, so the hypothesis
    says what the declaration says.
    """
    category = ds_category.strip()
    if not category:
        raise ValueError("a Data Safety category is required")

    if collected and shared:
        return f"This app collects {category} and shares it with third parties."
    if collected:
        return f"This app collects {category}."
    if shared:
        return f"This app shares {category} with third parties."
    # The declaration names the category and denies both actions. Phrasing it
    # positively and relying on CONTRADICTS would invert the judgement.
    return f"This app does not collect or share {category}."


def build_pair(candidate: AlignmentCandidate) -> tuple[str, str] | None:
    """Premise and hypothesis for one candidate, or None when there is nothing
    to compare.

    A candidate with no policy practice has no premise: the comparison is
    between a declaration and silence, which is F-21's absence case rather
    than an alignment question. Returning None keeps that decision with the
    verdict engine instead of inventing a premise here.
    """
    practice = candidate.mapped_practice
    if practice is None:
        return None
    premise = (practice.segment.text if practice.segment is not None else "").strip()
    if not premise:
        return None

    declared = candidate.declared_item
    hypothesis = build_hypothesis(
        candidate.ds_category,
        collected=bool(declared.is_collected) if declared is not None else True,
        shared=bool(declared.is_shared) if declared is not None else False,
    )
    return premise, hypothesis


# ---------------------------------------------------------------------------
# The aligner
# ---------------------------------------------------------------------------


class ZeroShotAligner:
    """F-18 via an NLI-pretrained encoder, used zero-shot.

    ``threshold`` is the confidence below which a judgement is marked
    abstained. It is **provisional**: Phase 3 names the threshold and sets no
    value, and this one has not been tuned on a gold set because no gold set
    exists.
    """

    def __init__(self, backend: NliBackend, threshold: float = 0.50) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold {threshold} is not a probability")
        self._backend = backend
        self.threshold = threshold

    def judge(self, candidates: Sequence[AlignmentCandidate]) -> list[AlignmentJudgement]:
        """One judgement per candidate, in the order given.

        Candidates with no premise are judged ``NO_MATCH`` with zero
        confidence **and** ``model_abstained=True``: the model was never
        consulted, so a confident NO_MATCH would be a claim nobody made.
        """
        pairs: list[tuple[str, str]] = []
        indices: list[int] = []
        for index, candidate in enumerate(candidates):
            pair = build_pair(candidate)
            if pair is not None:
                pairs.append(pair)
                indices.append(index)

        predictions = self._backend.predict(pairs) if pairs else []
        if len(predictions) != len(pairs):
            raise ValueError(
                f"the backend returned {len(predictions)} predictions for "
                f"{len(pairs)} pairs"
            )

        scored: dict[int, NliPrediction] = dict(zip(indices, predictions, strict=True))
        judgements: list[AlignmentJudgement] = []
        for index, candidate in enumerate(candidates):
            prediction = scored.get(index)
            if prediction is None:
                judgements.append(
                    AlignmentJudgement(
                        candidate=candidate,
                        label=ALIGN_NO_MATCH,
                        confidence=0.0,
                        model_abstained=True,
                    )
                )
                continue

            nli_class, confidence = prediction.best
            judgements.append(
                AlignmentJudgement(
                    candidate=candidate,
                    label=NLI_TO_ALIGNMENT[nli_class],
                    confidence=confidence,
                    # Label preserved, uncertainty flagged. Rewriting a
                    # low-confidence judgement as NO_MATCH would turn "unsure"
                    # into "the policy is silent".
                    model_abstained=confidence < self.threshold,
                )
            )
        return judgements


__all__ = [
    "NLI_CLASSES",
    "NLI_TO_ALIGNMENT",
    "NliBackend",
    "NliPrediction",
    "ZeroShotAligner",
    "build_hypothesis",
    "build_pair",
]
