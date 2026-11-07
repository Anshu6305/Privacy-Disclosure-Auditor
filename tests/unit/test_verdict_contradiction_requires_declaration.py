"""A contradiction needs a declaration to contradict (ALG-8 step 1 inputs).

Spotify's audit 2 reported **Web browsing: Contradictory** against a
declaration that never mentions Web browsing. Tracing it:

* F-12 predicted the data type `User online activities` for three passages
  that are about messaging, device sensor data and sharing with other Spotify
  users;
* F-15 maps that value to both App activity and Web browsing, correctly and
  as two partial rules, because the OPP-115 value does not distinguish them;
* `build_pair` found no declared item for Web browsing and built the
  hypothesis "This app collects Web browsing." anyway, with `collected=True`;
* the NLI contradicted that sentence, and ALG-8 step 1 read the result as the
  two sources disagreeing.

Nothing in the declaration was ever involved. The probe is a question put to
the policy so that a trusted SUPPORTS can reach In-policy-not-declared; a
CONTRADICTS against it means the policy denies a practice the declaration
never asserted, which is agreement, not disagreement.

ALG-8 is unchanged: step 1 still fires on any trusted contradiction. What
changed is that a probe of an undeclared category is no longer one.
"""

from __future__ import annotations

from analysis.verdict.verdict_engine import assign_category_verdict
from tests.unit.fixtures_verdict import (
    COLLECTS_EMAIL,
    NEVER_LOCATION,
    declared,
    judgement,
    not_declared,
)


def test_a_contradiction_needs_a_declaration_to_contradict():
    """The regression. Undeclared category, policy denies it -> agreement."""
    result = assign_category_verdict(
        "Location",
        not_declared("Location"),
        [
            judgement(
                "CONTRADICTS",
                NEVER_LOCATION,
                ds_category="Location",
                with_declaration=False,
            )
        ],
    )

    assert result.verdict != "Contradictory", (
        "an undeclared category was reported as contradicting a declaration "
        "that never mentioned it"
    )
    assert result.declared is False


def test_a_contradiction_against_a_real_declaration_still_fires():
    """The other half. Without this the fix would simply disable step 1."""
    result = assign_category_verdict(
        "Location",
        declared("Location"),
        [judgement("CONTRADICTS", NEVER_LOCATION, ds_category="Location")],
    )

    assert result.verdict == "Contradictory"
    assert result.found_in_policy is True
    assert result.records[0].record_type == "evidence"


def test_an_undeclared_category_can_still_reach_in_policy_not_declared():
    """The probe must keep working for SUPPORTS.

    If the fix had removed the hypothesis for undeclared categories instead,
    this verdict would have become unreachable and the system could never
    report a practice the policy describes and the declaration omits - which
    is one of the two findings the project exists to make.
    """
    result = assign_category_verdict(
        "Personal info",
        not_declared("Personal info"),
        [judgement("SUPPORTS", COLLECTS_EMAIL, with_declaration=False)],
    )

    assert result.verdict == "In-policy-not-declared"
    assert result.found_in_policy is True
    assert result.records[0].record_type == "evidence"


def test_a_policy_only_contradiction_does_not_claim_the_policy_mentions_it():
    """`found_in_policy` must not be set by a judgement that no longer
    decides anything. Reporting it true would leave a Consistent verdict
    asserting the policy covered a category on evidence the engine just
    declined to act on."""
    result = assign_category_verdict(
        "Web browsing",
        not_declared("Web browsing"),
        [
            judgement(
                "CONTRADICTS",
                NEVER_LOCATION,
                ds_category="Web browsing",
                with_declaration=False,
            )
        ],
    )

    assert result.found_in_policy is False


def test_an_abstained_contradiction_is_still_not_decisive_either_way():
    """Unchanged behaviour, asserted so the new precondition cannot be read
    as the only gate on step 1."""
    result = assign_category_verdict(
        "Location",
        declared("Location"),
        [
            judgement(
                "CONTRADICTS",
                NEVER_LOCATION,
                ds_category="Location",
                model_abstained=True,
            )
        ],
    )

    assert result.verdict == "Undetermined"
    assert result.abstention_involved is True
