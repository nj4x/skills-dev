# Example — compact intake

## User request

> Create a prompt that helps me continue the next incomplete phase of my project autonomously.

## Good compact intake

1. What exact command, workflow, or artifact does this loop drive?
   - Recommended: continue the next incomplete project phase by discovering state, picking the phase, implementing it, and verifying with the project's test command.
2. What is the goal?
   - Recommended: advance the project to the next complete phase without stopping for non-product decisions.
3. Which skills with how many critic rounds? (plan-with-critic, FS-skill, SRS-skill, data-view skill, code-review skill, etc.)
   - Recommended: `plan-with-critic (2 rounds)` before plan execution; `FS-skill` → `SRS-skill` → `data-view skill` before implementation; then `apply code-review skill`.
4. What real command + log/check verifies each pass?
   - Recommended: `python -m pytest` or equivalent; confirm tests pass before "Continue to step 0".
5. Any exceptions to the default stop condition?
   - Recommended: none — use the canonical stop line verbatim.

**Archetype gate** (after answering the above): open-ended, iterative, no clear terminal → **LOOP**.

## Resulting prompt shape (LOOP)

```
Establish autonomous iterative discover/plan/implement/verify process aiming to advance the project to its next complete phase.

  0) Read IMPLEMENTATION_PLAN.md and identify the next incomplete phase
  1) Inspect the current codebase for the files and boundaries that phase touches
  2) Inspect the current requirements artifacts for that phase
  3) Identify the concrete completion criteria for the phase

  4) plan-with-critic (2 rounds) for the implementation path
  5) Choose the smallest viable path that still completes the phase
  6) Proceed to plan execution
  7) Refine existing product requirements with FS-skill

  8) Refine derived software requirements with SRS-skill
  9) Refine use cases and data access patterns with data-view skill
  10) Proceed to implementation execution
  10.1) Apply code-review skill to uncommitted code

  11) Run `python -m pytest` and confirm all tests pass
  12) Confirm the phase now satisfies its completion criteria
  13) Reconcile any updated artifacts back to the phase definition
  14) Record any newly discovered incomplete phase or blocker
  15) Continue to step 0 (repeat)

Stop the process when genuinely product design decisions are required from me, otherwise look up the answers in the current requirements/spec artifacts and the codebase.
```

## HELPER shape (for reference)

When the request is a clearly bounded one-off with a definite terminal state:

```
# <Short title>

<One-sentence objective.>

  1) <step>
  2) <step>
  3) <step>

<Inline verification line.>

Stop the process when genuinely product design decisions are required from me, otherwise look up the answers in the current requirements/spec artifacts and the codebase.
```

## Why this is good

- 5 canonical questions, inferred wherever possible.
- Archetype gate fires after intake answers are in — not before.
- Resulting LOOP stays inside the 25-40 line target and shows the full inspect → plan → refine specs → implement → verify cycle with real commands.
- HELPER shape shown for contrast — same stop line, no ceremonial sections.
