# Requirement Change Log

Any deviation from the approved Phase 2 SRS or Phase 3 design, with its
justification and approval state.

The approved documents are the baseline. Implementation does not get to change
them quietly. An entry here is a request until the faculty guide approves it.

| ID | Date | Approved baseline | Proposed change | Reason | Approval |
|---|---|---|---|---|---|

**No entries.** As of the end of Milestone 1, nothing implemented deviates from
the approved requirements or design.

---

## Known candidates for a future entry

These are not changes yet. They are places where a change may become necessary,
recorded now so they are not presented as surprises later.

1. **FR-12 span extraction scope.** If PolicyIE and PI-Extract licence terms do
   not permit our use, span supervision rests on OPP-115 alone. Phase 2
   assumption A-04 already states the project must not depend on those corpora,
   and Phase 3 records a documented fallback. Invoking that fallback would
   require an entry here and faculty approval.

2. **F-18 semantic alignment training data.** No public corpus labels
   (policy statement, Data Safety claim) pairs. Plan §7 sets out two options.
   Option A, which keeps the approved methodology, needs 300 to 500
   hand-labelled pairs. If neither option proves workable, any change to the
   approved three-task methodology would require an entry here.

3. **NFR-02 single-audit latency.** Phase 3 records design issue DI-1 as open:
   the 60-second CPU target is not yet demonstrated. It is measured in
   Milestone 6. If it cannot be met with the chosen models, the options are a
   smaller model or a revised target, and the latter would require an entry
   here.
