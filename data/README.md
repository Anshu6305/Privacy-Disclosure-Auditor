# Data directory

Nothing in this directory is committed to the repository (see the root
`.gitignore`). Every team member obtains these files locally. This is a
licensing requirement, not a convenience choice: OPP-115 is released for
research, teaching and scholarship use and is not ours to redistribute,
and the privacy policies and Play Store records are third-party content.

Expected layout:

```
data/
  raw/
    opp115/                 OPP-115 corpus, extracted exactly as downloaded
    app350/                 APP-350, only if its licence terms permit our use
    policyie/               PolicyIE, only if its licence terms permit our use
    pi_extract/             PI-Extract, only if its licence terms permit our use
  corpus/
    declarations/           Data Safety declarations collected from the Play Store
    index.csv               package name, app name, collection timestamp, source URL
  policies/
    raw/<sha256>.html       privacy policy documents as retrieved, never edited
    raw/<sha256>.pdf
  goldset/
    annotations/            per-annotator gold labels, four labels only
    adjudicated/            agreed gold set used by F-31
  taxonomy/
    mapping_v1.json         OPP-115 category to Data Safety category mapping (F-15)
```

## OPP-115

Place the extracted corpus directly inside `data/raw/opp115/` so that the
corpus's own top-level folders (for example `annotations/`,
`sanitized_policies/`, `consolidation/`, `documentation/`) sit immediately
inside it. Do not rename or reorganise anything inside the download — the
loader reads the original structure, and keeping it unmodified is what lets
us state honestly which release we used.

After placing it, run the verification script (added in Milestone 1):

```
python ml/data/verify_opp115.py
```

It reports the document count, the annotation count, the category
distribution and a checksum manifest. The manifest is committed; the data
is not. That gives us a reproducibility record without redistributing the
corpus.

## Database and raw documents

Policy documents live on the filesystem under `policies/raw/`, named by the
SHA-256 of their bytes, with the path and hash recorded in the
`disclosure_snapshot` table. The database stores no document bodies. This
follows Phase 3 Section 10 and keeps the database small enough to dump.

## Rules

- Never commit anything from this directory.
- Never edit a retrieved policy document. Evidence must be verbatim.
- Record provenance for everything collected: source URL, timestamp,
  retrieval method, content hash (F-07).
