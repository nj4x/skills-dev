# Deep-Module Lens (shared)

Shared pre-read, bounded-context rule, and deep-module detection scenarios used by review agents whose angle includes **Deep-Module Detection**: Step 4.1 Finder B (medium/high-effort fan-out), Step 4.1-RTM Agent 3 (mutating modes), and Step 4.9 (low-effort single-subagent brief). Each agent pre-reads these files, applies the bounded-context rule, and reports per the two scenarios below. The agent's own architecture/compliance bullets stay in its Finder/Agent prompt.

## Pre-read (before reviewing the diff)

1. Read `~/.claude/skills/improve-codebase-architecture/SKILL.md` — for the deep-module detection lens and deletion test.
2. Read `~/.claude/skills/codebase-design/SKILL.md` — for the canonical vocabulary: **module**, **interface**, **depth**, **seam**, **adapter**, **leverage**, **locality**. Use these terms exactly in all findings — not "component," "service," "API," or "boundary."
3. Read `~/.claude/skills/codebase-design/DEEPENING.md` — for dependency classification and seam discipline.

## Bounded context (before applying the deep-module lens)

- If PROJECT_MODULE_VIEW is set: for each changed file, identify its module boundary per the MODULE_VIEW document and read all source files in that module.
- Otherwise: for each changed file, read all source files in its parent directory (package-prefix fallback).
- READ-ONLY — do not walk the full codebase.

## Deep-Module Detection

Use vocabulary from the pre-read skill docs — apply to the diff only, never flag pre-existing debt the diff leaves untouched.

*Scenario 1 — Diff creates a new shallow module:*
Apply the deletion test to every new module introduced by the diff: would deleting it concentrate complexity back into callers (deep) or just move it (shallow)? If shallow → MAJOR.
Description format: `Module '<name>' is shallow (interface ≈ implementation complexity; deletion test: deleting it moves complexity rather than concentrating it). Deepening sketch: <one-line suggestion using codebase-design vocabulary>.`

*Scenario 2 — Diff deepens an existing module:*
If the diff reduces interface surface, introduces a seam, or pulls logic behind an interface:
- Deepening complete (interface genuinely simpler, implementation absorbs complexity) → POSITIVE.
  Description: `Module '<name>' deepened: interface surface reduced — good locality gain. (<vocabulary term> applied correctly.)`
- Deepening incomplete (seam still leaky, interface still cluttered) → MAJOR.
  Description: `Module '<name>' partially deepened but seam is still leaky: <what remains exposed>. To complete: <one-line sketch>.`
