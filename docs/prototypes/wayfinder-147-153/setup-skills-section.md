<!-- PROTOTYPE for wayfinder #153 — rough setup-skills/SKILL.md edits, to react to. -->

## Intro bullet list (add)

- **Testing** — how tests run and where they go, and the repo idioms `tdd` writes to (`docs/agents/testing.md`)

## Step 1 Explore (add bullets)

- Languages present and their runner markers: read `../refactor-tests/reference/patterns.md` → "Language detection" and "Runner detection" when `refactor-tests` is installed; otherwise `pyproject.toml`, `package.json`, `go.mod`, `pom.xml`, `build.gradle*`.
- The test tree: sample 5 test files per language. Does each mirror its source path (patterns.md "Path templates")? Is there an integration directory? A meta-test or baseline file that guards it (`rg -l 'baseline|tier' <tests dir>`)?
- Idioms in use, by search, per heading: `__all__` / `export` (Seam declaration); `autospec`, a `patch_*` helper, a deps object (Stub helper); `def (_?assert|check|expect|verify)\w*` in test files (Assertion idiom); parametrize construct (Parametrize idiom); a shuffler plugin in dependencies (Order independence); slow markers in runner config (Cost budget); a mutation tool in dependencies (`mutmut`, `cosmic-ray`, Stryker, PIT).
- An existing testing guide that `AGENTS.md`/`CLAUDE.md` points to (e.g. `docs/claude/testing.md`, `CODING_STANDARDS.md`).

## Step 2 — Section E: Testing

Skip this section entirely when the `tdd` skill isn't installed (a `tdd` folder alongside this one, or `tdd` in your available skills) — same rule as Section B and `triage`. Add the `tdd` check to the Step 1 explore list.

> Explainer: `tdd` writes tests that `refactor-tests` can later check. It needs this repo's facts — where a test goes, how a seam is declared public, which stub helper and assertion idioms to use — under fixed headings in `docs/agents/testing.md`.

Show one draft of the file, every heading filled. Mark each value by source:

- **detected** — found in the repo (explore step);
- **default** — proposed from `../refactor-tests/reference/patterns.md` for the language (path template, integration directory, assertion prefixes, 0.5 s budget); never from a copy in this skill;
- **not set** — nothing found and no default.

Ask only about these, one question each, recommended answer first:

1. A **detected** value that differs from the default (e.g. the test tree is flat, not mirrored): keep the repo's convention, or adopt the default for new tests?
2. **Seam declaration**, when not detected: propose the language's own public marker.
3. **Mutation check**, when no tool is detected: `none` (recommended) or a command.

Accept the rest in one word. A value the user does not give stays `not set`.

When an existing testing guide holds a fact, copy the fact as one line under its heading and link the guide for the detail. Do not move or rewrite the guide.

## Step 3 Confirm (add)

- The contents of `docs/agents/testing.md` (or the diff against it).

## Step 4 Write (add)

Agent skills block:

    ### Testing

    [one-line summary — languages and runner]. See `docs/agents/testing.md`.

Sync rules, `testing.md` row: the seven headings plus Commands are fixed names. A heading the local file lacks is added from the template. Values stay local. A heading the user renamed is a conflict: put it to the user, since `tdd` will not find it under another name.

Seed template list: `[testing.md](./testing.md) — test commands, layout, and authoring idioms`.

## Step 5 Done (add)

`tdd`, `testing`, and `refactor-tests` now read `docs/agents/testing.md`.
