/**
 * Single place where the frontend talks to the API.
 *
 * Every path is relative, so the same code works against the Vite dev proxy
 * and against FastAPI serving the built app from the same origin.
 *
 * Errors are surfaced, never swallowed into a fallback value. A screen that
 * silently shows empty results when a request failed would misrepresent the
 * state of the system, which matters more here than in most applications.
 */

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
  } catch (cause) {
    throw new ApiError(`Could not reach the API at ${path}.`, 0, null);
  }

  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!response.ok) {
    const detail = body && body.detail ? body.detail : response.statusText;
    throw new ApiError(`${path} failed: ${detail}`, response.status, body);
  }

  return body;
}

export const api = {
  health: () => request('/api/health'),
  databaseHealth: () => request('/api/health/database'),
  scope: () => request('/api/meta/scope'),
};
