---
name: to-spec
description: Turn the current conversation into a spec and publish it to the project issue tracker — no interview, just synthesis of what you've already discussed.
---

The issue tracker and triage label vocabulary should have been provided to you — run `/setup-skills` if not.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't already. Read `docs/agents/domain.md` for the domain doc layout and `engineering/setup-lineage/SKILL.md` → [Requirements boundary](../setup-lineage/SKILL.md#requirements-boundary). Use the project's domain glossary vocabulary throughout the spec, and respect any ADRs in the area you're touching. If `.data/requirements/` exists, read relevant FS/SRS contracts and legacy companions; keep invocation and realization detail in the source ADR. When a spec item traces to a formal requirement, tag it inline with the requirement ID in parentheses — e.g. "As a user, I want … (REQ-1234)" — so the IDs flow through to tickets. Search source code conceptually and cross-file; search docs and requirements as a document corpus; for architecture-level questions start with a global search before reading individual files.

2. Sketch out the seams at which you're going to test the feature. Existing seams should be preferred to new ones. Use the highest seam possible. If new seams are needed, propose them at the highest point you can. The fewer seams across the codebase, the better — the ideal number is one.

   **Headless detection:** check whether the `AskUserQuestion` tool is available in the current session. If it is absent, the skill is running headless (invoked by another agent with no interactive user). In headless mode, skip the seam-check user interaction below and draw seam decisions from the conversation or task context instead. **Shaping-context validation:** before skipping, confirm the context contains explicit seam decisions; if none are found, stop with: "headless mode requires pre-shaped context with seam decisions — provide seam decisions in the task description and re-invoke."

   Check with the user that these seams match their expectations (skip this interaction in headless mode).

3. **Derive the feature slug.** Slugify the conversation's feature name — take it from the first user message or task description, lowercase it, collapse non-alphanumeric characters to `-`, and trim. In headless mode fall back to `<CLAUDE_CODE_SESSION_ID>-<unix-timestamp>`. The slug lives in memory for the duration of this run.

3.5. **Resolve source ADRs (ADR-0066).**
   - Collect all ADR paths (`docs/adr/*.md`) mentioned in the conversation context.
   - If none found, ask: "Which ADR(s) does this spec derive from? Provide paths under `docs/adr/`."
   - `**Source ADR**:` must resolve to at least one validated path before writing.
   - For each path: verify the file exists under `docs/adr/`; verify the file body contains `**Status**: Approved`.
     - **Path not found**: surface the gap and request a valid path, or offer to initiate `grill-with-docs` to produce the missing ADR first.
     - **Not Approved**: block finalization and surface which ADR is not yet approved.
   - Store the validated list as `source_adrs`.

   <!-- Note (ADR-0066 §4): the `**Status**: Approved` check relies on an informal body-text convention, not a formalized frontmatter field. Formalizing this convention belongs in ADR-0056 in a future pass; this skill only implements the check as currently specified. -->


4. Write the spec to a **staging file** at `.scratch/<feature-slug>/draft-spec.md`, using the spec template below. The draft **must** begin with this YAML frontmatter block (required for critic's artifact-type detection):

   ```
   ---
   artifact-type: spec
   lineage-rules:
     - "Every spec section must reference at least one source ADR"
     - "Source ADR must exist in docs/adr/ and be in Approved status"
   ---
   ```

   The spec body must include a `**Source ADR**:` field at the top, listing the comma-separated ADR paths from `source_adrs` (e.g., `docs/adr/0034-foo.md, docs/adr/0035-bar.md`).

   Do **not** publish yet. If `.scratch/<feature-slug>/draft-spec.md` already exists (e.g. from a prior interrupted run), overwrite it — a re-run is a fresh draft start, not a resume. Also clear any `dirty` marker at `.scratch/<feature-slug>/dirty` left by a prior failed critic run.

5. **Verify frontmatter and lineage fields.** Confirm that `.scratch/<feature-slug>/draft-spec.md`, after stripping any leading BOM or whitespace, begins with the `artifact-type: spec` frontmatter block. If it does not, stop with: "draft-spec.md is missing the required `artifact-type: spec` frontmatter — re-write the staging file with the frontmatter block and re-invoke."

   Additionally confirm:
   - `**Source ADR**:` is present in the draft body with at least one entry.
   - The listed paths match `source_adrs` exactly. On any mismatch, block the critic loop and surface the specific gap.

   **Already-published guard:** if `.scratch/<feature-slug>/spec.md` already exists, stop with: "already published — delete `.scratch/<feature-slug>/spec.md` to republish." Do not overwrite a previously published spec.

6. **Run the critic loop** over the staged draft:

   ```
   Skill(critic, args: "pickup:.scratch/<feature-slug>/draft-spec.md 3 auto")
   ```

   Critic detects `artifact-type: spec` from the frontmatter, selects the 4-group review roster (A — Completeness, B — Consistency, C — Robustness, D — Requirement Traceability), and runs up to 3 review iterations (at most 2 automatic revisions). The synthesizer edits `draft-spec.md` in place during revisions. On approval, critic prints the sentinel `PLAN_APPROVED_READY_FOR_FINALIZATION: <path>` and returns control here.

7. **Route on outcome.**

   **Approved** (critic printed the sentinel, `auto_approval` true): publish.
   - **Local tracker:** copy `draft-spec.md` → `.scratch/<feature-slug>/spec.md`, strip the `artifact-type:` frontmatter block from the copy, then remove `draft-spec.md`. Apply `ready-for-agent` status to the published spec.
   - **Real tracker (GitHub, Linear, …):** publish the spec body (frontmatter stripped) as a single issue or document with `ready-for-agent` label.

   **Not approved** (revise-at-cap, unresolved major issues, hard-abort — no sentinel from critic): leave the draft staged at `.scratch/<feature-slug>/draft-spec.md`.
   - **Interactive mode:** show the staged spec and the unresolved critic issues, then offer **revise / publish anyway / abandon**.
   - **Headless mode:** write a summary of the unresolved issues to `.scratch/<feature-slug>/critic-review.md` and stop. Do not auto-publish; headless publishing occurs only on genuine critic approval.

<spec-template>

**Source ADR**: docs/adr/{slug}.md

## Problem Statement
## Solution
## User Stories  (long numbered list, "As an <actor>, I want a <feature>, so that <benefit>")
## Implementation Decisions  (modules, interfaces, arch decisions, schema, API contracts — no file paths/snippets except prototype excerpts)
## Testing Decisions  (what makes a good test, which modules, prior art)
## Out of Scope
## Further Notes

</spec-template>
