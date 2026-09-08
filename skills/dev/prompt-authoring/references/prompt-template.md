# Prompt template

Choose an archetype after compact intake, before writing:
- **LOOP** (default) — for any open-ended, iterative, or engineering workflow. Bias hard to this.
- **HELPER** — only when the work is clearly a one-shot with a definite terminal state and fewer than 5 steps.

## Canonical stop line

> Stop the process when genuinely product design decisions are required from me, otherwise look up the answers in the current requirements/spec artifacts and the codebase.

Copy this line verbatim into every authored prompt as the single stop condition.

---

## Skeleton A — LOOP (default)

```
Establish autonomous iterative <verb1>/<verb2>/<verb3> process aiming to <one concrete goal>.

  0) <inspect/baseline — e.g. check current number of lines in /tmp/<app>.log>
  1) <run the real command — e.g. `LOG_LEVEL=DEBUG <app> <subcommand>`>
  2) <observe console output and new log entries>
  3) <capture the newly surfaced evidence>

  4) <identify the highest-value issue or next phase>
  5) <look up answers in current requirements/spec artifacts and the codebase>
  6) <consult reference material only when it changes the next move>
  7) <plan-with-critic (N rounds) the root-cause or implementation path>
  8) <record the chosen approach and concrete success signal>

  9) <proceed to plan execution>
  10) <if code changes are in scope: refine existing requirements/spec artifacts — use relevant requirements/data skills>
  11) <proceed to implementation execution>
  11.1) <apply relevant review skill to uncommitted code>

  12) <run the actual verification command>
  13) <confirm the concrete success signal>
  14) <update any reusable artifact or note needed for the next pass>
  15) <record any remaining issue as the next loop input>
  16) Continue to step 0 (repeat)

Stop the process when genuinely product design decisions are required from me, otherwise look up the answers in the current requirements/spec artifacts and the codebase.
```

### Authoring notes

- Opening line is mandatory; use the "Establish autonomous iterative …/aiming to…" phrasing.
- Name every skill inline with its round count or explicit depth marker (for example, `<planning skill> (N rounds)`, `<requirements skill>`, `<review skill>`). Round counts are part of the instruction, not decoration.
- For any prompt that can change code, the loop must be spec-driven: refine existing requirements/spec artifacts first, then clarify software requirements and use cases/data access patterns, then implementation, then review.
- Embed the **actual** command, the **actual** log path, and the **actual** check. No abstract "verification gate" wording.
- Reference-project paths and research-persistence folders go inline within a step, not in a separate section.
- Copy the canonical stop line verbatim from the `## Canonical stop line` section above. One line, no bullets.
- Steps 5 and 6.1 are optional — include them only when spec-update or code-review is relevant.
- Target: 25-40 lines total. If you're past 40, cut prose before cutting structure.

### Do not add

No separate sections for: Why-this-exists, Capability-model, Acceptance-criteria-as-N-items, Output-format, Review-checklist, multi-bullet Stop conditions, Assumptions-confirmed/inferred — unless the user explicitly asks for one of these.

---

## Skeleton B — HELPER (simple one-offs only)

```
# <Short title>

<One-paragraph objective.>

  1) <step>
  2) <step>
  3) <step>

<Inline verification: run X and confirm Y.>

Stop the process when genuinely product design decisions are required from me, otherwise look up the answers in the current requirements/spec artifacts and the codebase.
```

### Authoring notes

- Use only when the work is clearly bounded, single-pass, and has a definite terminal state.
- On ambiguity, use LOOP.
- If code changes are in scope, promote to LOOP so the prompt can carry the spec-first refinement chain.
- Target: 10-20 lines total.

---

## Concision bar

- LOOP prompts: 25-40 lines.
- HELPER prompts: 10-20 lines.
- Compress wording before adding sections. Never add a section the loop does not need.
- If a verification step is missing, add it as a numbered loop step — not as a `## Verification gates` section.
- If a stop condition is missing, paste the canonical stop line — not as a `## Stop and escalation conditions` section.
- If code changes are in scope and the prompt lacks relevant requirements/data skills before implementation, add them.
