"""F-08 — policy text extraction and cleaning.

All documents here are controlled fixtures written for these tests. None came
from a real application.
"""

from __future__ import annotations

import pytest

from acquisition.models import PolicyDocument
from analysis.text.extractor import (
    ExtractionError,
    extract_policy_text,
    normalise_unicode,
    normalise_whitespace,
)

HTML = """<html><head><title>Privacy</title>
<script>var tracker = 1; document.write("tracking");</script>
<style>body { color: red; }</style></head>
<body>
<nav><a href="/">Home</a><a href="/about">About</a></nav>
<header>Our Company</header>
<h1>Privacy Policy</h1>
<p>We collect your email address.</p>
<h2>Exceptions</h2>
<p>We do not collect location data, except where you enable check-ins.</p>
<ul><li>Name</li><li>Email address</li></ul>
<footer>Copyright 2026</footer>
<noscript>Enable JavaScript</noscript>
</body></html>"""


def test_extracts_policy_prose_from_html():
    result = extract_policy_text(HTML)

    assert result.succeeded
    assert "We collect your email address." in result.text
    assert result.length > 0


def test_removes_scripts_styles_and_navigation():
    result = extract_policy_text(HTML)

    for removed in ("var tracker", "document.write", "color: red",
                    "Home", "About", "Our Company", "Copyright 2026",
                    "Enable JavaScript"):
        assert removed not in result.text, f"{removed!r} survived extraction"

    assert result.removed["script"] == 1
    assert result.removed["nav"] == 1
    assert result.removed["footer"] == 1


def test_retains_headings_definitions_exceptions_and_lists():
    """Each of these can carry a data practice; losing one loses a finding."""
    result = extract_policy_text(HTML)

    assert "Privacy Policy" in result.text
    assert "Exceptions" in result.text
    assert "except where you enable check-ins" in result.text
    assert "Name" in result.text
    assert "Email address" in result.text


def test_repetitive_content_is_not_removed():
    """Policies repeat themselves by nature. A cleaner that dropped repeated
    phrasing would delete the clauses the audit exists to find."""
    repeated = (
        "<html><body>"
        + "<p>We may collect your data.</p>" * 6
        + "<p>We may collect your precise location.</p>"
        + "</body></html>"
    )
    result = extract_policy_text(repeated)

    assert result.text.count("We may collect your data.") == 6
    assert "precise location" in result.text


def test_headings_are_separated_from_the_prose_beneath_them():
    """Otherwise a heading and the following sentence merge into one, and
    sentence segmentation would treat them as a single statement."""
    result = extract_policy_text(
        "<html><body><h2>Data we share</h2><p>We share nothing.</p></body></html>"
    )
    assert "Data we share\n\nWe share nothing." in result.text


def test_plain_text_input_is_passed_through():
    text = "Privacy Policy\n\nWe collect your email address."
    result = extract_policy_text(text, media_type="text/plain")

    assert result.succeeded
    assert result.text == text


def test_malformed_html_still_extracts():
    """Real pages are malformed. One bad document must not stop a corpus."""
    broken = "<html><body><p>We collect data<div><span>and share it</p></body>"
    result = extract_policy_text(broken)

    assert result.succeeded
    assert "We collect data" in result.text
    assert "and share it" in result.text


def test_unclosed_tags_and_stray_brackets():
    result = extract_policy_text("<p>We collect <b>your email<p>and more")
    assert result.succeeded
    assert "your email" in result.text


def test_unicode_is_normalised():
    """Compatibility forms are folded so a quoted sentence reads as written."""
    result = extract_policy_text(
        "<p>We collect your eﬀective address​ and more.</p>"
    )
    assert "effective address and more." in result.text
    assert "​" not in result.text


def test_non_breaking_spaces_become_ordinary_spaces():
    result = extract_policy_text("<p>We collect your email.</p>")
    assert "We collect your email." in result.text


def test_accented_text_is_preserved():
    """Normalisation must not strip meaning from non-English policy text."""
    result = extract_policy_text("<p>Nous collectons votre adresse e-mail.</p>")
    assert "collectons votre adresse" in result.text


def test_empty_document_fails_explicitly():
    result = extract_policy_text("")

    assert result.succeeded is False
    assert "empty" in result.reason.lower()
    assert result.text == ""


def test_whitespace_only_document_fails_explicitly():
    assert extract_policy_text("   \n\n  \t ").succeeded is False


def test_markup_with_no_text_fails_with_a_useful_reason():
    """A page whose content loads from a script. We do not execute scripts."""
    result = extract_policy_text(
        "<html><head><script>render()</script></head><body><div></div></body></html>"
    )

    assert result.succeeded is False
    assert "loads from a script" in result.reason


def test_pdf_is_reported_as_unsupported_not_garbled():
    result = extract_policy_text("%PDF-1.4 binary", media_type="application/pdf")

    assert result.succeeded is False
    assert "PDF text extraction is not implemented" in result.reason
    assert result.text == ""


def test_non_string_input_is_a_programming_error():
    with pytest.raises(ExtractionError, match="expected text"):
        extract_policy_text(b"<p>bytes</p>")


def test_accepts_a_policy_document_from_f05():
    """The M3A interface. F-08 consumes what F-05 produces."""
    document = PolicyDocument(
        package_name="com.example.app",
        source_url="https://example.invalid/privacy",
        content=HTML,
        content_sha256="a" * 64,
        storage_path="/corpus/raw/policies/a.html",
        media_type="text/html",
    )
    result = extract_policy_text(document)

    assert result.succeeded
    assert result.source_sha256 == "a" * 64
    assert result.media_type == "text/html"


def test_the_source_string_is_not_modified():
    original = HTML
    extract_policy_text(original)
    assert original == HTML


def test_extraction_is_deterministic():
    """F-09's offsets index this output, so the same document must always
    produce the same text."""
    assert extract_policy_text(HTML).text == extract_policy_text(HTML).text


def test_a_successful_result_cannot_be_empty():
    from analysis.text.models import ExtractionResult

    with pytest.raises(ValueError, match="cannot be marked"):
        ExtractionResult(text="   ", succeeded=True)


def test_a_failed_result_must_say_why():
    from analysis.text.models import ExtractionResult

    with pytest.raises(ValueError, match="must carry a reason"):
        ExtractionResult(text="", succeeded=False)


# ---------------------------------------------------------------------------
# Whitespace and Unicode helpers
# ---------------------------------------------------------------------------


def test_single_newlines_become_spaces_but_paragraph_breaks_survive():
    """In HTML a source newline renders as a space. One surviving into a
    quoted sentence would be a line break the policy never had."""
    assert normalise_whitespace("one\ntwo") == "one two"
    assert normalise_whitespace("one\n\ntwo") == "one\n\ntwo"
    assert normalise_whitespace("one\n\n\n\n\ntwo") == "one\n\ntwo"


def test_runs_of_spaces_collapse():
    assert normalise_whitespace("a     b\t\tc") == "a b c"


def test_normalise_unicode_drops_invisible_characters():
    assert normalise_unicode("a​b﻿c") == "abc"
