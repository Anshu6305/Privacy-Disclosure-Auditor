"""F-07 provenance, and the offline corpus: manifest, validation, import.

The sample corpus under ``tests/fixtures/sample_corpus`` is **invented test
data**. ``com.example.sampleapp`` is not a real application and its policy
text was written for this fixture. It demonstrates the format; it is not
evidence that an operational corpus exists.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from acquisition.corpus import (
    CORPUS_SCHEMA_VERSION,
    CorpusFormatError,
    CorpusPaths,
    build_manifest,
    read_record,
    record_to_dict,
    validate_corpus,
    write_manifest,
    write_record,
)
from acquisition.declaration import normalise_declaration
from acquisition.models import ApplicationRecord
from acquisition.policy_document import load_policy_document, sha256_of_file
from acquisition.provenance import (
    data_safety_url,
    manual_import_provenance,
    play_listing_url,
    provenance_from_dict,
    provenance_to_dict,
    read_provenance_log,
    summarise_log,
    write_provenance_log,
)
from analysis.vocabulary import SOURCE_DATA_SAFETY, SOURCE_PRIVACY_POLICY

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_corpus"
WHEN = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# F-07 provenance
# ---------------------------------------------------------------------------


def test_manual_import_provenance_records_the_five_required_facts():
    p = manual_import_provenance(
        SOURCE_PRIVACY_POLICY, "https://example.invalid/privacy", WHEN, "a" * 64,
        content_bytes=1234, collector_note="saved by R2",
    )
    assert p.source_url == "https://example.invalid/privacy"
    assert p.retrieved_at == WHEN
    assert p.retrieval_mode == "manual_import"
    assert p.content_sha256 == "a" * 64
    assert p.outcome == "success"
    assert p.collector_note == "saved by R2"


def test_provenance_round_trips_through_json():
    p = manual_import_provenance(SOURCE_DATA_SAFETY, "https://x.invalid", WHEN, "b" * 64)
    assert provenance_from_dict(json.loads(json.dumps(provenance_to_dict(p)))) == p


def test_provenance_log_records_failures_alongside_successes(tmp_path):
    """A corpus that logged only successes would misrepresent a collection
    pass as having gone better than it did."""
    from acquisition.models import Provenance

    entries = [
        manual_import_provenance(SOURCE_DATA_SAFETY, "https://a.invalid", WHEN, "a" * 64),
        Provenance(SOURCE_DATA_SAFETY, "https://b.invalid", WHEN, "live_fetch",
                   "blocked", failure_reason="HTTP 429"),
        Provenance(SOURCE_PRIVACY_POLICY, "https://c.invalid", WHEN, "live_fetch",
                   "not_found", failure_reason="HTTP 404"),
    ]
    log = tmp_path / "provenance.jsonl"
    assert write_provenance_log(log, entries) == 3

    read_back = read_provenance_log(log)
    assert len(read_back) == 3
    assert summarise_log(read_back) == {"blocked": 1, "not_found": 1, "success": 1}


def test_provenance_log_is_append_only(tmp_path):
    log = tmp_path / "provenance.jsonl"
    write_provenance_log(log, [
        manual_import_provenance(SOURCE_DATA_SAFETY, "https://a.invalid", WHEN, "a" * 64)
    ])
    write_provenance_log(log, [
        manual_import_provenance(SOURCE_DATA_SAFETY, "https://b.invalid", WHEN, "b" * 64)
    ])
    assert len(read_provenance_log(log)) == 2


def test_url_helpers():
    assert data_safety_url("com.x") == (
        "https://play.google.com/store/apps/datasafety?id=com.x"
    )
    assert play_listing_url("com.x") == (
        "https://play.google.com/store/apps/details?id=com.x"
    )


# ---------------------------------------------------------------------------
# The sample record
# ---------------------------------------------------------------------------


def test_sample_record_reads_and_is_complete():
    record = read_record(SAMPLE / "apps" / "com.example.sampleapp" / "record.json")

    assert record.package_name == "com.example.sampleapp"
    assert record.declaration is not None
    assert record.policy_sha256 is not None
    assert record.is_analysable is True
    assert record.declaration.collected_categories == (
        "Contacts", "Location", "Personal info",
    )
    assert record.declaration.shared_categories == ("Contacts",)


def test_sample_policy_hash_verifies():
    record = read_record(SAMPLE / "apps" / "com.example.sampleapp" / "record.json")
    assert sha256_of_file(SAMPLE / record.policy_path) == record.policy_sha256


def test_sample_policy_loads_through_f05():
    """The F-05 interface M4's F-08 will consume."""
    record = read_record(SAMPLE / "apps" / "com.example.sampleapp" / "record.json")
    doc = load_policy_document(
        record.package_name, SAMPLE / record.policy_path, record.policy_url,
        expected_sha256=record.policy_sha256,
    )
    assert "We collect your email address" in doc.content
    assert doc.media_type == "text/html"


def test_sample_corpus_validates():
    report = validate_corpus(SAMPLE)
    assert report.ok, report.errors
    assert report.records_read == 1
    assert report.analysable == ["com.example.sampleapp"]
    assert report.duplicates == []
    assert report.hash_mismatches == []


def test_sample_manifest_matches_the_records():
    manifest = build_manifest(CorpusPaths(SAMPLE))
    assert manifest["application_count"] == 1
    assert manifest["analysable_count"] == 1
    assert "NOT OPP-115" in manifest["note"]


# ---------------------------------------------------------------------------
# Validation of a corpus with problems
# ---------------------------------------------------------------------------


def _record(package: str, **kwargs) -> ApplicationRecord:
    base = {
        "package_name": package,
        "app_name": package,
        "collected_at": WHEN,
        "validation_status": "test",
    }
    base.update(kwargs)
    return ApplicationRecord(**base)


@pytest.fixture
def corpus(tmp_path):
    paths = CorpusPaths(tmp_path / "corpus")
    paths.create()
    return paths


def test_missing_declaration_is_a_warning_not_an_error(corpus):
    """An incomplete record is still worth keeping: the gap must be visible
    and countable, not silently dropped."""
    policy = corpus.raw_policies / "p.html"
    policy.write_text("<html>policy</html>", encoding="utf-8")
    write_record(corpus, _record(
        "com.example.nodecl", policy_path=str(policy),
        policy_sha256=sha256_of_file(policy),
    ))

    report = validate_corpus(corpus.root)
    assert report.ok, "an incomplete record must not fail the corpus"
    assert report.missing_declaration == ["com.example.nodecl"]
    assert report.analysable == []


def test_missing_policy_is_detected(corpus):
    write_record(corpus, _record(
        "com.example.nopolicy",
        declaration=normalise_declaration({
            "package_name": "com.example.nopolicy",
            "entries": [{"category": "Location", "collected": True}],
        }),
    ))
    report = validate_corpus(corpus.root)
    assert report.missing_policy == ["com.example.nopolicy"]
    assert report.analysable == []


def test_hash_mismatch_is_an_error(corpus):
    policy = corpus.raw_policies / "p.html"
    policy.write_text("<html>original</html>", encoding="utf-8")
    write_record(corpus, _record(
        "com.example.tampered", policy_path=str(policy),
        policy_sha256=sha256_of_file(policy),
    ))
    policy.write_text("<html>modified after import</html>", encoding="utf-8")

    report = validate_corpus(corpus.root)
    assert report.ok is False
    assert report.hash_mismatches == ["com.example.tampered"]


def test_missing_policy_file_is_an_error(corpus):
    write_record(corpus, _record(
        "com.example.gone",
        policy_path=str(corpus.raw_policies / "absent.html"),
        policy_sha256="c" * 64,
    ))
    report = validate_corpus(corpus.root)
    assert report.ok is False
    assert any("policy file missing" in e for e in report.errors)


def test_directory_name_must_match_the_package(corpus):
    """Otherwise two directories could describe one application."""
    write_record(corpus, _record("com.example.one"))
    stray = corpus.apps / "com.example.other"
    stray.mkdir(parents=True)
    content = (corpus.apps / "com.example.one" / "record.json").read_text()
    (stray / "record.json").write_text(content, encoding="utf-8")

    report = validate_corpus(corpus.root)
    assert report.ok is False
    assert "com.example.one" in report.duplicates


def test_malformed_record_does_not_hide_the_rest(corpus):
    """One bad file must not stop the other records being checked."""
    write_record(corpus, _record("com.example.good"))
    bad = corpus.apps / "com.example.bad"
    bad.mkdir(parents=True)
    (bad / "record.json").write_text("{ not json", encoding="utf-8")

    report = validate_corpus(corpus.root)
    assert report.ok is False
    assert report.records_read == 1
    assert any("not valid JSON" in e for e in report.errors)


def test_schema_version_mismatch_is_refused(corpus):
    write_record(corpus, _record("com.example.old"))
    path = corpus.record_path("com.example.old")
    raw = json.loads(path.read_text())
    raw["schema_version"] = "0.9"
    path.write_text(json.dumps(raw), encoding="utf-8")

    report = validate_corpus(corpus.root)
    assert report.ok is False
    assert any("schema_version" in e for e in report.errors)


def test_declaration_naming_a_different_package_is_refused(corpus):
    write_record(corpus, _record("com.example.mismatch"))
    path = corpus.record_path("com.example.mismatch")
    raw = json.loads(path.read_text())
    raw["declaration"] = {
        "package_name": "com.example.somethingelse",
        "entries": [{"category": "Location", "collected": True}],
    }
    path.write_text(json.dumps(raw), encoding="utf-8")

    report = validate_corpus(corpus.root)
    assert report.ok is False
    assert any("different package" in e for e in report.errors)


def test_missing_corpus_directory_reports_where_to_look(tmp_path):
    report = validate_corpus(tmp_path / "absent")
    assert report.ok is False
    assert any("M3_ACQUISITION_REPORT" in e for e in report.errors)


# ---------------------------------------------------------------------------
# The manual import workflow
# ---------------------------------------------------------------------------


def test_manual_import_workflow_end_to_end(corpus):
    """The documented procedure, exercised: save a policy, hash it, build a
    record with provenance, write it, regenerate the manifest, validate."""
    package = "com.example.imported"

    # 1. A collector saves the policy page by hand.
    policy_text = "<html><body><p>We collect your email address.</p></body></html>"
    digest_path = corpus.raw_policies / "pending.html"
    digest_path.write_text(policy_text, encoding="utf-8")
    digest = sha256_of_file(digest_path)
    stored = corpus.policy_path(digest)
    digest_path.rename(stored)

    # 2. The declaration is entered in the documented format.
    declaration = normalise_declaration({
        "package_name": package,
        "entries": [{"category": "Personal info", "data_type": "Email address",
                     "collected": True, "purposes": ["App functionality"]}],
        "security": {"encrypted_in_transit": True},
    })

    # 3. Provenance for both sources.
    provenances = (
        manual_import_provenance(SOURCE_DATA_SAFETY, data_safety_url(package),
                                 WHEN, "d" * 64, collector_note="entered by hand"),
        manual_import_provenance(SOURCE_PRIVACY_POLICY, "https://example.invalid/p",
                                 WHEN, digest, content_bytes=stored.stat().st_size),
    )

    # 4. Write the record and the manifest.
    write_record(corpus, ApplicationRecord(
        package_name=package, app_name="Imported App",
        policy_url="https://example.invalid/p",
        declaration=declaration,
        policy_path=str(stored), policy_sha256=digest,
        collected_at=WHEN, provenances=provenances,
        validation_status="imported",
    ))
    write_manifest(corpus)

    # 5. Validate.
    report = validate_corpus(corpus.root)
    assert report.ok, report.errors
    assert report.analysable == [package]

    # 6. The policy loads back through F-05 with its hash verified.
    record = read_record(corpus.record_path(package))
    doc = load_policy_document(package, record.policy_path, record.policy_url,
                               expected_sha256=record.policy_sha256)
    assert "We collect your email address" in doc.content

    manifest = json.loads(corpus.manifest.read_text())
    assert manifest["application_count"] == 1
    assert manifest["analysable_count"] == 1


def test_record_round_trips(corpus):
    record = _record("com.example.rt", app_name="RT", developer_name="Dev")
    write_record(corpus, record)
    assert read_record(corpus.record_path("com.example.rt")).package_name == "com.example.rt"
    assert record_to_dict(record)["schema_version"] == CORPUS_SCHEMA_VERSION


def test_unreadable_record_raises_a_format_error(tmp_path):
    path = tmp_path / "record.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(CorpusFormatError):
        read_record(path)
