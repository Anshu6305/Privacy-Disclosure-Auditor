"""F-10 — analysability validation, and T2 end to end.

An unanalysable policy must stop the audit with a recorded reason. Fourteen
Consistent verdicts because neither source mentioned anything looks identical
to fourteen Consistent verdicts because the policy was an error page, and only
one of those is a finding.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from acquisition.corpus import read_record
from acquisition.models import PolicyDocument
from acquisition.policy_document import load_policy_document
from analysis.text.models import (
    PROVISIONAL_THRESHOLDS,
    AnalysabilityResult,
    AnalysabilityThresholds,
    PolicySegment,
)
from analysis.text.pipeline import (
    process_policy_document,
    write_cleaned_text,
)
from analysis.text.segmenter import load_sentencizer, verify_segments
from analysis.text.validator import (
    ThresholdConfigurationError,
    thresholds_from_config,
    validate_analysability,
)

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_corpus"
TIGHT = AnalysabilityThresholds(min_segments=3, min_tokens=40)


@pytest.fixture(scope="module")
def nlp():
    return load_sentencizer()


def make_segments(count: int, tokens_each: int) -> list[PolicySegment]:
    segments = []
    cursor = 0
    for index in range(count):
        text = " ".join(["word"] * tokens_each) or "x"
        segments.append(
            PolicySegment(index, text, cursor, cursor + len(text), tokens_each)
        )
        cursor += len(text) + 2
    return segments


# ---------------------------------------------------------------------------
# Rejection
# ---------------------------------------------------------------------------


def test_empty_segment_list_is_rejected():
    result = validate_analysability([], thresholds=TIGHT)

    assert result.analysable is False
    assert "no segments" in result.reason
    assert result.segment_count == 0
    assert result.token_count == 0


def test_zero_token_input_is_rejected():
    segments = [PolicySegment(0, "---", 0, 3, token_count=0)]
    result = validate_analysability(segments, thresholds=TIGHT)

    assert result.analysable is False
    assert "no tokens" in result.reason


def test_below_minimum_segment_count_is_rejected_with_the_numbers():
    result = validate_analysability(make_segments(2, 50), thresholds=TIGHT)

    assert result.analysable is False
    assert "2 segment(s), below the minimum of 3" in result.reason


def test_below_minimum_token_count_is_rejected_with_the_numbers():
    result = validate_analysability(make_segments(5, 2), thresholds=TIGHT)

    assert result.analysable is False
    assert "10 token(s), below the minimum of 40" in result.reason


def test_both_thresholds_failed_reports_both():
    result = validate_analysability(make_segments(1, 3), thresholds=TIGHT)

    assert result.analysable is False
    assert "segment(s), below" in result.reason
    assert "token(s), below" in result.reason


def test_rejection_reason_suggests_what_the_document_probably_is():
    result = validate_analysability(make_segments(1, 5), thresholds=TIGHT)
    assert "error page" in result.reason


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def test_exactly_at_the_segment_minimum_passes():
    result = validate_analysability(make_segments(3, 20), thresholds=TIGHT)
    assert result.analysable is True


def test_one_below_the_segment_minimum_fails():
    assert validate_analysability(make_segments(2, 100), thresholds=TIGHT).analysable is False


def test_exactly_at_the_token_minimum_passes():
    result = validate_analysability(make_segments(4, 10), thresholds=TIGHT)
    assert result.token_count == 40
    assert result.analysable is True


def test_one_below_the_token_minimum_fails():
    result = validate_analysability(
        make_segments(4, 10)[:3] + [PolicySegment(3, "w " * 4, 500, 500 + 8, 9)],
        thresholds=TIGHT,
    )
    assert result.token_count == 39
    assert result.analysable is False


def test_both_thresholds_satisfied_returns_an_explicit_success():
    result = validate_analysability(make_segments(10, 20), thresholds=TIGHT)

    assert result.analysable is True
    assert "meeting the minimums of 3 and 40" in result.reason
    assert result.thresholds == TIGHT


def test_a_successful_result_still_carries_a_reason():
    with pytest.raises(ValueError, match="always carry a reason"):
        AnalysabilityResult(analysable=True, reason="", segment_count=1, token_count=1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_missing_thresholds_raise_rather_than_defaulting():
    """A threshold nobody chose is not a configured minimum."""
    with pytest.raises(ThresholdConfigurationError, match="No thresholds supplied"):
        validate_analysability(make_segments(5, 20))


def test_provisional_values_must_be_asked_for_explicitly():
    result = validate_analysability(make_segments(5, 20), allow_provisional=True)

    assert result.analysable is True
    assert result.thresholds == PROVISIONAL_THRESHOLDS


def test_missing_config_raises_unless_provisional_is_allowed():
    with pytest.raises(ThresholdConfigurationError, match="No analysability thresholds"):
        thresholds_from_config(None)
    assert thresholds_from_config(None, allow_provisional=True) == PROVISIONAL_THRESHOLDS


def test_config_missing_a_key_is_rejected():
    with pytest.raises(ThresholdConfigurationError, match="missing \\['min_tokens'\\]"):
        thresholds_from_config({"min_segments": 2})


@pytest.mark.parametrize("bad", ["5", 5.0, None, True])
def test_non_integer_threshold_is_rejected(bad):
    with pytest.raises(ThresholdConfigurationError, match="must be an integer"):
        thresholds_from_config({"min_segments": bad, "min_tokens": 50})


@pytest.mark.parametrize("value", [0, -1])
def test_zero_or_negative_threshold_is_rejected(value):
    """A threshold of zero would accept an empty document."""
    with pytest.raises(ThresholdConfigurationError, match="at least 1"):
        thresholds_from_config({"min_segments": value, "min_tokens": 50})


def test_config_mapping_is_accepted():
    assert thresholds_from_config({"min_segments": 4, "min_tokens": 99}) == (
        AnalysabilityThresholds(4, 99)
    )


def test_non_mapping_config_is_rejected():
    with pytest.raises(ThresholdConfigurationError, match="must be a mapping"):
        thresholds_from_config([1, 2])


def test_provisional_values_are_labelled_as_such():
    assert PROVISIONAL_THRESHOLDS.min_segments == 1
    assert PROVISIONAL_THRESHOLDS.min_tokens == 50
    from analysis.text import models
    assert "provisional" in models.AnalysabilityThresholds.__doc__.lower()


# ---------------------------------------------------------------------------
# T2 end to end: F-05 → F-08 → F-09 → F-10
# ---------------------------------------------------------------------------


def test_pipeline_over_the_sample_fixture(nlp):
    """Controlled fixture, not a real application audit."""
    record = read_record(SAMPLE / "apps" / "com.example.sampleapp" / "record.json")
    document = load_policy_document(
        record.package_name, SAMPLE / record.policy_path, record.policy_url,
        expected_sha256=record.policy_sha256,
    )

    processed = process_policy_document(document, allow_provisional=True, nlp=nlp)

    assert processed.extraction.succeeded
    assert processed.analysability.analysable
    assert processed.ready_for_analysis
    assert len(processed.segments) == 12
    assert verify_segments(processed.cleaned_text, list(processed.segments)) == []
    assert "We collect your email address" in processed.cleaned_text


def test_pipeline_offsets_index_the_cleaned_text(nlp):
    record = read_record(SAMPLE / "apps" / "com.example.sampleapp" / "record.json")
    document = load_policy_document(
        record.package_name, SAMPLE / record.policy_path, record.policy_url
    )
    processed = process_policy_document(document, allow_provisional=True, nlp=nlp)

    for s in processed.segments:
        assert processed.cleaned_text[s.char_start : s.char_end] == s.text


def test_pipeline_records_why_an_unreadable_document_stopped(nlp):
    document = PolicyDocument(
        package_name="com.example.broken",
        source_url="https://example.invalid/p",
        content="<html><head><script>render()</script></head><body></body></html>",
        content_sha256="c" * 64,
        storage_path="/x.html",
        media_type="text/html",
    )
    processed = process_policy_document(document, allow_provisional=True, nlp=nlp)

    assert processed.ready_for_analysis is False
    assert processed.segments == ()
    assert "Text extraction failed" in processed.analysability.reason
    assert "loads from a script" in processed.analysability.reason


def test_pipeline_rejects_a_too_short_document(nlp):
    document = PolicyDocument(
        package_name="com.example.stub",
        source_url="https://example.invalid/p",
        content="<html><body><p>404 Not Found</p></body></html>",
        content_sha256="d" * 64,
        storage_path="/x.html",
        media_type="text/html",
    )
    processed = process_policy_document(document, allow_provisional=True, nlp=nlp)

    assert processed.extraction.succeeded, "the page does have text"
    assert processed.analysability.analysable is False
    assert "too little usable text" in processed.analysability.reason


def test_cleaned_text_is_written_for_later_highlighting(tmp_path, nlp):
    """F-25 highlights evidence, which needs the document the offsets index."""
    record = read_record(SAMPLE / "apps" / "com.example.sampleapp" / "record.json")
    document = load_policy_document(
        record.package_name, SAMPLE / record.policy_path, record.policy_url
    )
    processed = process_policy_document(document, allow_provisional=True, nlp=nlp)

    path = write_cleaned_text(processed, tmp_path)

    assert path.name == f"{record.policy_sha256}.txt"
    stored = path.read_text(encoding="utf-8")
    assert stored == processed.cleaned_text
    for s in processed.segments:
        assert stored[s.char_start : s.char_end] == s.text


def test_cleaned_text_is_not_written_when_extraction_failed(tmp_path, nlp):
    document = PolicyDocument(
        package_name="com.example.empty", source_url="https://x.invalid",
        content="", content_sha256="e" * 64, storage_path="/x.html",
        media_type="text/html",
    )
    processed = process_policy_document(document, allow_provisional=True, nlp=nlp)

    with pytest.raises(ValueError, match="extraction failed"):
        write_cleaned_text(processed, tmp_path)
