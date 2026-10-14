---
lineage-rules: exempt
---

# ADR-0078: Upstream Sync d81f3a1..49dd158 (2026-10)

**Status**: Approved  
**Date:** 2026-10-13  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet — retrofit tracked in ADR-0065)

## Context

skills-dev shares no git history with upstream `mattpocock/skills` (`/Users/roman/projects/skills`) and ports its changes by hand. The last sync stopped at upstream `d81f3a1` (skills-dev `0816eb5`, 2026-09-29). Upstream has 37 newer non-merge commits up to `49dd158` (2026-10-09). `docs/research/upstream-skills-assessment.md` classifies each change as port, adapt, or skip. Most changes are one-sentence guardrails or tracker-command fixes. One upstream change, omitting the `Blocked by` ticket section, conflicts with contracts recorded in `docs/agents/skill-dependencies.md`.

## Decision

1. **Port** these upstream changes, with their substance kept and wording adjusted to local convention:
   - `setup-skills` tracker seed docs: issue read via `gh issue view --json`, external-PR list via the REST pulls endpoint, `glab -O json`, `<child-iid>`, and a new "make a sub-issue" operation (`5b7cade`, `e0efb6e`, `cffab50`).
   - `setup-skills` Section B creates each configured triage label the tracker lacks (`5b7cade`).
   - `wizard/template.sh` replaced verbatim with upstream (`868c4cf`, `49dd158`, `c20facd`; `49dd158` alone fails the single-quote round-trip on bash 3.2).
   - `wayfinder`: four guardrails from `8295b8e`.
   - `diagnosing-bugs` (`f3fc563`), `tdd` (`3f59913`), `teach` (`ad5400b`): one-line additions.
2. **Adapt** these upstream ideas to local structure:
   - `dev/code-review` discovers the target repo's own standards files (`CODING_STANDARDS.md`, `CONTRIBUTING.md`, and similar) and hands them to Finder C and the low-effort pass. The bundled language standards remain the fallback (`3da8c01`).
   - `grilling`: each question is worded so "yes" accepts its recommendation; a bare "yes" to a multi-question round accepts every recommendation in it (`95249b0`).
   - `to-tickets`: when the source is an existing issue, each published ticket becomes its sub-issue, using the tracker doc's operation if present, else a `Part of #<parent>` line (`cffab50`).
   - `implement`: when passed a ticket reference, fetch it and state its title before the first edit (`6d6a5b9`).
3. **Keep** these local divergences:
   - The `Blocked by` section stays in every ticket body, even when native blocking edges exist. critic validates it, the local tracker uses it as the task graph, and it records edges a partial publish never created.
   - `resolving-merge-conflicts` stays, despite its upstream removal (`daa01d8`).
   - Cross-skill invocation stays as `/skill-name` and `Skill(name, args: …)`, not "call the Skill tool with …".
   - `diagnosing-bugs` keeps its hand-off to `/improve-codebase-architecture`.
4. **Skip** `chief-of-staff`, `ask-matt` (inspiration only), upstream governance scaffolding (`SCOPE.md`, `.out-of-scope/`, issue forms), and plugin/release tooling.
5. The `setup-skills` sub-issue operation and the `to-tickets` sub-issue step ship in the same change.

## Considered Options

- Port the `Blocked by` omission too: rejected. It breaks critic validation of the dependency graph and the local tracker's task graph (`docs/agents/skill-dependencies.md`).
- Add `chief-of-staff`: rejected. Upstream marks it experimental, and it overlaps `task-execution` and `goal-loop`.
- Make `to-tickets` require the sub-issue operation: rejected. Repos set up from the old seed lack it; the `Part of #<parent>` fallback keeps them working.

## Consequences

- Repos that run `/setup-skills` after this change get working tracker commands and pre-created triage labels. Repos set up earlier keep the old commands in their own `docs/agents/issue-tracker.md` until they rerun it.
- Generated wizards write `.env` values as `KEY='VALUE'` with mode 0600. A tool that reads `.env` as another user may lose access. Old unquoted env files still read correctly.
- code-review applies repo-documented standards, which closes the `retro` → `CODING_STANDARDS.md` → review loop.
- The next sync baseline is upstream `49dd158`, except the wizard template, which is pinned at `c20facd`.
