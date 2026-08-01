---
name: refactor-tests
description: Refactor a project's flat test layout into a source-package-mirrored structure (polyglot — Python, TS/JS, Go, Java/Kotlin). Use when a project's tests live in one flat directory and you want them reorganized to mirror the source packages so that changed code maps to a small, relevant test subset. Keywords - test refactor, mirror tests, test layout, package-mirrored tests, reorganize tests.
disable-model-invocation: true
argument-hint: "[project-path]"
---

You are refactoring a project's test layout to mirror its source package structure.

PROJECT_PATH: $1 (default: `$PWD`)

The end state: every test file sits at the location its language convention dictates for the source it exercises (see `reference/patterns.md`), imports are rewritten to stay valid, and the full test suite passes with zero regressions against a pre-refactor baseline.

---

## Step 0 — Load repeat contract

Check whether `~/.claude/skills/repeat/SKILL.md` exists:
```bash
test -f ~/.claude/skills/repeat/SKILL.md && echo FOUND || echo MISSING
```

- **FOUND**: Read `~/.claude/skills/repeat/SKILL.md` and follow the repeat loop contract, binding the extension points below (GENERATE_STEP, REVIEW_STEP, FINALIZE_STEP). The repeat contract governs Guards, Mode detection, the Decision Protocol, and the loop — do not re-derive them here.
- **MISSING**: stop with: `repeat skill not found. Install it with: ln -s /Users/roman/projects/skills-dev/planning/repeat ~/.claude/skills/repeat`

The **artifact** the loop refines is the **migration plan** — the list of file moves and import rewrites, held on disk as `.scratch/refactor-tests/plan.json` under `PROJECT_PATH`. GENERATE_STEP builds and refines that plan; REVIEW_STEP is an adversarial critic over the plan; FINALIZE_STEP executes the approved plan and runs the one-shot health gate.

Read `reference/patterns.md` (beside this SKILL.md) before GENERATE_STEP — it holds the per-language path templates, language-detection heuristics, and the ledger/plan schema.

---

## Step 1 — Resolve project and detect stack

1. `PROJECT_PATH` defaults to `$PWD`. Resolve to an absolute path; hard-stop if it is not a directory.
2. **Ledger resume check.** If `$PROJECT_PATH/.scratch/refactor-tests/ledger.json` exists and its `phase` is not `done`, print the recorded phase and resume from it (see [Ledger and resume](#ledger-and-resume)). Otherwise initialize a fresh ledger with `phase: discovery`.
3. **Detect languages** by extension scan (`reference/patterns.md` → Language detection). Record the set of present languages and, per language, the source roots discovered (multi-root: all `src/`, `lib/`, `packages/*/src/`, `src/main/java` trees).
4. **Detect the test runner(s)** per language via convention markers (`reference/patterns.md` → Runner detection). Store them in the ledger.

---

## Ledger and resume

The ledger at `$PROJECT_PATH/.scratch/refactor-tests/ledger.json` is the durable record that survives context compaction. Schema in `reference/patterns.md`. It tracks:

- `phase`: one of `discovery`, `planning`, `baseline`, `moving`, `rewriting`, `validating`, `done`
- `languages`, `source_roots`, `runners`
- `baseline`: the pre-refactor suite result (per runner: passed count, failed test ids)
- `moves`: applied file moves (`from` → `to`), appended as each is written to disk
- `rewrites`: applied import rewrites (`file`, count)

Update the ledger after **every** durable side effect (each move, each rewrite batch, each phase transition), not in a single trailing write — a mid-phase compaction must be recoverable. On resume, re-derive in-flight state from the ledger and continue; never re-apply a move already recorded in `moves`.

---

## Extension point bindings

### GENERATE_STEP — Build/refine the migration plan

Set ledger `phase: planning`.

**Iteration 0 (FRESH):** produce the migration plan.

For each detected source file in each source root:
1. Compute its **target test path** from the language path template (`reference/patterns.md`).
2. Find its **existing test(s)**: query `search-codebase` (`search_root`) for tests referencing the file's public symbols; fall back to `fd`/`rg` by filename and by the flat-layout naming pattern (e.g. `test_<module>.py`). This is the same search-codebase-first, path-based-fallback strategy the `testing` skill uses.
3. Emit a move entry `{ from: <current test path>, to: <target test path>, language, source_file }` when the two differ.
4. For each moved file, statically determine the **import rewrites** its relocation forces (relative-import depth changes; see `reference/patterns.md` → Import rewriting). Emit `{ file, edits: [...] }`.

Classify tests that map to **no single source file** (fixtures, integration, e2e, tests exercising many packages) as **cross-cutting**: record them under `unmapped` with the reason. Do **not** move them in v1 — leave them in place and surface them in the report.

Write the plan to `.scratch/refactor-tests/plan.json` and return its path as `artifact_text` (the artifact in flight is the path, per the repeat file-based-artifact convention). In `guided` mode, append a `FLAGGED_DECISIONS` block for any genuinely ambiguous mapping (e.g. a test that plausibly belongs to two modules).

**Iteration > 0 (revision):** read the critic's issues, edit `plan.json` in place to address each major finding, and return the path again.

### REVIEW_STEP — Adversarial critic over the plan

Invoke an Agent (`subagent_type: "claude"`) that reads `plan.json` and the project tree, and returns **raw JSON** `{ verdict, severity, top_issues, suggested_fixes }` (same contract and temp-file validation harness as the `critic` skill). The critic evaluates ONLY the plan, on these lenses:

- **Completeness**: is every existing test file either in a `move`, already at its target, or justified under `unmapped`? A test silently dropped from all three is a **major**.
- **Correctness**: does each `to` path match the language template for its `source_file`? Wrong target = **major**.
- **Import soundness**: will the recorded rewrites keep each moved file's imports resolvable? A move with a depth change but no corresponding rewrite = **major**.
- **Collisions**: do two moves target the same path? = **major**.
- **Cross-cutting judgment**: is anything in `unmapped` actually cleanly mappable (under-classification), or is a `move` actually cross-cutting (over-classification)? = **minor** unless it would break the suite.

Approve when no major remains. Prefix each issue `[<lens>][major|minor] claim — evidence`.

### FINALIZE_STEP — Execute plan and run the health gate

Only when `approved == True` (verdict `approve`, severity not `major`, cap not reached). If not approved, write the plan and critic summary as text, leave the project untouched, call `say_skill_done`, and return.

Approved path:

1. **Baseline** (`phase: baseline`). Run the full suite per runner (`reference/patterns.md`). Record pass count and the set of failing test ids into ledger `baseline`. A pre-existing failure is part of the baseline, not a regression.
2. **Move** (`phase: moving`). Apply each `move` with `git mv` (preserves history; falls back to plain move outside git). Record each in ledger `moves` as it happens.
3. **Rewrite** (`phase: rewriting`). Apply each import rewrite using the language's AST tool (`reference/patterns.md` → Import rewriting) — never blind regex. Record each in ledger `rewrites`.
4. **Validate** (`phase: validating`). Re-run the full suite. Compare to `baseline`:
   - **Healthy** = the set of passing tests is a superset of the baseline passing set and no new failures appeared. Set `phase: done`.
   - **Regressed** = any test that passed in baseline now fails, or a collected test errors on import. **Leave the refactored state intact** (do not roll back) and carry the failing set into the report for the user to fix forward or revert via git.
5. **Report** (detailed, per #24) and `say_skill_done`.

**Do not commit.** Leave all changes in the working tree for the user to review with `git diff` and commit themselves.

---

## Final report

Print:

- **Files moved**: count, and the move list (or a sample if large)
- **Imports rewritten**: count, with a few representative rewrites
- **Cross-cutting (left in place)**: the `unmapped` list with reasons
- **Baseline**: `<N> passed, <M> failed` before refactor
- **Post-refactor**: `<N> passed, <M> failed` — `✓ zero regressions` or `✗ <k> regressions:` followed by the regressed test ids
- **Warnings**: AST parse failures, imports that could not be rewritten, runner-detection ambiguities
- **Next steps** if regressed: which files to inspect, and `git checkout -- <paths>` to revert selectively

---

## Hard invariants

- Do NOT launch headless `claude` CLI processes via Bash.
- Never pass plan or file text as a shell argument. Write to a temp file when Bash must read it.
- Bash non-zero exit, unparseable critic JSON, or a missing required field = hard abort. Never treat as approval.
- Import rewriting is AST-based per language — never blind regex search-replace.
- On a regressed health gate, **never** auto-rollback and never `git commit`; leave the tree for the user.
- Update the ledger after every durable side effect so a mid-run compaction is recoverable.
- `rm -f` any temp file on every exit path, including hard-abort paths.
- The repeat audio-suppression marker must be cleared via `say_skill_done`/`say_skill_cancel` on every exit path.
