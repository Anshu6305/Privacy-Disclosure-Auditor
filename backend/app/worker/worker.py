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
from datetime import datetime, timezone

from app.config import get_settings
from app.db.models import AuditRun
from app.db.session import engine_or_none
from app.services.audit_pipeline import (
    AuditFailedError,
    claim_next_audit,
)
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from analysis.vocabulary import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
)

logger = logging.getLogger("auditor.worker")


@dataclass
class WorkerStats:
    claimed: int = 0
    completed: int = 0
    failed: int = 0


class AuditWorker:
    """Claims one audit, runs it, commits, repeats.

    ``build_pipeline`` is injected: it receives a session and the audit id,
    and returns an :class:`AuditPipeline` bound to that audit's recorded
    model versions. Injecting it keeps the loop testable without models;
    taking the audit id is F-13, which binds one variant per audit at claim
    time and never switches it.
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
            try:
                # Inside the try: building the pipeline loads the models, and
                # a checkpoint that will not load must fail the audit rather
                # than stranding it.
                # F-13: bound to the version set this audit recorded when
                # it was requested, never re-resolved here. Passing the
                # audit id is what makes "never switch variants during an
                # audit" true rather than merely intended.
                pipeline = self._build_pipeline(session, audit_id)
                outcome = pipeline.run(audit_id)
            except AuditFailedError as failure:
                # The pipeline has already recorded status and reason on the
                # row; committing stores them. The audit is not retried: the
                # reason is a fact about the data, not a transient fault.
                session.commit()
                self.stats.failed += 1
                logger.warning("audit %s failed: %s", audit_id, failure)
                return True
            except Exception as unexpected:
                # Every exit from here must leave the audit in a terminal
                # state. The claim was committed before the work began, so a
                # rollback alone leaves the row `running` for ever - and
                # `claim_next_audit` returns nothing while any audit is
                # running, so a single unexpected error would wedge the whole
                # queue permanently rather than failing one audit.
                session.rollback()
                self._mark_failed(audit_id, unexpected)
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

    def _mark_failed(self, audit_id: int, error: BaseException) -> None:
        """Record a terminal failure on its own session.

        A fresh session because the one that raised has been rolled back and
        cannot be trusted to write. Best-effort: if even this fails the
        exception is logged and the original error still propagates, because
        losing the real cause behind a bookkeeping error would be worse than
        an audit left running.
        """
        reason = (
            f"the audit stopped with an unexpected {type(error).__name__}: "
            f"{str(error).splitlines()[0][:400]}"
        )
        try:
            with self._session_factory() as session:
                audit = session.get(AuditRun, audit_id)
                if audit is None or audit.status in (STATUS_COMPLETED, STATUS_FAILED):
                    return
                audit.status = STATUS_FAILED
                audit.failure_reason = reason
                audit.completed_at = datetime.now(timezone.utc)
                session.commit()
        except Exception:  # noqa: BLE001 - never mask the original failure
            logger.exception(
                "audit %s could not be marked failed; it may remain running",
                audit_id,
            )

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


def describe_target(database_url: str) -> str:
    """Host, port and database, with the credentials dropped.

    The worker used to log only "worker started", so a worker connected to a
    different database from the one holding the audits sat quietly polling an
    empty queue. Naming the target makes that visible in the first line of
    output. The password is never rendered: only the three fields below are
    read off the parsed URL (NFR - credentials are not printed).
    """
    url = make_url(database_url)
    return f"{url.host}:{url.port}/{url.database}"


def count_by_status(session: Session, status: str) -> int:
    """How many audits this database holds in one status."""
    return session.execute(
        select(func.count()).select_from(AuditRun).where(AuditRun.status == status)
    ).scalar_one()


def count_queued(session: Session) -> int:
    """How many audits this database has waiting, for the startup line."""
    return count_by_status(session, STATUS_QUEUED)


def main() -> int:  # pragma: no cover - process entry point
    logging.basicConfig(level=get_settings().log_level)
    engine = engine_or_none()
    if engine is None:
        logger.error("no database configured; set POSTGRES_PASSWORD in .env")
        return 2

    from app.services.model_registry import build_bound_pipeline_factory

    try:
        factory = build_bound_pipeline_factory()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2

    def session_factory() -> Session:
        return Session(bind=engine)

    settings = get_settings()
    target = describe_target(settings.database_url)
    try:
        with session_factory() as session:
            queued = count_queued(session)
            running = count_by_status(session, STATUS_RUNNING)
    except SQLAlchemyError as exc:
        # The compose file already documents exit 2 for an unavailable
        # database; this is where that becomes true rather than a stack trace
        # from the first poll.
        logger.error("cannot reach the database at %s: %s", target, exc)
        return 2

    logger.info("polling %s; %s audit(s) queued there", target, queued)
    if queued == 0:
        logger.warning(
            "nothing queued in %s. If an audit is waiting elsewhere, this "
            "worker is pointed at the wrong database: set POSTGRES_DB to the "
            "one the audit was created in.",
            target,
        )
    if running:
        # DD-2 allows one active audit, so a stuck `running` row stops the
        # queue moving and looks exactly like an idle worker from the log.
        logger.warning(
            "%s audit(s) already `running` in %s. Under DD-2 nothing else is "
            "claimed until they finish; scripts/release_stuck_audits.py "
            "releases a row left behind by a crash.",
            running,
            target,
        )

    AuditWorker(
        session_factory, factory, poll_interval=get_settings().worker_poll_interval_seconds
    ).run_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
