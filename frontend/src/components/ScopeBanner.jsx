/**
 * F-26 — scope statement.
 *
 * The wording is fetched from the API rather than written here, so there is
 * exactly one copy of it in the system and the interface cannot drift from
 * what the API documents. If the statement cannot be loaded, the banner says
 * so instead of rendering nothing: a report shown without its limits stated
 * is the one failure mode this component exists to prevent.
 */

import { useEffect, useState } from 'react';
import { api } from '../api/client.js';

export default function ScopeBanner() {
  const [scope, setScope] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .scope()
      .then((data) => {
        if (!cancelled) setScope(data.scope);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (failed) {
    return (
      <aside className="scope scope--error" role="note">
        The scope statement could not be loaded. Findings must not be read as
        legal or compliance conclusions.
      </aside>
    );
  }

  if (!scope) {
    return <aside className="scope scope--loading" role="note" aria-busy="true" />;
  }

  return (
    <aside className="scope" role="note">
      <strong>What this tool does: </strong>
      {scope}
    </aside>
  );
}
