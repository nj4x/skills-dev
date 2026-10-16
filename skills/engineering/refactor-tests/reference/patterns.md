# refactor-tests reference

Path templates, detection heuristics, and on-disk schemas for the `refactor-tests` skill.

## Language detection

Scan `PROJECT_PATH` for source files (respect `.gitignore`; skip `vendor/`, `node_modules/`, `.venv/`, `build/`, `.reference-projects/`, and any `.scratch/` tree). A language is **present** when its source extension appears outside test files:

| Language | Source extensions | Layout style |
|---|---|---|
| Python | `.py` | mirrored tree |
| TypeScript/JavaScript | `.ts`, `.tsx`, `.js`, `.jsx` | co-located |
| Go | `.go` | co-located |
| Java/Kotlin | `.java`, `.kt` | mirrored tree |

A project may be polyglot — apply each language's rule to its own files independently.

**Source roots** (multi-root auto-discovery): treat each of these, where present, as a root and mirror it independently — `src/`, `lib/`, `app/`, every `packages/*/src/` (monorepo), and `src/main/java` / `src/main/kotlin` (Maven/Gradle).

## Path templates

Let a source file be `<root>/<pkg-path>/<name>.<ext>`.

### Python — mirrored tree
- Target: `tests/<pkg-path>/test_<name>.py`
- Example: `src/protrading/adapters/instruments.py` → `tests/protrading/adapters/test_instruments.py`
- The `src/` prefix is dropped; the package path below it is preserved. Create `__init__.py` in new test dirs only if the existing test tree uses package-style test dirs (detect by presence of any `tests/**/__init__.py`).

### TypeScript / JavaScript — co-located
- Target: `<root>/<pkg-path>/<name>.test.<ext>` (or `.spec.<ext>` — match the project's existing suffix; if both appear, prefer `.test`)
- Example: `src/foo/bar/baz.ts` → `src/foo/bar/baz.test.ts`
- The test file moves **next to** its source, not into a separate tree.

### Go — co-located
- Target: `<dir>/<name>_test.go` in the same directory as the source
- Example: `pkg/foo/handler.go` → `pkg/foo/handler_test.go`
- Go's convention is already co-located; a refactor here mostly relocates strays back beside their source.

### Java / Kotlin — mirrored tree
- Target: `src/test/<lang>/<pkg-path>/<Name>Test.<ext>` mirroring `src/main/<lang>/<pkg-path>/<Name>.<ext>`
- Example: `src/main/java/com/foo/Bar.java` → `src/test/java/com/foo/BarTest.java`

## Integration directory targets (cross-cutting tests)

Cross-cutting tests are moved to a dedicated integration directory — not left in place. File names are preserved.

| Language | Integration target directory |
|---|---|
| Python | `tests/integration/` |
| TypeScript/JavaScript | `tests/integration/` |
| Go | `integration/` (at project root) |
| Java/Kotlin | `src/test/integration/` |

**Directory guard check.** Before moving any file into the integration target, check whether that directory is constrained by a project-specific guard — a meta-test or CI check that restricts what may live there (e.g. a frozen baseline file, a marker/fixture requirement enforced by AST). Look for it the same way you'd look for the runner: a project doc (`AGENTS.md`/`CLAUDE.md`-pointed testing guide) describing the directory's membership rule, or a test file named after the constraint. If such a guard exists and the candidate file would violate it (e.g. it doesn't carry the required marker/fixture and the baseline may not grow), do not move it — leave it in place and record it as pinned (same treatment as the Go build-tag exception below), with the guard's name as the reason.

## Test-file naming

| Language | Test file name for source `<name>` |
|---|---|
| Python | `test_<name>.py` |
| TS/JS | `<name>.test.ts` / `<name>.spec.ts` (match existing) |
| Go | `<name>_test.go` |
| Java/Kotlin | `<Name>Test.java` / `<Name>Test.kt` |

## Per-runner output formats

Capture test ids using runner output specified here:

| Language | Command | Output file | Parse notes |
|---|---|---|---|
| Python | `pytest --junitxml=<file> [paths...]` (add `-p no:randomly` when pytest-randomly is importable in the runner's environment, to pin fixed order) | JUnit XML | Parse `<testcase classname="..." name="...">` elements; id = `classname::name` |
| TS/JS | `npm test -- --json --outputFile=<file>` | JSON via Jest | Extract `testResults[].assertionResults[].fullName`; id = `<file>::<fullName>` |
| Go | `go test -json ./... > <file>` | JSON | Parse `{"Test":"..."}` events; id = package + `::` + test name |
| Java (Maven) | `mvn test -Dorg.slf4j.simpleLogger.defaultLogLevel=info` (output to file) | Surefire XML in `target/surefire-reports/TEST-*.xml` | Parse `<testcase classname="..." name="...">` elements; id = `classname::name` |
| Java/Kotlin (Gradle) | `./gradlew test --rerun-tasks` (or `gradle test`) | Gradle test report | Parse `build/test-results/test/*/TEST-*.xml` files; id = `classname::name` |

Record runner output to a consistent temp location between baseline and validation runs; diff the id sets to detect regressions.

## Runner detection (convention markers)

| Language | Marker files (any) | Command |
|---|---|---|
| Python | `pytest.ini`, `pyproject.toml`, `setup.cfg`, `tox.ini` | `pytest` |
| TS/JS | `package.json` (has a `test` script) | `npm test` (or `yarn test` if `yarn.lock` exists, `pnpm test` if `pnpm-lock.yaml`) |
| Go | `go.mod` | `go test -json ./...` (use `-json` for structured id capture) |
| Java | `pom.xml` | `mvn test` |
| Java/Kotlin | `build.gradle`, `build.gradle.kts` | `gradle test` (or `./gradlew test` in root) |

If markers are ambiguous for a present language, try the candidate commands in table order and use the first that runs. Record the **exact resolved command** in the ledger so validation reuses the same baseline command.

## Assertion vocabulary (dead-test detection)

The dead-test criterion flags tests with no assertion statements. Use this vocabulary per language to identify assertions; a test with none of these is a candidate for the `review_candidates` array:

| Language | Assertion keywords |
|---|---|
| Python | `assert`, `pytest.raises`, `pytest.warns` |
| TypeScript/JavaScript | `expect`, `assert` (chai), `should` (should.js), `.to.throw` (chai), `.toThrow` (jest) |
| Go | `t.Error`, `t.Errorf`, `t.Fatal`, `t.Fatalf`, `require.*`, `assert.*` (testify) |
| Java | `assertThat`, `assertTrue`, `assertEquals`, `fail` (JUnit/AssertJ) |
| Kotlin | `assertThat`, `assertTrue`, `assertEquals`, `fail` (same as Java) |

## Import rewriting (AST-based, per language)

Moving a test file can invalidate **relative** imports (their depth to the source changes); **absolute/package** imports usually survive.

| Language | Parser | What to rewrite |
|---|---|---|
| Python | `libcst` (comment/format-preserving); fall back to stdlib `ast` splice when libcst is unavailable | relative `from ..x import y` whose depth changed; convert to absolute `from <pkg>.x import y` where the package path is known |
| TS/JS | TypeScript compiler API or Babel (`@babel/parser` + `@babel/traverse`) | relative `import ... from './x'` / `require('./x')` specifiers; recompute the `./`-relative path from the new location; leave path-alias and package imports untouched |
| Go | `go/parser` + `go/printer` (or `goimports`) | rarely needed — Go imports are module-absolute; run `goimports` on moved files to fix ordering; cross-cutting tests use `//go:build integration` tags instead of path moves (see below) |
| Java | `JavaParser` (com.github.javaparser) — parse compilation unit, update `PackageDeclaration` node, pretty-print | `package` declaration to match the new directory |
| Kotlin | Kotlin compiler PSI via `kotlin-compiler-embeddable` — update `KtPackageDirective` node, emit with PSI printer, `ktlint --format` for cleanup | `package` declaration to match the new directory |

Any file the parser cannot process is a **warning** (not a silent skip): record it in the report and leave its imports unchanged for manual follow-up.

### Go cross-cutting tests — build tags instead of moves

Go's one-directory-one-package rule makes moving cross-cutting tests across packages into a single `integration/` directory problematic (compile errors). Instead, **pin Go cross-cutting tests in place and add a build tag**:

```go
//go:build integration

package foo_test

// test code
```

This preserves the package (compilation works) and allows filtering: `go test ./...` excludes them; `go test -tags integration ./...` includes them. In Phase A, for Go cross-cutting tests: do not move, add `//go:build integration` to the top of each file, and record as non-moved in the ledger.

## Ledger schema (`.scratch/refactor-tests/ledger.json`)

```json
{
  "phase": "discovery|baseline|moving|rewriting|validating|evidence|seams|simplifying|simplify-validating|context-measuring|context-consolidating|context-switching|context-validating|done|failed-layout|failed-simplify|failed-context",
  "dry_run": false,
  "phases_requested": ["A", "B", "C"],
  "project_path": "/abs/path",
  "languages": ["python"],
  "source_roots": ["src"],
  "runners": { "python": "pytest" },
  "spring_boot": false,
  "baseline": { "python": { "passed": 412, "failed": ["tests/test_x.py::test_a"] } },
  "id_map": { "tests/test_instruments.py::test_parse": "tests/protrading/adapters/test_instruments.py::test_parse" },
  "moves": [
    { "from": "tests/test_instruments.py", "to": "tests/protrading/adapters/test_instruments.py", "language": "python", "source_file": "src/protrading/adapters/instruments.py", "cross_cutting": false },
    { "from": "tests/test_end_to_end.py", "to": "tests/integration/test_end_to_end.py", "language": "python", "source_file": null, "cross_cutting": true }
  ],
  "rewrites": [ { "file": "tests/protrading/adapters/test_instruments.py", "count": 2 } ],
  "evidence": {
    "file": ".scratch/refactor-tests/test-evidence.json",
    "python": { "status": "ok", "reason": null, "tests": 410 }
  },
  "seams": {
    "status": "confirmed",
    "modules": { "src/protrading/adapters/instruments.py": { "seams": [ { "name": "parse_instrument", "signal": "__all__", "status": "confirmed" } ] } }
  },
  "simplification": {
    "post_layout_baseline": { "python": { "passed": 412, "failed": [] } },
    "removals": [ { "file": "tests/protrading/adapters/test_instruments.py", "test_name": "test_parse_duplicate", "criterion": "exact-duplicate" } ],
    "review_candidates": [ { "file": "tests/protrading/adapters/test_instruments.py", "test_name": "test_always_passes", "criterion": "dead-test" } ],
    "parametrizations": [ { "file": "tests/protrading/adapters/test_instruments.py", "replaced": ["test_parse_1", "test_parse_2", "test_parse_3"], "consolidated_name": "test_parse_parametrized" } ],
    "call_time": { "label": "serial call time, not wall time", "before_s": 41.2, "after_s": 37.9, "delta_s": -3.3, "removed": [ { "id": "tests/protrading/adapters/test_instruments.py::test_parse_duplicate", "call_s": 0.012 } ], "warning": null }
  },
  "spring": {
    "baseline": { "context_count": 5, "wall_time_seconds": 42.5 },
    "consolidations": [
      { "file": "src/test/kotlin/com/org/support/AbstractApiDocumentationTest.kt", "base_class": "AbstractApiDocumentationTest", "annotations_removed": ["@SpringBootTest", "@AutoConfigureWebTestClient", "@AutoConfigureRestDocs"], "mocks_removed": 11 }
    ],
    "post_context_cost": { "context_count": 1, "wall_time_seconds": 28.3 }
  }
}
```

## Plan schema (`.scratch/refactor-tests/plan.json`)

```json
{
  "moves": [
    { "from": "...", "to": "...", "language": "python", "source_file": "..." }
  ],
  "rewrites": [
    { "file": "<to path>", "edits": [ { "before": "from ..x import y", "after": "from pkg.x import y" } ] }
  ],
  "cross_cutting": [
    { "from": "tests/test_end_to_end.py", "to": "tests/integration/test_end_to_end.py", "language": "python", "reason": "exercises adapters + audit + persistence; 3 distinct non-mocked classes" }
  ]
}
```

`plan.json` is the Phase A artifact; `baseline-ids.json` stores the baseline test id sets; `ledger.json` is the durable execution record, rewritten after every side effect so a mid-run compaction can resume. Archival of failed ledgers uses `ledger.YYYY-MM-DDTHH-MM-SS.json` naming.

## Simplification plan schema (`.scratch/refactor-tests/simplification-plan.json`)

```json
{
  "schema_version": 2,
  "evidence": { "file": ".scratch/refactor-tests/test-evidence.json", "status": "ok" },
  "removals": [
    {
      "file": "tests/protrading/adapters/test_instruments.py",
      "test_name": "test_parse_instrument_copy",
      "criterion": "exact-duplicate",
      "evidence": "body identical to test_parse_instrument (lines 42-51 vs 55-64)"
    }
  ],
  "review_candidates": [
    {
      "file": "tests/protrading/adapters/test_instruments.py",
      "test_name": "test_always_passes",
      "criterion": "dead-test",
      "evidence": "no assertion statement in body; executes code but no verify call"
    },
    {
      "file": "tests/protrading/adapters/test_instruments.py",
      "test_name": "test_parse_slow_roundtrip",
      "criterion": "coverage-subset",
      "evidence": "all 14 lines and 11 arcs also covered by other passing tests",
      "call_s": 1.84,
      "time_saved_s": 1.84
    },
    {
      "file": "tests/protrading/adapters/test_instruments.py",
      "test_name": "test_parse_slow_roundtrip",
      "criterion": "cost",
      "evidence": "call_s 1.84 s, top decile of 12 coverage-subset candidates, at least 0.5 s",
      "call_s": 1.84,
      "time_saved_s": 1.84
    }
  ],
  "parametrizations": [
    {
      "file": "tests/protrading/adapters/test_instruments.py",
      "tests": ["test_parse_equity", "test_parse_future", "test_parse_option"],
      "consolidated_name": "test_parse_instrument_by_type",
      "consolidated_body": "@pytest.mark.parametrize('symbol,expected_type', [('AAPL', 'equity'), ('ESZ4', 'future'), ('AAPL241220C200', 'option')])\ndef test_parse_instrument_by_type(symbol, expected_type):\n    result = parse_instrument(symbol)\n    assert result.type == expected_type",
      "required_imports": ["pytest"],
      "criterion": "parametrize-cluster",
      "evidence": "all three call parse_instrument(symbol) and assert result.type == expected; same structure, different inputs"
    }
  ],
  "unanalyzable": [
    { "file": "tests/conftest.py", "reason": "fixture-only file; no test functions" }
  ]
}
```

`simplification-plan.json` is the Phase B artifact. Note: the `consolidated_body` field contains concrete parametrized code, not a sketch.

The top-level `schema_version` is `2`.

Every `review_candidates` entry has the base fields `{ file, test_name, criterion, evidence }`. Some criteria add optional fields:

| Field | Type | Criteria that set it |
|---|---|---|
| `call_s` | number, seconds | coverage-subset, cost |
| `time_saved_s` | number, seconds | coverage-subset, cost |
| `note` | string | pinning |
| `seed` | integer | order-dependent, flaky |
| `failing_ids` | array of test ids | order-dependent, flaky |

A test that meets several criteria gets one entry per criterion, not one merged entry.

`reference/python/select_candidates.py` builds the coverage-subset and cost entries from `test-evidence.json`; `time_saved_s` equals the test's own `call_s` (serial time, not wall time). `test_name` in these entries is the id remainder after the file path (`Class::test[param]` for methods and parametrized ids), not a bare function name. `reference/python/calltime_delta.py` builds ledger `simplification.call_time`: total `call_s` before (evidence pass) and after (simplify validation run), `delta_s = after_s - before_s`, and `call_s` per removed test id (`null` when the id has no evidence entry; ids are node ids, and a bare `<file>::<test>` also matches the `<file>::<Class>::<test>` method and its parametrized ids). A missing validation-run calltime file also gives null figures and a warning. With evidence status other than `ok`, every figure is `null` and `warning` names the reason.

`evidence.<lang>.status` is `ok`, `skipped`, or `failed`; `reason` is a one-line string when not `ok`; `tests` is the number of entries written. Resume reuses a recorded status rather than re-running. The top-level `evidence` object in `simplification-plan.json` is `{ "file": ".scratch/refactor-tests/test-evidence.json", "status": "ok|skipped|failed" }`: `ok` when any language is `ok`, else `failed` when any is `failed`, else `skipped`.

## Seam classification (Python)

Step 7b of `SKILL.md`. Helper: `reference/python/classify_seams.py` (`propose`, `classify`). The seam definition quoted in `SKILL.md` comes from `skills/engineering/tdd/SKILL.md:20`; module, interface, seam, adapter come from `codebase-design`.

**Seam signals**, per source module, strongest first. A name takes the first signal that proposes it, and the proposal records that signal.

| Signal | Value | Proposes |
|---|---|---|
| (a) `__all__` | `__all__` | each public name listed in the module's `__all__` |
| (b) cross-package import | `cross-package-import` | a public function or class that a source file in another package of the project imports from this module (`from <module> import <name>`, relative imports resolved) |
| (c) public surface | `public-api` | only when the module has no `__all__`: public top-level functions and classes, and the public methods of those classes as `Class.method` |

Names with a leading underscore are never proposed. Test files and `conftest.py` are not source modules.

**Static classification**, per test and per source module, from the test's AST only. The test's references to that module are the names it imports and uses, attribute access on imported modules and classes, and `patch("pkg.mod.name")` (as a call or as a decorator on the test or its class), `patch.object(mod, "name")`, `monkeypatch.setattr("pkg.mod.name", ...)` targets. A reference is a seam when its name is a confirmed seam, or its first segment is a seam class and the remaining segments are public. A method call on an instance is not resolved.

- **Interface test**: at least one reference, and every reference is a seam.
- **Pinning candidate**: at least one reference is not a seam (`internals` lists them, e.g. `_tokenize`, or a mock patched at an internal path).
- One test can be an interface test for one module and a pinning candidate for another.

**Coverage against the interface** (needs evidence status `ok`). A seam's body lines are the lines of its body statements (decorators and the `def`/`class` header excluded: the header runs at import, outside any `|run` context). A seam is **reached** when an interface test's `covered` lines for the module intersect its body lines; parametrized ids merge by their base id. A confirmed seam no interface test reaches is an **add candidate**; pinning tests never count. A seam whose name has no function or class body in its module (a re-export or a constant in `__all__`) is never an add candidate; the report warns. A pinning candidate has `covered_through_interface: true` when some interface test of the same module covers a superset of its lines in that module (a pinning test with no coverage in the evidence gets `false`, with a warning); the note is then "covered through the interface", otherwise "move the assertion to the interface". With evidence status other than `ok`, `add_candidates` and `covered_through_interface` are omitted (keys absent) and the note is "move the assertion to the interface".

**`seams` object** in `simplification-plan.json` (only confirmed seams are listed; under `--dry-run` or unattended runs seams stay `proposed` in the ledger and the plan carries no `pinning_candidates`):

```json
"seams": {
  "modules": {
    "src/protrading/adapters/instruments.py": {
      "seams": [ { "name": "parse_instrument", "signal": "__all__", "status": "confirmed" } ]
    }
  },
  "add_candidates": [ { "module": "src/protrading/adapters/instruments.py", "seam": "parse_instrument" } ],
  "pinning_candidates": [
    {
      "file": "tests/protrading/adapters/test_instruments.py",
      "test_name": "test_tokenize_directly",
      "module": "src/protrading/adapters/instruments.py",
      "internals": ["_tokenize"],
      "covered_through_interface": true,
      "note": "covered through the interface"
    }
  ]
}
```

Each pinning candidate also goes to `review_candidates` as `{ file, test_name, criterion: "pinning", evidence, note }`.

## Test evidence schema (`.scratch/refactor-tests/test-evidence.json`)

Written by the evidence pass (Phase B, first step) on post-layout test ids. Schema version 1. Python helpers: `reference/python/calltime.py` (timing hook), `extract_arcs.py` (per-test lines and arcs), `assemble_evidence.py` (this file).

```json
{
  "schema_version": 1,
  "id_basis": "post-layout",
  "languages": {
    "python": {
      "status": "ok",
      "tools": { "coverage": "7.16.2", "pytest-cov": "7.1.0", "pytest": "9.1.1" },
      "commands": {
        "coverage": "COVERAGE_CORE=ctrace ... pytest -p no:randomly --cov=src --cov-branch --cov-context=test",
        "timing": "... pytest -p no:randomly -p calltime"
      },
      "tests": {
        "tests/protrading/adapters/test_instruments.py::test_parse[AAPL]": {
          "outcome": "passed",
          "call_s": 0.000089,
          "covered": {
            "src/protrading/adapters/instruments.py": {
              "lines": [9, 11],
              "arcs": [[-8, 9], [9, 11], [11, -8]]
            }
          }
        }
      },
      "excluded": [ { "id": "tests/protrading/test_flaky.py::test_x", "outcome": "failed" } ]
    }
  }
}
```

- `tests` is keyed by test id (node id). Only tests whose call-phase `outcome` is `passed` get an entry; every other test is listed under `excluded` with its outcome: `failed`, `skipped`, `no-coverage` (a passed test with no `|run` context in the coverage data), or `no-timing` (a covered id with no row from the timing run).
- `call_s` is the call-phase duration in seconds from the serial, untraced timing run. `covered` comes from the traced run, `|run` contexts only. Negative arc endpoints are function entry and exit.
- A language block with `status` `skipped` or `failed` carries a `reason` and empty `tests`.
- `kill_set` is a reserved top-level key for a later mutation-based check. v1 does not write it.

## AST editor guidance (per language)

| Language | Remove test function | Add parametrize decorator | Notes |
|----------|---------------------|--------------------------|-------|
| Python | stdlib `ast` — locate `FunctionDef` by name, remove node, unparse with `ast.unparse` | Insert `@pytest.mark.parametrize(argnames, argvalues)` decorator node before function; add `import pytest` if absent | Use `libcst` when round-trip formatting fidelity is required |
| TS/JS | `@babel/parser` + `@babel/traverse` — locate `describe`/`it`/`test` call by name, remove subtree | Replace with `test.each([...])(...)` or `it.each([...])(...)`; preserve surrounding `describe` block if siblings remain | Reprint with `@babel/generator`; run `prettier` on result if project uses it |
| Go | `go/ast` + `go/printer` — locate `func Test<Name>(t *testing.T)` by name, remove declaration | Replace N funcs with one table-driven func using a `tests := []struct{...}` slice and `t.Run(tc.name, func(t *testing.T){...})` subtests per entry; `gofmt` after edit | Subtests are mandatory: they preserve per-case test ids and `t.Fatal` isolation |
| Java | `JavaParser` (com.github.javaparser) — parse compilation unit, locate `@Test` method by name, remove node, pretty-print | Replace with `@ParameterizedTest` + `@MethodSource` (complex args) or `@CsvSource` (primitives/strings); add required imports | JavaParser supports full round-trip source rewriting |
| Kotlin | Kotlin compiler PSI via `kotlin-compiler-embeddable` — locate `@Test` function by name, remove PSI element | Replace with `@ParameterizedTest` + `@MethodSource`; `ktlint --format` for cleanup | Emit with PSI printer |

**Fallback for removal** (when AST edit would corrupt formatting): fall back to line-range splicing — record line range in ledger, splice lines, warn in final report.

**Fallback for parametrization** (when composite AST edit fails at edit time, not at parse time): skip the entry entirely, record as `skipped` in the ledger, leave the file unchanged, surface in final report as a warning. Do not attempt partial edits (no partial deletions without the consolidated insert).

---

## Log assertion (Kotlin / Log4j2)

Prefer a real in-memory appender to `mockkStatic(LoggerFactory)`:

1. Implement `BeforeEachCallback`/`AfterEachCallback`. In `beforeEach`: attach an `AbstractAppender` to the named logger via `LoggerContext.getContext(false)` and `Configurator.setLevel`. In `afterEach`: stop the appender and call `Configurator.reconfigure()` to restore the original configuration.
2. Store captured events in a `CopyOnWriteArrayList<LogEvent>` for thread safety.
3. Expose `count(level: Level)` and `assertCount(expected, level)` helpers.
4. Name the appender with a unique suffix (e.g., `System.nanoTime()`) to avoid collisions when multiple extension instances are active in the same JVM.
5. Register via `@RegisterExtension val logs = Log4j2ListAppenderExtension.of(MyService::class)`.

This approach works with async loggers, does not require power-mock classloader tricks, and does not leak between tests because `Configurator.reconfigure()` fully restores the Log4j2 state.
