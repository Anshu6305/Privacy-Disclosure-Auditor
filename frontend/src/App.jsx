/**
 * Application shell and routing.
 *
 * The seven approved screens: S1 search, S2 application detail, S3
 * processing, S4 results, S5 evidence detail (inside S4, since evidence is
 * only meaningful beside its verdict), S6 history, S7 comparison. There are
 * no login, registration or administration screens, by design.
 *
 * The scope statement sits above the routed content on every screen, not
 * only on the report: a reader can arrive at any URL directly, and the
 * project's scope is narrower than the interface would otherwise suggest.
 */

import { NavLink, Route, Routes } from 'react-router-dom';
import ScopeBanner from './components/ScopeBanner.jsx';
import ApplicationPage from './pages/ApplicationPage.jsx';
import AuditStatusPage from './pages/AuditStatusPage.jsx';
import ComparePage from './pages/ComparePage.jsx';
import HistoryPage from './pages/HistoryPage.jsx';
import ReportPage from './pages/ReportPage.jsx';
import SearchPage from './pages/SearchPage.jsx';
import SystemPage from './pages/SystemPage.jsx';

function NotFound() {
  return (
    <section className="card">
      <h2>No such page</h2>
      <p>
        <NavLink to="/">Back to search</NavLink>
      </p>
    </section>
  );
}

export default function App() {
  return (
    <div className="app">
      <header className="app__header">
        <div>
          <h1>Privacy Disclosure Consistency Auditor</h1>
          <p className="app__subtitle">
            Google Play Data Safety declarations compared against privacy policy text
          </p>
        </div>
        <nav className="app__nav">
          <NavLink to="/" end>
            Search
          </NavLink>
          <NavLink to="/system">System</NavLink>
        </nav>
      </header>

      <ScopeBanner />

      <main className="app__main">
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/applications/:packageName" element={<ApplicationPage />} />
          <Route path="/applications/:packageName/audits" element={<HistoryPage />} />
          <Route path="/applications/:packageName/compare" element={<ComparePage />} />
          <Route path="/audits/:auditId" element={<AuditStatusPage />} />
          <Route path="/audits/:auditId/report" element={<ReportPage />} />
          <Route path="/system" element={<SystemPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>

      <footer className="app__footer">
        B.Tech CSE Major Project &middot; KIIT &middot; Phase 4
      </footer>
    </div>
  );
}
