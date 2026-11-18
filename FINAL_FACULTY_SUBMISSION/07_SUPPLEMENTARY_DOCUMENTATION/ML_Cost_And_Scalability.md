# ML cost and scalability

Supplementary to the approved Phase 1 and Phase 3 reports. It answers the
faculty requirement for "ML token-level cost estimation and scalability".
**The approved reports are not modified.**

Prepared 18 November 2026. Measured values are marked **[measured]** and
assumptions **[assumed]**.

---

## 1. There is no token billing, and why that matters

The faculty requirement assumes the common case: an application that calls a
hosted generative model and is billed per token. **This project does not do
that, and the distinction is the first thing to state.**

Phase 1 constraint C-02 and Phase 2 restrict the system to **encoder-scale
models only**; pretraining is out of scope and large generative models are
excluded. Every model here is an encoder that runs locally:

| Component | Model | Parameters | Disk |
|---|---|---:|---:|
| F-11 baseline (M5) | TF-IDF + one-vs-rest logistic regression | n/a (sparse linear) | **2.6 MB** [measured] |
| F-11 improved | `distilbert-base-uncased`, fine-tuned | 66,961,162 [measured] | **255.4 MB** [measured] |
| F-12 span extractor | DistilBERT token classification, 55 BIO labels | ~66 M | **253.3 MB** [measured] |
| F-18 aligner | `cross-encoder/nli-distilroberta-base`, zero-shot | ~82 M | **313.3 MB** [measured] |

**There is no paid API, no API key, no per-token charge and no vendor
dependency at inference time.** The marginal monetary cost of running one more
audit is therefore **₹0** — it is electricity and wall-clock time on hardware
the team already owns. Reporting a token price here would be inventing a
charge that does not exist.

What *is* worth measuring is **computational cost**: tokens processed, forward
passes, time and memory. Those are below.

## 2. Token volume, measured

Measured on the real pilot policy (`com.spotify.music`, SHA-256
`13089e7b…4ea8`) with the project's own tokenizer:

| Quantity | Value |
|---|---:|
| Raw policy HTML | 196,868 bytes [measured] |
| Cleaned policy text | 43,244 characters [measured] |
| WordPiece tokens in the whole policy | **8,176** [measured] |
| Segments produced | 629 [measured] |
| Mean tokens per segment | ≈ 13 (8,176 / 629) |

Each segment is padded to `max_sequence_length = 256` for the classifier, so
the *billed-equivalent* token count is not what the model actually processes.
The model processes 629 × 256 = **161,024 token positions** for
classification, most of them padding. That inefficiency is a deliberate
trade: fixed-width padding keeps the served probabilities identical to the
evaluated ones (C-90).

## 3. Compute per audit, measured

| Stage | Forward passes | Input width |
|---|---:|---|
| F-11 classification | 629 [measured] | 256 tokens, padded |
| F-12 span extraction | 629 [measured] | up to 512 tokens |
| F-18 alignment | 611 [measured] | premise + hypothesis pairs |
| **Total** | **1,869 encoder forward passes** | |

**Observed wall-clock:** a full pipeline run over this policy completed in
roughly **two minutes on CPU** [measured, agent VM, aarch64, no GPU], producing
629 segments, 3,386 practices, 611 judgements, 14 verdicts. This is an
observation from one run on one machine, **not a benchmark** and not a
measurement against NFR-02's target, which remains unverified.

**Memory:** design decision DD-2 keeps one audit active at a time precisely so
that one model set is resident. The three encoders total about 0.82 GB of
weights; with activations and the Python runtime this fits the 8 GB machine
Phase 1 assumed. F-34's sequential loading — one model per stage, released
before the next — would reduce the resident set further and **is not
implemented**; all three are held for the run.

## 4. Scalability

### Within one audit

Cost is linear in policy length. A policy twice as long produces roughly twice
the segments and twice the forward passes. Nothing in the pipeline is
quadratic: alignment runs over (candidate practice × declared claim) pairs that
survive the taxonomy mapping and the confidence floor, which is why 3,386
practices reduced to 611 judgements rather than to a product of thousands.

### Across a corpus

| Corpus | Audits | Encoder forward passes | CPU time at the observed rate |
|---|---:|---:|---|
| Current actual | 1 | 1,869 | ≈ 2 minutes |
| Phase 3 lower bound | 300 | ≈ 561,000 | ≈ 10 hours |
| Phase 3 upper bound | 500 | ≈ 935,000 | ≈ 17 hours |
| NFR-19 ceiling | 1,000 | ≈ 1,869,000 | ≈ 33 hours |

**[assumed]** the pilot policy is of representative length and the per-audit
cost is constant. Policy length varies widely in practice, so these are
order-of-magnitude figures.

Thirty-three hours of single-threaded CPU for the full NFR-19 ceiling is
tolerable for an offline corpus build and is the reason Phase 3 chose an
asynchronous worker over synchronous request handling: the user is never
waiting on it. A GPU would reduce it by roughly an order of magnitude, and the
two fine-tunes already used a free Colab T4 for exactly this reason.

**The scaling limit is not compute.** It is **corpus collection and
annotation**: one application has been collected against a design expectation
of 300–500, and the gold set of approximately 100 annotated applications does
not exist. Those are human-effort bounds, not machine ones, and no amount of
hardware shortens them.

### Training cost, as incurred

| Run | Hardware | Cost |
|---|---|---|
| M5 baseline | Local CPU | ₹0 |
| F-11 improved, 3 epochs | Colab T4, free tier [measured: losses 0.3331, 0.1823, 0.1170] | ₹0 |
| F-12 span extractor, 4 epochs | Colab T4, free tier | ₹0 |
| F-18 aligner | **Not trained** — zero-shot under approved decision D-01 Option A | ₹0 |

Total model training expenditure: **₹0**, consistent with the Phase 1 budget
of ₹8,000–₹10,000, which allotted nothing to paid compute.
