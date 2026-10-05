---
name: setup-skills
description: Configure this repo for the engineering skills — set up its issue tracker, triage label vocabulary, domain doc layout, and data folders, and migrate a legacy `CONTEXT.md` glossary to `GLOSSARY.md`. Run once before first use of the other engineering skills.
disable-model-invocation: true
---

# Setup Skills

Scaffold the per-repo configuration that the engineering skills assume:

- **Issue tracker** — where issues live (GitHub by default; local markdown is also supported out of the box)
- **Triage labels** — the strings used for the five canonical triage roles
- **Domain docs** — where `GLOSSARY.md`, ADRs, requirements, and reference docs live, and the consumer rules for reading them
- **Legacy glossary migration** — rename a pre-rename `CONTEXT.md`/`CONTEXT-MAP.md` to `GLOSSARY.md`/`GLOSSARY-MAP.md`, so the consumer skills find it

This is a prompt-driven skill, not a deterministic script. Explore, present what you found, confirm with the user, then write.

## Process

### 1. Explore

Look at the current repo to understand its starting state. Read whatever exists; don't assume:

- `git remote -v` and `.git/config` — is this a GitHub repo? Which one?
- `AGENTS.md` and `CLAUDE.md` at the repo root — does either exist? Is there already an `## Agent skills` section in either?
- `GLOSSARY.md` and `GLOSSARY-MAP.md` at the repo root
- Legacy glossary files from before the `GLOSSARY.md` rename: `CONTEXT.md` and `CONTEXT-MAP.md` at the root, plus per-context `CONTEXT.md` files (follow the links in `CONTEXT-MAP.md`, or run `fd -t f '^CONTEXT(-MAP)?\.md$'`). Also note every file that mentions `CONTEXT.md` or `CONTEXT-MAP.md` (`rg -l 'CONTEXT(-MAP)?\.md'`).
- `docs/adr/` and any `src/*/docs/adr/` directories
- `docs/agents/` — does this skill's prior output already exist?
- `.scratch/` — sign that a local-markdown issue tracker convention is already in use
- `.data/requirements/` — formal requirements docs (FS, SRS, API definitions); note if present
- `.data/docs/` — external reference documentation (vendor APIs, integrations); note if present
- Is the `triage` skill installed? (a `triage` skill folder alongside this one, or `triage` in your available skills.) This decides whether Section B runs at all.
- Monorepo signals — a `pnpm-workspace.yaml`, a `workspaces` field in `package.json`, or a populated `packages/*` with its own `src/`. Present only in a genuinely large multi-package repo; their absence means single-context, which is almost every repo.

### 2. Present findings and ask

Summarise what's present and what's missing. Then take the sections in order — one section, one answer, then the next.

Lead each section with the recommended answer so the user can accept it in a word. Give a one-line explainer only when the choice genuinely branches; skip the section entirely when exploration already settled it (Section B when `triage` isn't installed, Section C when there's no monorepo, Section D when no legacy `CONTEXT.md`/`CONTEXT-MAP.md` exists).

**Section A — Issue tracker.**

> Explainer: The "issue tracker" is where issues live for this repo. Skills like `to-tickets`, `triage`, `to-spec`, and `qa` read from and write to it — they need to know whether to call `gh issue create`, write a markdown file under `.scratch/`, or follow some other workflow you describe. Pick the place you actually track work for this repo.

Default posture: these skills were designed for GitHub. If a `git remote` points at GitHub, propose that. If a `git remote` points at GitLab (`gitlab.com` or a self-hosted host), propose GitLab. Otherwise (or if the user prefers), offer:

- **GitHub** — issues live in the repo's GitHub Issues (uses the `gh` CLI)
- **GitLab** — issues live in the repo's GitLab Issues (uses the [`glab`](https://gitlab.com/gitlab-org/cli) CLI)
- **Local markdown** — issues live as files under `.scratch/<feature>/` in this repo (good for solo projects or repos without a remote)
- **Other** (Jira, Linear, etc.) — ask the user to describe the workflow in one paragraph; the skill will record it as freeform prose

Record the choice in `docs/agents/issue-tracker.md`. The GitHub and GitLab templates carry a "PRs as a request surface" flag, defaulted **off** — leave it off and don't raise it; a user who wants external PRs in the triage queue can flip the flag in the file later.

**Section B — Triage label vocabulary.** Skip this section entirely if the `triage` skill isn't installed (exploration told you) — an uninstalled skill needs no labels.

If it is installed, ask exactly one question:

> Do you want to keep the default triage labels? (recommended: **yes**)

The defaults are the five canonical roles, each label string equal to its name: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. On **yes**, write them as-is. Only if the user says no — usually because their tracker already uses other names (e.g. `bug:triage` for `needs-triage`) — collect the overrides so `triage` applies existing labels instead of creating duplicates.

**Section C — Domain docs.** Default to **single-context** — one `GLOSSARY.md` + `docs/adr/` at the repo root. This fits almost every repo; write it without asking.

Offer **multi-context** — a root `GLOSSARY-MAP.md` pointing to per-context `GLOSSARY.md` files — only when exploration found monorepo signals. Then confirm which layout they want.

In either case, also note what data folders exist (`.data/requirements/`, `.data/docs/`) and include them in the generated `docs/agents/domain.md` so skills know where to look for requirements and reference docs.

If exploration found a legacy `CONTEXT-MAP.md`, the repo is already multi-context. Keep that layout; don't ask again.

**Section D — Legacy glossary migration.** Skip this section entirely when exploration found no `CONTEXT.md` or `CONTEXT-MAP.md`.

> Explainer: The skills now read the domain glossary from `GLOSSARY.md` (and `GLOSSARY-MAP.md` in multi-context repos). This repo still uses the old `CONTEXT.md` names, so the skills will not find its glossary until the files are renamed.

Recommend **migrate**. The plan has three parts:

- **Rename files in place.** Rename each `CONTEXT.md` to `GLOSSARY.md` and each `CONTEXT-MAP.md` to `GLOSSARY-MAP.md` in the same directory. File contents do not change, except the links in the map (next item).
- **Rewrite live references.** Change every `CONTEXT.md` to `GLOSSARY.md` and every `CONTEXT-MAP.md` to `GLOSSARY-MAP.md` in these places: the links inside the renamed `GLOSSARY-MAP.md`, `CLAUDE.md`, `AGENTS.md`, and `docs/agents/*.md`.
- **Leave history alone.** Other files that mention the old names can include ADRs, changelogs, dated notes, and source code. List them for the user, and let the user choose which ones to rewrite. ADRs and dated notes are records of the past, so default to leaving them as they are.

Stop and ask the user when a directory has both `CONTEXT.md` and `GLOSSARY.md`. Never overwrite one with the other. The user merges them by hand, or chooses which file to keep.

If the user declines the migration, record in `docs/agents/domain.md` that this repo keeps its glossary in `CONTEXT.md`. Otherwise the consumer skills will look only for `GLOSSARY.md`.

### 3. Confirm and edit

Show the user a draft of:

- The `## Agent skills` block to add to whichever of `CLAUDE.md` / `AGENTS.md` is being edited (see step 4 for selection rules)
- The contents of `docs/agents/issue-tracker.md`, `docs/agents/domain.md`, and `docs/agents/triage-labels.md` (the last only when `triage` is installed)
- The legacy glossary migration plan, when Section D ran: each file rename as `old path → new path`, and each file whose references will be rewritten

Let them edit before writing.

### 4. Write

**Migrate the legacy glossary first** (only when Section D ran and the user accepted). Rename with `git mv` in a git repo, so history follows the file. Use plain `mv` in a repo that is not under git. Then rewrite the references from the approved plan. Do this before you edit `CLAUDE.md`/`AGENTS.md` below, so the `## Agent skills` block and the docs files use the new names from the start. When the migration is done, run `rg 'CONTEXT(-MAP)?\.md'` again. Only the files that the user chose to leave alone must show hits.

**Pick the file to edit:**

- If `CLAUDE.md` is an import stub (its first non-blank line is `@AGENTS.md`) and `AGENTS.md` exists, edit `AGENTS.md`. The stub keeps only Claude Code-specific content.
- Else if `CLAUDE.md` exists, edit it.
- Else if `AGENTS.md` exists, edit it.
- If neither exists, ask the user which one to create — don't pick for them.

Never create `AGENTS.md` when `CLAUDE.md` already exists (or vice versa) — always edit a file that's already there.

If an `## Agent skills` block already exists in the chosen file, update its contents in-place rather than appending a duplicate. Don't overwrite user edits to the surrounding sections.

The block:

```markdown
## Agent skills

### Issue tracker

[one-line summary of where issues are tracked]. See `docs/agents/issue-tracker.md`.

### Triage labels

[one-line summary of the label vocabulary]. See `docs/agents/triage-labels.md`.

### Domain docs

[one-line summary of layout — "single-context" or "multi-context"]. See `docs/agents/domain.md`.
```

Include the `### Triage labels` sub-block, and write `docs/agents/triage-labels.md`, only when `triage` is installed and Section B ran. When it isn't, both are omitted.

Then write the docs files using the seed templates in this skill folder as a starting point:

- [issue-tracker-github.md](./issue-tracker-github.md) — GitHub issue tracker
- [issue-tracker-gitlab.md](./issue-tracker-gitlab.md) — GitLab issue tracker
- [issue-tracker-local.md](./issue-tracker-local.md) — local-markdown issue tracker
- [triage-labels.md](./triage-labels.md) — label mapping (only if `triage` is installed)
- [domain.md](./domain.md) — domain doc consumer rules + layout

For "other" issue trackers, write `docs/agents/issue-tracker.md` from scratch using the user's description.

### 5. Done

Tell the user the setup is complete and which engineering skills will now read from these files. If the glossary was migrated, list the renamed files and any old-name mentions that were left alone on purpose. Mention they can edit `docs/agents/*.md` directly later — re-running this skill is only necessary if they want to switch issue trackers, migrate a legacy `CONTEXT.md` glossary, or restart from scratch.
