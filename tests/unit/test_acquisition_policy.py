"""F-05 — policy document loading and SHA-256 verification."""

from __future__ import annotations

import pytest

from acquisition.policy_document import (
    PolicyDecodeError,
    PolicyFileMissingError,
    PolicyHashMismatchError,
    load_policy_document,
    media_type_for,
    sha256_of_bytes,
    sha256_of_file,
    verify_policy_file,
)

POLICY = "<html><body><p>We collect your email address.</p></body></html>"


@pytest.fixture
def policy_file(tmp_path):
    path = tmp_path / "policy.html"
    path.write_text(POLICY, encoding="utf-8")
    return path


def test_loads_and_returns_the_text_and_hash(policy_file):
    doc = load_policy_document(
        "com.example.app", policy_file, "https://example.invalid/privacy"
    )
    assert doc.content == POLICY
    assert doc.content_sha256 == sha256_of_bytes(POLICY.encode())
    assert doc.source_url == "https://example.invalid/privacy"
    assert doc.media_type == "text/html"
    assert doc.length == len(POLICY)


def test_verifies_a_matching_hash(policy_file):
    expected = sha256_of_file(policy_file)
    doc = load_policy_document(
        "com.example.app", policy_file, "https://x.invalid", expected_sha256=expected
    )
    assert doc.content_sha256 == expected


def test_hash_mismatch_stops_the_load(policy_file):
    """Returning the text anyway would let an audit quote a document that is
    not the one its provenance describes."""
    with pytest.raises(PolicyHashMismatchError) as caught:
        load_policy_document(
            "com.example.app", policy_file, "https://x.invalid",
            expected_sha256="b" * 64,
        )
    assert caught.value.expected == "b" * 64
    assert caught.value.actual == sha256_of_file(policy_file)
    assert "modified, truncated or replaced" in str(caught.value)


def test_a_modified_file_is_detected(policy_file):
    """The realistic corruption: someone opens and re-saves the file."""
    original = sha256_of_file(policy_file)
    policy_file.write_text(POLICY + "<!-- edited -->", encoding="utf-8")

    assert verify_policy_file(policy_file, original) is False
    with pytest.raises(PolicyHashMismatchError):
        load_policy_document(
            "com.example.app", policy_file, "https://x.invalid",
            expected_sha256=original,
        )


def test_missing_file_reports_what_to_do(tmp_path):
    with pytest.raises(PolicyFileMissingError) as caught:
        load_policy_document(
            "com.example.app", tmp_path / "absent.html", "https://x.invalid"
        )
    assert "copied without its raw documents" in str(caught.value)


def test_the_raw_file_is_not_modified_by_loading(policy_file):
    before = policy_file.read_bytes()
    before_mtime = policy_file.stat().st_mtime_ns
    load_policy_document("com.example.app", policy_file, "https://x.invalid")
    assert policy_file.read_bytes() == before
    assert policy_file.stat().st_mtime_ns == before_mtime


def test_undecodable_file_is_reported_not_silently_damaged(tmp_path):
    """Analysing text full of replacement characters would produce findings
    about characters the policy does not contain."""
    path = tmp_path / "policy.html"
    path.write_bytes(b"<html>\xff\xfe invalid utf-8 \xff</html>")

    with pytest.raises(PolicyDecodeError, match="not valid utf-8"):
        load_policy_document("com.example.app", path, "https://x.invalid")


def test_pdf_is_stored_but_not_decoded_here(tmp_path):
    """Text extraction from PDF is F-08, Milestone 4."""
    path = tmp_path / "policy.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(PolicyDecodeError, match="F-08"):
        load_policy_document("com.example.app", path, "https://x.invalid")


def test_media_type_detection(tmp_path):
    assert media_type_for(tmp_path / "a.html") == "text/html"
    assert media_type_for(tmp_path / "a.txt") == "text/plain"
    assert media_type_for(tmp_path / "a.pdf") == "application/pdf"
    assert media_type_for(tmp_path / "a.bin") == "application/octet-stream"


def test_hash_of_file_and_bytes_agree(policy_file):
    assert sha256_of_file(policy_file) == sha256_of_bytes(POLICY.encode())
