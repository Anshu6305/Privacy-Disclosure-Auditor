import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { mockApi, renderAt } from '../test/helpers.jsx';
import ComparePage from './ComparePage.jsx';

const COMPARISON = {
  package_name: 'com.example.one',
  earlier_audit_id: 8,
  later_audit_id: 9,
  changed_count: 1,
  changes: [
    {
      ds_category: 'Location',
      earlier_verdict: 'Consistent',
      later_verdict: 'Declared-not-in-policy',
      changed: true,
    },
    {
      ds_category: 'Contacts',
      earlier_verdict: 'Consistent',
      later_verdict: 'Consistent',
      changed: false,
    },
  ],
};

function render(route, routes) {
  mockApi(routes);
  return renderAt(<ComparePage />, { path: '/applications/:packageName/compare', route });
}

const ROUTE = '/applications/com.example.one/compare?earlier=8&later=9';

describe('S7 comparison', () => {
  it('shows what changed, and how many of how many were compared', async () => {
    render(ROUTE, { '/api/audits/8/compare/9': { body: COMPARISON } });
    expect(await screen.findByRole('rowheader', { name: 'Location' })).toBeInTheDocument();
    expect(screen.getByText('Declared-not-in-policy')).toBeInTheDocument();
    expect(screen.getByText(/of 2 categories changed/)).toBeInTheDocument();
  });

  it('hides unchanged categories by default but can show them', async () => {
    // Showing only changes cannot distinguish "these agree everywhere else"
    // from "the rest was never compared", so the count is always stated and
    // the full list is one click away.
    render(ROUTE, { '/api/audits/8/compare/9': { body: COMPARISON } });
    await screen.findByRole('rowheader', { name: 'Location' });
    expect(screen.queryByRole('rowheader', { name: 'Contacts' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByLabelText(/show unchanged/i));
    expect(await screen.findByRole('rowheader', { name: 'Contacts' })).toBeInTheDocument();
  });

  it('asks for two audits rather than comparing nothing', async () => {
    render('/applications/com.example.one/compare', {});
    expect(await screen.findByText(/Two audits are needed/)).toBeInTheDocument();
  });

  it("surfaces the API's refusal to compare audits of different applications", async () => {
    render(ROUTE, {
      '/api/audits/8/compare/9': {
        status: 400,
        body: { detail: 'audits 8 and 9 belong to different applications' },
      },
    });
    expect(await screen.findByRole('alert')).toHaveTextContent(/different applications/);
  });
});
