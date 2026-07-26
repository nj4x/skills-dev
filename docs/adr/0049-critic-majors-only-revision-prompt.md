# Critic: verdict coercion — revise only on major severity

The coordinator MERGE RULE is changed so that `verdict = "revise"` only when `severity == "major"`. Minor-only runs become `approve + minor`, exiting the loop naturally without a revision pass.

## Context

The current MERGE RULE (critic/SKILL.md:319-323) sets `verdict = "revise"` if any sub-agent returns "revise", regardless of that sub-agent's severity. In the amon-watchlist-wiring loop, groups repeatedly returned "revise" + "minor", keeping the loop running on non-blocking concerns. The synthesizer, obligated to address all feedback, added defensive machinery that was then attacked in the next pass.

Two approaches considered:

- **Orchestrator-side filter + short-circuit**: filter `last_top_issues` to majors only, short-circuit to FINALIZE on revise+minor. Not viable: `top_issues` is a flat `string[]` with no per-item severity (critic/SKILL.md:247-251, 319-323); a short-circuit guard has no legal home — repeat/SKILL.md:156-161 STOP_CONDITIONS are exhaustive and critic/SKILL.md:25 prohibits re-deriving the loop.
- **Coordinator verdict coercion**: change the merge rule so verdict tracks severity directly. The coordinator already sees all sub-agent outputs and can derive this before returning. `top_issues` stays unfiltered; no new fields; no schema changes.

## Decision

Replace the verdict line in the coordinator MERGE RULE (critic/SKILL.md:319-323):

```
MERGE RULE (after all sub-agents respond):
- severity: highest across all sub-agents (major > minor > none)
- verdict: "revise" if severity == "major"; "approve" otherwise
- top_issues: concatenate all arrays; remove obvious duplicates
- suggested_fixes: concatenate all arrays; remove obvious duplicates
```

`top_issues` is unchanged — it carries all findings at all severities as before. On an approve+minor outcome, `top_issues` reaches FINALIZE_STEP unmodified and is rendered under "Remaining risks / open questions" with the existing note "optional improvements may still be listed when verdict is 'approve' and severity is 'minor'" (critic/SKILL.md:442). No new fields, no validator changes, no repeat-contract extensions.

## Consequences

- Minor-only loops no longer spin: verdict coercion turns revise+minor into approve+minor, which satisfies repeat/SKILL.md:156 STOP_CONDITION 1 and exits normally.
- `auto_approval = True` on approve+minor (`severity != "major"`, `verdict == "approve"`, not cap-reached). The PLAN_APPROVED_READY_FOR_FINALIZATION sentinel fires normally; spec/tickets publishing handshake is unaffected.
- The existing validator at critic/SKILL.md:381-393 already permits approve+minor (only approve+major and revise+none are rejected). No validator change needed.
- No change to repeat/SKILL.md, STOP_CONDITIONS, REVIEW_STEP return shape, or FINALIZE_STEP parameter list.
- Minor findings are not lost: they remain in `top_issues` and are surfaced in Critic Review on the approval pass.
- Synthesizer already knows minors are non-blocking: critic/SKILL.md:166 states "Minor improvements may still be noted on approval." No prompt change needed.
