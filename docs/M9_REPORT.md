# M9 — Frontend Integration

**Date:** 2026-11-06 · **Owner:** R6 · **Status:** implemented and tested.

All seven approved screens built against the E1–E11 endpoints M8 delivered.
No endpoint was invented and no backend contract changed; the only backend
file touched in this milestone is none.

## 1. Screens

| Screen | Route | Endpoints |
| --- | --- | --- |
| S1 search | `/` | E1 |
| S2 application detail | `/applications/:packageName` | E2, E9, E3 |
| S3 processing | `/audits/:auditId` | E4 |
| S4 results | `/audits/:auditId/report` | E5 |
| S5 evidence detail | inside S4, per category | E6 |
| S6 history | `/applications/:packageName/audits` | E7 |
| S7 comparison | `/applications/:packageName/compare` | E8 |
| System (team-facing, not an approved user screen) | `/system` | E10, E11 |

S5 sits inside S4 rather than at its own URL: evidence is interpretable only
beside the verdict it supports.

F-24 is `pages/ReportPage.jsx`, F-25 `components/EvidencePanel.jsx`, F-26
`components/ScopeBanner.jsx` (now on every screen), F-27
`components/SourceLinks.jsx`.

## 2. Where the interface declines

The backend's refusals are the project's main safeguard, and an interface
that smoothed them over would undo them. Each is carried through and tested:

* **Fixture models are declared on the report**, not only in the provenance
  table. A demonstration report and a real one are otherwise
  indistinguishable to a reader.
* **A failed audit shows `failure_reason` verbatim** — including the F-15
  "holds no rules" message, which is the failure this project will actually
  hit today.
* **`absence` records carry no quotation.** A test asserts no `blockquote`
  is rendered for one.
* **A Consistent verdict's empty evidence panel explains itself** (F-23).
* **Loading, error and empty are three distinct states.** A failed search
  shows an alert, never the no-match message.
* **Null `declares_no_data_collected` renders as "never retrieved"**, not as
  an absent declaration.
* **All fourteen categories appear on a report**, and the comparison states
  how many of how many were compared.

## 3. Tests and checks

| Check | Result |
| --- | --- |
| Vitest (7 files) | **32 passed, 0 failed, 0 skipped** |
| `vite build` | succeeds — 49 modules, 192 kB JS (61 kB gzipped) |
| `npm run lint` | clean |
| Backend `pytest tests` | **625 passed, 78 skipped** (unchanged — no backend file was modified) |
| PostgreSQL integration | **78 passed, 0 skips at head** (C-72, verified before M9 began) |

The 78 backend skips are the PostgreSQL and model-dependent suites that do
not run without `TEST_DATABASE_URL`; they are not passes, and they are the
same set as before M9.

Every response body in the frontend tests is written out in full against the
Pydantic schemas in `backend/app/api/schemas/audit.py`. An unstubbed path
throws rather than returning an empty body, so a screen that calls an
endpoint nobody stubbed fails loudly.

## 4. Files

**New** — `frontend/src/pages/`: SearchPage, ApplicationPage,
AuditStatusPage, ReportPage, HistoryPage, ComparePage and SystemPage, each
with a `.test.jsx` beside it. `frontend/src/components/`: Async,
EvidencePanel, FixtureNotice, SourceLinks, VerdictBadge.
`frontend/src/test/`: setup.js, helpers.jsx. `frontend/.eslintrc.cjs`.

**Changed** — `frontend/src/App.jsx` (routing), `src/main.jsx`
(BrowserRouter), `src/api/client.js` (E1–E11), `src/styles.css`,
`vite.config.js` (Vitest), `package.json` (test scripts, dev dependencies).

No backend, schema, migration or ML file was touched.

## 5. Limitations

* **No browser-level end-to-end test.** Component tests mock `fetch`, which
  is the right boundary for them, but the dev proxy, CORS and the built app
  served by FastAPI are exercised only by running the stack.
* **No screen has been seen against real audit data**, because no real audit
  can run yet: the F-15 mapping rules are unauthored and the M5 checkpoint is
  not present in every environment. Every screen has been exercised against
  the exact response shapes the API declares.
* **No accessibility audit** beyond semantic markup, labelled controls and
  not relying on colour alone.
* **The system page is team-facing** and is not one of the approved screens.

## 6. Next

**M10 — end-to-end demonstration and evaluation.** Two pieces of project
work gate a real audit and neither is blocked by anything external:

1. **Author the F-15 taxonomy mapping rules.** Until they exist the pipeline
   correctly refuses every audit, so no screen can show a real verdict.
2. **Rebuild the M5 baseline checkpoint** and register it as the active
   classification model.

With both in place, an audit can run with a real classifier end to end and
the interface can be demonstrated on genuine output. F-18 remains zero-shot
at best: its fine-tuning pairs and the gold set still do not exist, and that
is reported, not filled in.
