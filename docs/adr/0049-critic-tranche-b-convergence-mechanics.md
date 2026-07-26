# Critic: Tranche B convergence mechanics

Tranche B implements four inter-dependent loop-level mechanics to break non-convergence in critic reviews: per-issue ledger persistence, revision-prompt filtering to majors only, convergence guard halting, and anti-spiral tagging of newly-introduced constructs.

## Context

The amon-watchlist-wiring tickets loop (12 passes) demonstrated three failure modes:

1. **Re-litigation** (~30% of issue slots): same findings appeared across passes 5–9 and 12. The critic had no memory of prior findings; the orchestrator could only fix, never decline.
2. **Spiralling complexity** (passes 4–8): synthesizer added machinery (`scoring_attempt_counters`, `check_alive()`) to resolve uncertain critic findings. Next pass attacked the new machinery; issue count stayed flat.
3. **No halt signal** (all 12 passes): critic was invoked regardless of progress. Even when major count was flat or growing, the loop continued until manual stop.

## Decision

**Five sub-decisions:**

### 1. Orchestrator-owned per-issue ledger (ADR-0048 details)

The orchestrator maintains `<staging-dir>/critic-ledger.json` with structured issue records:
```json
[
  { "id": "ID-001", "group": "A", "claim": "...", "evidence": "...", "severity": "major", "fix": "...", "status": "open" },
  { "id": "ID-002", "group": "B", "claim": "...", "evidence": "...", "severity": "minor", "fix": "...", "status": "fixed" }
]
```

After each REVIEW_STEP: orchestrator upserts findings from `top_issues` and `suggested_fixes` into the ledger. New claims → `status: open`. Repeat claims (matched by ID or normalized text) → update severity/evidence if changed. Status stays `open` unless the next pass resolves it.

After each GENERATE_STEP revision: orchestrator does NOT write the ledger. The next REVIEW_STEP verdict determines if a claim is resolved.

The orchestrator also tracks per-pass `INTRODUCED: [construct_name]` annotations from the synthesizer revision, storing them in the ledger for anti-spiral tagging.

### 2. Majors-only revision prompt

The orchestrator filters `top_issues` to include only `major`-severity items before passing them to the synthesizer in the next GENERATE_STEP revision prompt. Minors are omitted with a note: "Only major-severity issues are listed below. Minor improvements may be addressed in future passes if they accumulate."

This removes the obligation for the synthesizer to address every minor comment; it reduces workload and allows flat issue-count passes where only majors are tackled.

### 3. Ledger summary in revision prompt

Before the `CRITIC TOP ISSUES` section, the orchestrator injects a `LEDGER SUMMARY`:
```
LEDGER SUMMARY (open issues from prior passes):
- ID-001 (group A, severity major): "scope includes X" → still open
- ID-003 (group C, severity major): "missing error handling for Y" → still open
```

This orients the synthesizer to cumulative progress and gives each issue a stable ID.

### 4. Anti-spiral tagging

The synthesizer prompt includes: "If you introduce new functions, classes, configuration keys, or machinery, annotate them with a line: `INTRODUCED: [name]`."

The orchestrator extracts `INTRODUCED:` annotations from the synthesizer's revision response and stores them in the ledger per pass. On pass 2+, the coordinator prompt includes:
```
CRITIC-INDUCED CONSTRUCTS (treat findings about these as minor after pass 2):
- scoring_attempt_counters (introduced pass 1)
- check_alive() (introduced pass 1)
```

The critic is instructed: "Findings about newly-introduced constructs are capped at `minor` severity after pass 2, since you requested their introduction."

### 5. Convergence guard

After each REVIEW_STEP (pass 2+), the orchestrator checks: if `major_count_in_ledger[pass N] >= major_count_in_ledger[pass N-1]`, set `halt_convergence_guard = true`.

In the STOP_CONDITIONS evaluation (after REVIEW_STEP), add a new condition before the cap-reached check:
- If `halt_convergence_guard == true`, go to Finalize and emit: "Convergence guard halted: major count did not decrease. Standing issues:" (list all open majors).

This halts the loop after 2 consecutive non-decreasing passes, preventing the flat-issue treadmill.

### Auto-approval gate

Auto-approval remains: `verdict == "approve" AND NOT cap_reached`. Trust the sub-agent merge rule (unanimous approval = no majors). Do not double-check severity against the ledger; the verdict already encodes it.

## Consequences

- **Re-litigation eliminated:** critic cannot re-raise `accepted` issues; orchestrator suppresses repeat claims in the ledger summary.
- **Spiral broken:** anti-spiral tagging prevents the critic from attacking constructs it induced; synthesizer is guided to prefer simplification.
- **Halt signal present:** convergence guard halts non-progress after 2 flat passes, preventing manual intervention loops.
- **Ledger is visible:** users can inspect the ledger post-run to understand which issues were open, fixed, accepted.
- **`Accepted` requires explicit input:** in guided mode, the orchestrator calls `AskUserQuestion` for any issue the synthesizer wants to mark accepted; in auto mode, no issue is auto-accepted (only fixed or still-open).
- **Prompt size grows:** adding ledger summaries, anti-spiral tagging, and induced-constructs headers to GENERATE_STEP and REVIEW_STEP prompts. Refactored into Option A includes (ADR-0050) to keep SKILL.md under compaction risk.
- **Orchestrator state management:** ledger file is persistent across passes; it is never deleted during a run (may be cleaned by caller post-completion).

## Related ADRs

- ADR-0047: Evidence-gated major severity (Tranche A).
- ADR-0048: Orchestrator-owned per-issue ledger (foundational for this ADR).
- ADR-0050: Critic SKILL.md refactored into on-demand prompt includes (consequence of size growth).
