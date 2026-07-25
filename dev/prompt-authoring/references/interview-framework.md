# Interview framework

Use a two-tier interview model. Start at Tier 1 by default.

## Tier 1 — compact intake (default)

Ask only the 5 canonical questions. These are duplicated from `references/question-bank.md`, the authoritative wording source:

1. What exact command, workflow, or artifact does this prompt drive?
2. What is the goal?
3. Which skills are involved, with how many critic rounds each? (plan-with-critic, FS-skill, SRS-skill, data-view skill, code-review, etc.)
4. What real command + log/check verifies each pass or completion?
5. Any exceptions to the default stop condition?

**Rules:**
- Prefer multiple-choice framing with a recommended default.
- Infer from the current request, existing specs, and code before asking.
- Use memory as hinting input, not a silent override.
- Ask the minimum needed to remove ambiguity. Do not ask all 5 if fewer suffice.

### Archetype decision (after intake answers, not before)

With intake answers in hand, apply the gate:
- Open-ended / iterative / no clear terminal → **LOOP** (self-repeating numbered loop, 25-40 lines)
- Clearly one-shot / definite terminal / fewer than 5 steps → **HELPER** (10-20 lines)
- Ambiguous → **LOOP**

Note: even prompts from deep interviews (Tier 2) still emit the LOOP or HELPER shape — not a spec document.

### Exit criteria

Advance to synthesis when these are all answerable:
- Target is explicit (the actual command/workflow)
- Archetype is decided (LOOP vs HELPER)
- Skills + round counts are named (or confirmed not needed)
- Verification command is named
- Stop condition is confirmed (canonical line or an exception)

If any remain unclear after the 5 questions, move to Tier 2.

---

## Tier 2 — deep interview mode

Use when Tier 1 leaves material ambiguity about what the prompt should do.

### Escalate when

- The workflow is underspecified and the prompt will be reused many times.
- Multiple phases or systems are involved and the author is uncertain of scope.
- Critic loops, review gates, or delegation strategy are still unclear.
- The user explicitly says "grill me".

### Deep interview topics (resolve one at a time)

- What exactly is the prompt optimizing for?
- What evidence sources may it consult? (codebase / current requirements/spec artifacts / logs / reference projects / memory / MCP)
- What phases should exist in the loop?
- Which skills with which round counts?
- What commands or checks define success for a single pass?
- What should trigger escalation to the user?

### Interaction style

- One decisive question at a time.
- Provide a recommended answer with each question.
- Invoke `grill-me` skill if available and the user wants intensive guidance.

---

## Defaulting policy

Apply these defaults when a stable pattern fits:

- Engineering requests → LOOP shape; single stop line; skills inline with round counts.
- Autonomous implementation → plan-with-critic (N rounds) in the loop.
- Spec/requirements change → refine existing requirements/spec artifacts with FS-skill + SRS-skill + data-view skill in the loop.
- Any code change → apply code-review skill step in the loop.
- Current requirements/spec artifacts + codebase lookup before asking = the "know-your-project-requirements" default; confirm it is in scope.

Do not force defaults when the choice is genuinely product-defining.

---

## Final synthesis handoff

Once ambiguity is low enough, stop interviewing and synthesize immediately. Do not keep asking after the structure is clear.
