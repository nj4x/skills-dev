# Authoring Workflow

A step-by-step process for building a skill from idea to production. Follow in order; each step informs the next.

---

## Step 1: Identify the Bottleneck

Before writing anything, answer: **Why does the agent fail at this task today?**

- Can't do X → Pattern A (capability primitive)
- Does X badly → Pattern B (process primitive)

If you can't name the specific failure, you're solving the wrong problem. Observe the agent on real tasks first.

---

## Step 2: Pick the Pattern

From your bottleneck answer:

| Bottleneck | Pattern | Shape |
|---|---|---|
| Missing capability | A — capability primitive | Thin wrapper + script |
| Bad process/quality | B — process primitive | Methodology in prose |

See [design-philosophy.md](design-philosophy.md) for the full decision tree.

---

## Step 3: Draft the Description (Triggers Only)

The description is the only part of your skill loaded at every session start. It must answer one question: **"Should I open this skill right now?"**

- Include: triggering conditions, symptoms, action verbs, specific tools/file types
- Exclude: how the skill works, implementation steps, mechanism descriptions

Draft 3–5 test phrases a user might say, and check that your description matches all of them. If fewer than 3 fire, revise the description before touching the body.

---

## Step 4: Write the Minimal Body

Write the smallest SKILL.md body that handles the common case. Don't aim for completeness — aim for correctness on the 80% path.

Rules:
- Pattern A: show the command syntax and explain the output shape; stop there
- Pattern B: write the ordered steps with explicit checkpoints; omit edge cases for now
- No prose that explains the obvious; every sentence should tell the agent something it wouldn't infer
- Under 5k tokens total

---

## Step 5: Extract Depth into `docs/`

Once the body is working, move rarely-needed content out:

- Advanced configuration → `docs/`
- Edge-case handling → `docs/`
- Detailed examples → `docs/`
- Platform-specific instructions → `docs/`

Keep each docs/ file flat — it must not reference other docs/ files (one level deep only).

---

## Step 6: Build Validation Loops into the Body

For every step in the skill that produces a meaningful output or modifies state, add an explicit checkpoint:

```
3. Run the migration:
   alembic upgrade head

4. Verify the migration applied:
   alembic current
   → Expected: the new revision hash. If not, check the error log before proceeding.
```

Don't leave verification implicit. The agent will skip it unless the skill body makes it explicit. Every non-trivial output should have a "verify before continuing" checkpoint.

**Pattern for destructive actions:**
```
Before [action]: check current state
If [expected state]: proceed with [action]
If [unexpected state]: surface to operator before acting
After [action]: confirm [expected result], log [outcome]
```

---

## Step 7: Run Adversarial Tests

Before publishing, deliberately try to break the skill:

1. **Near-miss triggers** — phrases that almost but shouldn't match the description. Confirm the skill doesn't fire.
2. **Partial-match invocations** — activate the skill then give it an incomplete or ambiguous request. Confirm it branches correctly rather than guessing.
3. **Edge-step stress tests** — send a task that exercises the fragile steps (the ones with explicit checkpoints). Confirm the agent uses the checkpoints, not free-form improvisation.
4. **"What can go wrong?"** — ask a separate LLM session: "What edge cases break this skill?" Patch the gaps it names.

Target: the skill fires on 4/5+ of the intended phrasings and stays silent on all near-miss phrasings.

---

## Step 8: Measure Token Cost

Count tokens before publishing:

- SKILL.md: < 5,000 tokens
- Each docs/ file: no hard limit, but question anything over 2,000 tokens

If SKILL.md is over 5k, you've left content in that belongs in docs/. If a docs/ file is over 3k, consider whether it should be two files.

Quick estimate: word count × 1.3 ≈ token count.

---

## Step 9: Publish and Monitor

Version-control the skill like code. After the first real use, observe where the agent diverges from the body and patch the specific line responsible — don't rewrite wholesale.

---

*Related: [testing-protocol.md](testing-protocol.md) for detailed test matrices. [design-philosophy.md](design-philosophy.md) for Pattern A vs B decision tree.*
