"""A Contradictory verdict needs a contradiction about the same practice.

Spotify's audit 4 reported **App activity: Contradictory** at 0.8341. Its two
quoted passages were about account-data erasure and optional messaging
collection. Neither denies the declared practice — collecting app
interactions, in-app search history, installed apps — and the aligner's
confidence was in its own label, not in the subjects matching.

Both passages reached App activity through F-15's **partial** rule for the
OPP-115 value `User online activities`, which the authored table marks
partial precisely because that value does not distinguish in-app actions
from browsing. Measured on the real audit, every one of App activity's 30
CONTRADICTS judgements came through that partial rule.

A partial mapping is the rule table's own statement that it is not
established the passage is about this practice. That is not enough to
report two sources as conflicting, so such a contradiction now abstains and
ALG-8 step 3 returns Undetermined.

Support is deliberately left decisive. A partial mapping is still evidence
that the policy *mentions* a category, and that is all Consistent and
In-policy-not-declared claim. Only the finding that the sources **conflict**
needs the subjects to line up, because only that one accuses a developer of
something.
"""

from __future__ import annotations

from analysis.verdict.models import (
    AlignmentCandidate,
    AlignmentJudgement,
    MappedPolicyPractice,
)
from analysis.verdict.verdict_engine import assign_category_verdict
from tests.unit.fixtures_verdict import declared, practice

#: Verbatim from the Spotify policy, as quoted in audit 4's report.
ERASURE = (
    "to request erasure of your account data from Spotify, follow the steps "
    "on our support page. This data includes your User Data, Usage Data and "
    "other data listed in Section 3 'Personal data we collect about you'"
)
MESSAGING = (
    "If messaging is available in your market and where you've chosen to use "
    "messaging, we collect and process message data. Message data means text "
    "or other content you send directly to another user."
)
#: An explicit denial of the same practice, for the control case.
EXPLICIT_DENIAL = "We do not collect any app activity or in-app search history."


def judgement_on(
    text: str,
    label: str,
    *,
    is_partial: bool,
    confidence: float = 0.8341,
    ds_category: str = "App activity",
    segment_id: int = 1,
) -> AlignmentJudgement:
    return AlignmentJudgement(
        candidate=AlignmentCandidate(
            ds_category=ds_category,
            declared_item=declared(ds_category).items[0],
            mapped_practice=MappedPolicyPractice(
                practice=practice(text, segment_id=segment_id),
                ds_category=ds_category,
                is_partial=is_partial,
            ),
        ),
        label=label,
        confidence=confidence,
    )


def test_the_spotify_app_activity_passages_do_not_make_a_contradiction():
    """The regression, with audit 4's own evidence.

    Both passages reached App activity through the partial `User online
    activities` rule, so neither establishes that the policy denies the
    declared practice.
    """
    result = assign_category_verdict(
        "App activity",
        declared("App activity", data_type="App interactions"),
        [
            judgement_on(ERASURE, "CONTRADICTS", is_partial=True, segment_id=83),
            judgement_on(MESSAGING, "CONTRADICTS", is_partial=True, segment_id=210),
        ],
    )

    assert result.verdict != "Contradictory", (
        "an unrelated passage was reported as contradicting the declaration"
    )
    assert result.verdict == "Undetermined"
    assert result.abstention_involved is True
    assert result.records[0].record_type == "inconclusive"


def test_the_inconclusive_record_names_the_partial_mapping_as_the_cause():
    """It must not claim a confidence threshold was missed: 0.8341 cleared
    the threshold comfortably, and saying otherwise would be untrue."""
    result = assign_category_verdict(
        "App activity",
        declared("App activity", data_type="App interactions"),
        [judgement_on(MESSAGING, "CONTRADICTS", is_partial=True, segment_id=210)],
    )

    reason = result.records[0].reason
    assert "partial taxonomy mapping" in reason
    assert "same data practice" in reason
    assert "below the confidence threshold" not in reason


def test_an_explicit_denial_through_an_exact_mapping_is_still_contradictory():
    """The control. Without this the fix would just disable step 1."""
    result = assign_category_verdict(
        "App activity",
        declared("App activity", data_type="App interactions"),
        [judgement_on(EXPLICIT_DENIAL, "CONTRADICTS", is_partial=False)],
    )

    assert result.verdict == "Contradictory"
    assert result.found_in_policy is True
    assert result.records[0].record_type == "evidence"
    assert result.records[0].quoted_text == EXPLICIT_DENIAL


def test_one_exact_denial_outweighs_any_number_of_partial_ones():
    """A genuine contradiction must not be buried by ambiguous company."""
    result = assign_category_verdict(
        "App activity",
        declared("App activity", data_type="App interactions"),
        [
            judgement_on(ERASURE, "CONTRADICTS", is_partial=True, segment_id=83),
            judgement_on(MESSAGING, "CONTRADICTS", is_partial=True, segment_id=210),
            judgement_on(
                EXPLICIT_DENIAL, "CONTRADICTS", is_partial=False, segment_id=5
            ),
        ],
    )

    assert result.verdict == "Contradictory"
    assert result.records[0].quoted_text == EXPLICIT_DENIAL


def test_support_through_a_partial_mapping_is_still_decisive():
    """Deliberate asymmetry, asserted so it is a choice and not an accident.

    Consistent and In-policy-not-declared claim only that the policy mentions
    the category. Making partial support abstain too would push almost every
    category on this corpus to Undetermined - measured on the real Spotify
    audit, all 30 of App activity's SUPPORTS judgements are partial - which
    would make the system silent rather than careful.
    """
    result = assign_category_verdict(
        "App activity",
        declared("App activity", data_type="App interactions"),
        [judgement_on(MESSAGING, "SUPPORTS", is_partial=True, confidence=0.76)],
    )

    assert result.verdict == "Consistent"
    assert result.found_in_policy is True


def test_a_partial_no_match_is_unaffected():
    """Only contradictions gained a precondition."""
    result = assign_category_verdict(
        "App activity",
        declared("App activity", data_type="App interactions"),
        [judgement_on(MESSAGING, "NO_MATCH", is_partial=True, confidence=0.88)],
    )

    assert result.verdict == "Declared-not-in-policy"
    assert result.records[0].record_type == "absence"
