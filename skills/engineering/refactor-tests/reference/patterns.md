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

**Directory guard check.** Before moving any file into the integration target, check whether that directory is constrained by a project-specific guard — a meta-test or CI check that restricts what may live there (e.g. a frozen baseline file, a marker/fixture requirement enforced by AST). Read `docs/agents/testing.md` → Test layout first. When its `Integration directory:` line sets a directory for a language (a single line; split it on `; ` into `<language>: <dir>` pairs, each naming its language's directory; a bare value, with no language, belongs to the primary test language, defined under Language detection), that directory replaces that language's table default as the move target, and the membership rule written beside it applies; other languages keep the table default. When its `Guard:` line names a check, that check is the guard. When the file, the `Integration directory:` line or the `Guard:` line is absent or reads `not set` (rule: `setup-skills/testing.md`), the table default stands for a missing directory line, and a missing guard line sends you to look for the guard the way you'd look for the runner: a project doc (`AGENTS.md`/`CLAUDE.md`-pointed testing guide) describing the directory's membership rule, or a test file named after the constraint. If such a guard exists and the candidate file would violate it (e.g. it doesn't carry the required marker/fixture and the baseline may not grow), do not move it — leave it in place and record it as pinned (same treatment as the Go build-tag exception below), with the guard's name as the reason.

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
| `kind` | string | dead-test (see Assertion vocabulary → Dead-test kinds), pinning (see `seam-classification.md` → Pinning kinds) |
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

Moved to `review-queue.md` (beside this file).

## Seam classification (Python)

Moved to `seam-classification.md` (beside this file).

## Random-order gate

Moved to `random-order-gate.md` (beside this file).

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

Moved to `mutation-gate.md` (beside this file).

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
