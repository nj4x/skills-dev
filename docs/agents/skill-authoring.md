# Skill authoring

How skills are structured, installed, and grouped in this workspace.

## The SKILL.md contract

A skill directory is centered on `SKILL.md`. Its YAML frontmatter defines the invoked `name`, the natural-language trigger `description`, an optional `argument-hint`, and whether it is directive-only (`disable-model-invocation: true`). An optional `version` field can track a load-bearing semantic for self-update or self-reference flows (e.g., `deepapi` uses it to track API contract versions). Supporting scripts, templates, and references remain beside that contract.

## Installation (no build step)

Skills are installed by symlinking their directory into `~/.claude/skills/<name>`, so a `SKILL.md` edit takes effect immediately — there is no build step.

```sh
ln -s "$(pwd)/<category>/<skill>" ~/.claude/skills/<name>
```

The `publishing/html-view` skill also ships an `install.sh` for convenience.

## Categories

Category directories group related capabilities: **engineering**, requirements, planning, session, publishing, development, research, email, learning, and notifications.

## Decisions rejected from upstream (`mattpocock/skills`)

This repo periodically cherry-picks from upstream (see `docs/research/upstream-skills-sync-2026-08-20.md`). Some upstream directions were considered and explicitly rejected — recorded here so a future sync doesn't reopen them.

- **Harness-neutral subagent dispatch** (upstream `14bfbbd`/`c0d6901`). Upstream stripped references to the `Agent` tool and `subagent_type` (e.g. `general-purpose`, `Explore`) so its skills work on non-Claude-Code harnesses like Codex. This repo is Claude-Code-only — commit `7426dc8` went the opposite way, adding explicit `subagent_type` declarations across 7 skills. Keep them.
- **Cross-skill invocation policy** (upstream `1dab982`, reversing its earlier `call the Skill tool with "name"` convergence in `fcf0071`). Upstream now forbids a skill from invoking a user-invoked (`disable-model-invocation: true`) skill; it must tell the user to run the slash command instead. This repo's `to-spec`, `to-tickets`, and `grilling` depend on programmatic hand-offs — `Skill(critic, args: "pickup:...")` and `Skill("code-review")` — so that restriction is unworkable here. Keep the existing local convention: prose references use `` /skill-name `` (e.g. "run the `/grilling` skill"); hand-offs that need to pass arguments or resume state use `Skill(name, args: ...)` literally.
- **Em-dash removal** (upstream `3216582`). Upstream rewrote all em-dashes to colons/commas/sentence breaks repo-wide and added a steering rule against them. This repo keeps em-dashes — the style is established and pervasive, and rewriting ~56+ files for a cosmetic convention isn't worth it. Consequence: future upstream diffs must filter em-dash-only changes (`diff | grep -v '—'` or equivalent) to see substantive deltas.
- **`diagnosing-bugs` Phase 6 hand-off removal** (upstream `1dab982`). Upstream deleted the "what would have prevented this bug?" hand-off to `improve-codebase-architecture` and retitled Phase 6 from "Cleanup + post-mortem" to "Cleanup". This repo keeps the hand-off — it's a useful automatic bridge between the two skills and costs nothing to retain.
