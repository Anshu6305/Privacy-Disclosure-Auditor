import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { mockApi, renderAt } from '../test/helpers.jsx';
import HistoryPage from './HistoryPage.jsx';

const ENTRIES = [
  {
    audit_id: 9,
    status: 'completed',
    requested_at: '2026-11-06T00:00:00Z',
    completed_at: '2026-11-06T00:05:00Z',
    snapshot_id: 7,
    verdict_counts: { Consistent: 13, 'Declared-not-in-policy': 1 },
  },
  {
    audit_id: 8,
    status: 'failed',
    requested_at: '2026-11-05T00:00:00Z',
    completed_at: '2026-11-05T00:01:00Z',
    snapshot_id: 7,
    verdict_counts: {},
  },
];

function render(body) {
  mockApi({ '/api/applications/com.example.one/audits': { body } });
  return renderAt(<HistoryPage />, {
    path: '/applications/:packageName/audits',
    route: '/applications/com.example.one/audits',
  });
}

describe('S6 audit history', () => {
  it('lists each audit with the verdict counts the API returned', async () => {
    render(ENTRIES);
    expect(await screen.findByText('Consistent: 13')).toBeInTheDocument();
    expect(screen.getByText('Declared-not-in-policy: 1')).toBeInTheDocument();
  });

  it('says plainly when no audit has run', async () => {
    render([]);
    expect(await screen.findByText(/No audit has been run/)).toBeInTheDocument();
  });

  it('cannot select a failed audit for comparison', async () => {
    // A failed audit produced no verdicts. Comparing it would render an empty
    // change list that reads as "nothing changed".
    render(ENTRIES);
    const checkboxes = await screen.findAllByRole('checkbox');
    expect(checkboxes[0]).toBeEnabled();
    expect(checkboxes[1]).toBeDisabled();
  });

  it('enables comparison only once two audits are selected', async () => {
    render([
      ENTRIES[0],
      { ...ENTRIES[1], audit_id: 7, status: 'completed', verdict_counts: { Consistent: 14 } },
    ]);
    const button = await screen.findByRole('button', { name: /compare the two/i });
    expect(button).toBeDisabled();

    const checkboxes = screen.getAllByRole('checkbox');
    await userEvent.click(checkboxes[0]);
    expect(button).toBeDisabled();
    await userEvent.click(checkboxes[1]);
    expect(button).toBeEnabled();
  });
});
