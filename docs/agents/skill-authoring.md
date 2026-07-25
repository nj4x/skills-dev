# Skill authoring

How skills are structured, installed, and grouped in this workspace.

## The SKILL.md contract

A skill directory is centered on `SKILL.md`. Its YAML frontmatter defines the invoked `name`, the natural-language trigger `description`, an optional `argument-hint`, and whether it is directive-only (`disable-model-invocation: true`). Supporting scripts, templates, and references remain beside that contract.

## Installation (no build step)

Skills are installed by symlinking their directory into `~/.claude/skills/<name>`, so a `SKILL.md` edit takes effect immediately — there is no build step.

```sh
ln -s "$(pwd)/<category>/<skill>" ~/.claude/skills/<name>
```

The `publishing/html-view` skill also ships an `install.sh` for convenience.

## Categories

Category directories group related capabilities: **engineering**, requirements, planning, session, publishing, development, research, email, learning, and notifications.
