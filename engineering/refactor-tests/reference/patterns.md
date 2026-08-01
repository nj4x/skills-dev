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
| Python | stdlib `ast` (parse, locate `Import`/`ImportFrom`, recompute `level` and module for relative imports, unparse or splice) | relative `from ..x import y` whose depth changed; convert to absolute `from <pkg>.x import y` where the package path is known |
| TS/JS | TypeScript compiler API or Babel (`@babel/parser` + `@babel/traverse`) | relative `import ... from './x'` / `require('./x')` specifiers; recompute the `./`-relative path from the new location; leave path-alias and package imports untouched |
| Go | `go/parser` + `go/printer` (or `goimports`) | rarely needed — Go imports are module-absolute; run `goimports` on moved files to fix ordering |
| Java/Kotlin | `javalang` (Python) or a Kotlin/Java parser | `package` declaration to match the new directory, and any relative-resource references |

Any file the parser cannot process is a **warning** (not a silent skip): record it in the report and leave its imports unchanged for manual follow-up.

## Ledger schema (`.scratch/refactor-tests/ledger.json`)

```json
{
  "phase": "discovery|planning|baseline|moving|rewriting|validating|done",
  "project_path": "/abs/path",
  "languages": ["python"],
  "source_roots": ["src"],
  "runners": { "python": "pytest" },
  "baseline": { "python": { "passed": 412, "failed": ["tests/test_x.py::test_a"] } },
  "moves": [ { "from": "tests/test_instruments.py", "to": "tests/protrading/adapters/test_instruments.py", "language": "python", "source_file": "src/protrading/adapters/instruments.py" } ],
  "rewrites": [ { "file": "tests/protrading/adapters/test_instruments.py", "count": 2 } ]
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
  "unmapped": [
    { "file": "tests/test_end_to_end.py", "reason": "exercises adapters + audit + persistence; cross-cutting" }
  ]
}
```

`plan.json` is the artifact the repeat loop refines; `ledger.json` is the durable execution record written during FINALIZE_STEP.
