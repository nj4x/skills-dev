# Critic: session-scoped ledger filename

The critic ledger tracks open issues, major counts, and convergence guard state across iterations. Its path is derived as `<staging_dir>/critic-ledger.json`. For `spec` and `tickets` artifacts the staging dir is already per-feature (`.scratch/<feature>/`), so collisions are unlikely. For `plan` and `design-review` the staging dir collapses to the shared `~/.claude/plans/`, producing a bare `critic-ledger.json` at the plans root.

Concurrent critic sessions in different agents both write `~/.claude/plans/critic-ledger.json` and clobber each other — mixing issue IDs, major counts, and convergence-guard state across unrelated sessions. This violates session isolation and produces undefined ledger behavior.

## Decision

Include `CLAUDE_CODE_SESSION_ID` in the ledger filename universally.

Derive `critic_ledger_path = <staging_dir>/critic-ledger-<CLAUDE_CODE_SESSION_ID>.json` (instead of `<staging_dir>/critic-ledger.json`). Applied unconditionally across all artifact types; redundant for `spec`/`tickets` but harmless, and eliminates a special case. Incorporates the session ID analogously to the plan file (`<session_id>-plan.md`), though the ID sits as a suffix here versus a prefix there.

## Consequences

- **Session isolation:** concurrent critic sessions no longer share or clobber ledger state regardless of artifact type.
- **File proliferation:** `~/.claude/plans/` accumulates one ledger per session ID. Ledgers for deleted plans persist until manually cleaned — acceptable, low-storage, mirrors plan file retention.
- **Backward compatibility:** existing bare `critic-ledger.json` files are orphaned and ignored. No data loss.

## Related ADRs

- ADR-0049 (`0049-critic-tranche-b-convergence-mechanics`): documents the `<staging-dir>/critic-ledger.json` ledger this ADR amends for session isolation. It attributes the originating decision to ADR-0048 (orchestrator-owned per-issue ledger), for which no file currently exists in `docs/adr/`.
- ADR-0050: critic GROUP additions that write to the ledger.
