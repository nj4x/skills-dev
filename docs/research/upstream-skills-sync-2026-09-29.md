# Upstream skills sync — `mattpocock/skills` → `skills-dev` (2026-09-29)

| | |
|---|---|
| Upstream repo | `/Users/roman/projects/skills` — `https://github.com/mattpocock/skills.git` |
| Upstream HEAD | `d81f3a1` (2026-09-29, "Merge pull request #1120 from mattpocock/release/v1.3") |
| Local repo | `/Users/roman/projects/skills-dev` — `https://github.com/nj4x/skills-dev.git` |
| Local HEAD | `ec0bba5` (2026-09-21) |
| Last recorded sync baseline | `0ab1b63` (2026-08-20, "grilling: separate questions in a round with an HR"); further syncs at `8b36d4f..0ab1b63` (2026-08-20) and `d2945f3..c612def` (2026-09-24) for three skills: implement-spec, pr, retro |
| Unsynced upstream range | `0ab1b63..d81f3a1` — 42 commits (non-merge), 34 of which touch files under `skills/` |

---

## Sync status

skills-dev last pulled upstream code-review, diagnosing-bugs, domain-modeling, grilling, wait-what, and others at `0ab1b63` (2026-08-20). Since then, the three big ported skills — implement-spec, pr, retro — have shipped in-progress (up to `c612def`, 2026-09-24) and then graduated to `engineering/` with preconditions and clarity edits. skills-dev ported them on 2026-09-20 (commit e5008ea) at an intermediate point (`84b5ee5`, `c55ee46`, `0243b6e`), then moved them into `skills/` on 2026-09-21 (commit 7ceb737) and added implement-spec preconditions. The local versions are now stale on three fronts:

1. **implement-spec** (lines 8–38, step descriptions): Upstream evolved the goal statement and step details after skills-dev's port. skills-dev has a custom Preconditions section (good) with no matching upstream equivalent (as of d81f3a1).
2. **pr** SKILL.md (domain language ref): Upstream changed from "CONTEXT.md" to "GLOSSARY.md" on 2026-08-15 (d80fa0f). skills-dev kept "CONTEXT.md". Also CREDITS.md attribution text was refined in a7d038f.
3. **retro** SKILL.md: Upstream is at engineering/retro, skills-dev at session/retro. No substantive skill changes after d6654f6b (2026-08-24), but **Automated checks** section merits review against skills-dev `engineering/refactor-tests` and existing guardrail patterns.
4. **diagnosing-bugs**: Upstream changed CONTEXT.md ref to GLOSSARY.md (d81f3a1 shows diff vs 0ab1b63); also carries the Redact section from the 2026-08 sync.
5. **domain-modeling**: CONTEXT.md → GLOSSARY.md rename across description and body (d80fa0f).

---

## Summary table

| Upstream change | Upstream commit(s) | Skills-dev target file | Classification | Priority |
|---|---|---|---|---|
| implement-spec goal & step rewording | 153fc1b, a31f3f6, c612def | skills/engineering/implement-spec/SKILL.md | **Adapt** | High |
| implement-spec Preconditions (local-only) | ec0bba5 (skills-dev) | skills/engineering/implement-spec/SKILL.md | **Port** | High |
| pr GLOSSARY.md ref (domain language) | d80fa0f, d2945f3 | skills/publishing/pr/SKILL.md | **Adapt** | Medium |
| pr component tree example formatter fix | a7d038f | skills/publishing/pr/SKILL.md | **Port** | Low |
| pr CREDITS.md refinement | a7d038f | skills/publishing/pr/CREDITS.md | **Port** | Low |
| retro placement in workflow | 389f5d2, 9781ce1, b1f3390 | engineering/ask-matt (docs, not retro skill) | **Skip** | N/A |
| retro deterministic-checks classification | 0243b6e | skills/session/retro/SKILL.md | **Adapt** | Medium |
| diagnosing-bugs GLOSSARY.md ref | d81f3a1 | engineering/diagnosing-bugs/SKILL.md | **Adapt** | Medium |
| domain-modeling GLOSSARY.md rename | d80fa0f | engineering/domain-modeling/SKILL.md | **Adapt** | Low |
| GLOSSARY.md convention (repo-wide) | d80fa0f, 006a52b, b1f3390 | — | **Skip** | — |

---

## Detailed recommendations

### 1. **implement-spec goal and step rewording** (153fc1b, a31f3f6, c612def)

**Status**: Stale in skills-dev. Port with local Preconditions.

**What changed upstream**:
- `153fc1b` (2026-09-24) — Goal statement clarified: "The goal is the entire spec implemented on a single **integration branch**, with every ticket resolved the way the issue tracker closes work." Introducers "The issue tracker should have been provided to you. If not, tell the user to run `/setup-matt-pocock-skills`." And step descriptions now reference "integration branch" and expect implementer subagents to call `Skill tool with tdd`, confirm worktree base, and merge the integration tip before reporting.
- `a31f3f6` (2026-09-24) — Two clarity edits: "Read the spec and tickets to understand the task graph" (remove "Read enough to"). "merges the integration branch tip into its own branch before reporting done" (remove "so step 5 is a fast-forward").
- `c612def` (2026-09-24) — Description changed from "Implement a specification in code" to "Implement the result of /to-spec and /to-tickets in code" to link it to the upstreamskill chain. openai.yaml short_description also changed.

**skills-dev state**: 
- skills-dev commit e5008ea (2026-09-20) ported at `84b5ee5` (2026-08-21), which predates all three commits above. 
- skills-dev commit ec0bba5 (2026-09-21) *added* a local Preconditions section (good; upstream has none).
- Current skills-dev SKILL.md has old goal statement and step names; openai.yaml has old description.

**Action**: 
1. Adopt upstream goal statement, step rewording, and description.
2. **Keep** the local Preconditions section (lines 17–27 in current local SKILL.md) — it's load-bearing for skills-dev's `.scratch/<feature-slug>/` staging and GitHub Issues tracker model. Upstream has no tracker setup, so no parallel section.
3. Amend Preconditions to note that step 4 now requires implementer subagents to call `Skill tool with tdd` (upstream calls it a hand-off requirement; skills-dev should verify consistency with `engineering/tdd/SKILL.md`).
4. Update `openai.yaml` description to match upstream: `"Implement the result of /to-spec and /to-tickets in code."`.

**File path**: `/Users/roman/projects/skills-dev/skills/engineering/implement-spec/SKILL.md` (lines 8–38, 40–43) and `/Users/roman/projects/skills-dev/skills/engineering/implement-spec/agents/openai.yaml` (line 3).

---

### 2. **pr GLOSSARY.md convention** (d80fa0f, d2945f3)

**Status**: Stale. Adapt to skills-dev's naming choice or update domain reference.

**What changed upstream**:
- `d80fa0f` (2026-08-15, commit c612def to repo's CONTEXT.md) — Renamed the repo's `CONTEXT.md` to `GLOSSARY.md` across all skills and docs. 
- In `pr/SKILL.md` line 37 (Sections > Summary), text changed from "Skip all preambles and keep prose brief" to "Skip all preambles and keep prose brief. Use the user's domain language from `GLOSSARY.md`."

**skills-dev state**: 
- skills-dev `CONTEXT.md` still exists at repo root (no rename). `pr/SKILL.md` still references `CONTEXT.md` ("Use the user's domain language from `CONTEXT.md.`").
- Upstream is now on `GLOSSARY.md` convention; skills-dev has kept `CONTEXT.md`.

**Action**: 
**Adapt**. Skills-dev should decide: (a) adopt the `GLOSSARY.md` rename repo-wide (higher cost, unifies with upstream), or (b) keep `CONTEXT.md` and do not update this reference. If keeping `CONTEXT.md`:
- No change needed to `pr/SKILL.md` — reference already correct for local convention.
- Do **not** port upstream's GLOSSARY.md renames to other skills (diagnosing-bugs, domain-modeling, etc.) until repo-wide decision is made.

**Recommendation**: Keep `CONTEXT.md` for now (lower churn). Note in `docs/agents/skill-authoring.md` that upstream now uses `GLOSSARY.md` and a future sync can revisit.

**File path**: N/A if keeping `CONTEXT.md`; otherwise `/Users/roman/projects/skills-dev/skills/publishing/pr/SKILL.md` line 37.

---

### 3. **pr component tree example formatter fix** (a7d038f)

**Status**: Minor fix. Port.

**What changed upstream**: 
- `a7d038f` (2026-09-24) fixed the component-tree example that had been "mangled by a formatter". The TSX code block's indentation and syntax were corrected.

**Action**: Check skills-dev `skills/publishing/pr/SKILL.md` component tree (around line 68–73). If it matches the old mangled format, apply the formatter fix from a7d038f.

**File path**: `/Users/roman/projects/skills-dev/skills/publishing/pr/SKILL.md` (lines 68–73).

---

### 4. **pr CREDITS.md refinement** (a7d038f)

**Status**: Attribution clarity. Port.

**What changed upstream**: 
- `a7d038f` refined CREDITS.md line 3 from "The **Summary** section's menu of visuals…and its placement guidance…" to "The **Summary** section's menu of visuals (pseudocode, call trees, component trees, file trees, Mermaid, diffs) and its placement guidance…" — slightly more explicit list.

**Action**: Check skills-dev `skills/publishing/pr/CREDITS.md` line 3. If it has the old phrasing, update to the new one.

**File path**: `/Users/roman/projects/skills-dev/skills/publishing/pr/CREDITS.md` (line 3).

---

### 5. **retro deterministic-checks classification** (0243b6e)

**Status**: Refinement. Adapt for skills-dev context.

**What changed upstream**: 
- `0243b6e` (2026-09-15, pre-graduation from in-progress) changed the **Coding standards** section bullet from:
  > "should the **reviewer agent** be given a new rule to enforce?…Reserve `CODING_STANDARDS.md` for genuine **judgement calls**."
  
  To:
  > "should the **reviewer agent** be given a new rule to enforce?…Classify the violation first: a **mechanical** one (a fixed syntactic pattern, a banned API, an import shape, a file-location rule) gets a deterministic check, full stop: a custom rule in the repo's own linter, a new pre-commit hook, or a new CI job, whichever the repo's language and existing guardrail make cheapest. Default to building the check over writing the rule. Reserve `CODING_STANDARDS.md` for genuine **judgement calls**."

This is a high-quality refinement: it tells the agent how to classify and route coding-standards findings toward deterministic checks rather than prose rules.

**skills-dev state**: skills-dev `skills/session/retro/SKILL.md` has the old phrasing (ported from 0243b6e-era upstream, but without this commit's improvements).

**Action**: Adopt the upstream text for the **Coding standards** bullet. Verify consistency with skills-dev `engineering/refactor-tests` (which likely has parallel logic) and `docs/agents/domain.md` sections on guardrails.

**File path**: `/Users/roman/projects/skills-dev/skills/session/retro/SKILL.md` (lines 16–18, Coding standards bullet).

---

### 6. **diagnosing-bugs GLOSSARY.md ref** (d81f3a1 diff vs 0ab1b63)

**Status**: Stale if not yet updated. Adapt per CONTEXT.md decision.

**What changed upstream**: 
- As part of the d80fa0f GLOSSARY.md rename, `skills/engineering/diagnosing-bugs/SKILL.md` line 10 changed from "read `CONTEXT.md` (if it exists)" to "read `GLOSSARY.md` (if it exists)".

**skills-dev state**: skills-dev `engineering/diagnosing-bugs/SKILL.md` still has "CONTEXT.md".

**Action**: If keeping `CONTEXT.md` convention locally, **no change needed**. If adopting `GLOSSARY.md`, update this reference.

**File path**: `/Users/roman/projects/skills-dev/engineering/diagnosing-bugs/SKILL.md` (line 10).

---

### 7. **domain-modeling GLOSSARY.md rename** (d80fa0f)

**Status**: Stale if not yet updated. Adapt per CONTEXT.md decision.

**What changed upstream**: 
- `d80fa0f` renamed all `CONTEXT.md` / `CONTEXT-MAP.md` / `CONTEXT-FORMAT.md` references in domain-modeling to their GLOSSARY counterparts across description, body, and file structure diagrams.

**skills-dev state**: skills-dev `engineering/domain-modeling/SKILL.md` still has `CONTEXT.md` and `CONTEXT-MAP.md`.

**Action**: If keeping `CONTEXT.md` convention locally, **no change needed**. If adopting `GLOSSARY.md`, apply the d80fa0f rename comprehensively to domain-modeling.

**File path**: `/Users/roman/projects/skills-dev/engineering/domain-modeling/SKILL.md` (description, body, diagrams).

---

### 8. **Reject: GLOSSARY.md rename repo-wide** (d80fa0f, 006a52b, b1f3390)

**Status**: Decision point. Skip for now.

**What changed upstream**: 
- `d80fa0f` (2026-08-15) renamed `CONTEXT.md` → `GLOSSARY.md` and updated docs and ADRs.
- `006a52b` (2026-08-15) renamed the upstream repo's own `CONTEXT.md` to `GLOSSARY.md`.
- `b1f3390` (2026-09-24) updated the domain-modeling trigger note changeset to reference GLOSSARY.md.

**Skills-dev decision**: skills-dev has invested in `CONTEXT.md` convention (documented in `docs/agents/domain.md`, used across the repo). A repo-wide rename would touch ~30+ files and diverge further from upstream's convention. **Recommendation**: Defer this decision. Either (1) commit to `CONTEXT.md` permanently and filter these renames in future diffs, or (2) schedule a deliberate `CONTEXT.md` → `GLOSSARY.md` migration sprint. For this sync, leave it as-is.

---

## Open questions for the user

1. **`CONTEXT.md` vs `GLOSSARY.md` naming**: Should skills-dev adopt upstream's `GLOSSARY.md` convention repo-wide? The cost is rewriting ~30 files and docs; the benefit is lower friction in future upstream syncs. Decide now so subsequent skill edits use the chosen name consistently.

2. **`retro` placement**: Upstream graduated retro to `engineering/retro` (a7d038f, 24f41cc) as part of the main workflow (ask-matt, implement-spec, pr routing). skills-dev has it at `session/retro`. Does the placement affect guidance or hand-off semantics? If not, no action needed.

3. **`implement-spec` step 4 and `tdd` integration**: Upstream now explicitly expects step 4 implementer subagents to call `Skill tool with tdd`. Verify skills-dev `engineering/tdd/SKILL.md` has the `tool-invocation-proof` or `model-invocation-proof` that implement-spec subagents can use (not a hard blocker, but good to confirm before the next implement-spec run).

4. **`CODING_STANDARDS.md` vs guardrail checks**: Upstream `retro` now pushes mechanical findings toward deterministic checks, with guidance on classifying violations. Does skills-dev's `refactor-tests` (which also validates standards) use the same classification? If not, align them.

5. **do-once: record GLOSSARY.md rejection decision**: If skills-dev rejects the GLOSSARY.md rename, add a note to `docs/agents/skill-authoring.md` or `docs/adr/` so a future 2027 sync doesn't reopen it.

---

## Counts

- **Port** (mostly verbatim, no adaptation): 3 items (implement-spec Preconditions, pr component tree fix, pr CREDITS.md)
- **Adapt** (idea sound, needs local rework): 4 items (implement-spec rewording, pr GLOSSARY ref, retro deterministic-checks, diagnosing-bugs/domain-modeling GLOSSARY refs)
- **Skip** (local or upstream decision): 2 items (GLOSSARY.md repo-wide rename, retro workflow placement docs)

**Top 3 recommendations**:
1. Adapt implement-spec goal/steps and keep local Preconditions (High priority, unblocks workflow clarity).
2. Decide CONTEXT.md vs GLOSSARY.md once (affects 4 follow-on adaptations; do now, not piecemeal).
3. Adapt retro's deterministic-checks guidance (Medium priority, high quality-of-life improvement for future sessions).
