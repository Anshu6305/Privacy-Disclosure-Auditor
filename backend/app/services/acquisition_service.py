"""F-06 — optional live retrieval, wired to the snapshot and provenance layer.

**Offline-first, and that is a requirement rather than a default.** No audit
depends on this module. The pipeline reads the frozen filesystem corpus; live
retrieval only adds to it. If Google blocks the project the day before the
demonstration, nothing stops working, and a deployment with no adapter
configured is a supported configuration rather than a broken one.

Everything that leaves the machine goes through :class:`AcquisitionGateway`
(NFR-16), so the rate limiter (NFR-15), the response cache and the failure
classification apply here unchanged. This module adds no transport of its own.

**It also adds no scraper.** The project has no parser for Google's Data
Safety markup, and inventing one would mean inventing the declarations it
produced. A successful fetch with no parser configured is therefore recorded
as ``parse_failed`` — we reached the page and could not understand it — which
is deliberately *not* the same as the application declaring nothing. A parser
can be injected when the team writes one.

One application at a time, because the gateway's rate limiter is per-process
and Phase 1 ruled out mass scraping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.db.repositories.application_repo import ApplicationRepository
from app.db.repositories.snapshot_repo import SnapshotRepository
from sqlalchemy.orm import Session

from acquisition.corpus import CorpusPaths
from acquisition.declaration import DeclarationFormatError, normalise_declaration
from acquisition.gateway import AcquisitionGateway, parse_failure
from acquisition.models import (
    OUTCOME_NOT_FOUND,
    OUTCOME_SUCCESS,
    ApplicationRecord,
    DataSafetyDeclaration,
    Provenance,
)
from acquisition.policy_document import media_type_for, sha256_of_bytes
from acquisition.provenance import data_safety_url, play_listing_url
from analysis.vocabulary import SOURCE_DATA_SAFETY, SOURCE_PRIVACY_POLICY


class DeclarationParser(Protocol):
    """Turns a fetched Data Safety page into the documented corpus shape.

    Deliberately a protocol with no implementation in the repository. Writing
    one is a scraping task the team has not done, and a stub that returned an
    empty declaration would manufacture a disclosure.
    """

    def parse(self, body: bytes, package_name: str) -> Mapping[str, Any]:
        """Return the raw declaration mapping, or raise to signal a parse
        failure."""
        ...


@dataclass(frozen=True, slots=True)
class LiveRetrievalUnavailable:
    """Live retrieval is not configured for this deployment.

    Not an error. The offline corpus is what every audit reads, and a
    deployment without an adapter is the project's normal state.
    """

    package_name: str
    detail: str = (
        "Live retrieval is not configured: the acquisition gateway has no "
        "adapter, so this run is offline. Audits read the frozen corpus and "
        "never require network access. Collect the application manually and "
        "import it; see docs/M3_ACQUISITION_REPORT.md section 10."
    )


@dataclass(frozen=True, slots=True)
class LiveRetrievalResult:
    """What one live collection attempt achieved, successful or not."""

    package_name: str
    snapshot_id: int | None
    status: str
    declaration_outcome: str
    policy_outcome: str
    provenances: tuple[Provenance, ...]
    policy_stored_at: str | None
    persisted: bool

    @property
    def succeeded(self) -> bool:
        """Both sources captured. Anything less is recorded, not hidden."""
        return (
            self.declaration_outcome == OUTCOME_SUCCESS
            and self.policy_outcome == OUTCOME_SUCCESS
        )


class LiveAcquisitionService:
    """F-06. Fetch through the gateway, store, and record one collection event.

    ``gateway`` is injected so the offline case is the same code path with a
    different adapter, rather than a branch that is never exercised in tests.
    """

    def __init__(
        self,
        session: Session,
        gateway: AcquisitionGateway,
        corpus_root: Path | str = "data/corpus",
        declaration_parser: DeclarationParser | None = None,
        repository_root: Path | str = ".",
    ) -> None:
        self._session = session
        self._gateway = gateway
        self._paths = CorpusPaths(Path(corpus_root))
        self._parser = declaration_parser
        self._repository_root = Path(repository_root)
        self._applications = ApplicationRepository(session)
        self._snapshots = SnapshotRepository(session, policy_root=repository_root)

    @property
    def available(self) -> bool:
        """Whether a fetch can be **attempted**. Never whether one succeeds."""
        return self._gateway.adapter is not None

    def collect(
        self,
        package_name: str,
        *,
        app_name: str | None = None,
        policy_url: str | None = None,
        persist: bool = True,
    ) -> LiveRetrievalResult | LiveRetrievalUnavailable:
        """Attempt one live collection and record what happened.

        ``policy_url`` must be supplied by the caller. It normally comes from
        the Play Store listing, and discovering it there needs the parser this
        project does not have; guessing a URL would attribute some other
        document to the application.
        """
        package_name = (package_name or "").strip()
        if not package_name:
            raise ValueError("a package name is required")
        if not self.available:
            return LiveRetrievalUnavailable(package_name=package_name)

        declaration, declaration_provenance = self._retrieve_declaration(package_name)
        policy_provenance, policy_path = self._retrieve_policy(package_name, policy_url)

        record = ApplicationRecord(
            package_name=package_name,
            app_name=app_name or package_name,
            developer_name=None,
            store_category=None,
            play_store_url=play_listing_url(package_name),
            policy_url=policy_url,
            declaration=declaration,
            policy_path=policy_path,
            policy_sha256=policy_provenance.content_sha256 if policy_path else None,
            collected_at=datetime.now(timezone.utc),
            provenances=(declaration_provenance, policy_provenance),
            validation_status="live",
        )

        snapshot_id: int | None = None
        if persist:
            app_id, _created = self._applications.upsert_from_record(record)
            snapshot = self._snapshots.record_collection_event(app_id, record)
            snapshot_id = snapshot.snapshot_id
            status = snapshot.status
        else:
            from app.db.repositories.snapshot_repo import derive_status

            status = derive_status(record)

        return LiveRetrievalResult(
            package_name=package_name,
            snapshot_id=snapshot_id,
            status=status,
            declaration_outcome=declaration_provenance.outcome,
            policy_outcome=policy_provenance.outcome,
            provenances=(declaration_provenance, policy_provenance),
            policy_stored_at=policy_path,
            persisted=persist,
        )

    # -- the two sources ---------------------------------------------------

    def _retrieve_declaration(
        self, package_name: str
    ) -> tuple[DataSafetyDeclaration | None, Provenance]:
        url = data_safety_url(package_name)
        result = self._gateway.retrieve(url, SOURCE_DATA_SAFETY)
        if not result.ok or result.content is None:
            return None, result.provenance

        if self._parser is None:
            # Fetched and not understood. Distinct from "declares nothing":
            # the remedy is a parser, not a verdict.
            return None, parse_failure(
                url,
                SOURCE_DATA_SAFETY,
                "The page was retrieved but no Data Safety parser is "
                "configured, so no declaration could be read from it. This is "
                "not an absent declaration.",
                http_status=result.provenance.http_status,
            )

        try:
            raw = self._parser.parse(result.content, package_name)
            declaration = normalise_declaration(raw, provenance=result.provenance)
        except (DeclarationFormatError, ValueError, KeyError, TypeError) as exc:
            return None, parse_failure(
                url,
                SOURCE_DATA_SAFETY,
                f"The page was retrieved but could not be parsed: "
                f"{type(exc).__name__}: {exc}",
                http_status=result.provenance.http_status,
            )

        return declaration, result.provenance

    def _retrieve_policy(
        self, package_name: str, policy_url: str | None
    ) -> tuple[Provenance, str | None]:
        if not policy_url:
            return (
                Provenance(
                    source_type=SOURCE_PRIVACY_POLICY,
                    source_url=play_listing_url(package_name),
                    retrieved_at=datetime.now(timezone.utc),
                    retrieval_mode="live_fetch",
                    outcome=OUTCOME_NOT_FOUND,
                    failure_reason=(
                        "No privacy policy URL was supplied. It is published "
                        "on the Play Store listing, and reading it from there "
                        "needs the Data Safety parser this project does not "
                        "have. A guessed URL could attribute another "
                        "document to this application."
                    ),
                ),
                None,
            )

        result = self._gateway.retrieve(policy_url, SOURCE_PRIVACY_POLICY)
        if not result.ok or result.content is None:
            return result.provenance, None

        digest = sha256_of_bytes(result.content)
        suffix = media_type_for(Path(policy_url)) and Path(policy_url).suffix or ".html"
        if suffix not in {".html", ".htm", ".pdf", ".txt"}:
            suffix = ".html"
        destination = self._paths.policy_path(digest, suffix=suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(result.content)

        # Stored relative to the repository root so a corpus stays portable.
        try:
            stored = str(destination.resolve().relative_to(self._repository_root.resolve()))
        except ValueError:
            stored = str(destination)
        return result.provenance, stored


__all__ = [
    "DeclarationParser",
    "LiveAcquisitionService",
    "LiveRetrievalResult",
    "LiveRetrievalUnavailable",
]
