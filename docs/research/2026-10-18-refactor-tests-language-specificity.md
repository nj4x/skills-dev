# Which refactor-tests expectations are language-specific

**Date:** 2026-10-18. **Ticket:** nj4x/skills-dev#148 (map #147). **Status:** research; changes no skill.

**Question.** Which expectations in `skills/engineering/refactor-tests/` that a test author can influence are stated for Python only, which have per-language templates, and which are language-neutral? For each, what per-repo fact would a `docs/agents/testing.md` need to hold so a language-neutral `tdd` rule can point at it?

**Sources read.** `skills/engineering/refactor-tests/SKILL.md`, `reference/patterns.md`, the `reference/python/` helper list, `reference/springboot.md` (scope only), `skills/engineering/tdd/SKILL.md:18-24`, `docs/agents/skill-dependencies.md:12-14`. Source report: `pro-trading/.claude/worktrees/782-safety-flag-audit-gaps/docs/research/2026-10-18-test-maintainability-guidance-for-skills.md`, section (b). Worked example: `pro-trading/docs/claude/testing.md` and `pro-trading/CODING_STANDARDS.md`.

**Citations.** Unprefixed paths are relative to `skills/engineering/refactor-tests/` in this repo at commit `7b72ba7`. Paths prefixed `pt:` are relative to the pro-trading checkout root. The source report cites a user-level copy of the skill whose line numbers and some rules differ (here `no-raise-contract` is the first dead-test kind and is kept, not queued). Every skill citation below was re-read in this repo's copy.

## Verdict

Expectations fall into four groups:

- **Per-language template exists:** file layout, test-file naming, integration-directory target, assertion vocabulary. Each has rows for Python, TS/JS, Go and Java/Kotlin (`reference/patterns.md:20-63`, `:91-101`).
- **Language-neutral criterion, per-language editor, Python-only detection:** parametrize cluster and pair. Thresholds are stated neutrally (`SKILL.md:143-144`) and editors exist for five languages (`reference/patterns.md:632-646`), but the scan and apply helpers are Python (`SKILL.md:212`, `:296-299`).
- **Python-only by statement:** per-test coverage evidence, seam signals and pinning classification, the order gate, call-time measurement, the hotspot probe. Other languages are skipped (`SKILL.md:154`, `:186`, `:235`, `:265`).
- **Language-neutral:** assertion strength over line coverage, "judge a table-driven test whole", and the mutation deletion gate (`reference/patterns.md:327-342`, `:614-630`).

For a non-Python repo, `refactor-tests` measures only layout, naming and assertion vocabulary (plus the neutral parts of exact-duplicate and trivially-true checks). A neutral `tdd` rule can state the other expectations, but nothing verifies them there.

## Classification

| # | Expectation | Class | Cite | Tooling dependency |
|---|---|---|---|---|
| 1 | Mirrored or co-located layout | Per-language template | `reference/patterns.md:20-41`: Python `tests/<pkg-path>/test_<name>.py`; TS/JS `<name>.test.<ext>` beside source; Go `<name>_test.go` beside source; Java/Kotlin `src/test/<lang>/<pkg>/<Name>Test.<ext>`. Phase goal `SKILL.md:12` | none |
| 2 | Test-file naming | Per-language template | `reference/patterns.md:56-63` | none; `testing` skill relies on it (`docs/agents/skill-dependencies.md:14`) |
| 3 | One source module per file; cross-cutting goes to integration dir | Per-language template plus per-repo guard | targets `reference/patterns.md:43-52`; guard `:54`; definition `SKILL.md:69`; Go pins in place with a build tag `reference/patterns.md:126-138` | cross-cutting detection uses `search-codebase` |
| 4 | Assertion vocabulary (dead-test) | Per-language template | `reference/patterns.md:91-101`; kinds `:103-110` | kinds use Python idioms (`side_effect=…Error`, `pytest.skip`, `reference/patterns.md:108-109`); scan helper is Python-only (`SKILL.md:212`) |
| 5 | "Does not raise" contract stated | Python-only | `reference/patterns.md:107`: last statement calls `validate(` or a `--raiser` name, or name/docstring says "does not raise" or "must not raise". Kept and counted, never ticketed (`SKILL.md:431`) | `--raiser` flag of `scan_static.py` (`SKILL.md:212`) |
| 6 | Fail-soft test asserts the outcome | Python-only | `reference/patterns.md:108` | `side_effect=…Error` is `unittest.mock` |
| 7 | Assertion in the test body, or in a fixture that asserts | Neutral idea; fixture exemption is Python-only | vocabulary row allows a requested fixture or called helper "defined in the test file or `conftest.py`" (`reference/patterns.md:97`); trivially-true skips such tests (`SKILL.md:140`) | `conftest.py` |
| 8 | Coverage recorded in the test body (`\|run` contexts) | Python-only | `SKILL.md:172`; `reference/patterns.md:608-609` (`no-coverage` exclusion, `covered` from `\|run` only); `reference/patterns.md:490` (seam header runs at import, outside any `\|run`) | `pytest-cov --cov-context=test`, `COVERAGE_CORE=ctrace` (`SKILL.md:159-163`) |
| 9 | Seams declared | Python-only | `reference/patterns.md:456-468`: (a) `__all__`, (b) cross-package import, (c) `public-api`; underscore names never proposed. `SKILL.md:186`: "Python only: other languages get no seams and no pinning classification" | `reference/python/classify_seams.py` |
| 10 | References only seams (interface vs pinning) | Python-only | `reference/patterns.md:470-474`, kinds `:478-488`; `SKILL.md:200` | `classify_seams.py` |
| 11 | Stub collaborators by injection, not patching an imported name | Python-only | `reference/patterns.md:476` (`patch`, `patch.object`, `monkeypatch.setattr`); re-point rule `:484` | `classify_seams.py` |
| 12 | Import the defining module, not a package re-export | Python-only | `SKILL.md:200` | `classify_seams.py` warns |
| 13 | Parametrize, do not copy | Neutral criterion, per-language editors, Python-only detection | thresholds `SKILL.md:143-144`; editors `reference/patterns.md:632-646`; detection `SKILL.md:212`; apply `SKILL.md:296-299` | `scan_static.py`, `apply_param.py` |
| 14 | Order independence | Python-only | `SKILL.md:261-265` ("Python-only for now"; others skipped with `no random-order gate for <lang>`); plugin choice `reference/patterns.md:537-541` | pytest-randomly or pytest-random-order |
| 15 | Cheap call time | Neutral threshold, Python-only measurement | `SKILL.md:142`, `:233` (0.5 s floor, top decile of coverage-subset candidates); hook `SKILL.md:167`; hotspot probe "Python only" `SKILL.md:235`; fix lives "in the test tier (a fixture or stub), never by deleting tests" `SKILL.md:249` | `calltime.py`, `hotspot_profile.py` |
| 16 | Unique assertions, not only unique lines | Language-neutral | `reference/patterns.md:327-342`; mutation gate `reference/patterns.md:614-630` | mutation tool is per repo |
| 17 | Judge a table-driven test whole | Language-neutral (reviewer guidance) | `reference/patterns.md:340` | none |

Rows 11-12 split the report's two items "stub imported collaborators by injection" and "import the defining module"; the report's "instance calls are invisible" (`SKILL.md:200`) is a classifier limit, not an author action, and is left out. Phase C (Spring Boot) changes configuration and source, not how a test is authored (`SKILL.md:339`), so it is out of scope for `tdd`.

## Python-only enforcement, in detail

1. **Per-test coverage, `|run` contexts.** The evidence run is `pytest -p no:randomly --cov=<roots> --cov-branch --cov-context=test` with `COVERAGE_CORE=ctrace`, because on Python 3.14+ the default `sysmon` core silently drops contexts that pytest-cov sets (`SKILL.md:159-163`). `extract_arcs.py` reads only `|run` contexts and exits non-zero when none exist (`SKILL.md:172`). Setup and teardown contexts are fixture-owned and ignored. Other languages get `status: skipped`, reason `no evidence tooling for <lang>` (`SKILL.md:154`). With evidence not `ok`, every evidence-based item is dropped: coverage-subset, cost, hotspot, add candidates and `covered_through_interface` (`SKILL.md:179`, `:197`).
2. **pytest-randomly.** Normal runs pin fixed order with `-p no:randomly` (`SKILL.md:81`; `reference/patterns.md:73`). The gate shuffles one full run with pytest-randomly or pytest-random-order (`SKILL.md:267-271`; `reference/patterns.md:541`). Non-Python: `skipped` (`SKILL.md:265`).
3. **`call_s`.** Comes from the `calltime` pytest plugin in an untraced serial run (`SKILL.md:167`; `reference/patterns.md:609`). Cost, the hotspot probe and the serial-time delta (`SKILL.md:321-328`) all read it.
4. **Seams and pinning.** AST-only and Python-only (`SKILL.md:186`). Signal (a) is `__all__`, a Python construct. Go (capitalized names), Java (`public`) and TS (`export`) have analogues, but the skill defines none.
5. **Evidence-free scan.** Exact duplicate, dead, trivially true, parametrize cluster and pair run in one Python helper (`SKILL.md:212`). `SKILL.md:208` says "using the language's AST parser" and the editor table covers five languages, but `reference/` holds no non-Python scan helper.

## Per-repo fact a `docs/agents/testing.md` would need

For each expectation the neutral `tdd` rule states the intent without a language construct and points to the fact below.

| Expectation | Fact the file holds | Why it cannot be neutral |
|---|---|---|
| Layout, naming, integration dir (1-3) | Source-path to test-path rule per language present; the integration-directory membership rule and the guard that enforces it | Templates differ per language (`reference/patterns.md:20-63`); a repo guard can refuse moves (`:54`) |
| Assertion vocabulary, no-raise, fail-soft (4-7) | The repo's assertion helper names (matching the vocabulary), the documented "does not raise" idiom (raiser name or naming phrase), which shared fixtures assert | Vocabulary is a per-language table (`reference/patterns.md:91-101`); raisers are passed as `--raiser` per repo (`SKILL.md:212`) |
| Stubbing (11) | The sanctioned mechanism (injection point or checked-patch helper) and where it lives | The classifier reads the patch idiom; the replacement is repo-defined |
| Coverage in body (8) | Which shared or autouse fixtures do real work, so the call under test sits in the test function | Only the Python runner records the `run` context |
| Seams (9, 10, 12) | How a seam is declared in this language (`__all__`, `export`, capitalized name, `public`) and where agreed seams are recorded | The three signals are Python constructs (`reference/patterns.md:460-468`) |
| Parametrize (13) | The table-driven idiom of the runner (`@pytest.mark.parametrize`, `test.each`, `t.Run` over a table, `@ParameterizedTest`) | Editors differ per language (`reference/patterns.md:632-646`) |
| Order independence (14) | Whether a shuffler is installed or planned; the shared state tests must not leak (database, environment, cache path, port) | Plugin names are Python; leak sources are repo facts |
| Call-time cost (15) | Cost budget in use (default 0.5 s), the markers that define the slow tier, known expensive setup fixtures | The 0.5 s default is the skill's; markers and fixtures are the repo's |
| Assertion strength (16) | The mutation command, or "none" | Tool is per repo |
| Run commands | Full-suite and single-file commands, so `refactor-tests` resolves the runner | `reference/patterns.md:79-90` detects by marker file and falls back to trial and error |

Suggested section shape: Commands; Layout; Integration-dir rule; Assertion and no-raise idioms; Stubbing; Seam declaration; Parametrize idiom; Markers and slow tier; Shared state; Mutation check.

## Worked example: pro-trading

| Fact needed | Present? | Where |
|---|---|---|
| Run commands | Yes | `pt:docs/claude/testing.md:5-11` (pytest through uv, `-m "not slow"`, selective runner `scripts/covering_tests.py`) |
| Layout rule | No | in neither file; only `reference/patterns.md:24-27` holds it |
| Integration-dir rule | Yes | `pt:docs/claude/testing.md:73` (real database via `integration_db` or a `postgres_*` fixture, or live under `tests/protrading/`; enforced by `tests/test_integration_tier_honesty.py` against `_tier_baseline.txt`) |
| Assertion helpers, "does not raise" idiom | No | absent |
| Stubbing mechanism | Yes | `pt:CODING_STANDARDS.md:22-24` (`patch_checked`); `pt:docs/claude/testing.md:48` |
| Shared fixture factories | Yes | `pt:CODING_STANDARDS.md:26-28`; `pt:docs/claude/testing.md:50` |
| Assert every wait in loop-driver tests | Yes (repo rule) | `pt:CODING_STANDARDS.md:18-20` (`sleep_fn=sleeps.append`) |
| Seam declaration | No | `testing.md:50` calls `ScriptedRoundScorer` "the seam `decide_round` scores through", but there is no export rule |
| Parametrize idiom | No | not in the repo; the report finds it only in a reviewer standard outside the repo |
| Order independence and shared state | Partial | no shuffler installed (per the source report); per-worktree database, cache path and port derived in `tests/conftest.py` (`pt:docs/claude/testing.md:52-60`) |
| Slow tier markers | Yes | `pt:docs/claude/testing.md:62-71` |
| Known cost hotspot | Yes | `pt:docs/claude/testing.md:75-81` (`_stub_os_keychain`; keychain subprocesses were about 60% of serial call time on macOS) |
| Mutation check | Yes | `pt:docs/claude/testing.md:83-113` (gate rule at `:87`) |

Pattern: pro-trading documents commands, tiers, cost and the mutation gate, which it learned through incidents. It documents none of the facts `refactor-tests` reads statically: layout, seam declaration, assertion and no-raise idioms, parametrize idiom. Those four rows are what a `setup-skills` scaffold of `docs/agents/testing.md` should prompt for. `pt:CODING_STANDARDS.md` is reviewer-facing ("Judgement-call rules for the reviewer", `:1-3`) with a severity per rule, so author-facing facts belong in `testing.md`.

## Notes for map #147

- A neutral `tdd` rule can say: call the code under test inside the test body; assert on the outcome; stub only through the sanctioned mechanism; prefer table-driven cases over copies; keep tests order independent; keep call time low. It should name each fact by its `testing.md` heading, not by a Python construct.
- The skill's seam quote is shared with `tdd/SKILL.md:20` and is already registered at `docs/agents/skill-dependencies.md:12`. A new `tdd` to `docs/agents/testing.md` pointer is a new dependency line there; `testing` also depends on the layout templates (`:14`).
- Non-Python seam signals are a gap in `refactor-tests` itself. A neutral `tdd` rule cannot make a Go or TS repo measurable; it can only make that repo's seam declaration a recorded fact.
