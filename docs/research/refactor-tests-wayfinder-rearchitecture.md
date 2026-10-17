# Research: Should refactor-tests adopt wayfinder's tracker-issue-plus-sub-issues architecture?

**Date:** 2026-10-16
**Outcome:** ADR-0079 adopted Option C with one change: Step 11 publishes by default, with `--no-publish-review` as the opt-out. The ADR's decisions override the sketch in section 5.
**Scope:** `skills/engineering/refactor-tests/` (SKILL.md, reference/patterns.md, reference/springboot.md, reference/python/*.py); `skills/engineering/wayfinder/SKILL.md`; `skills/engineering/to-tickets/SKILL.md`; `docs/agents/{skill-authoring,skill-dependencies,issue-tracker,triage-labels,hooks,domain}.md`; ADR-0040, ADR-0041; GitHub issues #20, #32, #112, #119, #128. External: GitHub docs on sub-issue limits and REST secondary rate limits.

Location note: this repo keeps research notes in `docs/research/` (e.g. `docs/research/refactor-tests-coverage-speed-deep-modules.md`), so this file follows that convention. `GLOSSARY.md` has no entries for ledger, wayfinder, or tracker, and `.data/requirements/` is empty, so neither constrains this question.

---

## Verdict

**Do not re-architect refactor-tests around a tracking issue with sub-issues.** It is feasible mechanically, but it fits badly. refactor-tests is a single-run, mechanical, suite-gated executor whose units of work are only valid as a batch. Wayfinder is a multi-session *decision* planner whose units are independent questions resolved one per session. Moving refactor-tests' state into GitHub would duplicate a ledger that already gives crash-safe resume, multiply full-suite runs, and add a hard `gh` dependency to a skill that runs on arbitrary local projects.

**Do add a narrow, optional hybrid:** after the run, publish the *human-review queue* (the items the skill already refuses to act on and hands to "the user decides") as tickets through the existing `/to-tickets` pipeline. The ledger stays the source of truth for execution. Effort: about 1 to 2 days. A full re-architecture is about 1.5 to 3 weeks and loses guarantees.

---

## 1. refactor-tests today

### 1.1 Shape of the run

- Three phases, each behind a suite-wide health gate: Phase A layout, Phase B simplification, Phase C Spring context cost (`skills/engineering/refactor-tests/SKILL.md:11-14`). A gate is healthy when zero baseline-passing tests now fail; a regressed gate stops the run (`SKILL.md:16`).
- Steps run in a fixed sequence: Step 1 resolve/resume (`SKILL.md:47-55`), Step 2 discovery writes `plan.json` (`SKILL.md:59-72`), Step 3 baseline (`SKILL.md:76-88`), Steps 4-6 move/rewrite/validate (`SKILL.md:94-123`), Step 7 evidence pass (`SKILL.md:147-179`), Step 7b seam classification (`SKILL.md:183-199`), Step 8 plan (`SKILL.md:203-229`), Step 8b random-order gate (`SKILL.md:231-258`), Step 9 execute (`SKILL.md:260-275`), Step 10 validate (`SKILL.md:277-295`), Phase C Steps C0-C4 (`SKILL.md:299-310`, `reference/springboot.md:73-214`).
- It is one invocation, not one-unit-per-session: the only user round is the seam confirmation, "one round per run" (`SKILL.md:194`). It also runs unattended: with no user, seams stay `proposed` (`SKILL.md:194`).
- It never commits: "Leave every change in the working tree for the user to review and commit" (`SKILL.md:31`).
- The frontmatter has no `disable-model-invocation` (`SKILL.md:1-5`), so the model can invoke it; wayfinder is user-invoked only (`skills/engineering/wayfinder/SKILL.md:4`).

### 1.2 State and resumability

- Durable state lives under `$PROJECT_PATH/.scratch/refactor-tests/`: `ledger.json`, `plan.json`, `baseline-ids.json`, `simplification-plan.json`, `test-evidence.json`, `order-gate.json` (`reference/patterns.md:131-201`, `SKILL.md:229`, `SKILL.md:253`).
- The ledger is rewritten "after every durable side effect so a mid-run compaction is recoverable" (`SKILL.md:32`). Its `phase` enum has 19 values (`reference/patterns.md:135`).
- Resume is per-step and fine-grained: Step 1 resumes from the recorded phase and archives completed or failed ledgers with timestamps (`SKILL.md:51`); evidence status per language is final (`SKILL.md:151`); seam `confirmed` is final (`SKILL.md:191`); order-gate status and seed are reused (`SKILL.md:235`, `SKILL.md:239`); Step 9 skips applied removals and parametrizations and detects writes that landed before a crash (`SKILL.md:268-275`). The Step 9 rule was added recently by issue #128 ("If the run crashes mid-step and is resumed, the removals run again", `gh issue view 128`) and commit `fa62a0f`.
- Atomic writes: `write_atomic` writes a temp file then `os.replace` (`reference/python/refactor_tests_shared.py:31-37`); each parametrization is "a single atomic file write; ledger entry written in the same durable step" (`SKILL.md:30`).
- `id_basis` (`post-layout` vs `pre-layout`) ties the evidence file to the tree its ids came from, and `assemble_evidence.py` refuses to merge a mismatched file (`SKILL.md:172`, `reference/patterns.md:398`).

### 1.3 Units of work and outputs

| Unit | Where produced | Who acts |
|---|---|---|
| File move (regular / cross-cutting) | `plan.json` `moves`, `cross_cutting` (`SKILL.md:65-72`) | Skill, automatically |
| Import rewrite | `plan.json` `rewrites` (`SKILL.md:109-112`) | Skill |
| Removal (exact-duplicate, trivially-true) | `simplification-plan.json` `removals` (`SKILL.md:211`) | Skill |
| Parametrize consolidation | `simplification-plan.json` (`SKILL.md:225-227`) | Skill |
| Review candidates: dead-test, coverage-subset, cost, pinning, order-dependent, flaky | `review_candidates` (`SKILL.md:213`, `221-223`, `197`, `248`) | **Human** ("user decides", `SKILL.md:213`, `341`) |
| Add candidates (confirmed seams no interface test reaches) | `seams.add_candidates`, reported only (`SKILL.md:197`) | **Human** |
| Skipped parametrizations, AST warnings | ledger `warnings`, `parametrizations[].skipped` (`SKILL.md:111`, `266`) | **Human** |
| Spring cluster consolidation / skipped cluster / C3 switches | ledger `spring.consolidations`, report (`reference/springboot.md:115`, `161`, `212`) | Skill; skipped clusters to human |

The skill's output is a working-tree diff plus the Final report (`SKILL.md:324-356`). The report is the only place review candidates and add candidates go. Nothing tracks whether the human ever acted on them.

### 1.4 Cross-skill contracts that bound any change

- `refactor-tests` → `codebase-design` + `tdd` (seam quote) (`docs/agents/skill-dependencies.md:12`).
- `testing` → `refactor-tests` path templates in `reference/patterns.md` (`docs/agents/skill-dependencies.md:13`).
- Audio cues: multi-turn skills call `say_skill_start` / `say_skill_done` / `say_skill_cancel` on every exit (`docs/agents/hooks.md:5-7`; `SKILL.md:35`, `39-43`, `360-367`).

None of these touches tracker state, so a tracker integration would add a new dependency rather than break an existing one.

---

## 2. Wayfinder's approach, precisely

- **Map** = one issue labelled `wayfinder:map`; tickets are child issues (`wayfinder/SKILL.md:27`). The map is "an index, not a store" (`wayfinder/SKILL.md:29`). Body sections: Destination, Notes, Decisions so far, Not yet specified, Out of scope (`wayfinder/SKILL.md:37-59`).
- **Physical form is tracker-specific**, read from the tracker doc's "Wayfinding operations"; with no tracker it defaults to local markdown (`wayfinder/SKILL.md:31`). On GitHub: `gh issue create --label wayfinder:map`; children via `gh issue create --parent` or `gh issue edit <parent> --add-sub-issue` (gh 2.94+), else REST `POST .../issues/<parent>/sub_issues -F sub_issue_id=<db-id>`, else `Part of #<parent>` (`docs/agents/issue-tracker.md:11`, `43-44`).
- **Labels:** `wayfinder:<type>` with type `research`/`prototype`/`grilling`/`task`, never triage labels on decision tickets (`wayfinder/SKILL.md:71`). Execution-map children are `/to-tickets` slices labelled `ready-for-agent` (`wayfinder/SKILL.md:15`, `71`).
- **Blocking:** GitHub native issue dependencies via `POST .../issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, fallback `Blocked by:` line (`docs/agents/issue-tracker.md:46`; `wayfinder/SKILL.md:75`). Edges are wired in a second pass after ids exist (`wayfinder/SKILL.md:120`).
- **Claim / frontier:** claim = assign to self, first write (`wayfinder/SKILL.md:73`; `issue-tracker.md:48`). Frontier = open, unblocked, unassigned children (`wayfinder/SKILL.md:75`; `issue-tracker.md:47`).
- **Pace:** "never resolve more than one ticket per session", research excepted (`wayfinder/SKILL.md:111`); stop after each ticket (`wayfinder/SKILL.md:137`).
- **Resolve:** composed comment (answer + `## Followups` tagged `[impl]`/`[map]`/`[defer]`), close, append pointer to the map (`wayfinder/SKILL.md:131`, `145-164`; `issue-tracker.md:49`).
- **Purpose:** "Plan, don't do"; tickets resolve decisions, not build slices (`wayfinder/SKILL.md:11-13`). Build work is handed to an execution map published via `Skill("to-tickets", ...)` and worked with `/implement` (`wayfinder/SKILL.md:181-204`).
- **Resumability** comes from the tracker itself: map body, open children, assignees, and the handoff's adopt-or-create rule for an orphaned successor (`wayfinder/SKILL.md:128`, `168-170`, `182`).

---

## 3. Fit analysis

### 3.1 Mapping refactor-tests units onto sub-issues

| Unit | Sub-issue fit | Reason |
|---|---|---|
| Per-file / per-package moves | **Poor** | Moves are only judged as a batch: Step 6 re-runs the full suite and checks every baseline id through `id_map` (`SKILL.md:116-123`). A per-package ticket would need its own full-suite gate run, or would close before its health is known. Moves are mechanical (`git mv` + AST rewrite, `SKILL.md:100`, `110`); there is no decision to record. |
| Removals, parametrizations | **Poor** | Already planned, evidence-gated, order-gated, then applied with ledger-level idempotency (`SKILL.md:248-275`). A ticket per removal adds no information the plan entry lacks. |
| Evidence pass, order gate | **None** | Single suite-wide runs whose output feeds later steps (`SKILL.md:155-172`, `240-247`). |
| Seam confirmation | **Weak** | One HITL round per run, per module (`SKILL.md:194`). Could be a grilling-style ticket, but it blocks Step 7b item 3 within the same run, so an async ticket stalls the run. |
| Review candidates (dead-test, coverage-subset, cost, pinning, order-dependent, flaky) | **Good** | The skill already refuses to act and hands them to a human (`SKILL.md:138-141`, `197`, `213`, `341`). Each one is a standalone decision or small fix. Today they evaporate after the report. |
| Add candidates (untested seams) | **Good** | "The skill writes no new tests: `add_candidates` are reported only" (`SKILL.md:197`). Each is a natural `/tdd` or `/implement` slice. |
| Skipped parametrizations, skipped Spring clusters, AST failures | **Good** | Human-resolution items surfaced only in the report (`SKILL.md:266`, `reference/springboot.md:115`, `212`). |
| Phase C cluster consolidations | **Poor to moderate** | Each cluster is an atomic per-class rewrite (`reference/springboot.md:153-161`), but C4's gate is suite-wide and has four MUST-PASS checks (`reference/springboot.md:201-212`). |

The split is clean: everything the skill **does** is a poor fit; everything the skill **hands to a human** is a good fit.

### 3.2 Conceptual mismatches with wayfinder

1. **Decision vs execution.** Wayfinder's tickets are decisions; build work belongs to an execution map of `/to-tickets` slices (`wayfinder/SKILL.md:11-15`). refactor-tests' automated work is neither: it is a deterministic batch with no per-unit decision.
2. **Pace.** One ticket per session (`wayfinder/SKILL.md:111`) against a skill designed to finish in one run with one user round (`SKILL.md:194`). A 200-move plan becomes 200 sessions, or the rule is ignored and the tickets are noise.
3. **Gate granularity.** Health is defined on the whole suite against a baseline (`SKILL.md:16`, `118`, `281`). Sub-issue closure would need either per-ticket full-suite runs (cost) or tickets closed before they are known healthy (false audit trail).
4. **Commit model.** refactor-tests never commits (`SKILL.md:31`). Issue-driven execution in this repo pairs a ticket with a commit and PR (`docs/agents/skill-dependencies.md:17`, `/implement` → `pr`). Closing a ticket against an uncommitted working tree has no durable anchor.
5. **Precedent already exists at the right layer.** refactor-tests itself was designed and rebuilt through wayfinder maps: #20 (`wayfinder: test-layout-refactor skill + selective runner`, label `wayfinder:map`) and #112 → execution map #119 with sub-issues #120-#125 (`gh issue view 119 --json subIssues`). Wayfinder already serves the *development of the skill*; it does not need to live inside the skill's *runtime*.

### 3.3 Benefits a tracker would bring

- **Audit trail and follow-through for the review queue**: today review/add candidates exist only in the Final report (`SKILL.md:341-345`). Tickets give them owners, state, and closure.
- **Parallelism for human work**: review candidates are independent; the frontier/claim model (`issue-tracker.md:47-48`) lets several sessions or people work them.
- **Visibility for teams**: native blocking renders the frontier in the GitHub UI (`wayfinder/SKILL.md:75`).
- Resumability is **not** a benefit: the ledger already covers it at finer grain than issues can (`SKILL.md:32`, `51`, `268-275`).

### 3.4 Costs

- **Hard dependency on GitHub and `gh` in the target repo.** refactor-tests runs on any `PROJECT_PATH` (`SKILL.md:9`, `49`). Tracker operations come from that repo's `docs/agents/issue-tracker.md`, written by `/setup-skills`; `to-tickets` stops without it (`docs/agents/skill-dependencies.md:14-15`). Many target repos (scratch clones, private mirrors, GitLab) would lack it.
- **Rate and size limits.** GitHub allows "up to 100 sub-issues per parent issue" and eight nesting levels (https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues), and secondary limits of "no more than 80 content-generating requests per minute and no more than 500 content-generating requests per hour" (https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api). Each sub-issue costs at least two writes (create + link), plus one per blocking edge (`issue-tracker.md:11`, `46`). A per-move or per-removal ticketing of a medium suite crosses 100 children and can hit the hourly cap.
- **No idempotent publish yet.** Real-tracker publish is stop-and-report on partial failure; resume/idempotency-by-slug is deferred (ADR-0040 "On partial failure (real tracker): stop and report, do not roll back"; ADR-0041 "Status: proposed / deferred"; `to-tickets/SKILL.md:148`). Only the sub-issue pass is idempotent (`to-tickets/SKILL.md:149`). A crash mid-publish of many tickets needs manual cleanup, which is worse than the current ledger resume.
- **Duplicate source of truth.** Ledger + issues must agree; every resume rule (`SKILL.md:51`, `151`, `191`, `235`, `268-275`) would need a tracker reconciliation step.
- **Evidence size.** `test-evidence.json` holds per-test line and arc maps (`reference/patterns.md:366-396`). It cannot go into issue bodies; tickets can only carry the ≤2-line `evidence` excerpt and `call_s`/`time_saved_s` fields the plan already has (`SKILL.md:211`, `222-223`), and link to local files that other people cannot see.
- **Token and latency cost**: each `gh` call and each issue body is agent output and tool output re-read per turn; wayfinder accepts this because it spans sessions, refactor-tests does not need to.
- **Contract additions**: a new `refactor-tests` → `setup-skills` / `to-tickets` edge in `docs/agents/skill-dependencies.md`; a hard dependency in the core path would also change model-invocation behaviour, since an auto-invoked skill would start creating public issues.

### 3.5 Migration effort for a full re-architecture

Files that change: `SKILL.md` (all of Steps 1, 4-6, 9-10, Final report, Hard Invariants: about 368 lines, `wc -l`), `reference/patterns.md` (ledger schema `131-183` plus a tracker-mapping schema), `reference/springboot.md` C2/C4 bookkeeping (`161`, `199-214`), new helper(s) to render tickets from plan/ledger plus tests in `reference/python/tests/`, `docs/agents/skill-dependencies.md`. The Python helpers (`assemble_evidence.py`, `classify_seams.py`, `order_gate.py`, `select_candidates.py`, `calltime_delta.py`) are independent of the orchestration and would not change. The hard parts are designing per-ticket gates and two-way ledger/tracker reconciliation, which have no existing design (ADR-0041 is still deferred). Estimate: **1.5 to 3 weeks**, with a likely wayfinder decision map of its own, and a net loss of the "one run, suite-gated, nothing committed" guarantees.

---

## 4. Alternatives

| Option | Description | Effort | Assessment |
|---|---|---|---|
| A. Full re-architecture | Map issue per run, sub-issue per move/removal/cluster, closed by the skill | 1.5-3 weeks | Reject: see 3.2 and 3.4. |
| B. Wayfinder wraps refactor-tests | Run `/wayfinder` on "refactor this project's tests"; tickets are decisions (scope, seam confirmation, Phase C go/no-go) and one `task` ticket runs `/refactor-tests` | 0 (usage only) | Already possible today; useful only for large, multi-team efforts. Document as a usage pattern if wanted. |
| C. Hybrid publish of the review queue (recommended) | Optional final step, `--publish-review`, turns the human-only items into a manifest and hands it to `/to-tickets` | 1-2 days | Fits: targets the exact gap (items with no follow-through), reuses the critic-reviewed publish path, keeps ledger as truth, degrades to the local tracker. |
| D. Local-only review file | Write `.scratch/refactor-tests/review-queue.md` as a checklist | ~0.5 day | Cheapest; no tracker, no audit trail beyond the working tree. A good first increment toward C. |

---

## 5. Recommendation and design sketch (Option C)

**Principle:** the ledger stays the single source of truth for everything the skill executes. The tracker receives only what a human must decide, after the run finishes healthy (or after `--dry-run`).

1. **Trigger.** New flag `--publish-review` parsed in Step 1 (`SKILL.md:50`). Off by default, so model invocation never creates issues unprompted, and runs on repos without a tracker behave exactly as today.
2. **Step 11 — Publish review queue** (after Step 10 healthy or Phase C done, or after the `--dry-run` exit point in `SKILL.md:33`):
   - A new helper `reference/python/render_review_queue.py` reads `simplification-plan.json`, `ledger.json`, and `order-gate.json` and writes to-tickets-shaped drafts under `.scratch/refactor-tests-review/draft-issues/<NN>-<slug>.md` plus `manifest.md` with `artifact-type: tickets` frontmatter (the shape `to-tickets/SKILL.md:41` expects). Use `write_atomic` from `refactor_tests_shared.py:31-37` for JSON outputs.
   - **Granularity: one ticket per group, not per test.** Group by `criterion` and module, e.g. "Review 7 coverage-subset tests in `src/pkg/adapters` (4.2 s serial)", "Add interface tests for 3 untested seams in `instruments.py`", "Fix 2 order-dependent tests (seed 1234567)". This keeps a typical run under ~20 tickets, far below the 100-sub-issue cap and the rate limits.
   - Body: criterion, test ids, ≤2-line evidence excerpts, `call_s`/`time_saved_s`, seed and `failing_ids` for order/flaky (fields already in the plan, `reference/patterns.md:263-275`). No raw coverage maps.
   - Labels: `ready-for-human` for review-only removals (pinning, coverage-subset, cost, dead-test) since the skill's rule is that a human decides (`SKILL.md:138-141`); `ready-for-agent` for add candidates and order-dependent fixes, which are `/tdd`/`/implement` slices (`docs/agents/triage-labels.md:9-10`). Do not use `wayfinder:*` labels: these are not decision-map tickets (`wayfinder/SKILL.md:71`).
   - Blocking: order-dependent/flaky tickets block the review tickets that touch the same tests, because the gate demoted those changes (`SKILL.md:248`).
3. **Publish via `Skill("to-tickets", ...)`**, following the programmatic hand-off convention (`docs/agents/skill-authoring.md:28`). This reuses the critic loop, create-then-link ordering, the local-tracker fallback, and the optional parent pass (`to-tickets/SKILL.md:135-149`). If a parent tracking issue is wanted, create one "Test-suite review: <project> <date>" issue first and pass it as the source, so pass 3 makes the tickets its sub-issues (`to-tickets/SKILL.md:149`).
4. **Ledger.** Record `publish: { status, manifest, tickets: [ids] }`, with the same final-status resume rule as evidence and the order gate (`SKILL.md:151`, `235`). A status of `failed` never changes the run's health result.
5. **Report.** Final report gains one line with the ticket URLs or the local `issues/` path.
6. **Contracts.** Add to `docs/agents/skill-dependencies.md`: `engineering/refactor-tests` → `engineering/to-tickets` (optional, only with `--publish-review`), inheriting to-tickets' `setup-skills` requirement (`skill-dependencies.md:15`). Multi-turn audio cues already cover the extra step (`docs/agents/hooks.md:5-7`).

**Effort:** helper plus tests about 0.5-1 day (pattern matches existing `select_candidates.py` and its tests); SKILL.md, patterns.md schema, and skill-dependencies.md edits about 0.5 day; one validation run on a reference project about 0.5 day. **Total 1 to 2 days.** Option D alone is about half a day and can ship first.

**Revisit** a deeper integration only if ADR-0041 (idempotent publish) lands and a real need appears for multi-session execution of Phase A or C on very large suites.
