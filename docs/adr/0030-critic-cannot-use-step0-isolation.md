# Critic's isolation is reviewer-level, not skill-level

Critic's PICKUP mode is context-coupled. Reviewer-level isolation via the Agent tool is sufficient; skill-level auto-isolation is unnecessary and would be fragile.

## Context

When critic was designed, code-review's Step 0 auto-isolation pattern (ADR-0029) existed as a model for uniform isolation. The question arose: should critic receive the same treatment for symmetry? Critic is called inline from parent skills: `learning/grill-me`, `engineering/grill-with-docs`, and `engineering/refactor-claude-md` all invoke critic without arguments.

However, ADR-0029 was subsequently reversed: Step 0's bash detection never fired because plans/ uses descriptive slug filenames, not session-ID filenames. The pattern it was meant to enforce is no longer available.

## Decision

Critic's isolation strategy is **not** skill-level auto-detection (like the attempted Step 0), but **reviewer-level isolation** via the Agent tool.

## Why the current approach is sufficient

Critic's PICKUP mode discovers the plan/manifest file from either:
1. An explicit path sentinel: `pickup:plans/foo.md` (caller-provided, plan-mode-independent)
2. A plan-mode context line: `A plan file exists from plan mode at: <path>` (interactive Claude Code only)

The core isolation concern — reviewer pollution from grilling context — is already addressed: Critic's REVIEW_STEP dispatches the adversarial reviewer as a fresh Agent subagent with plan/ADR content passed **verbatim** in the prompt. The reviewer never sees the grilling transcript or parent context. The isolation concern for the *judging work* is structurally met, regardless of how critic is invoked.

Critic's orchestration is also lightweight: no build, no PR intake, no document discovery. It reads plan text and dispatches agents. The pollution surface is minimal compared to code-review.

## Callers must provide explicit paths

Recent changes ensure PICKUP works in plan-mode-disabled environments (agent / headless runs) by accepting an explicit `pickup:<path>` sentinel from the caller. Callers like `grill-me` now write the manifest and pass `pickup:plans/manifest.md` explicitly, decoupling critic from plan-mode context availability.

If a concrete isolation failure emerges (caller context visibly polluting reviewer judgment), convert PICKUP entirely to FRESH with explicit manifest-path arguments — but this has not been necessary.
