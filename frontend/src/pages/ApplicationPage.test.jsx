import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { mockApi, renderAt } from '../test/helpers.jsx';
import ApplicationPage from './ApplicationPage.jsx';

const DETAIL = {
  package_name: 'com.example.one',
  app_name: 'Example One',
  developer_name: 'Example Labs',
  store_category: null,
  play_store_url: null,
  first_seen_at: '2026-11-06T00:00:00Z',
  latest_snapshot: {
    snapshot_id: 7,
    collected_at: '2026-11-06T00:00:00Z',
    status: 'complete',
    source_url_listing: 'https://play.google.com/store/apps/details?id=com.example.one',
    source_url_policy: 'https://example.invalid/privacy',
    has_declaration: true,
    has_policy: true,
    declares_no_data_collected: false,
  },
};

const SOURCES = {
  package_name: 'com.example.one',
  snapshot_id: 7,
  collected_at: '2026-11-06T00:00:00Z',
  source_url_listing: 'https://play.google.com/store/apps/details?id=com.example.one',
  source_url_policy: 'https://example.invalid/privacy',
  policy_doc_sha256: 'a'.repeat(64),
};

function render(routes) {
  mockApi(routes);
  return renderAt(<ApplicationPage />, {
    path: '/applications/:packageName',
    route: '/applications/com.example.one',
  });
}

describe('S2 application detail', () => {
  it('shows the collection event and F-27 source links', async () => {
    render({
      '/api/applications/com.example.one/sources': { body: SOURCES },
      '/api/applications/com.example.one': { body: DETAIL },
    });
    expect(await screen.findByText('Example One')).toBeInTheDocument();
    expect(await screen.findByText('a'.repeat(64))).toBeInTheDocument();
    expect(screen.getByText(/Both sources collected/)).toBeInTheDocument();
  });

  it('distinguishes an unread Data Safety section from a "no data" declaration', async () => {
    // Three-state on purpose: null means never read. Collapsing it into
    // "declares nothing collected" would turn a retrieval failure into an
    // explicit negative declaration by the developer.
    render({
      '/api/applications/com.example.one/sources': { body: SOURCES },
      '/api/applications/com.example.one': {
        body: {
          ...DETAIL,
          latest_snapshot: { ...DETAIL.latest_snapshot, declares_no_data_collected: null },
        },
      },
    });
    expect(await screen.findByText(/Not read — the Data Safety section was never retrieved/))
      .toBeInTheDocument();
  });

  it('reports an unknown package as F-03 does, without claiming a fetch would succeed', async () => {
    render({
      '/api/applications/com.example.one': {
        status: 404,
        body: {
          detail: {
            package_name: 'com.example.one',
            present_in_corpus: false,
            live_retrieval_configured: true,
            can_request_audit: false,
            reason: 'This package is not in the corpus.',
            suggested_action: 'Ask the team to collect it.',
          },
        },
      },
    });
    expect(await screen.findByRole('heading', { name: /is not in the corpus/ })).toBeInTheDocument();
    expect(screen.getByText(/That is not a successful fetch/)).toBeInTheDocument();
    expect(screen.getByText(/an audit needs a collected disclosure/)).toBeInTheDocument();
  });

  it("shows the API's own refusal sentence when an audit cannot start", async () => {
    render({
      '/api/applications/com.example.one/sources': { body: SOURCES },
      '/api/applications/com.example.one': { body: DETAIL },
      '/api/audits': {
        status: 409,
        body: {
          detail: {
            package_name: 'com.example.one',
            reason: 'policy_missing',
            detail: 'The collection event holds no policy document.',
            snapshot_status: 'declaration_only',
          },
        },
      },
    });
    await userEvent.click(await screen.findByRole('button', { name: /request an audit/i }));
    expect(await screen.findByText('The collection event holds no policy document.'))
      .toBeInTheDocument();
    expect(screen.getByText('declaration_only')).toBeInTheDocument();
  });
});
