import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { mockApi, renderAt } from '../test/helpers.jsx';
import SearchPage from './SearchPage.jsx';

const MATCHES = [
  { package_name: 'com.example.one', app_name: 'Example One', developer_name: 'Example Labs' },
];

function render() {
  return renderAt(<SearchPage />, { path: '/', route: '/' });
}

describe('S1 search', () => {
  it('lists the applications the API returned, and only those', async () => {
    mockApi({ '/api/applications?q=example': { body: MATCHES } });
    render();
    await userEvent.type(screen.getByLabelText(/application name/i), 'example');
    await userEvent.click(screen.getByRole('button', { name: /search/i }));

    expect(await screen.findByText('Example One')).toBeInTheDocument();
    expect(screen.getByText('com.example.one')).toBeInTheDocument();
  });

  it('does not call the API for a one-character query', async () => {
    const fetchMock = mockApi({});
    render();
    await userEvent.type(screen.getByLabelText(/application name/i), 'e');
    await userEvent.click(screen.getByRole('button', { name: /search/i }));

    expect(await screen.findByText(/at least 2 characters/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('explains that no match means the corpus does not hold it', async () => {
    mockApi({ '/api/applications?q=zzzz': { body: [] } });
    render();
    await userEvent.type(screen.getByLabelText(/application name/i), 'zzzz');
    await userEvent.click(screen.getByRole('button', { name: /search/i }));

    expect(await screen.findByText(/No application matches/)).toBeInTheDocument();
    expect(screen.getByText(/already collected into the corpus/i)).toBeInTheDocument();
  });

  it('shows a failed search as a failure, never as an empty result', async () => {
    // The failure this guards: a reader cannot distinguish "nothing found"
    // from "nothing loaded" if the screen renders its empty state on error.
    mockApi({ '/api/applications?q=example': { status: 500, body: { detail: 'boom' } } });
    render();
    await userEvent.type(screen.getByLabelText(/application name/i), 'example');
    await userEvent.click(screen.getByRole('button', { name: /search/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i);
    await waitFor(() =>
      expect(screen.queryByText(/No application matches/)).not.toBeInTheDocument(),
    );
  });
});
