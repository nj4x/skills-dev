# Composition Patterns

Skills compose at runtime — the agent loads multiple skills as needed for a single task. These patterns help you design skills that work together without stepping on each other.

---

## Core Rule: One Skill, One Concern

Each skill should have exactly one reason to trigger. Skills that bundle multiple concerns cause:
- Ambiguous triggering (fires when only part of the task applies)
- Bloated bodies (rare cases inflate the common-case load)
- Brittle coupling (updating one concern breaks the other)

If your skill does three things, it should be three skills with a lightweight orchestration layer.

---

## Pattern 1: Capability + Process Layers

The most common composition: a Pattern A skill provides a tool; a Pattern B skill directs how to use it.

```
Pattern B skill (code-review-discipline)
  └── invokes Pattern A skill (run-linter) as one step
```

Design the Pattern A skill to be invocable standalone. The Pattern B skill references it by name in its body instructions: "Run the lint check using the `run-linter` skill before proceeding."

---

## Pattern 2: Shared Config Substrate

When multiple skills need to share configuration (project context, team preferences, env flags), use a repo-level file they all read.

```
my-project/
├── AGENTS.md         ← shared context all skills read at activation
├── .claude/skills/
│   ├── skill-a/
│   └── skill-b/
```

Each skill body includes: "Before starting, read `AGENTS.md` for project-specific context." This avoids duplicating configuration across skill bodies and keeps a single update point.

---

## Pattern 3: Sequential Handoff

Skills designed to run in sequence (align → spec → build → verify) should define their output shapes explicitly so downstream skills can parse them reliably.

```
skill-align
  → writes: DECISION.md with a standard schema
skill-spec
  → reads: DECISION.md; writes: SPEC.md
skill-build
  → reads: SPEC.md
```

Document the schema in a shared `docs/formats.md` referenced by each skill in the chain.

---

## Avoiding Trigger Conflicts

When two skills have overlapping trigger conditions, one will shadow the other. Prevent this:

- Be specific about the domain in each description (file types, tools, exact scenarios)
- Use `disable-model-invocation: true` on skills that should only run when explicitly called
- Separate broad skills into narrow ones with distinct trigger phrases

Test the pair: give a prompt that should trigger only one skill and confirm the other stays silent.

---

## Anti-pattern: Bundled Mega-Skills

A skill that handles design + planning + implementation + testing + deployment is a framework, not a skill. The agent can't load just the testing part without loading the rest. Split it.

---

*See [AP-17 in common-anti-patterns.md](common-anti-patterns.md) for the anti-pattern entry on bundling.*
