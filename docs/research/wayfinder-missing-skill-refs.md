# Wayfinder Missing Skill References: `/prototype` and `setup-lineage`

## Summary

`/prototype` and `setup-lineage` are NOT missing or undefined. Both are real, installed skills with `disable-model-invocation: true` frontmatter. They don't appear in the session's available-skills list because `disable-model-invocation` prevents Claude from loading their descriptions into context — they are invocable only by you manually (via `/prototype` slash command), not by Claude automatically. Wayfinder correctly references them in its documentation as slash commands (not as skills Claude invokes).

---

## 1. Exact Locations and Wording of References

### Wayfinder SKILL.md (repo and installed)

**Repo path**: `/Users/roman/projects/skills-dev/skills/engineering/wayfinder/SKILL.md`  
**Installed symlink**: `~/.claude/skills/wayfinder → /Users/roman/projects/skills-dev/skills/engineering/wayfinder`

**References**:

| Line | Context | Full Quote |
|------|---------|-----------|
| 19 | Inline paragraph on requirements-lineage | `Consult `engineering/setup-lineage/SKILL.md` → [Requirements boundary](../setup-lineage/SKILL.md#requirements-boundary).` |
| 71 | Ticket Types heading | `Each ticket carries a `wayfinder:<type>` label — one of `research`, `prototype`, `grilling`, `task`…` |
| 84 | Prototype ticket type description | `**Prototype** (HITL): Raise the fidelity of the discussion by making a cheap, rough, concrete artifact to react to — an outline, a rough take, a stub, or UI/logic code via the /prototype skill.` |

No differences between repo and installed versions (both live at same location via symlink).

### Other Files Referencing `/setup-lineage`

- **`skills/planning/critic/docs/critic-prompt.md:147`**: `**Requirements boundary**: Consult `engineering/setup-lineage/SKILL.md` → [Requirements boundary](../../engineering/setup-lineage/SKILL.md#requirements-boundary).`
- **`skills/requirements/FS-skill/SKILL.md:77`**: `Read `engineering/setup-lineage/SKILL.md` → [Requirements boundary](../../engineering/setup-lineage/SKILL.md#requirements-boundary).`
- **`skills/requirements/SRS-skill/SKILL.md:11`**: `Read `engineering/setup-lineage/SKILL.md` → [Requirements boundary](../../engineering/setup-lineage/SKILL.md#requirements-boundary).`
- **`skills/requirements/data-view-skill/SKILL.md:9`**: `Read `engineering/setup-lineage/SKILL.md` → [Requirements boundary](../../engineering/setup-lineage/SKILL.md#requirements-boundary).`

All are relative links to `../../engineering/setup-lineage/SKILL.md`, which resolve correctly from their locations.

---

## 2. Do These Skills Exist?

**YES. Both exist and are installed.**

### `prototype` skill

- **Repo location**: `/Users/roman/projects/skills-dev/skills/engineering/prototype/`
- **Installed at**: `~/.claude/skills/prototype → /Users/roman/projects/skills-dev/skills/engineering/prototype` (symlink created 2026-09-20)
- **SKILL.md frontmatter**:
  ```yaml
  name: prototype
  description: Build a throwaway prototype to answer a design question. Use when the user wants to sanity-check whether a state model or logic feels right, or explore what a UI should look like.
  disable-model-invocation: true
  ```
- **Supporting files**: `LOGIC.md`, `UI.md`, `agents/openai.yaml`
- **Git history**: Initial commit `ff52648` (2026-07-24), refactored to `skills/engineering/prototype/` in commit `e42e1dd` (2026-09-08)

### `setup-lineage` skill

- **Repo location**: `/Users/roman/projects/skills-dev/skills/engineering/setup-lineage/`
- **Installed at**: `~/.claude/skills/setup-lineage → /Users/roman/projects/skills-dev/skills/engineering/setup-lineage` (symlink created 2026-09-20)
- **SKILL.md frontmatter**:
  ```yaml
  name: setup-lineage
  description: Retrofit an existing repo with lineage frontmatter and inline source-reference fields across the FS→SRS→ADR→Spec→Ticket chain. Standalone skill — not part of setup-skills.
  disable-model-invocation: true
  ```
- **Git history**: Created in commit `353beac` (2026-07-27); was at root as symlink (`setup-lineage → engineering/setup-lineage`) and removed via commit `bfdee67` (2026-08-29)
- **ADR**: ADR-0065 documents the skill's design (status: Approved)

### `wayfinder` skill

- **Repo location**: `/Users/roman/projects/skills-dev/skills/engineering/wayfinder/`
- **Installed at**: `~/.claude/skills/wayfinder → /Users/roman/projects/skills-dev/skills/engineering/wayfinder`
- **SKILL.md frontmatter**:
  ```yaml
  name: wayfinder
  description: Plan a huge chunk of work — more than one agent session can hold — as a shared map of decision tickets on your issue tracker, and resolve them one at a time until the way to the destination is clear.
  disable-model-invocation: true
  ```
- **Git history**: Adopted from mattpocock/skills, refactored to `skills/engineering/wayfinder/` in `e42e1dd`; updated in `75ad8b8` (2026-08-29) with requirements-lineage section

---

## 3. Why Aren't They in the Session's Available-Skills List?

**All three skills (`prototype`, `setup-lineage`, `wayfinder`) have `disable-model-invocation: true`.**

Per [Claude Code docs (code.claude.com)](https://code.claude.com/docs/en/skills):

> Set to `true` to prevent Claude from automatically loading this skill. Use for workflows you want to trigger manually with `/name`. Also prevents the skill from being preloaded into subagents.
>
> **Effect on availability:**
> - The skill's **description is NOT loaded into context**, so Claude doesn't know the skill exists
> - You can still invoke it manually with `/skill-name`
> - Claude cannot invoke it automatically via the Skill tool

The session's available-skills list shows only skills **without** `disable-model-invocation: true` — those where Claude's context is loaded with the description and Claude can see them. The skills-dev repo intentionally marks `wayfinder`, `prototype`, and `setup-lineage` as directive-only (manual invocation only) because they are workflows with side effects (creating issues, opening editors, making decisions) that should not be triggered automatically by Claude.

**Symlink verification**:
```
~/.claude/skills/prototype → /Users/roman/projects/skills-dev/skills/engineering/prototype
~/.claude/skills/setup-lineage → /Users/roman/projects/skills-dev/skills/engineering/setup-lineage
~/.claude/skills/wayfinder → /Users/roman/projects/skills-dev/skills/engineering/wayfinder
```
All three symlinks are installed and active (created 2026-09-20, per `ls -la`).

---

## 4. Other Skills Referencing These Names

**Blast radius** — skills that link to or mention `/prototype` and/or `setup-lineage`:

| Skill | File | Reference Type | Line(s) |
|-------|------|---|---|
| wayfinder | `skills/engineering/wayfinder/SKILL.md` | Path (`engineering/setup-lineage/SKILL.md`), slash command (`/prototype`) | 19, 71, 84 |
| critic | `skills/planning/critic/docs/critic-prompt.md` | Path (`engineering/setup-lineage/SKILL.md`) | 147 |
| FS-skill | `skills/requirements/FS-skill/SKILL.md` | Path (`engineering/setup-lineage/SKILL.md`) | 77 |
| SRS-skill | `skills/requirements/SRS-skill/SKILL.md` | Path (`engineering/setup-lineage/SKILL.md`) | 11 |
| data-view-skill | `skills/requirements/data-view-skill/SKILL.md` | Path (`engineering/setup-lineage/SKILL.md`) | 9 |

All links resolve correctly. No other skills invoke `prototype` or `setup-lineage` programmatically — they reference them as documentation anchors or user-invoked commands only.

---

## 5. Recommended Fix Options

### Option A: No action required (recommended)

The references are correct and intentional. The skills are:
- ✅ Installed and available for manual invocation (`/prototype`, `/setup-lineage`)
- ✅ Correctly documented in wayfinder (slash commands, not automatic invocation)
- ✅ Marked with `disable-model-invocation: true` by design (side-effect workflows)
- ✅ Reachable via path references from other skills' docs

**Tradeoff**: None — the system is working as designed.

### Option B: Add a clarification note to wayfinder SKILL.md

If future readers find it confusing that `wayfinder` cites skills Claude can't see, add a note:

```markdown
### About skill references in this documentation

This skill cites `/prototype` and `/setup-lineage`. Both are real skills, installed and available for your manual invocation. They carry `disable-model-invocation: true` because they open editors and create issues — workflows Claude should never trigger automatically. When you see a `/skillname` in wayfinder, run it yourself via that slash command; don't ask Claude to invoke it.
```

**Tradeoff**: Slight verbosity, but eliminates confusion if someone searches the repo for `prototype` and finds it only in disabled skills.

### Option C: Retarget to call-the-user-instead approach

Rewrite wayfinder's Prototype ticket type to say:

> Use the `/prototype` skill manually to raise the fidelity of the discussion by making a cheap, rough, concrete artifact to react to.

Instead of:

> …via the /prototype skill.

**Tradeoff**: Marginal improvement — the reference is already correct.

---

## Conclusion

No issue found. The references are accurate, the skills are installed, and their absence from the available-skills list is intentional (they are directive-only). The documentation is working correctly.

