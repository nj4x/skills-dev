# Two-gate autonomy model for CLAUDE.md refactoring skill

The skill runs fully autonomously except for two decision gates: **Gate 1 — contradiction resolution** (the user chooses which of two conflicting instructions to keep and explains why) and **Gate 2 — redundancy confirmation** (the user approves instructions flagged for deletion). Essentials extraction, category grouping, satellite file creation, and root CLAUDE.md rewriting all happen without gates.

The two gates are numbered sequentially, Gate 1 and Gate 2, with no phantom gaps. An earlier draft numbered them "Gate 1" and "Gate 3" — a leftover from a dropped essentials gate that once sat between them. That numbering is corrected here: contradiction is Gate 1, redundancy is Gate 2. The summary report and any user-facing prompts must use this same numbering.

## Empty-set behavior at each gate

A gate only blocks when it has something to decide:

- **Gate 1 (contradiction)**: if the analysis finds zero contradictions, the gate is silently skipped — no prompt is shown. The skill logs "No contradictions detected" to the summary report and proceeds.
- **Gate 2 (redundancy)**: if nothing is flagged for deletion, the gate is silently skipped — no prompt is shown. The skill logs "No redundant instructions detected" and proceeds.

The skill never blocks on an empty prompt. If both sets are empty, the skill runs end-to-end without any user interaction.

## Considered Options

An earlier design included a third gate for essentials review — the user would eyeball the proposed "essentials" list and promote/veto items. This was dropped because essentials extraction is mechanical (LLM semantic clustering) and the user can see the result in the refactored root CLAUDE.md without a blocking step. Dropping it left a hole in the gate numbering (see above), which is why the model is now explicitly renumbered to Gate 1 / Gate 2.

## Consequences

Users who disagree with how essentials were extracted must re-run the skill. **Re-running is destructive** (see ADR-0027): it overwrites the root CLAUDE.md and satellite files. The correct course-correction is therefore to **edit the source CLAUDE.md and re-run** — not to hand-edit the generated output, because those edits will be clobbered. Because re-running is the only in-session lever for essentials, ADR-0027 requires that re-runs back up the prior output first so a user who edited the output by mistake can recover it.
