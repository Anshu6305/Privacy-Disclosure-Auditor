/**
 * F-24, S4 and S5 — the report (E5) with per-category evidence (E6).
 *
 * The order of this page is deliberate. Provenance comes before verdicts:
 * whether the models were fixtures, which mapping version ran, what
 * thresholds applied. A reader who scrolls to the table first and the
 * provenance never has read a list of findings without knowing what produced
 * them, and the fixture case makes that difference total.
 *
 * All fourteen Data Safety categories are listed, including those neither
 * source mentions. Omitting them would leave a reader unable to tell "nothing
 * to report here" from "not examined".
 */

import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client.js';
import { Failed, Loading, Unavailable } from '../components/Async.jsx';
import EvidencePanel from '../components/EvidencePanel.jsx';
import FixtureNotice from '../components/FixtureNotice.jsx';
import VerdictBadge from '../components/VerdictBadge.jsx';

function Thresholds({ thresholds }) {
  const entries = Object.entries(thresholds ?? {});
  if (entries.length === 0) return <p>No thresholds were recorded for this run.</p>;
  return (
    <ul className="thresholds">
      {entries.map(([key, value]) => (
        <li key={key}>
          <span className="thresholds__key">{key}</span>
          <span className="thresholds__value">{String(value)}</span>
        </li>
      ))}
    </ul>
  );
}

export default function ReportPage() {
  const { auditId } = useParams();
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(() => new Set());

  useEffect(() => {
    let cancelled = false;
    api
      .auditReport(auditId)
      .then((data) => !cancelled && setReport(data))
      .catch((err) => !cancelled && setError(err));
    return () => {
      cancelled = true;
    };
  }, [auditId]);

  function toggle(category) {
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  }

  // 409: the audit has not finished. A partial report would present an
  // unfinished analysis as a result, so the API withholds it.
  if (error && error.status === 409) {
    return (
      <Unavailable title="This audit has no report yet.">
        <p>A report is assembled only once an audit completes.</p>
        <p>
          <Link to={`/audits/${auditId}`}>Check the audit status</Link>
        </p>
      </Unavailable>
    );
  }

  if (error) return <Failed error={error} what={`the report for audit ${auditId}`} />;
  if (!report) return <Loading what="the report" />;

  return (
    <>
      <section className="card">
        <h2>Report — {report.package_name}</h2>
        <p className="report__scope">{report.scope_note}</p>
        <FixtureNotice usesFixtureModels={report.uses_fixture_models} />
      </section>

      <section className="card">
        <h2>How this report was produced</h2>
        <dl className="pairs">
          <dt>Audit</dt>
          <dd>
            {report.audit_id} ·{' '}
            <Link to={`/audits/${report.audit_id}`}>status</Link>
          </dd>
          <dt>Completed</dt>
          <dd>
            {report.completed_at
              ? new Date(report.completed_at).toLocaleString()
              : 'Not recorded'}
          </dd>
          <dt>Taxonomy mapping</dt>
          <dd>{report.taxonomy_mapping_version ?? 'None recorded'}</dd>
          <dt>Thresholds</dt>
          <dd><Thresholds thresholds={report.thresholds} /></dd>
        </dl>

        <h3>Models</h3>
        {report.models.length === 0 ? (
          <p>No model versions were recorded against this audit.</p>
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
              {report.models.map((model) => (
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
        <h2>Verdicts</h2>
        <p className="state__hint">
          All {report.verdicts.length} Data Safety categories are listed,
          including those neither source mentions.
        </p>
        <table className="table table--verdicts">
          <thead>
            <tr>
              <th scope="col">Category</th>
              <th scope="col">Verdict</th>
              <th scope="col">Declared</th>
              <th scope="col">In policy</th>
              <th scope="col">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {report.verdicts.map((verdict) => {
              const isOpen = open.has(verdict.ds_category);
              return [
                <tr key={verdict.ds_category}>
                  <th scope="row">{verdict.ds_category}</th>
                  <td>
                    <VerdictBadge
                      verdict={verdict.verdict}
                      abstentionInvolved={verdict.abstention_involved}
                    />
                  </td>
                  <td>{verdict.declared ? 'Yes' : 'No'}</td>
                  <td>{verdict.found_in_policy ? 'Yes' : 'No'}</td>
                  <td>
                    <button
                      type="button"
                      className="link-button"
                      aria-expanded={isOpen}
                      onClick={() => toggle(verdict.ds_category)}
                    >
                      {isOpen ? 'Hide' : 'Show'} evidence
                    </button>
                  </td>
                </tr>,
                isOpen ? (
                  <tr key={`${verdict.ds_category}-evidence`} className="row--evidence">
                    <td colSpan={5}>
                      <EvidencePanel
                        auditId={report.audit_id}
                        dsCategory={verdict.ds_category}
                        verdict={verdict.verdict}
                      />
                    </td>
                  </tr>
                ) : null,
              ];
            })}
          </tbody>
        </table>
      </section>
    </>
  );
}
