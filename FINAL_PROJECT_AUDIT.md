# Final project audit

Record of the final organisation pass that turned the repository into a clean,
runnable software project. Dated 18 November 2026. Everything below was
executed and observed; nothing is projected.

---

## 1. What changed

The repository previously carried a nested `FINAL_FACULTY_SUBMISSION/` folder
that duplicated runtime assets and mixed academic reports into the codebase.
That folder is gone, the academic documents were handed over separately, and
the root now holds only what the software needs.

| Action | Detail |
|---|---|
| Removed | `FINAL_FACULTY_SUBMISSION/` (858 MB) — a duplicate copy of runtime assets plus Phase 1–3 reports and supplementary documents |
| Moved | 6 audit exports (5 `spotify_audit_*_report.json` + `spotify_policy.html`) from the root into `artifacts/audit_exports/`, with `git mv` so history follows |
| Moved | 15 PostgreSQL verification logs from the root into `artifacts/test_evidence/` |
| Deleted | Regenerable caches only: `__pycache__/`, `*.pyc`, `.DS_Store`, `.ruff_cache/`, `.pytest_cache/` |
| Deleted | 2.7 GB of unused alternative F-18 model formats — see §3 |
| Rewritten | Root `README.md`, now a technical guide rather than an academic report |
| Replaced | `FINAL_SUBMISSION_AUDIT.md` by this file |
| Updated | `.gitignore` — the stale submission-folder rules replaced by a documented `artifacts/` policy, and `.ruff_cache/` added |
| Updated | `docs/PHASE4_CLOSEOUT.md` — audit-export paths now point at `artifacts/audit_exports/` |

Project size fell from **6.0 GB to 2.5 GB**. Of what remains, 1.2 GB is the
local `.venv` and 835 MB is `ml/` (832 MB of it model checkpoints) — both
ignored by git, neither deletable without breaking the project.

No source file, migration, checkpoint, dataset, taxonomy mapping, test,
notebook, Docker file or dependency manifest was deleted. No directory was
renamed or re-cased. The database was not touched, no Docker volume was
removed and git history was not rewritten.

## 2. Preserved runtime assets

Every asset that was inside the removed submission folder was compared against
its canonical path by SHA-256 before anything was deleted:

```
identical to canonical : 27
hash differs           :  0
missing canonically    :  0
```

All 27 were byte-identical duplicates, so removing the folder removed copies,
not originals. The canonical assets, all present and verified loadable:

| Asset | Size | SHA-256 (first 16) |
|---|---|---|
| `ml/checkpoints/improved_classifier/model.safetensors` | 256 MB | `5c433a51938c83f8` |
| `ml/checkpoints/nli-mnli-v1/model.safetensors` | 314 MB | `9df3eb5d37118f95` |
| `ml/checkpoints/span-extractor-v1/model.safetensors` | 254 MB | `ec695acfc2d9072c` |
| `ml/checkpoints/classifier-baseline-v1/model.joblib` | 2.7 MB | `37ae7b3d21343398` |
| `analysis/mapping/taxonomy/mapping_v1.json` | 16 KB | `7f32294606044c9f` |
| `data/corpus/apps/com.spotify.music/record.json` | 12 KB | `5ba75341a322c376` |
| `data/corpus/raw/.../13089e7b…fa4ea8.html` | 196 KB | `13089e7b1972c6e4` |

The policy document's filename is its own SHA-256; the recomputed digest
matches it, so the stored policy is unaltered since collection.

Also retained deliberately: `backend/migrations/versions/` (all three
revisions, `0001_baseline_schema` frozen), `data/raw/` (339 MB, the OPP-115
corpus), `data/processed/` (18 MB, derived training files), `ml/runs/`
(metrics and the Colab training bundles), `notebooks/`, `.env` and
`.env.example`, and the three empty-but-required directories `data/policies/`
(the configured `POLICY_STORAGE_DIR` and a Docker volume mount),
`data/goldset/` and `data/taxonomy/`.

## 3. The 2.7 GB of F-18 duplicates

The aligner checkpoint shipped with four redundant weight formats alongside the
`model.safetensors` that the code actually loads: `onnx/`, `openvino/`,
`flax_model.msgpack` and `pytorch_model.bin`. Rather than assume they were
unused, they were quarantined and the system re-exercised against the
remainder:

* the aligner loaded as `ZeroShotAligner`;
* real inference produced correct outputs on all three NLI outcomes
  (entailment 0.1098 / neutral 0.8822 / contradiction 0.0080 on the neutral
  case; 0.9847 contradiction on the contradiction case);
* the full suite ran **818 passed, 78 skipped**;
* `test_f18_real_inference.py` and `test_f12_real_inference.py` ran
  **14 passed**, executed rather than skipped.

Only then were they deleted. Nothing was removed for being large alone.

## 4. Test results

Run on 18 November 2026 against the organised tree.

| Check | Command | Result |
|---|---|---|
| Backend suite | `pytest tests -p no:warnings` | **818 passed, 78 skipped, 0 failed** (7.04 s) |
| Python lint | `ruff check .` | **All checks passed** (ruff 0.8.4, the pinned version) |
| Frontend suite | `npm test` | **33 passed in 7 files** |
| Frontend lint | `npm run lint` | **clean**, exit 0 |
| Frontend build | `npm run build` | **succeeded** — 49 modules, 192.30 kB JS / 7.22 kB CSS |
| Alembic offline DDL | `alembic upgrade 0001:0003 --sql` | **exit 0**, 84 lines of real DDL emitted |
| Application import | `from app.main import app` | **ok** — 18 route objects registered |
| Checkpoint loading | all four registries | **ok** — `ImprovedPracticeClassifier`, `BaselinePracticeClassifier`, `SpanExtractor`, `ZeroShotAligner` |

**The 78 skips are skips, not passes.** Every one is a PostgreSQL integration
test that refuses to guess a database when `TEST_DATABASE_URL` is unset:

| Suite | Skipped |
|---|---|
| `tests/integration/test_postgresql_schema.py` | 32 |
| `tests/integration/test_application_search_postgresql.py` | 24 |
| `tests/integration/test_m3b_persistence_postgresql.py` | 16 |
| `tests/integration/test_m8_pipeline_postgresql.py` | 6 |
| **Total** | **78** |

No ML test was skipped — the real-inference suites executed against the actual
checkpoints.

### Not executed, and why

* **Live PostgreSQL integration tests.** PostgreSQL runs in Docker Desktop on
  the team Mac and is not reachable from an agent session; these must be run by
  the team with `./scripts/verify_migrations.sh` and the output reported. Prior
  runs are in `artifacts/test_evidence/`.
* **Backend and worker startup against the live database**, and the browser
  walkthrough of the Spotify audit, for the same reason. The commands in the
  README were each checked against the actual configuration they invoke
  (`vite.config.js` proxy target, the `/api` router prefixes, the compose
  service names, `request_audit.py`'s real flags) rather than written from
  memory.
* **Docker image build.** Not rebuilt in this pass; unchanged since it was last
  verified to start.

The backend suite was run with Python 3.10 in the verification environment, not
the project's Python 3.12. The project's own virtual environment and
`node_modules` are macOS builds and cannot execute there; the frontend checks
were therefore run against an `npm ci` install from the committed
`package-lock.json`, which is the same dependency set.

## 5. Git status

Branch `master`. Last commit before this pass: `fb9733b`.

```
M  .gitignore
M  docs/PHASE4_CLOSEOUT.md
D  FINAL_FACULTY_SUBMISSION/…                    (20 files)
R  spotify_audit_{2..6}_report.json  -> artifacts/audit_exports/…
R  spotify_policy.html               -> artifacts/audit_exports/…
```

No stashes. No untracked files outside the ignore rules. History was not
rewritten; the submission folder's files were removed with `git rm --cached`
first, so their history survives in the log.

`artifacts/audit_exports/` is committed — those reports are the evidence the
documentation cites. `artifacts/test_evidence/` is local only, covered by the
existing `*.log` rule, and `.gitignore` now says so in a comment.

## 6. Items for the team

Not defects, and not changed here because they fall outside the permitted edits
for this pass:

1. **`data/policies/raw/` is empty and untracked.** It is the configured
   `POLICY_STORAGE_DIR` and a Docker volume mount, but git does not carry empty
   directories, so a fresh clone will not have it. A `.gitkeep` would fix it.
   In practice the collected policy is read from `data/corpus/raw/policies/`,
   so nothing is broken today.
2. **`data/goldset/` and `data/taxonomy/` are empty** and referenced only in
   documentation. They are reserved, not dead, and were left in place.
3. **The Docker worker image omits the ML dependency set**, so a containerised
   worker can claim an audit but not complete it. This is deliberate, and the
   README says so.
