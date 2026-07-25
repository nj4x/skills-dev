# Design Decisions Reached During Grilling

Design decisions captured during a grill-with-docs session on integrating adversarial critic review into the `to-spec` and `to-tickets` skills, with auto-proceed to publishing on approval.

- docs/adr/0034-critic-first-flow-for-to-spec-and-to-tickets.md
- docs/adr/0035-to-spec-removes-disable-model-invocation.md
- docs/adr/0036-critic-common-core-plus-artifact-specific-fifth-group.md
- docs/adr/0037-frontmatter-signals-artifact-type-to-critic.md
- docs/adr/0038-synthesizer-edits-artifact-in-place-during-revisions.md
- docs/adr/0039-invocation-chain-to-spec-to-tickets-invoke-critic-and-route-finalize-to-publishing.md
- docs/adr/0040-auto-publish-failure-handling-create-then-link-with-resume.md
- docs/adr/0041-publishing-reliability-resume-and-idempotency-deferred.md

---

## Session Ledger

| Role         | Outcome              |
|--------------|----------------------|
| orchestrator | —                    |
| synthesizer  | complete (3 revisions) |
| critic #1    | revise (major)       |
| critic #2    | revise (major)       |
| critic #3    | revise (major)       |
| critic #4    | approve (minor)      |

## Critic Review

- **Final verdict:** approve
- **Severity:** minor
- **Iterations used:** 4 (MAX_ITERATIONS = ∞, backstop 10)
- **Approval status:** ✓ Automatically approved by critic. This is an advisory design review — the ADR set is the deliverable; no implementation was in scope.
- **Post-approval hardening:** the clear-win minor findings were folded into the ADRs after approval — dirty-marker lifecycle (0034), draft-spec.md cleanup symmetry (0034), rejection rationale for all four considered options (0034), stale-slug annotation (0036), path-traversal/absolute-path rejection in manifest parsing (0037), resolution-order-safe spec re-read + tickets re-read analogue + spec read-failure assertion + acyclicity assertion (0038), cyclic-manifest create-pass abort (0040), overwrite-vs-resume inherited-constraint note (0041).
- **Remaining advisory risks (deliberately not changed):**
  - Headless "shaping-context validation" (0034) is a fuzzy semantic pre-gate; kept as a defensible safety layer rather than cut or over-formalised.
  - Slug plumbing to markers/reports is left as an implementation detail (skill owns the slug; markers write under `.scratch/<feature-slug>/`).
  - Concurrent runs sharing a feature-derived slug are out of scope (no staging lock); overwrite semantics are single-run only.
