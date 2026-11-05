"""M6 — F-11 improved, F-12 span extraction, F-18 zero-shot alignment.

**No model is trained or loaded here.** Every backend is a deterministic stub,
so what these tests establish is that the decision logic, the offsets, the
abstention behaviour and the label mapping are correct. They say nothing
about accuracy: no encoder weights exist yet, and none of these numbers are
model results.
"""

from __future__ import annotations

import pytest

from analysis.alignment.nli import (
    NLI_TO_ALIGNMENT,
    NliPrediction,
    ZeroShotAligner,
    build_hypothesis,
)
from analysis.models.improved_classifier import (
    ImprovedClassifierConfig,
    ImprovedPracticeClassifier,
)
from analysis.models.span_extractor import (
    ExtractedSpan,
    SpanExtractor,
    TaggedToken,
    decode_bio,
)
from analysis.verdict.models import (
    AlignmentCandidate,
    DeclaredItem,
    MappedPolicyPractice,
    PolicyPractice,
    PolicySegmentRef,
)
from analysis.vocabulary import ALIGN_CONTRADICTS, ALIGN_NO_MATCH, ALIGN_SUPPORTS
from ml.data.opp115_spans import (
    SPAN_TYPE_DATA_TYPE,
    SPAN_TYPE_PURPOSE,
    LabelledSpan,
    bio_tags,
    to_document_offsets,
)

# ---------------------------------------------------------------------------
# F-12: BIO tagging and offsets
# ---------------------------------------------------------------------------

SEGMENT = "We collect your email address to send you marketing messages."


def span(span_type: str, start: int, end: int) -> LabelledSpan:
    return LabelledSpan(
        policy_id="p",
        segment_index=0,
        span_type=span_type,
        start=start,
        end=end,
        text=SEGMENT[start:end],
        value="v",
        category="First Party Collection/Use",
        annotator_id="a",
    )


def test_bio_tags_mark_the_highlighted_tokens():
    start = SEGMENT.index("email address")
    tags = bio_tags(SEGMENT, [span(SPAN_TYPE_DATA_TYPE, start, start + len("email address"))], SPAN_TYPE_DATA_TYPE)
    labelled = [(token, tag) for token, _s, _e, tag in tags if tag != "O"]
    assert labelled == [("email", "B-data_type"), ("address", "I-data_type")]


def test_tokens_outside_the_span_are_outside():
    start = SEGMENT.index("email address")
    tags = bio_tags(SEGMENT, [span(SPAN_TYPE_DATA_TYPE, start, start + 13)], SPAN_TYPE_DATA_TYPE)
    assert tags[0][3] == "O"


def test_only_the_requested_span_type_is_tagged():
    data_start = SEGMENT.index("email address")
    purpose_start = SEGMENT.index("marketing messages")
    spans = [
        span(SPAN_TYPE_DATA_TYPE, data_start, data_start + 13),
        span(SPAN_TYPE_PURPOSE, purpose_start, purpose_start + 18),
    ]
    tags = bio_tags(SEGMENT, spans, SPAN_TYPE_PURPOSE)
    assert {tag for _t, _s, _e, tag in tags if tag != "O"} == {
        "B-purpose",
        "I-purpose",
    }


def test_overlapping_spans_of_one_type_take_the_earliest():
    """Three annotators per policy; their highlights can overlap, and a token
    cannot begin two spans at once."""
    start = SEGMENT.index("email address")
    spans = [
        span(SPAN_TYPE_DATA_TYPE, start, start + 13),
        span(SPAN_TYPE_DATA_TYPE, start + 6, start + 13),
    ]
    tags = [tag for _t, _s, _e, tag in bio_tags(SEGMENT, spans, SPAN_TYPE_DATA_TYPE)]
    assert tags.count("B-data_type") == 1


def test_offsets_translate_into_document_coordinates():
    """OPP-115 indexes a segment; M4 indexes the cleaned document."""
    document = "Intro paragraph. " + SEGMENT
    shift = document.index(SEGMENT)
    start = SEGMENT.index("email address")
    doc_start, doc_end = to_document_offsets(start, start + 13, shift)
    assert document[doc_start:doc_end] == "email address"


def test_a_backwards_span_is_rejected():
    with pytest.raises(ValueError, match="not a span"):
        to_document_offsets(10, 5, 0)


# ---------------------------------------------------------------------------
# F-12: decoding tags back into verifiable spans
# ---------------------------------------------------------------------------


class StubTagger:
    """Tags tokens from a fixed map. No model involved."""

    def __init__(self, tag_for: dict[str, tuple[str, float]]) -> None:
        self._tag_for = tag_for

    def tag(self, tokens):
        return [
            TaggedToken(token, start, end, *self._tag_for.get(token.strip(".,"), ("O", 1.0)))
            for token, start, end in tokens
        ]


def test_decoded_spans_slice_out_of_the_document():
    document = "Intro. " + SEGMENT
    shift = document.index(SEGMENT)
    extractor = SpanExtractor(
        StubTagger({"email": ("B-data_type", 0.9), "address": ("I-data_type", 0.9)})
    )
    (found,) = extractor.extract(SEGMENT, document, shift)

    assert found.text == "email address"
    assert document[found.start : found.end] == "email address"
    assert found.verify_against(document) is True


def test_a_low_confidence_span_is_flagged_not_dropped():
    document = SEGMENT
    extractor = SpanExtractor(
        StubTagger({"email": ("B-data_type", 0.3), "address": ("I-data_type", 0.3)})
    )
    (found,) = extractor.extract(SEGMENT, document, 0)
    assert found.abstained is True
    assert found.text == "email address"


def test_a_leading_i_tag_still_opens_a_span():
    """Taggers produce this; losing a real span to a formatting detail would
    be worse than opening one."""
    spans = decode_bio(
        [TaggedToken("email", 0, 5, "I-data_type", 0.8)], "email address", threshold=0.5
    )
    assert len(spans) == 1
    assert spans[0].text == "email"


def test_a_mismatched_segment_offset_is_refused():
    """The offsets would point at the wrong words while still looking valid."""
    extractor = SpanExtractor(StubTagger({}))
    with pytest.raises(ValueError, match="not the slice"):
        extractor.extract(SEGMENT, "a completely different document", 0)


def test_verify_against_fails_when_the_document_changed():
    found = ExtractedSpan(
        span_type=SPAN_TYPE_DATA_TYPE, start=0, end=5, text="email", confidence=0.9
    )
    assert found.verify_against("email address") is True
    assert found.verify_against("other text here") is False


def test_an_unknown_span_type_is_rejected():
    with pytest.raises(ValueError, match="unknown span type"):
        ExtractedSpan(span_type="sentiment", start=0, end=1, text="x", confidence=0.5)


# ---------------------------------------------------------------------------
# F-18: hypothesis construction and label mapping
# ---------------------------------------------------------------------------


def test_the_hypothesis_states_the_declaration():
    assert build_hypothesis("Location", collected=True, shared=False) == (
        "This app collects Location."
    )
    assert build_hypothesis("Location", collected=True, shared=True) == (
        "This app collects Location and shares it with third parties."
    )
    assert build_hypothesis("Location", collected=False, shared=True) == (
        "This app shares Location with third parties."
    )


def test_a_denial_is_phrased_as_a_denial():
    """Phrasing it positively and relying on CONTRADICTS would invert the
    judgement."""
    assert build_hypothesis("Location", collected=False, shared=False) == (
        "This app does not collect or share Location."
    )


def test_the_approved_three_labels_map_from_nli():
    assert NLI_TO_ALIGNMENT == {
        "entailment": ALIGN_SUPPORTS,
        "contradiction": ALIGN_CONTRADICTS,
        "neutral": ALIGN_NO_MATCH,
    }


def make_candidate(*, with_practice: bool = True, abstained: bool = False):
    practice = None
    if with_practice:
        practice = MappedPolicyPractice(
            practice=PolicyPractice(
                practice_id=1,
                segment=PolicySegmentRef(
                    segment_id=1,
                    text="We collect your precise location to show nearby offers.",
                    char_start=0,
                    char_end=55,
                ),
                opp115_category="First Party Collection/Use",
                confidence=0.8,
                abstained=abstained,
            ),
            ds_category="Location",
        )
    return AlignmentCandidate(
        ds_category="Location",
        declared_item=DeclaredItem(
            declared_practice_id=1,
            ds_category="Location",
            is_collected=True,
            is_shared=False,
        ),
        mapped_practice=practice,
    )


class StubNli:
    def __init__(self, prediction: NliPrediction) -> None:
        self.prediction = prediction
        self.pairs: list[tuple[str, str]] = []

    def predict(self, pairs):
        self.pairs = list(pairs)
        return [self.prediction] * len(pairs)


def test_the_premise_is_the_policy_sentence_verbatim():
    backend = StubNli(NliPrediction(0.9, 0.05, 0.05))
    ZeroShotAligner(backend).judge([make_candidate()])
    (premise, hypothesis) = backend.pairs[0]
    assert premise == "We collect your precise location to show nearby offers."
    assert hypothesis == "This app collects Location."


@pytest.mark.parametrize(
    "prediction,expected",
    [
        (NliPrediction(0.9, 0.05, 0.05), ALIGN_SUPPORTS),
        (NliPrediction(0.05, 0.05, 0.9), ALIGN_CONTRADICTS),
        (NliPrediction(0.05, 0.9, 0.05), ALIGN_NO_MATCH),
    ],
)
def test_each_nli_outcome_becomes_its_approved_label(prediction, expected):
    (judgement,) = ZeroShotAligner(StubNli(prediction)).judge([make_candidate()])
    assert judgement.label == expected
    assert judgement.abstained is False


def test_a_low_confidence_judgement_keeps_its_label_and_flags_abstention():
    """Rewriting it as NO_MATCH would turn "unsure" into "the policy is
    silent", which ALG-8 treats very differently."""
    (judgement,) = ZeroShotAligner(StubNli(NliPrediction(0.4, 0.35, 0.25))).judge(
        [make_candidate()]
    )
    assert judgement.label == ALIGN_SUPPORTS
    assert judgement.model_abstained is True
    assert judgement.abstained is True


def test_upstream_abstention_propagates_even_on_a_confident_judgement():
    """The structural rule: no caller can produce a confident judgement from
    an uncertain input."""
    (judgement,) = ZeroShotAligner(StubNli(NliPrediction(0.95, 0.03, 0.02))).judge(
        [make_candidate(abstained=True)]
    )
    assert judgement.model_abstained is False
    assert judgement.abstained is True


def test_a_candidate_with_no_premise_is_never_confidently_no_match():
    """The model was never consulted, so a confident NO_MATCH would be a claim
    nobody made."""
    backend = StubNli(NliPrediction(0.9, 0.05, 0.05))
    (judgement,) = ZeroShotAligner(backend).judge([make_candidate(with_practice=False)])
    assert judgement.label == ALIGN_NO_MATCH
    assert judgement.confidence == 0.0
    assert judgement.abstained is True
    assert backend.pairs == []


def test_a_backend_returning_the_wrong_count_is_an_error():
    class Broken:
        def predict(self, pairs):
            return []

    with pytest.raises(ValueError, match="returned 0 predictions"):
        ZeroShotAligner(Broken()).judge([make_candidate()])


# ---------------------------------------------------------------------------
# F-11 improved
# ---------------------------------------------------------------------------


class StubEncoder:
    def __init__(self, row: list[float]) -> None:
        self.row = row

    def predict_proba(self, texts):
        return [list(self.row) for _ in texts]


def classifier(row: list[float], threshold: float = 0.5):
    config = ImprovedClassifierConfig(decision_threshold=threshold)
    return ImprovedPracticeClassifier(StubEncoder(row), config), config


def test_every_category_is_scored_not_only_the_predicted_ones():
    """"The classifier looked and found nothing" and "the classifier was never
    asked" are different, and only a complete score vector distinguishes
    them."""
    model, config = classifier([0.9] + [0.01] * (len(ImprovedClassifierConfig().categories) - 1))
    (row,) = model.predict(["some policy text"])
    assert len(row) == len(config.categories)
    assert sum(1 for score in row if score.predicted) == 1


def test_the_classifier_does_not_decide_abstention():
    """F-14 owns that decision, exactly as it does for the M5 baseline.

    Setting it here as well would put one rule in two places, which is what
    the M5 authorisation forbade.
    """
    from analysis.confidence.gate import apply_threshold_to_all

    model, _ = classifier([0.3] + [0.9] * (len(ImprovedClassifierConfig().categories) - 1))
    segment = PolicySegmentRef(segment_id=1, text="text", char_start=0, char_end=4)
    practices = model.predict_practices(segment)

    assert all(practice.abstained is False for practice in practices)

    gated = apply_threshold_to_all(practices, 0.5)
    assert gated[0].abstained is True
    assert all(practice.abstained is False for practice in gated[1:])
    assert len(gated) == len(practices)


def test_the_improved_variant_matches_the_baseline_contract():
    """A drop-in replacement: same call, same output type, same flags."""
    model, _ = classifier([0.9] * len(ImprovedClassifierConfig().categories))
    segment = PolicySegmentRef(segment_id=7, text="text", char_start=0, char_end=4)
    practices = model.predict_practices(segment, first_practice_id=100)

    assert practices[0].practice_id == 100
    assert practices[0].segment is segment
    assert isinstance(practices[0], PolicyPractice)


def test_predict_labels_returns_only_what_crossed_the_threshold():
    categories = ImprovedClassifierConfig().categories
    model, _ = classifier([0.9, 0.8] + [0.01] * (len(categories) - 2))
    assert model.predict_labels(["text"]) == [(categories[0], categories[1])]


def test_empty_input_returns_empty():
    model, _ = classifier([0.9] * len(ImprovedClassifierConfig().categories))
    assert model.predict([]) == []


def test_a_backend_returning_the_wrong_width_is_an_error():
    model = ImprovedPracticeClassifier(StubEncoder([0.5, 0.5]))
    with pytest.raises(ValueError, match="scores for"):
        model.predict(["text"])


def test_the_configuration_is_recorded_for_reproducibility():
    metadata = ImprovedClassifierConfig().as_metadata()
    assert metadata["model_variant"] == "improved"
    assert metadata["random_seed"] == 20261105
    assert metadata["threshold_is_provisional"] is True
