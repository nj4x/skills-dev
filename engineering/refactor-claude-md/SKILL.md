---
name: refactor-claude-md
description: Refactor a CLAUDE.md file to follow progressive disclosure principles — minimal root with intent-grouped satellite files, grounded in the actual codebase. Use when a CLAUDE.md has grown bloated, become internally inconsistent, or drifted out of sync with the code.
argument-hint: "[path/to/CLAUDE.md]"
disable-model-invocation: true
---

# Refactor CLAUDE.md for Progressive Disclosure

Refactor a CLAUDE.md file into a **minimal root** (only truly universal instructions) plus **intent-grouped satellite files** linked via `@import`. Ground every instruction against the actual codebase before refactoring. Run autonomously, stopping only at two decision gates: contradiction resolution (Gate 1) and redundancy/staleness confirmation (Gate 2).

## Parallelism

Three fan-out points reduce wall-clock time:

1. **Steps 1b ∥ 2** — Codebase grounding and contradiction detection are independent; start both immediately after Step 1 completes.
2. **Step 1b internal** — Each instruction's claim verification is independent; fan out per-instruction.
3. **Step 8 satellite writes** — All satellite files are independent; write them in parallel, then write the root.

Sequential gates: Gate 1 must close before Steps 3–4; Gate 2 must close before Step 6; Steps 7–8 must complete before Step 10.

## Step 0 — Resolve the target file

If an argument was supplied, use it as the target path. Otherwise default to the nearest `CLAUDE.md` in the current project root (`.`). If no file is found at the resolved path, stop with a clear error: `No CLAUDE.md found at <path>.`

Edge cases to check before proceeding:

- **Malformed file** (binary content, truncated, unreadable): stop and report the parse error.
- **Thin file** (fewer than 10 distinct instructions): warn the user ("This CLAUDE.md has only N instructions; refactoring may not yield much value") then proceed.
- **Already-refactored** (root is < 10 lines and already has `@import` lines): note in the summary report; still check for contradictions and staleness.

## Step 1 — Extract all instructions

Parse the file into a flat numbered list (I-001, I-002, …). Each instruction is one atomic directive — a bullet, a paragraph, or a heading+body block. When in doubt, keep a block together.

## Step 1b — Codebase grounding (autonomous, fan out per-instruction)

For each instruction, extract **verifiable claims** and check them:

| Claim type | Examples | How to verify |
|---|---|---|
| File path | `src/server.py`, `docs/agents/` | `fd` |
| Shell command | `uv run pytest`, `npm test` | `package.json`, `Makefile`, `pyproject.toml` |
| Symbol / entity | function `build_index`, class `RAGPipeline` | `rg` |
| Tool / library | "use ripgrep", "prefer uv over pip" | imports, lockfiles, config |
| Convention claim | "we use intent-driven grouping", "no mocks" | `rg` for counter-examples |

Classify each claim:

- **Verified** — matches reality.
- **Stale** — provably wrong or outdated (path missing, symbol renamed, command absent from build files, convention contradicted by the majority of the codebase).
- **Unverifiable** — abstract advice; skip.

An instruction with any stale claim is **stale**. Tag it for Gate 2; grounding ends here.

**Enrichment:** When a verified instruction would be more actionable with a specific name or path found during grounding (e.g., "use the factory interface" → "use `DataProviderFactory`"), update the instruction text. Enrich only when the referent is unambiguous; leave precise instructions alone.

## Step 2 — GATE 1: Contradiction detection (autonomous, fan out with Step 1b)

Feed the full instruction list to the model: *"Which pairs of instructions could cause an agent to make conflicting decisions? List each pair and explain the conflict."*

Zero contradictions found: log "No contradictions detected" and close the gate.

Contradictions found: for each conflicting pair, stop and ask the user:

1. Show both instructions side-by-side with the model's explanation of the conflict.
2. Ask: "Which do you want to keep?" (A / B / both / neither)
3. Ask: "Why?" — captures the reasoning.

Update the instruction list after each resolution. All contradictions must be resolved before this gate closes.

Fallback: if the model fails to produce a structured list, fall back to keyword-overlap heuristics (flag pairs sharing >3 content words that express different directives). Still gate on user confirmation.

## Steps 3–4 — Essentials extraction and intent grouping (autonomous, single LLM pass)

Feed the post-Gate-1 instruction list to the model in one pass:

*"For each instruction: (1) Is it universal — applies to more than half of all tasks, or is a foundational constraint? If yes: ESSENTIAL. If no: (2) Which intent category does it belong to? Use kebab-case intent names (testing, git-workflow, code-review, logging, search-strategy, or a new intent-driven name). Artifact names like python or typescript are not valid categories."*

Classification outputs:
- **Essential** — stays in root CLAUDE.md
- **Specific → category** — moves to `docs/agents/<category>.md`

Merge any category with fewer than 2 instructions into the closest existing category.

This step is fully autonomous; the user sees the result in the refactored output.

## Step 5 — GATE 2: Redundancy and staleness confirmation

Collect two sets:

**Set A — Stale (from Step 1b):** Instructions tagged stale. For each: show the claim, the evidence, and ask "Delete, rewrite to match the current code, or keep as-is?"

**Set B — Redundant (LLM pass):** Feed all remaining instructions to the model: *"Which are: redundant (the agent already knows this), too vague to be actionable, or obviously true? For each, explain why."* Exclude instructions already in Set A.

Both sets empty: log "No redundant or stale instructions detected" and close the gate.

Either set non-empty: present in two labeled sections. For stale instructions the user chooses to rewrite, update the text to match the verified codebase state before continuing.

All instructions flagged: stop and ask explicitly before proceeding.

Apply confirmed deletions and rewrites, then close the gate.

## Step 6 — Build the disposition map

Build and update this map throughout Steps 3–5 as each classification is made. It is the source of truth for critic's over-deletion audit.

| ID | Summary | Grounding | Disposition | Destination |
|----|---------|-----------|-------------|-------------|
| I-001 | … | verified | essential | root CLAUDE.md |
| I-002 | … | unverifiable | moved | docs/agents/testing.md |
| I-003 | … | stale | deleted | (stale — path not found) |
| I-004 | … | stale | rewritten | docs/agents/testing.md |
| I-005 | … | verified | deleted | (redundant — stated reason) |

Write the completed map to `<source-dir>/docs/agents/disposition-<timestamp>.md`.

## Step 7 — Backup existing output

Before any writes, take a timestamped backup:

- `<source-dir>/CLAUDE.md` → `<source-dir>/CLAUDE.md.bak-<timestamp>` (only if it exists and differs from the source)
- `<source-dir>/docs/agents/` → `<source-dir>/docs/agents.bak-<timestamp>/` (only if the directory exists)

Record backup paths in the summary report. Backups accumulate; the report reminds users to prune old `.bak-*` paths.

## Step 8 — Write output files (satellite writes parallelizable)

Output location mirrors the source file:

- `~/.claude/CLAUDE.md` → satellites to `~/.claude/docs/agents/`
- `<project>/CLAUDE.md` → satellites to `<project>/docs/agents/`
- `<project>/sub/CLAUDE.md` → satellites to `<project>/sub/docs/agents/`

Write in order:

1. **Satellite files** (parallel) — `<source-dir>/docs/agents/<category>.md`, one per category, with a one-line summary at the top.
2. **Root CLAUDE.md** (sequential, after satellites) — essentials only, with one `@import <relative-path>` line per satellite preceded by a one-line summary of its scope.

Verification: every satellite must have a corresponding `@import` in the root. A satellite with no inbound import is an error — fix before continuing.

Re-runs overwrite silently (Step 7 makes this recoverable). Edit the source CLAUDE.md and re-run — generated files are overwritten each run.

## Step 9 — Summary report

**Essentials kept in root (N)**
- Bullet list of instruction summaries

**Satellites created (N)**
- `docs/agents/testing.md` — 4 instructions
- `docs/agents/git-workflow.md` — 2 instructions
- …

**Stale instructions fixed (N)**
- I-003: `src/old-path.py` — path not found; deleted
- I-004: `build.sh` → `uv run pytest` — updated to match pyproject.toml

**Instructions deleted as redundant (N)**
- Each with the rationale confirmed at Gate 2

**Output paths**
- Root: `<path>`
- Satellites: `<dir>`
- Disposition map: `<path>`
- Backups: `<paths>` (prune when no longer needed)

## Step 10 — Critic review

Write a manifest file to `plans/refactor-claude-md-review.md` with this preamble and a markdown list of file paths:

```
Critic's job is to assess whether the refactored structure is correct — right essentials, right categories, no valuable content lost. Use the original and disposition map to verify that deleted content was genuinely redundant and that moved content landed in the right category.

- <rewritten root CLAUDE.md>
- <each satellite file>
- <pre-refactor backup from Step 7>
- <disposition map from Step 6>
```

Then invoke `/critic pickup:plans/refactor-claude-md-review.md`, passing the manifest path explicitly so critic can locate it without relying on plan-mode context.

If critic flags content the user approved for deletion at Gate 2, surface the conflict and ask: re-run against an edited source, or accept the deletion?
