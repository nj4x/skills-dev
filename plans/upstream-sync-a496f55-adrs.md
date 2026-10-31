# Design Decisions Reached During Grilling — upstream sync 49dd158..a496f55

These are the design decisions reached during a grilling session on which upstream `mattpocock/skills` changes to port into skills-dev. Evidence is in `docs/research/upstream-skills-diff-2026-10-30.md`; the prior sync is `docs/adr/0078-upstream-sync-2026-10.md`.

- docs/adr/0083-upstream-sync-2026-10-30.md

---

## Session Ledger

| Role         | Outcome            |
|--------------|--------------------|
| orchestrator | —                  |
| planner      | complete           |
| critic #1    | revise (major)     |
| critic #2    | revise (major)     |
| critic #3    | approve (minor)    |

## Critic Review

- **Final verdict:** approve
- **Severity:** minor
- **Iterations used:** 3 (pass 2 halted on the convergence guard; user approved the fixes and a third pass)
- **Approval status:** Approved by critic on pass 3 after user-directed fixes (union GitLab frontier, implement-spec sequenceDiagram). ID-006 and ID-007 accepted by the user as out-of-scope follow-ups.
- **Risks / questions:**
  - [major] ADR-0083 Decision 2 (`implement-spec`) describes an orchestrator/subagent exchange in prose only; no `sequenceDiagram`.
  - [major] GitLab frontier change drops existing wayfinder children that carry only `Part of #<map>` once a repo reruns `/setup-skills`; no migration, backfill or union alternative recorded.
  - Minors: Part-of-only tickets invisible to the frontier; `-F json` evidence not in the follow-up list; Section A bullet filed under Port though already shipped; scope noise in Consequences; 7739eae site claim ambiguous for implement-spec.
