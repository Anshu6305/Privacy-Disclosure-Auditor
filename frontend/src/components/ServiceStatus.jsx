/**
 * Milestone 1 verification view.
 *
 * Shows the real result of the health endpoints. It reports "unconfigured" or
 * "unavailable" as plainly as it reports "ok", because a status panel that
 * only ever shows green is worse than no status panel.
 *
 * This component is scaffolding for the development stack, not one of the
 * seven approved screens (S1 to S7).
 */

import { useEffect, useState } from 'react';
import { api } from '../api/client.js';

const LABELS = {
  ok: 'reachable',
  unconfigured: 'not configured',
  unavailable: 'not reachable',
};

export default function ServiceStatus() {
  const [apiState, setApiState] = useState('checking');
  const [dbState, setDbState] = useState('checking');
  const [dbDetail, setDbDetail] = useState(null);

  useEffect(() => {
    api
      .health()
      .then((data) => setApiState(data.status))
      .catch(() => setApiState('unavailable'));

    api
      .databaseHealth()
      .then((data) => {
        setDbState(data.status);
        setDbDetail(data.detail ?? null);
      })
      .catch(() => setDbState('unavailable'));
  }, []);

  return (
    <section className="status">
      <h2>Service status</h2>
      <dl>
        <dt>API</dt>
        <dd data-state={apiState}>{LABELS[apiState] ?? apiState}</dd>
        <dt>Database</dt>
        <dd data-state={dbState}>
          {LABELS[dbState] ?? dbState}
          {dbDetail ? <span className="status__detail"> — {dbDetail}</span> : null}
        </dd>
      </dl>
    </section>
  );
}
