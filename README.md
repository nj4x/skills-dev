# skills-dev

A collection of Claude Code skills for software engineering, requirements, planning, publishing, research, email, learning, notifications, and development workflows.

## Credits & Sources

This repository contains **20 original skills** and **26 adapted skills** from upstream open-source repositories:

- [mattpocock/skills](https://github.com/mattpocock/skills) — 18 adapted skills covering engineering, development, and learning workflows
- [davidondrej/skills](https://github.com/davidondrej/skills) — 8 adapted skills for research, session management, and planning

See [Borrowed Skills](#borrowed-skills) for the full attribution table with modification details.

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
/skill-authoring        # create or refine a skill
/writing-great-skills   # audit skill quality across the repo
/prompt-authoring       # refine agent prompts and tool wiring
/inbox                  # triage email with category rules from prefs.json
```

## Configuration

### `~/.claude/CLAUDE.md`

The root is minimal — one universal instruction plus `@import` pointers to intent-grouped satellite files in `~/.claude/docs/agents/`.

```markdown
When reporting information to me, be extremely concise and sacrifice grammar for sake of concision.

## Code Review

Scope defaults, branch handling, and the autonomous fix-and-commit workflow for reviews.
@docs/agents/code-review.md

## Task Execution, Planning & Research

Deliver-first discipline, multi-phase fan-out, and autonomous-loop behavior.
@docs/agents/task-execution.md

## Search Strategy

When to use fd/rg vs mcp-vectors, the tool reference table, entity-graph pre-conditions, and worktree safety.
@docs/agents/search-strategy.md

## Testing, Committing & Logging

Test-suite/lint discipline, commit staging, real test data and dependency wiring (app-level factories), and file-only logging.
@docs/agents/testing.md

## Token Optimization

The RTK token-killer CLI proxy command reference.
@RTK.md
```

#### `~/.claude/docs/agents/code-review.md`

```markdown
# Code Review Workflow

Scope defaults, branch handling, and autonomous fix implementation for code reviews.

Code reviews default to **committed** scope, not the working tree. Confirm scope (committed vs working-tree) before starting and pass `--scope` explicitly.

On non-`main` branches, proceed directly to review. On `main`: if `--scope` is committed, automatically check out a feature branch first, then proceed; if `--scope` is working-tree, review the uncommitted changes in the current branch — say so immediately rather than halting silently mid-review.

Identify all Major and Critical findings, then autonomously: (1) implement every fix, (2) write regression tests for each, (3) run the full test suite, (4) if any test fails, debug and re-run until 100% pass, (5) commit with a structured summary listing each finding and its fix. Only stop to ask if a fix requires a genuine product decision; otherwise resolve ambiguity by reading the codebase and specs.

When the user asks to merge after code review, merge the working branch into main.
```

#### `~/.claude/docs/agents/task-execution.md`

```markdown
# Task Execution, Planning & Research

Deliver-first discipline for plans/research, multi-phase fan-out, and autonomous-loop behavior.

## Delivering plans and research

Deliver plan or research text first; wait for user approval before reading files or making edits.

## Fan-out execution

Fan out any multi-file or multi-phase task into independent sub-phases, each to a separate sub-agent, instructed to implement its module, write and pass its own tests, and avoid touching shared files. After all agents report back, run a reconciliation pass — check entity fields, event counts, and API signatures are consistent across every module, fix any mismatches in lockstep, run the full suite, and commit only when all tests pass with zero regressions.

## Autonomous loops

When the user requests an autonomous loop (debug, fix-and-verify, requirements-to-SRS sync), proceed without pausing for manual approval and persist intermediate research/findings to disk as you go.
```

#### `~/.claude/docs/agents/search-strategy.md`

```markdown
# Search Strategy

Choosing between fd/rg and mcp-vectors, the tool reference table, entity-graph pre-conditions, and worktree safety.

For exact, single-site lookups (known symbol, literal, filename): `fd`/`rg`/`Read`. For a *blast-radius question* on a known symbol (who calls it, what it touches, inheritance): `get_entity_callers` / `get_entity_neighbors` — prefer these over grepping for usages, since the graph resolves aliased imports and cross-file edges that `rg` misses. For conceptual, cross-file, or architecture-level retrieval: the mcp-vectors tools below.

| Tool | Use for |
|---|---|
| `search_code` | Conceptual or cross-file code retrieval. |
| `search_documents` | Non-code documentation, configuration, and requirements retrieval. |
| `search_entities` | A named or partially known entity. |
| `get_entity_neighbors` | Graph connections from a known entity. |
| `get_entity_callers` | Callers of a known entity. |
| `search_global` | Architecture-level questions; prefer when persisted community reports exist. Falls back to vector search if reports are missing or dirty. |

**Entity-graph tools** (`search_entities`, `get_entity_neighbors`, `get_entity_callers`) are cheap single calls — use them inline. Run `search_global` via Explore or general-purpose sub-agents, in parallel with applicable `fd` or `rg` searches.

## Task-shaped triggers for the entity graph

- Before changing a function/class signature or renaming: `get_entity_callers` first.
- During code review, for each modified public entity: check blast radius via `get_entity_callers`.
- When asked "how does X relate to / affect Y" or tracing a dependency chain: `get_entity_neighbors` (depth 2) before reading files.
- When planning multi-file work: start with `search_entities` on the central concepts to get the file map.

Assume the entity graph exists for indexed roots and just try the call — a failed call costs one tool call. If the target root is not indexed, fall back to `rg` and `fd`; offer indexing when the search is substantial.

For worktree paths, use filesystem tools directly; restrict `mcp-vectors` to the canonical repository root.
```

#### `~/.claude/docs/agents/testing.md`

```markdown
# Testing, Committing & Logging

Test-suite discipline, commit staging, test data conventions, and logging defaults.

Always run the full test suite AND lint after code changes, then commit/push when the user requests it.

When committing, run `git status` first and stage ALL changes — modified files alongside renames and new files — before creating the commit.

Never invent test IDs or fake production-context stubs/adapters. Use real implementations and real requirement IDs; when wiring dependencies, use the app-level factory interface (e.g. DataProviderFactory) rather than concrete providers.

Logging should be file-only (no console output) unless explicitly requested otherwise.
```

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
      "LM_STUDIO_URL": "http://127.0.0.1:1234/v1",
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
- **learning**: (none — all learning skills are borrowed)
- **notifications**: `mute`
- **dev**: `prompt-authoring`, `skill-authoring`, `test-mcp`, `tool-authoring`

## Borrowed Skills

The following 26 skills were adapted from upstream open-source skill repositories. Each entry notes the source, the upstream skill name, what was added or changed locally, and the approximate proportion of new content.

| Local Skill | Source Repo | Upstream Name | Key Modifications | % New Content |
|---|---|---|---|---|
| `codebase-design` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `codebase-design` | Verbatim adoption. | ~0% |
| `research` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `research` | Verbatim adoption. | ~0% |
| `tdd` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `tdd` | Verbatim adoption. | ~0% |
| `writing-great-skills` (dev) | [mattpocock/skills](https://github.com/mattpocock/skills) | `writing-great-skills` | Verbatim adoption. | ~0% |
| `git-guardrails-claude-code` (dev) | [mattpocock/skills](https://github.com/mattpocock/skills) | `git-guardrails-claude-code` | Verbatim adoption. | ~0% |
| `improve-codebase-architecture` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `improve-codebase-architecture` | One-line tweaks only. | ~5% |
| `wayfinder` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `wayfinder` | One-line tweaks only. | ~5% |
| `diagnosing-bugs` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `diagnosing-bugs` | Minor wording edits. | ~5% |
| `prototype` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `prototype` | Minor wording edits. | ~5% |
| `domain-modeling` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `domain-modeling` | Added upfront `CONTEXT.md` stub creation; sharpened the "term resolved" definition. | ~10% |
| `teach` (learning) | [mattpocock/skills](https://github.com/mattpocock/skills) | `teach` | Added "Be Very Concise" section; extracted the fluency/storage philosophy into a separate `PHILOSOPHY.md`. | ~20% |
| `setup-skills` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `setup-matt-pocock-skills` | Renamed skill; added `.data/requirements` and `.data/docs` folder handling and their propagation into `domain.md`. | ~15% |
| `to-spec` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `to-spec` | Condensed the spec template; added formal-requirements tracing (REQ-ID inline tags), `docs/agents/domain.md` and `.data/requirements/` wiring; added headless detection, staging with artifact-type frontmatter, critic invocation, and auto-publish on approval (ADR-0034/0035/0037/0039). | ~65% |
| `implement` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `implement` | Added isolated-subagent code-review flow, issue/spec status transitions, and requirement-ID propagation into commits/PRs (doubled in size). | ~50% |
| `grilling` (learning) | [mattpocock/skills](https://github.com/mattpocock/skills) | `grilling` | Added ADR-capture phase and an automatic post-grilling `/critic` review handoff (manifest + verdict). | ~55% |
| `grill-with-docs` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `grill-with-docs` | Delegates to `/grilling`; added ADR collection and `/critic` audit flow. | ~60% |
| `to-tickets` (engineering) | [mattpocock/skills](https://github.com/mattpocock/skills) | `to-tickets` | Heavily condensed and rewritten; added requirements-tracing (`Requirements:` field), local-file tracker path, `/implement` frontier guidance; added headless detection, staging with artifact-type frontmatter, manifest, critic invocation, and auto-publish on approval (ADR-0034/0037/0039/0040). | ~75% |
| `pi-web-search` (research) | [davidondrej/skills](https://github.com/davidondrej/skills) | `pi-web-search` | Verbatim adoption. | ~0% |
| `research-prompt` (research) | [davidondrej/skills](https://github.com/davidondrej/skills) | `research-prompt` | Verbatim adoption. | ~0% |
| `short` (session) | [davidondrej/skills](https://github.com/davidondrej/skills) | `short` | Verbatim adoption. | ~0% |
| `youtube-transcript` (research) | [davidondrej/skills](https://github.com/davidondrej/skills) | `youtube-transcript` | Minor wording edits. | ~5% |
| `handoff` (session) | [davidondrej/skills](https://github.com/davidondrej/skills) | `handoff` | Near-verbatim; added a "Suggested Skills" section; removed `disable-model-invocation`. | ~10% |
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
