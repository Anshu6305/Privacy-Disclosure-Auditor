"""Verdict confidence (F-19 processing step 3, NFR-07).

These are the tests that were missing. Milestone 7 implemented the ALG-8
precedence correctly and omitted step 3 entirely, and 169 passing tests did not
reveal it because none of them asked whether a verdict carries a confidence.
The suite verified what had been built rather than what the design required.

The approved rule:

    "Set the verdict confidence from the judgement that determined the
    outcome; for an Undetermined verdict, record the highest sub-threshold
    confidence instead."

NFR-07 then requires that value to reach the user rather than being hidden
behind a binary result.
"""

from __future__ import annotations

import pytest

from analysis.verdict.models import CategoryVerdict, DeclarationState
from analysis.verdict.verdict_engine import assign_category_verdict, assign_verdicts
from tests.unit.fixtures_verdict import (
    COLLECTS_EMAIL,
    NEVER_LOCATION,
    SHARES_CONTACTS,
    VAGUE,
    declaration_only_judgement,
    declared,
    judgement,
    not_declared,
)

CATEGORY = "Personal info"


def verdict_for(declaration: DeclarationState, *judgements) -> CategoryVerdict:
    return assign_category_verdict(CATEGORY, declaration, list(judgements))


# ---------------------------------------------------------------------------
# The confidence of the deciding judgement
# ---------------------------------------------------------------------------


def test_contradictory_carries_the_contradicting_confidence():
    result = verdict_for(
        declared(), judgement("CONTRADICTS", NEVER_LOCATION, confidence=0.84)
    )

    assert result.verdict == "Contradictory"
    assert result.confidence == pytest.approx(0.84)


def test_consistent_by_agreement_carries_the_supporting_confidence():
    result = verdict_for(
        declared(), judgement("SUPPORTS", COLLECTS_EMAIL, confidence=0.93)
    )

    assert result.verdict == "Consistent"
    assert result.confidence == pytest.approx(0.93)


def test_in_policy_not_declared_carries_the_supporting_confidence():
    result = verdict_for(
        not_declared(),
        judgement("SUPPORTS", COLLECTS_EMAIL, confidence=0.77, with_declaration=False),
    )

    assert result.verdict == "In-policy-not-declared"
    assert result.confidence == pytest.approx(0.77)


def test_declared_not_in_policy_carries_the_non_match_confidence():
    result = verdict_for(declared(), declaration_only_judgement())

    assert result.verdict == "Declared-not-in-policy"
    assert result.confidence == pytest.approx(0.95)


def test_the_strongest_judgement_of_the_deciding_class_is_used():
    """Where several judgements of the same class are present, the verdict
    rests on the strongest, which is also the one F-20 quotes first."""
    result = verdict_for(
        declared(),
        judgement("SUPPORTS", VAGUE, segment_id=1, confidence=0.62),
        judgement("SUPPORTS", COLLECTS_EMAIL, segment_id=2, confidence=0.91),
        judgement("SUPPORTS", SHARES_CONTACTS, segment_id=3, confidence=0.70),
    )

    assert result.confidence == pytest.approx(0.91)


def test_confidence_comes_from_the_deciding_class_not_the_whole_set():
    """A contradiction decides the verdict, so a more confident SUPPORTS in the
    same category must not be reported as the verdict's confidence."""
    result = verdict_for(
        declared(),
        judgement("SUPPORTS", COLLECTS_EMAIL, segment_id=1, confidence=0.99),
        judgement("CONTRADICTS", NEVER_LOCATION, segment_id=2, confidence=0.55),
    )

    assert result.verdict == "Contradictory"
    assert result.confidence == pytest.approx(0.55)


# ---------------------------------------------------------------------------
# Undetermined — the highest sub-threshold confidence
# ---------------------------------------------------------------------------


def test_undetermined_carries_the_highest_sub_threshold_confidence():
    result = verdict_for(
        declared(),
        judgement("SUPPORTS", VAGUE, segment_id=1, confidence=0.31, model_abstained=True),
        judgement("NO_MATCH", VAGUE, segment_id=2, confidence=0.47, model_abstained=True),
    )

    assert result.verdict == "Undetermined"
    assert result.confidence == pytest.approx(0.47)


def test_undetermined_confidence_ignores_trusted_judgements():
    """A trusted NO_MATCH may be more confident than anything abstained, but it
    is not what left the question open. Reporting it would overstate how close
    the system came to an answer."""
    result = verdict_for(
        declared(),
        judgement("NO_MATCH", COLLECTS_EMAIL, segment_id=1, confidence=0.96),
        judgement("SUPPORTS", VAGUE, segment_id=2, confidence=0.33, model_abstained=True),
    )

    # A trusted NO_MATCH plus an abstention: abstention wins the precedence,
    # and the confidence reported is the sub-threshold one.
    assert result.verdict == "Undetermined"
    assert result.confidence == pytest.approx(0.33)


def test_undetermined_from_upstream_abstention_reports_that_confidence():
    """An alignment that looked confident but rested on an uncertain practice.

    The reported figure is the alignment confidence, which is what the system
    actually computed; the reason it is not trusted is carried by the
    inconclusive record, not by lowering the number.
    """
    result = verdict_for(
        declared(),
        judgement("SUPPORTS", COLLECTS_EMAIL, confidence=0.99, practice_abstained=True),
    )

    assert result.verdict == "Undetermined"
    assert result.confidence == pytest.approx(0.99)
    assert result.records[0].record_type == "inconclusive"


# ---------------------------------------------------------------------------
# When there is nothing to report
# ---------------------------------------------------------------------------


def test_consistent_by_silence_has_no_confidence():
    """Neither source mentioned the category, so no judgement exists. A number
    here would be invented."""
    result = verdict_for(not_declared())

    assert result.verdict == "Consistent"
    assert result.consistency_basis == "neither_source_mentions"
    assert result.confidence is None


def test_declared_with_no_judgements_has_no_confidence():
    result = verdict_for(declared())

    assert result.verdict == "Declared-not-in-policy"
    assert result.confidence is None


def test_no_confidence_is_invented_across_a_whole_report():
    """Every category with no judgement must report None, not a default."""
    results = assign_verdicts(declaration={}, judgements_by_category={})

    assert all(r.confidence is None for r in results)


# ---------------------------------------------------------------------------
# Range
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_verdict_confidence_must_be_a_probability(bad):
    with pytest.raises(ValueError, match="not a probability"):
        CategoryVerdict(
            ds_category=CATEGORY,
            verdict="Consistent",
            declared=True,
            found_in_policy=True,
            confidence=bad,
        )


def test_every_verdict_type_reports_a_defined_confidence_state():
    """NFR-07: the user must be able to see a confidence or see that there is
    none. No verdict may leave the field in an undefined state."""
    cases = [
        verdict_for(declared(), judgement("SUPPORTS", COLLECTS_EMAIL)),
        verdict_for(not_declared()),
        verdict_for(declared(), declaration_only_judgement()),
        verdict_for(
            not_declared(),
            judgement("SUPPORTS", COLLECTS_EMAIL, with_declaration=False),
        ),
        verdict_for(declared(), judgement("CONTRADICTS", NEVER_LOCATION)),
        verdict_for(declared(), judgement("SUPPORTS", VAGUE, model_abstained=True)),
    ]

    for result in cases:
        assert result.confidence is None or 0.0 <= result.confidence <= 1.0
