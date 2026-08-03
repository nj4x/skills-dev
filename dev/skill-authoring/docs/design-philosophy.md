# Design Philosophy: Capability vs Process Primitives

Before writing a skill, name the bottleneck. Two types of bottleneck exist, and each calls for a different kind of skill.

## The Bottleneck Question

Ask: **Why does the agent fail at this task today?**

- "The agent _can't do X_" → **Pattern A** (capability primitive)
- "The agent _does X badly or inconsistently_" → **Pattern B** (process primitive)

The wrong answer leads to a skill that is too thin (agent still can't do the task) or too heavy (agent can do the task but you've wrapped simple judgment in 300 lines of instructions).

---

## Pattern A — Capability Primitives

A thin wrapper over a deterministic CLI or script. The real logic lives in code; the skill's job is to teach the agent how to invoke that code and interpret its output.

**Shape:**
- 30–80 lines in SKILL.md
- Heavy on command examples with inline comments
- Light on prose
- References `scripts/` for the actual work

**Choose Pattern A when:**
- The agent consistently hallucinates data it should fetch (→ add a real search/API call)
- The task requires side effects the agent can't produce alone (→ send email, write file, call webhook)
- The output must be deterministic regardless of context (→ script it)

**Examples:**
- Email sender: agent composes, script delivers
- Search tool: agent queries, script fetches and returns results
- API-access wrapper: agent constructs params, script handles auth/HTTP/parsing
- Browser automation: agent decides what to do, script drives the browser

**Anti-pattern to avoid:** Writing a capability skill with 200 lines of prose instructions for what the script already handles. The script output is the interface; the skill just needs to explain what inputs to pass and what the output means.

---

## Pattern B — Process Primitives

Encodes a methodology the agent should follow. Pure prompt engineering — no scripts. The skill's job is to shape the agent's _process_, not add to its tools.

**Shape:**
- 50–200 lines in SKILL.md (more prose is justified because it IS the logic)
- Checklists, ordered steps, decision trees
- Validation checkpoints built into the body
- Little or no `scripts/`

**Choose Pattern B when:**
- The agent can do the task but skips steps, takes shortcuts, or produces inconsistent quality
- The workflow requires enforced sequencing (never deploy before tests pass)
- The agent needs to adapt to context at each step (a rigid script would be too brittle)

**Examples:**
- Code-review discipline: the agent can read code, but without the skill it misses security checks
- TDD workflow: the agent can write tests, but without the skill it writes them after the code
- Design-alignment process: the agent can draft specs, but without the skill it skips stakeholder concerns

**Anti-pattern to avoid:** Wrapping a Pattern B skill in scripts. If the logic is judgment-dependent, a script can't capture it. You'll write a script that calls the LLM, which defeats the purpose.

---

## A Mature Setup Uses Both

Pattern A gives the agent better _tools_. Pattern B gives it better _methods_. They compose: a Pattern B skill (e.g. "deployment discipline") can invoke a Pattern A skill (e.g. "run health check script") as one of its steps.

Don't bundle them into one skill. Separation keeps each triggerable independently and lets you improve the tool or the method without touching the other.

---

## Decision Tree

```
Why is the agent failing?
├── Can't do X (missing capability)
│   └── Pattern A — write a thin wrapper with a real script
└── Does X badly (poor quality / inconsistent process)
    └── Pattern B — write a methodology the agent follows

Is it both?
└── Two skills: one Pattern A for the capability, one Pattern B for the process
    └── The Pattern B skill can reference the Pattern A skill in its steps
```

---

## Note on Line Count

Pattern A skills are short because their logic is in code. If your Pattern A SKILL.md exceeds 100 lines, you've probably written prose that the script already handles — trim it. If your Pattern B SKILL.md is under 30 lines, you've probably been too vague — the agent will fill gaps with its own judgment, inconsistently.

---

*See [skill-authoring](../SKILL.md) for where these patterns fit in the create workflow.*
