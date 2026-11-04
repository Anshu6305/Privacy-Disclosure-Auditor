"""Tests for the OPP-115 verification logic.

These use synthetic rows, not the corpus. The corpus is not committed, so any
test that required it would fail in a fresh checkout and on the grading
machine. The real corpus is checked by running the script, and its output is
recorded in ml/data/opp115_manifest.json.
"""

import json

import pytest

from ml.data.opp115_schema import CATEGORIES, EXPECTED_COLUMN_COUNT, SPAN_FREE_VALUES
from ml.data.verify_opp115 import Report, inspect_attributes, verify


def make_report() -> Report:
    from pathlib import Path

    return Report(corpus_path=Path("unused"))


def test_span_free_values_are_not_counted_as_errata():
    """'Unspecified', 'not-selected' and 'Does' legitimately carry no span.

    Counting them as damage would understate available supervision by almost
    half, which is the mistake this test exists to prevent.
    """
    report = make_report()
    for value in sorted(SPAN_FREE_VALUES):
        inspect_attributes(json.dumps({"Attr": {"value": value}}), report)

    assert report.spans_total == len(SPAN_FREE_VALUES)
    assert report.spans_absent_by_design == len(SPAN_FREE_VALUES)
    assert sum(report.span_errata.values()) == 0
    assert report.spans_usable == 0


def test_missing_span_on_a_substantive_value_is_errata():
    report = make_report()
    inspect_attributes(json.dumps({"Attr": {"value": "Collect on website"}}), report)

    assert report.span_errata["Collect on website"] == 1
    assert report.spans_absent_by_design == 0


@pytest.mark.parametrize("start,end", [(-1, -1), (0, 0)])
def test_degenerate_offsets_are_rejected(start, end):
    """Per the corpus errata, both -1 and both 0 mean the span is unusable."""
    report = make_report()
    payload = {
        "Attr": {
            "selectedText": "we collect your email",
            "startIndexInSegment": start,
            "endIndexInSegment": end,
            "value": "Collect on website",
        }
    }
    inspect_attributes(json.dumps(payload), report)

    assert report.spans_usable == 0
    assert report.spans_degenerate_offsets == 1
    assert sum(report.span_errata.values()) == 1


def test_real_span_is_counted_as_usable():
    report = make_report()
    payload = {
        "Attr": {
            "selectedText": "we collect your email",
            "startIndexInSegment": 10,
            "endIndexInSegment": 31,
            "value": "Collect on website",
        }
    }
    inspect_attributes(json.dumps(payload), report)

    assert report.spans_usable == 1
    assert sum(report.span_errata.values()) == 0


def test_unparseable_attribute_json_is_counted_not_raised():
    report = make_report()
    inspect_attributes("{not json", report)
    assert report.attribute_json_failures == 1


def test_missing_corpus_is_reported_as_a_problem(tmp_path):
    """A missing corpus must produce a clear problem, not a crash or a pass."""
    report = verify(tmp_path / "absent")
    assert not report.ok
    assert any("not found" in problem for problem in report.problems)


def test_schema_constants_match_the_documented_release():
    assert len(CATEGORIES) == 10
    assert EXPECTED_COLUMN_COUNT == 9
    assert len(set(CATEGORIES)) == 10, "category list contains a duplicate"
