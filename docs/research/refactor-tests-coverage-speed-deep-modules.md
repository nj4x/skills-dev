# Research: How refactor-tests can find redundant, useless, or unimportant tests

**Date:** 2026-10-15
**Scope:** `skills/engineering/refactor-tests/` (SKILL.md, reference/patterns.md, reference/springboot.md, provenance-marks-value.md); `skills/engineering/codebase-design/`; `skills/engineering/improve-codebase-architecture/`; `skills/engineering/tdd/`; `skills/engineering/testing/`; `docs/agents/skill-dependencies.md`. External: per-test coverage, per-test timing, mutation testing, and test-impact tooling for Python, JVM, JS/TS, .NET, Go, Rust, and briefly Ruby and PHP. Academic work on test-suite minimization. Ousterhout and Feathers for deep modules and seams.

Verification notes: WebFetch returns model summaries, so quotes marked "(summary)" were not checked against raw text. Items marked **[unverified]** could not be confirmed from a primary text.

---

## Summary

The current skill decides removals from static source features only: AST-level duplicate detection, assertion-list subset checks, and a dead-test check (SKILL.md:133-140). It never looks at what a test actually executes or how long it takes. That makes its removal claims weak. Redundancy is a property of runtime evidence: which lines or arcs a test covers, which mutants it kills, and what it costs. Several mainstream tools expose this per test. Python (coverage.py contexts, pytest-cov) and JS (Stryker `perTest`) do it best. JVM (OpenClover, PIT's kill matrix) and .NET (only Stryker.NET) are narrower. Go and Rust give per-test coverage only by running each test separately, and no mutation tool there records killers.

Core recommendation: add a per-test evidence step (coverage by context, per-test duration, and where available a mutant-kill matrix). Make removal require a subsumption test on that evidence. Use the deep-module vocabulary from `codebase-design` to classify tests by seam. Coverage-only minimization loses fault-detection power, so coverage subset alone must never delete a test.

---

## 1. Per-test tooling by language

### 1.1 Python

**Per-test coverage.** coverage.py supports dynamic contexts. Setting `dynamic_context = test_function` starts a new context per test function, and code run between tests goes to the empty context (https://github.com/nedbat/coveragepy/blob/master/doc/contexts.rst). pytest-cov provides `--cov-context=test`, which records coverage "for each test individually" (https://pytest-cov.readthedocs.io/en/latest/contexts.html). Context names look like `test_x.py::test_a|run`, with the phase after the pipe being setup, run, or teardown. Each parametrize case gets its own context. pytest-cov warns if both `dynamic_context` and `--cov-context` are set (https://github.com/pytest-dev/pytest-cov/blob/master/src/pytest_cov/engine.py).

Export: `coverage json --show-contexts` adds a `contexts` map per file, keyed by line number. Its format version is 3 (https://coverage.readthedocs.io/en/latest/commands/cmd_json.html; https://github.com/nedbat/coveragepy/blob/master/coverage/jsonreport.py). `coverage html --show-contexts` is the HTML equivalent. The `CoverageData` API (added in 5.0) provides `contexts_by_lineno()`, `measured_contexts()`, and `set_query_contexts()` (https://coverage.readthedocs.io/en/latest/api_coveragedata.html). The SQLite schema has `context`, `line_bits`, and `arc` tables (https://coverage.readthedocs.io/en/latest/dbschema.html). The numbits encoding is an implementation detail, so use the provided helpers.

Caveats:
- With xdist, pytest-cov's own tests run contexts under `-n 1..3` (https://github.com/pytest-dev/pytest-cov/blob/master/tests/test_pytest_cov.py), but the docs do not state xdist support for contexts (https://pytest-cov.readthedocs.io/en/latest/xdist.html). Run the evidence pass without xdist.
- Contexts disable the sysmon core. The config docs say sysmon "does not yet support plugins, dynamic contexts" (https://github.com/nedbat/coveragepy/blob/master/doc/config.rst). Coverage warns "Dynamic contexts aren't supported with core=sysmon" in `coverage/control.py`. On Python 3.14+, set `[run] core = ctrace` (inference from source, not a documented recommendation).
- Branch data: `--cov-branch` or `[run] branch = True`. Arcs are stored per context.

**Per-test timing.** `pytest --durations=N` and `--durations-min` (https://github.com/pytest-dev/pytest/blob/main/src/_pytest/runner.py; https://docs.pytest.org/en/stable/how-to/usage.html). JUnit XML is written with `--junitxml`. `junit_duration_report` takes `total` (default, includes setup and teardown) or `call` (test body only) (https://docs.pytest.org/en/stable/how-to/output.html). Use `call` for the cost of the test itself. `pytest-json-report` (1.5.0, no release since 2022) writes per-stage `duration` for `setup`, `call`, and `teardown` (https://github.com/numirias/pytest-json-report).

**Mutation testing.**
- mutmut 3.8.0 (https://mutmut.readthedocs.io/en/latest/; https://github.com/boxed/mutmut): runs a stats pass that records `tests_by_mangled_function_name` and `duration_by_test` in `mutants/mutmut-stats.json` (`src/mutmut/stats.py`). It runs tests with `-x`, so it stops at the first failure. Results store only exit codes per mutant. **It does not record which test killed a mutant.** `mutmut tests-for-mutant` gives the candidate set. Per-test kill data needs a custom rerun without `-x`.
- cosmic-ray 8.7.0 (https://github.com/sixty-north/cosmic-ray): a SQLite session with one record per mutation. `WorkResult` holds only outcome, output, and diff (`src/cosmic_ray/work_item.py`). No per-test kill data.

**Test impact analysis.** pytest-testmon 2.2.0 (https://github.com/tarpas/pytest-testmon) writes `.testmondata` with `test_execution(test_name, duration, failed, forced)` and method-level fingerprints (`testmon/db.py`). It gives per-test duration for free and selects tests by change.

**Order dependence.** Before removing anything, run with pytest-randomly (shuffles by default; `-p no:randomly` disables it; https://github.com/pytest-dev/pytest-randomly) or pytest-random-order (`--random-order`; https://github.com/pytest-dev/pytest-random-order). Order-dependent tests can be hidden by the current order. Luo et al. (2014) and Lam et al. (2019) report order dependence as a real flake class (section 5).

### 1.2 JVM (Java and Kotlin, Maven and Gradle, JUnit)

**Per-test coverage.**
- JaCoCo has no per-test feature. Its FAQ has no entry for it (https://www.jacoco.org/jacoco/trunk/doc/faq.html). The agent supports `sessionid` ("A session identifier that is written with the execution data"), `output=tcpserver`, and `jmx=true` (https://www.jacoco.org/jacoco/trunk/doc/agent.html). A per-test recipe is possible: call `IAgent.setSessionId(testName)` and `getExecutionData(reset=true)` from a JUnit listener. This is an inference, not a documented feature. The Maven `dump` goal requests a dump over TCP (https://www.jacoco.org/jacoco/trunk/doc/dump-mojo.html).
- **OpenClover 5.1 has native per-test coverage.** Enable it with `<distributedCoverage/>` in `clover-maven-plugin` (https://openclover.org/doc/manual/latest/maven--using-distributed-per-test-coverage.html). Quote: "Clover's per-test coverage data gives you unique insight into how each of your tests exercises the codebase." Caveat: "Clover's per-test coverage collection does not support parallel test execution" (https://openclover.org/doc/manual/4.2.0/general--what-is-distributed-per-test-coverage.html). The documented detection covers JUnit 3/4 and TestNG. **JUnit 5 support is unverified.** Its test optimization mode (`clover:optimize`, `.clover/clover.snapshot`) runs only tests covering changed files (https://openclover.org/doc/manual/latest/maven--using-test-optimization.html).
- Kover 0.9.8: its docs do not mention per-test attribution. Treat it as unsupported (https://kotlin.github.io/kotlinx-kover/gradle-plugin/).

**Per-test timing.**
- Surefire 3.6.0 writes `TEST-*.xml` to `target/surefire-reports` (https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html). `reportFormat` affects only the `.txt` files, not the XML. The per-testcase `time` attribute was not verified from the XSD **[unverified]**.
- Gradle writes XML to `build/test-results/<task>` (one file per class). `outputPerTestCase` links log output to each case. `mergeReruns` records retried failures as `<flakyFailure>` (https://docs.gradle.org/current/userguide/java_testing.html).
- JUnit Open Test Reporting: `junit.platform.reporting.open.xml.enabled=true` writes `open-test-report.xml` (https://docs.junit.org/6.0.3/advanced-topics/junit-platform-reporting.html). The page does not mention per-test duration.

**Mutation testing: PIT (pitest 1.30.1).**
- `fullMutationMatrix`: "When set to true causes pitest to continue processing after a test fails." Output is partially supported. Default `false` (https://pitest.org/quickstart/maven/).
- Javadoc in source: with `false`, "the test execution will stop after the first killing test" (https://github.com/hcoles/pitest/blob/master/pitest-maven/src/main/java/org/pitest/maven/PitMojo.java).
- `mutations.xml` (XML listener only, so `XML` must be in `outputFormats`) has each `<mutation>` with `detected`, `status`, `numberOfTestsRun`, and either `killingTest` (matrix off) or `killingTests`, `succeedingTests`, `coveringTests` (matrix on, names joined by `|`) (https://github.com/hcoles/pitest/blob/master/pitest-entry/src/main/java/org/pitest/mutationtest/report/xml/XMLReportListener.java).
- Other options: `+auto_threads`, `withHistory` (experimental, https://pitest.org/quickstart/incremental_analysis/), `testStrengthThreshold`.
- JUnit 5 needs `pitest-junit5-plugin` (1.2.3, requires pitest 1.19.4+; https://github.com/pitest/pitest-junit5-plugin). Gradle plugin `info.solidsoft.pitest` (https://gradle-pitest-plugin.solidsoft.info/). Commands: `mvn org.pitest:pitest-maven:mutationCoverage`, `./gradlew pitest`.
- Kotlin: Arcmutate's `pitest-kotlin-plugin` is commercial and filters coroutine and inline junk mutants (https://docs.arcmutate.com/docs/kotlin.html).

**Test impact analysis.** Develocity Predictive Test Selection is ML-based and needs build-scan history (https://docs.develocity.ai/predictive-test-selection/). STARTS (https://github.com/TestingResearchIllinois/starts) and Ekstazi (https://github.com/gliga/ekstazi) do static and dynamic class-level selection. Surefire's `-Dsurefire.rerunFailingTestsCount=N` flags flakes (https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html).

### 1.3 JavaScript and TypeScript

**Coverage.** Jest `--coverageProvider` is `babel` (default) or `v8` (https://jestjs.io/docs/cli). The `json` reporter writes Istanbul `coverage-final.json` (https://jestjs.io/docs/configuration). Vitest `--coverage.provider` is `v8`, `istanbul`, or `custom` (https://vitest.dev/guide/cli.html). Neither Jest nor Vitest records per-test coverage. Node's `NODE_V8_COVERAGE` writes raw V8 coverage (https://nodejs.org/api/test.html). c8 was not verified.

**Timing.** Jest `--json --outputFile=<f>` gives per-assertion `duration`, `status`, `ancestorTitles`, and per-file `perfStats` (https://jestjs.io/docs/configuration; https://jestjs.io/docs/cli). Vitest `--reporter json|junit` plus `--outputFile`. Node test runner `--test-reporter junit` needs `--test-reporter-destination` (https://nodejs.org/api/test.html).

**Mutation testing: StrykerJS.** This is the strongest per-test source in JS.
- `coverageAnalysis`: `off`, `all`, `perTest`. Default is `perTest`. With `perTest`, "only those tests run" that cover each mutant. Tests must be runnable independently and in random order (https://stryker-mutator.io/docs/stryker-js/configuration/).
- JSON reporter: `--reporters json` writes `reports/mutation/mutation.json` by default. `--incremental` with `incrementalFile` (https://stryker-mutator.io/docs/stryker-js/configuration/).
- Report schema (mutation-testing-report-schema, fetched as a summary): mutant `status` enum includes `Killed`, `Survived`, `NoCoverage`, `Timeout`. `killedBy` lists test ids that killed the mutant. `coveredBy` lists test ids that covered it. `testFiles[].tests[]` gives `id`, `name`, `location` (https://raw.githubusercontent.com/stryker-mutator/mutation-testing-elements/master/packages/report-schema/src/mutation-testing-report-schema.json). The schema says tests should bail on the first failing test, so `killedBy` can under-report.
- Per-test metrics in `packages/metrics`: `TestStatus` is `Killing`, `Covering`, or `NotCovering` (https://raw.githubusercontent.com/stryker-mutator/mutation-testing-elements/master/packages/metrics/src/model/test-model.ts). A test that is `Covering` or `NotCovering` kills nothing, which is the redundancy signal.

**Test impact analysis.** Jest `--findRelatedTests <files>`, `--onlyChanged` (needs a static dependency graph), `--changedSince <ref>` (https://jestjs.io/docs/cli). Vitest `vitest related <files>` and `--changed [since]` (https://vitest.dev/guide/cli.html).

### 1.4 Go

**Coverage.** `-coverprofile`, `-covermode` (`set`, `count`, `atomic`), and `-coverpkg` (https://pkg.go.dev/cmd/go/internal/test). Per-test coverage requires one run per test: `go test -run '^TestX$' -coverprofile=x.out pkg`. Note that `-run=X/Y` also runs parents (same page).

Go 1.20+ `GOCOVERDIR` and `go tool covdata` (https://go.dev/doc/build-cover; https://pkg.go.dev/cmd/covdata). `covdata` has `textfmt`, `merge`, `subtract`, and `intersect`, with `-i=dir1,dir2 -o=outdir`. These set operations give a direct subsumption test. If `subtract` of test B's data from test A's leaves nothing, B adds no coverage beyond A. Set `-test.gocoverdir` per run to keep data separate; this flag was not verified on the docs page **[unverified]**.

**Timing.** `go test -json` emits test2json events with `Elapsed` on `pass` and `fail` (https://pkg.go.dev/cmd/test2json). gotestsum v1.13.0 adds `--jsonfile`, `--junitfile`, and `gotestsum tool slowest --threshold` (https://github.com/gotestyourself/gotestsum).

**Mutation testing.**
- gremlins v0.6.0: `gremlins unleash --output=output.json` writes per-mutation `line`, `column`, `type`, `status` (KILLED, LIVED, NOT COVERED, TIMED OUT, NOT VIABLE). No killing-test field (https://gremlins.dev/latest/usage/commands/unleash/).
- go-mutesting (avito-tech): exec contract is exit codes only, no per-test data (https://github.com/avito-tech/go-mutesting).
- ooze: score and surviving-mutant diffs only (https://github.com/gtramontina/ooze).

**Caching.** `go test` caches results for package list mode, and `-count=1` disables it. Go has no built-in test impact analysis (https://pkg.go.dev/cmd/go/internal/test).

### 1.5 Rust

**Coverage.** cargo-llvm-cov v0.9.1 supports `--json`, `--lcov`, `--cobertura`, `--codecov`, `--no-report`, and `report`. Per-test coverage is possible by running `clean --workspace`, then `cargo llvm-cov --no-report nextest -E 'test(=name)'`, then `report --json` (https://github.com/taiki-e/cargo-llvm-cov). The raw mechanism is `RUSTFLAGS="-C instrument-coverage"` with `LLVM_PROFILE_FILE` (https://doc.rust-lang.org/rustc/instrument-coverage.html).

**Timing.** nextest JUnit: `[profile.ci.junit] path = "junit.xml"`, where `<testcase time>` is in seconds (https://nexte.st/docs/machine-readable/junit/). libtest JSON is experimental (`NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`, https://nexte.st/docs/machine-readable/libtest-json/). libtest `--report-time` and `--format json` are unstable (https://doc.rust-lang.org/rustc/tests/index.html).

**Mutation testing.** cargo-mutants v27.1.0 writes `outcomes.json`, `caught.txt`, `missed.txt`, `timeout.txt`, `unviable.txt` (https://mutants.rs/mutants-out.html). The source shows `ScenarioOutcome` holds log and diff paths, not the killing test (https://github.com/sourcefrog/cargo-mutants/blob/main/src/outcome.rs). Killer names exist only in `logs/`. `--test-tool=nextest` is supported. Doctests do not run (https://mutants.rs/nextest.html).

### 1.6 C# and .NET

**Coverage.** coverlet: `dotnet test --collect:"XPlat Code Coverage"` with `coverlet.collector`. Formats are cobertura (default), json, lcov, opencover, teamcity. No per-test option is documented (https://github.com/coverlet-coverage/coverlet/blob/master/Documentation/VSTestIntegration.md). `coverlet.collector` does not support the Microsoft Testing Platform. Microsoft's MTP coverage extension has no per-test option (https://learn.microsoft.com/en-us/dotnet/core/testing/microsoft-testing-platform-extensions-code-coverage). `dotnet-coverage` has `snapshot --reset --tag-name`, which could give per-test snapshots by inference; the docs do not claim it (https://learn.microsoft.com/en-us/dotnet/core/additional-tools/dotnet-coverage).

**Timing.** `--logger "trx;LogFileName=x.trx"` (https://github.com/microsoft/vstest/blob/main/docs/report.md). The trx `duration` attribute was not verified **[unverified]**. Console verbosity `detailed` shows per-test lines.

**Mutation testing.** Stryker.NET: `coverage-analysis` defaults to `perTest` (config file only). Values are `perTest`, `perTestInIsolation`, `all`, `off`. `-r json` writes a JSON report, and `--since` runs only changed code (https://stryker-mutator.io/docs/stryker-net/configuration/; https://stryker-mutator.io/docs/stryker-net/reporters/). Whether that JSON uses the report schema with `killedBy`/`coveredBy` is **unverified**. Check the source before relying on it.

### 1.7 Ruby and PHP (brief)

- Ruby: simplecov 1.2+ with `track_tests` records which test covers each line. `simplecov tests --redundant` lists tests whose covered lines other tests also cover (https://github.com/simplecov-ruby/simplecov). mutant can use that data for test selection (https://github.com/mbj/mutant/blob/main/docs/test-selection.md).
- PHP: PHPUnit `--path-coverage` needs Xdebug, since "PCOV only supports line coverage" (https://docs.phpunit.de/en/12.5/code-coverage.html). Infection's `--only-covering-test-cases` runs only tests covering the mutated line (https://infection.github.io/guide/command-line-options.html).

### 1.8 Per-test data summary

| Language | Per-test coverage | Per-test timing | Per-test kills | Cheapest route |
|---|---|---|---|---|
| Python | coverage.py contexts, `--cov-context=test` | `--durations`, junit `call` | none (mutmut, cosmic-ray) | pytest-cov + json contexts |
| JVM | OpenClover (no parallel, JUnit 5 unverified) | Surefire/Gradle XML | PIT `fullMutationMatrix` | PIT XML matrix + Surefire XML |
| JS/TS | none native | Jest json `duration` | Stryker `killedBy`/`coveredBy` | Stryker perTest json |
| .NET | none | trx (duration unverified) | Stryker.NET (schema unverified) | Stryker.NET json |
| Go | per-run `-coverprofile`, `covdata subtract` | `go test -json` `Elapsed` | none | per-test runs + covdata |
| Rust | per-run with cargo-llvm-cov | nextest junit `time` | none (killer only in logs) | nextest junit + per-test llvm-cov |
| Ruby | simplecov `track_tests` | not checked | mutant (commercial) | simplecov tests |

---

## 2. Decision method: turning the data into decisions

### 2.1 Why coverage alone is not enough

Coverage-based minimization removes tests that add no coverage. That removes fault-detection power.
- Rothermel et al. (1998) found "the fault detection capabilities of test suites can be severely compromised by minimization" (ICSM 1998, https://doi.org/10.1109/ICSM.1998.738487). Per Yoo and Harman, fault-detection reduction was over 50% for more than half of 1000 suites on Siemens.
- Rothermel et al. (2002) repeated this: "the fault-detection capabilities of test suites can be severely compromised by test-suite reduction" (STVR 12(4), https://doi.org/10.1002/stvr.256). On `space`, HGS lost 8.9% versus 18.1% for random reduction of equal size (per Yoo and Harman).
- Wong et al. (1995) found small losses on random suites: mean effectiveness loss 0 to 1.45% across block-coverage bands (ICSE 1995, https://doi.org/10.1145/225014.225018; figures via Yoo and Harman). The disagreement is explained by subject programs, suite redundancy, and fault difficulty (Rothermel 2002, as summarized by Yoo and Harman).
- Shi et al. (2014) quantify the trade-off: statement-coverage reduction "can reduce test-suite size on average 62.9% but loses up to 20.5% in killed mutants." Killed-mutant-based reduction gave no loss in killed mutants, with an 11.9 percentage point larger suite (FSE 2014, https://doi.org/10.1145/2635868.2635921).

**Implication for the skill:** a coverage subset is a candidate signal only. Mutant kills (or an explicit fault-detection proxy) must confirm removal.

### 2.2 Mutants as the signal for usefulness

- Just et al. (2014) found "statistically significant correlation between mutant detection and real fault detection, independently of code coverage" (FSE 2014, https://doi.org/10.1145/2635868.2635929). 73% of real faults were coupled to mutants.
- Papadakis et al. (2018) found that correlations are weak once test suite size is controlled (ICSE 2018, https://doi.org/10.1145/3180155.3180183). They still conclude that "mutants provide good guidance for improving the fault detection of test suites."
- Inozemtseva and Holmes (2014) found "low to moderate correlation between coverage and effectiveness when the number of test cases in the suite is controlled for" (ICSE 2014, https://doi.org/10.1145/2568225.2568271). This supports using kills over coverage.
- Redundant mutants inflate scores. Ammann, Delamaro, and Offutt (2014) show how to minimize mutant sets by subsumption (ICST 2014, https://doi.org/10.1109/ICST.2014.13). Apply the same reasoning to tests.

### 2.3 Algorithm

Harrold, Gupta, and Soffa (1993) define the baseline. Their heuristic removes redundant and obsolete tests while preserving the coverage of the full suite (TOSEM 2(3), https://doi.org/10.1145/152388.152391). Minimization is NP-complete, reducible from set cover (Yoo and Harman 2012, STVR 22(2), https://doi.org/10.1002/stvr.430). Jeffrey and Gupta (2007) improve HGS by keeping some redundant tests that kill extra faults (TSE 33(2), https://doi.org/10.1109/TSE.2007.18).

Proposed decision rule per test T, on the evidence in section 3:
1. **Remove (safe)**: exact duplicate AST and fixtures (existing criterion), or trivially true (existing).
2. **Remove candidate (needs kill data)**: every covered line and arc of T is covered by kept tests in the same run (subset by context), **and** T kills no mutant that no other kept test kills (kill-set subset). Coverage subset alone goes to review, not removal.
3. **Keep**: T is the sole test at a seam (section 4), or T kills a unique mutant.
4. **Review (costly, low value)**: T is in the top cost decile by `call` duration, and passes criterion 2. Surface these to the user with their time saved.
5. **Gate**: candidates must pass a randomized-order run (section 1.1, 1.3) and a flake retry (existing SKILL.md:118, 176).

Greedy selection order: take tests with the highest duration first, as HGS does with requirement rarity. Re-verify after each removal, because removing one test changes the subset relations of others. The existing ordering guard (SKILL.md:160) does this for assertion subsets only.

### 2.4 Other criteria to add

- **Implementation coupling** (section 4): tests that mock internal collaborators, assert on private methods, or assert on call counts of internal functions. Van Deursen et al. (2001) and Meszaros (2007) name these smells. Google's guidance "Test State, Not Interactions" says interaction tests "check how a system arrived at its result" (SWE at Google ch. 12, https://abseil.io/resources/swe-book/html/ch12.html). These are candidates for rewrite, not removal.
- **Flakiness**: a test that fails intermittently gives no signal and should be fixed or removed. Luo et al. (2014) report that async wait is 45% of flaky-fix causes and order dependence is 12% (FSE 2014, https://doi.org/10.1145/2635868.2635920). Google treats around 1% flakiness as the point where tests "begin to lose value" (https://abseil.io/resources/swe-book/html/ch11.html).
- **Test size**: Google's small/medium/large model (https://abseil.io/resources/swe-book/html/ch11.html) gives a cost axis. Bazel's default timeouts are small 60 s, medium 300 s, large 900 s (https://bazel.build/reference/be/common-definitions).

---

## 3. Deep modules and seams

### 3.1 Vocabulary in this repo

`skills/engineering/codebase-design/SKILL.md` is the shared source of the terms.
- **Depth** is "leverage at the interface: the amount of behaviour a caller (or test) can exercise per unit of interface they have to learn" (SKILL.md:20). A module is deep when much behaviour sits behind a small interface.
- **Interface** includes "invariants, ordering constraints, error modes, required configuration, and performance characteristics" (SKILL.md:16). This is wider than a type signature.
- **Seam** is "where a caller depends on a module's interface" (SKILL.md:22), following Feathers.
- **Deletion test** (SKILL.md:63): if deleting a module concentrates complexity, it was earning its keep. If complexity only moves, it was a pass-through.
- **"The interface is the test surface"** (SKILL.md:64). If you want to test past the interface, the module is probably the wrong shape.
- **"One adapter means a hypothetical seam. Two adapters means a real one"** (SKILL.md:65; DEEPENING.md:29).

`DEEPENING.md` says: "Old unit tests on shallow modules become waste once tests at the deepened module's interface exist — delete them" (DEEPENING.md:34). It also says "Tests assert on observable outcomes through the interface, not internal state" (DEEPENING.md:36), and "If a test has to change when the implementation changes, it's testing past the interface" (DEEPENING.md:37).

`DESIGN-IT-TWICE.md` compares interfaces on depth, locality, and seam placement (DESIGN-IT-TWICE.md:42).

### 3.2 Original sources

- Ousterhout, *A Philosophy of Software Design*, ch. 4 "Modules Should Be Deep". Verbatim from his rebuttal in the aposd-vs-clean-code repo: "The best methods are those that provide a lot of functionality but have a very simple interface: they replace a large cognitive load (reading the detailed implementation) with a much smaller cognitive load (learning the interface). I call these methods 'deep'." (https://github.com/johnousterhout/aposd-vs-clean-code/blob/main/README.md). He also says that "the deep/shallow characterization ... captures both sides of the tradeoff." Chapter text on information hiding (ch. 5) and "Design It Twice" (ch. 11) was not retrieved verbatim **[unverified]**.
- Ousterhout on tests (same repo): "I am a huge fan of unit testing. I believe that unit tests are an indispensable part of the software development process and pay for themselves over and over." He prefers "somewhat larger units than in TDD, perhaps a few methods or a class." (same URL). Use this to justify testing at class or module interface, not per private method.
- Feathers, *Working Effectively with Legacy Code* (2004), ch. 4 "Seam Model". Verbatim from InformIT: "A seam is a place where you can alter behavior in your program without editing in that place." (https://www.informit.com/articles/article.aspx?p=359417&seqNum=2). Enabling point: "Every seam has an enabling point, a place where you can make the decision to use one behavior or another." (https://www.informit.com/articles/article.aspx?p=359417&seqNum=3). Seam types are preprocessing, link, and object seams (same URL). Feathers' unit-test speed rule and "legacy code is code without tests" were not verified **[unverified]**.
- Feathers' unit-test definition (not-a-unit-test list, fetched as a summary): a test is not a unit test if it talks to the database, communicates across the network, touches the file system, cannot run in parallel with other unit tests, or needs environment changes (https://www.artima.com/weblogs/viewpost.jsp?thread=126923). This maps to the dependency categories in DEEPENING.md (in-process, local-substitutable, ports, external).
- Beck's Test Desiderata: "structure-insensitive: tests should not change their result if the structure of the code changes" (https://testdesiderata.com/, summary). Also "isolated", "deterministic", "behavioral", "specific". This is the best short statement of the seam rule.
- Fowler, "UnitTest" (https://martinfowler.com/bliki/UnitTest.html): solitary tests use doubles for collaborators; sociable tests do not. Fowler's "TestPyramid" (https://martinfowler.com/bliki/TestPyramid.html) says UI tests are "brittle, expensive to write, and time consuming to run" (summary).

### 3.3 Mapping to refactor-tests

The mapping below turns deep-module vocabulary into test decisions. Use `codebase-design` terms exactly.

| Test kind (by seam) | Decision |
|---|---|
| Test calls the module's public interface and asserts observable outcomes | Keep. This is the test surface. |
| Test pins an internal of a deep module (private helper, internal collaborator, call count) and an interface test covers the same behaviour | Delete candidate (DEEPENING.md:34). Confirm with kill data. |
| Test pins an internal of a deep module, and no interface test covers that behaviour | Rewrite at the interface (move the assertion up), not delete. |
| Public function or seam with no interface-level test | Add candidate. Report it as a gap. |
| Shallow module (pass-through) with its own tests | Deletion test first. If it is a pass-through, its tests are waste. |
| Test mocks an internal collaborator | Rewrite, or delete if the interface test covers the path. |
| Test crosses a real external boundary (DB, network) inside a unit suite | Classify by DEEPENING.md dependency category. Keep if it is the only seam test. |

**Measuring coverage against the interface.** Line coverage is measured on the implementation, so an interface test that exercises deep code counts fully. For seam coverage, define the set of public entry points (from the module's exports, router, or public class API) and map each test to the entry points it calls. A seam with zero tests is an add candidate. A seam with tests only from internal test files is a pinning risk. Record this map in the ledger as `seams` (new field, §5).

**Tests pinning internals of a deep module** are the main deletion risk. Deleting them when the interface test does not cover the same mutants loses fault detection (section 2.1). The kill-set subset rule (section 2.3, criterion 2) prevents this.

**Seam discipline**: DEEPENING.md:29 says one adapter means a hypothetical seam. Tests that exist only to exercise a single-adapter port (a fake that is the only implementation) should be reviewed as indirection, not kept as seam tests.

### 3.4 Cross-skill contracts

`docs/agents/skill-dependencies.md` has no entry for `engineering/testing` as a consumer; the only related lines are `engineering/implement` → `engineering/testing` and `engineering/implement-spec` → `engineering/testing` (`docs/agents/skill-dependencies.md:15`, `:18`). It has no entry for `refactor-tests` either. `skills/engineering/testing/SKILL.md:29` depends on the `refactor-tests` mirroring convention to compute test paths. That dependency is undocumented in the dependency graph. Add an entry: `engineering/testing` → `engineering/refactor-tests` (path convention only). If the mirroring convention changes, `testing` breaks silently.

`engineering/tdd/SKILL.md:14-26` already defines the seam rule ("Tests live at seams, never against internals") and uses `/codebase-design` for vocabulary. `refactor-tests` should use the same definition, so the two skills do not disagree on what a seam is. Add `refactor-tests` to the dependency graph as a consumer of `codebase-design`.

`improve-codebase-architecture/SKILL.md:33` asks "Which parts of the codebase are untested, or hard to test through their current interface?" The refactor-tests add-candidates feed the same question. The two skills can share the seam map.

---

## 4. What the current skill does and what to change

### 4.1 Current behaviour

- Phase B criteria (SKILL.md:133-140): exact duplicate, dead test (no assertion statement), trivially true, subset assertions, parametrize cluster, parametrize pair. All are static. Subset assertions compare assertion lists, not what the code executes.
- Baseline (SKILL.md:76-86) records pass and fail ids only. It does not record per-test duration or coverage.
- Step 2 (SKILL.md:68) classifies cross-cutting files by counting non-mocked methods. This is an AST proxy for seam count, not coverage.
- `patterns.md:69-75` lists per-runner output. Only ids are captured; no timing, coverage, or kill data.
- Phase C (SKILL.md:183-193; springboot.md:73-81) measures context count and wall time, but the only per-test timing is slowest-class reports.
- Dead-test check uses an assertion vocabulary (patterns.md:91-101). It misses tests whose assertions are weak (for example `assertTrue(result != null)`), which kill-set data would catch.

### 4.2 Prioritized recommendations

**P1. Add an evidence pass (new Step 2.5, after baseline).** Run the suite once per language in the configuration below, and write `test-evidence.json` with per-test coverage (line and arc sets keyed by test id), per-test `call` duration, and, where available, a kill matrix. Add the file to the ledger. Without this, no removal decision can be justified.

Per-language evidence command table (verify each flag in the project's version before use):

| Language | Coverage per test | Timing per test | Kill matrix | Notes |
|---|---|---|---|---|
| Python | `pytest --cov=<pkg> --cov-branch --cov-context=test`, then `coverage json --show-contexts` | `pytest --junitxml=<f>` with `junit_duration_report=call` in ini, or `--json-report` | none native; run mutmut per mutant without `-x` (custom) | Run without xdist. Use `core = ctrace` on 3.14+ |
| Java/Kotlin (Maven) | OpenClover `<distributedCoverage/>` (Java only, JUnit 5 unverified) | Surefire `target/surefire-reports/TEST-*.xml` | `mvn org.pitest:pitest-maven:mutationCoverage` with `fullMutationMatrix=true` and `outputFormats` containing `XML` | PIT matrix needs XML output |
| Java/Kotlin (Gradle) | OpenClover via plugin (verify) | `build/test-results/test/TEST-*.xml` | `./gradlew pitest` with the same matrix option | Kotlin mutation needs Arcmutate (commercial) |
| JS/TS | none native; use Stryker | Jest `--json --outputFile=<f>` (per-assertion `duration`) | `npx stryker run` with `coverageAnalysis: perTest` and `reporters: json` | Stryker needs independent, random-order tests |
| Go | `go test -run '^Name$' -coverprofile=<f>` per test; `go tool covdata subtract` | `go test -json` (`Elapsed`) | gremlins `unleash --output` (no killer names) | Per-test runs are slow; limit to candidates |
| Rust | `cargo llvm-cov --no-report nextest -E 'test(=name)'` per test, then `report --json` | nextest JUnit `[profile.ci.junit]` | cargo-mutants (killer names only in `logs/`) | libtest JSON is experimental |
| .NET | none native (coverlet is aggregate) | `dotnet test --logger "trx;LogFileName=<f>"` | `dotnet stryker` with `-r json` (schema unverified) | Verify report format first |
| Ruby | simplecov `track_tests` | not checked | mutant (commercial) | `simplecov tests --redundant` |
| PHP | PHPUnit `--path-coverage` (Xdebug) | JUnit log | Infection `--only-covering-test-cases` | Path coverage needs Xdebug |

**P2. Rewrite Phase B criteria (SKILL.md:133-160).** Keep exact duplicate, trivially true, and dead test. Replace "subset assertions" with two data-driven criteria: coverage subset (within a run, using test-evidence) and kill-set subset (using the kill matrix when present). Coverage subset without kill data goes to `review_candidates`, never `removals`. This fixes the claim that removal is safe. Note the rule that Rothermel (1998) and Shi (2014) give for coverage-only removal losses.

**P3. Add seam classification (new Step 7.5).** Use the vocabulary in section 3.3. For each source module, record public entry points and the tests that call them. Emit `seams` in `simplification-plan.json` with `add_candidates` (entry points with no interface test) and `pinning_candidates` (tests on internals). Delete only pinning candidates that pass the kill-set rule.

**P4. Add a cost criterion.** Sort candidates by `call` duration. Report the top-N slow tests with no unique coverage or kills as `review_candidates` with time saved. This addresses the user's speed question directly.

**P5. Add an order and flake gate before removal.** Run the suite with random order (pytest-randomly, pytest-random-order's `--random-order`, Jest `--randomize` (Jest 29.2+), or Stryker's built-in requirement). A removal candidate that fails under random order is order-dependent and must not be removed silently. Use the existing flake retry (SKILL.md:118, 176) as the first check.

**P6. Make Phase C cost data a first-class input.** The ledger already has `spring.baseline` (springboot.md:73-81). Store per-test `call` duration next to it so Phase B and Phase C use the same measurement. Keep the wall-time gate informational as now (SKILL.md:193).

**P7. Document the dependency.** Add `engineering/testing → engineering/refactor-tests` (path convention) to `docs/agents/skill-dependencies.md`. Add `refactor-tests → codebase-design`. Keep the seam definition identical to `tdd/SKILL.md:20`.

**P8. Fix reference notes.** `provenance-marks-value.md` is an analysis note with a broken location claim ("repo root"). It is not used by the skill. Leave it alone or move it. It does not affect refactor-tests behaviour.

### 4.3 Proposed workflow

1. Discovery and baseline (existing Steps 1-3), plus per-test `call` duration in baseline.
2. Evidence pass (new): coverage per test, kill matrix where the tool supports it, random-order run.
3. Layout (Phase A, unchanged).
4. Classify each test by seam (Phase B, new step).
5. Apply removal rules (section 2.3). Coverage subset alone goes to review.
6. Parametrize clusters (existing), but check kill sets before merging: two tests that kill different mutants should not merge into one without keeping both kill sets.
7. Validate (existing), with the post-layout baseline and flake retry.
8. Report: removals, review candidates with time saved, add candidates, pinning candidates, and per-test durations before and after.

### 4.4 Risks

- Coverage contexts are slow and disable sysmon on Python 3.14+ (section 1.1). Run the evidence pass once, not per phase.
- Per-test coverage for Go and Rust multiplies run time by the test count. Restrict to candidates, or to tests flagged as slow.
- Mutation runs are costly. Use `perTest` coverage analysis to limit runs (Stryker), and treat kill-matrix data as optional. Without it, the skill still removes only exact duplicates and trivially true tests.
- OpenClover needs no parallel test execution and may miss JUnit 5 tests (unverified). Confirm before use.

---

## Sources

Official docs and source repos:
- https://github.com/nedbat/coveragepy/blob/master/doc/contexts.rst
- https://coverage.readthedocs.io/en/latest/contexts.html
- https://coverage.readthedocs.io/en/latest/commands/cmd_json.html
- https://coverage.readthedocs.io/en/latest/api_coveragedata.html
- https://coverage.readthedocs.io/en/latest/dbschema.html
- https://github.com/nedbat/coveragepy/blob/master/coverage/jsonreport.py
- https://github.com/nedbat/coveragepy/blob/master/doc/config.rst
- https://pytest-cov.readthedocs.io/en/latest/contexts.html
- https://pytest-cov.readthedocs.io/en/latest/xdist.html
- https://github.com/pytest-dev/pytest-cov/blob/master/src/pytest_cov/plugin.py
- https://github.com/pytest-dev/pytest-cov/blob/master/src/pytest_cov/engine.py
- https://github.com/pytest-dev/pytest-cov/blob/master/tests/test_pytest_cov.py
- https://github.com/pytest-dev/pytest/blob/main/src/_pytest/runner.py
- https://docs.pytest.org/en/stable/how-to/usage.html
- https://docs.pytest.org/en/stable/how-to/output.html
- https://github.com/numirias/pytest-json-report
- https://mutmut.readthedocs.io/en/latest/
- https://github.com/boxed/mutmut
- https://github.com/sixty-north/cosmic-ray
- https://github.com/tarpas/pytest-testmon
- https://github.com/pytest-dev/pytest-randomly
- https://github.com/pytest-dev/pytest-random-order
- https://www.jacoco.org/jacoco/trunk/doc/faq.html
- https://www.jacoco.org/jacoco/trunk/doc/agent.html
- https://www.jacoco.org/jacoco/trunk/doc/dump-mojo.html
- https://openclover.org/doc/manual/latest/maven--using-distributed-per-test-coverage.html
- https://openclover.org/doc/manual/4.2.0/general--what-is-distributed-per-test-coverage.html
- https://openclover.org/doc/manual/latest/maven--using-test-optimization.html
- https://kotlin.github.io/kotlinx-kover/gradle-plugin/
- https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html
- https://docs.gradle.org/current/userguide/java_testing.html
- https://docs.junit.org/6.0.3/advanced-topics/junit-platform-reporting.html
- https://pitest.org/quickstart/maven/
- https://pitest.org/quickstart/incremental_analysis/
- https://github.com/hcoles/pitest/blob/master/pitest-maven/src/main/java/org/pitest/maven/PitMojo.java
- https://github.com/hcoles/pitest/blob/master/pitest-entry/src/main/java/org/pitest/mutationtest/report/xml/XMLReportListener.java
- https://github.com/pitest/pitest-junit5-plugin
- https://gradle-pitest-plugin.solidsoft.info/
- https://docs.arcmutate.com/docs/kotlin.html
- https://docs.develocity.ai/predictive-test-selection/
- https://github.com/TestingResearchIllinois/starts
- https://github.com/gliga/ekstazi
- https://jestjs.io/docs/cli
- https://jestjs.io/docs/configuration
- https://vitest.dev/guide/cli.html
- https://nodejs.org/api/test.html
- https://stryker-mutator.io/docs/stryker-js/configuration/
- https://stryker-mutator.io/docs/stryker-net/configuration/
- https://stryker-mutator.io/docs/stryker-net/reporters/
- https://raw.githubusercontent.com/stryker-mutator/mutation-testing-elements/master/packages/report-schema/src/mutation-testing-report-schema.json
- https://raw.githubusercontent.com/stryker-mutator/mutation-testing-elements/master/packages/metrics/src/model/test-model.ts
- https://pkg.go.dev/cmd/go/internal/test
- https://pkg.go.dev/cmd/test2json
- https://pkg.go.dev/cmd/covdata
- https://go.dev/doc/build-cover
- https://github.com/gotestyourself/gotestsum
- https://gremlins.dev/latest/usage/commands/unleash/
- https://github.com/avito-tech/go-mutesting
- https://github.com/gtramontina/ooze
- https://github.com/taiki-e/cargo-llvm-cov
- https://doc.rust-lang.org/rustc/instrument-coverage.html
- https://nexte.st/docs/machine-readable/junit/
- https://nexte.st/docs/machine-readable/libtest-json/
- https://doc.rust-lang.org/rustc/tests/index.html
- https://mutants.rs/mutants-out.html
- https://github.com/sourcefrog/cargo-mutants/blob/main/src/outcome.rs
- https://mutants.rs/nextest.html
- https://github.com/coverlet-coverage/coverlet/blob/master/Documentation/VSTestIntegration.md
- https://learn.microsoft.com/en-us/dotnet/core/testing/microsoft-testing-platform-extensions-code-coverage
- https://learn.microsoft.com/en-us/dotnet/core/additional-tools/dotnet-coverage
- https://github.com/microsoft/vstest/blob/main/docs/report.md
- https://github.com/simplecov-ruby/simplecov
- https://github.com/mbj/mutant/blob/main/docs/test-selection.md
- https://docs.phpunit.de/en/12.5/code-coverage.html
- https://infection.github.io/guide/command-line-options.html
- https://bazel.build/reference/be/common-definitions
- https://abseil.io/resources/swe-book/html/ch11.html
- https://abseil.io/resources/swe-book/html/ch12.html
- https://testdesiderata.com/ (summary)
- https://martinfowler.com/bliki/UnitTest.html (summary)
- https://martinfowler.com/bliki/TestPyramid.html (summary)
- https://github.com/johnousterhout/aposd-vs-clean-code/blob/main/README.md
- https://www.informit.com/articles/article.aspx?p=359417&seqNum=2
- https://www.informit.com/articles/article.aspx?p=359417&seqNum=3
- https://www.artima.com/weblogs/viewpost.jsp?thread=126923 (summary)

Academic:
- Harrold, Gupta, Soffa (1993), TOSEM 2(3): https://doi.org/10.1145/152388.152391
- Yoo and Harman (2012), STVR 22(2): https://doi.org/10.1002/stvr.430
- Rothermel, Harrold, Ostrin, Hong (1998), ICSM: https://doi.org/10.1109/ICSM.1998.738487
- Rothermel, Harrold, von Ronne, Hong (2002), STVR 12(4): https://doi.org/10.1002/stvr.256
- Wong, Horgan, London, Mathur (1995), ICSE: https://doi.org/10.1145/225014.225018
- Jeffrey and Gupta (2007), TSE 33(2): https://doi.org/10.1109/TSE.2007.18
- Shi, Gyori, Gligoric, Zaytsev, Marinov (2014), FSE: https://doi.org/10.1145/2635868.2635921
- Inozemtseva and Holmes (2014), ICSE: https://doi.org/10.1145/2568225.2568271
- Just, Jalali, Inozemtseva, Ernst, Holmes, Fraser (2014), FSE: https://doi.org/10.1145/2635868.2635929
- Papadakis, Shin, Yoo, Bae (2018), ICSE: https://doi.org/10.1145/3180155.3180183
- Ammann, Delamaro, Offutt (2014), ICST: https://doi.org/10.1109/ICST.2014.13
- Luo, Hariri, Eloussi, Marinov (2014), FSE: https://doi.org/10.1145/2635868.2635920
- Lam, Oei, Shi, Marinov, Xie (2019), iDFlakies, ICST: https://doi.org/10.1109/ICST.2019.00038
- van Deursen, Moonen, van den Bergh, Kok (2001), XP: https://homepages.cwi.nl/~leon/papers/xp2001/xp2001.pdf (not retrieved; abstract secondary)
- Meszaros (2007), *xUnit Test Patterns*: http://xunitpatterns.com/Fragile%20Test.html (secondary)
- Winters, Manshreck, Wright (2020), *Software Engineering at Google*: https://abseil.io/resources/swe-book/html/ch12.html

Repo files:
- skills/engineering/refactor-tests/SKILL.md (lines 68, 76-86, 118, 133-160, 176, 183-193)
- skills/engineering/refactor-tests/reference/patterns.md (lines 69-75, 91-101)
- skills/engineering/refactor-tests/reference/springboot.md (lines 73-81)
- skills/engineering/codebase-design/SKILL.md (lines 16, 20, 22, 63-65)
- skills/engineering/improve-codebase-architecture/DEEPENING.md (lines 29, 34-37)
- skills/engineering/improve-codebase-architecture/DESIGN-IT-TWICE.md (line 42)
- skills/engineering/improve-codebase-architecture/SKILL.md (line 33)
- skills/engineering/tdd/SKILL.md (lines 14, 20, 26)
- skills/engineering/testing/SKILL.md (line 29)
- docs/agents/skill-dependencies.md
