# Taxonomy mapping (F-15)

The OPP-115 category to Google Play Data Safety category mapping lives here as
a versioned JSON file and is seeded into the `taxonomy_mapping_version` and
`taxonomy_mapping_entry` tables.

It is here rather than under `data/` because it is the team's own authored
artefact, not a third-party dataset: it must be version-controlled, reviewable
and citable in the report.

**This mapping is a rule-based lookup, not a learned model.** That separation is
deliberate and is recorded in the Phase 3 design: F-15 is deterministic
lookup, F-18 is learned semantic alignment, and merging them would make the
system's reasoning impossible to explain or audit.

Built in Milestone 7. Nothing here yet.
