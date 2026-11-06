/**
 * Team-facing provenance and acquisition state (E10, E11).
 *
 * Not one of the seven approved user screens. It exists so a demonstration
 * can answer "what is actually loaded right now" without anybody reading the
 * database, and it reports unavailability as plainly as availability.
 */

import { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import { Failed, Loading, Unavailable } from '../components/Async.jsx';
import FixtureNotice from '../components/FixtureNotice.jsx';
import ServiceStatus from '../components/ServiceStatus.jsx';

export default function SystemPage() {
  const [versions, setVersions] = useState(null);
  const [acquisition, setAcquisition] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.versions(), api.acquisitionStatus()])
      .then(([v, a]) => {
        if (cancelled) return;
        setVersions(v);
        setAcquisition(a);
      })
      .catch((err) => !cancelled && setError(err));
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <Failed error={error} what="the system status" />;
  if (!versions || !acquisition) return <Loading what="the system status" />;

  return (
    <>
      <ServiceStatus />

      <section className="card">
        <h2>Versions</h2>
        <FixtureNotice usesFixtureModels={versions.uses_fixture_models} />
        <dl className="pairs">
          <dt>Schema revision</dt>
          <dd>{versions.schema_revision ?? 'Not recorded'}</dd>
          <dt>Taxonomy mapping</dt>
          <dd>
            {versions.taxonomy_mapping_version ?? (
              <span className="muted">No active mapping version</span>
            )}
          </dd>
        </dl>

        <h3>Active models</h3>
        {versions.models.length === 0 ? (
          <Unavailable title="No active model versions are registered.">
            <p>An audit cannot run without a classifier and an aligner.</p>
          </Unavailable>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Task</th>
                <th scope="col">Variant</th>
                <th scope="col">Identifier</th>
                <th scope="col">Version</th>
              </tr>
            </thead>
            <tbody>
              {versions.models.map((model) => (
                <tr key={`${model.task}-${model.model_identifier}`}>
                  <td>{model.task}</td>
                  <td>{model.variant}</td>
                  <td>
                    <code>{model.model_identifier}</code>
                    {model.model_identifier.startsWith('fixture:') ? (
                      <span className="tag tag--fixture">fixture</span>
                    ) : null}
                  </td>
                  <td>{model.version_label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Acquisition</h2>
        <dl className="pairs">
          <dt>Live retrieval</dt>
          <dd>
            {acquisition.live_retrieval_configured
              ? 'An adapter is configured'
              : 'Not configured'}
          </dd>
          <dt>Applications in the corpus</dt>
          <dd>{acquisition.corpus_application_count}</dd>
        </dl>
        <p className="state__hint">{acquisition.detail}</p>
      </section>
    </>
  );
}
