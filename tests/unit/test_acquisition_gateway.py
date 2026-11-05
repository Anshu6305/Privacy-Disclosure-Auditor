"""F-06 — gateway, rate limiting, caching and failure handling.

These tests use a stub adapter. **They do not demonstrate that live
retrieval works.** No request in this suite leaves the machine, and the
project has never retrieved a page from Google Play.
"""

from __future__ import annotations

import pytest

from acquisition.adapters import NullAdapter, looks_like_challenge
from acquisition.gateway import (
    AcquisitionGateway,
    BlockedError,
    RateLimiter,
    ResponseCache,
    parse_failure,
)
from acquisition.models import (
    OUTCOME_BLOCKED,
    OUTCOME_FETCH_FAILED,
    OUTCOME_NOT_FOUND,
    OUTCOME_PARSE_FAILED,
    OUTCOME_SUCCESS,
    RETRIEVAL_MODE_CACHE,
)

URL = "https://example.invalid/datasafety"
BODY = b"<html>a declaration</html>"


class StubAdapter:
    """Returns scripted responses and counts calls."""

    def __init__(self, *responses, raises: Exception | None = None):
        self.responses = list(responses)
        self.raises = raises
        self.calls: list[str] = []

    def fetch(self, url):
        self.calls.append(url)
        if self.raises is not None:
            raise self.raises
        return self.responses.pop(0) if self.responses else (200, BODY)


# ---------------------------------------------------------------------------
# Retrieval is optional
# ---------------------------------------------------------------------------


def test_gateway_without_an_adapter_records_a_failure_rather_than_raising():
    """The normal offline state. Audits read the corpus and never need this."""
    result = AcquisitionGateway().retrieve(URL, "data_safety")

    assert result.ok is False
    assert result.provenance.outcome == OUTCOME_FETCH_FAILED
    assert "never require network access" in result.provenance.failure_reason


def test_null_adapter_makes_an_offline_run_explicit():
    gateway = AcquisitionGateway(adapter=NullAdapter())
    result = gateway.retrieve(URL, "data_safety")
    assert result.ok is False
    assert "live retrieval is disabled" in result.provenance.failure_reason


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------


def test_successful_fetch_records_hash_and_size():
    gateway = AcquisitionGateway(adapter=StubAdapter((200, BODY)))
    result = gateway.retrieve(URL, "data_safety")

    assert result.ok
    assert result.content == BODY
    assert result.provenance.outcome == OUTCOME_SUCCESS
    assert len(result.provenance.content_sha256) == 64
    assert result.provenance.content_bytes == len(BODY)
    assert result.provenance.http_status == 200


# ---------------------------------------------------------------------------
# Failure handling, each kind distinguished
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403, 429])
def test_refusal_statuses_are_recorded_as_blocked(status):
    """Blocked means stop, not retry. The distinction drives the remedy."""
    gateway = AcquisitionGateway(adapter=StubAdapter((status, b"")))
    result = gateway.retrieve(URL, "data_safety")

    assert result.provenance.outcome == OUTCOME_BLOCKED
    assert "stop" in result.provenance.failure_reason


def test_404_is_not_found_not_a_failure():
    gateway = AcquisitionGateway(adapter=StubAdapter((404, b"")))
    result = gateway.retrieve(URL, "data_safety")

    assert result.provenance.outcome == OUTCOME_NOT_FOUND
    assert "removed from the store" in result.provenance.failure_reason


def test_server_error_is_a_fetch_failure():
    gateway = AcquisitionGateway(adapter=StubAdapter((500, b"boom")))
    assert gateway.retrieve(URL, "data_safety").provenance.outcome == OUTCOME_FETCH_FAILED


def test_network_exception_is_captured_not_propagated():
    """One unreachable host must not end a collection pass over 300 apps."""
    gateway = AcquisitionGateway(
        adapter=StubAdapter(raises=ConnectionError("name resolution failed"))
    )
    result = gateway.retrieve(URL, "data_safety")

    assert result.provenance.outcome == OUTCOME_FETCH_FAILED
    assert "ConnectionError" in result.provenance.failure_reason


def test_captcha_challenge_is_blocked_not_parsed():
    """A challenge page returns HTTP 200. Parsing it as a declaration would
    produce an application that appears to declare nothing."""
    gateway = AcquisitionGateway(
        adapter=StubAdapter(raises=BlockedError("unusual traffic page"))
    )
    result = gateway.retrieve(URL, "data_safety")

    assert result.provenance.outcome == OUTCOME_BLOCKED


def test_challenge_detection_reads_the_body():
    assert looks_like_challenge(b"<html>Our systems have detected unusual traffic</html>")
    assert looks_like_challenge(b"<html>please complete the reCAPTCHA</html>")
    assert not looks_like_challenge(b"<html>Data safety</html>")


def test_parse_failure_is_distinct_from_fetch_failure():
    """A parse failure means the adapter needs updating. Phase 1 expects it."""
    provenance = parse_failure(URL, "data_safety", "no data-safety block in the page")
    assert provenance.outcome == OUTCOME_PARSE_FAILED
    assert provenance.succeeded is False


def test_a_failure_never_carries_a_content_hash():
    """A hash on a failed retrieval would imply a document we do not have."""
    gateway = AcquisitionGateway(adapter=StubAdapter((500, b"")))
    assert gateway.retrieve(URL, "data_safety").provenance.content_sha256 is None


# ---------------------------------------------------------------------------
# Rate limiting (NFR-15)
# ---------------------------------------------------------------------------


def test_rate_limiter_waits_between_requests():
    slept: list[float] = []
    limiter = RateLimiter(3.0, sleep=slept.append, clock=lambda: 0.0)

    limiter.wait()
    limiter.wait()
    limiter.wait()

    assert slept == [3.0, 3.0], "every request after the first must wait"


def test_rate_limiter_does_not_wait_when_enough_time_has_passed():
    slept: list[float] = []
    times = iter([0.0, 10.0, 10.0])
    limiter = RateLimiter(3.0, sleep=slept.append, clock=lambda: next(times))

    limiter.wait()
    limiter.wait()

    assert slept == []


def test_rate_limiting_cannot_be_disabled():
    """A misconfiguration must not turn the collector into a fast scraper."""
    assert RateLimiter(0.0).interval_seconds == RateLimiter.MINIMUM_INTERVAL_SECONDS
    assert RateLimiter(-5).interval_seconds == RateLimiter.MINIMUM_INTERVAL_SECONDS
    assert RateLimiter(10.0).interval_seconds == 10.0


def test_gateway_applies_the_rate_limiter():
    slept: list[float] = []
    limiter = RateLimiter(2.0, sleep=slept.append, clock=lambda: 0.0)
    gateway = AcquisitionGateway(
        adapter=StubAdapter((200, BODY), (200, BODY)), rate_limiter=limiter
    )

    gateway.retrieve(URL, "data_safety")
    gateway.retrieve(URL + "2", "data_safety")

    assert slept == [2.0]


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def test_cache_miss_then_hit_makes_only_one_request(tmp_path):
    """Re-running a pass over collected applications must make no requests."""
    adapter = StubAdapter((200, BODY))
    cache = ResponseCache(tmp_path)
    gateway = AcquisitionGateway(adapter=adapter, cache=cache)

    first = gateway.retrieve(URL, "data_safety")
    second = gateway.retrieve(URL, "data_safety")

    assert len(adapter.calls) == 1, "the second call must be served from cache"
    assert first.content == second.content == BODY
    assert second.provenance.retrieval_mode == RETRIEVAL_MODE_CACHE
    assert cache.hits == 1
    assert cache.misses == 1


def test_failures_are_not_cached(tmp_path):
    """Caching a transient outage would make it permanent."""
    adapter = StubAdapter((500, b""), (200, BODY))
    gateway = AcquisitionGateway(adapter=adapter, cache=ResponseCache(tmp_path))

    assert gateway.retrieve(URL, "data_safety").ok is False
    assert gateway.retrieve(URL, "data_safety").ok is True
    assert len(adapter.calls) == 2


def test_a_damaged_cache_entry_is_a_miss_not_an_error(tmp_path):
    """The cache is an optimisation and must not be able to break a run."""
    cache = ResponseCache(tmp_path)
    cache.put(URL, BODY)
    for path in tmp_path.rglob("*.json"):
        path.write_text("{ truncated", encoding="utf-8")

    adapter = StubAdapter((200, BODY))
    gateway = AcquisitionGateway(adapter=adapter, cache=cache)

    assert gateway.retrieve(URL, "data_safety").ok is True
    assert len(adapter.calls) == 1


def test_cache_does_not_collide_across_urls(tmp_path):
    cache = ResponseCache(tmp_path)
    cache.put("https://a.invalid", b"A")
    cache.put("https://b.invalid", b"B")
    assert cache.get("https://a.invalid") == b"A"
    assert cache.get("https://b.invalid") == b"B"
