"""The Milestone 7 stages working together on one controlled scenario.

This runs F-14, F-15, F-16, F-17 and F-19 in sequence over a small invented
policy and declaration, and checks the verdicts that come out.

F-18 is **not** involved. It belongs to Milestone 6 and does not exist. The
alignment labels in this test are written by hand to describe what a correct
aligner would say about these sentences, which is what makes the rest of the
chain testable now. No model runs, and nothing here stands in for one.

The scenario is also the walkthrough the team can use to explain the engine:
one case of each verdict, end to end.
"""

from __future__ import annotations

from analysis.confidence.gate import apply_threshold_to_all
from analysis.mapping.candidate_builder import build_candidates
from analysis.mapping.declaration_normaliser import normalise_declaration
from analysis.mapping.taxonomy_mapper import MappingRule, TaxonomyMapper
from analysis.verdict.models import (
    AlignmentJudgement,
    DeclaredItem,
    PolicyPractice,
    PolicySegmentRef,
)
from analysis.verdict.verdict_engine import assign_verdicts
from analysis.vocabulary import DS_CATEGORIES

THRESHOLD = 0.60

# --- An invented privacy policy, four segments -----------------------------
SENTENCES = [
    "We collect your email address so that we can send you service updates.",
    "We never collect or store your precise location.",
    "We share your contact list with advertising partners.",
    "We may process certain information in order to improve the service.",
]


def _segments() -> list[PolicySegmentRef]:
    """Segments with offsets running consecutively through the document."""
    segments: list[PolicySegmentRef] = []
    cursor = 0
    for index, text in enumerate(SENTENCES, start=1):
        segments.append(
            PolicySegmentRef(
                segment_id=index,
                text=text,
                char_start=cursor,
                char_end=cursor + len(text),
            )
        )
        cursor += len(text) + 1
    return segments


def _scenario():
    segments = _segments()

    # --- F-11/F-12 output, stated rather than predicted --------------------
    # The last sentence is vague, and the classifier is given a low confidence
    # for it so the gate will abstain. That is the point of including it.
    raw_practices = [
        PolicyPractice(1, segments[0], "First Party Collection/Use", 0.94),
        PolicyPractice(2, segments[1], "First Party Collection/Use", 0.91),
        PolicyPractice(3, segments[2], "Third Party Sharing/Collection", 0.88),
        PolicyPractice(4, segments[3], "First Party Collection/Use", 0.34),
    ]

    # --- F-14 ---------------------------------------------------------------
    gated = apply_threshold_to_all(raw_practices, THRESHOLD)

    # --- F-15 ---------------------------------------------------------------
    mapper = TaxonomyMapper(
        rules=[
            MappingRule("First Party Collection/Use", "Personal info"),
            MappingRule("Third Party Sharing/Collection", "Contacts"),
        ],
        version_label="scenario-v1",
    )
    mapped = list(mapper.map_all(gated))

    # The denial of location collection and the vague sentence are both mapped
    # to Personal info by the rules above. Location is handled separately
    # below so the scenario can exercise a declared-but-absent category.

    # --- F-16 ---------------------------------------------------------------
    declaration = normalise_declaration(
        [
            # Declared and described in the policy -> Consistent.
            DeclaredItem(1, "Personal info", "Email address", is_collected=True),
            # Declared but the policy never mentions it -> Declared-not-in-policy.
            DeclaredItem(2, "Calendar", "Calendar events", is_collected=True),
            # Declared, and the policy denies it -> Contradictory.
            DeclaredItem(3, "Location", "Precise location", is_collected=True),
        ]
    )

    # --- F-17 ---------------------------------------------------------------
    candidates = build_candidates(declaration, mapped)

    return segments, declaration, candidates


def test_scenario_produces_each_verdict():
    segments, declaration, candidates = _scenario()

    # --- F-18 would label the candidates. Here the labels are stated. -------
    judgements: dict[str, list[AlignmentJudgement]] = {}

    for candidate in candidates["Personal info"]:
        practice = candidate.mapped_practice
        assert practice is not None
        text = practice.segment.text

        if "email address" in text:
            label, confidence = "SUPPORTS", 0.93
        elif "never collect" in text:
            # A denial of location collection says nothing about email, so a
            # correct aligner reports no match for Personal info.
            label, confidence = "NO_MATCH", 0.87
        else:
            # The vague sentence. The practice was already abstained by the
            # gate, so whatever label is attached here it stays untrusted.
            label, confidence = "SUPPORTS", 0.71

        judgements.setdefault("Personal info", []).append(
            AlignmentJudgement(candidate, label, confidence)
        )

    for candidate in candidates["Contacts"]:
        judgements.setdefault("Contacts", []).append(
            AlignmentJudgement(candidate, "SUPPORTS", 0.9)
        )

    # Location is declared; the policy contains a denial of it. That sentence
    # is segment 2, and a correct aligner reports a contradiction.
    location_candidates = candidates["Location"]
    assert len(location_candidates) == 1, "declared with no mapped practice"
    judgements["Location"] = [
        AlignmentJudgement(location_candidates[0], "NO_MATCH", 0.9)
    ]

    results = {v.ds_category: v for v in assign_verdicts(declaration, judgements)}

    # Every category appears, whether or not either source mentioned it.
    assert len(results) == len(DS_CATEGORIES)

    # Declared and described: affirmative agreement, no evidence record.
    personal = results["Personal info"]
    assert personal.verdict == "Consistent"
    assert personal.consistency_basis == "affirmative_agreement"
    assert personal.records == ()
    assert personal.abstention_involved is True, (
        "the vague sentence abstained; that must be recorded even though it "
        "did not change the verdict"
    )

    # Described in the policy but never declared.
    contacts = results["Contacts"]
    assert contacts.verdict == "In-policy-not-declared"
    assert contacts.records[0].record_type == "evidence"
    assert contacts.records[0].quoted_text == SENTENCES[2]

    # Declared, and the policy says nothing about it.
    calendar = results["Calendar"]
    assert calendar.verdict == "Declared-not-in-policy"
    assert calendar.records[0].record_type == "absence"
    assert calendar.records[0].quoted_text is None

    # Declared, and no policy practice mapped to it at all.
    location = results["Location"]
    assert location.verdict == "Declared-not-in-policy"

    # Untouched by either source.
    messages = results["Messages"]
    assert messages.verdict == "Consistent"
    assert messages.consistency_basis == "neither_source_mentions"
    assert messages.records == ()


def test_scenario_abstains_where_the_gate_abstained():
    """The vague sentence must not produce a confident finding on its own.

    Here it is the only policy practice mapped to the category, so there is
    nothing else to fall back on and the verdict has to be Undetermined.
    """
    segments = _segments()
    vague = PolicyPractice(4, segments[3], "First Party Collection/Use", 0.34)
    gated = apply_threshold_to_all([vague], THRESHOLD)
    assert gated[0].abstained is True

    mapper = TaxonomyMapper(
        rules=[MappingRule("First Party Collection/Use", "Personal info")],
        version_label="scenario-v1",
    )
    mapped = list(mapper.map_all(gated))
    declaration = normalise_declaration(
        [DeclaredItem(1, "Personal info", "Email address", is_collected=True)]
    )
    candidates = build_candidates(declaration, mapped)

    # Even stated as a confident SUPPORTS, the judgement stays untrusted.
    judgement = AlignmentJudgement(candidates["Personal info"][0], "SUPPORTS", 0.95)
    assert judgement.abstained is True

    results = {
        v.ds_category: v
        for v in assign_verdicts(declaration, {"Personal info": [judgement]})
    }

    assert results["Personal info"].verdict == "Undetermined"
    assert results["Personal info"].records[0].record_type == "inconclusive"


def test_evidence_offsets_point_at_the_real_text():
    """Reconstruct the document and check that every evidence quote can be
    found at the offsets the record gives. This is what makes a finding
    checkable by a human reader."""
    document = "\n".join(SENTENCES)
    segments, declaration, candidates = _scenario()

    judgements = {
        "Contacts": [
            AlignmentJudgement(candidate, "SUPPORTS", 0.9)
            for candidate in candidates["Contacts"]
        ]
    }
    results = assign_verdicts(declaration, judgements)

    checked = 0
    for verdict in results:
        for record in verdict.records:
            if record.record_type != "evidence":
                continue
            assert record.quoted_text is not None
            assert (
                document[record.char_start : record.char_end] == record.quoted_text
            ), "evidence offsets do not locate the quoted text in the document"
            checked += 1

    assert checked > 0, "the scenario produced no evidence to check"
