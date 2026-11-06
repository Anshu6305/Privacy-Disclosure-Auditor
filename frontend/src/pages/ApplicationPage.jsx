/**
 * S2 — application detail, sources and audit request (E2, E9, E3).
 *
 * Two refusals reach the reader here unchanged:
 *
 *   404  the package is not in the corpus. The API's F-03 report says whether
 *        live retrieval is even configured and whether an audit can be
 *        requested; both are shown, because "we could fetch it" and "we did
 *        fetch it" are different facts and the second is never claimed.
 *   409  the application is held but its collection event cannot support a
 *        report. The API's own sentence is shown rather than a generic
 *        failure, since it names the specific thing that is missing.
 */

import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client.js';
import { Failed, Loading, Unavailable } from '../components/Async.jsx';
import SourceLinks from '../components/SourceLinks.jsx';

const SNAPSHOT_STATUS = {
  complete: 'Both sources collected',
  declaration_only: 'Data Safety declaration only — no privacy policy',
  policy_only: 'Privacy policy only — no Data Safety declaration',
  declaration_absent: 'Listing reached, but it has no Data Safety section',
  fetch_failed: 'Collection failed',
  parse_failed: 'Collected, but could not be parsed',
};

function declaresNoData(value) {
  if (value === null || value === undefined) {
    return 'Not read — the Data Safety section was never retrieved';
  }
  return value ? 'Declares it collects no data' : 'Does not declare "no data collected"';
}

export default function ApplicationPage() {
  const { packageName } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [requesting, setRequesting] = useState(false);
  const [refusal, setRefusal] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setError(null);
    setRefusal(null);
    api
      .applicationDetail(packageName)
      .then((data) => !cancelled && setDetail(data))
      .catch((err) => !cancelled && setError(err));
    return () => {
      cancelled = true;
    };
  }, [packageName]);

  async function onRequestAudit() {
    setRequesting(true);
    setRefusal(null);
    try {
      const accepted = await api.requestAudit(packageName);
      navigate(`/audits/${accepted.audit_id}`);
    } catch (err) {
      // The API's refusal body names what is missing; keep its words.
      setRefusal(err.body?.detail ?? { detail: err.message });
    } finally {
      setRequesting(false);
    }
  }

  // F-03: the package is not held. This is an answer, not a failure.
  if (error && error.status === 404 && error.body?.detail?.present_in_corpus === false) {
    const report = error.body.detail;
    return (
      <section className="card">
        <h2>{report.package_name} is not in the corpus</h2>
        <p>{report.reason}</p>
        <p>{report.suggested_action}</p>
        <dl className="pairs">
          <dt>Live retrieval</dt>
          <dd>
            {report.live_retrieval_configured
              ? 'An adapter is configured, so a fetch could be attempted. That is not a successful fetch.'
              : 'Not configured'}
          </dd>
          <dt>Audit can be requested</dt>
          <dd>{report.can_request_audit ? 'Yes' : 'No — an audit needs a collected disclosure'}</dd>
        </dl>
        <p>
          <Link to="/">Back to search</Link>
        </p>
      </section>
    );
  }

  if (error) return <Failed error={error} what="this application" />;
  if (!detail) return <Loading what="the application" />;

  const snapshot = detail.latest_snapshot;

  return (
    <>
      <section className="card">
        <h2>{detail.app_name}</h2>
        <dl className="pairs">
          <dt>Package</dt>
          <dd><code>{detail.package_name}</code></dd>
          <dt>Developer</dt>
          <dd>{detail.developer_name ?? 'Not recorded'}</dd>
          <dt>Store category</dt>
          <dd>{detail.store_category ?? 'Not recorded'}</dd>
          <dt>First seen</dt>
          <dd>{new Date(detail.first_seen_at).toLocaleString()}</dd>
        </dl>
      </section>

      <section className="card">
        <h2>Latest collection event</h2>
        {snapshot ? (
          <dl className="pairs">
            <dt>Status</dt>
            <dd>{SNAPSHOT_STATUS[snapshot.status] ?? snapshot.status}</dd>
            <dt>Collected</dt>
            <dd>{new Date(snapshot.collected_at).toLocaleString()}</dd>
            <dt>Data Safety declaration</dt>
            <dd>{snapshot.has_declaration ? 'Present' : 'Not collected'}</dd>
            <dt>Privacy policy</dt>
            <dd>{snapshot.has_policy ? 'Stored' : 'Not collected'}</dd>
            <dt>“No data collected”</dt>
            <dd>{declaresNoData(snapshot.declares_no_data_collected)}</dd>
          </dl>
        ) : (
          <Unavailable title="No collection event has been recorded.">
            <p>An audit compares two collected disclosures; there is nothing to compare yet.</p>
          </Unavailable>
        )}
      </section>

      <SourceLinks packageName={detail.package_name} />

      <section className="card">
        <h2>Audit</h2>
        <p className="actions">
          <button type="button" onClick={onRequestAudit} disabled={requesting}>
            {requesting ? 'Requesting…' : 'Request an audit'}
          </button>
          <Link to={`/applications/${encodeURIComponent(detail.package_name)}/audits`}>
            Audit history
          </Link>
        </p>
        {refusal ? (
          <Unavailable title="This audit was not started.">
            <p>{refusal.detail ?? refusal.reason}</p>
            {refusal.snapshot_status ? (
              <p className="state__hint">
                Collection event status: <code>{refusal.snapshot_status}</code>
              </p>
            ) : null}
          </Unavailable>
        ) : null}
      </section>
    </>
  );
}
