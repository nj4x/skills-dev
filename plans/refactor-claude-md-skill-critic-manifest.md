# CLAUDE.md Refactoring Skill — Design Decisions for Critic Review

These ADRs capture the non-obvious architectural decisions reached during the grill-with-docs session for the planned `refactor-claude-md` skill. Critic should assess whether these decisions are sound, internally consistent, and whether any blind spots or contradictions exist between them.

- docs/adr/0026-refactor-claude-md-two-gate-autonomy.md
- docs/adr/0027-refactor-claude-md-mirror-source-location.md
- docs/adr/0028-refactor-claude-md-critic-reviews-output-not-adrs.md

## Skill design summary (for critic context)

The skill refactors any CLAUDE.md file (project or global, passed as optional argument) into a minimal root + intent-driven satellite files under `docs/agents/`. It:

1. Runs LLM contradiction detection → stops for user decision (Gate 1)
2. Extracts essentials via semantic clustering → writes to root autonomously
3. Groups remaining instructions by intent into satellite files → writes autonomously
4. Runs LLM redundancy detection → stops for user deletion confirmation (Gate 3)
5. Writes a summary report
6. Invokes critic on the refactored output files

Satellites mirror the source location. Re-runs overwrite silently. No separate ADRs are written for contradiction/deletion choices.
