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

**Primary test language:** the present language with the most test files; a tie goes to the language listed first in the table. A bare `Integration directory:` value in `docs/agents/testing.md` belongs to it.

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

**Directory guard check.** Before moving any file into the integration target, check whether that directory is constrained by a project-specific guard — a meta-test or CI check that restricts what may live there (e.g. a frozen baseline file, a marker/fixture requirement enforced by AST). Read `docs/agents/testing.md` → Test layout first. When its `Integration directory:` line sets a directory for a language (a bare value belongs to the primary test language, defined under Language detection; `<language>: <dir>` values name theirs), that directory replaces that language's table default as the move target, and the membership rule written beside it applies; other languages keep the table default. When its `Guard:` line names a check, that check is the guard. When the file, the `Integration directory:` line or the `Guard:` line is absent or reads `not set` (rule: `setup-skills/testing.md`), the table default stands for a missing directory line, and a missing guard line sends you to look for the guard the way you'd look for the runner: a project doc (`AGENTS.md`/`CLAUDE.md`-pointed testing guide) describing the directory's membership rule, or a test file named after the constraint. If such a guard exists and the candidate file would violate it (e.g. it doesn't carry the required marker/fixture and the baseline may not grow), do not move it — leave it in place and record it as pinned (same treatment as the Go build-tag exception below), with the guard's name as the reason.

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
| Python | `assert`, `raise`, `pytest.raises`, `pytest.warns`, `pytest.fail`, `pytest.deprecated_call`; a call to any function whose name starts with `assert`, `_assert`, `check`, `_check`, `expect`, `_expect`, `verify`, or `_verify`; a fixture the test requests, or a helper it calls, that is defined in the test file or `conftest.py` and whose body asserts |
| TypeScript/JavaScript | `expect`, `assert` (chai), `should` (should.js), `.to.throw` (chai), `.toThrow` (jest) |
| Go | `t.Error`, `t.Errorf`, `t.Fatal`, `t.Fatalf`, `require.*`, `assert.*` (testify) |
| Java | `assertThat`, `assertTrue`, `assertEquals`, `fail` (JUnit/AssertJ) |
| Kotlin | `assertThat`, `assertTrue`, `assertEquals`, `fail` (same as Java) |

**Dead-test kinds.** Each dead-test entry carries `kind`, from this ordered list. The order is the precedence: when several kinds match, the first one wins.

| Order | `kind` | Matches | Disposition |
|---|---|---|---|
| 1 | `no-raise-contract` | The last statement calls a documented raiser (bare `validate(` or `*.validate(` on any receiver, or a name the project lists with `--raiser`: a bare call matches any raiser with that last name, a dotted call matches only when one dotted name ends with the other, so `config.load(` matches `pkg.config.load`, never `other.load`), or the test name or docstring says "does not raise" or "must not raise". | Keep. It is the only guard against an over-strict validator. Counted in the Final report, never ticketed. |
| 2 | `fail-soft` | The body sets up an error (`side_effect=…Error`) and calls the code under test. | Add an assertion on the log or the return value. Check it by hand-mutating the function to a silent no-op: the test must fail. |
| 3 | `never-fails` | The only outcome other than a pass is `pytest.skip` (or `pytest.importorskip`). | Replace the skip with an assertion, or remove the test. |
| 4 | `no-assertion` | Everything else. | Add an assertion, or remove the test. |

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
  "phase": "discovery|baseline|moving|rewriting|validating|evidence|seams|simplifying|order-gate|executing|simplify-validating|context-measuring|context-consolidating|context-switching|context-validating|publishing|done|failed-layout|failed-simplify|failed-context",
  "started_at": "2026-10-16T19-26-00",
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
    "confirmed_file": "ok",
    "confirm_path": "per-module",
    "modules": { "src/protrading/adapters/instruments.py": { "seams": [ { "name": "parse_instrument", "signal": "__all__", "status": "confirmed" } ] } },
    "propose_warnings": [ "src/protrading/adapters/__init__.py: __all__ is computed or mutated, not a literal list; only its literal names are proposed under __all__ and public-api is not used" ],
    "warnings": [ "src/protrading/adapters/__init__.py: __all__ is computed or mutated, not a literal list; only its literal names are proposed under __all__ and public-api is not used" ]
  },
  "order_gate": {
    "status": "ok",
    "reason": null,
    "plugin": "pytest-randomly",
    "seed": 1234567,
    "order_dependent": ["tests.protrading.adapters.test_instruments::test_parse_cached"],
    "flaky": []
  },
  "simplification": {
    "post_layout_baseline": { "python": { "passed": 412, "failed": [] } },
    "removals": [ { "file": "tests/protrading/adapters/test_instruments.py", "test_name": "test_parse_duplicate", "criterion": "exact-duplicate" } ],
    "review_candidates": [ { "file": "tests/protrading/adapters/test_instruments.py", "test_name": "test_always_passes", "criterion": "dead-test" } ],
    "parametrizations": [
      { "file": "tests/protrading/adapters/test_instruments.py", "replaced": ["test_parse_1", "test_parse_2", "test_parse_3"], "consolidated_name": "test_parse_parametrized" },
      { "file": "tests/protrading/adapters/test_instruments.py", "tests": ["test_fmt_a", "test_fmt_b", "test_fmt_c"], "consolidated_name": "test_fmt_parametrized", "skipped": "composite edit failed: decorator order differs" }
    ],
    "hotspot_probe": { "status": "ok", "reason": null, "n": 2, "profiled": ["tests/protrading/db/test_store.py::test_roundtrip", "tests/protrading/db/test_store.py::test_query"], "failed": [ { "id": "tests/protrading/db/test_store.py::test_bulk", "reason": "pytest exit 1" } ], "hotspots": 1, "warnings": ["profile of tests/protrading/db/test_store.py::test_bulk failed (pytest exit 1); left out of n"] },
    "call_time": { "label": "serial call time, not wall time", "before_s": 41.2, "after_s": 37.9, "delta_s": -3.3, "attributable_s": 0.012, "removed": [ { "id": "tests/protrading/adapters/test_instruments.py::test_parse_duplicate", "call_s": 0.012 } ], "warning": null }
  },
  "spring": {
    "baseline": { "context_count": 5, "wall_time_seconds": 42.5 },
    "consolidations": [
      { "file": "src/test/kotlin/com/org/support/AbstractApiDocumentationTest.kt", "base_class": "AbstractApiDocumentationTest", "annotations_removed": ["@SpringBootTest", "@AutoConfigureWebTestClient", "@AutoConfigureRestDocs"], "mocks_removed": 11 }
    ],
    "skipped_clusters": [
      { "cluster": "MockBean(PaymentClient)+WebMvcTest", "classes": ["PaymentApiTest", "RefundApiTest", "PayoutApiTest"], "reason": "differing types under field name client: PaymentClient vs PaymentClientV2" }
    ],
    "post_context_cost": { "context_count": 1, "wall_time_seconds": 28.3 }
  },
  "publish": {
    "status": "published",
    "slug": "refactor-tests-review-2026-10-16t19-26-00",
    "parent": "#140",
    "tickets": [ { "ref": "#141", "keys": ["review|dead-test|tests/protrading/adapters/test_instruments.py::test_always_passes"] } ],
    "already_tracked": [ { "key": "review|pinning|tests/protrading/adapters/test_instruments.py::test_cache_internals", "ref": "#97" } ]
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
      "evidence": "body identical to test_parse_instrument (lines 42-51 vs 55-64)",
      "duplicate_of": "test_parse_instrument"
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

`simplification-plan.json` is the Phase B artifact. Note: the `consolidated_body` field contains concrete parametrized code, not a sketch. Every parametrization carries `class` (the test class; `null` for top-level tests), and its `tests` and `consolidated_name` take the `Class::test` form. An `unanalyzable` entry holds `{ file, reason }`; one for a cluster the helper skipped also carries that cluster's `tests`. `reference/python/scan_static.py` builds the `removals`, the dead-test `review_candidates`, and the `parametrizations` for Python; `reference/python/apply_param.py` applies the parametrizations (SKILL.md Step 9).

The top-level `schema_version` is `2`.

Every `review_candidates` entry except `hotspot` (below) has the base fields `{ file, test_name, criterion, evidence }`. Some criteria add optional fields:

| Field | Type | Criteria that set it |
|---|---|---|
| `call_s` | number, seconds | coverage-subset, cost |
| `time_saved_s` | number, seconds | coverage-subset, cost |
| `note` | string | pinning |
| `kind` | string | dead-test (see Assertion vocabulary → Dead-test kinds), pinning (see Seam classification → Pinning kinds) |
| `seed` | integer | order-dependent, flaky |
| `failing_ids` | array of test ids | order-dependent, flaky |

A test that meets several criteria gets one entry per criterion, not one merged entry.

A `hotspot` entry has no `file` or `test_name`: it names a function, not a test. `reference/python/hotspot_probe.py analyze` builds it from the Step 8 profiles (SKILL.md Step 8 → Hotspot probe):

```json
{
  "criterion": "hotspot",
  "function": "src/protrading/db/connection.py:connect",
  "share": 0.84,
  "tests": ["tests/protrading/db/test_store.py::test_roundtrip", "tests/protrading/db/test_store.py::test_query"],
  "subprocess_spawns": { "tests/protrading/db/test_store.py::test_query": 12, "tests/protrading/db/test_store.py::test_roundtrip": 12 },
  "via": ["keyring/core.py:get_password", "subprocess.py:run"]
}
```

`function` is `<path>:<name>`, the path relative to `site-packages`, the standard library, or the project root; a built-in reads as its pstats name, except `builtins` dispatchers such as `next`, which never count. The probe tells functions apart by path, line and name: when two functions print the same `<path>:<name>` (two `__init__` methods in one file), each prints as `<path>:<name>:<line>`, and their hits are never added together. `share` is the mean, over the profiles where the function itself holds at least 0.5, of its cumulative time divided by the test's profiled time (setup, call, teardown; a session-scoped fixture set up by the profiled test counts, so read a hotspot that sits in fixture setup with that in mind). `tests` are the tests where it or a `via` function holds at least 0.5. `subprocess_spawns` maps every usable profiled test id to the processes it started (`_posixsubprocess.fork_exec`, `posix_spawn`, `system`, `_winapi.CreateProcess` calls). `via` lists the other hotspots this one reaches through calls: a hotspot that another hotspot calls is folded into the hotspot at the top of that call chain, so one shared cause makes one entry.

**Hotspot rule.** With n usable profiles, a function is a hotspot when its share is at least 0.5 in at least max(2, ceil(n / 2)) of them: n=2 needs 2 hits, n=3 needs 2, n=4 needs 2, n=5 needs 3. One hit is never a hotspot. pytest and pluggy frames, the test function, and every caller of the test function (a decorator, an async runner) are wrappers and never count. A profile that is missing, unreadable, or empty, or a test whose profile run exited non-zero, is excluded from n and is listed under `failed`. With fewer than 2 usable profiles no hotspot is emitted and `warnings` says so.

`test_name` is the test id after the file path. Its form follows what the criterion judges. Coverage-subset and cost judge evidence ids, so their `test_name` keeps the parameter suffix (`Class::test[param]`): each parametrized id is its own candidate, with its own `call_s`. Dead-test and pinning judge test functions in the source, so their `test_name` has no suffix (`Class::test`). Order-dependent and flaky take `test_name` from each test a demoted change involves: the removal's own `test_name`, a kept duplicate's `duplicate_of`, or each name in a parametrization's `tests`. Stripping the suffix from coverage-subset entries would merge distinct candidates into duplicate names, so the two forms stay.

`reference/python/select_candidates.py` builds the coverage-subset and cost entries from `test-evidence.json`; `time_saved_s` equals the test's own `call_s` (serial time, not wall time). `reference/python/calltime_delta.py` builds ledger `simplification.call_time`: total `call_s` before (evidence pass) and after (simplify validation run), `delta_s = after_s - before_s`, `attributable_s` (the sum of `call_s` of the removed and replaced tests), and `call_s` per removed test id (ids are node ids; an id matches its evidence entry exactly or through its parametrized ids `<id>[...]`). A bare `<file>::<test>` names a top-level test only. With no exact match it gets `call_s: null` and is never charged a class method's `call_s`, even when only one `<file>::<Class>::<test>` has that name; when same-name class methods exist, `warning` names them so the caller can pass the full node id. A missing validation-run calltime file also gives null figures and a warning. With evidence status other than `ok`, every figure is `null` and `warning` names the reason. When |`delta_s`| > 2 × `attributable_s` + 2% of `before_s`, `warning` is "delta exceeds what the changes can explain; treat it as run-to-run variance". When `before_s` is zero the check is not computed and `warning` says so.

An `exact-duplicate` removal also carries `duplicate_of`: the name of the test that stays, and `duplicate_of_file` when that test is in another file (default: the removal's `file`). Step 8b reads both to treat that kept test as involved in the change.

`evidence.<lang>.status` is `ok`, `skipped`, or `failed`; `reason` is a one-line string when not `ok`; `tests` is the number of entries written. Resume reuses a recorded status rather than re-running. The top-level `evidence` object in `simplification-plan.json` is `{ "file": ".scratch/refactor-tests/test-evidence.json", "status": "ok|skipped|failed" }`: `ok` when any language is `ok`, else `failed` when any is `failed`, else `skipped`.

## What each criterion proves

Each evidence-based criterion shows less than its name suggests. A review ticket is a prompt to look, never a deletion order.

| Criterion | Proves | Does not prove |
|---|---|---|
| dead-test | No assertion statement in the body. | That no exception path asserts. See [Schema-migration tests](#schema-migration-tests-hint) for a kind that often looks dead. |
| coverage-subset | The test's lines and arcs are covered by other passing tests. | Anything about assertions. The result is one greedy set cover. See [Schema-migration tests](#schema-migration-tests-hint). |
| cost | Slow and coverage-subset. | Why it is slow. Its `time_saved_s` is an upper bound if the test is deleted; a hotspot fix often saves the time with no test deleted. |
| hotspot | One function holds at least half the profiled time of at least half the profiled cost candidates. | That it is the only cause, or that tests outside the profiled ones share it. |
| pinning, `covered_through_interface` | Lines are a subset of one interface test's lines. | Arcs, assertions, or the same behaviour. |

- **Greedy single set cover.** The coverage-subset result comes from one greedy pass: it names tests whose coverage the rest of the suite holds, not the smallest or the only such set. Order decides which of two mutually covering tests is flagged: the slower one, since flagged tests leave the pool. Removing all flagged tests keeps line and arc coverage, but says nothing about assertions.
- **Parametrized cases.** One case of a table-driven test is almost always wrong to flag alone: the cases share one body and differ by input. Judge the whole test, not the case.
- **Several modules.** A test with entries for several modules is removable only when every entry allows it.
- **Removal gate.** Remove a test on this evidence only when a mutation check of its module shows no lost kill. See `SKILL.md` → Follow-up: mutation deletion gate (optional).

### Schema-migration tests (hint)

Schema-migration tests (Alembic, Flyway, Liquibase, Django) mix four kinds:

- static revision or source checks: deletable;
- head-schema invariants: move to a schema test;
- data movement on legacy rows: deletable only once every persistent database is past that revision (an operator fact);
- misfiled repo or model tests: move.

Never apply a "delete non-head migration tests" rule as a whole. The classification needs project knowledge, so treat this as a hint for the reviewer, not a step of the run.

## Review queue (Step 11)

`reference/python/render_review_queue.py` turns the run's human-action items into `.scratch/refactor-tests/review-queue.md` and, with `--stage`, into `to-tickets` drafts. Decisions: ADR-0079, amended by ADR-0080.

**Items and keys.** Each item belongs to one category and has the key `<category>|<criterion>|<id>`:

| Category | Source | Criterion | Id | Label |
|---|---|---|---|---|
| review | plan `review_candidates` | `dead-test`, `coverage-subset`, `cost`, `pinning` | `<file>::<test_name>` | `ready-for-human` |
| fix | plan `review_candidates` | `order-dependent`, `flaky` | `<file>::<test_name>` | `ready-for-agent` |
| hotspot | plan `review_candidates` | `hotspot` | `<function>` | `ready-for-agent` |
| add | plan `seams.add_candidates` | `untested-seam` | `<module>::<seam>` | `ready-for-agent` |
| skipped | ledger `simplification.parametrizations` with `skipped` | `skipped-parametrization` | `<file>::<consolidated_name>` | `ready-for-human` |
| skipped | ledger `spring.skipped_clusters` | `skipped-spring-cluster` | `<cluster>` | `ready-for-human` |

**Grouping.** One ticket per category, criterion, and module. Dead-test and pinning items also split by `kind`: one ticket per criterion, kind, and module, with the kind in the title. A pinning `collaborator-double` ticket is labelled `ready-for-agent`; every other review ticket stays `ready-for-human`. Every pinning `boundary-double` item still becomes a `ready-for-human` ticket, although the double is allowed: the ticket carries the keep-the-double, do-not-delete text, so a reviewer who sees the flag knows no deletion is wanted. A dead-test `no-raise-contract` item is never ticketed: `render` leaves it out of the queue and counts it in its output under `report_only`. The helper accepts an item with any `kind` value, or none. Any string kind on a dead-test or pinning item splits the ticket, also one the helper has no text for. A kind on another criterion, or a non-string kind, shows in the item line and does not split the ticket. The module is the test file's directory, the source module for add candidates, the cluster for Spring clusters, and the function for a hotspot, so each hotspot gets its own ticket, titled `Fix cost hotspot <function> in the test tier`. A group over 25 ids splits into tickets titled `(part i of n)`. Tickets are numbered fix first, then hotspot, review, add, and skipped, so every hotspot ticket comes before every review ticket. Each ticket lists its ids with an evidence excerpt of at most two lines, plus `call_s` and `time_saved_s`, `note`, `failing_ids`, the skipped `tests`, or the Spring `classes` when the item has them; a hotspot item lists its `share`, profiled `tests`, `subprocess_spawns` per test, and `via`. Two blocking edges: a fix ticket blocks each review ticket that holds a test matching one of its ids (`order_gate.matches`); a hotspot ticket blocks each `cost` and `coverage-subset` ticket that holds a test in the directory of one of the hotspot's `tests`, because fixing the hotspot changes their `call_s` order (ADR-0080 Decision 2). A hotspot ticket's text (`WHAT["hotspot"]`) says: "Fix this in the test tier (a fixture or stub), never by deleting tests. Re-run the evidence pass after the fix, because `call_s` order changes." A review ticket's "What to build" text depends on its criterion (`WHAT["review"]`): coverage-subset, cost and pinning carry the mutation-gate caveat (see What each criterion proves). A known kind replaces that text (`review_what`; a pinning `boundary-double` ticket says to keep the double and not delete the test): a dead-test ticket states its kind's disposition (no kind reads as `no-assertion`), and a pinning `collaborator-double` ticket says "Re-point the stub (deps injection or a checked patch); do not delete." with no mutation-gate caveat. Other pinning kinds keep the pinning text. A fix ticket ends its text with a `Reproduce:` command built from the ledger `runners.python` command, the `order_gate.plugin` install, and the seed, for example `uv run --with pytest-randomly pytest -p randomly --randomly-seed=<seed> <file>`. Every ticket body, and `spec.md`, carries the line `git_sha: <sha>`, read from the evidence file's `git_sha`, so a later agent can tell whether the list is stale; it reads `git_sha: unknown` when there is no evidence file or its `git_sha` is `null`.

**Volume gate** (ADR-0080 Decision 3). `render` counts the tickets it would stage after dedupe, hotspot tickets included, before any triage, and prints `volume: { tickets, threshold: 50, over, action, choice, chosen_by }`. With `--tracker local|real`, `action` is `publish` (`tickets` at most 50), `ask` (interactive), `triage` (`--unattended` on the local tracker; `render` then stages option (b) itself and prints `triage: true`), or `drafted` (`--unattended` on a real tracker); without `--tracker` it is `null`. The gate's answer is recorded in `choice` and `chosen_by`:

| Gate | `action` | `choice` | `chosen_by` |
|---|---|---|---|
| 50 tickets or fewer, no answer | `publish` | `null` | `null` |
| interactive, not yet answered | `ask` | `null` | `null` |
| unattended, local tracker, no answer | `triage` | `b` | `unattended-default` |
| unattended, real tracker, no answer | `drafted` | `null` | `unattended-default` |
| any count, any attendance, `--choice a` | `publish` | `a` | `asked` |
| any count, any attendance, `--choice b` (or `--triage`) | `triage` | `b` | `asked` |
| any count, any attendance, `--choice c` | `declined` | `c` | `asked` |

An explicit answer wins over the gate's default, at 50 tickets or fewer and in an unattended run too, and the staging follows the recorded action: `triage` stages option (b), `publish` and `declined` stage every ticket (under `declined` Step 11 publishes none of them). Without `--choice`, `render` reuses the `choice` recorded in ledger `publish.volume` only when its `chosen_by` is `asked`, as if it were passed again, so a resumed run does not ask again and an unattended resume keeps the human answer. The recorded answer decides only the staging: Step 11 item 3 still records `publish.status: drafted` on an unattended real-tracker run, so `volume.action` may be `publish` or `triage` while `publish.status` is `drafted`. A recorded `unattended-default` is never reused: the gate is computed again, so an interactive resume still asks. `--triage` is an alias of `--choice b`; the two flags are mutually exclusive. Option (b) stages:

| Staged under (b) | Ticket |
|---|---|
| fix, hotspot, add | Unchanged, with their `key:` lines. |
| review (dead-test, coverage-subset, cost, pinning) | One triage ticket per review criterion with at least one review ticket, in the review tickets' place. |
| skipped (parametrization, Spring cluster) | Not staged; listed in `review-queue.md` only. |

A triage ticket is titled `Triage <n> <criterion> tests from the review queue` (`test` when `<n>` is 1), labelled `ready-for-human`, and numbered where the review tickets were (after hotspot, before add). Its body says to triage by module and hotspot before per-test review, links `.scratch/refactor-tests/review-queue.md` and `.scratch/refactor-tests/run-summary.json`, and lists its tests per module (`- <module>: <n> tests`), with no `key:` line; its `tickets.json` entry has `keys: []` and `criterion: <criterion>`. Its items stay out of the cross-run index and queue again next run (ADR-0080 Consequences). It takes the blocking edges of the review tickets it replaced: a fix ticket blocks it when it holds a matching test, and a hotspot ticket blocks the `cost` and `coverage-subset` triage tickets of its directories. A hotspot edge to a criterion with no triage ticket is dropped. `review-queue.md` lists every per-test ticket in either mode.

**Run summary** `.scratch/refactor-tests/run-summary.json`: every `render` call writes it, `--rekey-only` included, so every Step 11 path leaves one. It is small enough to commit.

```json
{
  "schema_version": 1,
  "started_at": "2026-10-16T19-26-00",
  "stopped_at": null,
  "git_sha": "3f2c9a1e0b7d4c6a8e5f1b2d3c4a5e6f7a8b9c0d",
  "dirty": false,
  "runner": { "python": "uv run pytest" },
  "seed": 1234567,
  "evidence_status": "ok",
  "counts": { "coverage-subset": 412, "cost": 41, "dead-test": 33, "pinning": 1813, "hotspot": 1 },
  "kinds": { "dead-test/no-raise-contract": 31, "dead-test/no-assertion": 2, "pinning/collaborator-double": 577 },
  "report_only": { "dead-test/no-raise-contract": 31 },
  "excluded": { "failed": 2, "skipped": 14, "no-coverage": 1 },
  "evidence_tests": 3120,
  "shares": { "coverage-subset": 0.132, "cost": 0.0131, "dead-test": 0.0006, "pinning": 0.5811 },
  "warnings": ["pinning flags 58% of evidence tests: criterion is not discriminating on this suite; triage by module and hotspot before per-test review"],
  "concentration": {
    "by_candidates": [ { "module": "tests/protrading/db", "candidates": 640 } ],
    "by_call_s": [ { "module": "tests/protrading/db", "call_s": 812.4 } ]
  },
  "hotspots": [ { "criterion": "hotspot", "function": "src/protrading/db/connection.py:connect", "share": 0.84, "tests": ["…"], "subprocess_spawns": {}, "via": [] } ],
  "call_time": { "before_s": 861.7, "after_s": 858.2 },
  "volume": { "tickets": 765, "threshold": 50, "over": true, "action": "triage", "choice": "b", "chosen_by": "asked" },
  "notes": []
}
```

- `git_sha`, `dirty`: from the evidence file, the same source as the ticket bodies; `null` when there is no evidence file or it holds `null`. `runner` is ledger `runners`. `seed` is ledger `order_gate.seed`, `null` when the gate did not run. `stopped_at` is the `--stopped-at` value.
- `counts` per plan `review_candidates` criterion and `kinds` per `<criterion>/<kind>`, both counted before `no-raise-contract` items are dropped; `report_only` as in the `render` output. `null` with no plan.
- `excluded`: evidence `excluded` entries per outcome, all languages; `null` with no evidence file.
- `shares`: per review criterion, distinct flagged tests divided by `evidence_tests` (the entries of the `ok` language blocks). `warnings` holds one line per criterion whose share is above 0.5. Both need evidence `ok`: otherwise `shares` is `null` and `warnings` is empty. A dead-test `no-raise-contract` test is never ticketed, so it counts in no share and raises no warning; a criterion whose only candidates are report-only has no `shares` key.
- `concentration`: top 15 modules (test file directories) by review candidate count, and by the summed `call_s` of their review candidates, a test flagged both coverage-subset and cost counted once. Dead-test `no-raise-contract` candidates are left out, as in `shares`. `null` with no plan.
- `hotspots`: the plan's hotspot entries; `[]` when the probe found none or did not run.
- `call_time`: ledger `simplification.call_time` `before_s` and `after_s`; `null` when evidence is not `ok`.
- `volume`: the volume gate as `render` printed it, `choice` and `chosen_by` included (see Volume gate); `null` after `--rekey-only`. The last render wins, so after the user answers the gate the file holds the answer.
- `notes`: one line per field left `null` (or `[]`) and why: no evidence file, evidence not `ok` with each language's reason, no plan, no seed, no hotspot, no call-time totals.

**Staged files** under `.scratch/<slug>/`, where the slug is `refactor-tests-review-<started_at>` lowercased (the `to-tickets` slug rule applied to the title `refactor-tests review <started_at>`):
- `spec.md`: that title as H1, `Project: <name>`, item counts, already-tracked items, and a "Proposed tickets" table (NN, title, label, blocked by).
- `draft-issues/<NN>-<slug>.md`: the `to-tickets` spec-linked template with `label:` in its frontmatter and the same value under `## Status`.
- `manifest.md`: `artifact-type: tickets` frontmatter, then the draft paths in order.
- `tickets.json`: `{ slug, tickets: [ { nn, slug, keys } ] }`, which `record` reads. A triage ticket's entry is `{ nn, slug, keys: [], criterion }`; `record` builds the triage sentence it looks for from `criterion`, never from the slug. An entry with no `criterion` is credited by name only.

**Cross-run index** `.scratch/refactor-tests/review-index.json`: `{ schema_version: 1, entries: { <key>: { ref, slug } } }`. `render` maps each entry's id through the ledger's `id_map`, or, when `id_map` has no entry, through its `moves` (old file to new file), before comparing keys. `render` then writes the re-keyed entries back, except after a layout regression (`--stopped-at failed-layout`, whose moves the user may revert; Phase A moves stay in the tree after a later regression), so a test moved in this run still matches its entry when a later ledger no longer holds the move. `render --rekey-only` does only the re-key, for a run with `--no-publish-review`; it needs no `--plan`. If two entries re-key to the same key, the first is kept. Only `record` adds entries, and only for published tickets. A ticket counts as published when `--ref` names it, when a manifest line reads `<tracker-ID> <name>` (`<name>` is `<NN>-<slug>`, any number of digits, `.md` optional), or when `issues/<name>.md` exists. Its body is `issues/<name>.md` or `draft-issues/<name>.md`. Each ticket item line ends with `` key: `<key>` ``. An item is credited to the published ticket whose body holds its full key in backticks, so a ticket `to-tickets` renamed, merged, or split still counts. A triage ticket (option (b); its `tickets.json` entry has `keys: []` and its `criterion`) has no key to credit: it counts as published when a published name is its `<NN>-<slug>`, or when a published body holds the triage sentence of its entry's `criterion` (`stands for every <criterion> test it flagged`), and it adds no index entry. `record` prints `{ status, tickets, unpublished, unmatched }`: `status` is `published` (every key and every triage ticket credited), `drafted` (none), or `partial` (some; Step 11 maps it to the ledger status); `tickets` holds one `{ ref, keys }` per credited ref, a triage ticket's with `keys: []`; `unpublished` lists every key no published body names, then the `<NN>-<slug>` of every triage ticket not published; `unmatched` lists published names with no body file. An entry suppresses its item whatever the ticket's tracker state; delete the entry to re-ticket the item. `render` reports an earlier `refactor-tests-review-*` directory as superseded when it has `draft-issues/`, no `issues/`, no manifest line with a tracker id, and no index entry.

**Ledger `publish`**: `{ status, slug, parent, volume, tickets: [ { ref, keys } ], already_tracked: [ { key, ref } ] }`. `volume` is the last `render` output's `volume`; `render` reuses its `choice` on resume only when `chosen_by` is `asked`. `tickets` is `record`'s `tickets`: a published triage ticket appears as `{ ref, keys: [] }`, so the report still has one line per ticket, while `entries` in the cross-run index never hold it.

| `status` | Meaning | Final |
|---|---|---|
| `skipped` | `--no-publish-review` given. | yes |
| `queued` | Queue file written; publish not yet attempted. A resume reruns Step 11 from item 2. | no |
| `publishing` | `to-tickets` called; it may have published some or all tickets. A resume goes to `record` (item 6). | no |
| `local-only` | No `docs/agents/issue-tracker.md`, or a gate regressed. Queue file only. | yes |
| `empty` | Zero items after dedupe. No parent, no `to-tickets` call. | yes |
| `drafted` | Drafts staged, nothing published. | yes |
| `declined` | The user chose (c) at the volume gate: not to publish. Queue file and drafts kept; nothing published. A resume never retries it. | yes |
| `published` | `to-tickets` finished without a pass 1 or 2 failure. Pass-3 sub-issue fallbacks count as published. Items no published body names are reported as not ticketed and queue again next run. | yes |
| `failed` | `to-tickets` real-tracker pass 1 or 2, or a local-tracker promotion, stopped partway. | yes |

## Seam classification (Python)

Step 7b of `SKILL.md`. Helper: `reference/python/classify_seams.py` (`propose`, `reuse`, `classify`). The seam definition quoted in `SKILL.md` comes from `skills/engineering/tdd/SKILL.md` `## Seams — where tests go`; module, interface, seam, adapter come from `codebase-design`.

**Seam signals**, per source module, strongest first. A name takes the first signal that proposes it, and the proposal records that signal.

| Signal | Value | Proposes |
|---|---|---|
| (a) `__all__` | `__all__` | each public name listed in the module's `__all__` |
| (b) cross-package import | `cross-package-import` | a public function or class that a source file in another package of the project imports from this module (`from <module> import <name>`, relative imports resolved) |
| (c) public surface | `public-api` | only when the module has no `__all__`: public top-level functions and classes, and the public methods of those classes as `Class.method` |

Names with a leading underscore are never proposed. Test files and `conftest.py` are not source modules. `__all__` built from literal lists with `+`, `+=`, `.extend`, or `.append` is evaluated. A computed part (`[...] + other.__all__`) still means the module has an `__all__`: its literal names are proposed, signal (c) does not apply, and `propose` adds a `warnings` entry for the module. Any other change to `__all__` counts as computed the same way: `__all__.remove(...)`, `.insert(...)`, `.pop(...)` and the other list mutators, `del __all__[...]`, `__all__[:] = ...`, `-=`, and any assignment or mutation of `__all__` nested in a module-level `if`, `try`, `for`, `while`, or `with`. Only module scope is read: an `__all__` assigned or changed inside a function, lambda, or class body, and a value-less annotation `__all__: list[str]`, are ignored, so signal (c) still applies when the module has no other `__all__`. The ledger keeps these `propose` warnings in `seams.propose_warnings`. `seams.warnings` holds them followed by the `classify` warnings of the latest `classify` run: each run, a resume included, rebuilds it from `propose_warnings`, so `classify` warnings are never appended twice. The Final report lists `seams.warnings` whether or not a confirm round ran.

**Static classification**, per test and per source module, from the test's AST only. The test's references to that module are the names it imports and uses, attribute access on imported modules and classes, and `patch("pkg.mod.name")` (as a call or as a decorator on the test or its class), `patch.object(mod, "name")`, `monkeypatch.setattr("pkg.mod.name", ...)`, and `monkeypatch.setattr(mod, "name", ...)` targets. A reference is a seam when its name is a confirmed seam, or its first segment is a seam class and the remaining segments are public. A method call on an instance is not resolved.

- **Interface test**: at least one reference, and every reference is a seam.
- **Pinning candidate**: at least one reference is not a seam (`internals` lists them, e.g. `_tokenize`, or a mock patched at an internal path).
- One test can be an interface test for one module and a pinning candidate for another.

**Test doubles.** `classify` reads, per source module, which top-level names the module binds by an import and which it defines (`def`, `class`, or an assignment, also inside a module-level `if` or `try`; a name both imported and defined counts as defined). A `patch(...)`, `patch.object(...)`, or `monkeypatch.setattr(...)` target that names an imported name is a **test double**: the test replaces a collaborator, not the module's own code. It is listed under `doubles`, not `internals`. A test whose only non-seam references in a module are doubles is an interface test with doubles: it stays a pinning candidate with `kind: collaborator-double` and the note "re-point the stub (deps injection or a checked patch); do not delete". When the double's name is imported from outside the project's source files (third-party or stdlib, a system boundary), the kind is `boundary-double` instead, with the note "double of a system boundary: keep, no deletion"; project ports that wrap a boundary count as project modules and stay `collaborator-double`. No static signal marks a port, so a patched port keeps the ticket; inject the port instead of patching it (`tdd/mocking.md`: inject first). When the same test takes a stricter kind in another module, every record of it carries that kind and the move or covered note instead. (`codebase-design` has no term for this; it names an in-memory fake or a mock adapter, which a test double may be.)

**Pinning kinds.** Each non-seam reference has a kind, and each pinning candidate carries `kind`:

| `kind` | Reference | Workflow |
|---|---|---|
| `public-non-seam` | A public name defined in the module that is not a confirmed seam. | A human seam decision: confirm it as a seam, or move the test to one. |
| `private` | A `def`, `class`, or lambda name with a leading-underscore part (`_tokenize`, `Acc._drain`). | Merge the assertion into the closest existing interface test as parametrized cases, keep the original, run the mutation check (`SKILL.md` → Follow-up: mutation deletion gate (optional)), then delete. |
| `collaborator-double` | A patch target bound by an import (a test double). | Re-point the stub: deps injection or a checked patch. Do not delete. |
| `boundary-double` | A patch target bound by an import from outside the project's source files (third-party or stdlib: a system boundary). | Keep the double; do not delete. Check the patch is injected or checked. |
| `constant` | A module-level name bound by an assignment, not a `def`, `class`, or lambda, with or without a leading underscore (`TIMEOUT`, `_cache`). | Re-point the stub. |
| `other` | Anything else, for example an imported name the test uses without patching it. | Look by hand. |

When a test has several kinds, it follows the strictest: `public-non-seam` > `private` > `collaborator-double` > `constant` > `boundary-double` > `other`. `kind` is the strictest over every non-seam reference of the test, in every module, so all entries of one test carry the same kind and the test is grouped under it. Writing one new interface test per pinning test is not the goal.

**Coverage against the interface** (needs evidence status `ok`). A seam's body lines are the lines of its body statements (decorators and the `def`/`class` header excluded: the header runs at import, outside any `|run` context). A seam is **reached** when an interface test's `covered` lines for the module intersect its body lines; parametrized ids merge by their base id. A confirmed seam no interface test reaches is an **add candidate**; pinning tests never count. A seam whose name has no function or class body in its module (a re-export or a constant in `__all__`) is never an add candidate; the report warns. A test that imports a name through a package `__init__` re-export (`from pkg import run`, where `pkg/__init__.py` has `from .mod import run`) is linked to the `__init__`, not to `mod.py`, so it is not an interface test of `mod.py` and its coverage does not count toward reaching `mod.py`'s seam. When such a seam is an add candidate, the helper adds a warning that the candidate needs a check by hand. Re-exports are followed through every package level: when `pkg/sub/__init__.py` re-exports `run` from `.mod` and `pkg/__init__.py` re-exports it from `.sub`, a test importing `from pkg import run` is linked to `pkg/__init__.py` the same way: it does not reach the seam in `pkg/sub/mod.py`, and that add candidate gets the warning. A pinning candidate has `covered_through_interface: true` when some interface test of the same module covers a superset of its lines in that module (a pinning test with no coverage in the evidence gets `false`, with a warning); the note is then "lines covered by one interface test (assertions not compared)", otherwise "move the assertion to the interface". With evidence status other than `ok`, `add_candidates` and `covered_through_interface` are omitted (keys absent) and the note is "move the assertion to the interface".

**`seams` object** in `simplification-plan.json` (only confirmed seams are listed; under `--dry-run` or unattended runs with no readable `seams-confirmed.json`, seams stay `proposed` in the ledger and the plan carries no `pinning_candidates`):

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
      "doubles": ["load_config"],
      "kind": "private",
      "covered_through_interface": true,
      "note": "lines covered by one interface test (assertions not compared)"
    }
  ]
}
```

Each pinning candidate also goes to `review_candidates` as `{ file, test_name, criterion: "pinning", kind, evidence, note }`.

**Seam sidecars**, all under `.scratch/refactor-tests/`:

| File | Written by | Holds |
|---|---|---|
| `seams-proposed.json` | Step 7b item 1 | the `propose` output of this run |
| `seams-classified.json` | Step 7b item 3 | the `classify` output of this run |
| `seams-confirmed.json` | Step 7b item 2, when a round confirms | `{ schema_version: 1, modules }` in the `propose` shape; each seam has `status: confirmed`, or `rejected` for a name the user removed |

Step 1 never archives `seams-confirmed.json`: it carries the confirmed seams from run to run. A `--dry-run` never writes it.

**Reuse across runs.** `classify_seams.py reuse --root P --proposed .scratch/refactor-tests/seams-proposed.json` reads `seams-confirmed.json` (`--confirmed` overrides the path) and prints `{ status, modules, diff: { new_modules, added, removed }, review_modules, public_api_modules, warnings }`:

- `status` is `ok`, `absent` (no file), or `ignored`. A file that cannot be read, is not JSON, or has the wrong shape (no `modules` key, `modules` not an object, or a module without a `seams` list of entries with string `name` and `status`) is `ignored` with a warning; the run then behaves as with no file.
- `modules` keeps each earlier seam with its status and adds this run's new proposals as `proposed`. A rejected name is not proposed again.
- A confirmed module whose file no longer exists, or a seam name its module no longer binds (top-level name or `Class.method`), is dropped with a warning naming it. A module that cannot be parsed, or that has a star import or a module `__getattr__`, keeps its seams unchecked, with a warning. Literal `__all__` names count as bound.
- `diff`: `new_modules` (not in the file), `added` (newly proposed names per module), `removed` (confirmed names this run no longer proposes, except `signal: user` names, which were never proposed; they stay confirmed until the user removes them).
- `review_modules` are the new or changed modules: the only ones the confirm round shows. `public_api_modules` are those of them with a `public-api` proposal, the weakest signal.

## Random-order gate

Step 8b of `SKILL.md`. Helper: `reference/python/order_gate.py` (`plugin`, `classify`, `demote`). The gate compares JUnit ids (`classname::name`, as in Per-runner output formats); `classify` converts node-id baselines (`path.py::Class::name`, the ledger and `baseline-ids.json` form) to that form first.

**Plugin choice.** pytest-random-order already importable in the runner's environment: use it with `--random-order-bucket=global --random-order-seed=<seed>`, plus `-p no:randomly` when pytest-randomly is importable too. Otherwise: pytest-randomly with `--randomly-seed=<seed>`, installed only for the gate run when it is not already present, and with the recorded `-p no:randomly` dropped. One shuffler per run, never two. Every other run of the skill stays in fixed order (Step 3).

**Classification**, against the gate baseline (ledger `simplification.post_layout_baseline`, or the Step 3 baseline when it is absent: `--phases=B`, or a `--dry-run` that moved nothing):

| Baseline | Gate run | Same-seed re-run | Result |
|---|---|---|---|
| not passing | any | — | excluded, listed as a baseline failure |
| passing | passed or skipped | — | no label |
| passing | failed or error | failed, error, skipped, or absent | `order-dependent` |
| passing | failed or error | passed | `flaky` |

The baseline is `simplification.post_layout_baseline`, or the Step 3 baseline when that is absent. A baseline that gives a pass count instead of passing ids (the ledger shape) counts every id not in its `failed` list as passing. A baseline that lists passing ids marks any other id `not-in-baseline` and excludes it.

**`order-gate.json`** (`classify` output, kept in `.scratch/refactor-tests/`):

```json
{
  "seed": 1234567,
  "order_dependent": ["tests.protrading.adapters.test_instruments::test_parse_cached"],
  "flaky": [],
  "excluded": [ { "id": "tests.protrading.test_slow::test_x", "baseline": "failed" } ],
  "candidates": ["tests.protrading.adapters.test_instruments::test_parse_cached"],
  "rerun_required": false
}
```

**Ledger `order_gate`**: `{ status: ok|skipped|failed, reason, plugin, seed, order_dependent: [ids], flaky: [ids] }`. `reason` is `null` with `ok`, else one line. `status: ok` is written only after `demote` exits 0. `demote` exit 2 with stderr starting `order_gate demote:` (`rerun_required` refusal) is not a helper failure; any other exit 2 is: no status is written until the same-seed re-run is classified and `demote` exits 0; a re-run that cannot complete gives `failed` with reason `rerun_required: <why>`. Any other non-zero `demote` exit gives `failed`. Resume reuses a recorded status and never runs the suite again.

**Demotion.** A planned change involves a flagged test when the test's file and base name (parameter suffix dropped on both sides) match an id; when both the id and the plan entry name a class, the class must agree. A class-less side matches any class: a plan `test_name` of `test_x` matches a flagged `Cls::test_x`, and a flagged top-level `test_x` matches a plan `Cls::test_x`. This differs on purpose from `calltime_delta.py`, where a bare id names a top-level test only. The two errors cost different things. A missed demotion lets Step 9 delete or merge an order-dependent test, while a needless demotion only adds a `review_candidates` entry, so the gate errs toward demoting. A wrong `call_s` charge misstates the reported saving, so call time errs toward charging nothing. `demote` refuses a gate result with `rerun_required: true` (exit 2, plan unchanged): its candidates carry no label until the same-seed re-run is classified. The tests a change involves: a removal's `test_name`; for an exact-duplicate removal also its kept test in `duplicate_of`; every name in a parametrization's `tests`. A change that involves an `order-dependent` or `flaky` test leaves `removals` or `parametrizations` whole. It goes to `review_candidates` as one entry per involved test and per criterion: `{ file, test_name, criterion: "order-dependent"|"flaky", evidence, seed, failing_ids }`, where `failing_ids` holds the flagged ids that this change involves.

## Test evidence schema (`.scratch/refactor-tests/test-evidence.json`)

Written by the evidence pass (Phase B, first step). Schema version 1. Python helpers: `reference/python/calltime.py` (timing hook), `extract_arcs.py` (per-test lines and arcs), `assemble_evidence.py` (this file).

```json
{
  "schema_version": 1,
  "id_basis": "post-layout",
  "git_sha": "3f2c9a1e0b7d4c6a8e5f1b2d3c4a5e6f7a8b9c0d",
  "dirty": false,
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

- `id_basis` names the tree the test ids come from. `post-layout`: Phase A moved the tests and Step 6 found the layout healthy (ledger `simplification.post_layout_baseline` is set). `pre-layout`: the ids are those of Step 3, because Phase A moved no file: `--dry-run` (with or without Phase A in `--phases`) or `--phases=B`. Under `pre-layout`, a test that `plan.json` moves keeps its old path in its id. The caller passes the value with `--id-basis`; `assemble_evidence.py` refuses an `--existing` file with another value.
- `tests` is keyed by test id (node id). Only tests whose call-phase `outcome` is `passed` get an entry; every other test is listed under `excluded` with its outcome: `failed`, `skipped`, `no-coverage` (a passed test with no `|run` context in the coverage data), or `no-timing` (a covered id with no row from the timing run).
- `call_s` is the call-phase duration in seconds from the serial, untraced timing run. `covered` comes from the traced run, `|run` contexts only. Negative arc endpoints are function entry and exit.
- A language block with `status` `skipped` or `failed` carries a `reason` and empty `tests`.
- `git_sha` and `dirty` are the provenance: `git rev-parse HEAD` and whether `git status --porcelain` is not empty, run in `--root`. An `ok` call writes them. Both are `null` outside git or when git fails. A `failed` call writes `null` to both, also over values an `--existing` file holds, so a failed assembly leaves no SHA. A `skipped` call keeps the values an `--existing` file holds and otherwise writes `null`. Step 11 reads `git_sha` from this file for the ticket bodies and `run-summary.json`.
- `kill_set` is a reserved top-level key for a later mutation-based check. v1 does not write it, and the mutation deletion gate below does not write it yet.

## Mutation deletion gate

Optional follow-up, per module; see `SKILL.md` → Follow-up: mutation deletion gate (optional). Coverage-subset is not redundancy: on one pro-trading module, deleting the flagged set would have dropped the mutation score from 26/28 to 11/28. A first summary also counted excluded `no-coverage` tests as non-killers, which turned "15 of 26" into "21 of 26". Neither mutmut nor Cosmic Ray records which test killed a mutant, so the gate compares two runs.

**Contract.** Delete test T only if every mutant T kills is also killed by some kept test. Tests listed under evidence `excluded` are kept tests: they count as killers, never as candidates.

**Recipe.**

1. Run mutmut twice on module M, scoped to M's covering tests: once as is, once with the candidate batch deselected. A mutant killed in the first run and surviving the second is a lost kill.
2. A timeout counts as killed in both runs. A mutant with a non-deterministic outcome counts as lost.
3. Re-run only the lost mutants without fail-fast, to build the restore list: the tests to keep.
4. Use batches of 25 candidates.
5. Leave migrations and generated code out of the count. mutmut reads `mutate_only_covered_lines` and `do_not_mutate` only from project config: rely on them if the project already sets them; otherwise drop mutants in those files from both runs when comparing.
6. Install mutmut ephemerally, as Step 7 does. Edit no project config.
7. Run the gate after the hotspot fixes. It is about 9.6x cheaper once a shared cost is gone.

The gate is advice, not a build dependency. It does not write the reserved `kill_set` key of the evidence file. Porting a helper waits until pro-trading #843 proves its tool.

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
