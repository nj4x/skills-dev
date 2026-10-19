<!-- PROTOTYPE for wayfinder #153 — rough seed template, to react to. Would live at skills/engineering/setup-skills/testing.md -->

# Testing

How this repo runs and writes tests. `tdd` reads this file once before the first test. `testing` reads **Commands**. `refactor-tests` reads **Test layout** and **Assertion idiom**.

Edit values freely. Keep the headings: skills cite them by name. A heading with no fact for this repo says `not set` — skills then follow the neighbouring tests and ask when that is unclear.

## Commands

- full suite: `{command}`
- one file: `{command} <path>`
- covering tests for changed files: `{command}` (omit when the repo has no mapper)
- mutation check: `{command} <module>`, or `none`

## Test layout

One line per language present:

- {language}: `{source path template}` → `{test path template}`

Integration directory: `{dir}`. A test goes there when it exercises more than one source module. {Membership rule, or omit.} Guard: `{meta-test or CI check that enforces the rule}` (omit when none).

## Seam declaration

A seam that a ticket agrees is declared public by: {mechanism per language — e.g. "listed in the module's `__all__`", "`export`ed", "capitalized name", "`public`"}.

## Stub helper

- Injection point: {how a port or boundary is passed in — deps object, constructor argument, parameter}
- Checked patch, fallback only: `{helper}` (or `{autospec=True}`)
- Shared fakes and factories: `{path}` (omit when none)

## Assertion idiom

- Assertion helper prefix: `{prefix}` (e.g. `assert_`)
- "Does not raise" tests: name or docstring says "does not raise". Documented raisers: `{name}`, … (`refactor-tests` passes each as `--raiser`)
- Fixtures that assert: {names}, or none

## Parametrize idiom

`{runner's table-driven construct}` — e.g. `@pytest.mark.parametrize`, `test.each`, a table with `t.Run`, `@ParameterizedTest`. Case ids: {style}.

## Order independence

- Shuffler: `{plugin}` installed | planned | none
- Shared state a test must not leak: {database, environment, cache path, port, …} — isolated by {fixture or mechanism}

## Cost budget

- Per-test call time: under `{0.5 s}`
- Slow tier: marker `{name}`, excluded from the default run by `{command}` (omit when none)
- Known expensive setup: `{fixture}` — {what it stubs and why}
