"""F-17 — build the candidate pairs that F-18 will judge (ALG-6).

For each Data Safety category the builder pairs what the declaration says with
what the policy appears to say. Three shapes of candidate come out:

* both sides present — the usual comparison;
* a declared line with no policy practice — the input to a possible
  Declared-not-in-policy verdict;
* a policy practice with no declared line — the input to a possible
  In-policy-not-declared verdict.

The one-sided candidates matter as much as the paired ones. A finding about
something that is missing cannot be produced from a pair that was never built.

Abstention is carried into the candidate by
``AlignmentCandidate.abstained_upstream``, which reads through to the policy
practice, so an uncertain practice cannot enter the comparison looking
confident.

Complexity: O(P x k) where P is the number of mapped practices and k the number
of declared lines in the same category.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from analysis.verdict.models import (
    AlignmentCandidate,
    DeclarationState,
    MappedPolicyPractice,
)
from analysis.vocabulary import DS_CATEGORIES


def build_candidates(
    declaration: dict[str, DeclarationState],
    mapped_practices: Sequence[MappedPolicyPractice],
    categories: Iterable[str] = DS_CATEGORIES,
) -> dict[str, tuple[AlignmentCandidate, ...]]:
    """Build candidates for every category.

    Every category in ``categories`` is present in the result, with an empty
    tuple where neither source mentions it. The verdict engine needs that
    entry: a category absent from both sources still receives a verdict, and an
    empty tuple is the evidence that nothing was found rather than the evidence
    that nothing was looked at.
    """
    by_category: dict[str, list[MappedPolicyPractice]] = {}
    for practice in mapped_practices:
        by_category.setdefault(practice.ds_category, []).append(practice)

    unknown = set(by_category) - set(categories)
    if unknown:
        raise ValueError(
            f"mapped practices reference categories outside the vocabulary: "
            f"{sorted(unknown)}"
        )

    candidates: dict[str, tuple[AlignmentCandidate, ...]] = {}
    for category in categories:
        state = declaration.get(category, DeclarationState(ds_category=category))
        candidates[category] = _build_for_category(
            category, state, by_category.get(category, [])
        )
    return candidates


def _build_for_category(
    category: str,
    state: DeclarationState,
    practices: Sequence[MappedPolicyPractice],
) -> tuple[AlignmentCandidate, ...]:
    asserted = [item for item in state.items if item.asserts_practice]

    # Neither source says anything. No candidate to build; the verdict engine
    # reads this as "neither source mentions the category".
    if not asserted and not practices:
        return ()

    # Policy statements with nothing declared against them.
    if not asserted:
        return tuple(
            AlignmentCandidate(ds_category=category, mapped_practice=practice)
            for practice in practices
        )

    # Declared, but no policy statement to compare against.
    if not practices:
        return tuple(
            AlignmentCandidate(ds_category=category, declared_item=item)
            for item in asserted
        )

    # Both sides present: every declared line against every policy practice in
    # the category. The verdict engine takes the strongest outcome, so each
    # pairing has to be offered rather than guessed at here.
    return tuple(
        AlignmentCandidate(
            ds_category=category, declared_item=item, mapped_practice=practice
        )
        for item in asserted
        for practice in practices
    )
