"""F-14 — confidence thresholding and abstention (ALG-4).

The gate decides whether a prediction is trusted. It never deletes anything: a
prediction below threshold is returned with ``abstained=True`` so the
uncertainty can travel through F-15, F-17 and F-18 and end as Undetermined
rather than being mistaken for a confident absence.

Complexity: O(1) per prediction, O(n) over n predictions.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace

from analysis.verdict.models import PolicyPractice


def is_abstention(confidence: float, threshold: float) -> bool:
    """Whether a prediction falls below the trust threshold (ALG-4).

    The comparison is strict: a confidence exactly equal to the threshold is
    accepted. The boundary has to fall on one side or the other, and stating
    which here keeps it out of every call site.
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence {confidence} is not a probability")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold {threshold} is not a probability")
    return confidence < threshold


def apply_threshold(practice: PolicyPractice, threshold: float) -> PolicyPractice:
    """Return the practice with its abstention flag set from the threshold.

    Abstention is sticky. A practice already marked abstained upstream stays
    abstained even if this threshold would accept it, because the reason it was
    flagged earlier has not gone away.
    """
    abstained = practice.abstained or is_abstention(practice.confidence, threshold)
    return replace(practice, abstained=abstained)


def apply_threshold_to_all(
    practices: Iterable[PolicyPractice], threshold: float
) -> tuple[PolicyPractice, ...]:
    """Apply the gate to every practice, keeping all of them.

    The returned tuple is the same length as the input. Nothing is filtered
    out; that is the whole point of the design.
    """
    return tuple(apply_threshold(practice, threshold) for practice in practices)


def abstention_rate(practices: Sequence[PolicyPractice]) -> float:
    """Share of practices that were abstained.

    Reported alongside every evaluation result, because a model that abstains
    on most of its input can look accurate on the remainder while being of
    little practical use.
    """
    if not practices:
        return 0.0
    return sum(1 for practice in practices if practice.abstained) / len(practices)
