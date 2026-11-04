"""Confidence gate, taxonomy mapping, declaration normalisation and candidate
construction (F-14, F-15, F-16, F-17).

The recurring property across these stages is that uncertainty survives them.
Each stage is checked for keeping an abstained practice rather than dropping it.
"""

from __future__ import annotations

import pytest

from analysis.confidence.gate import (
    abstention_rate,
    apply_threshold,
    apply_threshold_to_all,
    is_abstention,
)
from analysis.mapping.candidate_builder import build_candidates
from analysis.mapping.declaration_normaliser import (
    UnknownDataSafetyCategoryError,
    normalise_declaration,
)
from analysis.mapping.taxonomy_mapper import MappingRule, TaxonomyMapper
from analysis.verdict.models import DeclaredItem
from analysis.vocabulary import DS_CATEGORIES
from tests.unit.fixtures_verdict import COLLECTS_EMAIL, VAGUE, mapped, practice

# ---------------------------------------------------------------------------
# F-14 — confidence gate (ALG-4)
# ---------------------------------------------------------------------------


def test_confidence_equal_to_the_threshold_is_accepted():
    """The boundary has to fall on one side. It is stated once, here."""
    assert is_abstention(0.5, 0.5) is False
    assert is_abstention(0.4999, 0.5) is True


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_gate_rejects_values_that_are_not_probabilities(bad):
    with pytest.raises(ValueError, match="not a probability"):
        is_abstention(bad, 0.5)


def test_gate_flags_rather_than_deletes():
    """A low-confidence practice is kept so its uncertainty can travel."""
    low = practice(VAGUE, confidence=0.2)
    gated = apply_threshold(low, 0.5)

    assert gated.abstained is True
    assert gated.confidence == pytest.approx(0.2)
    assert gated.segment.text == VAGUE


def test_gate_keeps_every_input():
    practices = [
        practice(COLLECTS_EMAIL, practice_id=1, confidence=0.9),
        practice(VAGUE, practice_id=2, confidence=0.1),
    ]
    gated = apply_threshold_to_all(practices, 0.5)

    assert len(gated) == 2, "the gate must not filter anything out"
    assert [p.abstained for p in gated] == [False, True]


def test_abstention_is_sticky():
    """A practice flagged upstream stays flagged even under a threshold that
    would accept it. The earlier reason for doubt has not gone away."""
    already = practice(COLLECTS_EMAIL, confidence=0.95, abstained=True)
    gated = apply_threshold(already, 0.5)

    assert gated.abstained is True


def test_abstention_rate_is_reported():
    practices = apply_threshold_to_all(
        [
            practice(COLLECTS_EMAIL, practice_id=1, confidence=0.9),
            practice(VAGUE, practice_id=2, confidence=0.1),
            practice(VAGUE, practice_id=3, confidence=0.2),
        ],
        0.5,
    )

    assert abstention_rate(practices) == pytest.approx(2 / 3)
    assert abstention_rate([]) == 0.0


# ---------------------------------------------------------------------------
# F-15 — taxonomy mapping (ALG-5)
# ---------------------------------------------------------------------------


@pytest.fixture
def mapper() -> TaxonomyMapper:
    return TaxonomyMapper(
        rules=[
            MappingRule("First Party Collection/Use", "Personal info"),
            MappingRule(
                "First Party Collection/Use",
                "Location",
                opp115_data_type="Location",
            ),
            MappingRule("Third Party Sharing/Collection", "Personal info"),
        ],
        version_label="test-v1",
    )


def test_mapping_is_a_deterministic_lookup(mapper):
    """F-15 is rule-based, not learned. The same input always maps the same
    way, which is what lets a report point at the rule it used."""
    first = mapper.map_practice(practice(COLLECTS_EMAIL))
    second = mapper.map_practice(practice(COLLECTS_EMAIL))

    assert [m.ds_category for m in first] == [m.ds_category for m in second]
    assert first[0].ds_category == "Personal info"


def test_a_more_specific_rule_wins(mapper):
    general = mapper.rules_for("First Party Collection/Use")
    specific = mapper.rules_for("First Party Collection/Use", "Location")

    assert [r.ds_category for r in general] == ["Personal info"]
    assert [r.ds_category for r in specific] == ["Location"]


def test_an_unmapped_category_produces_nothing(mapper):
    """Several OPP-115 categories, such as Policy Change, have no Data Safety
    counterpart. An empty result is a normal outcome, not an error."""
    result = mapper.map_practice(practice(VAGUE, opp115_category="Policy Change"))

    assert result == ()


def test_mapping_preserves_abstention(mapper):
    """The defect this test exists to prevent: a deterministic lookup must not
    launder an uncertain prediction into a confident one."""
    uncertain = practice(VAGUE, confidence=0.3, abstained=True)
    result = mapper.map_practice(uncertain)

    assert len(result) == 1
    assert result[0].abstained is True


def test_map_all_keeps_abstained_practices(mapper):
    practices = [
        practice(COLLECTS_EMAIL, practice_id=1, confidence=0.9),
        practice(VAGUE, practice_id=2, confidence=0.2, abstained=True),
    ]
    result = mapper.map_all(practices)

    assert len(result) == 2
    assert [m.abstained for m in result] == [False, True]


def test_mapper_records_its_version(mapper):
    """An audit states which mapping version produced it."""
    assert mapper.version_label == "test-v1"


# ---------------------------------------------------------------------------
# F-16 — declaration normalisation
# ---------------------------------------------------------------------------


def test_every_category_is_present_after_normalisation():
    """A category the declaration never mentions is a finding, not a missing
    dictionary key."""
    result = normalise_declaration([])

    assert set(result) == set(DS_CATEGORIES)
    assert all(state.declared is False for state in result.values())


def test_lines_are_grouped_by_category():
    items = [
        DeclaredItem(1, "Personal info", "Email address", is_collected=True),
        DeclaredItem(2, "Personal info", "Name", is_collected=True),
        DeclaredItem(3, "Location", "Precise location", is_shared=True),
    ]
    result = normalise_declaration(items)

    assert len(result["Personal info"].items) == 2
    assert len(result["Location"].items) == 1
    assert result["Personal info"].declared is True
    assert result["Location"].declared is True


def test_a_line_asserting_nothing_does_not_declare_the_category():
    items = [DeclaredItem(1, "Personal info", "Email address")]
    result = normalise_declaration(items)

    assert len(result["Personal info"].items) == 1
    assert result["Personal info"].declared is False


def test_an_unknown_category_stops_the_audit():
    """Google can revise its taxonomy. If that happens the audit must fail with
    the category named, rather than quietly producing a report that looks
    complete while missing a whole category."""
    items = [DeclaredItem(1, "Brain Activity", is_collected=True)]

    with pytest.raises(UnknownDataSafetyCategoryError) as caught:
        normalise_declaration(items)

    assert caught.value.category == "Brain Activity"
    assert "Brain Activity" in str(caught.value)


# ---------------------------------------------------------------------------
# F-17 — candidate construction (ALG-6)
# ---------------------------------------------------------------------------


def test_both_sides_present_produces_a_paired_candidate():
    declaration = normalise_declaration(
        [DeclaredItem(1, "Personal info", "Email address", is_collected=True)]
    )
    candidates = build_candidates(declaration, [mapped(COLLECTS_EMAIL)])

    pair = candidates["Personal info"]
    assert len(pair) == 1
    assert pair[0].declared_item is not None
    assert pair[0].mapped_practice is not None


def test_a_declared_line_with_no_policy_practice_still_produces_a_candidate():
    """Without this candidate there is no input to a Declared-not-in-policy
    finding. A finding about something missing cannot come from a pair that
    was never built."""
    declaration = normalise_declaration(
        [DeclaredItem(1, "Location", "Precise location", is_collected=True)]
    )
    candidates = build_candidates(declaration, [])

    assert len(candidates["Location"]) == 1
    assert candidates["Location"][0].mapped_practice is None


def test_a_policy_practice_with_no_declaration_still_produces_a_candidate():
    candidates = build_candidates(normalise_declaration([]), [mapped(COLLECTS_EMAIL)])

    assert len(candidates["Personal info"]) == 1
    assert candidates["Personal info"][0].declared_item is None


def test_a_category_neither_source_mentions_produces_no_candidates():
    candidates = build_candidates(normalise_declaration([]), [])

    assert candidates["Calendar"] == ()
    assert set(candidates) == set(DS_CATEGORIES)


def test_candidates_carry_upstream_abstention():
    candidates = build_candidates(
        normalise_declaration([]),
        [mapped(VAGUE, confidence=0.2, abstained=True)],
    )

    assert candidates["Personal info"][0].abstained_upstream is True


def test_every_declared_line_is_paired_with_every_practice():
    """The verdict engine takes the strongest outcome across pairings, so each
    pairing has to be offered rather than chosen here."""
    declaration = normalise_declaration(
        [
            DeclaredItem(1, "Personal info", "Email address", is_collected=True),
            DeclaredItem(2, "Personal info", "Name", is_collected=True),
        ]
    )
    practices = [
        mapped(COLLECTS_EMAIL, segment_id=1, practice_id=1),
        mapped(VAGUE, segment_id=2, practice_id=2),
    ]
    candidates = build_candidates(declaration, practices)

    assert len(candidates["Personal info"]) == 4


def test_a_practice_outside_the_vocabulary_is_rejected():
    with pytest.raises(ValueError, match="outside the vocabulary"):
        build_candidates(
            normalise_declaration([]), [mapped(COLLECTS_EMAIL, ds_category="Telepathy")]
        )
