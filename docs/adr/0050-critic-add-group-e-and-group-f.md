# Critic: add tickets Group E and spec/tickets Group F inline

Two new reviewer groups are added to the critic's parallel sub-agent set for `spec` and `tickets` artifact types. Both are defined inline in critic/SKILL.md under the existing `artifact_type` conditionals, following the pattern of the existing Groups D–E.

## Context

The amon-watchlist-wiring tickets loop identified two categories of issues that no existing group caught:

- **Cross-artifact contract drift** (Group E): ~60% of real ticket findings were config-key mismatches, `setup_id` type drift (int/str/UUID), audit-string vocabulary divergence, and duplicate ownership. No existing group owned this; it leaked unevenly into A and B.
- **Codebase grounding** (Group F): high-value findings (wrong function names, nonexistent columns, invalid signatures) arrived at passes 8–10 by accident. A dedicated pass-1 check with Read/search access would surface these first.

A prior proposal (ADR-0050 draft) attempted to move all GROUP prompts to on-demand include files. That approach was abandoned: the existing GROUP prompts occupy only ~57 lines (~3.5KB) of a 28.7KB file, so moving them cannot achieve a significant size reduction. Adding Groups E and F inline adds ~1–2KB — negligible, and far simpler than file-splitting with path resolution, sentinel validation, and group-count synchronization overhead.

## Decision

### tickets Group E — Cross-Artifact Contract Consistency

Add to critic/SKILL.md inside the `[IF artifact_type == tickets]` block (after Group D — Slice Boundaries). Runs on every iteration.

Reviewer role: adversarial reviewer for cross-artifact contract consistency.

Evaluation criteria:
- Config-key names: are keys referenced in ticket A consistent with how ticket B defines or reads them?
- Type-identifier drift: does `setup_id` (or equivalent) carry the same type (int / str / UUID) across all tickets that reference it?
- Audit-string vocabulary: are audit log strings consistent across tickets that share a domain entity?
- Duplicate ownership: does more than one ticket claim to own (create, migrate, or delete) the same entity?
- Blocking edges: are all `Blocked by` references in every ticket resolvable to a slug present in the manifest?

Each `major`-severity finding must cite the specific ticket slug(s) and the field/value discrepancy (evidence rule per ADR-0047).

### spec/tickets Group F — Codebase Grounding (iteration 0 only)

Add to critic/SKILL.md inside both the `[IF artifact_type == spec]` and `[IF artifact_type == tickets]` blocks, conditional on `iteration == 0`. Not spawned on later iterations. `plan` and `design-review` do not receive Group F (plans reference future code; design-review grounding occurs in grill-with-docs).

Reviewer role: adversarial reviewer for codebase grounding.

Evaluation criteria:
- Verify every named artifact (function, method, class, config key, schema field, DB column, type) cited in the artifact exists at the cited location in the codebase.
- For artifacts that are intentionally new (a ticket scaffolds a new function — that is expected), do not flag.
- For absent artifacts: cite the search performed plus the artifact quote naming the missing symbol (e.g., "spec §3 cites `parse_watchlist()`; rg over `CODEBASE_ROOT` returns no definition") — a `file:line` is not required when the finding is absence.

Tool guidance: search source code conceptually and cross-file, search docs and requirements as a document corpus, and for architecture-level questions start with a global search before reading individual files. Fall back to normal filesystem tools such as `rg`, `fd`, and Read for exact-string or local lookups.

Codebase root: the orchestrator derives `CODEBASE_ROOT` from `$CLAUDE_PROJECT_DIR` (falling back to `$PWD`). Before spawning Group F it checks that the path exists and is a readable directory. Semantic/indexed search is preferred when available, but it is not required: if the MCP server is unavailable, the root is unindexed or partially indexed, or a semantic search fails, Group F falls back to `rg`, `fd`, and Read against the filesystem. These fallback paths still produce the required evidence. `CODEBASE_ROOT: <path>` is injected into the coordinator prompt as a line immediately before the `SUB-AGENT PROMPTS` block so the Group F sub-agent can reference it directly.

**Nested tool access**: Group F is spawned two Agent levels deep (orchestrator → coordinator → Group F sub-agent). No tool restriction is specified; nested sub-agents inherit full tool access matching current Groups A–E behavior.

Group F is iteration-0-only as a cost tradeoff. A later revision could replace a verified citation with an unverified one; this is an accepted minor limitation rather than a reason to add another review pass. The initial grounding pass catches the high-value pre-existing mismatches while keeping the loop simple and bounded.

### SKILL.md coordinator instruction update

The coordinator instruction at critic/SKILL.md:245 is updated from its current fixed counts to:

- `spec`: 4 groups A/B/C/D on iteration > 0; 5 groups A/B/C/D/F on iteration 0 (or 4 if Group F skipped)
- `tickets`: 5 groups A/B/C/D/E on iteration > 0; 6 groups A/B/C/D/E/F on iteration 0 (or 5 if Group F skipped)
- `plan`: 5 groups A/B/C/D/E (unchanged)
- `design-review`: 3 groups A/B/C (unchanged)

The orchestrator computes the active group list based on `artifact_type`, `iteration`, and the Group F pre-flight result, then passes the resolved count and group letters to the coordinator prompt.

## Consequences

- **Cross-artifact contract findings (Group E)** are now systematically caught rather than leaking into Group A/B; the evidence rule (ADR-0047) ensures each finding is grounded in a specific ticket reference.
- **Codebase grounding findings (Group F)** surface on the first pass rather than at pass 8–10 by accident; the synthesizer resolves them before speculation about missing functions proliferates.
- **Revision-introduced citations are not re-verified**: Group F runs on iteration 0 only. If the synthesizer adds a reference to a function that doesn't exist during a revision pass, no group catches it. This is an accepted tradeoff — re-running Group F every pass is expensive (sub-agent spawn + codebase search). Mitigation: Group F on the final iteration before approval (if cost permits) can be added as a future improvement.
- **Group E on all iterations** means contract-drift introduced during revisions is caught. This is the desired behavior since the revision agent edits ticket files in place (critic/SKILL.md:118-125) and may alter `Blocked by` references or type identifiers.
- **Inline size increase**: ~1–2KB added to critic/SKILL.md. Still well within safe operating range.
- **Group-count computed at runtime**: the orchestrator no longer uses a fixed literal count in the coordinator prompt; it derives the group list and injects it. This is a small orchestrator change but eliminates the mismatch between static counts and runtime group omission.

## Related ADRs

- ADR-0047: Evidence-gated major severity (evidence rule applies to both new groups).
- ADR-0049: Majors-only revision prompt and verdict coercion (coordinator MERGE RULE change — independent of this ADR).
