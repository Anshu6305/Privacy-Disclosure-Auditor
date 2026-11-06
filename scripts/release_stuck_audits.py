#!/usr/bin/env python3
"""Give a terminal status to audits a crashed worker left `running`.

    python scripts/release_stuck_audits.py --database privacy_auditor_pilot
    python scripts/release_stuck_audits.py --database privacy_auditor_pilot --apply

The worker now marks an audit failed when it stops unexpectedly, so no new
audit should ever need this. It exists for rows stranded before that fix,
and `claim_next_audit` returns nothing while any audit is `running` — so a
single stranded row blocks the whole queue and no later audit can start.

**It only ever moves `running` to `failed`.** Queued, completed and failed
audits are not touched, no verdict or evidence row is read or written, and
nothing is deleted. The failure reason says the audit was released and why,
so the history records what happened rather than quietly losing a run.

Dry run by default; `--apply` is required to write.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.db.models import AuditRun  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from analysis.vocabulary import STATUS_FAILED, STATUS_RUNNING  # noqa: E402

REASON = (
    "Released by scripts/release_stuck_audits.py: the worker stopped without "
    "recording an outcome, leaving this audit `running` and the queue "
    "blocked. No report was produced and nothing here should be read as a "
    "finding. Request a new audit once the cause is fixed."
)


def release(session: Session, *, reason: str = REASON) -> list[int]:
    """Mark every `running` audit failed. Returns the ids affected."""
    stranded = session.execute(
        select(AuditRun).where(AuditRun.status == STATUS_RUNNING)
    ).scalars().all()
    for audit in stranded:
        audit.status = STATUS_FAILED
        audit.failure_reason = reason
        audit.completed_at = datetime.now(timezone.utc)
    return [audit.audit_id for audit in stranded]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="privacy_auditor_pilot")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()

    if arguments.database_url:
        url = arguments.database_url
    else:
        from scripts.register_models import compose_url

        url = compose_url(arguments.database)
    print(f"database: {make_url(url).database}\n")

    engine = create_engine(url, future=True)
    with Session(engine) as session:
        released = release(session)
        if not released:
            print("No audit is stuck in `running`. Nothing to do.")
            session.rollback()
            return 0

        for audit_id in released:
            audit = session.get(AuditRun, audit_id)
            print(f"  audit {audit_id}: running -> failed  (app_id {audit.app_id})")

        if arguments.apply:
            session.commit()
            print(f"\nCommitted. {len(released)} audit(s) released.")
        else:
            session.rollback()
            print("\n--dry-run (default): rolled back, nothing was written.")
            print("Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
