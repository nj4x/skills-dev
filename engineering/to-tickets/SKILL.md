---
name: to-tickets
description: Use when the user wants to create issues, tickets, or vertical slices from a plan, spec, or conversation. Publishes tracer-bullet slices with blocking edges to the configured tracker.
---

The issue tracker and triage label vocabulary should have been provided to you — run `/setup-skills` if not.

## Process

### 1. Gather context
Work from whatever is in the conversation. Fetch referenced specs or issue numbers in full. If `.data/requirements/` exists, read any relevant requirements docs for context. Track which requirement IDs each ticket will satisfy — inline `(ID)` tags in the source spec map straight onto the ticket's `Requirements:` field.

### 2. Explore the codebase (optional)
If not already done, explore to understand current state. Read `docs/agents/domain.md` for the domain doc layout. Use domain glossary vocabulary, respect ADRs. Look for prefactor opportunities. Search source code conceptually and cross-file; search docs and requirements as a document corpus; for architecture-level questions start with a global search before reading individual files.

### 3. Draft vertical slices

Rules: each slice cuts a narrow but COMPLETE path through every layer (schema, API, UI, tests); a completed slice is demoable; each slice fits in a single fresh context window; prefactoring goes first.

Give each ticket blocking edges. Wide refactors are the exception — use expand–contract sequencing (expand, migrate batches, contract).

### 4. Quiz the user

Present as numbered list (title, blocked-by, what it delivers). Iterate on granularity and edges until approved.

**Headless detection:** check whether the `AskUserQuestion` tool is available. If absent, the skill is running headless (invoked by another agent). Skip the quiz and draw slice granularity and blocking-edge decisions from the conversation or task context. **Shaping-context validation:** before skipping, confirm the context contains explicit slice and edge decisions; if none are found, stop with: "headless mode requires pre-shaped context with slice/edge decisions — provide them in the task description and re-invoke."

### 5. Stage the draft

**Derive the feature slug.** Slugify the conversation's feature name — lowercase, non-alphanumeric → `-`, trimmed. Headless fallback: `<CLAUDE_CODE_SESSION_ID>-<unix-timestamp>`. The slug lives in memory for this run.

**Staging-collision behaviour:** if `.scratch/<feature-slug>/draft-issues/` already exists, overwrite the draft files — a re-run is a fresh draft start. Clear any `dirty` marker at `.scratch/<feature-slug>/dirty` left by a prior failed critic run. If `.scratch/<feature-slug>/issues/` already exists (published tickets are present), stop with: "already published — delete `.scratch/<feature-slug>/issues/` to republish."

Write ticket draft files to `.scratch/<feature-slug>/draft-issues/<NN>-<slug>.md`, one per ticket, numbered in dependency order. Then write the manifest at `.scratch/<feature-slug>/manifest.md`. The manifest **must** begin with this YAML frontmatter block (required for critic's artifact-type detection):

```
---
artifact-type: tickets
---
```

The manifest body (after the closing `---`) lists the draft ticket file paths, one per line, in dependency order. Example:

```
---
artifact-type: tickets
---
.scratch/<feature-slug>/draft-issues/01-add-schema.md
.scratch/<feature-slug>/draft-issues/02-api-endpoint.md
.scratch/<feature-slug>/draft-issues/03-ui-component.md
```

Use the `<local-ticket-template>` for each ticket file:

```
# <NN> — <Title>

## What to build
<description>

## Requirements
<requirement IDs, or omit if none>

## Blocked by
<NN> — <slug>, or none

## Status
ready-for-agent

## Checklist
- [ ] ...
```

**Zero-slice guard:** if the ticket list is empty, stop — there is nothing to stage or publish.

**Verify manifest frontmatter:** confirm `.scratch/<feature-slug>/manifest.md`, after stripping any leading BOM or whitespace, begins with the `artifact-type: tickets` frontmatter block. If not, stop with: "manifest.md is missing the required `artifact-type: tickets` frontmatter — re-write the manifest with the frontmatter block and re-invoke."

### 6. Run the critic loop

```
Skill(critic, args: "pickup:.scratch/<feature-slug>/manifest.md 3 auto")
```

Critic detects `artifact-type: tickets` from the manifest frontmatter, selects the 4-group review roster (A — Completeness, B — Consistency, C — Robustness, D — Slice Boundaries), and runs up to 3 review iterations (at most 2 automatic revisions). During revisions the synthesizer edits ticket files and the manifest in place, maintaining the `Blocked by` graph and post-edit validation (acyclicity, manifest↔files consistency). On approval, critic prints the sentinel `PLAN_APPROVED_READY_FOR_FINALIZATION: <path>` and returns control here.

### 7. Route on outcome

**Approved** (critic printed the sentinel, `auto_approval` true): publish.

- **Local tracker:** for each path listed in the manifest, promote `draft-issues/<NN>-<slug>.md` → `issues/<NN>-<slug>.md`, apply `ready-for-agent`. After all promotions succeed, remove the `draft-issues/` directory. On partial promotion failure (permission error, disk full), stop and report which files were promoted and which remain in `draft-issues/`; do not remove `draft-issues/` until all promotions succeed.
- **Real tracker (GitHub, Linear, …):** publish in two passes — first create all issues in manifest dependency order (recording each slug → tracker ID), then create native blocking links resolving `Blocked by` slugs to tracker IDs. On partial failure in either pass, stop and report created issues (slug → ID), uncreated issues, and dangling edges. In headless mode write the report to `.scratch/<feature-slug>/publish-report.md`. Do not roll back created issues. See ADR-0041 for the deferred resume / idempotency-by-slug subsystem.

**Not approved** (revise-at-cap, unresolved major issues, hard-abort — no sentinel from critic): leave the drafts staged under `.scratch/<feature-slug>/draft-issues/` and `manifest.md`.
- **Interactive mode:** show the staged tickets and the unresolved critic issues, then offer **revise / publish anyway / abandon**.
- **Headless mode:** write a summary of the unresolved issues to `.scratch/<feature-slug>/critic-review.md` and stop. Do not auto-publish; headless publishing occurs only on genuine critic approval.

Work the frontier one ticket at a time with `/implement`, clearing context between tickets.
