# Frontmatter metadata signals artifact type to critic

When `to-spec` and `to-tickets` write their draft artifact to staging (ADR-0034), they include YAML frontmatter with an `artifact-type` field (`spec` or `tickets`). Critic reads this field to select the sub-agent group roster (ADR-0036) rather than inferring artifact type from content patterns or requiring the caller to pass a type parameter.

This must coexist with critic's **existing** detection: today `critic/SKILL.md` sets `is_design_review` by scanning the plan text for the sentinel string `Design Decisions Reached During Grilling`, and plain plans have no frontmatter at all. This ADR therefore defines a **precedence order** that resolves all cases into a single `artifact_type` value.

## Detection precedence (resolved in REVIEW_STEP, before group selection)

Resolution happens in REVIEW_STEP. Because `to-spec`/`to-tickets` always enter critic via `pickup:<path>` (ADR-0039), critic **skips iteration-0 GENERATE** and reaches REVIEW_STEP first; `artifact_type` is therefore **always resolved before any GENERATE_STEP or FINALIZE_STEP branches on it** (the pickup-only precondition, also stated in ADR-0039). No branch downstream can observe an unresolved type.

Given the picked-up artifact text (`current_plan` / `plan_or_manifest`), resolve `artifact_type` by the first rule that matches:

1. **Frontmatter** — **after stripping a leading UTF-8 BOM and any leading whitespace/blank lines**, if the text begins with a YAML frontmatter block (`---` fence) containing `artifact-type: <v>` and `<v>` is a recognized value (`spec` or `tickets`), then `artifact_type = <v>`. The strip is required: a stray leading blank line or an editor-inserted BOM must not defeat the "begins with frontmatter" check.
2. **Design-review sentinel** — else if the text contains `Design Decisions Reached During Grilling` (or the established ADR-marking text), then `artifact_type = design-review`.
3. **Plain plan** — else `artifact_type = plan`.

`is_design_review` becomes the derived predicate `artifact_type == design-review`, preserving every existing code path that branches on it.

**Missing or unrecognized `artifact-type` (organic pickup):** if the frontmatter is absent, or present but carries an unrecognized value (e.g. `artifact-type: foobar`), rule 1 does **not** match — resolution falls through to rules 2 and 3. An unrecognized value is treated as absent (not an error) so a stray or future value degrades gracefully to sentinel/plain-plan detection rather than hard-aborting. This graceful fall-through is the correct behaviour for artifacts a human picked up directly (a plain plan, or an ADR bundle).

**Pre-invocation verification by the calling skill:** the graceful fall-through above applies only to organic pickups. When `to-spec` or `to-tickets` prepares a staged file, the skill **verifies its own draft's frontmatter before invoking critic** — if the staged file does not begin with the expected `artifact-type: spec` or `artifact-type: tickets` YAML frontmatter, the **calling skill hard-errors** and does not invoke critic at all. This puts the safety check at the point where the expected type is known (the invoking skill), rather than inside critic where no expected type is available (see ADR-0039: the invocation is `pickup:<path> 3 auto` with no slot for an expected type). Critic's own resolution is **graceful fall-through only** — an unrecognized or absent `artifact-type` value degrades to sentinel/plain-plan detection, never a hard-error inside critic. The resolved `artifact_type` is printed in the critic status line so the selection is visible either way.

## Multi-file tickets: manifest carries the frontmatter

A `spec` is a single file, so its frontmatter lives at the top of that file. `tickets` are **N files** (ADR-0034). Mirroring the existing design-review pattern — where `current_plan` is a manifest (a markdown list of ADR file paths) — the tickets artifact is a **manifest file** that:

- carries the `artifact-type: tickets` frontmatter (so detection reads one place), and
- lists the ticket file paths (one per line), in dependency order.

Critic reads the manifest, resolves `artifact_type` from its frontmatter, then reads every referenced ticket file into the assembled artifact content (the same "read all referenced files" step design-review already performs). The individual ticket files need no frontmatter of their own. This keeps detection single-sourced and lets the synthesizer edit all ticket files in place plus the manifest itself when slices are added/removed/renumbered (ADR-0038).

**Manifest-body parse rules:** when critic reads the manifest to extract ticket file paths (the lines below the closing `---` frontmatter fence), it applies the following rules:
- Blank lines are ignored.
- Lines beginning with `#` (comment lines) are ignored.
- Each remaining line must be a **relative** path (not absolute — no leading `/`) that contains **no `..` segment** and, once resolved, stays inside the run's staging directory (`.scratch/<feature-slug>/draft-issues/`). It must also contain no shell metacharacters such as `;`, `|`, `&`, `$`, `(`, `)`, `` ` ``. This bounds what the publish promotion of ADR-0040 can read and write to the staging tree — an absolute path or `../../issues/x.md` would let promotion touch files outside staging.
- A path that violates the above, or is missing or unreadable on disk, is a **hard-error**: critic aborts, naming the offending path and the manifest file, rather than silently skipping it or proceeding with an incomplete artifact.

## Considered Options

- **Content-pattern detection** (`## Problem Statement` → spec): scans file text for signature sections. Brittle, silent, invisible in the file — and would collide with the design-review sentinel with no defined precedence.
- **New critic CLI argument `/critic <type> pickup:<path>`**: couples critic's argument surface to the artifact-type taxonomy; a new artifact type requires a critic argument change even when no critic logic changes.
- **Separate `critic-spec` / `critic-tickets` skills**: skill proliferation with duplicated critic orchestration logic.
- **Per-ticket frontmatter instead of a manifest**: N places to read and keep consistent; the manifest already needed to exist to list files in dependency order, so it is the natural single source.
