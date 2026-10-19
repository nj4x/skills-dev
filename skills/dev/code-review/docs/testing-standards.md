# Testing Standards

Language-neutral standard for test files in the diff. It states the same properties as the `tdd` Test shape section. Read the repo's `docs/agents/testing.md` for the concrete facts each check cites by heading; where it is absent, a heading reads `not set`, or a line key reads `Key: not set` (`Prefix:`, `Raisers:`, `Fixtures that assert:`), follow the neighbouring tests. Language specifics live in the language file (`kotlin-standards.md` → `## Testing`, `python-standards.md` → Testing Patterns).

Review reads the diff only. Review never runs a shuffle and never measures call time.

## Checks

Check each new or changed test against all eight:

1. **Mirrored layout.** The test file sits where "Test layout" maps its source file; a test that exercises more than one source module sits in the integration directory.
2. **Seam only.** The test calls seams declared public ("Seam declaration"). It never imports, calls, or patches the project's own internals.
3. **Mocking stance.** Doubles stand in for ports and boundaries only (I/O, network, clock, process). Call assertions (`verify`, `assert_called_with`) apply to commands only: a call that crosses a boundary or port and is the observable outcome (email sent, row saved). A query is asserted through the returned value. A double the language file mandates (for example `@MockkBean` use cases in a `@ControllerDocumentationTest`) is not a finding.
4. **Parametrize over copies.** A new test that meets all four grow conditions against an existing test is a row in that test: the same seam, the same setup and doubles, the same assertion shape, and a difference in data only. A second case converts the test, in the mirrored file. Each row carries a named id ("Parametrize idiom").
5. **In-body behavior.** The code under test runs in the test body, not in a fixture or setup.
6. **Assertion vocabulary.** The test holds an assertion. A "does not raise" test says so in its name or docstring, or its only check is a call to a name on the `Raisers:` line ("Assertion idiom"); a fixture on the "Fixtures that assert" line supplies the assertion for a test that uses it. Assertion helpers use the prefix on the `Prefix:` line of "Assertion idiom". Each test asserts something no other test asserts; a property the code enforces (a boundary, an anchor, a case rule, a type guard) has its own case, even when that case covers no new lines.
7. **Order independence, static smells only.** Flag state a test leaks to another: module-level mutables, shared fixtures that mutate, unisolated environment, database, cache path, or port ("Order independence").
8. **Cost, static smells only.** Flag unstubbed network, sleep, real subprocess, and expensive setup that "Cost budget" says to stub.

## Severity

- **Major**: the test has no assertion (a "does not raise" test excepted: by name or docstring, or its only check is a call to a `Raisers:` name; a test that uses a fixture on the "Fixtures that assert" line also excepted), is tautological, or tests or doubles the project's own internals (a double the language file mandates excepted).
- **Minor**: every other test finding.

A tautological test recomputes its expected value the way the code does, so it passes by construction. Expected values come from a literal, a worked example, or the spec.

An assertion that targets the test's own fixture input, and never what the code under test produced or received, is a no-op test: report it as tautological.

## Mock Verification model

```text
test "creates the user":
    given   repository = double of the UserRepository port
    given   service = UserService(repository)
    given   user = a user with id "user123"
    when    service.create_user(user)          # runs in the body
    then    assert_called_once_with(repository.save, user matching id "user123")   # command: asserted on the double's call
```

Assert a double's calls only for commands (`save`, `publish`, `send`). Never assert that a double answered a query (`find`, `get`): the returned value already proves it.
