"""F-06 — optional live retrieval wired to persistence.

Every fetch here goes through a controlled fake adapter. **No test in this
file reaches the network**, and none of them demonstrates that live retrieval
against Google works: that has never been attempted. What they establish is
that the wiring records what happened honestly, including when it fails.
"""

from __future__ import annotations

import pytest
from app.db.models import Base
from app.db.repositories import SnapshotRepository
from app.services.acquisition_service import (
    LiveAcquisitionService,
    LiveRetrievalResult,
    LiveRetrievalUnavailable,
)
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from acquisition.gateway import AcquisitionGateway, BlockedError, RateLimiter
from acquisition.models import (
    OUTCOME_BLOCKED,
    OUTCOME_NOT_FOUND,
    OUTCOME_PARSE_FAILED,
    OUTCOME_SUCCESS,
)
from acquisition.policy_document import sha256_of_bytes
from analysis.vocabulary import (
    SNAPSHOT_COMPLETE,
    SNAPSHOT_FETCH_FAILED,
    SNAPSHOT_PARSE_FAILED,
    SNAPSHOT_POLICY_ONLY,
)

PACKAGE = "com.example.live"
POLICY_URL = "https://example.com/privacy.html"
POLICY_BODY = b"<html><body><p>We collect your email address.</p></body></html>"
DATA_SAFETY_BODY = b"<html><body>data safety section</body></html>"


class FakeAdapter:
    """Returns canned responses per URL. Records what was asked for."""

    def __init__(self, responses: dict[str, tuple[int, bytes]], raises=None) -> None:
        self._responses = responses
        self._raises = raises or {}
        self.requested: list[str] = []

    def fetch(self, url: str) -> tuple[int, bytes]:
        self.requested.append(url)
        for fragment, error in self._raises.items():
            if fragment in url:
                raise error
        for fragment, response in self._responses.items():
            if fragment in url:
                return response
        return 404, b""


class StubParser:
    """A declaration parser standing in for one the project has not written."""

    def __init__(self, raw=None, error: Exception | None = None) -> None:
        self._raw = raw or {
            "package_name": PACKAGE,
            "declares_no_data_collected": False,
            "entries": [
                {
                    "category": "Personal info",
                    "data_type": "Email address",
                    "collected": True,
                    "shared": False,
                    "purposes": ["App functionality"],
                }
            ],
        }
        self._error = error

    def parse(self, body: bytes, package_name: str):
        if self._error is not None:
            raise self._error
        return self._raw


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def build(session, tmp_path, adapter=None, parser=None, rate_limiter=None):
    gateway = AcquisitionGateway(adapter=adapter, rate_limiter=rate_limiter)
    return LiveAcquisitionService(
        session,
        gateway,
        corpus_root=tmp_path / "corpus",
        declaration_parser=parser,
        repository_root=tmp_path,
    )


def both_sources_ok() -> FakeAdapter:
    return FakeAdapter(
        {"datasafety": (200, DATA_SAFETY_BODY), "privacy.html": (200, POLICY_BODY)}
    )


# ---------------------------------------------------------------------------
# Offline-first
# ---------------------------------------------------------------------------


def test_without_an_adapter_live_retrieval_is_unavailable_not_broken(
    session, tmp_path
):
    """A deployment with no adapter is supported, not misconfigured."""
    service = build(session, tmp_path)
    assert service.available is False

    result = service.collect(PACKAGE, policy_url=POLICY_URL)
    assert isinstance(result, LiveRetrievalUnavailable)
    assert "never require network access" in result.detail


def test_nothing_is_persisted_when_retrieval_is_unavailable(session, tmp_path):
    build(session, tmp_path).collect(PACKAGE, policy_url=POLICY_URL)
    assert SnapshotRepository(session).latest_for_app(1) is None


def test_an_empty_package_name_is_rejected(session, tmp_path):
    with pytest.raises(ValueError, match="package name is required"):
        build(session, tmp_path, adapter=both_sources_ok()).collect("  ")


# ---------------------------------------------------------------------------
# The successful path, with a parser injected
# ---------------------------------------------------------------------------


def test_both_sources_retrieved_produces_a_complete_event(session, tmp_path):
    service = build(session, tmp_path, adapter=both_sources_ok(), parser=StubParser())
    result = service.collect(PACKAGE, app_name="Live App", policy_url=POLICY_URL)

    assert isinstance(result, LiveRetrievalResult)
    assert result.succeeded is True
    assert result.status == SNAPSHOT_COMPLETE
    assert result.snapshot_id is not None


def test_the_policy_document_is_stored_under_its_hash(session, tmp_path):
    service = build(session, tmp_path, adapter=both_sources_ok(), parser=StubParser())
    result = service.collect(PACKAGE, policy_url=POLICY_URL)

    assert isinstance(result, LiveRetrievalResult)
    assert result.policy_stored_at is not None
    stored = tmp_path / result.policy_stored_at
    assert stored.read_bytes() == POLICY_BODY
    assert sha256_of_bytes(POLICY_BODY) in stored.name


def test_the_stored_document_loads_back_and_verifies(session, tmp_path):
    """F-06 into F-05: what live retrieval wrote must pass hash verification."""
    service = build(session, tmp_path, adapter=both_sources_ok(), parser=StubParser())
    result = service.collect(PACKAGE, policy_url=POLICY_URL)
    assert isinstance(result, LiveRetrievalResult)
    session.flush()

    loaded = SnapshotRepository(session, policy_root=tmp_path).load_policy_document(
        result.snapshot_id
    )
    assert loaded is not None
    assert loaded.content_sha256 == sha256_of_bytes(POLICY_BODY)


def test_persist_false_writes_nothing_but_still_reports(session, tmp_path):
    service = build(session, tmp_path, adapter=both_sources_ok(), parser=StubParser())
    result = service.collect(PACKAGE, policy_url=POLICY_URL, persist=False)
    assert isinstance(result, LiveRetrievalResult)
    assert result.persisted is False
    assert result.snapshot_id is None
    assert result.status == SNAPSHOT_COMPLETE


# ---------------------------------------------------------------------------
# Failures are recorded, never converted into absent disclosures
# ---------------------------------------------------------------------------


def test_a_fetched_but_unparsed_declaration_is_a_parse_failure(session, tmp_path):
    """The distinction this module exists to protect.

    With no parser configured the page is reached and not understood. That is
    not the application declaring nothing, and the status must not say so.
    """
    service = build(session, tmp_path, adapter=both_sources_ok(), parser=None)
    result = service.collect(PACKAGE, policy_url=POLICY_URL)

    assert isinstance(result, LiveRetrievalResult)
    assert result.declaration_outcome == OUTCOME_PARSE_FAILED
    assert result.status == SNAPSHOT_PARSE_FAILED
    assert result.succeeded is False

    (declaration_provenance, _policy) = result.provenances
    assert "not an absent declaration" in declaration_provenance.failure_reason


def test_a_parser_that_raises_is_recorded_as_a_parse_failure(session, tmp_path):
    service = build(
        session,
        tmp_path,
        adapter=both_sources_ok(),
        parser=StubParser(error=ValueError("unexpected markup")),
    )
    result = service.collect(PACKAGE, policy_url=POLICY_URL)
    assert isinstance(result, LiveRetrievalResult)
    assert result.declaration_outcome == OUTCOME_PARSE_FAILED
    assert "unexpected markup" in result.provenances[0].failure_reason


def test_a_declaration_that_404s_does_not_become_an_empty_declaration(
    session, tmp_path
):
    adapter = FakeAdapter({"privacy.html": (200, POLICY_BODY)})  # datasafety -> 404
    service = build(session, tmp_path, adapter=adapter, parser=StubParser())
    result = service.collect(PACKAGE, policy_url=POLICY_URL)

    assert isinstance(result, LiveRetrievalResult)
    assert result.declaration_outcome == OUTCOME_NOT_FOUND
    session.flush()
    snapshot = SnapshotRepository(session).latest_for_app(1)
    assert snapshot is not None
    assert snapshot.declares_no_data_collected is None


def test_a_blocked_service_is_classified_as_blocked(session, tmp_path):
    adapter = FakeAdapter({}, raises={"datasafety": BlockedError("challenge page")})
    service = build(session, tmp_path, adapter=adapter, parser=StubParser())
    result = service.collect(PACKAGE, policy_url=POLICY_URL)

    assert isinstance(result, LiveRetrievalResult)
    assert result.declaration_outcome == OUTCOME_BLOCKED
    assert "stop" in result.provenances[0].failure_reason.lower()


def test_both_sources_failing_is_a_fetch_failure(session, tmp_path):
    adapter = FakeAdapter({})
    service = build(session, tmp_path, adapter=adapter, parser=StubParser())
    result = service.collect(PACKAGE, policy_url=POLICY_URL)
    assert isinstance(result, LiveRetrievalResult)
    assert result.status == SNAPSHOT_FETCH_FAILED


def test_a_missing_policy_url_is_recorded_with_its_reason(session, tmp_path):
    """Guessing one could attribute another document to this application."""
    service = build(session, tmp_path, adapter=both_sources_ok(), parser=StubParser())
    result = service.collect(PACKAGE)

    assert isinstance(result, LiveRetrievalResult)
    assert result.policy_outcome == OUTCOME_NOT_FOUND
    assert "guessed URL" in result.provenances[1].failure_reason
    assert result.status != SNAPSHOT_COMPLETE


# ---------------------------------------------------------------------------
# Provenance, rate limiting and caching come from the gateway unchanged
# ---------------------------------------------------------------------------


def test_one_provenance_per_source_is_recorded(session, tmp_path):
    service = build(session, tmp_path, adapter=both_sources_ok(), parser=StubParser())
    result = service.collect(PACKAGE, policy_url=POLICY_URL)
    assert isinstance(result, LiveRetrievalResult)
    assert len(result.provenances) == 2
    assert {p.source_type for p in result.provenances} == {
        "data_safety",
        "privacy_policy",
    }
    assert all(p.retrieved_at is not None for p in result.provenances)


def test_the_rate_limiter_is_applied_to_every_request(session, tmp_path):
    """NFR-15. The limiter cannot be bypassed by going through this service."""
    waits: list[float] = []
    limiter = RateLimiter(interval_seconds=3.0, sleep=waits.append, clock=lambda: 0.0)
    service = build(
        session,
        tmp_path,
        adapter=both_sources_ok(),
        parser=StubParser(),
        rate_limiter=limiter,
    )
    service.collect(PACKAGE, policy_url=POLICY_URL)

    assert len(limiter.waits) == 2
    assert waits == [3.0]


def test_a_second_collection_supersedes_the_first(session, tmp_path):
    service = build(session, tmp_path, adapter=both_sources_ok(), parser=StubParser())
    first = service.collect(PACKAGE, policy_url=POLICY_URL)
    second = service.collect(PACKAGE, policy_url=POLICY_URL)
    session.flush()

    assert isinstance(first, LiveRetrievalResult)
    assert isinstance(second, LiveRetrievalResult)
    repo = SnapshotRepository(session)
    latest = repo.latest_for_app(1)
    assert latest is not None
    assert latest.snapshot_id == second.snapshot_id
    assert len(repo.history_for_app(1)) == 2


def test_only_the_two_expected_urls_are_requested(session, tmp_path):
    """No crawling. One application, two documents."""
    adapter = both_sources_ok()
    build(session, tmp_path, adapter=adapter, parser=StubParser()).collect(
        PACKAGE, policy_url=POLICY_URL
    )
    assert len(adapter.requested) == 2
    assert any("datasafety" in url for url in adapter.requested)
    assert POLICY_URL in adapter.requested


def test_a_policy_only_result_is_still_persisted(session, tmp_path):
    """A partial event is recorded with the status that says so."""
    adapter = FakeAdapter({"privacy.html": (200, POLICY_BODY)})
    service = build(session, tmp_path, adapter=adapter, parser=StubParser())
    result = service.collect(PACKAGE, policy_url=POLICY_URL)
    session.flush()

    assert isinstance(result, LiveRetrievalResult)
    assert result.policy_outcome == OUTCOME_SUCCESS
    assert result.status in {SNAPSHOT_POLICY_ONLY, "declaration_absent"}
    assert result.snapshot_id is not None
