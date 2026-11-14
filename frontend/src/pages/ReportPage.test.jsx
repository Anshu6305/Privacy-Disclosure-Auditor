import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { mockApi, renderAt } from '../test/helpers.jsx';
import ReportPage from './ReportPage.jsx';

const SNAPSHOT = {
  snapshot_id: 7,
  collected_at: '2026-11-06T00:00:00Z',
  status: 'complete',
  source_url_listing: 'https://play.google.com/x',
  source_url_policy: 'https://example.invalid/privacy',
  has_declaration: true,
  has_policy: true,
  declares_no_data_collected: false,
};

const SCOPE_NOTE =
  'This audit compares a Google Play Data Safety declaration with the text of a ' +
  'privacy policy. It does not observe what the application actually does at ' +
  'runtime, and it is not a legal compliance finding.';

function report(overrides = {}) {
  return {
    audit_id: 42,
    package_name: 'com.example.one',
    status: 'completed',
    requested_at: '2026-11-06T00:00:00Z',
    completed_at: '2026-11-06T00:05:00Z',
    snapshot: SNAPSHOT,
    thresholds: { classifier: 0.5, alignment: 0.5, provisional: true },
    models: [
      {
        task: 'classification',
        variant: 'baseline',
        model_identifier: 'fixture:classification',
        version_label: 'fixture-v1',
      },
    ],
    taxonomy_mapping_version: 'map-v1',
    uses_fixture_models: true,
    scope_note: SCOPE_NOTE,
    verdicts: [
      {
        ds_category: 'Location',
        verdict: 'In-policy-not-declared',
        confidence: 0.92,
        declared: false,
        found_in_policy: true,
        abstention_involved: true,
        evidence: [],
      },
    ],
    ...overrides,
  };
}

function render(routes) {
  mockApi(routes);
  return renderAt(<ReportPage />, {
    path: '/audits/:auditId/report',
    route: '/audits/42/report',
  });
}

describe('F-24 report', () => {
  it('states the scope on the report itself', async () => {
    render({ '/api/audits/42/report': { body: report() } });
    expect(await screen.findByText(/not a legal compliance finding/)).toBeInTheDocument();
  });

  it('declares a fixture-backed report as one, and tags the stub model', async () => {
    // The whole point: a demonstration report and a real one are otherwise
    // indistinguishable, and the difference is a finding versus an example.
    render({ '/api/audits/42/report': { body: report() } });
    expect(await screen.findByText(/Produced with fixture models/)).toBeInTheDocument();
    expect(screen.getByText(/not model predictions/)).toBeInTheDocument();
    expect(screen.getByText('fixture')).toBeInTheDocument();
  });

  it('shows no fixture notice when every model is a real one', async () => {
    render({
      '/api/audits/42/report': {
        body: report({
          uses_fixture_models: false,
          models: [
            {
              task: 'classification',
              variant: 'baseline',
              model_identifier: 'tfidf-logreg-2026-11',
              version_label: 'm5-v1',
            },
          ],
        }),
      },
    });
    expect(await screen.findByText('tfidf-logreg-2026-11')).toBeInTheDocument();
    expect(screen.queryByText(/Produced with fixture models/)).not.toBeInTheDocument();
    expect(screen.queryByText('fixture')).not.toBeInTheDocument();
  });

  it('marks a verdict that involved an abstention', async () => {
    render({ '/api/audits/42/report': { body: report() } });
    expect(await screen.findByText('In-policy-not-declared')).toBeInTheDocument();
    expect(screen.getByText('abstention involved')).toBeInTheDocument();
  });

  it('records the thresholds the run actually used', async () => {
    render({ '/api/audits/42/report': { body: report() } });
    expect(await screen.findByText('classifier')).toBeInTheDocument();
    expect(screen.getByText('provisional')).toBeInTheDocument();
  });

  it('withholds a report for an unfinished audit instead of showing a partial one', async () => {
    render({
      '/api/audits/42/report': { status: 409, body: { detail: 'audit is still running' } },
    });
    expect(await screen.findByText(/has no report yet/)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('fetches evidence only when a category is expanded', async () => {
    const fetchMock = mockApi({
      '/api/audits/42/evidence/Location': {
        body: [
          {
            record_type: 'evidence',
            display_order: 1,
            quoted_text: 'We collect your precise location.',
            char_start: 10,
            char_end: 43,
            reason: null,
            segment_id: 3,
          },
        ],
      },
      '/api/audits/42/report': { body: report() },
    });
    renderAt(<ReportPage />, {
      path: '/audits/:auditId/report',
      route: '/audits/42/report',
    });

    const toggle = await screen.findByRole('button', { name: /show evidence/i });
    expect(fetchMock.mock.calls.some(([p]) => p.includes('/evidence/'))).toBe(false);

    await userEvent.click(toggle);
    const quote = await screen.findByText('We collect your precise location.');
    expect(quote.tagName).toBe('BLOCKQUOTE');
    expect(screen.getByText(/Characters 10–43/)).toBeInTheDocument();
  });
});

describe('F-25 evidence records', () => {
  it('shows the passage an inconclusive record abstained on', async () => {
    // F-22 stores the sub-threshold candidate passage with an inconclusive
    // record. The panel showed a quotation only for `evidence`, so an
    // Undetermined verdict displayed a reason with no passage and a reviewer
    // could not see what the system could not decide about.
    mockApi({
      '/api/audits/42/evidence/Location': {
        body: [
          {
            record_type: 'inconclusive',
            display_order: 1,
            quoted_text: 'We may collect location in some circumstances.',
            char_start: 12,
            char_end: 57,
            reason: 'This is an abstention, not a finding of inconsistency.',
            segment_id: 7,
          },
        ],
      },
      '/api/audits/42/report': {
        body: report({
          verdicts: [
            {
              ds_category: 'Location',
              verdict: 'Undetermined',
              confidence: 0.31,
              declared: true,
              found_in_policy: false,
              abstention_involved: true,
              evidence: [],
            },
          ],
        }),
      },
    });
    renderAt(<ReportPage />, {
      path: '/audits/:auditId/report',
      route: '/audits/42/report',
    });

    await userEvent.click(await screen.findByRole('button', { name: /show evidence/i }));

    const quote = await screen.findByText(
      'We may collect location in some circumstances.',
    );
    expect(quote.tagName).toBe('BLOCKQUOTE');
    expect(screen.getByText('Not decided')).toBeInTheDocument();
    expect(
      screen.getByText(/abstention, not a finding of inconsistency/),
    ).toBeInTheDocument();
  });

  it('renders an absence record without a quotation', async () => {
    // An absence record is a system statement that the policy says nothing.
    // Rendering it as a quote would attribute words to the policy that the
    // policy does not contain.
    mockApi({
      '/api/audits/42/evidence/Location': {
        body: [
          {
            record_type: 'absence',
            display_order: 1,
            quoted_text: null,
            char_start: null,
            char_end: null,
            reason: 'The policy does not mention this category.',
            segment_id: null,
          },
        ],
      },
      '/api/audits/42/report': {
        body: report({
          verdicts: [
            {
              ds_category: 'Location',
              verdict: 'Declared-not-in-policy',
              confidence: null,
              declared: true,
              found_in_policy: false,
              abstention_involved: false,
              evidence: [],
            },
          ],
        }),
      },
    });
    renderAt(<ReportPage />, {
      path: '/audits/:auditId/report',
      route: '/audits/42/report',
    });

    await userEvent.click(await screen.findByRole('button', { name: /show evidence/i }));
    const row = await screen.findByText('The policy does not mention this category.');
    expect(row).toBeInTheDocument();
    expect(screen.getByText(/Nothing found in the privacy policy/)).toBeInTheDocument();
    expect(document.querySelector('blockquote')).toBeNull();
  });

  it('explains that a Consistent verdict carries no evidence by design', async () => {
    mockApi({
      '/api/audits/42/evidence/Location': { body: [] },
      '/api/audits/42/report': {
        body: report({
          verdicts: [
            {
              ds_category: 'Location',
              verdict: 'Consistent',
              confidence: 0.9,
              declared: true,
              found_in_policy: true,
              abstention_involved: false,
              evidence: [],
            },
          ],
        }),
      },
    });
    renderAt(<ReportPage />, {
      path: '/audits/:auditId/report',
      route: '/audits/42/report',
    });

    await userEvent.click(await screen.findByRole('button', { name: /show evidence/i }));
    expect(await screen.findByText(/both sources agree, and an agreement is not quoted/))
      .toBeInTheDocument();
  });

  it('lists every category the report returned, not only the interesting ones', async () => {
    const categories = ['Location', 'Personal info', 'Contacts'];
    mockApi({
      '/api/audits/42/report': {
        body: report({
          verdicts: categories.map((ds_category) => ({
            ds_category,
            verdict: 'Consistent',
            confidence: null,
            declared: false,
            found_in_policy: false,
            abstention_involved: false,
            evidence: [],
          })),
        }),
      },
    });
    renderAt(<ReportPage />, {
      path: '/audits/:auditId/report',
      route: '/audits/42/report',
    });

    for (const category of categories) {
      expect(await screen.findByRole('rowheader', { name: category })).toBeInTheDocument();
    }
    expect(screen.getByText(/All 3 Data Safety categories are listed/)).toBeInTheDocument();
  });
});
