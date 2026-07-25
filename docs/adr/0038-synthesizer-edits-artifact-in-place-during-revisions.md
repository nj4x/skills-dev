# Synthesizer edits artifact in place during critic revisions

When the critic loop requires a revision (major severity), the synthesizer agent reads the artifact file(s) and edits them **in place** using the Edit tool, rather than returning revised text for the orchestrator to write. The critic then re-reviews the file(s). This extends the in-place ADR revision pattern already established in critic's design-review mode to `spec` and `tickets` artifacts.

We chose in-place editing because it keeps the orchestrator out of the text-shuttle loop: returning full revised text adds a full-artifact round-trip through the agent boundary on every iteration, which wastes tokens and risks truncation on large specs or ticket lists. The Edit tool touches only changed sections. Consistency with the existing ADR revision pattern also keeps the synthesizer's behaviour predictable.

## Widen the GENERATE_STEP gate

The critic's GENERATE_STEP revision branch currently selects the in-place-edit path with `[IF is_design_review]` and otherwise (`[ELSE]`) returns full revised plan text. As written, `spec` and `tickets` fall into the ELSE branch, making this ADR's in-place editing structurally unreachable. The gate is therefore **widened**:

- **In-place-edit branch** — taken when `is_design_review OR artifact_type IN {spec, tickets}` (i.e. `artifact_type != plan`). The synthesizer edits the artifact file(s) in place and returns only the manifest/path as `artifact_text`.
- **Return-revised-text branch** (ELSE) — taken **only** for `artifact_type == plan`. The synthesizer returns full revised plan text and the orchestrator writes it.

The post-GENERATE_STEP handling that already special-cases `is_design_review` (storing the manifest as-is, skipping content extraction) applies unchanged to `spec` and `tickets`, because they too edit in place.

## Single-file spec: re-read by stored path each iteration (no manifest)

Design-review and tickets both give critic a **manifest** — a stable file whose body lists the artifact file paths — and critic's REVIEW_STEP manifest-read path is today gated on `is_design_review`. A `spec`, however, is a **single file with no manifest**. If the synthesizer merely returned the spec's path string as `artifact_text`, then on iteration > 0 `current_plan` would become a bare path and the spec body would be lost from review (the manifest-read path does not fire for a spec, and there is no manifest to read).

To avoid inventing a one-line wrapper manifest for the spec, the orchestrator handles `artifact_type == spec` by **re-reading the staged file from a stored path each iteration**. The rule is written to respect the resolution order (`artifact_type` is resolved *in* REVIEW_STEP, ADR-0037):

1. **On the first pickup**, the orchestrator records the staged spec path (the `pickup:<path>` argument, ADR-0039) as `spec_file_path`. **Iteration-0 review content is the file at the pickup path itself** — no `artifact_type`-conditioned re-read is needed before the type is known, because the pickup path already points at the on-disk spec.
2. **The synthesizer** edits the spec in place and returns the path string as `artifact_text` (as for every non-plan type).
3. **From iteration 1 onward** — once `artifact_type == spec` has been resolved in the prior REVIEW_STEP — the orchestrator **re-reads the file at `spec_file_path`** before each REVIEW_STEP into the artifact content under review. Review always sees the current on-disk spec body, never a bare path.

**Spec-side staging assertion:** before each re-read, if the file at `spec_file_path` is **missing, unreadable, or empty**, or the synthesizer returned a path that **disagrees with the recorded `spec_file_path`**, the orchestrator writes the `dirty` marker (see below), surfaces the error, and hard-stops rather than reviewing stale or empty content. This mirrors the multi-file post-edit validation so both artifact types fail loudly instead of silently reviewing nothing.

This keeps the spec free of frontmatter-carrying manifest scaffolding while guaranteeing the revised body is re-reviewed on every iteration. Tickets keep their manifest (they are genuinely multi-file, ADR-0037); the single-file spec uses the stored-path re-read, and the multi-file tickets use the symmetric manifest re-read defined next.

## Multi-file tickets: re-read the manifest and all ticket bodies each iteration

A tickets `pickup:<path>` points at `manifest.md`, whose body is only a path list — reviewing it verbatim would starve the tickets/D Slice Boundaries lens (ADR-0036), which needs the actual ticket bodies. Symmetric to the spec re-read: **before each REVIEW_STEP for `artifact_type == tickets`** (from iteration 0, where the manifest is already the pickup artifact), the orchestrator composes the review content as **the manifest plus the current on-disk body of every manifest-listed ticket file, in dependency order**. This is the same "read all referenced files" assembly design-review already performs, so the critic re-sees every revised ticket body on every iteration.

## Draft file must exist before the loop

In-place editing requires a persisted file. The draft is written to staging **before** the critic loop starts (ADR-0034, "Draft staging"): `.scratch/<feature-slug>/draft-spec.md` for a spec, and the ticket files + `manifest.md` for tickets. The pickup path passed to critic (ADR-0039) points at that staged file/manifest, so the very first iteration reads a real file.

## Multi-file tickets: edit siblings and the manifest together

A `spec` is a single file — a straightforward in-place edit. `tickets` are **N files plus a manifest** (ADR-0037), so a revision may need to change more than one file at once. The synthesizer receives the manifest **and the content of every referenced ticket file**, and edits in place across the set:

- **Content change within a slice** — edit that ticket file.
- **Add a slice** — write a new ticket file and add its path to the manifest (in dependency order).
- **Remove or renumber a slice** — delete/rename the ticket file, update the manifest, **and** update every sibling's `Blocked by` reference that pointed at the changed slice so no dangling edges remain.

The synthesizer returns the (possibly updated) manifest as its `artifact_text`; the critic re-reads the manifest and all referenced files for the next review, so cross-file blocking-edge integrity is re-checked each iteration by the Slice Boundaries group (ADR-0036).

**Post-edit validation:** after all edits are complete and before returning, the synthesizer validates the staged set — it re-derives the manifest↔files↔Blocked-by graph and asserts: (a) every path in the manifest refers to an existing, readable file; (b) every `Blocked by` reference in every ticket file resolves to a slug present in the manifest; (c) no staged ticket file is absent from the manifest; (d) the `Blocked by` graph is **acyclic** and no ticket blocks itself. Assertion (d) makes acyclicity a structural precondition, not merely a critic review lens (ADR-0036 tickets/D), so the dependency-ordered create pass of ADR-0040 can always topologically sort the manifest. If any assertion fails, the synthesizer writes a `dirty` marker file (`.scratch/<feature-slug>/dirty`) to the staging directory, reports the specific inconsistency, and does **not** return success. The orchestrator treats a staging directory containing a `dirty` marker as a **hard stop** — it surfaces the validation error and does not proceed to further review or publishing.

## Considered Options

- **Return revised text, orchestrator writes**: orchestrator stays in full control of file mutation but incurs full-artifact token cost on every iteration and risks truncation. Retained only for plain plans, which have no persisted draft file to edit.
- **Single-file tickets artifact**: collapse all slices into one file so a single in-place edit suffices. Rejected — the publish step (ADR-0034/0040) needs one file per issue in dependency order, and a single blob would have to be re-split on every iteration.
