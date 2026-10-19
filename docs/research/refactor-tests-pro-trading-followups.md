# refactor-tests: follow-ups from the nj4x/pro-trading run of 2026-10-16

## Question

"The user applied the `refactor-tests` skill in the repo nj4x/pro-trading. That run ended with a follow-up execution map: https://github.com/nj4x/pro-trading/issues/836. Identify useful points from that run (lessons, gaps, failure modes, missing steps, ordering problems, evidence/tooling needs) that should be ported into the refactor-tests skill."

## Short answer

The run worked mechanically. It finished at `phase: done`, with evidence `ok` for 10,237 tests, the order gate `ok`, and 3 parametrizations. But its review output could not be acted on as it stood. It flagged 9,358 review entries, which became 765 staged ticket drafts. The user did not publish them. Instead the user ran a separate research pass, and that pass rejected all four "delete the flagged tests" proposals. The pass turned into a 10-ticket execution map (#836). Every ticket on that map works around something the skill does not do.

The ten most important gaps, in priority order:

1. **Coverage-subset is presented as deletable, but it is not.** On one module, 15 of 26 killed mutants were killed only by coverage-subset tests. The review ticket text still offers "remove". The fix: the skill needs a mutation deletion gate, whose slot is already reserved as `kill_set`, or at minimum a hard "never delete on coverage alone" rule in the ticket text.
2. **Cost candidates are not diagnosed.** 84% of the slowest test's time was macOS keychain subprocesses behind every DB connection. A test-side stub, which deletes no test, cut the integration tier from 861.7 s to 89.4 s. The skill should profile the top cost tests and report shared hotspots before it queues per-test cost reviews.
3. **The dead-test vocabulary is too narrow.** 31 of the 33 dead-test flags were deliberate "does not raise" tests. The agent had to widen the vocabulary ad hoc (helper calls named `assert*`, `check*`, `expect*`, `verify*`) in its own scan script.
4. **The seam classifier treats a patched imported collaborator as pinning.** 577 of the 1,813 pinning entries are collaborator-only test doubles. The "covered through the interface" note compares lines only. In a 12-test sample, only 2 of the tests it marked were deletable.
5. **Several workflow gaps:**
   - At this scale, Step 11 has no triage or volume path: 765 drafts, plus a user choice the status table cannot record.
   - `--dry-run` cannot regenerate pinning candidates, but the follow-up tickets depend on it.
   - Confirmed seams are not persisted across runs.
   - There is no committable run summary.
   - The run does not record the commit it ran against.
   - The serial call-time delta is shown without a noise warning.
   - The agent hand-wrote six helper scripts for steps that have no helper.

Details, citations, and proposed wording are below.

## Sources

| Key | Source |
|---|---|
| [MAP] | Execution map, https://github.com/nj4x/pro-trading/issues/836 (body; no comments). Sub-issues #837–#846 via `gh api repos/nj4x/pro-trading/issues/836/sub_issues`. |
| [T01]…[T10] | Tickets https://github.com/nj4x/pro-trading/issues/837 … /846 (bodies and checklists, read 2026-10-17). |
| [PR847] | https://github.com/nj4x/pro-trading/pull/847, merged 2026-10-17, "Land the refactor-tests run …" (body, Merge Danger section). |
| [NOTE] | `docs/research/2026-10-17-test-suite-pruning-automation.md` on pro-trading `main` (fetched with `gh api …/contents/…?ref=main`). Line numbers refer to that file. |
| [RUN] | The run's own artifacts, local only: `/Users/roman/projects/pro-trading/.claude/worktrees/test-refactor/.scratch/refactor-tests/` (`ledger.json`, `simplification-plan.json`, `review-queue.md`, agent-written scripts). Not committed anywhere. |
| [SKILL] | `skills/engineering/refactor-tests/SKILL.md` in this repo (symlinked as `~/.claude/skills/refactor-tests`). |
| [PAT] | `skills/engineering/refactor-tests/reference/patterns.md`. |
| [RRQ] | `skills/engineering/refactor-tests/reference/python/render_review_queue.py`. |

No PRs exist yet for tickets #838–#846. Tickets #838–#841 have "Status: done" in their bodies with ticked checklists, but they are still open. Their worktrees exist locally (`836-integration`, `838-keychain-stub`, `839-cli-health-probes`, `840-dead-test-dispositions`, `841-migration-test-split`, `843-mutation-deletion-check`). Only #837 has a merged PR (#847).

## What the run did

From [RUN] `ledger.json`:

- **Run shape.** `phases_requested: [A, B, C]`, `dry_run: false`, `spring_boot: false`, and the final `phase` is `done`.
- **Phase A.** It moved 0 files. The note says "The tree already mirrors src/protrading; 199 test files are feature-named …". `tests/integration/` was left untouched because of the guard `tests/test_integration_tier_honesty.py`. The directory-guard rule ([PAT]:54) worked.
- **Evidence.** `status: ok` with 10,237 tests. Baseline 11,185 passed, 0 failed.
- **Order gate.** `ok`, using pytest-randomly with seed 180092053. It found 3 order-dependent tests and 0 flaky ones.
- **Plan.** `review_candidates` counts: coverage-subset 7,261, pinning 1,813, cost 251, dead-test 33. Pinning notes: 1,378 "move the assertion to the interface" and 435 "covered through the interface". There were 0 removals and 3 parametrizations.
- **Seams.** `seams.status: confirmed`, 440 modules. The agent's `confirm_seams.py` docstring reads "Mark every proposed seam confirmed (user accepted all)". [NOTE]:214 adds that all 3,599 proposed seams were confirmed, with names and signals unchanged.
- **Call time.** `call_time`: `before_s 1317.47`, `after_s 1184.90`, `delta_s -132.58`, `removed: []`.
- **Publish.** `publish`: `{ status: "local-only", slug: "refactor-tests-review-2026-10-16t20-42-11", note: "user chose queue file only; 765 drafts staged but not published" }`. `review-queue.md` is 2.5 MB.
- **Agent-written scripts.** The agent wrote these in `.scratch/refactor-tests/`: `discover.py` (Step 2), `scan_static.py` (Step 8 static criteria), `build_plan.py` (Step 8 plan assembly), `apply_param.py` (Step 9), `ledger_set.py` (ledger writes), `junit_ids.py`, `confirm_seams.py`, `seams_warnings.py`, `evidence_summary.py`, and `run_coverage.sh` / `run_timing.sh` / `run_gate.sh`.

After the run, the user ran a research pass. Its output was [NOTE], with the verdict "No" on all four deletion proposals ([NOTE]:12-20). The user then built the execution map [MAP]. Its standing rules are "delete nothing on coverage evidence alone", "the mutation deletion check (or the operator watermark, for migrations) gates every deletion", and "collaborator-only pinning tests get their stub re-pointed …, never deleted". Its "Out of scope" section names two skill changes explicitly: "widen its dead-test vocabulary to cover 'does not raise' contracts" and "teach the seam classifier that patching an imported collaborator is a test double, not pinning".

## Findings

Each point is either covered by the skill as it stands (with the file and line) or a gap. Gaps carry a proposed edit in the next section, under the same number.

| # | Point from the run | Source | Skill today | Verdict |
|---|---|---|---|---|
| 1 | Coverage-subset flagged 70.9% of the suite (7,261 of 10,237) across 434 of 443 files. A subset of the union of other tests' coverage is not redundancy: two tests can run the same lines and assert different outputs. | [NOTE]:115-120 | Criterion is "Review only, never removed" ([SKILL]:141). The review ticket says "Decide for each one: keep, rewrite at the interface, or remove" ([RRQ]:213). The final report says "user decides whether to remove" ([SKILL]:370). The End state calls Phase B "redundant unit tests removed" ([SKILL]:13). | **Gap.** Nothing tells the reviewer what the criterion does *not* prove, and the wording invites deletion. |
| 2 | On `classifier.py`, 15 of 26 killed mutants were killed only by coverage-subset-flagged tests. Deleting the flagged set would drop the mutation score from 26/28 to 11/28. Gate rule: "Delete test T only if every mutant T kills is also killed by some kept test." | [NOTE]:124-131, :184; [T07] | `kill_set` is "a reserved top-level key for a later mutation-based check. v1 does not write it" ([PAT]:453). | **Gap**, and it is the largest one. The map's ticket #843 builds the tool in the consumer repo. |
| 3 | Tests excluded from the evidence (`no-coverage`, 948 ids) were miscounted as non-killers in a first summary. That error turned "15 of 26" into "21 of 26", and the wrong figure is still in tickets #843 and #844. A kept test whose work runs outside `\|run` is invisible to the evidence. | [PR847] Merge Danger; [NOTE]:46, :128; [T07] body | Excluded ids are listed ([PAT]:450; [SKILL]:364), and setup and teardown contexts are ignored ([SKILL]:172). Nothing says excluded tests are still *kept* tests for any downstream gate, and nothing flags a large `no-coverage` count. | **Gap** (small). |
| 4 | Greedy order: of two mutually covering tests only the slower is flagged, so the survivors are one set cover, not the only one. | [NOTE]:42 | Stated as mechanism ([SKILL]:223; `select_candidates.py:51-63`), but not as a caveat for the reviewer. | **Partly covered.** Fold into #1. |
| 5 | 2,032 flagged ids are individual parametrized cases. Table-driven vocabulary cases (one case per allowlist entry) are the sole killers of single-member mutants, for example `test_classify_equity_and_index[RUT-index]`. | [NOTE]:115, :128 | Each parametrized id is its own coverage-subset candidate, by design ([PAT]:289). | **Gap.** Flagging individual cases of a table-driven test is almost always wrong, so annotate them. |
| 6 | The 251 cost tests are slow because `get_conn()` → `load_config()` runs 8 macOS keychain subprocesses per connection (656 in one test, 84% of its time). They are not slow because they are redundant. A test-tier stub made 225 of 241 measured cost tests drop below 0.5 s. Serial call time went from 1,317.5 s to about 496 s estimated, and to 372.5 s measured after #838. A second shared cost: an unstubbed `_probe_mcp_tradingview` spawning a Node subprocess, 2.19 s per call. | [NOTE]:18, :137-155; [T02] checklist; [T03] checklist | The cost criterion is "top decile by `call_s`" of the coverage-subset set ([SKILL]:142, :224). It records no cause, so each cost entry implies "delete to save `time_saved_s`" ([SKILL]:371). | **Gap.** There is no hotspot or root-cause probe. |
| 7 | The timing run measured the developer's environment: real secrets, and on macOS `security` subprocesses (CI on `macos-latest` pays the same). "All 2,548 tests pass with the keychain stubbed, so no test depends on the developer's real secrets." | [NOTE]:155 | No check for environment coupling in the evidence pass. | **Gap.** Fold into #6: subprocess spawns per test are a cheap, generic signal. |
| 8 | Dead-test: 31 of 33 flags were deliberate. 17 are schema positive cases (`jsonschema.validate` must not raise), 8 are fail-soft tests, 2 are gate happy paths, 3 are constraint-allows-row tests, and 1 is a fetch-budget no-raise. Real finds: 1 trivial, 1 that "can never fail" (only pass or `pytest.skip`). Helper-held assertions are also missed. | [NOTE]:41, :97-107; [MAP] Out of scope; [T04] | Python vocabulary is `assert`, `pytest.raises`, `pytest.warns` only ([PAT]:97). The agent's own scan used extra prefixes `("assert", "_assert", "check", "_check", "expect", "_expect", "verify", "_verify")` ([RUN] `scan_static.py`). | **Gap.** The map names it as a skill change. |
| 9 | Fail-soft tests "pass when the function silently does nothing". The ticket's fix (a `caplog` assertion) was verified by a hand mutation: the body was replaced with `return None`, and each test failed. | [T04] checklist | No guidance for the "no assertion, but deliberate" disposition. | **Gap** (small). Put the disposition note into the dead-test sub-kinds of #8. |
| 10 | Pinning: 577 of the 1,813 entries name only an imported collaborator, usually a patch target (`load_config`, `session_repo`, …). The assertion is already on the interface, so there is nothing to move. The right fix is to re-point the stub (deps injection / `patch_checked`), not to delete. | [NOTE]:220-226, :250-255; [MAP] Out of scope; [T09] | `patch("pkg.mod.name")` and `monkeypatch.setattr` targets count as references, and a non-seam reference makes a pinning candidate ([PAT]:348-351). No distinction between a collaborator imported into the module and a name defined in it. | **Gap.** The map names it as a skill change. |
| 11 | "Covered through the interface" compares the **lines** of **one** interface test. Arcs and assertions are not compared. In a 12-test sample, 2 were deletable. 11 tests carry both a true and a false entry for different modules. | [NOTE]:44, :212-213, :228-244 | Definition at [PAT]:354 and `classify_seams.py:560-582`. The note text "covered through the interface" reads as a removal hint. | **Gap.** Fix the wording and add a per-test roll-up. |
| 12 | Pinning kinds behave differently. Private function (759): merge into an existing interface test as parametrized cases, then delete behind a mutation check. Collaborator (457): re-point the stub. Constant (81): re-point. Public non-seam (65): a human seam decision. "Writing one new interface test per pinning test changes nothing but coupling." | [NOTE]:248-267; [T09] | Two notes only ([SKILL]:372; [PAT]:354). | **Gap.** Emit a `kind` per pinning entry. |
| 13 | The seam confirm round covered 440 modules and 3,599 seams, and the user accepted all of them. | [RUN] `confirm_seams.py`; [NOTE]:214 | "One list per source module … The user accepts, adds names, or removes names for each module" ([SKILL]:195). | **Gap.** At this size the round is a rubber stamp. Offer bulk accept plus a review of only the weak-signal modules. |
| 14 | Confirmed seams live only in the ledger. A later run archives a `done` ledger ([SKILL]:52). `--dry-run` holds no confirm round and skips classification ([SKILL]:195). Yet tickets #844, #845, and #846 tell the next agent to regenerate the candidates "with `/refactor-tests --phases=B --dry-run`", and #846 compares the pinning count (1,813) across runs. | [T08], [T09], [T10]; [SKILL]:52, :192, :195 | Not supported. A dry-run produces no pinning entries, so #845's regenerate path and #846's pinning trend row both break. | **Gap**, and a real inconsistency the map depends on. |
| 15 | The agent invented `seams-proposed.json` and `seams-classified.json` sidecars, which [NOTE] reads as artifacts. The skill names neither. | [RUN] file list; [NOTE]:214, :284 | Not named in [SKILL] or [PAT] (`rg seams-proposed` finds nothing). | **Gap** (small). It ties in with #14. |
| 16 | Artifacts are uncommitted and 150 MB (`test-evidence.json` alone is 153 MB). Every downstream ticket says "That file is not committed. When it is absent … regenerate". Ticket #837 had to build `summarize.py` plus a committed `data.json`, because the consumer's CODING_STANDARDS "requires a committed artifact behind every measured figure". | [T01]; [T08]; [T09]; [NOTE]:3, :282-307 | Everything is written under `.scratch/` ([SKILL]:33). No small, committable summary. | **Gap.** Emit a `run-summary.json`. |
| 17 | Staleness: #844 must decide whether "the test file has changed since 2026-10-16" before reusing the candidate list. | [T08] | Evidence records tool versions and commands ([SKILL]:163, :173), but no commit SHA or dirty flag (`rg sha|rev-parse` finds nothing in `assemble_evidence.py` or [PAT]). | **Gap** (small). |
| 18 | Ordering: the mutation gate is affordable only after the keychain fix (about 9.6× cheaper). A re-run after the stub reorders candidates by the new `call_s` ([T08]). The map orders the work as: environment cost first, then dead-test and migration dispositions, then the mutation tool, then gated deletions, then re-run and trend. | [NOTE]:202, :269-280; [T07] Blocked by; [T08] | Tickets are numbered fix, then review, then add, then skipped. The only blocking edge is fix → review ([PAT]:311). | **Gap.** Add a hotspot category that blocks cost and coverage-subset review. |
| 19 | Volume: 9,358 items became 765 drafts (25 ids per ticket, [RRQ]:48). The user declined to publish. The ledger recorded `local-only` plus an ad hoc `note`, although `local-only` is defined as "No `docs/agents/issue-tracker.md`, or a gate regressed" ([PAT]:328). | [RUN] `ledger.json` `publish` | Step 11 has no "user declined" outcome ([SKILL]:333-338) and no volume threshold. | **Gap.** |
| 20 | A criterion that flags 70.9% of the suite is not discriminating. The useful view was concentration: the top files and the top 15 modules, which hold 55% of the pinning entries. | [NOTE]:118, :215 | The report lists per criterion and per test ([SKILL]:370-372). There is no per-module concentration summary. | **Gap.** Ties in with #16 and #19. |
| 21 | `call_time` reported Δ −132.6 s (1,317.5 → 1,184.9 s) with 0 removals and 3 parametrizations whose covering tests run in 0.23 s ([PR847]). The delta is run-to-run variance. | [RUN] `ledger.json` `simplification.call_time`; [PR847] | Prints before, after, and Δ "serial call time, not wall time" ([SKILL]:286-293, :376). No variance caveat. | **Gap** (small). |
| 22 | The order gate found 3 order-dependent tests. The skill demoted them correctly, and the map tracks the 2 in `test_phase_676_workflows.py`. The follow-up needed an ad hoc reproduce command (`uv run --with pytest-randomly … -p randomly --randomly-seed=180092053`), because pytest-randomly is not a project dependency. | [MAP] Notes; [T05] | The fix ticket carries the seed in its title and check ([RRQ]:150-151, :220). The plugin and the reproduce command are not in the ticket. | **Partly covered.** Add the command. |
| 23 | Migration tests: a blanket "delete non-head migration tests" rule is wrong. The 100 functions split into 4 classes: 23 static, 30 head-schema invariants, 20 data movement on legacy rows, and 27 misfiled repo or model tests. Data movement can go only past an operator `alembic current` watermark ([ALEMBIC-COOKBOOK] in [NOTE]:30). | [NOTE]:48-91; [T05]; [T06] | The skill has no notion of migration tests. Coverage-subset and pinning review treats them like any other test. | **Gap**, but domain-specific. Port as a short reference hint, not a step. |
| 24 | The agent hand-wrote helpers for Step 2 discovery, Step 8 static criteria, plan assembly, the Step 9 atomic parametrize edit, and ledger merges. | [RUN] file list | Helpers exist only for evidence, seams, the order gate, call time, and the queue ([SKILL]:154, :190, :234, :317). Steps 2, 8 (static), and 9 are prose. | **Gap.** It is a source of variance between runs, and the agent widened the dead-test vocabulary in its own script (#8). |
| 25 | Integration-tier guard: `tests/integration/` stayed untouched, and the guard was named in a ledger note. | [RUN] ledger `notes` | Directory guard check ([PAT]:54). | **Covered.** |
| 26 | Order gate under pytest-randomly, ephemeral install, same-seed re-run. | [RUN] `order_gate`, `run_gate.sh` | [SKILL]:240-248. | **Covered.** |
| 27 | `COVERAGE_CORE=ctrace`, serial untraced timing run, `-p calltime`. | [RUN] `run_coverage.sh`, `run_timing.sh` | [SKILL]:156-171. | **Covered.** |

## Proposed skill edits

These are proposals only. No skill file was changed. The placement follows `writing-for-agents`. [SKILL] is already 402 lines, so new definitions and caveats go into [PAT] as disclosed reference. [SKILL] gets only the step or rule that every run needs.

### G1. Say what each evidence criterion does not prove (findings 1, 4, 11)

- **[PAT], new section "What each criterion proves"**, placed after the Simplification plan schema. Port the table from [NOTE]:39-44 in generic form:

  | Criterion | Proves | Does not prove |
  |---|---|---|
  | dead-test | No assertion statement in the body. | That no exception path asserts. |
  | coverage-subset | The test's lines and arcs are covered by other passing tests. | Anything about assertions. The result is one greedy set cover. |
  | cost | Slow and coverage-subset. | Why it is slow. |
  | pinning `covered_through_interface` | Lines are a subset of one interface test's lines. | Arcs, assertions, or the same behaviour. |

- **[SKILL]:141 and :142.** Change "Review only, never removed" to "Review only, never removed on this evidence alone: see `reference/patterns.md` → What each criterion proves".
- **[SKILL]:13.** Change "redundant unit tests removed" to "exact-duplicate and trivially-true tests removed; evidence-based candidates queued for gated review".
- **[RRQ]:213, `WHAT["review"]`.** Make the text criterion-specific. For `coverage-subset`, `cost`, and `pinning`, add: "Coverage shows execution, not assertion strength. Remove a test only when a mutation check of its module shows no lost kill; otherwise keep or merge it." For `dead-test`, point to the sub-kinds in G4.
- **Pinning note text ([PAT]:354).** Rename "covered through the interface" to "lines covered by one interface test (assertions not compared)". Add the rule: a test with entries for several modules is removable only when every entry allows it (finding 11).

### G2. Mutation deletion gate (findings 2, 3)

Fill the reserved `kill_set` slot ([PAT]:453) with a check that runs per module, is optional, and is off by default.

- **Contract** (put in [PAT]): "Delete test T only if every mutant T kills is also killed by some kept test. Tests listed under evidence `excluded` are kept tests: they count as killers, never as candidates." Finding 3 comes from violating the second sentence.
- **Design**, from [NOTE]:184-202 and [T07]:
  - Run mutmut twice on module M, scoped to M's covering tests: once as is, once with the candidate batch deselected.
  - A mutant killed in the first run and surviving the second is a lost kill.
  - A timeout counts as killed in both runs.
  - A mutant with a non-deterministic outcome counts as lost.
  - Re-run only the lost mutants without fail-fast to build the restore list.
  - Use batches of 25.
  - Use `mutate_only_covered_lines` and `do_not_mutate` for migrations and generated code.
  - Neither mutmut nor Cosmic Ray records killing tests ([NOTE]:32-33, :188-189; also `docs/research/refactor-tests-coverage-speed-deep-modules.md:34-35`). That is why the double-run design is needed.
- **Placement.** Put it in a new optional Step 8c, or in a follow-up section like "Follow-up: Assertion-API enforcement" ([SKILL]:343). The follow-up section is the cheaper first step. It writes no code into the skill and gives the agent a fixed recipe for the review tickets. Ticket #843's tool, once proven in pro-trading, is the reference implementation to port into `reference/python/`.
- **Cost note.** Gate only after the hotspot fixes of G3. In this run the mutation gate became about 9.6× cheaper once the keychain stub landed ([NOTE]:202).

### G3. Cost hotspot probe before the cost queue (findings 6, 7, 18)

- **[SKILL] Step 8, after the cost rule ([SKILL]:224).** Add a short item. Profile the top N cost candidates (for example 5, serially, with `python -m cProfile -o …`). Aggregate cumulative time by function across them. Also count `subprocess` spawns per test.
- **Hotspot rule.** A function that holds at least 50% of call time in at least half of the profiled tests is a **hotspot**. Emit one `review_candidates` entry `{ criterion: "hotspot", function, share, tests }`. Number its ticket before every review ticket. Make it block the `cost` and `coverage-subset` tickets of the same test directories.
- **Wording.** "A hotspot is fixed in the test tier (a fixture or stub), never by deleting tests. After the fix, re-run the evidence pass, because `call_s` order changes."
- **[PAT]:311.** Add the `hotspot` category and its blocking edge to the Grouping paragraph. Add a row to the Items and keys table. Label it `ready-for-agent`: the keychain fix #838 was a one-session agent ticket.
- **[SKILL]:371.** Label `time_saved_s` "upper bound if deleted; see hotspots". At present cost entries read as deletion savings.

### G4. Dead-test sub-kinds and wider vocabulary (findings 8, 9)

- **[PAT]:97.** Extend the Python row:
  - Count calls to any function whose name starts with `assert`, `_assert`, `check`, `_check`, `expect`, `_expect`, `verify`, or `_verify`, as the run's own `scan_static.py` did.
  - Count calls to a fixture or helper defined in the test file or `conftest.py` whose body asserts.
- **New sub-kinds.** Instead of a single `dead-test` flag, emit a `kind` from a small, ordered vocabulary:
  1. `no-raise-contract`: the last statement calls a documented raiser (`*.validate(`, a name the project lists), or the name or docstring says "does not raise" or "must not raise". Disposition: keep. It is the only guard against an over-strict validator.
  2. `fail-soft`: the body sets up an error (`side_effect=…Error`) and calls a function under test. Disposition: add an assertion on the log or the return value. Verify it by hand-mutating the function to a silent no-op ([T04]).
  3. `never-fails`: the only non-pass outcome is `pytest.skip`. Disposition: replace the skip with an assertion, or remove the test.
  4. `no-assertion`: everything else.
- **Placement.** [PAT] "Assertion vocabulary"; [RRQ] puts the kind into the ticket line. [SKILL]:139 stays "Review only, never removed" and adds "(sub-kind in `reference/patterns.md`)".

### G5. Collaborator test doubles are not pinning (findings 10, 12)

- **[PAT]:348-351.** Add a rule. A `patch(...)`, `patch.object(...)`, or `monkeypatch.setattr(...)` target that names a module attribute **bound by an import** in that module, not defined there, is a **test double**. It is not a pinning reference. Record it under `doubles`.
  - A test whose only non-seam references are doubles is an interface test with doubles. Emit it as `{ criterion: "pinning", kind: "collaborator-double" }` with the note "re-point the stub (deps injection or a checked patch); do not delete". Alternatively, drop it from pinning when the project opts in.
  - This keeps the ADR-0101 concern raised in [NOTE]:251-253 visible, because mocked internal seams hid real defects, without flooding the queue.
- **Pinning `kind` per entry.** Emit `private` (a name with a leading underscore, defined in the module), `collaborator-double`, `constant` (a module-level non-callable), `public-non-seam`, or `other`. In this run the counts were 1,048 / 577 / 95 / 76 / 17 ([NOTE]:220-226).
- **Workflow per kind** (put in [PAT], from [NOTE]:259-265 and [T09]):
  - `private`: merge the assertion into the closest existing interface test as parametrized cases, keep the original, run the mutation check of G2, then delete.
  - `collaborator-double` and `constant`: re-point the stub.
  - `public-non-seam`: a human seam decision.
  - A test with several kinds follows the strictest one.
  - "Writing one new interface test per pinning test is not the goal."
- **Helper.** `classify_seams.py` `classify` needs the module's import table to tell "imported into" from "defined in". It already parses source modules for `propose`.

### G6. Seams across runs and under `--dry-run` (findings 13, 14, 15)

- **Persist confirmed seams.** Write `.scratch/refactor-tests/seams-confirmed.json` when Step 7b item 2 confirms. Do not archive it with the ledger. On a later run, item 2 proposes only the **difference** (new modules, new or removed names) and reuses the rest.
- **Dry-run.** Change [SKILL]:195. "Under `--dry-run`, or when no user can answer, hold no round. When `seams-confirmed.json` exists, classify with it and say so in the report. Otherwise seams stay `proposed` …". This makes the `/refactor-tests --phases=B --dry-run` regenerate path in [T08]–[T10] produce pinning entries.
- **Bulk confirm.** Above roughly 50 modules, offer "accept all" plus an explicit list of only the `public-api`-signal modules (the weakest signal, [PAT]:344) for a per-module look. Record which path the user took.
- **Name the sidecars** in [PAT]: `seams-proposed.json` (the `propose` output) and `seams-classified.json` (the `classify` output). Agents wrote them anyway ([RUN]). Naming them makes them stable inputs for follow-up work.

### G7. Committable run summary and provenance (findings 16, 17, 20)

- **Summary file.** Step 11 writes `.scratch/refactor-tests/run-summary.json`, small enough to commit, with:
  - `started_at`, the git SHA, a dirty flag, the runner command, and the seed;
  - counts per criterion, and per `kind` where G4 and G5 apply;
  - excluded counts by outcome;
  - per-module or per-file concentration (top 15 by candidate count and by `call_s`);
  - hotspots (G3);
  - before and after serial call time.
- **Purpose.** Downstream notes cite it instead of a 153 MB evidence file. Ticket #837 had to build exactly this by hand ([T01]; [NOTE]:3).
- **Provenance in the evidence file.** `assemble_evidence.py` records `git rev-parse HEAD` and `git status --porcelain` emptiness ([PAT] evidence schema near :449). Step 11 tickets carry the SHA, so a later agent can tell whether a candidate list is stale ([T08]).
- **Report** ([SKILL]:370). Before the per-test listing, print the share of the suite flagged per criterion and the top-5 concentration. When one criterion flags more than about 50% of the evidence tests, print a warning: "criterion is not discriminating on this suite; triage by module and hotspot before per-test review".

### G8. Step 11 at volume, and a user-declined status (finding 19)

- **New status `declined`** in [PAT]:323-332: "The user chose not to publish. The queue file and drafts are kept. Final." The run currently misused `local-only` with an ad hoc `note`.
- **Volume gate in Step 11 item 3** ([SKILL]:335). When `tickets` exceeds a threshold (for example 50), an interactive run asks before item 4. It offers three choices:
  - (a) publish all;
  - (b) publish only fix, hotspot, and add tickets, plus one triage ticket per criterion that links the queue file and `run-summary.json`;
  - (c) queue file only.

  An unattended run picks (b) on the local tracker and `drafted` on a real tracker, as today. Option (b) is what the user effectively did by hand: one research ticket, then a short execution map.

### G9. Call-time variance caveat (finding 21)

- **[SKILL]:293 / `calltime_delta.py`.** Compute `attributable_s` = the sum of `call_s` of the removed and replaced tests. When |`delta_s`| > 2 × `attributable_s` + 2% of `before_s`, set `warning` to "delta exceeds what the changes can explain; treat it as run-to-run variance". The report prints it next to the totals ([SKILL]:376).

### G10. Fix-ticket reproduce command (finding 22)

- **[RRQ] fix tickets** ([RRQ]:150, :220). Add the exact reproduce line from the recorded runner command, the plugin `with` install, and the seed. Example: `uv run --with pytest-randomly pytest -p randomly --randomly-seed=<seed> <file>`. Ticket #841 had to work this out ([T05]).

### G11. Migration tests hint (finding 23)

- **[PAT], short reference note**, reached from the dead-test and coverage-subset rows of G1: "Schema-migration tests (Alembic, Flyway, Liquibase, Django) mix four kinds."
  - static revision or source checks: deletable;
  - head-schema invariants: move to a schema test;
  - data movement on legacy rows: deletable only once every persistent database is past that revision (an operator fact);
  - misfiled repo or model tests: move.

  Add: "Never apply a 'delete non-head migration tests' rule as a whole." Cite [NOTE]:56-91. Keep it a hint. The classification needs project knowledge, as [T05]'s 2 `unclassified` entries and its 28-versus-30 recount show.

### G12. Helpers for the prose-only steps (finding 24)

- Port helpers for Step 8's static criteria (exact duplicate, dead with the G4 kinds, trivially true, parametrize cluster and pair) and for Step 9's atomic parametrize edit.
  - Start from the shape of the run's `scan_static.py` and `apply_param.py`. The agent wrote both on its first try, and the 3 consolidations passed.
  - Add tests beside the existing `reference/python/tests/`.
- Discovery (Step 2) and ledger merges are lower priority. The run's versions were project-specific (`ROOT/"src"`, `ROOT/"tests"` hardcoded in `discover.py`).

## Contracts to preserve when editing

- **Seam definition quote.** Step 7b quotes `skills/engineering/tdd/SKILL.md` `## Seams — where tests go` word for word and reads `codebase-design` terms (`docs/agents/skill-dependencies.md:12`). G5 adds the "test double" term. Check `codebase-design` for an existing word before inventing one.
- **Step 11 and `to-tickets`** (`docs/agents/skill-dependencies.md:13`; ADR-0079). Any edit must keep these: the slug rule, the `` key: `…` `` lines, the `label:` field, and headless mode. A new category (G3 `hotspot`) or status (G8 `declined`) changes the [PAT] tables and `render_review_queue.py` together, and needs an ADR-0079 amendment for the new status and edge.
- **Path templates.** `testing` reads the [PAT] path templates (the `engineering/testing` → `engineering/refactor-tests` entry of `docs/agents/skill-dependencies.md`). None of the proposals touch them.
- **Audio cues.** `say_skill_start` / `say_skill_done` / `say_skill_cancel` on every exit path ([SKILL]:36, :40-44, :394-401; `docs/agents/hooks.md`). A new interactive question (G6 bulk confirm, G8 volume gate) sits inside the run's suppression window. Check `docs/agents/hooks.md` for whether a mid-run question needs a permission or idle cue.
- **Dry-run purity.** [SKILL]:33 allows writes only under `.scratch/refactor-tests/`. G3 profiling, the G6 seams file, and G7 summary all stay there. G2 mutation runs must not edit project config: install mutmut ephemerally, as Step 7 does.

## Not ported (project-specific)

- **The keychain stub itself, the `cli health` probe stubs, and `load_config()` caching.** These are pro-trading fixes. Only the generic detection (G3) is ported.
- **Specific dispositions.** The individual dead-test dispositions and the migration watermark values belong to the project.
- **pro-trading process conventions.** The 25-per-batch sequencing with a final combined check ([T08]) is good practice for G2, but it is pro-trading's ticket protocol. Mention it as a recommendation only.

## Limits

- **No PRs for most tickets.** Tickets #838–#846 have no PRs yet. Findings from #838–#841 come from their ticket checklists (agent-written "done" notes), not from merged code.
- **Unconfirmed figure.** The 15-versus-21 discrepancy is reported by [PR847], which the note and JSON follow. Tickets #843 and #844 still say 21. This was not recomputed here.
- **Local-only run artifacts.** [RUN] artifacts exist only on this machine and can change if the `test-refactor` worktree is reused.
