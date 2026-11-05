"""F-09 — segmentation, and the offset guarantees the audit report depends on.

The offsets index the **cleaned text produced by F-08**. Every test that
checks an offset does so by slicing that exact string, because an offset that
is not verified by slicing has not been verified at all.
"""

from __future__ import annotations

import pytest

from analysis.text.extractor import extract_policy_text
from analysis.text.models import PolicySegment
from analysis.text.segmenter import (
    DEFAULT_MAX_SEGMENT_CHARS,
    count_tokens_in,
    load_sentencizer,
    segment_policy_text,
    verify_segments,
)


@pytest.fixture(scope="module")
def nlp():
    return load_sentencizer()


def segment(text: str, **kwargs) -> list[PolicySegment]:
    return segment_policy_text(text, **kwargs)


# ---------------------------------------------------------------------------
# Offsets — the critical property
# ---------------------------------------------------------------------------


def test_offsets_locate_the_exact_text_by_slicing(nlp):
    text = (
        "Privacy Policy\n\n"
        "We collect your email address.\n\n"
        "We share it with no one."
    )
    segments = segment(text, nlp=nlp)

    for s in segments:
        assert text[s.char_start : s.char_end] == s.text, (
            f"segment {s.sequence_number} offsets do not locate its text"
        )


def test_no_sentence_is_lost_or_duplicated(nlp):
    """Every non-whitespace character belongs to exactly one segment."""
    text = (
        "Section One\n\n"
        "We collect your email address. We also collect your name.\n\n"
        "Section Two\n\n"
        "We share data with partners. We do not sell data."
    )
    segments = segment(text, nlp=nlp)

    assert verify_segments(text, segments) == []

    for index, character in enumerate(text):
        if character.isspace():
            continue
        owners = [s for s in segments if s.char_start <= index < s.char_end]
        assert len(owners) == 1, (
            f"character {index} ({character!r}) is in {len(owners)} segments"
        )


def test_segments_are_ordered_and_do_not_overlap(nlp):
    text = "\n\n".join(f"Paragraph number {i} has some text in it." for i in range(8))
    segments = segment(text, nlp=nlp)

    assert [s.sequence_number for s in segments] == list(range(len(segments)))
    for earlier, later in zip(segments, segments[1:], strict=False):
        assert later.char_start >= earlier.char_end


def test_text_is_never_altered(nlp):
    """F-20 quotes this text verbatim into the report."""
    text = "We collect Your Email Address, e.g. for NOTIFICATIONS.\n\nAnd more."
    segments = segment(text, nlp=nlp)

    rebuilt = " ".join(s.text for s in segments)
    assert "Your Email Address" in rebuilt
    assert "NOTIFICATIONS" in rebuilt
    assert not any(s.text != s.text.strip() for s in segments)


def test_segment_rejects_offsets_that_do_not_match_its_text():
    with pytest.raises(ValueError, match="point at the wrong part"):
        PolicySegment(0, "twenty characters!!!", 0, 5)


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_single_sentence_produces_one_segment(nlp):
    segments = segment("We collect your email address.", nlp=nlp)

    assert len(segments) == 1
    assert segments[0].sequence_number == 0
    assert segments[0].char_start == 0
    assert segments[0].text == "We collect your email address."


def test_multiple_paragraphs_produce_one_segment_each(nlp):
    text = "First paragraph here.\n\nSecond paragraph here.\n\nThird one."
    segments = segment(text, nlp=nlp)

    assert len(segments) == 3
    assert [s.text for s in segments] == [
        "First paragraph here.", "Second paragraph here.", "Third one.",
    ]


def test_multiple_sentences_in_one_paragraph_stay_together(nlp):
    """A paragraph is the analysis unit when it fits; splitting every
    sentence would strip each of its context."""
    text = "We collect email. We collect names. We collect addresses."
    segments = segment(text, nlp=nlp)

    assert len(segments) == 1
    assert segments[0].text == text


def test_long_paragraph_splits_at_sentence_boundaries(nlp):
    sentence = "We collect a particular kind of personal information from you. "
    text = (sentence * 40).strip()
    segments = segment(text, max_segment_chars=200, nlp=nlp)

    assert len(segments) > 1
    for s in segments:
        assert s.text.endswith("."), "a split landed mid-sentence"
        assert text[s.char_start : s.char_end] == s.text


def test_a_single_overlong_sentence_is_kept_whole(nlp):
    """Half a sentence is not quotable evidence."""
    text = "We collect " + "data and more data and " * 40 + "finally your email."
    segments = segment(text, max_segment_chars=100, nlp=nlp)

    assert len(segments) == 1
    assert segments[0].text == text


def test_headings_become_segments_and_label_what_follows(nlp):
    """A heading such as 'Information we share' is itself a statement about a
    data practice, so it is kept rather than dropped."""
    text = "Information we share\n\nWe share your contacts with partners."
    segments = segment(text, nlp=nlp)

    assert segments[0].text == "Information we share"
    assert segments[1].heading == "Information we share"


def test_bullet_list_items_survive_extraction_and_segmentation(nlp):
    extracted = extract_policy_text(
        "<h2>We collect</h2><ul><li>Email address</li><li>Precise location</li></ul>"
    )
    segments = segment(extracted.text, nlp=nlp)
    texts = [s.text for s in segments]

    assert "Email address" in texts
    assert "Precise location" in texts


def test_abbreviations_do_not_split_a_sentence(nlp):
    """'e.g.' and 'Inc.' are the reason the design specifies spaCy."""
    text = (
        "We share data with partners, e.g. Example Inc. and others, for "
        "analytics purposes. We do not sell it."
    )
    segments = segment(text, max_segment_chars=60, nlp=nlp)

    first = segments[0].text
    assert "e.g." in first
    assert first.endswith("purposes.") or len(segments) == 1


def test_punctuation_and_quotes_are_preserved(nlp):
    text = 'We call this "personal data" (as defined below); see section 3.'
    segments = segment(text, nlp=nlp)

    assert segments[0].text == text


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_input_produces_no_segments(nlp):
    """Phase 3: no sentences produces an empty list, handled by F-10."""
    assert segment("", nlp=nlp) == []
    assert segment("   \n\n  ", nlp=nlp) == []


def test_blank_paragraphs_are_skipped(nlp):
    text = "First.\n\n\n\n\n\nSecond."
    segments = segment(text, nlp=nlp)

    assert [s.text for s in segments] == ["First.", "Second."]
    assert verify_segments(text, segments) == []


def test_leading_and_trailing_whitespace_is_excluded_from_offsets(nlp):
    text = "\n\n   We collect your email.   \n\n"
    segments = segment(text, nlp=nlp)

    assert segments[0].text == "We collect your email."
    assert text[segments[0].char_start : segments[0].char_end] == segments[0].text


def test_invalid_max_segment_chars_is_rejected(nlp):
    with pytest.raises(ValueError, match="at least 1"):
        segment("Some text.", max_segment_chars=0, nlp=nlp)


def test_token_counts_are_recorded(nlp):
    segments = segment("We collect your email address.", nlp=nlp)

    assert segments[0].token_count == count_tokens_in(
        "We collect your email address.", nlp
    )
    assert segments[0].token_count > 0


def test_default_segment_size_is_documented():
    assert DEFAULT_MAX_SEGMENT_CHARS == 1000


def test_segmentation_is_deterministic(nlp):
    text = "First sentence here. Second sentence here.\n\nAnother paragraph."
    first = segment(text, nlp=nlp)
    second = segment(text, nlp=nlp)

    assert [(s.text, s.char_start, s.char_end) for s in first] == [
        (s.text, s.char_start, s.char_end) for s in second
    ]


def test_segment_converts_to_the_verdict_layer_reference(nlp):
    """The same offset invariant holds on both sides."""
    segments = segment("We collect your email address.", nlp=nlp)
    ref = segments[0].to_segment_ref(segment_id=7)

    assert ref.segment_id == 7
    assert ref.text == segments[0].text
    assert ref.char_start == segments[0].char_start


def test_verify_segments_detects_a_broken_offset(nlp):
    """The checker must actually catch a fault, not just pass on good input."""
    text = "We collect your email address.\n\nWe share nothing."
    segments = segment(text, nlp=nlp)
    tampered = [
        segments[0],
        PolicySegment(1, segments[1].text, 0, len(segments[1].text)),
    ]

    problems = verify_segments(text, tampered)
    assert problems, "a wrong offset was not detected"
