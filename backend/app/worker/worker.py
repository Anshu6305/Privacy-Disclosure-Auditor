"""F-32/F-33 — the background worker.

A loop, a database table and nothing else. The approved deployment has three
containers and no message broker: the queue is `audit_run`, claimed with
``FOR UPDATE SKIP LOCKED``.

**One audit at a time** (design decision DD-2). The memory plan assumes one
model set is resident at a time on an 8 GB machine; raising the concurrency
breaks that assumption rather than speeding anything up, so audits queue.

Models are built once per process and reused. A worker that cannot build them
**refuses to start** rather than running audits it would have to invent
predictions for.
"""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass

from app.config import get_settings
from app.db.session import engine_or_none
from app.services.audit_pipeline import (
    AuditFailedError,
    claim_next_audit,
)
from sqlalchemy.orm import Session

logger = logging.getLogger("auditor.worker")


@dataclass
class WorkerStats:
    claimed: int = 0
    completed: int = 0
    failed: int = 0


class AuditWorker:
    """Claims one audit, runs it, commits, repeats.

    ``build_pipeline`` is injected: it receives a session and returns an
    :class:`AuditPipeline`. Injecting it keeps the loop testable without
    models and makes the "no models, no worker" rule explicit at startup.
    """

    def __init__(self, session_factory, build_pipeline, poll_interval: float = 2.0):
        self._session_factory = session_factory
        self._build_pipeline = build_pipeline
        self.poll_interval = poll_interval
        self.stats = WorkerStats()
        self._stopping = False

    def stop(self, *_signal_args) -> None:
        """Finish the audit in hand, then exit. Never abandons a claimed run."""
        self._stopping = True

    def run_once(self) -> bool:
        """Claim and run at most one audit. True if one was processed.

        The claim is committed before the work starts, so a crash mid-audit
        leaves the row ``running`` with a ``claimed_at`` rather than silently
        back in the queue for a second worker.
        """
        with self._session_factory() as session:
            audit = claim_next_audit(session)
            if audit is None:
                return False
            audit_id = audit.audit_id
            session.commit()
            self.stats.claimed += 1

        with self._session_factory() as session:
            pipeline = self._build_pipeline(session)
            try:
                outcome = pipeline.run(audit_id)
            except AuditFailedError as failure:
                # The pipeline has already recorded status and reason on the
                # row; committing stores them. The audit is not retried: the
                # reason is a fact about the data, not a transient fault.
                session.commit()
                self.stats.failed += 1
                logger.warning("audit %s failed: %s", audit_id, failure)
                return True
            except Exception:
                session.rollback()
                self.stats.failed += 1
                logger.exception("audit %s raised an unexpected error", audit_id)
                raise

            session.commit()
            self.stats.completed += 1
            logger.info(
                "audit %s completed: %d verdicts, %d evidence records%s",
                audit_id,
                outcome.verdict_count,
                outcome.evidence_count,
                " (fixture models)" if outcome.uses_fixture_models else "",
            )
            return True

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        logger.info("worker started; one audit at a time")
        while not self._stopping:
            try:
                did_work = self.run_once()
            except Exception:  # noqa: BLE001 - logged above, loop survives
                did_work = False
            if not did_work:
                time.sleep(self.poll_interval)
        logger.info(
            "worker stopped: %d claimed, %d completed, %d failed",
            self.stats.claimed,
            self.stats.completed,
            self.stats.failed,
        )


def main() -> int:  # pragma: no cover - process entry point
    logging.basicConfig(level=get_settings().log_level)
    engine = engine_or_none()
    if engine is None:
        logger.error("no database configured; set POSTGRES_PASSWORD in .env")
        return 2

    from app.services.model_registry import build_pipeline_factory

    try:
        factory = build_pipeline_factory()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2

    def session_factory() -> Session:
        return Session(bind=engine)

    AuditWorker(
        session_factory, factory, poll_interval=get_settings().worker_poll_interval_seconds
    ).run_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
