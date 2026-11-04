/**
 * Application shell.
 *
 * Routes for the seven approved screens (S1 search, S2 application detail,
 * S3 processing, S4 results, S5 evidence detail, S6 history, S7 comparison)
 * are added as those screens are implemented in Milestone 9. There are no
 * login, registration or administration screens, by design.
 */

import ScopeBanner from './components/ScopeBanner.jsx';
import ServiceStatus from './components/ServiceStatus.jsx';

export default function App() {
  return (
    <div className="app">
      <header className="app__header">
        <h1>Privacy Disclosure Consistency Auditor</h1>
        <p className="app__subtitle">
          Google Play Data Safety declarations compared against privacy policy text
        </p>
      </header>

      <ScopeBanner />

      <main className="app__main">
        <ServiceStatus />
        <section className="placeholder">
          <h2>Not yet implemented</h2>
          <p>
            The seven screens are built in Milestone 9. This shell exists so the
            development stack can be verified end to end before any feature
            depends on it.
          </p>
        </section>
      </main>

      <footer className="app__footer">
        B.Tech CSE Major Project &middot; KIIT &middot; Phase 4
      </footer>
    </div>
  );
}
