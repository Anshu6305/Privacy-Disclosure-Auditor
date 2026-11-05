"""F-12 training data — spans extracted from the real OPP-115 annotations.

These read the actual corpus, so they are skipped where it is not present.
Everything asserted here is a property of the released data, not of a fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ml.data.opp115_spans import (
    ATTRIBUTE_FOR_SPAN_TYPE,
    DEFAULT_CORPUS,
    SPAN_TYPE_DATA_TYPE,
    SPAN_TYPE_PURPOSE,
    build_span_dataset,
    format_span_report,
)

CORPUS = Path(DEFAULT_CORPUS)
requires_corpus = pytest.mark.skipif(
    not (CORPUS / "annotations").is_dir(),
    reason="the OPP-115 corpus is not extracted at data/raw/opp115",
)


@pytest.fixture(scope="module")
def extracted():
    return build_span_dataset(CORPUS)


def test_only_two_attributes_are_treated_as_span_supervision():
    """An attribute added to the corpus must not silently become training
    data."""
    assert ATTRIBUTE_FOR_SPAN_TYPE == {
        "Personal Information Type": SPAN_TYPE_DATA_TYPE,
        "Purpose": SPAN_TYPE_PURPOSE,
    }


@requires_corpus
def test_both_span_types_have_substantial_supervision(extracted):
    _spans, report = extracted
    assert report.policies == 115
    assert report.by_type[SPAN_TYPE_DATA_TYPE] > 10_000
    assert report.by_type[SPAN_TYPE_PURPOSE] > 10_000


@requires_corpus
def test_every_kept_span_slices_back_out_of_its_segment(extracted):
    """The property the whole dataset rests on.

    A span that does not slice back would teach the model to point at the
    wrong words, and the resulting quote would not be the policy's text.
    """
    spans, _report = extracted
    from ml.data.opp115_schema import SEGMENT_SEPARATOR

    segments: dict[str, list[str]] = {}
    for path in (CORPUS / "sanitized_policies").glob("*.html"):
        segments[path.stem] = path.read_text(
            encoding="utf-8", errors="replace"
        ).split(SEGMENT_SEPARATOR)

    checked = 0
    for span in spans[:4000]:
        segment = segments[span.policy_id][span.segment_index]
        assert segment[span.start : span.end] == span.text
        checked += 1
    assert checked == 4000


@requires_corpus
def test_rejections_are_counted_rather_than_hidden(extracted):
    """A dataset that silently dropped supervision would misrepresent what
    the model was trained on."""
    _spans, report = extracted
    assert report.rejected > 0
    assert report.slice_mismatches > 0
    # Small enough that the corpus is usable, and reported either way.
    assert report.rejected / report.attributes_seen < 0.05


@requires_corpus
def test_span_free_values_are_not_counted_as_losses(extracted):
    """Those values carry no highlight by design: supervision the corpus never
    offered, not supervision that was lost."""
    _spans, report = extracted
    assert report.span_free_values > 1000
    assert report.span_free_values > report.rejected


@requires_corpus
def test_the_report_states_both_kept_and_rejected(extracted):
    _spans, report = extracted
    text = format_span_report(report)
    assert "spans kept" in text
    assert "total rejected" in text
    assert str(report.spans_kept) in text
