"""F-19 — assign a verdict to each Data Safety category (ALG-8).

ALG-8 is an ordered sequence of five rules. The order is the algorithm: the
same set of judgements produces different verdicts under a different order, so
the steps are written out one at a time and in sequence rather than collapsed
into a single expression.

    Step 1  Contradiction.      Any trusted CONTRADICTS       -> Contradictory
    Step 2  Decisive support,   Any trusted SUPPORTS, and
            resolved against      - the category is declared   -> Consistent
            the declaration        - it is not declared        -> In-policy-not-declared
    Step 3  Abstention.         Any abstained judgement       -> Undetermined
    Step 4  Absence.            Declared, nothing found       -> Declared-not-in-policy
    Step 5  Neither source      Not declared, nothing found   -> Consistent
            mentions it.

Two points about the order, because they are the ones a reviewer will ask
about.

**Why contradiction comes first.** A policy can both assert and deny a practice
in different sections. When that happens the disagreement is the finding, and
reporting Consistent because a supporting sentence was also present would hide
it.

**Why abstention comes before absence.** This is the rule that stops an
uncertain reading from becoming a confident claim. If the system was unsure
about the only policy statement that might have matched, it cannot then report
that the policy does not mention the category: the statement might have
matched. Step 3 sits above step 4 so that case ends as Undetermined, which is
an admission of uncertainty, rather than Declared-not-in-policy, which is an
assertion about the policy's contents.

**Verdict confidence.** F-19 processing step 3 requires the verdict to carry
the confidence of the judgement that determined it, and for an Undetermined
verdict the highest sub-threshold confidence instead. The helper
``_deciding_confidence`` below implements that, and each step passes the class
of judgements that triggered it. Confidence is None only where no judgement
determined anything; it is never invented to fill the field.

Complexity: O(J) over the judgements in a category, O(C x J) over all
categories.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from analysis.verdict.absence_recorder import record_absence
from analysis.verdict.evidence_selector import select_evidence
from analysis.verdict.inconclusive_recorder import record_inconclusive
from analysis.verdict.models import (
    AlignmentJudgement,
    CategoryVerdict,
    DeclarationState,
)
from analysis.vocabulary import (
    DS_CATEGORIES,
    VERDICT_CONSISTENT,
    VERDICT_CONTRADICTORY,
    VERDICT_DECLARED_NOT_IN_POLICY,
    VERDICT_IN_POLICY_NOT_DECLARED,
    VERDICT_UNDETERMINED,
)


def _deciding_confidence(
    judgements: Sequence[AlignmentJudgement],
) -> float | None:
    """Highest confidence among the judgements that decided the verdict.

    F-19 step 3 calls this "the judgement that determined the outcome". Where
    several judgements of the same class are present, the strongest is the one
    the verdict rests on, which is also the one F-20 quotes first.

    Returns None for an empty sequence, which is the case where nothing
    determined the verdict and there is no confidence to report.
    """
    if not judgements:
        return None
    return max(judgement.confidence for judgement in judgements)


def assign_category_verdict(
    ds_category: str,
    declaration: DeclarationState,
    judgements: Sequence[AlignmentJudgement],
    max_evidence: int = 3,
) -> CategoryVerdict:
    """Apply ALG-8 to one category.

    ``judgements`` are produced by F-18, which is Milestone 6 work. This
    function does not create, score or guess a judgement; it only reads the
    ones it is given.
    """
    for judgement in judgements:
        if judgement.ds_category != ds_category:
            raise ValueError(
                f"judgement for {judgement.ds_category!r} passed to "
                f"{ds_category!r}"
            )

    declared = declaration.declared

    contradictions = [j for j in judgements if j.is_decisive_contradiction]
    supports = [j for j in judgements if j.is_decisive_support]
    abstentions = [j for j in judgements if j.abstained]

    # ``found_in_policy`` is set explicitly in each branch below rather than
    # computed once here, because its value is part of what each step means. It
    # is true only on trusted evidence: an abstained judgement never
    # establishes that the policy mentions a category, whatever label it
    # carries.
    abstention_involved = bool(abstentions)

    # --- Step 1: contradiction wins outright ------------------------------
    if contradictions:
        return CategoryVerdict(
            ds_category=ds_category,
            verdict=VERDICT_CONTRADICTORY,
            declared=declared,
            found_in_policy=True,
            abstention_involved=abstention_involved,
            confidence=_deciding_confidence(contradictions),
            records=select_evidence(contradictions, max_records=max_evidence),
        )

    # --- Step 2: decisive support, resolved against the declaration -------
    if supports:
        if declared:
            # Both sources assert the practice: affirmative agreement. A
            # Consistent verdict carries no evidence record (F-23).
            return CategoryVerdict(
                ds_category=ds_category,
                verdict=VERDICT_CONSISTENT,
                declared=True,
                found_in_policy=True,
                abstention_involved=abstention_involved,
                confidence=_deciding_confidence(supports),
                records=(),
            )

        return CategoryVerdict(
            ds_category=ds_category,
            verdict=VERDICT_IN_POLICY_NOT_DECLARED,
            declared=False,
            found_in_policy=True,
            abstention_involved=abstention_involved,
            confidence=_deciding_confidence(supports),
            records=select_evidence(supports, max_records=max_evidence),
        )

    # --- Step 3: abstention, before any absence claim ---------------------
    if abstentions:
        return CategoryVerdict(
            ds_category=ds_category,
            verdict=VERDICT_UNDETERMINED,
            declared=declared,
            found_in_policy=False,
            abstention_involved=True,
            # F-19 step 3: for Undetermined, the highest sub-threshold
            # confidence. Deliberately taken from the abstained judgements
            # only. A trusted NO_MATCH in the same category may well be more
            # confident, but it is not what left the question open, and
            # reporting it here would overstate how close the system came to
            # an answer.
            confidence=_deciding_confidence(abstentions),
            records=record_inconclusive(abstentions, declared=declared),
        )

    # --- Step 4: declared, and the policy genuinely does not mention it ---
    if declared:
        return CategoryVerdict(
            ds_category=ds_category,
            verdict=VERDICT_DECLARED_NOT_IN_POLICY,
            declared=True,
            found_in_policy=False,
            abstention_involved=False,
            # The verdict rests on trusted non-matches where there are any.
            # With no judgements at all there is nothing to report, and the
            # field stays None rather than being filled with a guess.
            confidence=_deciding_confidence(
                [j for j in judgements if j.is_decisive_no_match]
            ),
            records=record_absence(ds_category, declaration),
        )

    # --- Step 5: neither source mentions the category ---------------------
    # Consistent, but for a different reason than step 2. CategoryVerdict
    # distinguishes the two through consistency_basis.
    return CategoryVerdict(
        ds_category=ds_category,
        verdict=VERDICT_CONSISTENT,
        declared=False,
        found_in_policy=False,
        abstention_involved=False,
        # Neither source mentioned the category, so no judgement exists and
        # there is no confidence to state.
        confidence=None,
        records=(),
    )


def assign_verdicts(
    declaration: dict[str, DeclarationState],
    judgements_by_category: dict[str, Sequence[AlignmentJudgement]],
    categories: Iterable[str] = DS_CATEGORIES,
    max_evidence: int = 3,
) -> tuple[CategoryVerdict, ...]:
    """Apply ALG-8 to every category, in vocabulary order.

    Every category receives a verdict, including those neither source mentions.
    A report that silently omitted them would leave a reader unable to tell the
    difference between "nothing to report here" and "not examined".
    """
    return tuple(
        assign_category_verdict(
            ds_category=category,
            declaration=declaration.get(
                category, DeclarationState(ds_category=category)
            ),
            judgements=judgements_by_category.get(category, ()),
            max_evidence=max_evidence,
        )
        for category in categories
    )
