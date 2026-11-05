"""The offline operational corpus: layout, manifest and validation.

This is the **Android application corpus** — real applications, their Google
Play Data Safety declarations and their privacy policy documents. It is not
OPP-115, which is a corpus of website privacy policies used to train the
classifier. The two are kept entirely separate and are never mixed.

Why a frozen offline corpus, rather than fetching during an audit: Phase 1
identified Play Store access as the project's least reliable dependency and
recorded the scraper library as unmaintained. A corpus collected slowly,
verified, and then frozen means an audit, an evaluation run and a
demonstration all work with no network at all.

Layout::

    data/corpus/
      manifest.json                    index of every record
      apps/<package_name>/record.json  one application
      raw/policies/<sha256>.html       policy documents, never modified
      processed/                       Milestone 4 output; empty for now
      provenance.jsonl                 append-only log of every attempt

Raw documents are named by the SHA-256 of their bytes, so a document is
identified by its content. Two applications sharing a policy share one file,
and re-saving an unchanged page produces the same name rather than a
duplicate.

Nothing in ``data/`` is committed. The corpus is third-party content that is
not ours to redistribute; the manifest and these tools are committed so the
corpus can be rebuilt and checked.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from acquisition.declaration import (
    DeclarationFormatError,
    declaration_to_dict,
    normalise_declaration,
)
from acquisition.models import ApplicationRecord
from acquisition.policy_document import sha256_of_file
from acquisition.provenance import provenance_from_dict, provenance_to_dict

#: Bumped when the record format changes incompatibly, so an old corpus is
#: rejected with a clear message rather than misread.
CORPUS_SCHEMA_VERSION = "1.0"

DEFAULT_CORPUS_ROOT = Path("data/corpus")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusPaths:
    root: Path

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def apps(self) -> Path:
        return self.root / "apps"

    @property
    def raw_policies(self) -> Path:
        return self.root / "raw" / "policies"

    @property
    def processed(self) -> Path:
        return self.root / "processed"

    @property
    def provenance_log(self) -> Path:
        return self.root / "provenance.jsonl"

    def record_path(self, package_name: str) -> Path:
        return self.apps / package_name / "record.json"

    def policy_path(self, sha256: str, suffix: str = ".html") -> Path:
        return self.raw_policies / f"{sha256}{suffix}"

    def create(self) -> None:
        for directory in (self.apps, self.raw_policies, self.processed):
            directory.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Record serialisation
# ---------------------------------------------------------------------------


def record_to_dict(record: ApplicationRecord) -> dict[str, Any]:
    return {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "package_name": record.package_name,
        "app_name": record.app_name,
        "developer_name": record.developer_name,
        "store_category": record.store_category,
        "play_store_url": record.play_store_url,
        "policy_url": record.policy_url,
        "policy_path": record.policy_path,
        "policy_sha256": record.policy_sha256,
        "collected_at": record.collected_at.isoformat() if record.collected_at else None,
        "declaration": (
            declaration_to_dict(record.declaration) if record.declaration else None
        ),
        "provenances": [provenance_to_dict(p) for p in record.provenances],
        "validation_status": record.validation_status,
    }


def record_from_dict(raw: dict[str, Any]) -> ApplicationRecord:
    if not isinstance(raw, Mapping):
        raise CorpusFormatError(
            f"a record must be a JSON object, got {type(raw).__name__}"
        )

    version = raw.get("schema_version")
    if version != CORPUS_SCHEMA_VERSION:
        raise CorpusFormatError(
            f"record schema_version is {version!r}, this code reads "
            f"{CORPUS_SCHEMA_VERSION!r}. Migrate the corpus rather than "
            f"reading it with mismatched code."
        )

    package_name = raw.get("package_name")
    if not package_name:
        raise CorpusFormatError("record is missing 'package_name'")

    declaration = None
    if raw.get("declaration") is not None:
        declaration = normalise_declaration(raw["declaration"])
        if declaration.package_name != package_name:
            raise CorpusFormatError(
                f"{package_name}: the embedded declaration names a different "
                f"package, {declaration.package_name!r}. One of the two is "
                f"wrong and the record must be corrected at source."
            )

    collected_at = raw.get("collected_at")
    return ApplicationRecord(
        package_name=package_name,
        app_name=raw.get("app_name") or package_name,
        developer_name=raw.get("developer_name"),
        store_category=raw.get("store_category"),
        play_store_url=raw.get("play_store_url"),
        policy_url=raw.get("policy_url"),
        declaration=declaration,
        policy_path=raw.get("policy_path"),
        policy_sha256=raw.get("policy_sha256"),
        collected_at=datetime.fromisoformat(collected_at) if collected_at else None,
        provenances=tuple(
            provenance_from_dict(p) for p in raw.get("provenances", ())
        ),
        validation_status=raw.get("validation_status", "unvalidated"),
    )


class CorpusFormatError(ValueError):
    """A corpus file does not match the documented format."""


# ---------------------------------------------------------------------------
# Reading and writing
# ---------------------------------------------------------------------------


def write_record(paths: CorpusPaths, record: ApplicationRecord) -> Path:
    path = paths.record_path(record.package_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record_to_dict(record), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def read_record(path: Path | str) -> ApplicationRecord:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusFormatError(f"{path}: not valid JSON — {exc}") from exc
    return record_from_dict(raw)


def iter_records(paths: CorpusPaths) -> Iterable[tuple[Path, ApplicationRecord]]:
    """Every record in the corpus, in package-name order."""
    if not paths.apps.is_dir():
        return
    for record_path in sorted(paths.apps.glob("*/record.json")):
        yield record_path, read_record(record_path)


def build_manifest(paths: CorpusPaths) -> dict[str, Any]:
    """An index of the corpus, derived from the records themselves.

    Derived rather than maintained by hand, so it cannot drift from what is
    actually on disk.
    """
    entries = []
    for _, record in iter_records(paths):
        entries.append(
            {
                "package_name": record.package_name,
                "app_name": record.app_name,
                "has_declaration": record.declaration is not None,
                "has_policy": record.policy_sha256 is not None,
                "policy_sha256": record.policy_sha256,
                "collected_at": (
                    record.collected_at.isoformat() if record.collected_at else None
                ),
                "validation_status": record.validation_status,
            }
        )
    return {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "corpus": "operational Android application corpus",
        "note": (
            "This is NOT OPP-115. OPP-115 is a corpus of website privacy "
            "policies used to train the classifier and lives in data/raw/opp115."
        ),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "application_count": len(entries),
        "analysable_count": sum(
            1 for e in entries if e["has_declaration"] and e["has_policy"]
        ),
        "applications": entries,
    }


def write_manifest(paths: CorpusPaths) -> Path:
    paths.root.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(paths)
    paths.manifest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return paths.manifest


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class ValidationReport:
    """What is wrong with the corpus, separated by severity.

    An *error* makes a record unusable. A *warning* is worth knowing but does
    not stop an audit. The distinction matters because a corpus with 40
    incomplete records is still a usable corpus of the remainder, and saying
    so honestly is better than refusing to proceed.
    """

    corpus_root: Path
    records_read: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    missing_declaration: list[str] = field(default_factory=list)
    missing_policy: list[str] = field(default_factory=list)
    hash_mismatches: list[str] = field(default_factory=list)
    analysable: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_corpus(root: Path | str = DEFAULT_CORPUS_ROOT) -> ValidationReport:
    """Check every record: duplicates, completeness and document hashes."""
    paths = CorpusPaths(Path(root))
    report = ValidationReport(corpus_root=paths.root)

    if not paths.root.is_dir():
        report.errors.append(
            f"Corpus directory not found: {paths.root}. See "
            f"docs/M3_ACQUISITION_REPORT.md for the import procedure."
        )
        return report

    seen: dict[str, Path] = {}

    for record_path, record in _safe_iter(paths, report):
        report.records_read += 1

        # Duplicate detection: a package name appearing twice means two
        # directories describe the same application, and an audit would then
        # depend on which one was read.
        if record.package_name in seen:
            report.duplicates.append(record.package_name)
            report.errors.append(
                f"duplicate package {record.package_name}: "
                f"{seen[record.package_name]} and {record_path}"
            )
        else:
            seen[record.package_name] = record_path

        directory_name = record_path.parent.name
        if directory_name != record.package_name:
            report.errors.append(
                f"{record_path}: directory is {directory_name!r} but the record "
                f"declares package {record.package_name!r}"
            )

        if record.declaration is None:
            report.missing_declaration.append(record.package_name)
            report.warnings.append(
                f"{record.package_name}: no Data Safety declaration. Not "
                f"auditable until one is imported."
            )

        if record.policy_sha256 is None or record.policy_path is None:
            report.missing_policy.append(record.package_name)
            report.warnings.append(
                f"{record.package_name}: no privacy policy document. Not "
                f"auditable until one is imported."
            )
        else:
            policy_file = Path(record.policy_path)
            if not policy_file.is_absolute():
                policy_file = paths.root.parent.parent / record.policy_path
                if not policy_file.is_file():
                    policy_file = paths.root / record.policy_path
            if not policy_file.is_file():
                report.errors.append(
                    f"{record.package_name}: policy file missing at "
                    f"{record.policy_path}"
                )
            else:
                actual = sha256_of_file(policy_file)
                if actual != record.policy_sha256:
                    report.hash_mismatches.append(record.package_name)
                    report.errors.append(
                        f"{record.package_name}: policy hash mismatch. "
                        f"recorded {record.policy_sha256[:16]}..., "
                        f"actual {actual[:16]}.... The stored file is not the "
                        f"document this record describes."
                    )

        if record.is_analysable:
            report.analysable.append(record.package_name)

    return report


def _safe_iter(paths: CorpusPaths, report: ValidationReport):
    """Iterate records, turning a malformed one into an error rather than a
    crash, so one bad file does not hide the state of the rest."""
    if not paths.apps.is_dir():
        report.errors.append(f"no apps directory under {paths.root}")
        return
    for record_path in sorted(paths.apps.glob("*/record.json")):
        try:
            yield record_path, read_record(record_path)
        except (CorpusFormatError, DeclarationFormatError, ValueError) as exc:
            report.errors.append(f"{record_path}: {exc}")


def format_report(report: ValidationReport) -> str:
    lines = [
        "-" * 68,
        "Operational Android application corpus — validation",
        "-" * 68,
        f"Corpus root        : {report.corpus_root}",
        f"Records read       : {report.records_read}",
        f"Analysable         : {len(report.analysable)}  "
        f"(declaration and policy both present)",
        f"Missing declaration: {len(report.missing_declaration)}",
        f"Missing policy     : {len(report.missing_policy)}",
        f"Duplicates         : {len(report.duplicates)}",
        f"Hash mismatches    : {len(report.hash_mismatches)}",
    ]
    if report.warnings:
        lines += ["", f"Warnings ({len(report.warnings)})"]
        lines += [f"  - {w}" for w in report.warnings[:15]]
        if len(report.warnings) > 15:
            lines.append(f"  ... and {len(report.warnings) - 15} more")
    if report.errors:
        lines += ["", f"Errors ({len(report.errors)})"]
        lines += [f"  ! {e}" for e in report.errors[:15]]
        if len(report.errors) > 15:
            lines.append(f"  ... and {len(report.errors) - 15} more")

    lines += ["", "RESULT: usable" if report.ok else "RESULT: errors found", "-" * 68]
    return "\n".join(lines)
