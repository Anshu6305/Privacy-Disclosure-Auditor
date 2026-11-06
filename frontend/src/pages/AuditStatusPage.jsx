/**
 * S3 — processing and failure (E4).
 *
 * Polls while the audit is queued or running, and stops as soon as it is not.
 *
 * A failed audit is the important case. The pipeline refuses to produce a
 * report it cannot support — an unanalysable policy, an unavailable model, an
 * unconfigured taxonomy mapping table — and stores the reason. That sentence
 * is shown verbatim and prominently, because the alternative, a generic
 * "audit failed", would leave the reader unable to tell a broken system from
 * a system correctly declining to guess.
 */

import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client.js';
import { Failed, Loading, Unavailable } from '../components/Async.jsx';

const POLL_MS = 2000;
const IN_PROGRESS = new Set(['queued', 'running']);

const EXPLAIN = {
  queued: 'Waiting for the worker. One audit runs at a time.',
  running: 'The worker is comparing the two disclosures.',
  completed: 'The audit finished.',
  failed: 'The audit stopped without producing a report.',
};

export default function AuditStatusPage() {
  const { auditId } = useParams();
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const timer = useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const data = await api.auditStatus(auditId);
        if (cancelled) return;
        setStatus(data);
        if (IN_PROGRESS.has(data.status)) {
          timer.current = setTimeout(poll, POLL_MS);
        }
      } catch (err) {
        if (!cancelled) setError(err);
      }
    }

    poll();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [auditId]);

  if (error) return <Failed error={error} what={`audit ${auditId}`} />;
  if (!status) return <Loading what="the audit" />;

  return (
    <section className="card">
      <h2>Audit {status.audit_id}</h2>
      <dl className="pairs">
        <dt>Application</dt>
        <dd>
          <Link to={`/applications/${encodeURIComponent(status.package_name)}`}>
            {status.package_name}
          </Link>
        </dd>
        <dt>Status</dt>
        <dd>
          <span className="audit-status" data-status={status.status}>
            {status.status}
          </span>
        </dd>
        <dt>Requested</dt>
        <dd>{new Date(status.requested_at).toLocaleString()}</dd>
        {status.completed_at ? (
          <>
            <dt>Finished</dt>
            <dd>{new Date(status.completed_at).toLocaleString()}</dd>
          </>
        ) : null}
      </dl>

      <p>{EXPLAIN[status.status] ?? ''}</p>

      {IN_PROGRESS.has(status.status) ? (
        <p className="state state--loading" role="status" aria-busy="true">
          Checking every {POLL_MS / 1000} seconds…
        </p>
      ) : null}

      {status.status === 'failed' && status.failure_reason ? (
        <Unavailable title="No report was produced, and here is why:">
          <p className="failure-reason">{status.failure_reason}</p>
          <p className="state__hint">
            The pipeline stops rather than publishing verdicts it cannot
            support. Nothing on this audit should be read as a finding.
          </p>
        </Unavailable>
      ) : null}

      {status.status === 'completed' ? (
        <p className="actions">
          <Link className="button-link" to={`/audits/${status.audit_id}/report`}>
            View the report
          </Link>
        </p>
      ) : null}
    </section>
  );
}
