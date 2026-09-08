# Question bank

**`references/question-bank.md` is the authoritative source for question wording. SKILL.md inlines the compact set for friction-free use — if they diverge, this file wins.**

---

## Canonical intake questions

Use this set first. Ask only the ones you cannot infer from the request, codebase, memory, or current requirements/spec artifacts.

1. What exact command, workflow, or artifact does this prompt drive?
2. What is the goal?
3. Which skills are involved, with how many critic rounds each? (plan-with-critic, FS-skill, SRS-skill, data-view skill, code-review, etc.)
4. What real command + log/check verifies each pass or completion?
5. Any exceptions to the default stop condition?

**Hinting style:** offer a recommended default + 2-3 alternatives. Example:

> Which skills with round counts? Recommended for spec/code-change loops: `plan-with-critic (3 rounds)` + `FS-skill` + `SRS-skill` + `data-view skill` + `apply code-review skill` to refine current requirements/spec artifacts before implementation. Alternatives: trim to `plan-with-critic` only for pure debugging.

---

## Extended bank (appendix — for deep interview mode)

Use these when Tier 1 intake leaves material ambiguity.

### Prompt objective

- What is the prompt meant to accomplish?
- Which best fits? research / planning / implementation / debugging / verification / end-to-end autonomous loop

### Exact target

- What command, skill, workflow, artifact, or operating loop should the prompt drive?
- One-shot task / reusable skill pattern / multi-phase autonomous workflow / review loop / refinement loop?

### Autonomy level

- Low — ask before major steps
- Medium — proceed with reasonable defaults, stop at checkpoints
- High — proceed autonomously except for genuine product decisions
- Max — run full loops, escalate only on hard blockers or product decisions

### Evidence sources

- What may the prompt rely on? current codebase / current requirements/spec artifacts / logs / reference projects / memory / web / external tools / MCP servers

### Critic / review loop

- None / one lightweight self-check / fixed N rounds / critic rounds until approval

### Delegation / chunking

- Monolithic / chunk into independent sub-phases / sub-agents for research only / sub-agents for implementation and review

### Memory reuse

- Preferred autonomy level / preferred output structure / favored verification style / repeated workflow sections / prior artifact-location patterns
