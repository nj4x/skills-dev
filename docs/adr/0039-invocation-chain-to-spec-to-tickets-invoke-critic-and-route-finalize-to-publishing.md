# Invocation chain: to-spec/to-tickets invoke critic and route FINALIZE to publishing

ADR-0034 says the skills "run the critic loop" and "auto-publish on approval," but not *how* the skills invoke critic, nor how critic's approval path — which today decomposes an approved plan into implementation phases — is redirected to **publishing** instead of code implementation. This ADR fixes the invocation chain.

## How the skills invoke critic

`to-spec` and `to-tickets` invoke critic via the **Skill tool** with the explicit-path sentinel:

```
Skill(critic, args: "pickup:<staged-draft-or-manifest-path> 3 auto")
```

Critic's frontmatter declares `arguments: [task, max_iterations, mode]` (positional). The iteration cap **must** be supplied explicitly as the second positional argument; otherwise `auto` would bind to `max_iterations` and the mode would silently default. The invocation is therefore three positional tokens:

- **`pickup:<path>`** (`task`) — critic's **plan-mode-independent** PICKUP path (critic Step "Critic-specific overrides", resolution rule 1). It works in headless/agent runs where plan mode is unavailable — required because `to-spec` becomes headless-capable (ADR-0035). The path is the staged draft: `.../draft-spec.md` for a spec, or `.../manifest.md` for tickets.
- **`3`** (`max_iterations`) — the revision cap of ADR-0034 ("reviewed up to 3 times (at most 2 automatic revisions)"), passed explicitly so `auto` lands in the `mode` slot.
- **`auto`** (`mode`) — critic runs its loop without pausing to flag decisions to the user; the skills have already taken the user's product-shaping input before drafting (ADR-0034), so critic's job here is purely the quality gate.

The skills do **not** re-implement the repeat loop via the Agent tool; delegating to the installed `critic` skill keeps one loop implementation. Critic already loads `repeat` for its loop contract.

## Pickup-only precondition (no iteration-0 GENERATE)

These skills **always** invoke critic via `pickup:<path>`, never via a fresh plan-mode entry. Consequently critic skips the iteration-0 GENERATE_STEP and enters directly at REVIEW_STEP over the staged file. Because `artifact_type` is resolved in REVIEW_STEP (ADR-0037), it is **always** resolved before any GENERATE_STEP branches on it (ADR-0038) or before FINALIZE_STEP routes on it (below). No code path reached through this invocation can observe an unresolved `artifact_type`.

## How FINALIZE routes to publishing, not implementation

Critic's FINALIZE_STEP `auto_approval == True` branch currently reads the approved artifact and **proceeds directly to implementation** (decompose into phases, spawn implementer sub-agents). For `artifact_type IN {spec, tickets}` this is wrong — the approved artifact must be *published to a tracker*, not implemented as code.

FINALIZE_STEP becomes **artifact-type-aware**:

- `artifact_type == plan` → existing behaviour (decompose + implement).
- `artifact_type == design-review` → existing behaviour (no implementation; ADRs are the artifact).
- `artifact_type IN {spec, tickets}` → **do not implement**. Critic prints the approval sentinel `PLAN_APPROVED_READY_FOR_FINALIZATION: <path>` and **returns control to the calling skill**. Publishing is owned by the publishing skill, not by critic.

On return, the to-spec / to-tickets orchestrator inspects the outcome:

- **Approved** (sentinel present, `auto_approval` true) → run the skill's own publish step (to-spec Step 3 publish / to-tickets Step 5), applying `ready-for-agent` and, for real trackers, creating issues + blocking edges with the failure handling of ADR-0040.
- **Not approved** (revise-at-cap, major severity, invalid output, hard-abort) → `auto_approval` is false, no sentinel; the skill does **not** publish and follows ADR-0034's cap-exhaustion / headless rules (present or stop, leave the draft staged).

Publishing logic stays in the publishing skills so critic remains artifact-agnostic beyond selecting groups and routing FINALIZE.

## Considered Options

- **Skill inlines repeat/critic logic via Agent tool**: duplicates the loop and drifts from `critic`/`repeat`. Rejected.
- **Critic performs the publish itself in FINALIZE**: couples critic to tracker APIs and the `ready-for-agent` vocabulary; every publishing change would touch critic. Rejected — critic only signals approval and hands back.
- **Plan-mode context-line pickup instead of `pickup:<path>`**: unavailable in headless runs; would break `to-spec`'s headless capability (ADR-0035). Rejected.
- **`MODE=guided`**: would surface FLAGGED_DECISIONS mid-loop and require an interactive user; the product-shaping decisions are already resolved before drafting, so `auto` is correct.
