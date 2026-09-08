---
name: prompt-authoring
description: Author reusable markdown prompt artifacts for autonomous research, planning, implementation, debugging, or verification workflows. Defaults to a single self-repeating numbered LOOP (inspect/run → analyze → critic → spec-first execution → verify → repeat) with one crisp stop condition. Keeps a lighter HELPER path for simple one-off prompts. Use when the user asks to "create a prompt", "author a prompt", "design an autonomous workflow prompt", "turn this idea into a reusable prompt", or "write me a prompt for Claude Code".
disable-model-invocation: true
---

# prompt-authoring

Author a reusable markdown prompt that another Claude or Claude Code session can execute reliably.

## Two archetypes

**LOOP** (default) — for any open-ended, iterative, or engineering workflow:
one opening line + single self-repeating numbered loop (0..N → Continue to step 0) + one verbatim stop line. Target 25-40 lines.

**HELPER** — only when the work is clearly one-shot, has a definite terminal state, and fewer than 5 steps. Target 10-20 lines.

Bias hard to LOOP. Default to LOOP on ambiguity. If code changes are in scope, promote to LOOP so the prompt can carry the full spec-first chain.

## Default stop line (copy verbatim from `references/prompt-template.md`)

> Stop the process when genuinely product design decisions are required from me, otherwise look up the answers in the current requirements/spec artifacts and the codebase.

This is the single-line stop condition for both archetypes. Do not expand into multiple bullets.

## Paradigm skills to promote inline (with round counts)

When synthesizing a LOOP prompt, name relevant skills inside loop steps with explicit round counts:
- `critic (N rounds)`
- `FS-skill` (refine existing requirements/spec artifacts)
- `SRS-skill` (refine derived software requirements against current specs)
- `data-view-skill` (refine use cases and data access patterns)
- `apply code-review skill to uncommitted code`

Round counts are part of the instruction — they control depth and are not decoration.

## Workflow

### Step 1 — classify signal

Identify: partial draft / vague idea / concrete request. Note whether the scope is open-ended or clearly bounded. Call out vague areas explicitly and give your own suggested defaults when a stable pattern clearly fits.

### Step 2 — compact intake (3-5 questions)

Ask only what is needed:

1. What exact command, workflow, or artifact does this prompt drive?
2. What is the goal?
3. Which skills are involved, with how many critic rounds each? (critic, FS-skill, SRS-skill, data-view-skill, code-review, etc.)
4. What real command + log/check verifies each pass or completion?
5. Any exceptions to the default stop condition?

Infer from the current request, codebase, and requirements before asking. Only ask what you cannot infer. If the current request is vague, explicitly identify the vague parts and propose the most likely defaults.

### Step 2.5 — archetype gate (after intake, with full information)

- Open-ended / iterative / no clear terminal → **LOOP**
- Truly single-pass / clear terminal / fewer than 5 steps → **HELPER**
- Ambiguous → **LOOP**
- If code changes are in scope, choose LOOP.

### Step 3 — memory scan

Check conversation history and any uploaded files for prior skill names, round counts, domain context, and preferred stop phrasing. See `references/memory-guidance.md`.

### Step 4 — synthesize into final authored prompt

Select the skeleton from `references/prompt-template.md`. Replace generic placeholders with the user's actual:
- skills and round counts (e.g. `critic (3 rounds)`, `FS-skill`, `SRS-skill`, `data-view-skill`, `apply code-review skill`)
- existing requirements/spec artifacts to refine, goal, and target command/workflow
- verification command and log path

The template files are never modified. Substitution happens only in the authored prompt.

For LOOP prompts: emit the loop shape directly. Do not expand into standalone `##` sections. Copy the canonical stop line verbatim.

For HELPER prompts: title + mission + ≤5 steps + inline verification + stop line. If code changes are in scope, promote to LOOP so the prompt can stay spec-first.

If the user explicitly wants a rigorous interview or says "grill me", use the `grilling` skill if available.

### Step 5 — pre-write guard + return

Before writing or returning the prompt, check:
1. Verification step present inline in the loop (or as an inline line for HELPER)?
2. Canonical stop line present verbatim?
3. Target/goal explicit in the opening line, including existing requirements/spec artifacts to refine when applicable?
4. If code changes are in scope, does the prompt include FS-skill + SRS-skill + data-view-skill before implementation?

Fix inline if any check fails. Then return the authored prompt inline, or write to file:
- User gave an explicit path → write there.
- User asked for a reusable file → write to `~/.claude/plans/<short-kebab-slug>-prompt.md`.
- Otherwise → return inline.

Report in one sentence: returned inline or written to `<path>`.

## Concision bar

LOOP: 25-40 lines. HELPER: 10-20 lines. If the prompt grows past the target, compress wording before adding sections. See `references/anti-patterns-and-defaults.md` for what not to include.

## Additional resources

- [references/prompt-template.md](references/prompt-template.md) — skeletons + canonical stop line
- [references/interview-framework.md](references/interview-framework.md) — Tier 1/2 interview model
- [references/anti-patterns-and-defaults.md](references/anti-patterns-and-defaults.md) — what to avoid
- [references/memory-guidance.md](references/memory-guidance.md) — memory rules
- [examples/autonomous-rd-prompt.md](examples/autonomous-rd-prompt.md) — LOOP + HELPER examples
- [examples/compact-intake.md](examples/compact-intake.md) — intake example
