# Milestone 4 — Privacy Policy Text Processing

Date: 2026-11-05
Task: T2. Functions F-08, F-09, F-10. Requirements FR-08, FR-09, FR-10.
Algorithm: ALG-1.

---

## 1. Processing architecture

```
  stored raw document
        │
        ▼
  F-05  load_policy_document        (M3A, reused unchanged)
        │  verifies SHA-256, returns PolicyDocument
        ▼
  F-08  extract_policy_text         analysis/text/extractor.py
        │  raw markup → cleaned plain text          ← CANONICAL TEXT
        ▼
  F-09  segment_policy_text         analysis/text/segmenter.py
        │  cleaned text → ordered segments with offsets INTO THAT TEXT
        ▼
  F-10  validate_analysability      analysis/text/validator.py
        │  segment + token counts vs configured minimums
        ▼
  analysable → M5/M6 classification        not analysable → audit stops
                                            with a recorded reason
```

`analysis/text/pipeline.py` wires the four together so the sequence exists in
one place and is tested as a whole. Nothing in T2 touches a database.

## 2. Files

**Created**

| File | Purpose |
|---|---|
| `analysis/text/models.py` | `ExtractionResult`, `PolicySegment`, `AnalysabilityThresholds`, `AnalysabilityResult` |
| `analysis/text/extractor.py` | F-08 |
| `analysis/text/segmenter.py` | F-09 |
| `analysis/text/validator.py` | F-10 |
| `analysis/text/pipeline.py` | T2 orchestration and cleaned-text storage |
| `tests/unit/test_text_extraction.py` | 24 tests |
| `tests/unit/test_text_segmentation.py` | 23 tests |
| `tests/unit/test_text_analysability.py` | 31 tests |
| `docs/M4_TEXT_PROCESSING_REPORT.md` | this report |

**Modified**

| File | Change |
|---|---|
| `backend/requirements.txt` | spaCy moved here from `requirements-ml.txt` |
| `backend/requirements-ml.txt` | spaCy removed, with a note saying where it went |
| `backend/app/config.py` | two provisional analysability thresholds |
| `.env.example` | the same two, labelled provisional |
| `pyproject.toml` | two named third-party deprecation filters |

**Not modified:** no M3A acquisition interface, no database model, no Alembic
migration, no API, no verdict engine.

## 3. Libraries

| Library | Use | Why |
|---|---|---|
| **spaCy 3.8.3** + `en_core_web_sm` 3.8.0 | Sentence boundaries (F-09) | The approved Phase 3 design specifies it. The statistical model is what keeps "e.g.", "Inc." and "U.S." from ending a sentence |
| **BeautifulSoup 4.12.3** | HTML parsing (F-08) | Already pinned in the project |
| **lxml 5.3.0**, **html5lib 1.1** | Parser backends | Already pinned. Tried in order; both tolerate malformed markup |

### One dependency correction

spaCy was in `backend/requirements-ml.txt`, the ~2 GB set, and has been moved
to `backend/requirements.txt`. F-09 needs it for the **baseline** pipeline —
text must be segmented before any classifier runs — so a baseline-only install
could not have segmented a policy. The 2 GB in the ML file is torch, not
spaCy, which is small on its own.

**The model is a separate download** and pip does not install it:

```bash
python -m spacy download en_core_web_sm
```

Verified working in this environment: `en-core-web-sm-3.8.0` installed
successfully.

## 4. F-08 — extraction and cleaning

Removes: `script`, `style`, `noscript`, `template`, `svg`, `canvas`, `iframe`,
`object`, `embed`, `form`, `button`, `input`, `select`, `textarea`, `nav`,
`header`, `footer`, `aside`, and HTML comments. A count of what was removed is
returned so the discarding can be audited.

Keeps everything else. **Nothing is removed for looking repetitive,
boilerplate or unimportant.** Privacy policies are repetitive by nature — "we
may collect" recurs a dozen times, definitions restate each other, the same
exception is qualified in three sections — and a cleaner judging content by
similarity would delete exactly the clauses the audit exists to find. A test
asserts that six identical sentences all survive.

Headings, definitions, legal qualifications, exceptions and list items are all
retained; each can carry a data practice, and a heading such as "Information
we share with third parties" is itself a statement about one.

**Block structure.** A paragraph break is inserted after every block-level
element, so a heading never runs into the prose beneath it and F-09 can group
by paragraph.

**Whitespace.** A single newline is collapsed to a space, because in HTML a
source newline renders as a space; one surviving into a quoted sentence would
be a line break the policy never had. Two newlines mark a paragraph and are
preserved. This was corrected during implementation after inspecting the
output.

**Unicode.** NFKC, with zero-width and soft-hyphen characters dropped, applied
before offsets are assigned so text and offsets agree. Accented text is
preserved; a test covers French policy text.

**Failure is explicit.** An empty document, markup with no readable text, and
an unsupported format each produce a failed result with a distinct reason
rather than an empty string that looks like a short policy. PDF is reported as
unimplemented, not garbled.

**The source is never modified.** A test asserts the input string is unchanged
after extraction, alongside the M3A test that the file on disk is untouched.

**Determinism.** The same document always produces the same cleaned text.
F-09's offsets index this output, so this is a correctness requirement, not a
nicety.

## 5. Offset preservation strategy

### What the offsets refer to

**Offsets index the cleaned plain text produced by F-08.** That is the
canonical coordinate base for the whole project.

This follows from the approved design rather than being chosen: Phase 3
defines F-09's input as "cleaned text" from F-08, so that is the only document
its offsets can count characters in. No offset in this project refers to raw
HTML, and nothing here changes what an offset means.

### Why not offsets into the raw HTML

They would need a character-level map maintained through tag stripping, entity
decoding, Unicode normalisation and whitespace collapsing — one entry per
character, rebuilt on every change to the cleaner. Phase 3 does not call for
one. §10.4 records that the segmented text is stored in the database so the
pipeline never depends on the raw files being present, which is the same
decision stated from the storage side.

### How the guarantee is kept

1. **Offsets are produced by slicing, never by reassembly.** Trimming moves
   the offsets rather than calling `strip()` on a copy.
2. **`PolicySegment` refuses to exist** unless `char_end - char_start` equals
   `len(text)`. A wrong offset cannot be constructed.
3. **The cleaned text is stored** at `data/corpus/processed/<source-sha256>.txt`,
   named after the raw document it came from, so a reader following an offset
   has the document to follow it in and F-25 has something to highlight.
4. **Tests verify by slicing.** Every offset test asserts
   `cleaned_text[s.char_start:s.char_end] == s.text` against the real string.
5. **Coverage is checked**: every non-whitespace character of the document
   belongs to exactly one segment, so nothing is lost or counted twice.
6. **`verify_segments` is itself tested against a deliberately broken offset**,
   so the checker is known to catch a fault rather than merely to pass.

## 6. F-09 — segmentation

1. Split on paragraph breaks, which F-08 writes as exactly two newlines.
2. A paragraph within the size limit becomes one segment, so a sentence keeps
   the context of its paragraph.
3. An over-long paragraph is split **at sentence boundaries only**.
4. A single sentence longer than the limit is kept whole: half a sentence is
   not quotable evidence.
5. Order is preserved; sequence numbers run consecutively from zero.

**Text is never altered.** Not lowercased, not re-wrapped, not normalised
further. Every segment's text is a verbatim slice of the cleaned document.

**Headings** become segments in their own right and also label the segments
that follow, as context for a human reader. A heading is never part of quoted
evidence.

**No fallback splitter.** If spaCy or its model is absent, F-09 raises with
installation instructions. A fallback would place sentence boundaries
differently, so the same policy would segment differently depending on what
happened to be installed and two team members would get different evidence
offsets for the same document. NFR-08 does not allow that.

### Provisional parameter

`DEFAULT_MAX_SEGMENT_CHARS = 1000`. **Provisional, not an approved
requirement.** Chosen so a segment stays within the 512-token input limit of
the encoder models under consideration for F-11, with room for sub-word
expansion. Configurable per call.

## 7. F-10 — analysability, and threshold configuration

Compares segment count and total token count against configured minimums, as
Phase 3 specifies. Token counts come from the same spaCy tokeniser that found
the sentences, so the number means one definite thing.

Rejects, each with its own reason: an empty segment list; segments with zero
tokens; below the segment minimum; below the token minimum; both. A rejection
names the actual numbers and the thresholds, and notes that such a document is
commonly an error page, a consent banner, or a page whose content loads from a
script.

A **successful** result also carries a reason, so the audit record states why
the document was accepted and not merely that it was.

### Thresholds are never defaulted silently

`validate_analysability` raises `ThresholdConfigurationError` when no
thresholds are given. The documented provisional values require
`allow_provisional=True`, passed explicitly. A configuration that is missing a
key, carries a non-integer, or sets a value below 1 is rejected — a threshold
of zero would accept an empty document, and a threshold nobody chose is not
the "configured minimum" Phase 3 requires.

### The provisional values

| Threshold | Value | Status |
|---|---|---|
| `min_segments` | 1 | **Provisional** |
| `min_tokens` | 50 | **Provisional** |

Phase 2 and Phase 3 require the comparison and name the two quantities but
**set no numbers**. These are the project's own proposal.

Reasoning: the shortest genuine policy in OPP-115 is `988_solarviews.com` at
703 characters in a single segment — short but real, and it was inspected
directly during Milestone 1. The thresholds sit below it so a real short
policy is still analysed, while an error page or a cookie banner is not. They
should be revisited once the operational corpus exists and the distribution of
real Android policy lengths is known.

Exposed as `MIN_POLICY_SEGMENTS` and `MIN_POLICY_TOKENS` in `.env.example` and
`Settings`, both labelled provisional in place.

## 8. Test results

```
$ pytest tests/unit/test_text_extraction.py      24 passed
$ pytest tests/unit/test_text_segmentation.py    23 passed
$ pytest tests/unit/test_text_analysability.py   31 passed

$ pytest tests
345 passed, 29 skipped in 1.18s

$ ruff check .
All checks passed!
```

**78 tests added. No test was skipped in M4.** The 29 skips are the PostgreSQL
integration suite, which skips without `TEST_DATABASE_URL` and is unrelated to
this milestone.

| Required coverage | Tests |
|---|---|
| **F-08** HTML extraction | 3 |
| Plain-text input | 1 |
| Malformed HTML | 2 |
| Script and navigation removal | 1 |
| Unicode | 3 |
| Legal definitions and exceptions | 2 |
| Empty documents | 3 |
| Unsupported formats and errors | 3 |
| **F-09** single sentence | 1 |
| Multiple paragraphs | 1 |
| Multiple sentences per paragraph | 1 |
| Long paragraphs requiring splitting | 2 |
| Headings and lists | 2 |
| Abbreviations and punctuation | 2 |
| Empty input | 2 |
| Correct offsets | 4 |
| No missing or duplicated sentences | 2 |
| **F-10** empty segments | 1 |
| Zero-token input | 1 |
| Minimum segment-count boundary | 2 |
| Minimum token-count boundary | 2 |
| Both thresholds satisfied | 2 |
| Both thresholds failed | 1 |
| Missing configuration | 3 |
| Invalid configuration | 7 |
| **T2 end to end** | 6 |

## 9. Sample run — controlled fixture, not a real application audit

`com.example.sampleapp` is invented. The policy text was written for the
fixture. This demonstrates the pipeline; it is not an audit of any application.

**Raw document (F-05):** 628 bytes, `text/html`, SHA-256
`410a3d40…13af0`, hash **verified** on load.

**Extracted (F-08):** succeeded, 495 characters, no elements removed — the
fixture has no scripts or navigation.

**Segmented (F-09):** 12 segments, every one slice-verified.

| seq | start | end | tokens | text |
|---|---|---|---|---|
| 0 | 0 | 25 | 4 | `Sample App Privacy Policy` |
| 1 | 27 | 41 | 2 | `Privacy Policy` |
| 2 | 43 | 71 | 6 | `Last updated 1 January 2026.` |
| 3 | 73 | 95 | 3 | `Information we collect` |
| 4 | 97 | 201 | 20 | `We collect your email address when you create an account, …` |
| 5 | 203 | 272 | 14 | `We collect your contact list in order to suggest people …` |

**Analysability (F-10):** analysable, 12 segments, 85 tokens, against
provisional minimums of 1 and 50.

> The document has 12 segment(s) and 85 token(s), meeting the minimums of 1
> and 50.

## 10. Traceability

| Requirement | Function | Code | Tests | Status |
|---|---|---|---|---|
| FR-08 | F-08 | `analysis/text/extractor.py` | `test_text_extraction.py` (24) | Implemented and verified |
| FR-09 | F-09 | `analysis/text/segmenter.py` | `test_text_segmentation.py` (23) | Implemented and verified |
| FR-10 | F-10 | `analysis/text/validator.py` | `test_text_analysability.py` (31) | Implemented and verified |
| T2 end to end | F-05→F-08→F-09→F-10 | `analysis/text/pipeline.py` | 6 tests | Implemented and verified |
| ALG-1 | F-08 + F-09 | both modules | the above | Implemented, O(n) single pass |
| NFR-08 reproducibility | — | deterministic extraction; pinned model; no fallback splitter | 2 determinism tests | Supported |

## 11. Known limitations

1. **No real policy has been processed.** Every document in the test suite is
   an invented fixture. The operational Android application corpus does not
   exist: 0 of the 300–500 target, 0 of the ~20 pilot. Real policies are far
   messier than these fixtures, and extraction will need adjustment once some
   exist.
2. **Thresholds are provisional**, chosen against OPP-115 website policies
   rather than Android application policies. They need revisiting once the
   corpus exists.
3. **The 1000-character segment limit is provisional** and tied to an encoder
   choice that has not been made.
4. **PDF policies are stored but not extracted.** The loader reports it
   clearly; extraction would need `pypdf`, already pinned.
5. **Script-rendered pages cannot be read.** This project does not execute
   JavaScript. Such a page is reported as unreadable, not analysed as empty.
6. **The `<title>` element survives extraction**, so a page title may appear
   as the first segment. Kept deliberately: removing it would be removing
   content, and the conservative rule is to keep anything that might be prose.
7. **Headings are segmented as their own units**, which produces several very
   short segments. Intended — a heading can carry a data practice — but it
   will affect classifier input and should be reviewed in M5.
8. **Boilerplate removal is structural only.** Cookie banners and consent
   text inside `<p>` elements are retained, because distinguishing them from
   policy prose reliably would need the classifier that has not been built.

## 12. Dependencies on other milestones

**Not blocked by M3B.** T2 reads from the filesystem through M3A's loader and
needs no database.

**Provides to M5 and M6:** `PolicySegment` with verified offsets is the input
to F-11 classification and F-12 span extraction. `PolicySegment.to_segment_ref`
converts to the verdict layer's `PolicySegmentRef`, so the offset invariant
holds across the boundary.

**Provides to M8:** segments map onto the approved `policy_segment` table —
`sequence_number` → `seq_no`, `char_start`/`char_end` → `start_offset`/
`end_offset`, `text` → `segment_text`. Persisting them is M8; the column
correspondence is noted here so no new mapping has to be invented then.

**Still pending elsewhere:** the D-1 decision, M3B persistence, the
operational corpus, and the class D findings in
`docs/PHASE4_DECISION_TABLE.md`. None of them blocks T2.
