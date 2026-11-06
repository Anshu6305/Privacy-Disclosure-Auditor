/**
 * S6 — audit history, and the entry point to a comparison (E7).
 *
 * Two completed audits must be selected before a comparison can be run: a
 * comparison of one audit with itself, or with an audit that produced no
 * verdicts, would show an empty change list that reads like "nothing
 * changed".
 */

import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client.js';
import { Empty, Failed, Loading } from '../components/Async.jsx';

export default function HistoryPage() {
  const { packageName } = useParams();
  const navigate = useNavigate();
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState([]);

  useEffect(() => {
    let cancelled = false;
    api
      .auditHistory(packageName)
      .then((data) => !cancelled && setEntries(data))
      .catch((err) => !cancelled && setError(err));
    return () => {
      cancelled = true;
    };
  }, [packageName]);

  function toggle(auditId) {
    setSelected((current) =>
      current.includes(auditId)
        ? current.filter((id) => id !== auditId)
        : [...current, auditId].slice(-2),
    );
  }

  function compare() {
    const [a, b] = [...selected].sort((x, y) => x - y);
    navigate(
      `/applications/${encodeURIComponent(packageName)}/compare?earlier=${a}&later=${b}`,
    );
  }

  if (error) return <Failed error={error} what="the audit history" />;
  if (!entries) return <Loading what="the audit history" />;

  return (
    <section className="card">
      <h2>Audit history — {packageName}</h2>

      {entries.length === 0 ? (
        <Empty>No audit has been run for this application yet.</Empty>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Compare</th>
                <th scope="col">Audit</th>
                <th scope="col">Status</th>
                <th scope="col">Requested</th>
                <th scope="col">Verdicts</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => {
                const completed = entry.status === 'completed';
                return (
                  <tr key={entry.audit_id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Select audit ${entry.audit_id} for comparison`}
                        disabled={!completed}
                        checked={selected.includes(entry.audit_id)}
                        onChange={() => toggle(entry.audit_id)}
                      />
                    </td>
                    <th scope="row">
                      <Link to={`/audits/${entry.audit_id}`}>{entry.audit_id}</Link>
                    </th>
                    <td>
                      <span className="audit-status" data-status={entry.status}>
                        {entry.status}
                      </span>
                    </td>
                    <td>{new Date(entry.requested_at).toLocaleString()}</td>
                    <td>
                      {Object.keys(entry.verdict_counts).length === 0 ? (
                        <span className="muted">none</span>
                      ) : (
                        <ul className="counts">
                          {Object.entries(entry.verdict_counts).map(([verdict, count]) => (
                            <li key={verdict}>
                              {verdict}: {count}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <p className="actions">
            <button type="button" onClick={compare} disabled={selected.length !== 2}>
              Compare the two selected audits
            </button>
            <span className="state__hint">
              Select two completed audits. {selected.length} selected.
            </span>
          </p>
        </>
      )}
    </section>
  );
}
