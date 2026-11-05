"""F-06 — the single gateway through which anything leaves this machine.

NFR-16 requires all external retrieval to pass through one component, and
Phase 1 named scraper breakage the project's highest-probability risk. Both
point at the same design: one chokepoint, with the site-specific parsing
behind a replaceable adapter.

Three properties matter more than features here.

**Retrieval is optional.** No audit depends on it. The pipeline reads the
frozen offline corpus; live retrieval only adds to that corpus. If Google
blocks us the day before the demonstration, nothing stops working.

**Requests are slow by default.** The rate limiter sleeps between requests and
cannot be turned off, only lengthened. NFR-15 requires it, and a project that
hammers a public service to collect 500 records deserves to be blocked.

**Failures are recorded, not raised away.** Every attempt returns a
:class:`RetrievalResult` carrying provenance, including the failures. A
corpus that quietly contains only the apps that happened to work would
misrepresent itself.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from acquisition.models import (
    OUTCOME_BLOCKED,
    OUTCOME_FETCH_FAILED,
    OUTCOME_NOT_FOUND,
    OUTCOME_PARSE_FAILED,
    OUTCOME_SUCCESS,
    RETRIEVAL_MODE_CACHE,
    RETRIEVAL_MODE_LIVE,
    Provenance,
)
from acquisition.policy_document import sha256_of_bytes


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalResult:
    """What one attempt produced. Always returned, success or not."""

    provenance: Provenance
    content: bytes | None = None

    @property
    def ok(self) -> bool:
        return self.provenance.succeeded


# ---------------------------------------------------------------------------
# Rate limiting (NFR-15)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Enforces a minimum interval between requests.

    The interval can be lengthened but not removed: a floor is applied so a
    misconfiguration cannot turn the collector into a scraper that fires as
    fast as the network allows.

    ``sleep`` is injectable so tests can assert the delay was requested
    without actually waiting.
    """

    #: Below this, the limiter refuses to go however it is configured.
    MINIMUM_INTERVAL_SECONDS = 1.0

    def __init__(
        self,
        interval_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if interval_seconds < self.MINIMUM_INTERVAL_SECONDS:
            interval_seconds = self.MINIMUM_INTERVAL_SECONDS
        self.interval_seconds = interval_seconds
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None
        self.waits: list[float] = []

    def wait(self) -> float:
        """Block until the interval since the previous request has elapsed."""
        now = self._clock()
        if self._last is None:
            self._last = now
            self.waits.append(0.0)
            return 0.0

        elapsed = now - self._last
        remaining = self.interval_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)
            self._last = self._clock()
            self.waits.append(remaining)
            return remaining

        self._last = now
        self.waits.append(0.0)
        return 0.0


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class ResponseCache:
    """A content-addressed cache of successful responses.

    Its purpose is to avoid asking a public service twice for the same page.
    A re-run of a collection pass over 300 applications should make zero
    requests for the ones already fetched.

    Only successes are cached. A failure is a fact about one moment, not about
    the resource, and caching it would make a transient outage permanent.
    """

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self.hits = 0
        self.misses = 0

    def _key_path(self, url: str) -> Path:
        digest = sha256_of_bytes(url.encode("utf-8"))
        return self.directory / digest[:2] / f"{digest}.json"

    def get(self, url: str) -> bytes | None:
        path = self._key_path(url)
        if not path.is_file():
            self.misses += 1
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            content = bytes.fromhex(payload["content_hex"])
        except (OSError, ValueError, KeyError):
            # A damaged cache entry is a miss, never an error: the cache is an
            # optimisation and must not be able to break a collection run.
            self.misses += 1
            return None
        self.hits += 1
        return content

    def put(self, url: str, content: bytes) -> None:
        path = self._key_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "url": url,
                    "cached_at": utcnow().isoformat(timespec="seconds"),
                    "content_hex": content.hex(),
                }
            ),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Adapter contract
# ---------------------------------------------------------------------------


class FetchAdapter(Protocol):
    """A replaceable transport.

    Everything site-specific lives behind this. When a scraper breaks, is
    replaced, or is swapped for a manual export, only an implementation of
    this protocol changes; the gateway, the rate limiting, the caching and the
    provenance do not.
    """

    def fetch(self, url: str) -> tuple[int, bytes]:
        """Return (HTTP status, body). Raise on transport failure."""
        ...


class BlockedError(Exception):
    """The service refused us: a challenge page, a 429, or a 403.

    Distinguished from an ordinary failure because the correct response is
    different. A blocked collector must stop for the day, not retry.
    """


# ---------------------------------------------------------------------------
# The gateway
# ---------------------------------------------------------------------------


class AcquisitionGateway:
    """The one place a request leaves this machine (NFR-16).

    Construct with ``adapter=None`` for an offline run: every call then returns
    a recorded failure instead of reaching the network, which is how the test
    suite and any demonstration run.
    """

    #: Statuses that mean "stop", not "try again".
    BLOCKING_STATUSES = frozenset({401, 403, 429})

    def __init__(
        self,
        adapter: FetchAdapter | None = None,
        rate_limiter: RateLimiter | None = None,
        cache: ResponseCache | None = None,
    ) -> None:
        self.adapter = adapter
        self.rate_limiter = rate_limiter
        self.cache = cache
        self.requests_made = 0

    def retrieve(self, url: str, source_type: str) -> RetrievalResult:
        """Fetch one URL, or report why not. Never raises on a fetch failure."""
        if self.cache is not None:
            cached = self.cache.get(url)
            if cached is not None:
                return RetrievalResult(
                    provenance=Provenance(
                        source_type=source_type,
                        source_url=url,
                        retrieved_at=utcnow(),
                        retrieval_mode=RETRIEVAL_MODE_CACHE,
                        outcome=OUTCOME_SUCCESS,
                        content_sha256=sha256_of_bytes(cached),
                        content_bytes=len(cached),
                    ),
                    content=cached,
                )

        if self.adapter is None:
            return self._failure(
                url,
                source_type,
                OUTCOME_FETCH_FAILED,
                "Live retrieval is not configured. The gateway has no adapter, "
                "so this run is offline. This is the normal state: audits read "
                "the frozen corpus and never require network access.",
            )

        if self.rate_limiter is not None:
            self.rate_limiter.wait()

        try:
            self.requests_made += 1
            status, body = self.adapter.fetch(url)
        except BlockedError as exc:
            return self._failure(
                url, source_type, OUTCOME_BLOCKED,
                f"The service refused the request: {exc}. Collection should "
                f"stop rather than retry.",
            )
        except Exception as exc:  # noqa: BLE001 - every transport fault is data
            return self._failure(
                url, source_type, OUTCOME_FETCH_FAILED,
                f"{type(exc).__name__}: {exc}",
            )

        if status in self.BLOCKING_STATUSES:
            return self._failure(
                url, source_type, OUTCOME_BLOCKED,
                f"HTTP {status}. The service is refusing requests; stop "
                f"collecting and increase the interval before trying again.",
                http_status=status,
            )
        if status == 404:
            return self._failure(
                url, source_type, OUTCOME_NOT_FOUND,
                "HTTP 404. The page does not exist. For a Data Safety URL this "
                "may mean the application has been removed from the store.",
                http_status=status,
            )
        if status >= 400 or not body:
            return self._failure(
                url, source_type, OUTCOME_FETCH_FAILED,
                f"HTTP {status} with {len(body) if body else 0} bytes.",
                http_status=status,
            )

        if self.cache is not None:
            self.cache.put(url, body)

        return RetrievalResult(
            provenance=Provenance(
                source_type=source_type,
                source_url=url,
                retrieved_at=utcnow(),
                retrieval_mode=RETRIEVAL_MODE_LIVE,
                outcome=OUTCOME_SUCCESS,
                content_sha256=sha256_of_bytes(body),
                content_bytes=len(body),
                http_status=status,
            ),
            content=body,
        )

    def _failure(
        self,
        url: str,
        source_type: str,
        outcome: str,
        reason: str,
        http_status: int | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(
            provenance=Provenance(
                source_type=source_type,
                source_url=url,
                retrieved_at=utcnow(),
                retrieval_mode=RETRIEVAL_MODE_LIVE,
                outcome=outcome,
                http_status=http_status,
                failure_reason=reason,
            )
        )


def parse_failure(
    url: str, source_type: str, reason: str, http_status: int | None = None
) -> Provenance:
    """Provenance for a page that was fetched but could not be understood.

    Separated from a fetch failure because the remedy differs: a parse failure
    means the adapter needs updating, which Phase 1 expects to happen.
    """
    return Provenance(
        source_type=source_type,
        source_url=url,
        retrieved_at=utcnow(),
        retrieval_mode=RETRIEVAL_MODE_LIVE,
        outcome=OUTCOME_PARSE_FAILED,
        http_status=http_status,
        failure_reason=reason,
    )
