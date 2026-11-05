"""F-07 — record where a disclosure came from.

Provenance is built here and kept deliberately free of any database shape.
Design decision D-1 — whether a disclosure snapshot is one row per collection
event or one row per source — is unresolved, so this module produces
per-source provenance, the smaller unit, from which either arrangement can be
assembled when D-1 is settled.

Nothing here writes to a database, and no persistent snapshot schema is
introduced. That is Milestone 3B.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from acquisition.models import (
    OUTCOME_SUCCESS,
    RETRIEVAL_MODE_MANUAL,
    Provenance,
)
from acquisition.policy_document import sha256_of_file
from analysis.vocabulary import SOURCE_DATA_SAFETY, SOURCE_PRIVACY_POLICY


def manual_import_provenance(
    source_type: str,
    source_url: str,
    retrieved_at: datetime,
    content_sha256: str,
    content_bytes: int | None = None,
    collector_note: str | None = None,
) -> Provenance:
    """Provenance for a document a team member obtained by hand.

    This is the project's primary acquisition path, not a fallback. Phase 1
    recorded the scraper library as unmaintained, so a manually saved page with
    an honest record of who saved it and when is more dependable than an
    automated fetch that may silently return a changed layout.
    """
    return Provenance(
        source_type=source_type,
        source_url=source_url,
        retrieved_at=retrieved_at,
        retrieval_mode=RETRIEVAL_MODE_MANUAL,
        outcome=OUTCOME_SUCCESS,
        content_sha256=content_sha256,
        content_bytes=content_bytes,
        collector_note=collector_note,
    )


def provenance_for_stored_file(
    source_type: str,
    source_url: str,
    path: Path | str,
    retrieved_at: datetime,
    collector_note: str | None = None,
) -> Provenance:
    """Build manual-import provenance by hashing a file already on disk."""
    path = Path(path)
    return manual_import_provenance(
        source_type=source_type,
        source_url=source_url,
        retrieved_at=retrieved_at,
        content_sha256=sha256_of_file(path),
        content_bytes=path.stat().st_size,
        collector_note=collector_note,
    )


def provenance_to_dict(provenance: Provenance) -> dict[str, Any]:
    return {
        "source_type": provenance.source_type,
        "source_url": provenance.source_url,
        "retrieved_at": provenance.retrieved_at.isoformat(),
        "retrieval_mode": provenance.retrieval_mode,
        "outcome": provenance.outcome,
        "content_sha256": provenance.content_sha256,
        "content_bytes": provenance.content_bytes,
        "http_status": provenance.http_status,
        "failure_reason": provenance.failure_reason,
        "collector_note": provenance.collector_note,
    }


def provenance_from_dict(raw: Mapping[str, Any]) -> Provenance:
    required = ("source_type", "source_url", "retrieved_at", "retrieval_mode", "outcome")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"provenance is missing required fields: {missing}")

    return Provenance(
        source_type=str(raw["source_type"]),
        source_url=str(raw["source_url"]),
        retrieved_at=datetime.fromisoformat(str(raw["retrieved_at"])),
        retrieval_mode=str(raw["retrieval_mode"]),
        outcome=str(raw["outcome"]),
        content_sha256=raw.get("content_sha256"),
        content_bytes=raw.get("content_bytes"),
        http_status=raw.get("http_status"),
        failure_reason=raw.get("failure_reason"),
        collector_note=raw.get("collector_note"),
    )


def write_provenance_log(path: Path | str, entries: Iterable[Provenance]) -> int:
    """Append provenance records to a JSON Lines log.

    Append-only, including failures. The log is how a collection pass can be
    audited afterwards: how many applications were attempted, how many
    succeeded, and why the rest did not.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as handle:
        for provenance in entries:
            handle.write(json.dumps(provenance_to_dict(provenance)) + "\n")
            count += 1
    return count


def read_provenance_log(path: Path | str) -> list[Provenance]:
    path = Path(path)
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(provenance_from_dict(json.loads(line)))
    return records


def summarise_log(entries: Iterable[Provenance]) -> dict[str, int]:
    """Counts by outcome, for an honest report of what a pass achieved."""
    summary: dict[str, int] = {}
    for provenance in entries:
        summary[provenance.outcome] = summary.get(provenance.outcome, 0) + 1
    return dict(sorted(summary.items()))


def data_safety_url(package_name: str) -> str:
    """The public Data Safety page for a package."""
    return f"https://play.google.com/store/apps/datasafety?id={package_name}"


def play_listing_url(package_name: str) -> str:
    return f"https://play.google.com/store/apps/details?id={package_name}"


__all__ = [
    "SOURCE_DATA_SAFETY",
    "SOURCE_PRIVACY_POLICY",
    "data_safety_url",
    "manual_import_provenance",
    "play_listing_url",
    "provenance_for_stored_file",
    "provenance_from_dict",
    "provenance_to_dict",
    "read_provenance_log",
    "summarise_log",
    "write_provenance_log",
]
