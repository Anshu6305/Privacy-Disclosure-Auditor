#!/usr/bin/env python3
"""Request an audit, optionally on a named model variant (F-13, DD-8).

    python scripts/request_audit.py com.spotify.music
    python scripts/request_audit.py com.spotify.music --variant improved --apply

This is the command-line tooling DD-8 reserves the variant for. End users
never choose a variant: the API omits it, the active version set is used,
and no selector exists in the frontend. A Corpus Maintainer comparing the
baseline against the improved model runs the same application twice from
here, once per variant.

**There is no fallback.** If the requested variant is not registered and
active for all three tasks, no audit is created and the refusal says which
task was missing it. Running the other variant instead would produce a
report whose provenance names a model that never ran.

Dry run by default; `--apply` is required to create the audit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.audit_service import AuditRequested, AuditService  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from analysis.vocabulary import MODEL_VARIANTS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_name")
    parser.add_argument(
        "--variant",
        default=None,
        choices=sorted(MODEL_VARIANTS),
        help="internal; omit for the active version set",
    )
    parser.add_argument("--database", default="privacy_auditor_pilot")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()

    if arguments.database_url:
        url = arguments.database_url
    else:
        from scripts.register_models import compose_url

        url = compose_url(arguments.database)
    print(f"database : {make_url(url).database}")
    print(f"package  : {arguments.package_name}")
    print(f"variant  : {arguments.variant or 'active version set'}")

    engine = create_engine(url, future=True)
    with Session(engine) as session:
        result = AuditService(session).request_audit(
            arguments.package_name, variant=arguments.variant
        )
        if not isinstance(result, AuditRequested):
            session.rollback()
            print(f"\nREFUSED ({result.reason}): {result.detail}", file=sys.stderr)
            return 1

        print(f"\naudit {result.audit_id}: {result.status}")
        print(f"  snapshot          : {result.snapshot_id}")
        print(f"  mapping version   : {result.taxonomy_mapping_version_id}")
        print(f"  classification    : {result.classification_model_id}")
        print(f"  span extraction   : {result.span_model_id}")
        print(f"  alignment         : {result.alignment_model_id}")

        if arguments.apply:
            session.commit()
            print("\nCommitted. The worker will claim it.")
        else:
            session.rollback()
            print("\n--dry-run (default): rolled back, no audit was created.")
            print("Re-run with --apply to queue it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
