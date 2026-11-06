import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mockApi, renderAt } from '../test/helpers.jsx';
import SystemPage from './SystemPage.jsx';

const HEALTH = { body: { status: 'ok' } };
const DB_HEALTH = { body: { status: 'ok', detail: null } };

function render(versions, acquisition) {
  mockApi({
    '/api/health/database': DB_HEALTH,
    '/api/health': HEALTH,
    '/api/versions': { body: versions },
    '/api/acquisition/status': { body: acquisition },
  });
  return renderAt(<SystemPage />, { path: '/system', route: '/system' });
}

describe('System status', () => {
  it('says when no mapping version is active rather than leaving it blank', async () => {
    // The project's current state. A blank field would read as "fine".
    render(
      {
        schema_revision: '0003_collection_event',
        taxonomy_mapping_version: null,
        models: [],
        uses_fixture_models: false,
      },
      { live_retrieval_configured: false, corpus_application_count: 0, detail: 'No adapter.' },
    );
    expect(await screen.findByText('No active mapping version')).toBeInTheDocument();
    expect(screen.getByText(/No active model versions are registered/)).toBeInTheDocument();
    expect(screen.getByText(/An audit cannot run without a classifier/)).toBeInTheDocument();
  });

  it('reports a configured adapter as configuration, never as a successful fetch', async () => {
    render(
      {
        schema_revision: '0003_collection_event',
        taxonomy_mapping_version: 'map-v1',
        models: [
          {
            task: 'classification',
            variant: 'baseline',
            model_identifier: 'fixture:classification',
            version_label: 'fixture-v1',
          },
        ],
        uses_fixture_models: true,
      },
      {
        live_retrieval_configured: true,
        corpus_application_count: 12,
        detail: 'An adapter is present. That is not a successful fetch.',
      },
    );
    expect(await screen.findByText('An adapter is configured')).toBeInTheDocument();
    expect(screen.getByText(/That is not a successful fetch/)).toBeInTheDocument();
    expect(screen.getByText(/Produced with fixture models/)).toBeInTheDocument();
  });
});
