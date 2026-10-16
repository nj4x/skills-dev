---
name: refactor-tests
description: Reorganize a flat test suite to mirror source packages, prune redundant/dead tests, and cut Spring Boot context startup cost.
argument-hint: "[project-path]"
---

You are refactoring a project's test suite along three axes, each behind its own **health gate**: where test files live, which test functions survive, and what the surviving tests cost to start up.

`PROJECT_PATH`: `$1` (default: `$PWD`)

End state — every source file accounted for, every applicable axis reached:
- **Phase A · Layout**: every test file at the location its language convention dictates for the source it exercises, imports rewritten to stay valid, suite passes with zero regressions.
- **Phase B · Simplification** (opens with a per-test evidence pass): redundant unit tests removed; clusters of tests that call the same function with varying inputs under the same assertion pattern consolidated into parametrized test cases.
- **Phase C · Context cost** (Spring Boot only): distinct Spring application contexts reduced, per-context background work switched off, suite wall time lower, assertions unchanged.

A gate is **healthy** when zero tests that passed at that phase's baseline now fail. A **regressed** gate stops the run at that phase — the later phases never start.

Read `reference/patterns.md` (beside this SKILL.md) before doing any work — it holds path templates, language-detection heuristics, AST tool guidance, and ledger/plan schemas.

---

## Hard Invariants

Every step relies on these preconditions:

- Do NOT launch headless `claude` CLI processes via Bash.
- Never pass plan or file text as a shell argument — write to a temp file if Bash must read it.
- **Expected non-zero exits** (test runners, detection probes) are data, not errors; only hard-abort on process errors (127, signals).
- Import rewriting and test editing are AST-based per language — never blind regex search-replace.
- Each parametrize consolidation is a single atomic file write; ledger entry written in the same durable step.
- Leave every change in the working tree for the user to review and commit — no `git commit`, and no auto-rollback on a regressed health gate.
- Update the ledger after every durable side effect so a mid-run compaction is recoverable.
- On `--dry-run`: write `plan.json` and `simplification-plan.json` then exit; no file mutations. The evidence pass still runs: it writes only under `.scratch/refactor-tests/`.
- `rm -f` any temp file on every exit path, including hard-abort paths.
- Clear the audio-suppression marker via `say_skill_done`/`say_skill_cancel` on every exit path.

---

## Step 0 — Audio suppression

```sh
[ -f ~/.claude/hooks/say-cue-lib.sh ] && . ~/.claude/hooks/say-cue-lib.sh && say_skill_start || true
```

---

## Step 1 — Resolve project and detect stack

1. `PROJECT_PATH` defaults to `$PWD`. Resolve to absolute path; hard-stop if not a directory.
2. **Parse command-line arguments**: `--dry-run` (skip file mutations, stop after plan), `--phases=A,B` (run only specified phases, default all available).
3. **Ledger resume.** If `$PROJECT_PATH/.scratch/refactor-tests/ledger.json` exists and `phase` is not `done`/`failed-*`, print the recorded phase and resume from it. On resume from `failed-*`, archive the old ledger to `ledger.YYYY-MM-DDTHH-MM-SS.json` and reuse the stored `baseline`. When `phase` is `done`, a fresh run is starting over an already-completed one: archive `ledger.json`, `plan.json`, and (if present) `simplification-plan.json` and `test-evidence.json` to their own `<name>.YYYY-MM-DDTHH-MM-SS.json` before writing new ones — the prior run's record would otherwise be silently overwritten with no trace. Otherwise (no ledger present) initialize a fresh ledger with `phase: discovery`.
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

**Fixed order.** For Python, when pytest-randomly is importable in the runner's environment (probe with the runner's own launcher, e.g. `uv run python -c 'import pytest_randomly'` or `.venv/bin/python -c ...`; exit 0 means present), append `-p no:randomly` to the resolved runner command and record the command with the flag in ledger `runners`. Every baseline and validation run, flake retries included, uses that recorded command, so test order stays fixed between runs.

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

Re-run the full suite with the recorded runner command (fixed order, see Step 3). Regression check: for each test id that passed in `baseline`, map it to its new id via `id_map` (or keep original id if unmoved), verify the mapped id still passes.

If any regressed id is found, **re-run just those ids once** with the recorded runner command to confirm the failure (flake detection). If they all pass on retry, resume as healthy. If any still fail, record as regressed.

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
| **Dead test** | Review only, never removed — no assertion statement in body (per-language vocabulary in `reference/patterns.md`) |
| **Trivially true** | Remove — only `assert True`, `assertEqual(x, x)`, `expect(1).toBe(1)` |
| **Coverage subset** | Review only, never removed — every line and branch arc the test covers is also covered by other passing tests (evidence-based; fixture identity not required; see Step 8) |
| **Cost** | Review only, never removed — a coverage-subset candidate in the top decile by `call_s`, at or above 0.5 s (evidence-based; see Step 8) |
| **Parametrize cluster** | Consolidate — N ≥ 3 tests call the same function with distinct args of the same structural type, identical fixtures+mocks, identical assertion pattern |
| **Parametrize pair** | Consolidate — N = 2 tests meeting cluster criteria where names differ only by trailing integer or single-letter suffix |

**Do NOT flag** as redundant: tests covering different scenarios, different input types, different fixture state, different mock return values, different decorators/markers, or any test the AST parser cannot fully analyze.

### Step 7 — Evidence pass

Set ledger `phase: evidence`. This step runs first in Phase B, on post-layout test ids: after a healthy Step 6, or after Step 3 when `--phases` excludes Phase A (ids are then the current ids). It runs under `--dry-run` and `--phases=B` too. It never gates the run: a failure degrades to less evidence (see Degrade rules).

**Ledger resume.** Ledger `evidence.<lang>.status` of `ok`, `skipped`, or `failed` is final: reuse it and skip that language. Run only languages with no status.

The pass is Python-only for now; other languages get `status: skipped` with reason `no evidence tooling for <lang>`. Helper scripts live in `reference/python/` beside this SKILL.md; call it `$SKILL_DIR` (the directory holding this SKILL.md). Write all outputs under `$PROJECT_PATH/.scratch/refactor-tests/`. Edit no project config; install tools ephemerally (`uv run --with …`, or `pip install --target` into `.scratch/refactor-tests/` plus `PYTHONPATH`, when the runner is not uv). Build both commands from the recorded runner command of Step 3: keep its launcher and add the tool flags. Examples below use a uv launcher; for another launcher, make `pytest-cov` and `coverage` importable first, then run plain `pytest`.

1. **Coverage run** (traced, fixed order). Replace `<source roots>` with the ledger `source_roots`, one `--cov=` each:

   ```sh
   COVERAGE_CORE=ctrace COVERAGE_FILE=.scratch/refactor-tests/.coverage-python \
     uv run --with pytest-cov --with coverage pytest -p no:randomly --cov=<source roots> --cov-branch --cov-context=test
   ```

   `COVERAGE_CORE=ctrace` is required on every Python version: on 3.14+ the default `sysmon` core silently drops contexts that pytest-cov sets. Record the command and tool versions (`coverage`, `pytest-cov`, `pytest`) for the evidence file.
2. **Timing run** (serial, untraced: tracing inflates durations unevenly). No `--cov`, no `-n`:

   ```sh
   PYTHONPATH=$SKILL_DIR/reference/python${PYTHONPATH:+:$PYTHONPATH} CALLTIME_FILE=.scratch/refactor-tests/calltime-python.json \
     uv run --with pytest-cov pytest --no-cov -p no:randomly -p calltime
   ```

   Project `addopts` stay in force, so collection matches the coverage run. `--no-cov` cancels any `--cov` in them. When they carry `-n`/`--numprocesses`, xdist is already installed: append `-n0` to keep the run serial. `calltime.py` writes one `{duration, outcome}` row per test, keyed by node id. Passed and failed tests get the call-phase duration. A test whose setup skipped or failed gets its outcome and `duration: null`. A failed teardown turns the outcome to `failed` and keeps the call duration.
3. **Extract per-test arcs**: `python $SKILL_DIR/reference/python/extract_arcs.py .scratch/refactor-tests/.coverage-python --root $PROJECT_PATH > .scratch/refactor-tests/arcs-python.json` (exits non-zero when the data file is missing or has no `|run` context: treat as a failed run) (needs `coverage` importable: prefix with `uv run --with coverage`). The script reads only `|run` contexts via `CoverageData.set_query_contexts`, one per test, then `lines()` and `arcs()`. Setup and teardown contexts are fixture-owned coverage and are ignored.
4. **Assemble** (schema in `reference/patterns.md`): `python3 $SKILL_DIR/reference/python/assemble_evidence.py --arcs .scratch/refactor-tests/arcs-python.json --calltime .scratch/refactor-tests/calltime-python.json --tool name=version … --command coverage='…' --command timing='…' --existing .scratch/refactor-tests/test-evidence.json --out .scratch/refactor-tests/test-evidence.json`. Always pass `--existing`: it merges with a block another language wrote earlier in this run, and a missing file counts as empty. `--out` is written atomically. Tests whose call `outcome` is not `passed` get no entry; the script lists them under `excluded`, a passed test with no coverage context is listed as `no-coverage`, and a covered id with no timing row as `no-timing`. A `--status skipped|failed` call needs `--reason`.
5. Record in ledger `evidence`: `{ file, python: { status: ok, reason: null, tests: <entry count> } }`. Delete the intermediate `.coverage-python`, `calltime-python.json`, and `arcs-python.json` files on every path, success or degraded.

**Degrade rules.** Evidence never stops the run.
- A tool will not install, a run crashes (exit 127 or signal), the coverage data file is missing, or the helper script exits non-zero: write the language block with `--status failed --reason <one line>`. A language with no tooling or no runner: `--status skipped`. Mirror status and reason in ledger `evidence.<lang>`; `tests` is 0.
- Exit 1 from either pytest run is data, not a failure: failing tests simply get no entry. Exit 2–5 (interrupted, internal error, usage error, no tests collected), or a timing file with zero `passed` rows, means the run itself broke: set `--status failed` with the exit code as reason.
- With status other than `ok`, drop every evidence-based item from the simplification plan (items that read coverage or `call_s`), and add a warning naming each dropped item kind. Evidence-free criteria still run.
- Non-`passed` tests: list them in the report; never invent entries for them.

---

### Step 8 — Scan and build simplification plan

Set ledger `phase: simplifying`.

Parse every test file (post-layout) using the language's AST parser. For each test function extract: name, body AST, fixture parameters, mock/stub configurations, decorator list, primary source function called, call arguments, assertion list.

Apply criteria in order: exact duplicate → dead → trivially true → coverage subset → cost → parametrize cluster → parametrize pair.

For each **removal** candidate (exact duplicate, trivially true): emit `{ file, test_name, criterion, evidence }` (evidence = ≤2-line excerpt proving the criterion).

For each **dead-test candidate**: emit `{ file, test_name, criterion: "dead-test", evidence }` to the `review_candidates` array only, never to `removals`. The user decides whether to remove it.

**Coverage-subset and cost candidates** (evidence-based, review only). Run only when the evidence status of the language is `ok`; otherwise the degrade rules of Step 7 drop them. Read `test-evidence.json`:

```sh
python3 $SKILL_DIR/reference/python/select_candidates.py --evidence .scratch/refactor-tests/test-evidence.json
```

The script prints the entries as a JSON list. Append them to `review_candidates`, never to `removals`. It applies these rules per language:
- **Coverage subset**: test T is a candidate when every line and arc in its `covered` map is in the union of the other passing tests' `|run` coverage. A test with an empty `covered` map is never a candidate. Process tests in descending `call_s` and remove each flagged test from the union, so of two tests that cover each other only the slower is flagged. Entry: `criterion: "coverage-subset"`, with `call_s` and `time_saved_s` (the test's own `call_s`).
- **Cost**: rank the coverage-subset candidates by `call_s`, descending. Take the top decile (ceiling of 10% of the candidates, minimum 1). Flag each one whose `call_s` is at least 0.5 s. Entry: `criterion: "cost"`, with `call_s` and `time_saved_s`. A test flagged by both criteria gets one entry per criterion. A slow test with unique coverage is never a cost candidate.

For each **parametrize** candidate:
- Verify expected assertion values share a structural type across all N tests (same type homogeneity). If they differ in type, classify as **unanalyzable**, skip.
- Emit `{ file, tests: [...], consolidated_name, consolidated_body, required_imports, criterion, evidence }` where `consolidated_body` is a concrete parametrized test body with the actual parameter tuples derived from the originals.

Write `$PROJECT_PATH/.scratch/refactor-tests/simplification-plan.json`, with top-level `evidence: { file: ".scratch/refactor-tests/test-evidence.json", status }`. `status` is `ok` when any language is `ok`, else `failed` when any is `failed`, else `skipped`.

### Step 9 — Execute simplification

**Removals**: delete each named test function from its file using the language's AST editor. Record each in ledger `simplification.removals` after the write. If removing the last test function in a file, delete the file with `git rm`.

**Parametrizations** (atomic per entry): in a **single file write** — delete all N original test functions, insert the consolidated parametrized function, add any `required_imports` not already present. Record in ledger `simplification.parametrizations` in the same durable step. If the AST editor cannot perform the composite edit, record as `skipped` in the ledger with the error, leave the file unchanged, surface in the report.

### Step 10 — Validate simplification

Set ledger `phase: simplify-validating`.

Re-run the full suite with the recorded runner command (fixed order, see Step 3). For Python with Step 7 `evidence.python.status` of `ok`, load the `calltime` hook in the first validation run only, and make it match the Step 7 timing run (serial, untraced): build it as in Step 7 (make `pytest-cov` importable, so `--no-cov` is a known flag), prefix `PYTHONPATH=$SKILL_DIR/reference/python${PYTHONPATH:+:$PYTHONPATH} CALLTIME_FILE=.scratch/refactor-tests/calltime-after-python.json`, append `--no-cov -p calltime`, and append `-n0` when project `addopts` carry `-n`/`--numprocesses`. The flake retry below uses the plain recorded command. With any other evidence status, load no hook. Regression check: compare against post-layout baseline. Exclude test ids in `simplification.removals` and replaced ids in `simplification.parametrizations` from the required-passing set. Verify each consolidated parametrized test id appears and passes.

If any regressed id is found, **re-run the full suite once** with the recorded runner command to confirm (flake detection; Phase B is post-consolidation so a failure under load is distinct from isolation). If all pass on retry, resume as healthy. If any still fail, record as regressed.

**Serial call time.** After the first validation run (the one that loaded the hook), compare per-test call time before and after. Pass one `--removed <file>::<test_name>` per ledger `simplification.removals` entry:

```sh
python3 $SKILL_DIR/reference/python/calltime_delta.py --evidence .scratch/refactor-tests/test-evidence.json \
  --calltime .scratch/refactor-tests/calltime-after-python.json --removed '<file>::<test_name>' …
```

Before is the total `call_s` of the evidence pass timing run (tests with an evidence entry); after is the total call duration of the passed rows in the validation run, minus ids listed under evidence `excluded` so both totals cover the same population. A missing `--calltime` file omits the figures with a warning; pass `--removed` the full node id (`<file>::<Class>::<test>`) or the bare `<file>::<test>`. The script prints `before_s`, `after_s`, `delta_s`, and `call_s` per removed test id, labelled "serial call time, not wall time". Record its output in ledger `simplification.call_time`. When the evidence status is not `ok` or the calltime file is missing, the script returns null figures and a `warning`: omit both totals from the report and surface the warning. Delete `calltime-after-python.json` on every path.

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

## Follow-up: Assertion-API enforcement (optional)

After Phase B normalises the assertion vocabulary (e.g., `kotlin.test` over JUnit Jupiter for Kotlin projects), lock it in with a static-analysis rule that fails the build on banned imports. This prevents Phase B invariants from drifting in future PRs without any code review burden.

**Kotlin/Gradle:** Add a `ForbiddenImport` rule set to a `detekt-test.yml` config targeting `src/test/`. Make the `test` task depend on `detektTest`. The rule set lists every JUnit import that the project decided to replace with `kotlin.test` equivalents, with a `reason` pointing to the replacement. Example from the reference project (commit 22759691): ban `org.junit.jupiter.api.Test`, `org.junit.jupiter.api.Assertions.*`, `org.junit.jupiter.api.BeforeEach`, etc. in favour of `kotlin.test.Test`, `kotlin.test.assertEquals`, `kotlin.test.BeforeTest`.

**Java/Maven:** Equivalent with Checkstyle `IllegalImport`.

---

## Final report

**Phase A — Layout:**
- Files moved: count and move list (sample if large)
- Imports rewritten: count with representative rewrites
- Cross-cutting (moved to integration dir): list with `from` → `to` and reason
- Baseline: `<N> passed, <M> failed`
- Post-layout: `<N> passed, <M> failed` — `✓ zero regressions` or `✗ <k> regressions (after flake retry):` + ids

**Phase B — Simplification:**
- Evidence: status per language (`ok`/`skipped`/`failed` plus reason), tests recorded, tests excluded (listed with outcome: did not pass, `no-coverage`, or `no-timing`), and a warning for each evidence-based item dropped
- Tests removed: count by criterion (exact-duplicate, trivially-true)
- Tests parametrized: count; before/after listing (original names → consolidated name + parameter tuples)
- Parametrizations skipped (AST editor failures): list with reasons
- Tests flagged for review: `review_candidates` grouped by criterion (dead-test, coverage-subset, cost), count and listing per group; for coverage-subset and cost, each test with its `time_saved_s` and a running total per criterion group (a test in both groups is one test: count its time once in any combined total), labelled "serial time, not wall time"; user decides whether to remove
- Unanalyzable files (skipped by AST parser): list with reasons
- Serial call time, not wall time: `<before> s → <after> s (Δ <delta> s)`, plus `call_s` per removed test; when evidence was not `ok`, omit the totals and print the warning
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

