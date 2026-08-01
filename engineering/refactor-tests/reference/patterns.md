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

## Test-file naming

| Language | Test file name for source `<name>` |
|---|---|
| Python | `test_<name>.py` |
| TS/JS | `<name>.test.ts` / `<name>.spec.ts` (match existing) |
| Go | `<name>_test.go` |
| Java/Kotlin | `<Name>Test.java` / `<Name>Test.kt` |

## Runner detection (convention markers)

| Language | Marker files (any) | Command |
|---|---|---|
| Python | `pytest.ini`, `pyproject.toml`, `setup.cfg`, `tox.ini` | `pytest` |
| TS/JS | `package.json` (has a `test` script) | `npm test` (or `yarn test` if `yarn.lock` exists, `pnpm test` if `pnpm-lock.yaml`) |
| Go | `go.mod` | `go test ./...` |
| Java | `pom.xml` | `mvn test` |
| Java/Kotlin | `build.gradle`, `build.gradle.kts` | `gradle test` |

If markers are ambiguous for a present language, try the candidate commands in table order and use the first that runs. Record the resolved command in the ledger so validation reuses the exact baseline command.

## Import rewriting (AST-based, per language)

Moving a test file can invalidate **relative** imports (their depth to the source changes); **absolute/package** imports usually survive. Rewrite with the language's parser, never blind regex.

| Language | Parser | What to rewrite |
|---|---|---|
| Python | `libcst` (comment/format-preserving); fall back to stdlib `ast` splice when libcst is unavailable | relative `from ..x import y` whose depth changed; convert to absolute `from <pkg>.x import y` where the package path is known |
| TS/JS | TypeScript compiler API or Babel (`@babel/parser` + `@babel/traverse`) | relative `import ... from './x'` / `require('./x')` specifiers; recompute the `./`-relative path from the new location; leave path-alias and package imports untouched |
| Go | `go/parser` + `go/printer` (or `goimports`) | rarely needed — Go imports are module-absolute; run `goimports` on moved files to fix ordering |
| Java | `JavaParser` (com.github.javaparser) — parse compilation unit, update `PackageDeclaration` node, pretty-print | `package` declaration to match the new directory |
| Kotlin | Kotlin compiler PSI via `kotlin-compiler-embeddable` — update `KtPackageDirective` node, emit with PSI printer, `ktlint --format` for cleanup | `package` declaration to match the new directory |

Any file the parser cannot process is a **warning** (not a silent skip): record it in the report and leave its imports unchanged for manual follow-up.

## Ledger schema (`.scratch/refactor-tests/ledger.json`)

```json
{
  "phase": "discovery|planning|baseline|moving|rewriting|validating|pruning|prune-validating|done",
  "project_path": "/abs/path",
  "languages": ["python"],
  "source_roots": ["src"],
  "runners": { "python": "pytest" },
  "baseline": { "python": { "passed": 412, "failed": ["tests/test_x.py::test_a"] } },
  "id_map": { "tests/test_instruments.py::test_parse": "tests/protrading/adapters/test_instruments.py::test_parse" },
  "moves": [
    { "from": "tests/test_instruments.py", "to": "tests/protrading/adapters/test_instruments.py", "language": "python", "source_file": "src/protrading/adapters/instruments.py", "cross_cutting": false },
    { "from": "tests/test_end_to_end.py", "to": "tests/integration/test_end_to_end.py", "language": "python", "source_file": null, "cross_cutting": true }
  ],
  "rewrites": [ { "file": "tests/protrading/adapters/test_instruments.py", "count": 2 } ],
  "pruning": {
    "post_layout_baseline": { "python": { "passed": 412, "failed": [] } },
    "removals": [ { "file": "tests/protrading/adapters/test_instruments.py", "test_name": "test_parse_duplicate", "criterion": "exact-duplicate" } ],
    "parametrizations": [ { "file": "tests/protrading/adapters/test_instruments.py", "replaced": ["test_parse_1", "test_parse_2", "test_parse_3"], "consolidated_name": "test_parse_parametrized" } ]
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

`plan.json` is the Phase A artifact the repeat loop refines; `ledger.json` is the durable execution record written during FINALIZE_STEP.

## Pruning plan schema (`.scratch/refactor-tests/pruning-plan.json`)

```json
{
  "removals": [
    {
      "file": "tests/protrading/adapters/test_instruments.py",
      "test_name": "test_parse_instrument_copy",
      "criterion": "exact-duplicate",
      "evidence": "body identical to test_parse_instrument (lines 42-51 vs 55-64)"
    },
    {
      "file": "tests/protrading/adapters/test_instruments.py",
      "test_name": "test_always_passes",
      "criterion": "dead-test",
      "evidence": "no assert/expect statement in body"
    }
  ],
  "parametrizations": [
    {
      "file": "tests/protrading/adapters/test_instruments.py",
      "tests": ["test_parse_equity", "test_parse_future", "test_parse_option"],
      "consolidated_name": "test_parse_instrument_by_type",
      "consolidated_body_sketch": "@pytest.mark.parametrize('symbol,expected_type', [('AAPL', 'equity'), ('ESZ4', 'future'), ('AAPL241220C200', 'option')])\ndef test_parse_instrument_by_type(symbol, expected_type): ...",
      "criterion": "parametrize-cluster",
      "evidence": "all three call parse_instrument(symbol) and assert result.type == expected; same structure, different inputs"
    }
  ],
  "unanalyzable": [
    { "file": "tests/conftest.py", "reason": "fixture-only file; no test functions" }
  ]
}
```

`pruning-plan.json` is the Phase B artifact the repeat loop refines.

## AST editor guidance (per language)

Test editing must use the same AST-based approach as import rewriting — never blind text deletion.

| Language | Remove test function | Add parametrize decorator | Notes |
|----------|---------------------|--------------------------|-------|
| Python | stdlib `ast` — locate `FunctionDef` by name, remove node, unparse with `ast.unparse` | Insert `@pytest.mark.parametrize(argnames, argvalues)` decorator node before function; add `import pytest` if absent | Use `libcst` when round-trip formatting fidelity is required |
| TS/JS | `@babel/parser` + `@babel/traverse` — locate `describe`/`it`/`test` call by name, remove subtree | Replace with `test.each([...])(...)` or `it.each([...])(...)`; preserve surrounding `describe` block if siblings remain | Reprint with `@babel/generator`; run `prettier` on result if project uses it |
| Go | `go/ast` + `go/printer` — locate `func Test<Name>(t *testing.T)` by name, remove declaration | Replace N funcs with one table-driven func using a `tests := []struct{...}` slice and `t.Run(tc.name, func(t *testing.T){...})` subtests per entry; `gofmt` after edit | Subtests are mandatory: they preserve per-case test ids and `t.Fatal` isolation |
| Java | `JavaParser` (com.github.javaparser) — parse compilation unit, locate `@Test` method by name, remove node, pretty-print | Replace with `@ParameterizedTest` + `@MethodSource` (complex args) or `@CsvSource` (primitives/strings); add required imports | JavaParser supports full round-trip source rewriting |
| Kotlin | Kotlin compiler PSI via `kotlin-compiler-embeddable` — locate `@Test` function by name, remove PSI element | Replace with `@ParameterizedTest` + `@MethodSource`; `ktlint --format` for cleanup | Emit with PSI printer |

**Fallback for removal** (when AST edit would corrupt formatting): fall back to line-range splicing — record line range in ledger, splice lines, warn in final report.

**Fallback for parametrization** (when composite AST edit fails at edit time, not at parse time): skip the entry entirely, record as `skipped` in the ledger, leave the file unchanged, surface in final report as a warning. Do not attempt partial edits (no partial deletions without the consolidated insert).
