# Testing

How this repo runs and writes tests. Skills read these headings:

- `testing` reads only **Commands**.
- `tdd` reads all seven headings below **Commands**, once, before the first test.
- `code-review` reads the whole file. It checks **Order independence** and **Cost budget** for static smells only.
- `implement` and `implement-spec` read **Seam declaration**.
- `refactor-tests` reads **Test layout** and **Assertion idiom**. It runs its own order and cost checks and never reads **Order independence** or **Cost budget**.

Edit values freely. Heading names and line keys are fixed: skills cite them by name. The line keys are `full suite:`, `one file:`, `covering tests for changed files:` (the Commands keys), `Integration directory:`, `Guard:`, `Prefix:`, `Raisers:`, `Fixtures that assert:`, `Named case id:`, `Shuffler:` and `Slow tier:`.

A heading with no fact for this repo reads `not set`; a line key with no fact reads `Key: not set`. Each reader states its own fallback:

- `testing` falls back per Commands line (one-file included) to the repo's AGENTS.md, then its runner config.
- `tdd` and `code-review` follow the neighbouring tests. `tdd` keeps the language's public-export marker for Seam declaration, and runs no budget check when Cost budget reads `not set`.
- `implement` and `implement-spec` use the public-export marker for Seam declaration.
- `refactor-tests` uses its own table defaults and the project's other docs.

## Commands

<!-- No fact for this repo: replace this comment and every {placeholder} line under it with `not set`. Fact filled: delete this comment, replace each {placeholder} with its value, and write `Key: not set` for a line key with no fact (delete a line marked "omit when none"). -->

- full suite: `{command}`
- one file: `{command} <path>`
- covering tests for changed files: `{command}` (omit when the repo has no mapper)

## Test layout

<!-- No fact for this repo: replace this comment and every {placeholder} line under it with `not set`. Fact filled: delete this comment, replace each {placeholder} with its value, and write `Key: not set` for a line key with no fact (delete a line marked "omit when none"). -->

One line per language present:

- {language}: `{source path template}` → `{test path template}`

Integration directory: `{dir}` (or one `{language}: {dir}` per language; a bare value applies to the repo's primary test language). A test goes there when it exercises more than one source module. {Membership rule, or omit.}

Guard: `{meta-test or CI check that enforces the rule}` (omit when none)

## Seam declaration

<!-- No fact for this repo: replace this comment and every {placeholder} line under it with `not set`. Fact filled: delete this comment, replace each {placeholder} with its value, and write `Key: not set` for a line key with no fact (delete a line marked "omit when none"). -->

A seam that a ticket agrees is declared public by: {mechanism per language, for example "listed in the module's `__all__`", "`export`ed", "capitalized name", "`public`"}.

## Stub helper

<!-- No fact for this repo: replace this comment and every {placeholder} line under it with `not set`. Fact filled: delete this comment, replace each {placeholder} with its value, and write `Key: not set` for a line key with no fact (delete a line marked "omit when none"). -->

- Injection point: {how a port or boundary is passed in: deps object, constructor argument, parameter}
- Checked patch, fallback only: `{helper}` (for example `autospec=True`)
- Shared fakes and factories: `{path}` (omit when none)

## Assertion idiom

<!-- No fact for this repo: replace this comment and every {placeholder} line under it with `not set`. Fact filled: delete this comment, replace each {placeholder} with its value, and write `Key: not set` for a line key with no fact (delete a line marked "omit when none"). -->

- Prefix: `{prefix}` (the assertion helper prefix, for example `assert_`)
- Raisers: {name}, … (documented "does not raise" helpers; `refactor-tests` passes each name as `--raiser`)
- "Does not raise" tests: name or docstring says "does not raise".
- Fixtures that assert: {names}, or none

## Parametrize idiom

<!-- No fact for this repo: replace this comment and every {placeholder} line under it with `not set`. Fact filled: delete this comment, replace each {placeholder} with its value, and write `Key: not set` for a line key with no fact (delete a line marked "omit when none"). -->

`{runner's table-driven construct}`, for example `@pytest.mark.parametrize`, `test.each`, a table with `t.Run`, `@ParameterizedTest`.

Named case id: `{how a row gets an id that names the behavior it pins}`, for example `pytest.param(..., id="comma-decimal")` or a `test.each` title template.

## Order independence

<!-- No fact for this repo: replace this comment and every {placeholder} line under it with `not set`. Fact filled: delete this comment, replace each {placeholder} with its value, and write `Key: not set` for a line key with no fact (delete a line marked "omit when none"). -->

- Shuffler: `{plugin}` installed | planned | none
- Shared state a test must not leak: {database, environment, cache path, port, …}, isolated by {fixture or mechanism}

## Cost budget

<!-- No fact for this repo: replace this comment and every {placeholder} line under it with `not set`. Fact filled: delete this comment, replace each {placeholder} with its value, and write `Key: not set` for a line key with no fact (delete a line marked "omit when none"). -->

- Per-test call time: under `{limit}`
- Slow tier: marker `{name}`, excluded from the default run by `{command}` (omit when none)
- Known expensive setup: `{fixture}`, which stubs {what} because {why}
