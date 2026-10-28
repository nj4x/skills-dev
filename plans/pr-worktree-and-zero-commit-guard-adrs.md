# Design Decisions Reached During Grilling — pr-worktree skill and code-review zero-commit guard

Design decisions reached during grilling (2026-10-28). They fix a retro finding: a session worked in the wrong worktree when its target was an existing PR branch. The ADR files are the ground truth; edit them directly.

- docs/adr/0081-pr-worktree-skill.md
- docs/adr/0082-code-review-zero-commit-guard.md

---

## Session Ledger

| Role         | Outcome                  |
|--------------|--------------------------|
| orchestrator | —                        |
| planner      | complete                 |
| critic #1    | revise (major)           |
| critic #2    | revise (major)           |

Convergence guard halted: major count did not decrease. Standing issues:
- [A][major] Only one branch-state row fetches; other rows and the sync rule assume `origin/<branch>` exists and is current.

## Critic Review

- **Final verdict:** revise
- **Severity:** major
- **Iterations used:** 2 of ∞ (convergence guard)
- **Approval status:** Requires manual review and approval.
- **Risks / questions:** fetch only in one row (major); fork PRs scope; `.claude/worktrees/` row skips step 4; no rule for unresolved branch/PR; upstream not set for existing untracked local branch; rename asked before divergence known; push safety depends on `push.default`; ADR-0082 counts all worktrees against one base; ADR-0082 has no rejected alternatives.
