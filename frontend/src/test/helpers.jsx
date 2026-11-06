/**
 * Test helpers.
 *
 * `mockApi` stubs `fetch` with a routing table keyed by path. Every response
 * body in a test is written out in full and matches the Pydantic schema in
 * `backend/app/api/schemas/audit.py`. Nothing is auto-generated: a fixture
 * that drifts from the contract would let a test pass against a shape the API
 * never sends.
 *
 * An unmatched path throws rather than returning an empty body, so a test
 * that calls an endpoint nobody stubbed fails loudly instead of rendering an
 * empty screen that looks correct.
 */

import { render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';

export function mockApi(routes) {
  const fetchMock = vi.fn(async (path) => {
    const match = Object.keys(routes).find((key) => path === key || path.startsWith(key));
    if (!match) throw new Error(`no stub for ${path}`);
    const entry = routes[match];
    const { status = 200, body } = typeof entry === 'function' ? entry() : entry;
    return {
      ok: status >= 200 && status < 300,
      status,
      statusText: String(status),
      text: async () => JSON.stringify(body),
    };
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** Render a component at a route, with the router params it expects. */
export function renderAt(element, { path, route }) {
  return render(
    <MemoryRouter
      initialEntries={[route]}
      // Opting in early silences two v7 warnings that would otherwise fill
      // the test output; neither affects what these tests assert.
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path={path} element={element} />
        <Route path="*" element={<div>navigated away</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

export const SCOPE = {
  scope:
    'This tool compares stated disclosures. It does not observe application behaviour.',
};
