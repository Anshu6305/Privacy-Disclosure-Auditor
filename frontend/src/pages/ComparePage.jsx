/**
 * S7 — comparing two audits of one application (E8).
 *
 * Unchanged categories are shown alongside changed ones, behind a toggle. A
 * list of only the changes cannot distinguish "these two audits agree
 * everywhere else" from "the rest was never compared".
 */

import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api/client.js';
import { Failed, Loading, Unavailable } from '../components/Async.jsx';

export default function ComparePage() {
  const { packageName } = useParams();
  const [params] = useSearchParams();
  const earlier = params.get('earlier');
  const later = params.get('later');

  const [comparison, setComparison] = useState(null);
  const [error, setError] = useState(null);
  const [showUnchanged, setShowUnchanged] = useState(false);

  useEffect(() => {
    if (!earlier || !later) return undefined;
    let cancelled = false;
    setComparison(null);
    setError(null);
    api
      .compareAudits(earlier, later)
      .then((data) => !cancelled && setComparison(data))
      .catch((err) => !cancelled && setError(err));
    return () => {
      cancelled = true;
    };
  }, [earlier, later]);

  if (!earlier || !later) {
    return (
      <Unavailable title="Two audits are needed for a comparison.">
        <p>
          <Link to={`/applications/${encodeURIComponent(packageName)}/audits`}>
            Choose two from the audit history
          </Link>
        </p>
      </Unavailable>
    );
  }

  if (error) return <Failed error={error} what="the comparison" />;
  if (!comparison) return <Loading what="the comparison" />;

  const rows = showUnchanged
    ? comparison.changes
    : comparison.changes.filter((change) => change.changed);

  return (
    <section className="card">
      <h2>Comparison — {comparison.package_name}</h2>
      <p>
        Audit <Link to={`/audits/${comparison.earlier_audit_id}`}>
          {comparison.earlier_audit_id}
        </Link>{' '}
        compared with audit{' '}
        <Link to={`/audits/${comparison.later_audit_id}`}>
          {comparison.later_audit_id}
        </Link>
        . <strong>{comparison.changed_count}</strong> of{' '}
        {comparison.changes.length} categories changed.
      </p>

      <p className="actions">
        <label>
          <input
            type="checkbox"
            checked={showUnchanged}
            onChange={(event) => setShowUnchanged(event.target.checked)}
          />{' '}
          Show unchanged categories
        </label>
      </p>

      {rows.length === 0 ? (
        <p>
          No category changed between these two audits. All{' '}
          {comparison.changes.length} were compared.
        </p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Category</th>
              <th scope="col">Audit {comparison.earlier_audit_id}</th>
              <th scope="col">Audit {comparison.later_audit_id}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((change) => (
              <tr key={change.ds_category} data-changed={change.changed}>
                <th scope="row">{change.ds_category}</th>
                <td>{change.earlier_verdict ?? <span className="muted">no verdict</span>}</td>
                <td>{change.later_verdict ?? <span className="muted">no verdict</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
