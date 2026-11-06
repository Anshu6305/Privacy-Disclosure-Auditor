/**
 * Loading, error and empty states, in one place.
 *
 * Every screen uses these rather than rolling its own, because the failure
 * mode they exist to prevent is uniform: a request fails, the screen renders
 * its empty layout, and the reader cannot tell "nothing found" from "nothing
 * loaded". `Loading` and `Failed` are therefore never silent.
 */

export function Loading({ what = 'data' }) {
  return (
    <p className="state state--loading" role="status" aria-busy="true">
      Loading {what}…
    </p>
  );
}

export function Failed({ error, what = 'data' }) {
  const status = error?.status;
  return (
    <div className="state state--error" role="alert">
      <strong>Could not load {what}.</strong>
      <p>{error?.message ?? 'The request failed.'}</p>
      {status === 0 ? (
        <p className="state__hint">
          The API did not respond. Check that the backend is running.
        </p>
      ) : null}
    </div>
  );
}

export function Empty({ children }) {
  return <p className="state state--empty">{children}</p>;
}

/**
 * Shown when the backend reports a capability it cannot currently provide —
 * an unconfigured taxonomy mapping table, say. Deliberately not styled as an
 * error: the system is working correctly and declining to produce a result it
 * cannot support. Showing a plausible-looking result instead is the one
 * outcome the project must never produce.
 */
export function Unavailable({ title, children }) {
  return (
    <div className="state state--unavailable" role="note">
      <strong>{title}</strong>
      {children}
    </div>
  );
}
