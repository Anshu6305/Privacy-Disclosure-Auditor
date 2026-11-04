"""Evidence selection and record construction (F-20, F-21, F-22, ALG-9).

The central property under test is that evidence is quoted, never generated:
every evidence record must contain a slice of the policy's own text with
offsets that locate it in the document.
"""

from __future__ import annotations

import pytest

from analysis.verdict.absence_recorder import record_absence
from analysis.verdict.evidence_selector import select_evidence
from analysis.verdict.inconclusive_recorder import record_inconclusive
from analysis.verdict.models import EvidenceRecord
from analysis.verdict.verdict_engine import assign_category_verdict
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


# ---------------------------------------------------------------------------
# F-20 — evidence is quoted, not generated
# ---------------------------------------------------------------------------


def test_evidence_quotes_the_policy_text_verbatim():
    records = select_evidence([judgement("SUPPORTS", COLLECTS_EMAIL)])

    assert len(records) == 1
    assert records[0].quoted_text == COLLECTS_EMAIL
    assert records[0].record_type == "evidence"


def test_evidence_offsets_locate_the_quote_in_the_document():
    """Offsets must span exactly the quoted text, or a reader following them
    lands somewhere else in the policy."""
    records = select_evidence([judgement("SUPPORTS", COLLECTS_EMAIL)])
    record = records[0]

    assert record.char_end - record.char_start == len(record.quoted_text)
    assert record.segment_id is not None


def test_evidence_is_ordered_by_confidence_highest_first():
    records = select_evidence(
        [
            judgement("SUPPORTS", VAGUE, segment_id=2, confidence=0.61),
            judgement("SUPPORTS", COLLECTS_EMAIL, segment_id=1, confidence=0.95),
            judgement("SUPPORTS", SHARES_CONTACTS, segment_id=3, confidence=0.78),
        ],
        max_records=3,
    )

    assert [r.quoted_text for r in records] == [
        COLLECTS_EMAIL,
        SHARES_CONTACTS,
        VAGUE,
    ]
    assert [r.display_order for r in records] == [0, 1, 2]


def test_evidence_is_capped():
    records = select_evidence(
        [
            judgement("SUPPORTS", COLLECTS_EMAIL, segment_id=i, confidence=0.9)
            for i in range(1, 9)
        ],
        max_records=3,
    )

    assert len(records) == 3


def test_the_same_segment_is_not_quoted_twice():
    """One segment can be reached through several declared lines in a
    category. Repeating it adds length, not information."""
    records = select_evidence(
        [
            judgement("SUPPORTS", COLLECTS_EMAIL, segment_id=1, confidence=0.9),
            judgement("SUPPORTS", COLLECTS_EMAIL, segment_id=1, confidence=0.8),
        ]
    )

    assert len(records) == 1


def test_ties_are_broken_deterministically():
    """Equal confidence must not reorder between runs, or two identical audits
    would appear to differ."""
    judgements = [
        judgement("SUPPORTS", SHARES_CONTACTS, segment_id=7, confidence=0.9),
        judgement("SUPPORTS", COLLECTS_EMAIL, segment_id=3, confidence=0.9),
    ]

    first = select_evidence(judgements)
    second = select_evidence(list(reversed(judgements)))

    assert [r.segment_id for r in first] == [r.segment_id for r in second] == [3, 7]


def test_an_abstained_judgement_cannot_support_evidence():
    """Evidence asserts that the policy says something. An abstained
    judgement is exactly the case where that is unknown."""
    with pytest.raises(ValueError, match="abstained judgement cannot support"):
        select_evidence([judgement("SUPPORTS", VAGUE, model_abstained=True)])


def test_evidence_needs_a_policy_practice_to_quote_from():
    with pytest.raises(ValueError, match="needs a policy practice"):
        select_evidence([declaration_only_judgement()])


# ---------------------------------------------------------------------------
# Record validity
# ---------------------------------------------------------------------------


def test_evidence_record_rejects_missing_quote():
    with pytest.raises(ValueError, match="must carry quoted policy text"):
        EvidenceRecord(record_type="evidence", segment_id=1, char_start=0, char_end=5)


def test_evidence_record_rejects_offsets_that_do_not_match_the_quote():
    """The guard against a quote that was edited after its offsets were set."""
    with pytest.raises(ValueError, match="do not match the length"):
        EvidenceRecord(
            record_type="evidence",
            segment_id=1,
            quoted_text="We collect your email address",
            char_start=0,
            char_end=5,
        )


def test_absence_record_rejects_a_quote():
    with pytest.raises(ValueError, match="cannot quote text"):
        EvidenceRecord(
            record_type="absence",
            reason="nothing found",
            quoted_text="no mention of location",
        )


def test_inconclusive_record_requires_a_reason():
    with pytest.raises(ValueError, match="must state why"):
        EvidenceRecord(record_type="inconclusive")


def test_unknown_record_type_is_rejected():
    with pytest.raises(ValueError, match="unknown record type"):
        EvidenceRecord(record_type="maybe", reason="x")


# ---------------------------------------------------------------------------
# F-21 — absence records
# ---------------------------------------------------------------------------


def test_absence_record_has_no_quote_and_states_a_reason():
    """Declared-not-in-policy is an absence. There is nothing to quote,
    because the finding is that no such statement exists."""
    records = record_absence(CATEGORY, declared())

    assert len(records) == 1
    assert records[0].record_type == "absence"
    assert records[0].quoted_text is None
    assert records[0].reason


def test_absence_reason_names_what_was_declared():
    records = record_absence(CATEGORY, declared(data_type="Email address"))
    reason = records[0].reason

    assert "Personal info" in reason
    assert "Email address" in reason
    assert "collection" in reason


def test_absence_reason_distinguishes_sharing_from_collection():
    collected = record_absence(CATEGORY, declared(is_collected=True))[0].reason
    shared = record_absence(
        CATEGORY, declared(is_collected=False, is_shared=True)
    )[0].reason

    assert "collection" in collected
    assert "sharing" in shared


def test_absence_reason_does_not_assert_wrongdoing():
    """The system reports what it did not find in the text it analysed. It
    does not conclude that the policy is inadequate or that the developer did
    anything wrong."""
    reason = record_absence(CATEGORY, declared())[0].reason.lower()

    assert "not a conclusion about" in reason
    for forbidden in ("violat", "unlawful", "illegal", "non-compliant", "deceptive"):
        assert forbidden not in reason


# ---------------------------------------------------------------------------
# F-22 — inconclusive records
# ---------------------------------------------------------------------------


def test_inconclusive_record_says_the_system_abstained():
    records = record_inconclusive(
        [judgement("SUPPORTS", VAGUE, model_abstained=True)], declared=True
    )

    assert len(records) == 1
    assert records[0].record_type == "inconclusive"
    assert "abstention, not a finding of inconsistency" in records[0].reason


def test_inconclusive_record_names_which_threshold_was_missed():
    """A reviewer needs to know whether the extraction or the comparison was
    the uncertain step, because they are different problems."""
    upstream = record_inconclusive(
        [judgement("SUPPORTS", VAGUE, practice_abstained=True)], declared=True
    )[0].reason
    alignment = record_inconclusive(
        [judgement("SUPPORTS", VAGUE, model_abstained=True)], declared=True
    )[0].reason

    assert "extracted from the policy text" in upstream
    assert "cross-source comparison" in alignment


def test_inconclusive_record_quotes_the_segment_verbatim_when_it_has_one():
    """A reviewer following up needs the policy's words, not a description."""
    records = record_inconclusive(
        [judgement("SUPPORTS", VAGUE, model_abstained=True)], declared=True
    )

    assert records[0].quoted_text == VAGUE
    assert records[0].char_end - records[0].char_start == len(VAGUE)


def test_inconclusive_requires_at_least_one_abstention():
    with pytest.raises(ValueError, match="at least one"):
        record_inconclusive([], declared=True)


# ---------------------------------------------------------------------------
# Records attached by the engine
# ---------------------------------------------------------------------------


def test_consistent_verdict_carries_no_records():
    """F-23: a Consistent verdict needs no evidence record."""
    agreement = assign_category_verdict(
        CATEGORY, declared(), [judgement("SUPPORTS", COLLECTS_EMAIL)]
    )
    silence = assign_category_verdict(CATEGORY, not_declared(), [])

    assert agreement.records == ()
    assert silence.records == ()


def test_contradictory_verdict_carries_evidence():
    result = assign_category_verdict(
        CATEGORY, declared(), [judgement("CONTRADICTS", NEVER_LOCATION)]
    )

    assert len(result.records) == 1
    assert result.records[0].record_type == "evidence"
    assert result.records[0].quoted_text == NEVER_LOCATION


def test_in_policy_not_declared_carries_evidence():
    result = assign_category_verdict(
        CATEGORY,
        not_declared(),
        [judgement("SUPPORTS", COLLECTS_EMAIL, with_declaration=False)],
    )

    assert result.records[0].record_type == "evidence"
    assert result.records[0].quoted_text == COLLECTS_EMAIL


def test_declared_not_in_policy_carries_an_absence_record():
    result = assign_category_verdict(CATEGORY, declared(), [])

    assert len(result.records) == 1
    assert result.records[0].record_type == "absence"
    assert result.records[0].quoted_text is None


def test_undetermined_carries_an_inconclusive_record():
    result = assign_category_verdict(
        CATEGORY, declared(), [judgement("SUPPORTS", VAGUE, model_abstained=True)]
    )

    assert len(result.records) == 1
    assert result.records[0].record_type == "inconclusive"


def test_record_types_match_the_verdict_in_every_case():
    """One table-driven check so a future change to ALG-8 cannot quietly
    attach the wrong kind of record."""
    cases = [
        (declared(), [judgement("SUPPORTS", COLLECTS_EMAIL)], "Consistent", set()),
        (not_declared(), [], "Consistent", set()),
        (declared(), [], "Declared-not-in-policy", {"absence"}),
        (
            not_declared(),
            [judgement("SUPPORTS", COLLECTS_EMAIL, with_declaration=False)],
            "In-policy-not-declared",
            {"evidence"},
        ),
        (
            declared(),
            [judgement("CONTRADICTS", NEVER_LOCATION)],
            "Contradictory",
            {"evidence"},
        ),
        (
            declared(),
            [judgement("SUPPORTS", VAGUE, model_abstained=True)],
            "Undetermined",
            {"inconclusive"},
        ),
    ]

    for declaration, judgements, expected_verdict, expected_types in cases:
        result = assign_category_verdict(CATEGORY, declaration, judgements)
        assert result.verdict == expected_verdict
        assert {r.record_type for r in result.records} == expected_types
