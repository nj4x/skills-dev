# Research: Which Python evidence commands hold up on a real project?

**Date:** 2026-10-15
**Issue:** nj4x/skills-dev#113 (parent #112, blocks #114)
**Scope:** Verify the Python row of the evidence command table in `docs/research/refactor-tests-coverage-speed-deep-modules.md` (section 1.1 and section 4.2). Primary sources only: coverage.py, pytest-cov, pytest-xdist, pytest, pytest-randomly, pytest-random-order, and pytest-json-report docs and source. Where the docs are silent, a throwaway experiment in `/tmp/pyev` was run.

Verification notes: doc and source text was downloaded raw from GitHub (`raw.githubusercontent.com`, default branch, fetched 2026-10-15) and read directly, not through a summarizer. Line numbers refer to those files on that date. Release data comes from the PyPI JSON API (`https://pypi.org/pypi/<name>/json`) and the GitHub REST API. Anything marked **(experiment)** was observed in the run described in section 0 and is not stated in any doc.

---

## Summary

1. `--cov-context=test` works under pytest-xdist. The docs do not say so, but pytest-cov's own test suite runs its context test with `-n 1`, `-n 2` and `-n 3`, and the experiment produced identical contexts with and without `-n 3`.
2. On Python 3.14+ the evidence pass **must** force the C tracer: `[run] core = ctrace` (or `COVERAGE_CORE=ctrace`). pytest-cov switches contexts through the API, so coverage.py does not fall back to ctrace on its own. With the default sysmon core, coverage 7.16.2 only warns, and the experiment silently lost a whole test context.
3. `coverage json --show-contexts` adds a `contexts` object per file: line number (string) to a list of context labels. Branch arcs carry no contexts. The function and class region entries repeat the whole-file map, so read only the file-level `contexts`. Per-test arcs need the `CoverageData` API.
4. For per-test `call` duration, use a JSON source keyed by pytest node id: pytest-json-report (`tests[].call.duration`) or a 15-line `pytest_runtest_logreport` hook. `junit_duration_report=call` works but loses precision (3 decimals) and does not give node ids. `--durations` is console-only.
5. pytest-randomly is the better-maintained random-order plugin (5.0.0 on 2026-09-01, active maintainer Adam Johnson). pytest-random-order is alive but quieter (1.2.0 on 2025-06-22). Neither changes context labels, but random order (and xdist) moves shared-fixture coverage between tests' `|setup` contexts. Use only `|run` contexts for subsumption.

Corrected Python row for the section 4.2 table:

| Language | Coverage per test | Timing per test | Notes |
|---|---|---|---|
| Python | `pytest -p no:randomly --cov=<pkg> --cov-branch --cov-context=test`, then `coverage json --show-contexts`; per-test arcs via `CoverageData.set_query_contexts()` + `arcs()` | `pytest -p no:randomly --json-report --json-report-file=<f>` (read `tests[].call.duration`), or a `pytest_runtest_logreport` hook | Set `[run] core = ctrace` on every Python version (required on 3.14+). xdist is fine for contexts. Use `|run` contexts only. Run timing without `--cov`. |

---

## 0. Experiment setup

Throwaway package in `/tmp/pyev` (not in this repo). Environment created with:

```sh
uv venv -p 3.14 .venv
uv pip install -p .venv/bin/python pytest pytest-cov pytest-xdist coverage pytest-randomly pytest-random-order pytest-json-report
```

Versions installed (`uv pip list`): Python 3.14.6 (macOS arm64), coverage 7.16.2, pytest 9.1.1, pytest-cov 7.1.0, pytest-xdist 3.8.0, pytest-randomly 5.0.0, pytest-random-order 1.2.0, pytest-json-report 1.5.0, pytest-metadata 3.1.1.

Code under test, `pkg/calc.py`:

```python
import time


def add(a, b):
    return a + b


def div(a, b):
    if b == 0:
        raise ZeroDivisionError("b is zero")
    return a / b


def slow_square(x):
    time.sleep(0.2)
    return x * x
```

Tests, `tests/test_calc.py`: `test_add`, `test_div` parametrized with `(4, 2, 2)` and `(9, 3, 3)`, `test_div_zero`, and `test_slow_square`, which uses a fixture that sleeps 0.3 s in setup and 0.1 s in teardown. That gives five test ids. `pytest.ini` sets `testpaths = tests` and `pythonpath = .`.

Contexts were read with `CoverageData(".coverage").read()`, then `measured_contexts()` and `contexts_by_lineno(file)`.

---

## 1. Does `--cov-context=test` work under pytest-xdist?

**Yes.**

Docs: the pytest-cov xdist page (`docs/xdist.rst`) covers combined coverage for `load` and `each` modes and does not mention contexts (https://github.com/pytest-dev/pytest-cov/blob/master/docs/xdist.rst). The contexts page (`docs/contexts.rst`) does not mention xdist either (https://github.com/pytest-dev/pytest-cov/blob/master/docs/contexts.rst). So the docs are silent.

Source:
- `pytest_sessionstart` starts a `DistWorker` controller on each worker and then registers `TestContextPlugin` when `--cov-context=test` is set. The registration is outside the worker/controller branch, so it runs on workers too (`src/pytest_cov/plugin.py:290-298`, https://github.com/pytest-dev/pytest-cov/blob/master/src/pytest_cov/plugin.py).
- `TestContextPlugin` calls `cov.switch_context(f'{item.nodeid}|{when}')` in `pytest_runtest_setup`, `pytest_runtest_call` and `pytest_runtest_teardown`, with `when` one of `setup`, `run`, `teardown` (`plugin.py:433-450`).
- pytest-cov's own `test_contexts` is decorated with `@xdist_params`, which parametrizes `opts` as `''`, `'-n 1'`, `'-n 2'`, `'-n 3'` (`tests/test_pytest_cov.py:148-155` and `1985-1993`, https://github.com/pytest-dev/pytest-cov/blob/master/tests/test_pytest_cov.py).

**(experiment)** With `core = ctrace` (see section 2):

```sh
.venv/bin/python -m pytest -p no:randomly -n 3 --cov=pkg --cov-branch --cov-context=test -q
# 5 passed in 1.07s
```

The worker data was combined into one `.coverage` file. `measured_contexts()` returned the same six contexts as the serial run (`''` plus five `...|run` contexts), and `contexts_by_lineno` matched line for line. Only the order inside each list differed.

Caveat: with xdist, each worker builds its own module- and session-scoped fixtures. Their coverage lands in the `|setup` context of whichever test triggers them first on that worker. See section 5.3.

---

## 2. Which coverage core on Python 3.14+?

**Set `core = ctrace` explicitly.** Exact setting, any of:

```ini
# .coveragerc
[run]
core = ctrace
```

```toml
# pyproject.toml
[tool.coverage.run]
core = "ctrace"
```

```sh
# environment variable
COVERAGE_CORE=ctrace pytest --cov=<pkg> --cov-context=test
```

All three were verified in the experiment (each produced all six contexts and no warning).

Docs:
- `[run] core` takes `ctrace`, `sysmon` or `pytrace`. sysmon is "the default in Python 3.14+" and "does not yet support plugins, dynamic contexts, or some concurrency libraries". The setting exists in config since 7.9 and was previously only the `COVERAGE_CORE` environment variable (`doc/config.rst:361-380`, https://github.com/coveragepy/coveragepy/blob/main/doc/config.rst).
- 7.9.1 (2025-06-13): "On Python 3.14+, the 'sysmon' core is now the default if it's supported for your configuration" (`CHANGES.rst:883-885`, https://github.com/coveragepy/coveragepy/blob/main/CHANGES.rst).
- 7.11.1 (2025-11-07): if the core is not specified and defaults to sysmon, but other settings conflict, "the 'ctrace' core will be used instead with no warning". If sysmon is requested explicitly and settings conflict, an error is raised (`CHANGES.rst:622-634`).
- 7.15.3 (2026-08-02): "using the context API as pytest-cov does, contexts would be silently dropped. Now a warning is issued" (`CHANGES.rst:198-202`).
- Warning text: "Dynamic contexts aren't supported with core=sysmon; context data may be incomplete (no-sysmon-context)". The docs say "Context data will be lost. Change your configuration to use the ctrace core" (`doc/messages.rst:164-167`, https://github.com/coveragepy/coveragepy/blob/main/doc/messages.rst).

Why the automatic fallback does not help: coverage.py checks for conflicts using its own configuration (`[run] dynamic_context`). pytest-cov does not set that. It calls `Coverage.switch_context()` after the core is already chosen (`plugin.py:448-450`; coverage `doc/contexts.rst:61-69`, https://github.com/coveragepy/coveragepy/blob/main/doc/contexts.rst). pytest-cov even warns against setting `dynamic_context = test_function` alongside `--cov-context` (`src/pytest_cov/engine.py:243-248` and `293-297`, https://github.com/pytest-dev/pytest-cov/blob/master/src/pytest_cov/engine.py).

**(experiment)** Active core, recorded with `COVERAGE_DEBUG=sys COVERAGE_DEBUG_FILE=<f>` (the `core:` line):

| Command | Active core | Contexts recorded |
|---|---|---|
| `pytest --cov=pkg --cov-context=test` (no config) | `SysMonitor` | 5 of 6: **`test_div[9-3-3]|run` missing**, plus warning `no-sysmon-context` |
| same, with `COVERAGE_CORE=ctrace` or `[run] core = ctrace` | `CTracer` | all 6 |
| `coverage run --rcfile=<f> -m pytest` with `[run] dynamic_context = test_function`, no core | `CTracer` (automatic fallback) | complete, but labels are `test_calc.test_div` etc.: no node ids, both parametrize cases merged into one context |

The sysmon failure is real data loss, not a cosmetic warning. The second parametrize case of `test_div` ran the same lines as the first, and sysmon recorded nothing for it. A subsumption check would then see no evidence for that test at all.

The warning appears only in pytest's warnings summary, and only once. It is easy to miss in CI logs, so do not rely on it as a gate.

Recommendation: always set `core = ctrace` for the evidence pass, on every Python version. It is a no-op before 3.14 (ctrace was already the default, `config.rst:367-368`) and required on 3.14+.

---

## 3. Exact shape of `coverage json --show-contexts`

Docs: `coverage json` has `--show-contexts` ("Show contexts for covered lines"), `--contexts=REGEX1,REGEX2,...` to filter, `-o OUTFILE` and `--pretty-print` (`doc/commands/cmd_json.rst`, https://github.com/coveragepy/coveragepy/blob/main/doc/commands/cmd_json.rst). The config equivalent is `[json] show_contexts = true` (`doc/config.rst:1017-1021`). The docs do not describe the JSON schema. The source does: `FORMAT_VERSION = 3`, and `reported_file["contexts"] = coverage_data.contexts_by_lineno(analysis.filename)` (`coverage/jsonreport.py:31` and `124`, https://github.com/coveragepy/coveragepy/blob/main/coverage/jsonreport.py).

**(experiment)** Real output from the `-n 3` ctrace run, `coverage json --show-contexts -o cov.json --pretty-print`. Trimmed: the `summary` objects (13 count/percent keys each) and the `functions` and `classes` region maps are elided; everything else is verbatim.

```json
{
    "meta": {
        "format": 3,
        "version": "7.16.2",
        "timestamp": "2026-10-15T23:38:21.495652",
        "branch_coverage": true,
        "show_contexts": true
    },
    "files": {
        "pkg/calc.py": {
            "executed_lines": [1, 4, 5, 8, 9, 10, 11, 14, 15, 16],
            "summary": { "...": "..." },
            "missing_lines": [],
            "excluded_lines": [],
            "contexts": {
                "1": [""],
                "4": [""],
                "8": [""],
                "14": [""],
                "5": ["tests/test_calc.py::test_add|run"],
                "9": [
                    "tests/test_calc.py::test_div_zero|run",
                    "tests/test_calc.py::test_div[9-3-3]|run",
                    "tests/test_calc.py::test_div[4-2-2]|run"
                ],
                "10": ["tests/test_calc.py::test_div_zero|run"],
                "11": [
                    "tests/test_calc.py::test_div[9-3-3]|run",
                    "tests/test_calc.py::test_div[4-2-2]|run"
                ],
                "15": ["tests/test_calc.py::test_slow_square|run"],
                "16": ["tests/test_calc.py::test_slow_square|run"]
            },
            "executed_branches": [[9, 10], [9, 11]],
            "missing_branches": [],
            "functions": { "add": { "...": "..." }, "div": { "...": "..." }, "slow_square": { "...": "..." }, "": { "...": "..." } },
            "classes": { "": { "...": "..." } }
        }
    },
    "totals": { "...": "..." }
}
```

Shape rules, all observed in this output:

- `files.<path>.contexts` is an object. Keys are line numbers **as strings**. Values are lists of context labels. Lines are not sorted numerically, and list order is not stable between runs.
- Only executed lines appear. A file with no executed lines has `"contexts": {}`.
- The label format is `<pytest node id>|<phase>`, phase `setup`, `run` or `teardown`. This matches the pytest-cov docs (`docs/contexts.rst`). Parametrize ids are part of the node id, so each case is its own context (same doc).
- `""` is the empty context: code run at import time or between tests (coverage `doc/contexts.rst:127-131`).
- `executed_branches` and `missing_branches` are plain `[from, to]` pairs with **no context information**.
- **Region entries repeat the whole-file map.** Each entry under `functions` and `classes` has its own `contexts` key, but its content is the full file map (for example, `functions.add.contexts` also lists lines 9 to 16). The cause is `make_region_data`, which calls `contexts_by_lineno(narrowed_analysis.filename)` on the whole file (`coverage/jsonreport.py:181`). Read only the file-level `contexts`. No matching upstream issue was found when searching `coveragepy/coveragepy` issues for "contexts json".

Per-test arcs: the JSON has none. Use the `CoverageData` API: `set_query_contexts()`, then `lines()` and `arcs()` (https://coverage.readthedocs.io/en/latest/api_coveragedata.html). **(experiment)**:

```python
import re
from coverage import CoverageData

d = CoverageData(".coverage")
d.read()
for ctx in sorted(d.measured_contexts()):
    if not ctx:
        continue
    d.set_query_contexts([f"^{re.escape(ctx)}$"])  # regexes, so anchor and escape
    for f in d.measured_files():
        print(ctx, sorted(d.lines(f) or []), sorted(d.arcs(f) or []))
```

Output for `pkg/calc.py`:

```text
tests/test_calc.py::test_add|run lines= [5] arcs= [(-4, 5), (5, -4)]
tests/test_calc.py::test_div[4-2-2]|run lines= [9, 11] arcs= [(-8, 9), (9, 11), (11, -8)]
tests/test_calc.py::test_div[9-3-3]|run lines= [9, 11] arcs= [(-8, 9), (9, 11), (11, -8)]
tests/test_calc.py::test_div_zero|run lines= [9, 10] arcs= [(-8, 9), (9, 10), (10, -8)]
tests/test_calc.py::test_slow_square|run lines= [15, 16] arcs= [(-14, 15), (15, 16), (16, -14)]
```

Negative line numbers are function entry and exit arcs. Escape the context string: node ids contain `[`, `]` and `.`, which are regex metacharacters.

---

## 4. Per-test `call` duration

Options compared, all run **(experiment)** on the same suite. `test_slow_square` has 0.3 s setup, 0.2 s call, 0.1 s teardown.

| Source | Command | Output for `test_slow_square` | Key | Precision |
|---|---|---|---|---|
| `--durations` | `pytest --durations=0 --durations-min=0` | console lines `0.31s setup`, `0.21s call`, `0.10s teardown` | node id, in text | 2 decimals, console only |
| JUnit, default | `pytest --junitxml=<f>` | `time="0.615"` (setup + call + teardown) | `classname="tests.test_calc"` + `name` | 3 decimals |
| JUnit, call | `pytest --junitxml=<f> -o junit_duration_report=call` | `time="0.205"` | same | 3 decimals |
| pytest-json-report | `pytest --json-report --json-report-file=<f>` | `"call": {"duration": 0.20519066601991653, "outcome": "passed"}` | `nodeid` | full float |
| Hook plugin (below) | `pytest -p calltime` | `"duration": 0.20515799999702722` | `nodeid` | full float |

Docs:
- `junit_duration_report` takes `total` (default: "setup, call, and teardown times") or `call` ("only call times, excluding setup and teardown"), added in pytest 4.1 (`doc/en/reference/reference.rst:1740-1763`, https://github.com/pytest-dev/pytest/blob/main/doc/en/reference/reference.rst). pytest notes the JUnit spec suggests total time, hence the default (`doc/en/how-to/output.rst:623-643`, https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/output.rst).
- `--durations=N` shows the N slowest "setup/test durations (N=0 for all)". `--durations-min` defaults to 0.005 s, or 0.0 with `-vv` (`reference.rst:3229-3237`; `doc/en/how-to/usage.rst:137-150`, https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/usage.rst). It writes to the terminal summary only.
- pytest-json-report: each test has `nodeid`, `outcome`, and a stage object per `setup`, `call`, `teardown` with `duration` and `outcome`. A stage is "absent if stage didn't run" (`README.md:309-351`, https://github.com/numirias/pytest-json-report/blob/master/README.md).

Why JUnit is the weaker choice for evidence:
- The JUnit `classname` is a dotted module path (`tests.test_calc`), not the file path in the coverage context label (`tests/test_calc.py`). Joining needs a lossy rewrite, which breaks for nested classes and for paths that contain dots. **(experiment)**
- 3 decimals: every fast test reads `0.000`, so fast tests cannot be ranked. **(experiment)**

pytest-json-report caveat: last release 1.5.0 on 2022-03-15 and last push to GitHub on 2023-07-31 (PyPI JSON API; GitHub API `repos/numirias/pytest-json-report`). It still worked on pytest 9.1.1 and under `-n 2` (stage durations reported for all five tests, no warnings with `-W default`) **(experiment)**. That is no guarantee for later pytest releases.

Zero-dependency alternative, a local plugin built on the standard `pytest_runtest_logreport` hook. **(experiment)**: it produced the same node ids and durations under serial and `-n 2` runs:

```python
# calltime.py, load with: pytest -p calltime  (module must be importable)
import json
import os

_rows = {}


def pytest_runtest_logreport(report):
    if report.when == "call":
        _rows[report.nodeid] = {"duration": report.duration, "outcome": report.outcome}


def pytest_sessionfinish(session):
    # Under xdist, reports from workers are replayed on the controller,
    # so only the controller (no workerinput) writes the file.
    if hasattr(session.config, "workerinput"):
        return
    with open(os.environ.get("CALLTIME_FILE", "calltime.json"), "w") as f:
        json.dump(_rows, f, indent=1, sort_keys=True)
```

Parse example joining coverage and timing into one evidence map. **(experiment)** Command:

```sh
pytest -p no:randomly --cov=pkg --cov-branch --cov-context=test --json-report --json-report-file=report.json
coverage json --show-contexts -o cov.json -q
python evidence.py
```

```python
# evidence.py
import json
from collections import defaultdict

cov = json.load(open("cov.json"))
rep = json.load(open("report.json"))

lines_by_test = defaultdict(set)
for path, f in cov["files"].items():
    for lineno, ctxs in f.get("contexts", {}).items():  # file level only
        for ctx in ctxs:
            if not ctx:
                continue  # empty context: import time / between tests
            nodeid, _, phase = ctx.rpartition("|")
            if phase == "run":  # setup/teardown are order dependent
                lines_by_test[nodeid].add(f"{path}:{lineno}")

evidence = {
    t["nodeid"]: {
        "call_s": round(t.get("call", {}).get("duration", 0.0), 6),
        "lines": sorted(lines_by_test.get(t["nodeid"], ())),
    }
    for t in rep["tests"]
}
print(json.dumps(evidence, indent=1))
```

Output (excerpt):

```json
"tests/test_calc.py::test_div[4-2-2]": {"call_s": 8.9e-05, "lines": ["pkg/calc.py:11", "pkg/calc.py:9"]},
"tests/test_calc.py::test_div[9-3-3]": {"call_s": 7.6e-05, "lines": ["pkg/calc.py:11", "pkg/calc.py:9"]},
"tests/test_calc.py::test_slow_square": {"call_s": 0.205251, "lines": ["pkg/calc.py:15", "pkg/calc.py:16"]}
```

The json-report `nodeid` equals the part of the coverage context label before `|`, so the join is exact. Use `rpartition("|")`: a parametrize id could itself contain `|`.

Recommendation (inference, not from a source): take timing from a separate run without `--cov`. Tracing adds overhead to every executed line, so durations measured under coverage are inflated unevenly, and the slow-test ranking can shift.

---

## 5. Which random-order plugin, and does it interact with contexts?

### 5.1 Maintenance

| | pytest-randomly | pytest-random-order |
|---|---|---|
| Latest release | 5.0.0, 2026-09-01 | 1.2.0, 2025-06-22 |
| Previous releases | 4.1.0 (2026-04-20), 4.0.1 (2025-09-12), 4.0.0 (2025-09-10) | 1.1.1 (2024-01-20), 1.1.0 (2022-12-03), 1.0.4 (2018-11-30) |
| Python | `>=3.10` (unreleased: "Drop Python 3.10 support") | `>=3.9` |
| Maintainer | Adam Johnson (`adamchainz`), commits up to 2026-10-04 | Jazeps Basko (PyPI author and maintainer); recent commits mostly from bots, last human commits 2026-04-14/15 by other contributors |
| Repo | https://github.com/pytest-dev/pytest-randomly, 722 stars, last push 2026-10-05 | https://github.com/pytest-dev/pytest-random-order (the old `jbasko/pytest-random-order` redirects here), 79 stars, last push 2026-10-12 |

Sources: PyPI JSON API for `pytest-randomly` and `pytest-random-order` (release dates, `requires_python`, author/maintainer); GitHub API `repos/<owner>/<repo>` and `repos/<owner>/<repo>/commits`; pytest-randomly `CHANGELOG.rst` (https://github.com/pytest-dev/pytest-randomly/blob/main/CHANGELOG.rst).

**pytest-randomly is better maintained.** 5.0.0 also fixed a reproducibility bug: the shuffle now runs in a hook wrapper before other plugins' `pytest_collection_modifyitems`, so "the final order is reproducible from the seed alone". Before that, the same seed could give different orders in different environments (`CHANGELOG.rst`, 5.0.0 entry, PR #746). 5.0.0 requires pytest 8+ (same entry).

### 5.2 Flags

pytest-randomly is **on by default once installed** (README: "All of these features are on by default but can be disabled with flags", https://github.com/pytest-dev/pytest-randomly/blob/main/README.rst):
- `--randomly-seed=<int>` or `--randomly-seed=last` to reproduce. The seed is printed as `Using --randomly-seed=<n>`.
- `--randomly-dont-reorganize` turns off shuffling. `--randomly-dont-reset-seed` turns off the per-test `random.seed()` reset.
- `-p no:randomly` disables the plugin.
- It also resets `random.seed()` before each test's setup, run and teardown, and resets factory boy, Faker, Model Bakery, NumPy's legacy random state and Polyfactory. It "works with pytest-xdist".

pytest-random-order is **off by default** (`--help`: "Randomise test order (by default, it is disabled)"; README, https://github.com/pytest-dev/pytest-random-order/blob/master/README.rst):
- `--random-order` turns it on with the default bucket `module`.
- `--random-order-bucket={global,package,module,class,parent,grandparent,none}` sets the scope. Tests from one bucket are never interleaved with another bucket.
- `--random-order-seed=<n>` reproduces a run. The seed is printed as `Using --random-order-seed=<n>`.
- Marker `pytest.mark.random_order(disabled=True)` on a module or class keeps its order.
- It calls `random.seed(seed)` once, when it shuffles at collection time, and does not reset the seed per test (`random_order/shuffler.py:41-42`, installed 1.2.0).

Both plugins pass the controller's seed to xdist workers, so all workers collect the same order: random-order reads `config.workerinput["random_order_seed"]` (`random_order/plugin.py:45-54`), and pytest-randomly registers its own `XdistHooks` (`pytest_randomly/__init__.py:120-121`). Both ran cleanly under `-n 2`/`-n 3` with `--cov-context=test` **(experiment)**.

Install only one. Both shuffle in `pytest_collection_modifyitems` (`pytest_randomly/__init__.py:209`, `random_order/plugin.py:66`, installed versions), so two shufflers on one run give an order that neither seed alone reproduces (inference).

### 5.3 Interaction with coverage contexts

Context labels do not depend on order: they are `nodeid|phase` (pytest-cov `plugin.py:448-450`). **(experiment)** Runs with pytest-randomly (seed 1307714350), with `--random-order` (bucket `module`, seed 653697), and with pytest-randomly under `-n 2` each produced the same six contexts as the fixed-order run.

But **what lands in the `|setup` contexts does depend on order.** A module- or session-scoped fixture runs once, inside the setup phase of whichever test needs it first. **(experiment)** A module-scoped fixture `conn` calls `pkg.db.connect()` and is used by `test_open` and `test_open_again`:

```text
--randomly-seed=1  {1: [''], 2: ['tests/test_db.py::test_open_again|setup'], 3: ['tests/test_db.py::test_open_again|setup']}
--randomly-seed=2  {1: [''], 2: ['tests/test_db.py::test_open_again|setup'], 3: ['tests/test_db.py::test_open_again|setup']}
--randomly-seed=3  {1: [''], 2: ['tests/test_db.py::test_open|setup'],       3: ['tests/test_db.py::test_open|setup']}
```

Under seeds 1 and 2, `test_open` appears to cover nothing in `pkg/db.py`. xdist has the same effect, because each worker builds its own fixtures (section 1). Consequences for refactor-tests:

- Build per-test coverage from `|run` contexts only. Treat `|setup` and `|teardown` coverage as fixture-owned, not test-owned.
- Run the coverage pass in a fixed order (`-p no:randomly`; pytest-random-order is already off unless `--random-order` is passed) so that the evidence can be reproduced. Run the order gate (P5 in the parent note) as a separate pass.
- pytest-randomly's per-test `random.seed()` reset can change which lines code driven by randomness executes, compared with a run without the plugin (README, features list). That is one more reason to pin the evidence pass with `-p no:randomly`.

---

## 6. Changes to make in the parent note

For `docs/research/refactor-tests-coverage-speed-deep-modules.md`:

- Section 1.1, xdist caveat: replace "Run the evidence pass without xdist" with "xdist works (pytest-cov tests it with `-n 1..3`). Use `|run` contexts only, because fixture setup coverage moves between workers."
- Section 1.1, sysmon caveat: the `core = ctrace` advice is now documented, not only inferred (`doc/messages.rst:164-167`). Add that the fallback to ctrace does not apply to pytest-cov, and that sysmon really drops contexts (section 2).
- Section 1.1, export: add that branch arcs carry no contexts in JSON, that region-level `contexts` repeat the file map, and that per-test arcs need `set_query_contexts()`.
- Section 1.1, timing: prefer node-id-keyed JSON (pytest-json-report or the hook) over JUnit. Take timing from a run without `--cov`.
- Section 1.1, order: the pytest-random-order repo is now `pytest-dev/pytest-random-order` (redirect from `jbasko/...`). Prefer pytest-randomly.
- Section 4.2: replace the Python row with the corrected row in the Summary above.

---

## Sources

coverage.py (https://github.com/coveragepy/coveragepy, default branch, fetched 2026-10-15; release 7.16.2 used in the experiment):
- `doc/config.rst:361-380` (`[run] core`), `:1017-1021` (`[json] show_contexts`): https://github.com/coveragepy/coveragepy/blob/main/doc/config.rst
- `doc/messages.rst:164-167` (`no-sysmon-context`): https://github.com/coveragepy/coveragepy/blob/main/doc/messages.rst
- `doc/contexts.rst:61-69`, `:120-131`: https://github.com/coveragepy/coveragepy/blob/main/doc/contexts.rst
- `doc/commands/cmd_json.rst`: https://github.com/coveragepy/coveragepy/blob/main/doc/commands/cmd_json.rst
- `CHANGES.rst` entries 7.9.1, 7.11.1, 7.15.3: https://github.com/coveragepy/coveragepy/blob/main/CHANGES.rst
- `coverage/jsonreport.py:31`, `:124`, `:181`: https://github.com/coveragepy/coveragepy/blob/main/coverage/jsonreport.py
- CoverageData API: https://coverage.readthedocs.io/en/latest/api_coveragedata.html

pytest-cov (https://github.com/pytest-dev/pytest-cov, default branch; 7.1.0 used):
- `docs/contexts.rst`: https://github.com/pytest-dev/pytest-cov/blob/master/docs/contexts.rst
- `docs/xdist.rst`: https://github.com/pytest-dev/pytest-cov/blob/master/docs/xdist.rst
- `src/pytest_cov/plugin.py:290-298`, `:433-450`: https://github.com/pytest-dev/pytest-cov/blob/master/src/pytest_cov/plugin.py
- `src/pytest_cov/engine.py:243-248`, `:293-297`: https://github.com/pytest-dev/pytest-cov/blob/master/src/pytest_cov/engine.py
- `tests/test_pytest_cov.py:148-155`, `:1985-1993`: https://github.com/pytest-dev/pytest-cov/blob/master/tests/test_pytest_cov.py

pytest (https://github.com/pytest-dev/pytest, default branch; 9.1.1 used):
- `doc/en/reference/reference.rst:1740-1763` (`junit_duration_report`), `:3229-3237` (`--durations`, `--durations-min`): https://github.com/pytest-dev/pytest/blob/main/doc/en/reference/reference.rst
- `doc/en/how-to/output.rst:623-643`: https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/output.rst
- `doc/en/how-to/usage.rst:137-150`: https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/usage.rst

pytest-xdist 3.8.0 (https://github.com/pytest-dev/pytest-xdist): used as the runner in the experiment; its docs say nothing about coverage contexts.

pytest-json-report (https://github.com/numirias/pytest-json-report; 1.5.0 used):
- `README.md:309-351`: https://github.com/numirias/pytest-json-report/blob/master/README.md

pytest-randomly (https://github.com/pytest-dev/pytest-randomly; 5.0.0 used):
- `README.rst`: https://github.com/pytest-dev/pytest-randomly/blob/main/README.rst
- `CHANGELOG.rst`: https://github.com/pytest-dev/pytest-randomly/blob/main/CHANGELOG.rst
- `src/pytest_randomly/__init__.py:120-121` (installed 5.0.0)

pytest-random-order (https://github.com/pytest-dev/pytest-random-order; 1.2.0 used):
- `README.rst`: https://github.com/pytest-dev/pytest-random-order/blob/master/README.rst
- `random_order/plugin.py:45-54`, `random_order/shuffler.py:41-42` (installed 1.2.0)

Release and maintenance data:
- PyPI JSON API: https://pypi.org/pypi/pytest-randomly/json, https://pypi.org/pypi/pytest-random-order/json, https://pypi.org/pypi/pytest-json-report/json, https://pypi.org/pypi/pytest-cov/json, https://pypi.org/pypi/pytest-xdist/json, https://pypi.org/pypi/coverage/json, https://pypi.org/pypi/pytest/json
- GitHub REST API: `repos/pytest-dev/pytest-randomly`, `repos/pytest-dev/pytest-random-order`, `repos/numirias/pytest-json-report` and their `/commits` endpoints
