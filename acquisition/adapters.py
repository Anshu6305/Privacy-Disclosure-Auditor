"""Replaceable transports for F-06.

Everything site-specific lives here. Phase 1 recorded the Play Store scraper
library as no longer actively maintained, with its own author advising that
the parser should be expected to break, so the project is built on the
assumption that whatever is here will stop working. When it does, only this
file changes.

**None of these adapters has been run against Google Play by this project.**
The development environment cannot reach `play.google.com`, and no pilot has
been performed. Passing unit tests here demonstrate the gateway's handling of
responses, not that live retrieval works. See `docs/M3_ACQUISITION_REPORT.md`.
"""

from __future__ import annotations

from collections.abc import Mapping

from acquisition.gateway import BlockedError

#: Phrases that indicate an interstitial rather than the page we asked for.
#: A challenge page returns HTTP 200, so status alone cannot detect it, and
#: parsing one as a declaration would produce an application that appears to
#: declare nothing.
CHALLENGE_MARKERS: tuple[str, ...] = (
    "unusual traffic",
    "detected unusual",
    "verify you are a human",
    "recaptcha",
    "/sorry/index",
    "captcha",
)


def looks_like_challenge(body: bytes) -> bool:
    """Whether a 200 response is actually a bot challenge."""
    sample = body[:4096].decode("utf-8", errors="ignore").lower()
    return any(marker in sample for marker in CHALLENGE_MARKERS)


class HttpxAdapter:
    """A plain HTTP transport.

    Deliberately minimal: one request, no retries, no redirect chasing beyond
    httpx's default. Retry policy belongs to the collector, which must slow
    down rather than try again, and the gateway records the failure either way.
    """

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = 20.0,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.extra_headers = dict(headers or {})

    def fetch(self, url: str) -> tuple[int, bytes]:
        import httpx  # imported here so the module loads without the dependency

        headers = {"User-Agent": self.user_agent, **self.extra_headers}
        response = httpx.get(
            url, headers=headers, timeout=self.timeout_seconds, follow_redirects=True
        )

        if looks_like_challenge(response.content):
            raise BlockedError(
                "the response looks like a bot challenge rather than the "
                "requested page; stop collecting and increase the interval"
            )

        return response.status_code, response.content


class NullAdapter:
    """An adapter that always refuses.

    Used to make an offline run explicit rather than accidental. A gateway
    built with this one records a clear failure for every request instead of
    silently having no transport.
    """

    def fetch(self, url: str) -> tuple[int, bytes]:
        raise RuntimeError(
            "live retrieval is disabled for this run; the corpus is read from "
            "disk and no request was made"
        )
