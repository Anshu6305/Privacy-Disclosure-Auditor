/**
 * S1 — application search (E1, with F-03 for a package that is not held).
 *
 * Search is prefix-only and needs at least two characters (C-54, C-55), so
 * the screen says both rather than letting a short or mid-word query look
 * like "no such application".
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client.js';
import { Empty, Failed, Loading } from '../components/Async.jsx';

const MIN_QUERY = 2;

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [submitted, setSubmitted] = useState(null);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event) {
    event.preventDefault();
    const trimmed = query.trim();
    setSubmitted(trimmed);
    setError(null);
    setResults(null);
    if (trimmed.length < MIN_QUERY) return;
    setBusy(true);
    try {
      setResults(await api.searchApplications(trimmed));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="card">
        <h2>Find an application</h2>
        <form className="search" onSubmit={onSubmit}>
          <label className="search__label" htmlFor="q">
            Application name or package identifier
          </label>
          <div className="search__row">
            <input
              id="q"
              name="q"
              type="search"
              autoComplete="off"
              placeholder="e.g. com.example.app"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <button type="submit" disabled={busy}>
              {busy ? 'Searching…' : 'Search'}
            </button>
          </div>
          <p className="search__hint">
            Matches the start of a name or package identifier. Minimum two
            characters.
          </p>
        </form>
      </section>

      {submitted !== null && submitted.length < MIN_QUERY ? (
        <Empty>Enter at least {MIN_QUERY} characters to search.</Empty>
      ) : null}

      {busy ? <Loading what="search results" /> : null}
      {error ? <Failed error={error} what="search results" /> : null}

      {results && results.length === 0 ? (
        <section className="card">
          <h2>No application matches “{submitted}”</h2>
          <p>
            Only applications already collected into the corpus can be audited.
            Search matches the <em>start</em> of a name or package identifier,
            so a word from the middle of a name will not match.
          </p>
        </section>
      ) : null}

      {results && results.length > 0 ? (
        <section className="card">
          <h2>
            {results.length} application{results.length === 1 ? '' : 's'}
          </h2>
          <ul className="results">
            {results.map((app) => (
              <li key={app.package_name}>
                <Link to={`/applications/${encodeURIComponent(app.package_name)}`}>
                  {app.app_name}
                </Link>
                <span className="results__package">{app.package_name}</span>
                {app.developer_name ? (
                  <span className="results__developer">{app.developer_name}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
