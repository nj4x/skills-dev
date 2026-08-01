---
name: refactor-tests
description: Refactor a project's flat test layout into a source-package-mirrored structure (polyglot — Python, TS/JS, Go, Java/Kotlin) and simplify the suite by removing redundant tests and consolidating parametrizable groups. Use when a project's tests live in one flat directory and you want them reorganized to mirror the source packages so that changed code maps to a small, relevant test subset, and to eliminate exact duplicates, dead tests, and unnecessarily split tests that can be expressed as parametrized cases. Keywords - test refactor, mirror tests, test layout, package-mirrored tests, reorganize tests, redundant tests, test simplification, dead tests, duplicate tests, parametrize.
disable-model-invocation: true
argument-hint: "[project-path]"
---

You are refactoring a project's test layout to mirror its source package structure **and** simplifying the suite by removing redundant tests and consolidating parametrizable groups.

PROJECT_PATH: $1 (default: `$PWD`)

The end state after both phases:
- **Layout**: every test file sits at the location its language convention dictates for the source it exercises (see `reference/patterns.md`), imports are rewritten to stay valid, and the full test suite passes with zero regressions against a pre-refactor baseline.
- **Simplification**: redundant unit tests (exact duplicates, dead tests, trivially-passing tests, subset tests) are removed; clusters of tests that call the same function with varying inputs under the same assertion pattern are consolidated into parametrized test cases — reducing test count without reducing scenario coverage.

---

## Step 0 — Load repeat contract

Check whether `~/.claude/skills/repeat/SKILL.md` exists:
```bash
test -f ~/.claude/skills/repeat/SKILL.md && echo FOUND || echo MISSING
```

- **FOUND**: Read `~/.claude/skills/repeat/SKILL.md` and follow the repeat loop contract, binding the extension points below. The repeat contract governs Guards, Mode detection, the Decision Protocol, and the loop — do not re-derive them here.
- **MISSING**: stop with: `repeat skill not found. Install it with: ln -s /Users/roman/projects/skills-dev/planning/repeat ~/.claude/skills/repeat`

This skill runs **two sequential repeat loops**: Phase A (Layout) refines and executes the migration plan; Phase B (Simplification) refines and executes the simplification plan. Phase B always runs after Phase A completes successfully.

The **Phase A artifact** is the migration plan: `.scratch/refactor-tests/plan.json`
The **Phase B artifact** is the simplification plan: `.scratch/refactor-tests/simplification-plan.json`

**PICKUP disambiguation**: the repeat contract's PICKUP mode selects the artifact from the ledger `phase`: if `phase` is in `{discovery, planning, baseline, moving, rewriting, validating}` the active artifact is `plan.json`; if `phase` is in `{simplifying, simplify-validating}` the active artifact is `simplification-plan.json` (and reload it at the start of GENERATE/FINALIZE to compute remaining work by diffing against `ledger.simplification`).

Read `reference/patterns.md` (beside this SKILL.md) before any GENERATE_STEP — it holds the per-language path templates, language-detection heuristics, ledger/plan schemas, and the simplification plan schema.

---

## Step 1 — Resolve project and detect stack

1. `PROJECT_PATH` defaults to `$PWD`. Resolve to an absolute path; hard-stop if it is not a directory.
2. **Ledger resume check.** If `$PROJECT_PATH/.scratch/refactor-tests/ledger.json` exists and its `phase` is not `done`, print the recorded phase and resume from it (see [Ledger and resume](#ledger-and-resume)). Otherwise initialize a fresh ledger with `phase: discovery`.
3. **Detect languages** by extension scan (`reference/patterns.md` → Language detection). Record the set of present languages and, per language, the source roots discovered (multi-root: all `src/`, `lib/`, `packages/*/src/`, `src/main/java` trees).
4. **Detect the test runner(s)** per language via convention markers (`reference/patterns.md` → Runner detection). Store them in the ledger.

---

## Ledger and resume

The ledger at `$PROJECT_PATH/.scratch/refactor-tests/ledger.json` is the durable record that survives context compaction. Schema in `reference/patterns.md`. It tracks:

- `phase`: one of `discovery`, `planning`, `baseline`, `moving`, `rewriting`, `validating`, `simplifying`, `simplify-validating`, `done`
- `languages`, `source_roots`, `runners`
- `baseline`: the pre-refactor suite result (per runner: passed count, failed test ids)
- `id_map`: a map `{ "<old test id>": "<new test id>" }` populated during Phase A for every moved test; used to exclude intentional renames from regression detection
- `moves`: applied file moves (`from` → `to`), appended as each is written to disk
- `rewrites`: applied import rewrites (`file`, count)
- `simplification`: applied removals and parametrizations, appended as each is written

Update the ledger after **every** durable side effect (each move, each rewrite batch, each removal/parametrization, each phase transition), not in a single trailing write — a mid-phase compaction must be recoverable. On resume, re-derive in-flight state from the ledger and continue; never re-apply an action already recorded.

---

## Phase A — Layout Refactoring

### GENERATE_STEP — Build/refine the migration plan

Set ledger `phase: planning`.

**Iteration 0 (FRESH):** produce the migration plan.

For each detected source file in each source root:
1. Compute its **target test path** from the language path template (`reference/patterns.md`).
2. Find its **existing test(s)**: query `search-codebase` (`search_root`) for tests referencing the file's public symbols; fall back to `fd`/`rg` by filename and by the flat-layout naming pattern (e.g. `test_<module>.py`). This is the same search-codebase-first, path-based-fallback strategy the `testing` skill uses.
3. Emit a move entry `{ from: <current test path>, to: <target test path>, language, source_file }` when the two differ.
4. For each moved file, statically determine the **import rewrites** its relocation forces (relative-import depth changes; see `reference/patterns.md` → Import rewriting). Emit `{ file, edits: [...] }`.

Classify tests that map to **no single source file** (fixtures, integration, e2e, tests exercising many packages) as **cross-cutting**: record them under `unmapped` with the reason. Do **not** move them in v1 — leave them in place and surface them in the report.

Write the plan to `.scratch/refactor-tests/plan.json` and return its path as `artifact_text`. In `guided` mode, append a `FLAGGED_DECISIONS` block for any genuinely ambiguous mapping (e.g. a test that plausibly belongs to two modules).

**Iteration > 0 (revision):** read the critic's issues, edit `plan.json` in place to address each major finding, and return the path again.

### REVIEW_STEP — Adversarial critic over the layout plan

Invoke an Agent (`subagent_type: "claude"`) that reads `plan.json` and the project tree, and returns **raw JSON** `{ verdict, severity, top_issues, suggested_fixes }` (same contract and temp-file validation harness as the `critic` skill). The critic evaluates ONLY the plan, on these lenses:

- **Completeness**: is every existing test file either in a `move`, already at its target, or justified under `unmapped`? A test silently dropped from all three is a **major**.
- **Correctness**: does each `to` path match the language template for its `source_file`? Wrong target = **major**.
- **Import soundness**: will the recorded rewrites keep each moved file's imports resolvable? A move with a depth change but no corresponding rewrite = **major**.
- **Collisions**: do two moves target the same path? = **major**.
- **Cross-cutting judgment**: is anything in `unmapped` actually cleanly mappable (under-classification), or is a `move` actually cross-cutting (over-classification)? = **minor** unless it would break the suite.

Approve when no major remains. Prefix each issue `[<lens>][major|minor] claim — evidence`.

### FINALIZE_STEP — Execute layout plan and run health gate

Only when `approved == True` (verdict `approve`, severity not `major`, cap not reached). If not approved, write the plan and critic summary as text, leave the project untouched, call `say_skill_done`, and return.

Approved path:

1. **Baseline** (`phase: baseline`). Run the full suite per runner (`reference/patterns.md`). Record pass count and the full set of passing and failing test ids into ledger `baseline`. A pre-existing failure is part of the baseline, not a regression.
2. **Move** (`phase: moving`). Apply each `move` with `git mv` (preserves history; falls back to plain move outside git). For each moved test file, derive the old→new test id mapping by replacing the path prefix and record in ledger `id_map`. Record each move in ledger `moves` as it happens.
3. **Rewrite** (`phase: rewriting`). Apply each import rewrite using the language's AST tool (`reference/patterns.md` → Import rewriting) — never blind regex. Record each in ledger `rewrites`.
4. **Validate** (`phase: validating`). Re-run the full suite. **Regression check**: for each test id that passed in `baseline`, map it to its new id via `id_map` (or keep the original id if unmoved), and verify the mapped id still passes. `id_map` derivation is language-specific: for Python (pytest) and TS/JS (jest) replace the file-path prefix; for Go test ids are `<pkg>::Test<Name>` — map by replacing the import path where the package moved; for Java/Kotlin ids are class-qualified — map by replacing the package prefix to match the new directory. Report any genuine regressions:
   - **Healthy** = zero genuine regressions. Record the post-layout suite result into ledger `simplification.post_layout_baseline`. Advance to Phase B (`phase: simplifying`).
   - **Regressed** = one or more genuine regressions. **Leave refactored state intact** (do not roll back); carry the regressed ids into the report. **Do not proceed to Phase B** — stop and surface regressions.
5. If healthy, print a layout summary (see [Final report](#final-report)) and proceed immediately to Phase B.

---

## Phase B — Test Simplification

Phase B runs immediately after Phase A's health gate passes. It refines and executes a simplification plan using its own repeat loop invocation (same MAX_ITERATIONS and MODE inherited from the outer invocation arguments). The baseline for Phase B is the post-layout suite result from the Phase A health-gate run.

### Redundancy criteria

A test (or test cluster) is a **simplification candidate** when it meets one or more of these criteria. **All criteria require that fixture parameters, mock/stub configurations, and decorators/markers are identical between compared tests** unless the criterion explicitly specifies otherwise.

| Criterion | Action | Signal |
|-----------|--------|--------|
| **Exact duplicate** | Remove one | Two test functions with byte/AST-identical bodies AND identical fixture parameters, mock stubs, and decorators (ignoring only name and docstring) |
| **Dead test** | Remove | No `assert` / `expect` / `should` / `verify` statement anywhere in the body |
| **Trivially true** | Remove | Only assertions of the form `assert True`, `assertEqual(x, x)`, `expect(1).toBe(1)` |
| **Subset assertions** | Remove weaker | Tests A and B call the same function with identical arguments AND identical fixture parameters AND identical mock/stub configurations; A's assertion list is a strict subset of B's — remove A |
| **Parametrize cluster** | Consolidate | N ≥ 3 tests call the same function, each with distinct positional/keyword arguments of the same structural type, identical fixture parameters and mock configurations, and identical assertion pattern (same assertion shape, values become parameters) — consolidate into one parametrized test with subtests |
| **Parametrize pair** | Consolidate (user-confirmed) | N = 2 tests meeting cluster criteria where both names differ only by a trailing integer or single-letter suffix (e.g. `test_foo_1`/`test_foo_2`, `test_parse_a`/`test_parse_b`) — flag in `FLAGGED_DECISIONS` in `guided` mode; auto-apply only in `auto` mode |

**Do NOT flag as redundant** — preserve even when tests look similar:
- Tests covering different scenarios (happy path vs. error path vs. edge case)
- Tests covering different input types (None, empty, non-empty, boundary, max)
- Tests that differ in fixture parameters or setup state (different precondition = different test)
- Tests with different mock/stub return values or side-effects (different code path exercised)
- Tests with different decorators or markers (e.g. `@pytest.mark.skipif`, `@pytest.mark.xfail`, `@pytest.mark.slow`)
- Any test the AST parser cannot fully analyze — record as **unanalyzable** and skip

### GENERATE_STEP — Build/refine the simplification plan

Set ledger `phase: simplifying`. If resuming, load `simplification-plan.json` and diff against `ledger.simplification` to determine which entries remain unapplied — process only those.

**Iteration 0:** scan every test file (post-layout) using the AST parser for each language:

1. **Parse** each test file. Files the parser cannot process → record in `unanalyzable` list and skip; never silently omit.
2. **Extract** each test function/method: name, body AST, fixture parameters (function signature beyond `self`/`t`), mock/stub configurations (calls to `mock`, `patch`, `jest.fn`, etc. and their configured return values), decorator/marker list, the primary source function called (first call resolving to a known source symbol), call arguments, and assertion list.
3. **Apply criteria in order**: exact duplicate → dead → trivially true → subset assertions → parametrize cluster → parametrize pair.
   - For each **removal** candidate: emit `{ file, test_name, criterion, evidence }` where `evidence` is a ≤2-line excerpt proving the criterion.
   - For each **parametrize** candidate: before emitting, verify that expected assertion values across all N tests share a structural type (same type homogeneity rule as call arguments — e.g. all strings, all integers, all dicts of the same shape); if they differ in type, classify the cluster as **unanalyzable** (not a parametrize candidate) to prevent bundling tests with incompatible expected values. Then emit `{ file, tests: [name, ...], consolidated_name, consolidated_body_sketch, required_imports, criterion, evidence }` where `consolidated_body_sketch` is a concrete (not a sketch) language-appropriate parametrized test body with the actual parameter tuples derived from the originals, and `required_imports` lists any new imports the consolidation needs (e.g. `pytest`, `@pytest.mark.parametrize`, `it.each`).
4. **Ordering guard**: if test A is a subset of test B and B is itself a removal candidate for another criterion, plan to remove B first before evaluating A.
5. In `guided` mode, append `FLAGGED_DECISIONS` for parametrize-pair candidates and any case where fixture/mock identity cannot be confirmed statically.

Write to `.scratch/refactor-tests/simplification-plan.json` (schema in `reference/patterns.md`). Return its path as `artifact_text`.

**Iteration > 0 (revision):** read the critic's issues, edit `simplification-plan.json` in place, return the path again.

### REVIEW_STEP — Adversarial critic over the simplification plan

Invoke an Agent subagent that reads `simplification-plan.json` and the project's test files, returning raw JSON `{ verdict, severity, top_issues, suggested_fixes }`. The critic must read **both** the flagged test body and any retained sibling before issuing a finding. Evaluate on these lenses:

- **False-positive removals**: a `removal` entry targets a test that is NOT actually redundant (different scenario, different precondition, different mock, different decorator). Any false positive = **major**.
- **False-positive parametrizations**: a `parametrize` entry groups tests covering different scenarios, different mocks, or different preconditions = **major**.
- **Unsafe consolidation**: the `consolidated_body_sketch` would change observable assertion semantics (different expected values per input not captured as parametrize parameters), or the consolidated test omits a scenario one of the originals tested = **major**.
- **Coverage gap**: a removal or consolidation leaves a code path that was previously tested with zero tests remaining = **major**. Trace each candidate to its sibling(s) and confirm at least one test still exercises every prior scenario.
- **Missing required_imports**: consolidated body uses a parametrize decorator not listed in `required_imports` = **major**.
- **Criterion misclassification**: a candidate labeled `exact-duplicate` that has differing assertions, fixtures, or mocks = **minor**.
- **Unanalyzable gap**: a suspicious file in `unanalyzable` that is clearly parseable = **minor**.

Approve when no major remains. Prefix each issue `[<lens>][major|minor] claim — evidence`.

### FINALIZE_STEP — Execute simplification plan and run health gate

Only when `approved == True`. If not approved, write the plan and critic summary as text, call `say_skill_done`, and return.

Approved path:

1. **Apply removals**: for each `removal` entry, delete the named test function from the file using the language's AST editor (see `reference/patterns.md` → AST editor guidance) — never blind text deletion. Record each in ledger `simplification.removals` immediately after the write succeeds. If removing the last test function in a file, delete the file with `git rm`.

2. **Apply parametrizations** (atomic per entry): for each `parametrize` entry, perform the following as a **single atomic file write**:
   - Delete all N original test functions from the file.
   - Insert the consolidated parametrized function (using the concrete `consolidated_body_sketch`) in their place.
   - Add any entries from `required_imports` that are not already present in the file's import block.
   - Write the file exactly once.
   - Record the entry in ledger `simplification.parametrizations` in the same durable step.
   - On resume: if the originals are already absent and the consolidated function is present, the entry is already done — skip and continue.
   - If the AST editor cannot perform the composite edit, record the entry as `skipped` in the ledger with the error, leave the file unchanged, and surface in the final report as a warning.

3. **Validate** (`phase: simplify-validating`). Re-run the full suite. **Regression check**: compare against post-layout baseline. Exclude test ids in `ledger.simplification.removals` and the replaced ids in `ledger.simplification.parametrizations` from the required-passing set (they were intentionally removed). For consolidated tests, verify the new parametrized test id appears and passes. A genuine regression is any test that was passing post-layout (and not intentionally removed/consolidated) that no longer passes:
   - **Healthy** = zero genuine regressions. Set `phase: done`.
   - **Regressed** = one or more genuine regressions. **Leave simplification changes intact** (do not roll back); carry the regressed ids into the final report and set `phase: done` with a regression warning.
4. `say_skill_done`.

**Do not commit.** Leave all changes in the working tree for the user to review with `git diff` and commit themselves.

---

## Final report

If Phase A regressed and the skill stopped before Phase B, print only the Phase A section followed by:
> **Phase B not reached** — resolve layout regressions first, then re-run the skill to proceed to test simplification.

Otherwise print both sections:

**Phase A — Layout:**
- **Files moved**: count, and the move list (or a sample if large)
- **Imports rewritten**: count, with a few representative rewrites
- **Cross-cutting (left in place)**: the `unmapped` list with reasons
- **Baseline**: `<N> passed, <M> failed` before refactor
- **Post-layout**: `<N> passed, <M> failed` — `✓ zero regressions` or `✗ <k> regressions:` followed by regressed test ids

**Phase B — Simplification:**
- **Tests removed**: count, grouped by criterion (exact-duplicate: N, dead: M, trivially-true: K, subset: J)
- **Tests parametrized**: count of consolidations; before/after listing (original test names → consolidated name + parameter tuples)
- **Parametrizations skipped** (AST editor failures): list with reasons
- **Unanalyzable files** (skipped by AST parser): list with reasons
- **Post-simplification**: `<N> passed, <M> failed` — `✓ zero regressions` or `✗ <k> regressions:` followed by regressed test ids

**Warnings**: AST parse/edit failures, imports that could not be rewritten, runner-detection ambiguities

**Next steps** if regressed: which files to inspect, and `git checkout -- <paths>` to revert selectively

---

## Hard invariants

- The audio-suppression marker spans the **entire skill lifetime** (both Phase A and Phase B loops). It is set once idempotently at the start of the first loop; the second loop's start call is a no-op if the marker already exists. It is cleared by exactly one `say_skill_done` call — at the end of Phase B's FINALIZE_STEP — or by `say_skill_cancel` on any hard-abort or early-exit path (Phase A not approved, Phase A regressed). No intermediate `say_skill_done` fires between phases.
- Do NOT launch headless `claude` CLI processes via Bash.
- Never pass plan or file text as a shell argument. Write to a temp file when Bash must read it.
- Bash non-zero exit, unparseable critic JSON, or a missing required field = hard abort. Never treat as approval.
- Import rewriting and test editing are AST-based per language — never blind regex search-replace.
- Each parametrize consolidation is a single atomic file write (all N deletions + the inserted consolidated function in one edit); the ledger entry is written in the same durable step.
- On a regressed health gate (either phase), **never** auto-rollback and never `git commit`; leave the tree for the user.
- Regression detection excludes intentionally moved (Phase A, via `id_map`) and intentionally removed/consolidated (Phase B) test ids from the required-passing set.
- Update the ledger after every durable side effect so a mid-run compaction is recoverable.
- `rm -f` any temp file on every exit path, including hard-abort paths.
- The repeat audio-suppression marker must be cleared via `say_skill_done`/`say_skill_cancel` on every exit path.
