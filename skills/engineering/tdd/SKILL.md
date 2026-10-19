---
name: tdd
description: Test-driven development. Use when the user wants to build features or fix bugs test-first, mentions "red-green-refactor", or wants integration tests.
---

# Test-Driven Development

TDD is the red → green loop. This skill is the reference that makes that loop produce tests worth keeping: what a good test is, where tests go, the anti-patterns, and the rules of the loop. Every section applies on every cycle — consult them before and during the loop, not after.

When exploring the codebase, read `GLOSSARY.md` (if it exists) so test names and interface vocabulary match the project's domain language, and respect ADRs in the area you're touching. Read `docs/agents/testing.md` once here too, before the first test. With no such file, follow the neighbouring tests' convention, ask when that is unclear, suggest `/setup-skills` once, and never block. A heading or line key that reads `not set` gets the same fallback: follow the neighbouring tests. "Seam declaration" keeps its own fallback (the language's public-export marker, below); a "Cost budget" that reads `not set` means no budget check. Search source code conceptually and cross-file; search docs and requirements as a document corpus; for architecture-level questions start with a global search before reading individual files.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. A good test reads like a specification — "user can checkout with valid cart" tells you exactly what capability exists — and survives refactors because it doesn't care about internal structure.

See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for mocking guidelines.

## Seams — where tests go

A **seam** is the public boundary you test at: the interface where you observe behavior without reaching inside. Tests live at seams, never against internals. Here "seam" means the module's external seam, its public interface; `codebase-design` also defines internal seams, which are not test surfaces.

**Test only at pre-agreed seams.** Before writing any test, write down the seams under test. A seam is agreed when the user or the ticket/spec names it (a "Test seams" or "Acceptance criteria" section counts); otherwise confirm it with the user. Every test lands at an agreed seam. You can't test everything — agreeing the seams up front is how testing effort lands on the critical paths and complex logic instead of every edge case.

When no seam is agreed, ask: "What's the public interface, and which seams should we test?" Give each proposed seam a one-line note on what it catches and what it misses.

**Declare each agreed seam public in code**, using the mechanism the "Seam declaration" heading of `docs/agents/testing.md` names. Without that file, or when that heading reads `not set`, use the language's own public-export marker; ask the user when that is unclear.

**A seam that cannot be declared public gets no test.** Stop and agree the seam again with the user or ticket: make the name public and declare it, or pick the public interface that exercises it.

When the shape of that interface is itself in question — how deep the module is, where the seam belongs, what the interface should expose — use the `/codebase-design` skill for the vocabulary. It is the shared source of the module, interface, depth, seam, adapter, leverage and locality terms, and it is a reference to consult, not a session to run.

## Test shape

Where `docs/agents/testing.md` holds the repo's concrete fact, the line cites its heading.

1. **Placement.** Mirror the source layout; put cross-cutting tests in the integration directory ("Test layout").
2. **Parametrize over copies.** Grow an existing parametrized test only when all four hold: the same seam, the same setup and doubles, the same assertion shape, and a difference in data only. Convert on the second case, in the mirrored file. Add one row per cycle, each with a named id ("Parametrize idiom").
3. **Behavior runs in the test body.** The code under test runs in the test body, not in a fixture or setup.
4. **Assertion helpers.** Name assertion helpers with the repo's assertion prefix ("Assertion idiom", `Prefix:` line).
5. **"Does not raise" tests.** The name or docstring says "does not raise", or the test's only check is a call to a name on the `Raisers:` line ("Assertion idiom").
6. **Order independence.** Each test owns its state and passes in any order ("Order independence").
7. **Call-time budget.** Stay under the budget; stub the slow boundary, not the test ("Cost budget").
8. **Assertion strength.** Each test asserts something no other test asserts. Give each property the code enforces (a boundary, an anchor, a case rule, a type guard) its own case, even when that case covers no new lines.

## Anti-patterns

- **Implementation-coupled** — mocks internal collaborators, tests private methods, or verifies through a side channel (querying the database instead of using the interface). The tell: the test breaks when you refactor but behavior hasn't changed.
- **Tautological** — the assertion recomputes the expected value the way the code does (`expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand the same way, a constant asserted equal to itself), so it passes by construction and can never disagree with the code. Expected values must come from an independent source of truth — a known-good literal, a worked example, the spec.
- **Horizontal slicing** — writing all tests first, then all implementation. Bulk tests verify _imagined_ behavior: you test the _shape_ of things rather than user-facing behavior, the tests go insensitive to real changes, and you commit to test structure before understanding the implementation. Work in **vertical slices** instead — one test → one implementation → repeat, each test a **tracer bullet** that responds to what the last cycle taught you.

## Rules of the loop

- **Red before green.** Write the failing test first, then only enough code to pass it. Don't anticipate future tests or add speculative features.
- **One slice at a time.** One seam, one test, one minimal implementation per cycle.
- **Refactoring is not part of the loop.** Refactoring the diff's tests and code follows review findings (`implement` Minor triage, autofix for Majors), not the red → green cycle. Suite-wide test restructuring belongs to `refactor-tests`.
- **Reshaping a test to take a new case row is part of writing the test.**
- **A green-on-arrival row never counts as the cycle's red.** Keep it only when the spec names that edge.
