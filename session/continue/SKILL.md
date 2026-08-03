---
name: continue
description: Resume work on a project — interactive mode surfaces next-step options; autonomous mode drives the next incomplete phase to a committed, tested state.
disable-model-invocation: true
---

# Continue Skill

## Two Modes

This skill operates in one of two modes. Pick based on how the skill was invoked:

- **Interactive mode (default)** — Discover state and present next-step *options* for the user to choose. Read-only and non-destructive. Follow the [Interactive Workflow](#interactive-workflow) below.

- **Autonomous mode** — Discover state, then *implement, test, self-heal, and commit* the next incomplete phase without stopping for choices. Follow the [Autonomous Workflow](#autonomous-workflow) below.

When ambiguous, prefer interactive mode and ask the user whether they want autonomous execution.

## Interactive Workflow

### Phase 1: Discover State

Gather all four categories below. The independent discovery probes (git log, git status, file searches, marker greps) should be issued in a single message so they execute in parallel; interpret the results in the order listed.

1. **Git state**
   - Current branch name (often encodes the phase: `feature/phase-5`, `research/hld`, etc.)
   - Latest commits (last 10–20) and their messages (look for phase markers, checkpoints, status updates)
   - Uncommitted changes (`git status --porcelain`)
   - Remote status (behind/ahead of origin)

2. **Artifact inventory**
   - `MASTER_RESEARCH_PLAN.md` or similar (if present) — defines the staged workflow
   - `CLAUDE.md` (project-specific instructions)
   - Phase-specific docs: `research/`, `design/`, `.data/requirements/`, `src/`
   - Task list or checklist files (if present)
   - Previous session plans in `~/.claude/plans/` (most recent edits)
   - **Domain model** — `CONTEXT.md` (domain glossary), `CONTEXT-MAP.md` (multi-context), `docs/adr/` (ADRs written by `/domain-modeling` or `/grill-with-docs`)
   - **Agent skill setup** — `docs/agents/domain.md`, `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` (written by `/setup-skills`; indicate whether engineering skills have been configured)
   - **Requirements pipeline** — `.data/requirements/` holds FS/EARS docs (`*-FS-*.md`), SRS docs (`*-SRS-*.md`), API Definitions (`*-API-Definition-*.md`), and Use Case Diagrams (`*-Use-Case-Diagrams-*.md`) produced by the `/FS-skill`, `/SRS-skill`, and companion skills
   - **Data View** — `.data/output/*-Data-View-*.md` produced by `/data-view-skill` (DynamoDB schema + access patterns)
   - **Issue tracker** — `.scratch/<feature>/issues/*.md` (local markdown issues written by `/to-tickets`)

3. **Completion markers**
   - Look for version numbers or "Approved" / "Final" in doc headers
   - Checkpoint records (e.g., "Checkpoint 3 approved")
   - Status enums: "draft" vs "ready-for-review" vs "approved"
   - Git tags or explicit "phase complete" commits

4. **Blockers & open questions**
   - "FIXME", "TODO", "Open question", "Deferred", "Blocked" in code/docs
   - Uncommitted changes (draft work in progress)
   - Unresolved pull requests or approvals
   - Ambiguity in requirements (marked as provisional or needing clarity)

**Reconnaissance complete when:** all four categories inspected; findings (including "not found" for absent artifacts) recorded.

### Phase 2: Triage to a Stage

Map findings to exactly one workflow stage. This is the **triage** step — assign the project to a single current position:

- **Preflight / discovery** — No artifacts yet; project is new or in planning phase
- **Setup complete** — `docs/agents/` written (setup-skills ran), `CONTEXT.md` created; requirements work not yet started
- **FS in progress / complete** — FS/EARS docs exist in `.data/requirements/`; SRS not yet started
- **SRS in progress / complete** — SRS doc exists; API Definition and/or Use Case Diagrams may also exist; Data View not yet done
- **Data View complete** — `.data/output/*-Data-View-*.md` exists; requirements pipeline is fully done; design/implementation not yet started
- **Design / architecture** — Design docs / ADRs exist; implementation not yet started
- **Implementation in progress** — Code written; tests or reviews pending; issues may be tracked in `.scratch/`
- **Implementation complete** — All features done; testing/review phase
- **Release / polish** — Features frozen; bug fixes and documentation
- **Post-mortem / wrap-up** — Shipped; retrospective or lessons-learned phase

**Triage complete when:** a single stage assigned; evidence for it stateable in one sentence (e.g., "SRS exists, Data View not yet started").

### Phase 3: Propose Next Actions

Based on the stage, propose 2–4 options:

| Stage | Typical Next Actions |
|-------|---|
| Preflight | Run `/setup-skills` to configure engineering skills, start requirements discovery, define scope |
| Setup complete | Run `/FS-skill` to write Feature Set requirements; start `CONTEXT.md` via `/domain-modeling` |
| FS in progress / complete | Run `/SRS-skill` to transform FS into SRS + API Definition + Use Case Diagrams |
| SRS in progress / complete | Run `/data-view-skill` to produce Data View; review/refine SRS or API Definition |
| Data View complete | Move to design — run `/to-spec` for PRD, create ADRs via `/domain-modeling` |
| Design / architecture | Run `/to-tickets` to break spec into issues; scaffold implementation |
| Implementation in progress | Continue feature work; review open issues in `.scratch/`; resolve blockers |
| Implementation complete | Run full test suite, document, prepare release |
| Release | Deploy, monitor, fix critical issues |
| Post-mortem | Write retrospective, update playbooks, plan next phase |

**Options drafted when:** 2–4 options written, each with a label, a one-line description, and any blockers or prerequisites called out.

### Phase 4: Present to User

Ask the user which direction to take using a **choice prompt** (2–4 options). Each option includes:
- A short label (e.g., "Continue Phase 5 (Data View)")
- A description of what that work involves
- Any prerequisites or blockers

Example:

> **What should we do next?**
>
> 1. **Continue Phase 5.3 (Data View)** — Write the Postgres schema design doc. You have a draft plan at `~/.claude/plans/data-view-postgres-design.md`; convert it to `ProTrading-Data-View-1.0.md` in `.data/requirements/` and commit.
> 2. **Jump to Phase 6 (Implementation planning)** — If you want to skip the Data View doc, go straight to planning the backend code structure. Requires: read the SRS and API Definition first.
> 3. **Review & refine the SRS** — Spend time improving the spec before moving to implementation. Current SRS is v1.1; consider edge cases and validation rules.

**Presentation complete when:** user picks one option; session pivots to that work.

## Autonomous Workflow

When invoked in **autonomous mode**, identify the next incomplete phase and drive it to a committed, fully-tested state, iterating on failures without surfacing to the user unless genuinely blocked.

**The mission:** implement the next incomplete phase from the project spec, fully test it, and commit it — iterating until tests pass without asking for help unless truly blocked.

Track progress with `TaskCreate`/`TaskUpdate`. Follow the six steps:

1. **Discover State** — Read `CLAUDE.md`, the task/state file, and `git log --oneline -10`. Identify the next incomplete phase and its requirements.
2. **Plan with Critic** — Write a detailed plan to the task file. Critique it for spec violations, missing edge cases, and API mismatches with existing code. Revise until sound. Prefer `/critic` for non-trivial phases.
3. **Implement** — Fan out to sub-agents for 3+ independent files; instruct each to write and pass its own tests without touching shared files. Run a reconciliation pass after fan-out.
4. **Test and Self-Heal** — Run the full suite. On failure: read output → root cause → minimal fix → re-run. Repeat up to **5 cycles**. Surface only if cycles are exhausted or a genuine product decision is required.
5. **Commit** — Stage ALL changes (`git status` first — modified files, renames, and new files); commit: `feat: [phase] — [N] files, [M] tests passing, [K] new tests added`.
6. **Update State + Hand Off** — Mark phase complete in the task file. Ask: *"Phase X complete. Shall I proceed to Phase Y autonomously?"*

**Guardrails:** fail-closed on safety gates (a failing safety test means the implementation is wrong); no `--no-verify` or destructive git; resolve ambiguity by reading specs/code before asking.

Full step-by-step reference with a worked self-heal example: [docs/autonomous-mode.md](docs/autonomous-mode.md)

## Implementation Notes

### Scripts & Deterministic Parts

Use simple bash inspection for:

```bash
# Git state
git rev-parse --abbrev-ref HEAD          # current branch
git log --oneline -10                    # recent commits
git status --porcelain                   # uncommitted changes
git rev-parse HEAD                       # current SHA

# File inventory
find . -name "MASTER_*PLAN*.md" -o -name "*Phase*.md" -o -name "*Checkpoint*.md"
ls -la research/ design/ .data/requirements/ .data/output/ src/ 2>/dev/null
stat -f %Sm -t %Y-%m-%d ~/.claude/plans/*.md | sort -rk1 | head -5
# Domain model & ADRs
ls CONTEXT.md CONTEXT-MAP.md docs/adr/ 2>/dev/null
# Agent skill setup
ls docs/agents/ 2>/dev/null
# Issue tracker
find .scratch -name "*.md" 2>/dev/null | head -10

# Grep for markers
grep -r "status.*approved\|checkpoint\|phase.*complete" *.md 2>/dev/null
grep -r "TODO\|FIXME\|Open question\|Deferred" --include="*.md" --include="*.py" --include="*.ts" 2>/dev/null
```

Keep this output concise — summarize findings, don't dump raw output into context.

### User Interaction

Use `AskUserQuestion` to present options:

```json
{
  "questions": [{
    "question": "Where should we pick up? (Choose one)",
    "header": "Next Steps",
    "multiSelect": false,
    "options": [
      {
        "label": "Option A",
        "description": "What this involves and why you might choose it"
      },
      {
        "label": "Option B",
        "description": "Alternative direction with different tradeoffs"
      }
    ]
  }]
}
```

### Handling Ambiguous State

If state is ambiguous — no artifacts found, many uncommitted changes, or unresolved questions blocking progress — see [EDGE-CASES.md](EDGE-CASES.md).

## Example Execution

**User command:**
```
/continue
```

**Skill discovers:**
- Current branch: `research/hld-artifacts`
- Last commit: `a8ea47f Phase 5.2 — Convert ASCII diagrams to PlantUML` (2 commits ago)
- Artifacts: `MASTER_RESEARCH_PLAN.md` (defines phases), `research/` (HLD), `.data/requirements/` (FS, SRS, API, Use Cases)
- Git status: clean (no uncommitted changes)
- Marker scan: No Data View doc yet (Phase 5.3 not done)

**Skill proposes:**
```
What's next? (You're partway through Phase 5.)

1. Continue Phase 5.3 (Data View) — Write the Postgres schema design doc.
   Draft exists at ~/.claude/plans/data-view-postgres-design.md
   
2. Jump to Phase 6 (Implementation planning) — Skip the Data View design doc,
   go straight to planning the backend implementation. Requires re-reading SRS.
   
3. Review & refine the SRS — Polish the spec before moving forward.
```

**User picks option 1**, and the session continues with that work.

## Edge Cases

For known limitations and troubleshooting guidance, see [EDGE-CASES.md](EDGE-CASES.md).
