---
name: refactor-tests
description: Reorganize a flat test suite to mirror source packages, prune redundant/dead tests, and cut Spring Boot context startup cost.
disable-model-invocation: true
argument-hint: "[project-path]"
---

You are refactoring a project's test suite along three axes, each behind its own **health gate**: where test files live, which test functions survive, and what the surviving tests cost to start up.

`PROJECT_PATH`: `$1` (default: `$PWD`)

End state — every source file accounted for, every applicable axis reached:
- **Phase A · Layout**: every test file at the location its language convention dictates for the source it exercises, imports rewritten to stay valid, suite passes with zero regressions.
- **Phase B · Simplification**: redundant unit tests removed; clusters of tests that call the same function with varying inputs under the same assertion pattern consolidated into parametrized test cases.
- **Phase C · Context cost** (Spring Boot only): distinct Spring application contexts reduced, per-context background work switched off, suite wall time lower, assertions unchanged.

A gate is **healthy** when zero tests that passed at that phase's baseline now fail. A **regressed** gate stops the run at that phase — the later phases never start.

Read `reference/patterns.md` (beside this SKILL.md) before doing any work — it holds path templates, language-detection heuristics, AST tool guidance, and ledger/plan schemas.

---

## Step 0 — Audio suppression

```sh
[ -f ~/.claude/hooks/say-cue-lib.sh ] && . ~/.claude/hooks/say-cue-lib.sh && say_skill_start || true
```

---

## Step 1 — Resolve project and detect stack

1. `PROJECT_PATH` defaults to `$PWD`. Resolve to absolute path; hard-stop if not a directory.
2. **Parse command-line arguments**: `--dry-run` (skip file mutations, stop after plan), `--phases=A,B` (run only specified phases, default all available).
3. **Ledger resume.** If `$PROJECT_PATH/.scratch/refactor-tests/ledger.json` exists and `phase` is not `done`/`failed-*`, print the recorded phase and resume from it. On resume from `failed-*`, archive the old ledger to `ledger.YYYY-MM-DDTHH-MM-SS.json` and reuse the stored `baseline`. Otherwise initialize a fresh ledger with `phase: discovery`.
4. **Detect languages** by extension scan (respect `.gitignore`; skip `vendor/`, `node_modules/`, `.venv/`, `build/`, `.reference-projects/`, `.scratch/`).
5. **Detect runner(s)** per language via convention markers in `reference/patterns.md`. Record the resolved command exactly.
6. **Spring Boot check** (JVM projects only): set ledger `spring_boot: true` when a Spring Boot dependency and ≥2 context-loading test classes are both present — this enables Phase C. Detection commands are in `reference/springboot.md` Step C0.
7. Write detected languages, source roots, and runners into the ledger.

---

## Step 2 — Discovery: map source files to target test paths

For each source file in each detected source root:

1. Compute its **target test path** using the language path template from `reference/patterns.md`.
2. Find its **existing test file**: search by filename (`fd`/`rg`) using the flat-layout naming pattern (e.g. `test_<module>.py`). Also `rg` for imports of the module to catch tests that import it under a different name.
3. If the existing test path differs from the target path, record a move entry `{ from, to, language, source_file }`.
4. If no test file exists for this source file, skip — do not create empty test files.

**Cross-cutting classification:** a test file is cross-cutting when it cannot be cleanly attributed to a single source file. Use `search-codebase` to check whether the test exercises 2+ distinct non-mocked methods from different classes; if yes, classify as cross-cutting. Also treat as cross-cutting: e2e tests and tests whose import list spans packages with no dominant module. **Exception: location-scoped fixtures** (`conftest.py`, jest setup files referenced in config paths, Go `TestMain` functions) are pinned in place — do not relocate them, even if not assigned to a source. For each cross-cutting file: compute its target path in the language's integration directory (from `reference/patterns.md`), preserving the filename. Record in `plan.json` `cross_cutting` array as `{ from, to, language, reason }`.

**When a mapping is ambiguous** (test plausibly belongs to two modules), pick the one whose module name appears first in the test file's import list. Record the decision in the ledger `notes` field; do not stop to ask.

Write `$PROJECT_PATH/.scratch/refactor-tests/plan.json` with the full move list, rewrites, and unmapped entries.

---

## Step 3 — Baseline

Set ledger `phase: baseline`.

Run the full test suite using the detected runner command. Per language, capture test ids using runner output specified in `reference/patterns.md` → Per-runner output formats. Record into ledger `baseline`:
- pass count
- failing count
- the full set of passing test ids (written to `baseline-ids.json` sidecar)
- the full set of failing test ids (pre-existing failures are baseline, not regressions)

**Expected non-zero exits:** test runners (`pytest`, `go test`, `mvn test`) exit non-zero when any test fails — this is data, not an error. Detection probes (e.g., `rg ... | grep -q .`) are also expected non-zero as their "not found" signal. Only hard-abort on process errors (exit 127, signal termination).

---

## Phase A — Layout

### Step 4 — Move files

Set ledger `phase: moving`.

For each entry in `plan.json` `moves`, then each in `plan.json` `cross_cutting`:
1. Create any missing target directory (including `__init__.py` if the test tree uses package-style dirs — detect by presence of any `tests/**/__init__.py`).
2. `git mv <from> <to>` (falls back to `mv` outside git). Hard-stop on non-zero exit.
3. Record `{ from, to, cross_cutting }` in ledger `moves` immediately — `true` for the `cross_cutting` entries, `false` for the rest.

Build `id_map` in the ledger: for each moved file (regular and cross-cutting), record the old→new pytest/jest/go test id mapping (replace file path prefix in the id).

### Step 5 — Rewrite imports

Set ledger `phase: rewriting`.

For each moved file with a rewrite entry in `plan.json`:
- Rewrite with the language's parser and tool per `reference/patterns.md` → Import rewriting.
- Files the parser cannot process: record as a **warning** in the ledger `warnings` field, leave imports unchanged, surface in the report.
- Record each completed rewrite in ledger `rewrites`.

### Step 6 — Validate layout

Set ledger `phase: validating`.

Re-run the full suite. Regression check: for each test id that passed in `baseline`, map it to its new id via `id_map` (or keep original id if unmoved), verify the mapped id still passes.

If any regressed id is found, **re-run just those ids once** to confirm the failure (flake detection). If they all pass on retry, resume as healthy. If any still fail, record as regressed.

- **Healthy**: record post-layout suite result in ledger `simplification.post_layout_baseline`. Print Phase A summary (see Final report). Advance to Phase B or stop if `--phases` excludes Phase B.
- **Regressed**: print the regressed test ids (confirmed after retry), set `phase: failed-layout`, emit `say_skill_done`, stop at Phase A.

---

## Phase B — Simplification

Phase B runs immediately after a healthy Phase A. The baseline for Phase B is the post-layout suite result.

### Redundancy criteria

A test is a **simplification candidate** when it meets one of these criteria. **All criteria require identical fixture parameters, mock/stub configurations, and decorators between compared tests** unless the criterion says otherwise.

| Criterion | Action |
|-----------|--------|
| **Exact duplicate** | Remove one — byte/AST-identical body AND identical fixtures, mocks, decorators (ignoring only name and docstring) |
| **Dead test** | Flag for review — no assertion statement in body (per-language vocabulary in `reference/patterns.md`) |
| **Trivially true** | Remove — only `assert True`, `assertEqual(x, x)`, `expect(1).toBe(1)` |
| **Subset assertions** | Remove weaker — same function, same args, same fixtures+mocks; A's assertion list is a strict subset of B's |
| **Parametrize cluster** | Consolidate — N ≥ 3 tests call the same function with distinct args of the same structural type, identical fixtures+mocks, identical assertion pattern |
| **Parametrize pair** | Consolidate — N = 2 tests meeting cluster criteria where names differ only by trailing integer or single-letter suffix |

**Do NOT flag** as redundant: tests covering different scenarios, different input types, different fixture state, different mock return values, different decorators/markers, or any test the AST parser cannot fully analyze.

### Step 7 — Scan and build simplification plan

Set ledger `phase: simplifying`.

Parse every test file (post-layout) using the language's AST parser. For each test function extract: name, body AST, fixture parameters, mock/stub configurations, decorator list, primary source function called, call arguments, assertion list.

Apply criteria in order: exact duplicate → dead → trivially true → subset → parametrize cluster → parametrize pair.

For each **removal** candidate: emit `{ file, test_name, criterion, evidence }` (evidence = ≤2-line excerpt proving the criterion).

For each **dead-test candidate**: emit `{ file, test_name, criterion: "dead-test", evidence }` to `review_candidates` array (not `removals`).

For each **parametrize** candidate:
- Verify expected assertion values share a structural type across all N tests (same type homogeneity). If they differ in type, classify as **unanalyzable**, skip.
- Emit `{ file, tests: [...], consolidated_name, consolidated_body, required_imports, criterion, evidence }` where `consolidated_body` is a concrete parametrized test body with the actual parameter tuples derived from the originals.

Ordering guard: if test A is a subset of B and B is itself a removal candidate, plan to remove B first.

Write `$PROJECT_PATH/.scratch/refactor-tests/simplification-plan.json`.

### Step 8 — Execute simplification

**Removals**: delete each named test function from its file using the language's AST editor. Record each in ledger `simplification.removals` after the write. If removing the last test function in a file, delete the file with `git rm`.

**Parametrizations** (atomic per entry): in a **single file write** — delete all N original test functions, insert the consolidated parametrized function, add any `required_imports` not already present. Record in ledger `simplification.parametrizations` in the same durable step. If the AST editor cannot perform the composite edit, record as `skipped` in the ledger with the error, leave the file unchanged, surface in the report.

### Step 9 — Validate simplification

Set ledger `phase: simplify-validating`.

Re-run the full suite. Regression check: compare against post-layout baseline. Exclude test ids in `simplification.removals` and replaced ids in `simplification.parametrizations` from the required-passing set. Verify each consolidated parametrized test id appears and passes.

If any regressed id is found, **re-run the full suite once** to confirm (flake detection; Phase B is post-consolidation so a failure under load is distinct from isolation). If all pass on retry, resume as healthy. If any still fail, record as regressed.

- **Healthy**: advance to Phase C when ledger `spring_boot` is `true` and `--phases` includes Phase C, otherwise set `phase: done`.
- **Regressed**: record regressed ids, set `phase: failed-simplify`, stop at Phase B.

---

## Phase C — Context cost (Spring Boot only)

Runs after a healthy Phase B, only when ledger `spring_boot` is `true`. Phases A and B reorganize files and test functions; Phase C cuts the **runtime cost of the Spring application context** the surviving tests load — a separate axis, so it gets its own gate.

**Disclosure: Phase C modifies source code outside the test tree.** It adds `autoStartup = "\${...}"` attributes to `@KafkaListener` annotations and `initialDelayString` to `@Scheduled` annotations in `src/main/` — always with defaults that preserve production behaviour. See Step C3 in `reference/springboot.md` for the knobs and their safety properties.

Read `reference/springboot.md` and execute its Steps C0–C4, setting the ledger `phase` at each: C1 `context-measuring`, C2 `context-consolidating`, C3 `context-switching`, C4 `context-validating`. The baseline for Phase C is the post-simplification suite result plus the context/wall-time numbers from its Step C1.

On regressed ids in Phase C, **re-run the full suite once** (not just the ids in isolation) to confirm — full-suite re-run surfaces Trap 4 state leakage.

- **Healthy** (zero regressions): set `phase: done`. Wall-time improvement is reported but not gated (machine-noisy). Context count is reported.
- **Regressed**: record regressed ids, set `phase: failed-context`.

---

## Final report

**Phase A — Layout:**
- Files moved: count and move list (sample if large)
- Imports rewritten: count with representative rewrites
- Cross-cutting (moved to integration dir): list with `from` → `to` and reason
- Baseline: `<N> passed, <M> failed`
- Post-layout: `<N> passed, <M> failed` — `✓ zero regressions` or `✗ <k> regressions (after flake retry):` + ids

**Phase B — Simplification:**
- Tests removed: count by criterion (exact-duplicate, trivially-true, subset)
- Tests flagged for review (dead-test): count with listing; user decides whether to remove
- Tests parametrized: count; before/after listing (original names → consolidated name + parameter tuples)
- Parametrizations skipped (AST editor failures): list with reasons
- Unanalyzable files (skipped by AST parser): list with reasons
- Post-simplification: `<N> passed, <M> failed` — `✓ zero regressions` or `✗ <k> regressions (after flake retry):` + ids

**Phase C — Context cost** (Spring Boot only): classes consolidated per cluster; Spring contexts before → after; per-context switches applied; clusters skipped with reasons; wall time before → after (informational, not gated).

Report only the phases that ran. When a gate regressed, name the phase that stopped the run and say the later phases were not reached — resolve those regressions and re-run to continue.

**Warnings**: AST parse/edit failures, imports not rewritten, runner-detection ambiguities, pinned-fixture location exceptions

**Next steps** if regressed: files to inspect; `git checkout -- <paths>` to revert selectively

---

## Audio completion

```sh
proj="$(basename "${CLAUDE_PROJECT_DIR:-$PWD}")"
proj_say="$(printf '%s' "$proj" | tr '_-' '  ')"
msg="Refactor tests finished${proj_say:+ in ${proj_say}}."
[ -f ~/.claude/hooks/say-cue-lib.sh ] && . ~/.claude/hooks/say-cue-lib.sh && say_skill_done "$msg" || true
```

---

## Hard invariants

- Do NOT launch headless `claude` CLI processes via Bash.
- Never pass plan or file text as a shell argument — write to a temp file if Bash must read it.
- **Expected non-zero exits** (test runners, detection probes) are data, not errors; only hard-abort on process errors (127, signals).
- Import rewriting and test editing are AST-based per language — never blind regex search-replace.
- Each parametrize consolidation is a single atomic file write; ledger entry written in the same durable step.
- Leave every change in the working tree for the user to review and commit — no `git commit`, and no auto-rollback on a regressed health gate.
- Update the ledger after every durable side effect so a mid-run compaction is recoverable.
- On `--dry-run`: write `plan.json` and `simplification-plan.json` then exit; no file mutations.
- `rm -f` any temp file on every exit path, including hard-abort paths.
- Clear the audio-suppression marker via `say_skill_done`/`say_skill_cancel` on every exit path.
