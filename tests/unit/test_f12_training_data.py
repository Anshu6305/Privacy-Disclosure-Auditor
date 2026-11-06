"""F-12's tagged dataset and value-carrying BIO tags.

The dataset build is also exercised against the real corpus, but only where
that is cheap: the expensive full build is one test, marked so it can be
deselected, and the logic tests use hand-written spans.
"""

from __future__ import annotations

import pytest

from analysis.models.span_extractor import TaggedToken, decode_bio
from ml.data.opp115_spans import LabelledSpan
from ml.data.span_training_data import (
    OUTSIDE,
    TaggedSegment,
    label_set,
    tag_segment,
)

TEXT = "We collect your location to show nearby shops."


def span(span_type, value, start, end):
    return LabelledSpan(
        policy_id="p1",
        segment_index=0,
        span_type=span_type,
        start=start,
        end=end,
        text=TEXT[start:end],
        value=value,
        category="First Party Collection/Use",
        annotator_id="a1",
    )


# -- tagging ----------------------------------------------------------------


def test_a_tag_names_the_attribute_value_not_only_the_span_type():
    """F-15's rules are keyed on the value.

    A tagger that learned `B-data_type` alone would produce spans no rule
    could ever match, so the value is part of the label and not metadata
    attached afterwards.
    """
    tokens, offsets, tags = tag_segment(TEXT, [span("data_type", "Location", 16, 24)])
    assert tags[tokens.index("location")] == "B-data_type:Location"
    assert offsets[tokens.index("location")] == (16, 24)


def test_both_span_types_share_one_tag_sequence():
    tokens, _offsets, tags = tag_segment(
        TEXT,
        [span("data_type", "Location", 16, 24), span("purpose", "Basic service/feature", 25, 45)],
    )
    assert "B-data_type:Location" in tags
    assert "B-purpose:Basic service/feature" in tags
    assert tags.count(OUTSIDE) == len(tokens) - sum(
        1 for tag in tags if tag != OUTSIDE
    )


def test_an_overlap_is_resolved_to_the_earliest_longest_span():
    """Three annotators per policy, and their highlights collide.

    A token cannot begin two spans at once. Dropping the collision instead
    would lose real supervision over a disagreement between annotators.
    """
    _tokens, _offsets, tags = tag_segment(
        TEXT,
        [
            span("data_type", "Location", 16, 24),
            span("data_type", "Generic personal information", 19, 30),
        ],
    )
    values = {tag.partition(":")[2] for tag in tags if tag != OUTSIDE}
    assert values == {"Location"}


def test_a_span_with_no_value_is_not_tagged():
    """An unvalued span cannot key a rule, so training on it would teach the
    model to emit something F-15 must then ignore."""
    _tokens, _offsets, tags = tag_segment(TEXT, [span("data_type", "", 16, 24)])
    assert set(tags) == {OUTSIDE}


def test_label_set_puts_outside_first_and_derives_the_rest_from_the_data():
    segment = TaggedSegment(
        policy_id="p1",
        segment_index=0,
        text=TEXT,
        tokens=("We", "collect"),
        offsets=((0, 2), (3, 10)),
        tags=(OUTSIDE, "B-data_type:Location"),
    )
    assert label_set([segment]) == [OUTSIDE, "B-data_type:Location"]


def test_a_segment_whose_offsets_do_not_slice_out_is_rejected():
    segment = TaggedSegment(
        policy_id="p1",
        segment_index=0,
        text=TEXT,
        tokens=("We", "wrong"),
        offsets=((0, 2), (3, 10)),
        tags=(OUTSIDE, OUTSIDE),
    )
    assert segment.verify_offsets() is False


def test_tokens_offsets_and_tags_must_be_the_same_length():
    with pytest.raises(ValueError, match="tokens"):
        TaggedSegment(
            policy_id="p1",
            segment_index=0,
            text=TEXT,
            tokens=("We",),
            offsets=((0, 2), (3, 10)),
            tags=(OUTSIDE,),
        )


# -- decoding the value back out --------------------------------------------


def tagged(word, start, end, tag, confidence=0.9):
    return TaggedToken(token=word, start=start, end=end, tag=tag, confidence=confidence)


def test_decode_recovers_the_value_from_a_compound_tag():
    spans = decode_bio(
        [tagged("location", 16, 24, "B-data_type:Location")], TEXT, threshold=0.5
    )
    assert len(spans) == 1
    assert spans[0].value == "Location"
    assert spans[0].span_type == "data_type"
    assert spans[0].text == "location"


def test_decode_still_accepts_a_plain_tag_and_leaves_the_value_unset():
    """A boundary-only tagger is still useful as evidence, just not mappable."""
    spans = decode_bio([tagged("location", 16, 24, "B-data_type")], TEXT, threshold=0.5)
    assert spans[0].value is None


def test_a_change_of_value_closes_the_span():
    """Two adjacent tokens with different values are two spans, even under
    I- tags. Merging them would attribute one value to text annotated with
    another."""
    spans = decode_bio(
        [
            tagged("your", 11, 15, "B-data_type:Contact"),
            tagged("location", 16, 24, "I-data_type:Location"),
        ],
        TEXT,
        threshold=0.5,
    )
    assert [s.value for s in spans] == ["Contact", "Location"]


def test_a_low_confidence_span_is_kept_and_flagged():
    spans = decode_bio(
        [tagged("location", 16, 24, "B-data_type:Location", confidence=0.2)],
        TEXT,
        threshold=0.5,
    )
    assert spans[0].abstained is True
    assert spans[0].text == "location"


# -- the real corpus --------------------------------------------------------


@pytest.mark.slow
def test_the_real_dataset_builds_and_every_offset_verifies():
    from ml.data.span_training_data import build_tagged_segments, split_segments

    segments = build_tagged_segments()
    assert len(segments) > 2000
    assert all(segment.verify_offsets() for segment in segments)

    split = split_segments(segments)
    train = {s.policy_id for s in split.train}
    test = {s.policy_id for s in split.test}
    validation = {s.policy_id for s in split.validation}
    assert not train & test, "a policy appears in both train and test"
    assert not train & validation
    assert not validation & test
