"""The invariants the domain types enforce.

Each of these guards exists to stop a specific wrong value entering the engine.
A guard that is never exercised is not a guarantee, so each one is triggered
here.
"""

from __future__ import annotations

import pytest

from analysis.confidence.gate import is_abstention
from analysis.verdict.evidence_selector import select_evidence
from analysis.verdict.inconclusive_recorder import record_inconclusive
from analysis.verdict.models import (
    AlignmentCandidate,
    AlignmentJudgement,
    CategoryVerdict,
    DeclaredItem,
    EvidenceRecord,
    PolicyPractice,
    PolicySegmentRef,
)
from tests.unit.fixtures_verdict import COLLECTS_EMAIL, VAGUE, declared, judgement, segment

# ---------------------------------------------------------------------------
# PolicySegmentRef
# ---------------------------------------------------------------------------


def test_segment_rejects_negative_start():
    with pytest.raises(ValueError, match="char_start is negative"):
        PolicySegmentRef(1, "text", -1, 3)


def test_segment_rejects_unordered_offsets():
    with pytest.raises(ValueError, match="greater than char_start"):
        PolicySegmentRef(1, "text", 10, 10)


def test_segment_rejects_offsets_that_do_not_span_the_text():
    """If the offsets do not describe this exact text, every quote taken from
    the segment points somewhere else in the document."""
    with pytest.raises(ValueError, match="Evidence offsets taken from this segment"):
        PolicySegmentRef(1, "four", 0, 99)


# ---------------------------------------------------------------------------
# PolicyPractice and AlignmentJudgement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.5, 1.2])
def test_practice_confidence_must_be_a_probability(bad):
    with pytest.raises(ValueError, match="not a probability"):
        PolicyPractice(1, segment("text"), "First Party Collection/Use", bad)


def test_judgement_rejects_an_unknown_label():
    candidate = AlignmentCandidate(
        "Personal info", declared_item=declared().items[0]
    )
    with pytest.raises(ValueError, match="unknown alignment label"):
        AlignmentJudgement(candidate, "PROBABLY", 0.9)


def test_judgement_confidence_must_be_a_probability():
    candidate = AlignmentCandidate(
        "Personal info", declared_item=declared().items[0]
    )
    with pytest.raises(ValueError, match="not a probability"):
        AlignmentJudgement(candidate, "SUPPORTS", 1.5)


def test_candidate_needs_at_least_one_side():
    with pytest.raises(ValueError, match="needs a declared item"):
        AlignmentCandidate("Personal info")


def test_declared_item_asserting_nothing():
    item = DeclaredItem(1, "Personal info", "Email address")
    assert item.asserts_practice is False
    assert DeclaredItem(2, "Personal info", is_collected=True).asserts_practice is True
    assert DeclaredItem(3, "Personal info", is_shared=True).asserts_practice is True


# ---------------------------------------------------------------------------
# Gate and selector arguments
# ---------------------------------------------------------------------------


def test_gate_rejects_a_threshold_that_is_not_a_probability():
    with pytest.raises(ValueError, match="threshold .* not a probability"):
        is_abstention(0.5, 1.4)


def test_evidence_selection_requires_a_positive_cap():
    with pytest.raises(ValueError, match="at least 1"):
        select_evidence([judgement("SUPPORTS", COLLECTS_EMAIL)], max_records=0)


def test_inconclusive_records_are_capped():
    abstentions = [
        judgement("NO_MATCH", VAGUE, segment_id=i, model_abstained=True)
        for i in range(1, 7)
    ]
    records = record_inconclusive(abstentions, declared=True, max_records=2)

    assert len(records) == 2


def test_inconclusive_skips_a_repeated_segment():
    abstentions = [
        judgement("NO_MATCH", VAGUE, segment_id=1, model_abstained=True),
        judgement("NO_MATCH", VAGUE, segment_id=1, model_abstained=True),
    ]
    records = record_inconclusive(abstentions, declared=True)

    assert len(records) == 1


def test_inconclusive_handles_a_judgement_with_no_segment():
    """A declared line with no policy practice has no segment to quote."""
    candidate = AlignmentCandidate(
        "Personal info", declared_item=declared().items[0]
    )
    abstained = AlignmentJudgement(candidate, "NO_MATCH", 0.2, model_abstained=True)

    records = record_inconclusive([abstained], declared=True)

    assert len(records) == 1
    assert records[0].segment_id is None
    assert records[0].quoted_text is None


# ---------------------------------------------------------------------------
# CategoryVerdict
# ---------------------------------------------------------------------------


def test_verdict_rejects_an_unknown_value():
    with pytest.raises(ValueError, match="unknown verdict"):
        CategoryVerdict(
            ds_category="Personal info",
            verdict="Mostly Fine",
            declared=True,
            found_in_policy=True,
        )


def test_consistency_basis_is_none_for_other_verdicts():
    result = CategoryVerdict(
        ds_category="Personal info",
        verdict="Contradictory",
        declared=True,
        found_in_policy=True,
    )
    assert result.consistency_basis is None


def test_vocabulary_guards():
    from analysis.vocabulary import (
        DS_CATEGORIES,
        is_known_ds_category,
        opp115_categories,
    )

    assert is_known_ds_category("Personal info") is True
    assert is_known_ds_category("Telepathy") is False
    assert len(DS_CATEGORIES) == 14
    assert len(opp115_categories()) == 10


# ---------------------------------------------------------------------------
# EvidenceRecord — the remaining guards
#
# These mirror the CHECK constraints on the evidence_record table. They are
# triggered here so the validation is known to work rather than assumed.
# ---------------------------------------------------------------------------


def test_evidence_record_requires_a_segment_reference():
    """Without it a reader cannot find the quote in the document."""
    with pytest.raises(ValueError, match="must name the segment"):
        EvidenceRecord(
            record_type="evidence",
            quoted_text="We collect your email address",
            char_start=0,
            char_end=29,
        )


def test_evidence_record_requires_both_offsets():
    with pytest.raises(ValueError, match="must carry character offsets"):
        EvidenceRecord(
            record_type="evidence",
            segment_id=1,
            quoted_text="We collect your email address",
            char_start=0,
        )


def test_evidence_record_requires_ordered_offsets():
    with pytest.raises(ValueError, match="must be ordered"):
        EvidenceRecord(
            record_type="evidence",
            segment_id=1,
            quoted_text="We collect your email address",
            char_start=40,
            char_end=11,
        )


def test_absence_record_without_a_reason_is_rejected():
    with pytest.raises(ValueError, match="must state why nothing was found"):
        EvidenceRecord(record_type="absence")


def test_no_match_judgement_helper():
    """is_decisive_no_match distinguishes a trusted non-match from an
    abstention, which is what lets step 4 of ALG-8 run."""
    trusted = judgement("NO_MATCH", VAGUE, confidence=0.95)
    untrusted = judgement("NO_MATCH", VAGUE, model_abstained=True)

    assert trusted.is_decisive_no_match is True
    assert untrusted.is_decisive_no_match is False
    assert trusted.is_decisive is False, (
        "a non-match is trusted but is not evidence that the policy says "
        "anything, so it is not decisive"
    )
