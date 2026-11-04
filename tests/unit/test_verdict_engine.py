"""ALG-8 verdict assignment (F-19).

Each test states the inputs and the verdict the approved algorithm requires.
All judgements come from controlled fixtures; no model is involved.
"""

from __future__ import annotations

import pytest

from analysis.verdict.models import CategoryVerdict, DeclarationState
from analysis.verdict.verdict_engine import assign_category_verdict, assign_verdicts
from analysis.vocabulary import DS_CATEGORIES, VERDICTS
from tests.unit.fixtures_verdict import (
    COLLECTS_EMAIL,
    NEVER_LOCATION,
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
# The five verdicts
# ---------------------------------------------------------------------------


def test_consistent_by_affirmative_agreement():
    """Declared, and the policy says so too."""
    result = verdict_for(declared(), judgement("SUPPORTS", COLLECTS_EMAIL))

    assert result.verdict == "Consistent"
    assert result.declared is True
    assert result.found_in_policy is True
    assert result.consistency_basis == "affirmative_agreement"


def test_consistent_because_neither_source_mentions_the_category():
    """Not declared, nothing found. Consistent, but for a different reason."""
    result = verdict_for(not_declared())

    assert result.verdict == "Consistent"
    assert result.declared is False
    assert result.found_in_policy is False
    assert result.consistency_basis == "neither_source_mentions"


def test_the_two_kinds_of_consistent_are_distinguishable():
    """Both are Consistent, but they mean different things to a reader and the
    report must be able to tell them apart."""
    agreement = verdict_for(declared(), judgement("SUPPORTS", COLLECTS_EMAIL))
    silence = verdict_for(not_declared())

    assert agreement.verdict == silence.verdict == "Consistent"
    assert agreement.consistency_basis != silence.consistency_basis


def test_declared_not_in_policy():
    """Declared, and the policy genuinely does not mention it."""
    result = verdict_for(declared(), declaration_only_judgement())

    assert result.verdict == "Declared-not-in-policy"
    assert result.declared is True
    assert result.found_in_policy is False


def test_declared_not_in_policy_with_no_judgements_at_all():
    """A declared category with nothing to compare against is still an
    absence finding, not an omission from the report."""
    result = verdict_for(declared())

    assert result.verdict == "Declared-not-in-policy"


def test_in_policy_not_declared():
    """The policy describes a practice the declaration does not mention."""
    result = verdict_for(
        not_declared(), judgement("SUPPORTS", COLLECTS_EMAIL, with_declaration=False)
    )

    assert result.verdict == "In-policy-not-declared"
    assert result.declared is False
    assert result.found_in_policy is True


def test_contradictory():
    """The two sources make opposing statements."""
    result = verdict_for(declared(), judgement("CONTRADICTS", NEVER_LOCATION))

    assert result.verdict == "Contradictory"
    assert result.found_in_policy is True


def test_undetermined_when_the_only_judgement_abstained():
    result = verdict_for(
        declared(), judgement("SUPPORTS", VAGUE, model_abstained=True)
    )

    assert result.verdict == "Undetermined"
    assert result.abstention_involved is True


def test_every_verdict_value_is_reachable():
    """All five verdicts are produced by the engine, not just defined."""
    produced = {
        verdict_for(declared(), judgement("SUPPORTS", COLLECTS_EMAIL)).verdict,
        verdict_for(not_declared()).verdict,
        verdict_for(declared(), declaration_only_judgement()).verdict,
        verdict_for(
            not_declared(),
            judgement("SUPPORTS", COLLECTS_EMAIL, with_declaration=False),
        ).verdict,
        verdict_for(declared(), judgement("CONTRADICTS", NEVER_LOCATION)).verdict,
        verdict_for(
            declared(), judgement("SUPPORTS", VAGUE, model_abstained=True)
        ).verdict,
    }
    assert produced == set(VERDICTS)


# ---------------------------------------------------------------------------
# Precedence — the order is the algorithm
# ---------------------------------------------------------------------------


def test_contradiction_beats_support():
    """A policy can assert and deny the same practice in different sections.
    The disagreement is the finding; reporting Consistent would hide it."""
    result = verdict_for(
        declared(),
        judgement("SUPPORTS", COLLECTS_EMAIL, segment_id=1, confidence=0.99),
        judgement("CONTRADICTS", NEVER_LOCATION, segment_id=2, confidence=0.55),
    )

    assert result.verdict == "Contradictory"


def test_contradiction_beats_support_regardless_of_confidence():
    """Precedence is ordinal. A weaker contradiction still wins."""
    result = verdict_for(
        declared(),
        judgement("SUPPORTS", COLLECTS_EMAIL, segment_id=1, confidence=1.0),
        judgement("CONTRADICTS", NEVER_LOCATION, segment_id=2, confidence=0.51),
    )

    assert result.verdict == "Contradictory"


def test_contradiction_beats_abstention():
    result = verdict_for(
        declared(),
        judgement("CONTRADICTS", NEVER_LOCATION, segment_id=1),
        judgement("SUPPORTS", VAGUE, segment_id=2, model_abstained=True),
    )

    assert result.verdict == "Contradictory"
    assert result.abstention_involved is True, (
        "the abstention still happened and must be recorded even when it did "
        "not change the verdict"
    )


def test_support_beats_abstention():
    result = verdict_for(
        declared(),
        judgement("SUPPORTS", COLLECTS_EMAIL, segment_id=1),
        judgement("SUPPORTS", VAGUE, segment_id=2, model_abstained=True),
    )

    assert result.verdict == "Consistent"
    assert result.abstention_involved is True


def test_abstention_beats_the_absence_rule():
    """The rule that stops uncertainty becoming a confident claim.

    Declared, and the only policy statement that might have matched was not
    trusted. The system cannot report that the policy omits the category,
    because the statement might have matched.
    """
    result = verdict_for(
        declared(), judgement("NO_MATCH", VAGUE, model_abstained=True)
    )

    assert result.verdict == "Undetermined"
    assert result.verdict != "Declared-not-in-policy"


def test_abstention_beats_neither_source_mentions():
    """Not declared, and the policy reading was uncertain.

    Consistent would claim the policy says nothing about the category, which
    the system does not know. The uncertain statement might have been an
    In-policy-not-declared finding.
    """
    result = verdict_for(
        not_declared(),
        judgement("NO_MATCH", VAGUE, with_declaration=False, model_abstained=True),
    )

    assert result.verdict == "Undetermined"
    assert result.verdict != "Consistent"


def test_trusted_no_match_does_not_block_the_absence_rule():
    """A trusted NO_MATCH is a real finding of absence, not an abstention."""
    result = verdict_for(declared(), judgement("NO_MATCH", VAGUE, confidence=0.97))

    assert result.verdict == "Declared-not-in-policy"
    assert result.abstention_involved is False


# ---------------------------------------------------------------------------
# Abstention propagation
# ---------------------------------------------------------------------------


def test_upstream_abstention_propagates_even_at_high_confidence():
    """A confident alignment built on an uncertain extraction is not trusted.

    The alignment model reports SUPPORTS at 0.99, but the policy practice it
    compared was itself below threshold. Treating this as decisive would turn
    an uncertain reading into a confident finding.
    """
    uncertain = judgement(
        "SUPPORTS", COLLECTS_EMAIL, confidence=0.99, practice_abstained=True
    )

    assert uncertain.model_abstained is False
    assert uncertain.abstained is True
    assert uncertain.is_decisive is False

    result = verdict_for(declared(), uncertain)
    assert result.verdict == "Undetermined"


def test_upstream_abstention_blocks_a_contradiction_too():
    """Abstention does not only suppress support; an untrusted contradiction
    must not raise a Contradictory verdict either."""
    result = verdict_for(
        declared(),
        judgement("CONTRADICTS", NEVER_LOCATION, confidence=0.98, practice_abstained=True),
    )

    assert result.verdict == "Undetermined"


def test_abstention_is_recorded_even_when_it_does_not_change_the_verdict():
    result = verdict_for(
        not_declared(),
        judgement("SUPPORTS", COLLECTS_EMAIL, segment_id=1, with_declaration=False),
        judgement("NO_MATCH", VAGUE, segment_id=2, with_declaration=False, model_abstained=True),
    )

    assert result.verdict == "In-policy-not-declared"
    assert result.abstention_involved is True


def test_found_in_policy_is_false_when_only_abstained_judgements_exist():
    """An abstained judgement never establishes that the policy mentions
    something."""
    result = verdict_for(
        declared(), judgement("SUPPORTS", COLLECTS_EMAIL, model_abstained=True)
    )

    assert result.found_in_policy is False


# ---------------------------------------------------------------------------
# Whole-report behaviour
# ---------------------------------------------------------------------------


def test_every_category_receives_a_verdict():
    """A report must cover all fourteen categories.

    Omitting the quiet ones would leave a reader unable to distinguish
    "nothing to report" from "not examined".
    """
    results = assign_verdicts(declaration={}, judgements_by_category={})

    assert len(results) == len(DS_CATEGORIES)
    assert [r.ds_category for r in results] == list(DS_CATEGORIES)
    assert all(r.verdict == "Consistent" for r in results)
    assert all(r.consistency_basis == "neither_source_mentions" for r in results)


def test_categories_are_independent():
    results = assign_verdicts(
        declaration={"Personal info": declared("Personal info")},
        judgements_by_category={
            "Location": [
                judgement(
                    "CONTRADICTS",
                    NEVER_LOCATION,
                    ds_category="Location",
                    with_declaration=False,
                )
            ]
        },
    )
    by_category = {r.ds_category: r for r in results}

    assert by_category["Personal info"].verdict == "Declared-not-in-policy"
    assert by_category["Location"].verdict == "Contradictory"
    assert by_category["Calendar"].verdict == "Consistent"


def test_a_judgement_for_the_wrong_category_is_rejected():
    """Mixing categories would attribute evidence to the wrong finding."""
    with pytest.raises(ValueError, match="passed to"):
        assign_category_verdict(
            "Location",
            declared("Location"),
            [judgement("SUPPORTS", COLLECTS_EMAIL, ds_category="Personal info")],
        )


def test_declaration_line_asserting_nothing_is_not_a_declaration():
    """A line that declares neither collection nor sharing asserts nothing.

    Counting it would manufacture a disclosure the developer never made.
    """
    state = declared(is_collected=False, is_shared=False)
    assert state.declared is False

    result = verdict_for(state)
    assert result.verdict == "Consistent"
    assert result.consistency_basis == "neither_source_mentions"


def test_sharing_only_declaration_still_counts_as_declared():
    state = declared(is_collected=False, is_shared=True)
    assert state.declared is True

    result = verdict_for(state)
    assert result.verdict == "Declared-not-in-policy"
