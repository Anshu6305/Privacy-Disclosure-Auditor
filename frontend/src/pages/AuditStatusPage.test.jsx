import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mockApi, renderAt } from '../test/helpers.jsx';
import AuditStatusPage from './AuditStatusPage.jsx';

function status(overrides = {}) {
  return {
    audit_id: 42,
    package_name: 'com.example.one',
    status: 'queued',
    requested_at: '2026-11-06T00:00:00Z',
    claimed_at: null,
    completed_at: null,
    failure_reason: null,
    ...overrides,
  };
}

function render(body) {
  mockApi({ '/api/audits/42': { body } });
  return renderAt(<AuditStatusPage />, { path: '/audits/:auditId', route: '/audits/42' });
}

describe('S3 audit status', () => {
  it('says the audit is waiting, and that one runs at a time', async () => {
    render(status());
    expect(await screen.findByText('queued')).toBeInTheDocument();
    expect(screen.getByText(/One audit runs at a time/)).toBeInTheDocument();
  });

  it('offers the report only once the audit completes', async () => {
    render(status({ status: 'completed', completed_at: '2026-11-06T00:05:00Z' }));
    expect(await screen.findByRole('link', { name: /view the report/i })).toBeInTheDocument();
  });

  it('does not offer a report for a queued audit', async () => {
    render(status());
    await screen.findByText('queued');
    expect(screen.queryByRole('link', { name: /view the report/i })).not.toBeInTheDocument();
  });

  it("shows the pipeline's own refusal sentence verbatim", async () => {
    // The refusal names what is missing. A generic "audit failed" would
    // leave a reader unable to tell a broken system from one correctly
    // declining to guess — here, an unconfigured F-15 mapping table.
    const reason =
      "taxonomy mapping version 'unauthored-v0' holds no rules (F-15). Without " +
      'them no policy practice can reach a Data Safety category, and every ' +
      'declared category would be reported as missing from the policy. Author ' +
      'the mapping rules before running an audit.';
    render(status({ status: 'failed', failure_reason: reason, completed_at: '2026-11-06T00:01:00Z' }));

    expect(await screen.findByText(reason)).toBeInTheDocument();
    expect(screen.getByText(/No report was produced, and here is why/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /view the report/i })).not.toBeInTheDocument();
  });
});
