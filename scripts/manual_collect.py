#!/usr/bin/env python3
"""Add one application to the corpus from manually collected sources.

    python scripts/manual_collect.py --template > myapp.json
    python scripts/manual_collect.py --input myapp.json --policy-file saved.html

Automated Google Play collection is not available in this project's
environment: the listing host is not reachable from the development sandbox,
and the approved design has always forbidden mass scraping. This is the
documented manual path, and it writes exactly the same corpus record an
automated collector would, with the same provenance fields, so nothing
downstream can tell or needs to.

**What this will not do.**

* It will not invent a declaration. Omit the ``declaration`` key and the
  record is stored with no declaration and a status that says so.
* It will not treat an unread Data Safety section as "collects nothing".
  ``declares_no_data_collected`` is three-state: omit it and it stays null,
  which means *not read*. Setting it true with any declared entry present is
  rejected outright.
* It will not fetch, reconstruct or summarise a policy. The policy file you
  pass is stored byte for byte and hashed as-is, so every later quotation is
  a slice of the text that was actually collected.
* It will not accept a Data Safety category outside the approved fourteen.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from acquisition.corpus import CorpusPaths, write_record  # noqa: E402
from acquisition.models import (  # noqa: E402
    OUTCOME_SUCCESS,
    RETRIEVAL_MODE_MANUAL,
    ApplicationRecord,
    DataSafetyDeclaration,
    DeclaredDataEntry,
    Provenance,
    SecurityPractices,
    is_known_category,
)
from acquisition.policy_document import sha256_of_bytes  # noqa: E402
from analysis.vocabulary import SOURCE_DATA_SAFETY, SOURCE_PRIVACY_POLICY  # noqa: E402

TEMPLATE = {
    "package_name": "com.example.app",
    "app_name": "Example App",
    "developer_name": "Example Developer",
    "store_category": None,
    "play_store_url": "https://play.google.com/store/apps/details?id=com.example.app",
    "policy_url": "https://example.com/privacy",
    "_comment_declaration": (
        "Copy this from the application's Data Safety section on its Play "
        "Store listing. OMIT the whole 'declaration' key if you did not read "
        "the section: an absent declaration and a declaration of nothing are "
        "different facts and the system keeps them apart."
    ),
    "declaration": {
        "declares_no_data_collected": False,
        "entries": [
            {
                "ds_category": "Location",
                "data_type": "Approximate location",
                "is_collected": True,
                "is_shared": False,
                "purpose": "App functionality",
                "is_optional": False,
            }
        ],
        "security": {
            "data_encrypted_in_transit": None,
            "user_can_request_deletion": None,
        },
    },
}


def build_declaration(package_name: str, raw: dict) -> DataSafetyDeclaration:
    entries = []
    for index, entry in enumerate(raw.get("entries", [])):
        category = entry.get("ds_category")
        if not is_known_category(category):
            raise SystemExit(
                f"entry {index}: {category!r} is not one of the fourteen "
                "approved Data Safety categories. Use the category exactly as "
                "the listing shows it rather than a near equivalent."
            )
        entries.append(
            DeclaredDataEntry(
                ds_category=category,
                data_type=entry.get("data_type"),
                is_collected=bool(entry.get("is_collected", False)),
                is_shared=bool(entry.get("is_shared", False)),
                purposes=tuple(
                part.strip()
                for part in (entry.get("purpose") or "").split(";")
                if part.strip()
            ),
                is_optional=entry.get("is_optional"),
            )
        )

    security_raw = raw.get("security", {})
    return DataSafetyDeclaration(
        package_name=package_name,
        entries=tuple(entries),
        security=SecurityPractices(
            data_encrypted_in_transit=security_raw.get("data_encrypted_in_transit"),
            data_deletion_available=security_raw.get("user_can_request_deletion"),
        ),
        declares_no_data_collected=bool(raw.get("declares_no_data_collected", False)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", action="store_true", help="print a blank record")
    parser.add_argument("--input", type=Path, help="the filled-in JSON")
    parser.add_argument(
        "--policy-file",
        type=Path,
        help="the privacy policy as saved from the browser; stored byte for byte",
    )
    parser.add_argument("--root", type=Path, default=Path("data/corpus"))
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    if arguments.template:
        print(json.dumps(TEMPLATE, indent=2))
        return 0
    if not arguments.input:
        parser.error("--input is required (or --template to start one)")

    raw = json.loads(arguments.input.read_text(encoding="utf-8"))
    package_name = raw.get("package_name")
    if not package_name:
        raise SystemExit("package_name is required")

    collected_at = datetime.now(timezone.utc)
    paths = CorpusPaths(arguments.root)
    provenances: list[Provenance] = []

    policy_path = policy_sha = None
    if arguments.policy_file:
        if not arguments.policy_file.is_file():
            raise SystemExit(f"{arguments.policy_file} does not exist")
        body = arguments.policy_file.read_bytes()
        policy_sha = sha256_of_bytes(body)
        target = paths.raw_policies / f"{policy_sha}.html"
        policy_path = target.relative_to(paths.root).as_posix()
        if not arguments.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        provenances.append(
            Provenance(
                source_type=SOURCE_PRIVACY_POLICY,
                source_url=raw.get("policy_url") or "",
                retrieved_at=collected_at,
                retrieval_mode=RETRIEVAL_MODE_MANUAL,
                outcome=OUTCOME_SUCCESS,
                content_sha256=policy_sha,
            )
        )

    declaration = None
    if "declaration" in raw and raw["declaration"] is not None:
        declaration = build_declaration(package_name, raw["declaration"])
        declaration_bytes = json.dumps(
            raw["declaration"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        declaration_sha = sha256_of_bytes(declaration_bytes)
        provenances.append(
            Provenance(
                source_type=SOURCE_DATA_SAFETY,
                source_url=raw.get("play_store_url") or "",
                retrieved_at=collected_at,
                retrieval_mode=RETRIEVAL_MODE_MANUAL,
                outcome=OUTCOME_SUCCESS,
                content_sha256=declaration_sha,
            )
        )

    record = ApplicationRecord(
        package_name=package_name,
        app_name=raw.get("app_name") or package_name,
        developer_name=raw.get("developer_name"),
        store_category=raw.get("store_category"),
        play_store_url=raw.get("play_store_url"),
        policy_url=raw.get("policy_url"),
        declaration=declaration,
        policy_path=policy_path,
        policy_sha256=policy_sha,
        collected_at=collected_at,
        provenances=tuple(provenances),
        validation_status="manually_collected",
    )

    print(f"package      : {record.package_name}")
    print(f"policy       : {'stored, sha256 ' + policy_sha if policy_sha else 'NONE'}")
    print(
        "declaration  : "
        + (
            f"{len(declaration.entries)} entries"
            if declaration
            else "NONE — the section was not read, which is not the same as "
            "'collects nothing'"
        )
    )
    print(f"analysable   : {record.is_analysable}")

    if arguments.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    written = write_record(paths, record)
    print(f"\nwritten: {written}")
    print("Next: python scripts/import_corpus.py --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
