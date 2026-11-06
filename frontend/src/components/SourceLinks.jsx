/**
 * F-27 — where the two compared disclosures came from.
 *
 * Both source URLs and the policy document's SHA-256. The hash is shown, not
 * hidden behind a tooltip: it is what lets a reader establish that the text
 * quoted in a report is the text that was collected, and a report whose
 * sources cannot be checked is an assertion rather than a finding.
 */

import { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import { Empty, Failed, Loading } from './Async.jsx';

export default function SourceLinks({ packageName }) {
  const [sources, setSources] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setSources(null);
    setError(null);
    api
      .sourceLinks(packageName)
      .then((data) => !cancelled && setSources(data))
      .catch((err) => !cancelled && setError(err));
    return () => {
      cancelled = true;
    };
  }, [packageName]);

  if (error) return <Failed error={error} what="the source links" />;
  if (!sources) return <Loading what="the source links" />;

  return (
    <section className="card">
      <h2>Sources</h2>
      <dl className="pairs">
        <dt>Play Store listing</dt>
        <dd>
          {sources.source_url_listing ? (
            <a href={sources.source_url_listing} rel="noreferrer noopener" target="_blank">
              {sources.source_url_listing}
            </a>
          ) : (
            <Empty>Not recorded for this collection event.</Empty>
          )}
        </dd>
        <dt>Privacy policy</dt>
        <dd>
          {sources.source_url_policy ? (
            <a href={sources.source_url_policy} rel="noreferrer noopener" target="_blank">
              {sources.source_url_policy}
            </a>
          ) : (
            <Empty>Not recorded for this collection event.</Empty>
          )}
        </dd>
        <dt>Policy SHA-256</dt>
        <dd>
          {sources.policy_doc_sha256 ? (
            <code className="hash">{sources.policy_doc_sha256}</code>
          ) : (
            <Empty>No policy document was stored for this event.</Empty>
          )}
        </dd>
        <dt>Collected</dt>
        <dd>{new Date(sources.collected_at).toLocaleString()}</dd>
      </dl>
    </section>
  );
}
