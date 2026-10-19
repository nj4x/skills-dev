# Testing

How this repo runs and writes tests. Skills read these headings:

- `testing` reads only **Commands**.
- `tdd` reads all seven headings below **Commands**, once, before the first test.
- `code-review` reads the whole file. It checks **Order independence** and **Cost budget** for static smells only.
- `implement` and `implement-spec` read **Seam declaration**.
- `refactor-tests` reads **Test layout** and **Assertion idiom**. It runs its own order and cost checks and never reads **Order independence** or **Cost budget**.

Edit values freely. Heading names and line keys (`Prefix:`, `Raisers:`, `Guard:`, `Shuffler:`) are fixed: skills cite them by name. A heading with no fact for this repo says `not set`; skills then follow the neighbouring tests and ask when that is unclear.

## Commands

- full suite: `{command}`
- one file: `{command} <path>`
- covering tests for changed files: `{command}` (omit when the repo has no mapper)
- mutation check: `{command} <module>`, or `none`

## Test layout

One line per language present:

- {language}: `{source path template}` → `{test path template}`

Integration directory: `{dir}`. A test goes there when it exercises more than one source module. {Membership rule, or omit.}

Guard: `{meta-test or CI check that enforces the rule}` (omit when none)

## Seam declaration

A seam that a ticket agrees is declared public by: {mechanism per language, for example "listed in the module's `__all__`", "`export`ed", "capitalized name", "`public`"}.

## Stub helper

- Injection point: {how a port or boundary is passed in: deps object, constructor argument, parameter}
- Checked patch, fallback only: `{helper}` (for example `autospec=True`)
- Shared fakes and factories: `{path}` (omit when none)

## Assertion idiom

- Prefix: `{prefix}` (the assertion helper prefix, for example `assert_`)
- Raisers: {name}, … (documented "does not raise" helpers; `refactor-tests` passes each name as `--raiser`)
- "Does not raise" tests: name or docstring says "does not raise".
- Fixtures that assert: {names}, or none

## Parametrize idiom

`{runner's table-driven construct}`, for example `@pytest.mark.parametrize`, `test.each`, a table with `t.Run`, `@ParameterizedTest`.

Named case id: `{how a row gets an id that names the behavior it pins}`, for example `pytest.param(..., id="comma-decimal")` or a `test.each` title template.

## Order independence

- Shuffler: `{plugin}` installed | planned | none
- Shared state a test must not leak: {database, environment, cache path, port, …}, isolated by {fixture or mechanism}

## Cost budget

- Per-test call time: under `{0.5 s}`
- Slow tier: marker `{name}`, excluded from the default run by `{command}` (omit when none)
- Known expensive setup: `{fixture}`, which stubs {what} because {why}
