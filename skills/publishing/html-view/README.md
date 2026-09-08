# html-view

A Claude Code skill that turns a plan, spec, design doc, markdown file, or sufficiently rich conversation context into a **self-contained HTML artifact**.

It supports four output shapes:

- **editorial** — long-form readable documents
- **technical-doc** — specs, API docs, and reference pages
- **dashboard** — comparison-heavy docs with cards/tables
- **slide-deck** — fullscreen slide-style presentations

> This directory contains the **skill definition and installer**, not a standalone renderer implementation. Claude performs the rendering by following `SKILL.md`.

## What the skill does

- Picks the best available source:
  - explicit file path passed to `/html-view`
  - `@`-referenced file in the latest user message
  - the most recent plan file when the user says “the plan”
  - recent conversation context as a last resort
- Writes a single `.html` file next to the source document, or under `~/.claude/plans/` for conversation-only renders
- Produces semantic, mobile-friendly HTML with inline CSS
- Includes in-page navigation, print styling, and a footer with provenance
- Uses inline SVG diagrams by default; Mermaid via CDN is allowed when the source benefits from it
- Auto-opens the generated file after writing it when possible

## Typical triggers

Use this skill when the user:

- runs `/html-view`
- asks to **render/export/share something as HTML**
- asks for a **web version** of a plan, spec, or design doc
- asks to **present something as slides / a deck / a slideshow**
- asks for a markdown artifact to become something more scannable or presentable

Examples:

- `/html-view`
- `/html-view ./docs/api-design.md`
- “Make this an HTML page.”
- “Render the SRS as a shareable HTML doc.”
- “Turn this into a slide deck.”

## Repository contents

```text
html-view/
├── .claude-plugin/plugin.json   Plugin manifest and skill metadata
├── install.sh                   Installs the skill into ~/.claude/skills/html-view
└── SKILL.md                     Canonical skill instructions
```

## Installation

### Global install

Makes `/html-view` available in new Claude Code sessions.

```sh
cd /path/to/skills-dev/html-view
chmod +x install.sh   # if the exec bit was not preserved
./install.sh
```

Uninstall:

```sh
rm ~/.claude/skills/html-view
```

### Per-project plugin

Add this directory to the project's `.claude/settings.json`:

```json
{
  "pluginDirectories": ["/path/to/skills-dev/html-view"]
}
```

### One-off dev session

```sh
claude --plugin-dir /path/to/skills-dev/html-view
```

## Notes

- The generated output is intended to be **one shareable HTML file**.
- The skill prefers writing HTML directly instead of routing markdown through a rendering library.
- External runtime dependencies are avoided except where the skill explicitly allows them (for example, optional Mermaid CDN usage for certain diagrams).
- The authoritative behavior lives in [`SKILL.md`](./SKILL.md); update that first when changing how the skill should behave.
