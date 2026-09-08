# Anti-patterns and defaults

## Anti-patterns — what to avoid

### 1. Vague target

Bad: "Create a prompt for this work"
Fix: name the exact command, skill, workflow, or artifact the prompt drives.

### 2. Generic template dump

Bad: pasting the same autonomous-agent template regardless of request shape.
Fix: do a quick signal read, gather compact intake, then apply the LOOP vs HELPER gate and tailor.

### 3. Missing verification — inline

Bad: the loop has no step that runs the real command or checks the real log.
Fix: embed the actual command + actual log path as a numbered loop step. Not as a `## Verification gates` section.

### 4. Missing stop condition

Bad: high-autonomy loop with no stop line.
Fix: paste the canonical stop line verbatim (copy from `references/prompt-template.md`). One line, not a bullet list.

### 5. Hidden assumptions

Bad: burying inferred defaults in prose paragraphs.
Fix: make the target, the command, and the skills explicit inside the loop steps.

### 6. Ceremonial bloat (NEW — top priority)

Bad: adding standalone `##` sections for Why-this-exists, Capability-model, Acceptance-criteria-as-N-items, Output-format, Review-checklist, or Assumptions-confirmed/inferred.
Fix: drop ceremonial sections. Verification lives inline in the loop. Stop condition is one line at the bottom.

### 7. Linear one-shot when a loop is needed (NEW)

Bad: a flat numbered task list with no "Continue to step 0" / repeat for an open-ended engineering request.
Fix: default to the LOOP archetype. Add "Continue to step 0 (repeat)" as the final step.

### 8. Multi-bullet stop condition (NEW)

Bad:
```
## Stop and escalation conditions
- Stop when X
- Do not proceed when Y
- Escalate when Z
```
Fix: one verbatim canonical stop line at the bottom. Multiple bullets are replaced by one line.

### 9. Skills without round counts (NEW)

Bad: "use plan-with-critic" or "apply code-review"
Fix: "plan-with-critic (3 rounds)", "apply code-review skill to uncommitted code". Round counts control depth and are part of the instruction.

### 10. Domain-specific names in templates (NEW)

Bad: hard-coding `SRS-skill`, `FS-skill`, `data-view skill`, or a project-specific command into the skill's template files.
Fix: templates use generic placeholders (`<relevant skills, M rounds of critic>`). Domain-specific skills are filled in by the author when synthesizing the final prompt.

### 11. Stale memory reuse

Bad: reusing a prior prompt pattern as if it were mandatory.
Fix: present remembered defaults as hints and confirm them.

### 12. Over-questioning

Bad: asking many open-ended questions before compact intake.
Fix: use the 5 canonical intake questions; infer everything you can first, then apply the archetype gate after intake answers are available.

---

## Pre-write guard (4 checks)

Before returning or writing the prompt:
1. Verification step present inline in the loop or HELPER steps?
2. Canonical stop line present verbatim?
3. Target/goal explicit in the opening line, including existing requirements/spec artifacts to refine when applicable?
4. If code changes are in scope, are FS-skill + SRS-skill + data-view skill present before implementation?

Fix inline if any check fails.

---

## Preferred defaults

### For LOOP prompts (autonomous engineering)
- Single self-repeating numbered loop (0..N → Continue to step 0).
- Skills named inline with round counts: `plan-with-critic (N rounds)`, `FS-skill`, `SRS-skill`, `data-view skill`, `apply code-review skill`.
- Canonical stop line verbatim at the end. One line.
- Real command + real log path embedded as loop steps.
- Refine existing requirements/spec artifacts first, then software requirements, then use cases/data access patterns, then implementation, then code review.
- Target 25-40 lines.

### For HELPER prompts (one-offs)
- Title + mission + ≤5 numbered steps + inline verification + stop line.
- Target 10-20 lines.

### For debugging prompts
- Start from evidence: check log line count, run the real command, observe output.
- Confirm-or-disprove the root cause before changing code.

### For review prompts
- Specify scope (committed vs working-tree).
- Severity framing. Evidence for each finding. Plan for what happens after findings.
