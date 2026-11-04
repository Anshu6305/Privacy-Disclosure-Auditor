# Annotation Guidelines — Cross-Source Semantic Alignment (F-18)

Guideline version: v1.0-draft
Date: 2026-11-04
Status: draft for team and faculty review. **Labelling does not begin until
Milestone 6.** No F-18 code exists yet.

This document exists because of safeguard 1 on the Option A decision: the
labels must be defined before anyone starts labelling. A guide written
afterwards describes what annotators happened to do, which is not the same
thing.

---

## 1. What is being labelled

One **pair**:

- **Claim** — a single normalised Data Safety declaration, expressed as a short
  sentence. Example: *"This app collects your email address."*
- **Statement** — one segment of privacy policy text, verbatim.

The annotator decides what the statement does to the claim. Three labels.

## 2. The three labels

### SUPPORTS

The statement asserts the claim, or something that necessarily includes it.

- *"We collect your name, email address and phone number."* supports *"collects
  your email address."*
- *"We collect your contact details."* supports *"collects your email
  address"* — a broader term that necessarily covers the narrower one.

### CONTRADICTS

The statement asserts something that cannot be true at the same time as the
claim.

- *"We never collect location data."* contradicts *"collects precise
  location."*
- *"We do not share any personal information with third parties."*
  contradicts *"shares your email address."*

The opposition must be genuine, not merely a difference in emphasis or
completeness. Silence is not contradiction — that is NO_MATCH.

### NO_MATCH

The statement neither asserts nor denies the claim. This is the default and
will be the most common label.

- *"We use cookies to remember your preferences."* against *"collects your
  precise location"* — unrelated.
- *"We take security seriously."* against anything — says nothing about
  collection.

## 3. Decision rules

Apply in order. The first that settles the case wins.

1. **Topic gate.** If the statement does not discuss the claim's data type or
   a category that contains it, label NO_MATCH and stop. Do not reason about
   what the developer probably does.
2. **Explicit denial.** If the statement denies the claimed practice for that
   data type, label CONTRADICTS.
3. **Explicit or necessarily-implied assertion.** If the statement asserts the
   practice, or uses a broader term that necessarily includes the claimed data
   type, label SUPPORTS.
4. **Scope mismatch.** If the statement is about a different actor (a named
   third party's own practice, not the app's), a different product, or a
   different jurisdiction's users only, label NO_MATCH and note it.
5. **Still undecided.** Leave the pair unlabelled and flag it for
   adjudication. Do **not** invent a middle label. There is no Undetermined
   here; Undetermined is a system abstention, and a human who cannot decide
   must not manufacture ground truth.

## 4. Hard rules

- **Judge only the text in front of you.** Not the app, not its reputation, not
  what the policy says elsewhere.
- **Collection and sharing are different claims.** A statement about sharing
  does not support a collection claim, and the reverse.
- **"May" still counts.** *"We may collect your location"* asserts the
  practice; the law of hedged policy drafting is not our problem.
- **Breadth supports, narrowness does not.** A broader term supports a
  narrower claim. A narrower statement does not support a broader claim: *"we
  collect your work email"* does not support *"collects all contact
  information."*
- **No legal reasoning.** Whether a disclosure is adequate, lawful or fair is
  outside the label set and outside this project.

## 5. Quality control

- Every pair is labelled by **two** annotators independently.
- Disagreements go to a third annotator for adjudication. The adjudicated label
  is the gold label and is marked as adjudicated.
- Agreement is measured with Cohen's kappa on the doubly-labelled set, reported
  per label as well as overall. The figure is reported as measured, whatever it
  is.
- If agreement is poor, the guide is revised and the affected pairs are
  relabelled under a new guideline version. Guideline version is recorded with
  every annotation.
- **Target volume:** 300 to 500 pairs. If that cannot be reached with
  acceptable agreement, fine-tuning does not proceed and the zero-shot model is
  retained, per safeguard 5.

## 6. Sampling and splits

- Pairs are drawn from the same applications as the gold set, so the splits can
  be grouped consistently.
- **Splits are grouped by application.** Every pair from one application sits
  entirely in train, or entirely in validation, or entirely in test. Policy text
  is heavily boilerplate and repeated across apps from the same developer, so a
  random split by pair would leak and inflate the result.
- Class balance is recorded, not forced. NO_MATCH will dominate; that is a
  property of the problem and is handled in the metrics, not by discarding data.

## 7. What gets reported

For the zero-shot baseline and the fine-tuned model, on the same held-out test
set:

- Precision, recall and F1 for each of SUPPORTS, CONTRADICTS and NO_MATCH.
- Macro-F1 across the three.
- The confusion matrix.
- Abstention rate, with metrics computed twice: over non-abstained pairs, and
  over all pairs with abstentions counted as errors.

Accuracy alone is never reported. No improvement over the zero-shot baseline is
claimed unless the held-out test set shows it.
