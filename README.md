# skills-dev

A collection of Claude Code skills for software engineering, requirements, planning, publishing, research, email, learning, notifications, and development workflows.

## Credits & Sources

This repository contains **20 original skills** and **26 adapted skills** from upstream open-source repositories:

- [mattpocock/skills](https://github.com/mattpocock/skills) — 18 adapted skills covering engineering, development, and learning workflows
- [davidondrej/skills](https://github.com/davidondrej/skills) — 8 adapted skills for research, session management, and planning

See [Borrowed Skills](#borrowed-skills) for the full attribution table with modification details.

## Installation

**Option 1: Manual symlink**

In Claude Code, tell the agent:

```
Hey please link all skills-dev skills to ~/.claude/skills.
```

The agent will symlink each skill directory to `~/.claude/skills/<name>` so they become available immediately.

**Option 2: Using `npx skills add`** ([vercel-labs/skills](https://github.com/vercel-labs/skills))

```bash
npx skills add https://github.com/nj4x/skills-dev.git
```

Prompt show, pick skills to install. Add `--skill '*' --yes` install all, no prompt. Default scope: project (`./.claude/skills/`); add `-g`/`--global` for `~/.claude/skills/`. Default install method: symlink; add `--copy` to copy files instead.

## Usage

**New repo — always start here:**
```
/setup-skills      # wire docs/agents/, .data/, issue tracker; run once per project
```

**Plan & design:**
```
/improve-codebase-architecture    # audit codebase architecture, find deepening opportunities
/critic                           # draft a plan and stress-test it with an adversarial critic
/repeat                           # drive any generate→review→refine loop
/goal-loop                        # run a plan to completion autonomously for /goal skill
```

**Requirements & specs:**
```
/FS-skill          # write EARS-format feature requirements
/SRS-skill         # turn FS requirements into a full SRS
/grill-with-docs   # architecture or design session from a file or plan
/to-spec           # synthesize the current conversation into a spec and publish it (grill-with-docs -> to-spec -> to-tickets -> implement)
/to-tickets        # break a spec into vertical-slice issues with blocking edges
/implement         # work the ticket frontier one slice at a time
```

**Implement & review:**
```
/code-review       # review committed changes (default) or working-tree diff
/continue          # pick up where you left off in a fresh session
```

**Session & publishing:**
```
/hs                # compact history summary (accepts N messages to look back)
/mark              # drop an anchor; /repeat with no args replays from it
/handoff           # full handoff doc for handing off to a fresh agent
/html-view         # render a plan, spec, or README as a shareable HTML file
```

**Dev & email:**
```
/skill-authoring        # create a new skill
/writing-for-agents     # write any document an agent consumes (skills, AGENTS.md, CLAUDE.md)
/prompt-authoring       # refine agent prompts and tool wiring
/inbox                  # triage email with category rules from prefs.json
/wait-what              # stop, re-pitch that — simpler, with the context I'm missing
```

## Configuration

### `~/.claude/CLAUDE.md`

Minimal — one universal instruction plus an `@RTK.md` include for token optimization:

```markdown
When reporting any information, be extremely concise and sacrifice grammar for sake of concision.

[Rust Token Killer](RTK.md) - Token-optimized CLI proxy
```

#### `~/.claude/RTK.md`

Loaded via `@RTK.md`. Documents the RTK (Rust Token Killer) CLI proxy: meta commands (`rtk gain`, `rtk discover`, `rtk proxy`), installation verification, and hook-based transparent rewriting of common commands (`git`, `grep`, `find`, etc.) for 60–90% token savings.

### `~/.claude/settings.json` (relevant segments)

**Status line** — displays model name, token count, and a context-window fill bar in the terminal:

```json
"statusLine": {
  "type": "command",
  "command": "~/.claude/statusline.sh"
}
```

`~/.claude/statusline.sh`:

```bash
#!/bin/bash
input=$(cat)
MODEL=$(echo "$input" | jq -r '.model.display_name')
PCT=$(echo "$input" | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)
TOKENS=$(echo "$input" | jq -r '.context_window.total_input_tokens // 0')
TOKENS_K=$(echo "$TOKENS" | awk '{printf "%dk", $1/1000}')

BAR_WIDTH=10
FILLED=$((PCT * BAR_WIDTH / 100))
EMPTY=$((BAR_WIDTH - FILLED))
BAR=""
[ "$FILLED" -gt 0 ] && printf -v FILL "%${FILLED}s" && BAR="${FILL// /▓}"
[ "$EMPTY" -gt 0 ] && printf -v PAD "%${EMPTY}s" && BAR="${BAR}${PAD// /░}"

echo "[$MODEL] ${TOKENS_K} $BAR $PCT%"
```

**Permissions** — runs in `auto` mode (no per-tool approval prompts) with interactive/UI tools blocked:

```json
"permissions": {
  "deny": [
    "ReadMcpResourceDirTool",
    "ReadMcpResourceTool",
    "EnterPlanMode",
    "ExitPlanMode",
    "DesignSync",
    "NotebookEdit",
    "SendMessage",
    "PushNotification",
    "RemoteTrigger",
    "ReportFindings",
    "ScheduleWakeup",
    "AskUserQuestion",
    "CronCreate",
    "CronDelete",
    "CronList"
  ],
  "defaultMode": "auto"
}
```

**Disable flags** — turns off bundled/built-in capabilities that overlap with or conflict with the custom skill set:

```json
"disableClaudeAiConnectors": true,
"disableBundledSkills": true,
"disableRemoteControl": true,
"disableWorkflows": true,
"disableArtifact": true
```

**Skill overrides** — disables specific built-in skills superseded by custom versions:

```json
"skillOverrides": {
  "claude-api": "off",
  "dataviz": "off",
  "keybindings-help": "off",
  "review": "off",
  "run": "off",
  "security-review": "off",
  "verify": "off"
}
```

### `~/.claude.json` — MCP server

Registers the local `mcp-vectors` server (requires Qdrant running at `localhost:6333` and an anthproxy instance at `localhost:8082` for entity extraction):

```json
"mcpServers": {
  "mcp-vectors": {
    "command": "uv",
    "args": [
      "run",
      "--directory",
      "path-to/skills-dev/mcp/mcp-vectors",
      "mcp-vectors"
    ],
    "env": {
      "LM_STUDIO_URL": "http://127.0.0.1:1235/v1",
      "QDRANT_URL": "http://localhost:6333",
      "CHUNK_SIZE": "1200",
      "CHUNK_OVERLAP": "150",
      "LLM_PROVIDER": "anthproxy",
      "ANTHPROXY_URL": "http://127.0.0.1:8082",
      "ANTHPROXY_MODEL": "haiku",
      "ENTITY_EXTRACTION": "true"
    }
  }
}
```

## Original Skills

The following 19 skills were created originally for this repository:

- **engineering**: `refactor-claude-md`, `resolving-merge-conflicts`
- **requirements**: `FS-skill`, `SRS-skill`, `data-view-skill`
- **planning**: `critic`, `repeat`, `goal-loop`
- **publishing**: `html-view`, `interview-style-doc-building`
- **research**: (none — all research skills are borrowed)
- **session**: `continue`, `hs`, `mark`
- **email**: `inbox`, `mail`
- **learning**: `grilling`
- **notifications**: `mute`
- **dev**: `prompt-authoring`, `skill-authoring`, `test-mcp`, `tool-authoring`
- **session**: (none — all session skills are borrowed)

## Borrowed Skills

The following 29 skills were adapted from upstream open-source skill repositories. Each entry notes the source, the upstream skill name, what was added or changed locally, and the approximate proportion of new content.

| Local Skill | Source Repo | Upstream Name | Key Modifications | % New Content |
|---|---|---|---|---|
| `codebase-design` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `codebase-design` | Verbatim adoption. | ~0% |
| `research` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `research` | Verbatim adoption. | ~0% |
| `tdd` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `tdd` | Added pointer to `/codebase-design` vocabulary. | ~2% |
| `writing-for-agents` (dev) | [mattpocock/skills](https://github.com/mattpocock/skills) | `writing-for-agents` | Adopted upstream replacement for `writing-great-skills`. Split skill mechanics into `SKILL-MECHANICS.md`; broadened scope to any agent-facing doc. | ~0% |
| `git-guardrails-claude-code` (dev) | [mattpocock/skills](https://github.com/mattpocock/skills) | `git-guardrails-claude-code` | Verbatim adoption. | ~0% |
| `improve-codebase-architecture` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `improve-codebase-architecture` | One-line tweaks only. | ~5% |
| `wayfinder` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `wayfinder` | Added requirements-lineage section and updated Grilling ticket-type wording. | ~10% |
| `diagnosing-bugs` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `diagnosing-bugs` | Minor wording edits. | ~5% |
| `prototype` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `prototype` | Updated LOGIC.md to shareable HTML (TUI → free-play buttons + guided walkthroughs); updated SKILL.md descriptions and run-instruction wording. | ~15% |
| `domain-modeling` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `domain-modeling` | Added upfront `CONTEXT.md` stub creation; sharpened the "term resolved" definition. | ~10% |
| `teach` (learning) | [mattpocock/skills](https://github.com/mattpocock/skills) | `teach` | Added "Be Very Concise" section; extracted the fluency/storage philosophy into a separate `PHILOSOPHY.md`. | ~20% |
| `setup-skills` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `setup-matt-pocock-skills` | Renamed skill; added `.data/requirements` and `.data/docs` folder handling and their propagation into `domain.md`. | ~15% |
| `to-spec` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `to-spec` | Condensed the spec template; added formal-requirements tracing (REQ-ID inline tags), `docs/agents/domain.md` and `.data/requirements/` wiring; added headless detection, staging with artifact-type frontmatter, critic invocation, and auto-publish on approval (ADR-0034/0035/0037/0039). | ~65% |
| `implement` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `implement` | Added isolated-subagent code-review flow, issue/spec status transitions, and requirement-ID propagation into commits/PRs (doubled in size). | ~50% |
| `grilling` (learning) | [mattpocock/skills](https://github.com/mattpocock/skills) | `grilling` | Adopted upstream round-based frontier methodology with `❓ **Q1**` question format and sub-agent fact-finding; kept local ADR-capture phase and automatic post-grilling `/critic` review handoff. | ~65% |
| `grill-with-docs` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `grill-with-docs` | Delegates to `/grilling`; added ADR collection and `/critic` audit flow. | ~60% |
| `to-tickets` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `to-tickets` | Heavily condensed and rewritten; added requirements-tracing (`Requirements:` field), local-file tracker path, `/implement` frontier guidance; added headless detection, staging with artifact-type frontmatter, manifest, critic invocation, and auto-publish on approval (ADR-0034/0037/0039/0040). | ~75% |
| `wizard` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `wizard` | Verbatim adoption. | ~0% |
| `triage` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `triage` | Renamed `/setup-matt-pocock-skills` reference to `/setup-skills`; added mcp-vectors search guidance; switched Skill-tool invocation phrasing to local `/grilling` `/domain-modeling` convention. | ~5% |
| `to-questionnaire` (publishing) | [mattpocock/skills](https://github.com/mattpocock/skills) | `to-questionnaire` | Verbatim adoption. | ~0% |
| `pi-web-search` (research) | [davidondrej/skills](https://github.com/davidondrej/skills) | `pi-web-search` | Verbatim adoption. | ~0% |
| `research-prompt` (research) | [davidondrej/skills](https://github.com/davidondrej/skills) | `research-prompt` | Verbatim adoption. | ~0% |
| `short` (session) | [davidondrej/skills](https://github.com/davidondrej/skills) | `short` | Verbatim adoption. | ~0% |
| `youtube-transcript` (research) | [davidondrej/skills](https://github.com/davidondrej/skills) | `youtube-transcript` | Minor wording edits. | ~5% |
| `handoff` (session) | [davidondrej/skills](https://github.com/davidondrej/skills) | `handoff` | Near-verbatim; added a "Suggested Skills" section; removed `disable-model-invocation`. | ~10% |
| `wait-what` (session) | [mattpocock/skills](https://github.com/mattpocock/skills) | `wait-what` | Verbatim adoption. | ~0% |
| `browser-harness` (research) | [davidondrej/skills](https://github.com/davidondrej/skills) | `browser-harness` | Trimmed the Hermes-specific integration and authenticated-extraction sections. | ~5% |
| `deep-research` (research) | [davidondrej/skills](https://github.com/davidondrej/skills) | `deep-research` | Light trimming / condensation. | ~10% |
| `goal-loop` (planning) | [davidondrej/skills](https://github.com/davidondrej/skills) | `goal-loop` | Added `disable-model-invocation`; expanded the 4,000-char contract-limit guidance with compression rules. | ~15% |
| `setup-help` (notifications) | [davidondrej/skills](https://github.com/davidondrej/skills) | `setup-help` | Condensed description and remaining-steps guidance. | ~5% |
| `deepapi` (research) | [davidondrej/skills](https://github.com/davidondrej/skills) | `deepapi` | Reduced to roughly one-quarter of upstream size; rewrote the description and pinned a different version hash. | ~5% |

> **% New Content** is the estimated share of the local skill's content that does not appear in the upstream source — i.e. lines added, rewritten, or restructured locally divided by total local line count. ~0% means verbatim or near-verbatim; higher values indicate progressively heavier local authorship.

Skills not listed above are original to this repository.

### Sources

- [mattpocock/skills](https://github.com/mattpocock/skills) — Matt Pocock's engineering and productivity skill collection (spec/ticket workflows, TDD, codebase design, grilling, teaching). Primary upstream for the `engineering/` category.
- [davidondrej/skills](https://github.com/davidondrej/skills) — David Ondrej's agent-orchestration, research/web, and ops skills. Primary upstream for the `research/research-and-web/` category plus several session/planning skills.
