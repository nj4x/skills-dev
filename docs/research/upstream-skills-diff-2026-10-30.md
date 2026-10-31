# Upstream skills diff — `mattpocock/skills` 49dd158..a496f55 → `skills-dev` (2026-10-30)

## Question

Which changes in upstream `mattpocock/skills` (`/Users/roman/projects/skills`) since the last sync should `skills-dev` (`/Users/roman/projects/skills-dev`) port today? Upstream `main` was just fast-forwarded from `49dd158` to `a496f55`, and tag `v1.3.2` is new.

## Short answer

The window is small: six non-merge commits, of which three touch skills that skills-dev carries. The substantive work is in the `setup-skills` tracker seed docs (`ed0de59`, `59db609`): a comment-then-close fix, reading a PR's body as well as its comments, the GitHub **Blocking** operation moved into Conventions with the native `gh` flags, a named "count open blockers" command, a GitLab MR-list flag fix, GitLab wayfinder child linking, and a reachable-remote check before a hosted tracker is recorded. The second item is `implement-spec` using a fresh implementer per ticket and for the integration fixes (`a496f55`), which needs light adaptation to skills-dev's richer step 4 and 7. The repo-wide "start every subagent with a fresh context window" sentence (`7739eae`) is mostly redundant here, because skills-dev declares an explicit `subagent_type` at each dispatch site and in Claude Code only `subagent_type: "fork"` inherits context. It is worth applying only at the two dispatch sites that still declare no type. Everything else is governance scaffolding, release tooling, `chief-of-staff`, or a CHANGELOG roll-up of commits that ADR-0078 already handled.

## 1. Baseline and scope

ADR-0078 (`docs/adr/0078-upstream-sync-2026-10.md`) synced the window `d81f3a1..c20facd` and named "upstream `c20facd`" as the next baseline, with the instruction to start from `git log --no-merges c20facd..HEAD`. The skills-dev commits that landed it are `31cbcef` (merge of PR #109, `feat/upstream-sync-49dd158`), `2955c68` ("record upstream sync window d81f3a1..c20facd and new baseline") and the follow-up `038a2b8` (#110).

That baseline needs one correction. `c20facd` ("wizard: keep apostrophes intact on bash 3.2 when Enter keeps current") is not on upstream `main`. It lives only on `origin/wizard-bash32-apostrophe` (`git branch -a --contains c20facd`), its parent is `49dd158`, and `git merge-base c20facd a496f55` is `49dd158`. So `c20facd..a496f55` is not a linear window: it lists the same six commits as `49dd158..a496f55`, but its diff also shows a reverse of the `c20facd` wizard fix. The effective baseline on upstream `main` is therefore **`49dd158`**, with `c20facd` treated as already ported. skills-dev's `skills/engineering/wizard/template.sh` is byte-identical to `git show c20facd:skills/engineering/wizard/template.sh`, so skills-dev is one fix ahead of upstream `main` on the wizard.

Window: `49dd158..a496f55`, six non-merge commits, 37 files, +171/−111 (`git diff --shortstat 49dd158 a496f55`). `v1.3.2` points at `d1478fc`; `a496f55` is one commit past it.

| Commit | Date | Subject | Files that matter |
|---|---|---|---|
| `5beb35b` | 2026-10-19 | chief-of-staff: keep memory in a dated, commit-cited wiki (#1304) | `skills/in-progress/chief-of-staff/SKILL.md` |
| `ed0de59` | 2026-10-27 | setup-matt-pocock-skills: reachable repo, legacy CONTEXT.md, tracker template fixes (#1228) | `setup-matt-pocock-skills/SKILL.md`, `issue-tracker-github.md`, `issue-tracker-gitlab.md`, `docs/engineering/domain-modeling.md` |
| `59db609` | 2026-10-27 | Close blank issues and route requests by kind (#1169) | `setup-matt-pocock-skills/issue-tracker-github.md`, `.github/ISSUE_TEMPLATE/*`, `CONTRIBUTING.md` |
| `7739eae` | 2026-10-29 | Start subagents with a fresh context window, not a fork (#1341) | `CLAUDE.md` and 9 `SKILL.md`/reference files |
| `d1478fc` | 2026-10-29 | chore: version skills (#1161) | `CHANGELOG.md` (1.3.2), `package.json`, `.claude-plugin/plugin.json`, changesets removed |
| `a496f55` | 2026-10-29 | implement-spec: a fresh implementer subagent per ticket (#1342) | `skills/engineering/implement-spec/SKILL.md` |

The 1.3.2 `CHANGELOG.md` section lists 19 entries, but 16 of them describe commits from the previous window (`b645f47`, `3da8c01`, `f3fc563`, `e0efb6e`, `95249b0`, `4f4e943`, `e48341a`, `6d6a5b9`, `5b7cade`, `cffab50`, `8295b8e`, `49dd158`, `868c4cf`, `3f59913`, `ad5400b` twice). Each of those is an ancestor of `49dd158` and was ported, adapted or skipped under ADR-0078 and `docs/research/upstream-skills-assessment.md`. Only the `5beb35b`, `59db609`, `ed0de59` and `7739eae` entries are new; `a496f55` has an unreleased changeset (`.changeset/implementer-fresh-per-ticket.md`).

## 2. Summary table

| # | Upstream change | Commit | skills-dev counterpart | Verdict | Effort |
|---|---|---|---|---|---|
| 1 | GitHub tracker: post the closing comment with `gh issue comment`, then `gh issue close` | `ed0de59` | `skills/engineering/setup-skills/issue-tracker-github.md:14` | PORT NOW | XS |
| 2 | GitHub tracker: read a PR's body with `gh pr view`, then `--comments` | `ed0de59` | `issue-tracker-github.md:36` | PORT NOW | XS |
| 3 | GitHub tracker: **Blocking** moved into Conventions with `--blocked-by` / `--add-blocked-by`; new **Count open blockers** | `ed0de59` | `issue-tracker-github.md:57-58` | PORT NOW (keep heading names) | S |
| 4 | GitLab tracker: `glab mr list -O json` | `ed0de59` | `skills/engineering/setup-skills/issue-tracker-gitlab.md:25` | PORT NOW | XS |
| 5 | GitLab tracker: wayfinder child linked with `--linked-issues <map> --link-type relates_to`; frontier lists the map's links | `ed0de59` | `issue-tracker-gitlab.md:43,45` | ADAPT (Wayfinding section only) | S |
| 6 | setup: wire up a reachable remote before recording a GitHub/GitLab tracker | `ed0de59` | `skills/engineering/setup-skills/SKILL.md:53-60` (Section A) | PORT NOW | XS |
| 7 | setup: offer to `git mv` a legacy `CONTEXT.md` | `ed0de59` | `setup-skills/SKILL.md:28,78-90,125` (Section D) | SKIP (already covered, more thoroughly) | — |
| 8 | GitHub tracker: file only into the user's own repo; check `gh repo view --json nameWithOwner` before the first `gh issue create` | `59db609` | `issue-tracker-github.md:16` | ADAPT (drop the `mattpocock/skills` name, keep the fork check) | XS |
| 9 | `implement-spec`: a fresh implementer per ticket and for the code-review fixes | `a496f55` (+ `7739eae` line) | `skills/engineering/implement-spec/SKILL.md:40,56` | ADAPT | S |
| 10 | "Start every subagent with a fresh context window" in 8 skills + `CLAUDE.md` | `7739eae` | `code-review`, `codebase-design`, `improve-codebase-architecture`, `research`, `grilling`: already typed; `wayfinder:121`: untyped | SKIP, except one ADAPT at `wayfinder/SKILL.md:121` | XS |
| 11 | `chief-of-staff` wiki memory | `5beb35b` | none (`planning/goal-loop`, `planning/task-execution` overlap) | SKIP (ADR-0078 §4); note the idea | — |
| 12 | Issue forms, `CONTRIBUTING.md`, blank-issue routing | `59db609` | none | SKIP (ADR-0078 §4, governance scaffolding) | — |
| 13 | `docs/engineering/domain-modeling.md` FAQ fix | `ed0de59` | none (skills-dev has no user-facing docs tree) | SKIP | — |
| 14 | Version bump, CHANGELOG, changesets | `d1478fc` | none | SKIP (ADR-0078 §4, release tooling) | — |
| 15 | `wizard/template.sh` | none in window | `skills/engineering/wizard/template.sh` | SKIP (skills-dev already at `c20facd`, ahead of upstream `main`) | — |

No upstream skill in the window lacks a counterpart, except the in-progress `chief-of-staff`. No NEW SKILL candidate.

## 3. Skill map for the changed upstream skills

| Upstream path | skills-dev path | Relationship |
|---|---|---|
| `skills/engineering/setup-matt-pocock-skills/` | `skills/engineering/setup-skills/` | renamed and extended (Sections D legacy glossary migration and E testing facts, local tracker, `.data/requirements/`) |
| `skills/engineering/implement-spec/SKILL.md` | `skills/engineering/implement-spec/SKILL.md` | same name, heavily extended (Test gate, round counter, blocked-ticket handling, `render_review_brief.py`) |
| `skills/engineering/code-review/SKILL.md` | `skills/dev/code-review/SKILL.md` | moved to `dev/`, local rewrite (four typed finders, workflow docs) |
| `skills/engineering/codebase-design/DESIGN-IT-TWICE.md` | `skills/engineering/codebase-design/DESIGN-IT-TWICE.md` | same file, typed dispatch added |
| `skills/engineering/improve-codebase-architecture/SKILL.md` | same path | extended (Explore dispatch, mcp-vectors search) |
| `skills/engineering/research/SKILL.md` | `skills/engineering/research/SKILL.md` | same, typed dispatch added |
| `skills/engineering/wayfinder/SKILL.md` | `skills/engineering/wayfinder/SKILL.md` | same name, extended (execution map) |
| `skills/productivity/grilling/SKILL.md` | `skills/learning/grilling/SKILL.md` | moved to `learning/`, extended (critic hand-off) |
| `skills/in-progress/chief-of-staff/SKILL.md` | none | upstream-only, experimental |

## 4. Per-item details

### Item 1 — Comment, then close (PORT NOW)

Upstream `ed0de59`, `skills/engineering/setup-matt-pocock-skills/issue-tracker-github.md` Conventions: "**Close**: post the explanation with `gh issue comment <number> --body "..."`, then `gh issue close <number>`. On an already-closed issue, `gh issue close --comment` drops the comment and still exits 0." (upstream issue #873.)

skills-dev still has the old form at `skills/engineering/setup-skills/issue-tracker-github.md:14`: `gh issue close <number> --comment "..."`. Readers of **Close** include `triage` (`skills/engineering/triage/SKILL.md:82-85`, the `wontfix` close with a reason). The GitHub Wayfinding **Resolve** line (`issue-tracker-github.md:60`) already uses comment-then-close, so this change also makes the doc consistent with itself. The GitLab doc already requires note-then-close (`issue-tracker-gitlab.md:13`). Applies cleanly; one line.

### Item 2 — Read a PR's body as well as its comments (PORT NOW)

Upstream `ed0de59`: "**Read a PR**: `gh pr view <number>`, then `gh pr view <number> --comments` (off a TTY, `--comments` prints only the comments, not the body), and `gh pr diff <number>` for the diff." (upstream issue #1138.)

skills-dev has the old command at `issue-tracker-github.md:36`. I confirmed the behaviour locally with `gh` 2.101.0: `gh pr view 175 --comments | head` in skills-dev printed nothing (PR #175 has no comments), while `gh pr view 175 | head` printed the title, state and metadata. An agent following the current line never sees the PR body. Applies cleanly; one line.

### Item 3 — Blocking in Conventions, and a named open-blocker count (PORT NOW, keep heading names)

Upstream `ed0de59` adds two Conventions bullets to the GitHub template and shortens the Wayfinding entries to pointers:

- "**Blocking**: GitHub's **native issue dependencies** … Add an edge with `gh issue create --blocked-by <n>,<n> ...` or `gh issue edit <child> --add-blocked-by <blocker>` (`gh` 2.94+). Older `gh`: `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>` … Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body."
- "**Count open blockers**: `gh api repos/<owner>/<repo>/issues/<n> --jq .issue_dependencies_summary.blocked_by` (open blockers only; 0 means startable). `gh issue view <n> --json blockedBy` also lists closed blockers, so filter it: `--jq '[.blockedBy.nodes[] | select(.state == "OPEN")] | length'`."
- Wayfinding **Blocking** becomes "see **Blocking** under Conventions", and **Frontier query** points at **Count open blockers**. (Upstream issues #855, #1118.)

skills-dev keeps **Blocking** only under Wayfinding operations (`issue-tracker-github.md:57`), with only the `gh api` form, and the frontier query inlines `issue_dependencies_summary.blocked_by > 0` (`:58`). That placement is wrong for skills-dev more than for upstream, because three non-wayfinder skills wire or read blocking edges on GitHub: `to-tickets` pass 2 "create native blocking links" (`skills/engineering/to-tickets/SKILL.md:152`), and `implement-spec`, whose real-tracker task graph is "linked … via the tracker's native blocking-issue relationships" (`skills/engineering/implement-spec/SKILL.md:28`) but which names no command for the frontier. Moving **Blocking** into Conventions gives them a named operation, and **Count open blockers** gives `implement-spec` a frontier test.

I verified the commands against local `gh` 2.101.0: `gh issue create --help` lists `--blocked-by`, `--blocking` and `--parent`; `gh issue edit --help` lists `--add-blocked-by` and `--remove-blocked-by`; `gh issue view --help` lists the JSON fields `blockedBy`, `blocking` and `subIssues`. `gh issue view 145 --json blockedBy` in skills-dev returned `{"blockedBy":{"nodes":[],"totalCount":0}}`, and `gh api repos/nj4x/skills-dev/issues/145 --jq .issue_dependencies_summary` returned `{"blocked_by":0,…}`, so both jq paths in upstream's text match the real shapes.

Contract note: the `Blocked by` fallback line in upstream's text is compatible with ADR-0078 §3 (skills-dev keeps a `## Blocked by` section in every ticket body). Port only the tracker doc text; do not port upstream's "omit `## Blocked by` when native edges exist", which ADR-0078 rejected. Keep the bold labels **Blocking**, **Frontier query**, **Make an issue a sub-issue of a parent** and **List the sub-issues of a parent** unchanged, since `to-tickets` pass 3 reads the last two by name (`docs/agents/skill-dependencies.md`, the `to-tickets` → `setup-skills` entry). Keep skills-dev's **Execution map** entry (`:56`), which upstream does not have.

### Item 4 — GitLab MR list flag (PORT NOW)

Upstream `ed0de59`, `issue-tracker-gitlab.md`: `glab mr list -F json` becomes `glab mr list -O json` (upstream issue #1143). skills-dev still has `-F json` at `skills/engineering/setup-skills/issue-tracker-gitlab.md:25`. ADR-0078 §1 ported "`glab -O json`" for `glab issue list` from `5b7cade`, but the MR line was fixed upstream only in this window. `glab` is not installed on this machine, so I could not check the flag myself; the fix rests on upstream's issue #1143 and on consistency with the `glab issue list -O json` line already at `:9`. Upstream left `glab issue view <number> --comments`, "Use `-F json`" unchanged, and so should skills-dev.

### Item 5 — GitLab wayfinder child linking and frontier listing (ADAPT)

Upstream `ed0de59`:

- "**Child ticket**: an issue carrying `Part of #<map>` at the top of its description, linked to the map (`glab issue create --linked-issues <map> --link-type relates_to`), and labels `wayfinder:<type>` …"
- "**Frontier query**: list the map's children with `glab api projects/:id/issues/<map>/links`, keeping open issues that carry a `wayfinder:<type>` label; drop any with an open blocker …"

skills-dev's GitLab Wayfinding entries (`issue-tracker-gitlab.md:43,45`) attach a child only by the `Part of #<map>` line and scope the frontier query to "the map's children" without saying how to find them, so the frontier query has no working enumeration step. Upstream's change fixes that.

The adaptation: put the `--linked-issues` link in the Wayfinding **Child ticket** entry only. Do not add it to the Conventions entry **Attach an issue to a parent issue** (`:10`), and do not rename that entry. `docs/agents/skill-dependencies.md` records that the GitLab seed doc has no **Make an issue a sub-issue of a parent** operation, so `to-tickets` pass 3 falls back to `Part of #<parent>`. A `relates_to` link is not a parent link, and turning it into one would change that contract. Keep the em-dash style of the surrounding skills-dev text. As with item 4, I could not run `glab` locally to confirm `--linked-issues` and `--link-type`.

### Item 6 — Reachable remote before a hosted tracker (PORT NOW)

Upstream `ed0de59`, `setup-matt-pocock-skills/SKILL.md` Section A: "A GitHub or GitLab tracker needs a reachable repo. When the user picks one and no `git remote` points at that host, get the repo URL from them and wire it up (`git init` if needed, `git remote add origin <url>`) before going further. Done when `gh repo view` / `glab repo view` prints the project from inside this directory; if it can't, stop and tell the user what's missing." (upstream issue #1201.)

skills-dev's Section A (`skills/engineering/setup-skills/SKILL.md:53-60`) has the same posture and gap: it offers GitHub or GitLab even when no remote points there, and nothing checks that the recorded tracker is reachable, so later `gh issue create` calls from `to-spec` and `to-tickets` fail. Insert the paragraph after `:60` ("Record the choice …"). Applies cleanly.

### Item 7 — Legacy `CONTEXT.md` rename offer (SKIP, already covered)

Upstream `ed0de59` adds one sentence to exploration: offer to `git mv` a legacy `CONTEXT.md` / `CONTEXT-MAP.md` and rewrite the names in `docs/agents/domain.md`. skills-dev already does more: exploration finds root and per-context legacy files plus every file that mentions them (`setup-skills/SKILL.md:28`), Section D asks, rewrites live references in `CLAUDE.md`, `AGENTS.md` and `docs/agents/*.md`, stops on a `CONTEXT.md`/`GLOSSARY.md` clash, and records a decline (`:78-90`), and the write step uses `git mv` (`:125`). `docs/agents/skill-authoring.md` ("Decisions accepted from upstream", `CONTEXT.md` → `GLOSSARY.md`) records that skills-dev added this migration because upstream had none. Nothing to port.

### Item 8 — File issues into the user's own repo (ADAPT)

Upstream `59db609`, GitHub template: "File issues only into the user's own repo. Never file into `mattpocock/skills` (the repo these skills come from) unless the user owns it. In a fork, `gh` can default to the upstream parent, so before the first `gh issue create` of a session, check the target with `gh repo view --json nameWithOwner` and confirm it with the user if it is not their repo." The trigger was upstream issues #541 to #550, specs and tickets that agents filed into upstream from clones and forks.

skills-dev has only "Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone" (`issue-tracker-github.md:16`). The fork hazard is real for any repo that uses this seed doc: in a fork, `gh` resolves the base repo to the parent unless `gh repo set-default` was run. skills-dev itself is not a fork (`gh repo view --json isFork,parent` returns `"isFork":false,"parent":null`), so the `mattpocock/skills` sentence does not fit. Adapt it to the general rule: before the first `gh issue create` of a session, check `gh repo view --json nameWithOwner`, and confirm with the user when the result is not the repo `git remote -v` names as `origin` (or is a parent the user does not own). Drop the upstream repo name.

### Item 9 — `implement-spec`: a fresh implementer per ticket and for the fixes (ADAPT)

Upstream `a496f55` (with `7739eae`), `skills/engineering/implement-spec/SKILL.md`:

- step 4: "Use **implementer subagents** to implement each ticket" becomes "Use a fresh **implementer subagent** for each ticket";
- step 7: "Fix all issues raised by the code review in a single **implementer subagent**" becomes "… in a single fresh **implementer subagent**";
- a new top-level line, "Start every subagent with a fresh context window."

The PR history matters here: its second commit made the merger fresh too, and its third ("merger subagent need not be fresh") reverted that, so upstream deliberately leaves the merger reusable.

skills-dev's counterparts are `skills/engineering/implement-spec/SKILL.md:40` (step 4, "Use **implementer subagents** to implement each ticket, each in its own worktree on its own branch") and `:56` (**Integration fixer**, "one implementer subagent in its own worktree on the integration tip"). Neither names a `subagent_type` or forbids reuse. The reuse risk is concrete in skills-dev: the integration fixer could be a ticket implementer resumed with `SendMessage`, which then fixes integration findings from memory of one ticket instead of reading the integration tip. That is the same failure that made skills-dev forbid a forked reviewer (`implement-spec/SKILL.md:54`, "dispatch a fresh `general-purpose` agent, never `"fork"`", and `skills/engineering/implement/SKILL.md:20`).

Adaptation, following skills-dev's explicit-type convention (`docs/agents/skill-authoring.md`, "Harness-neutral subagent dispatch", commit `7426dc8`): in step 4, say "a fresh `general-purpose` implementer subagent for each ticket, never `"fork"` and never an earlier implementer resumed with `SendMessage`"; in the **Integration fixer** bullet, say "one fresh implementer subagent (`general-purpose`, never a ticket implementer resumed with `SendMessage`)". Leave the merger and the optional exploration subagent as they are, matching upstream's final decision. Do not port the harness-neutral "fresh context window" sentence itself. This touches no cross-skill contract: the `implement` commit-only brief, the `<seam>: <test>` result lines and the `render_review_brief.py` call are unchanged.

### Item 10 — "Start every subagent with a fresh context window" (SKIP, one ADAPT)

Upstream `7739eae` adds the sentence to eight skills and a rule to `CLAUDE.md`: "Some harnesses (Codex, for one) fork the parent conversation by default, and a fork inherits the parent's context." The rationale is harness-neutrality. skills-dev is Claude-Code-only and rejected harness-neutral dispatch (`docs/agents/skill-authoring.md`, "Harness-neutral subagent dispatch", upstream `14bfbbd`/`c0d6901`); it declares `subagent_type` instead (`7426dc8`). In Claude Code, an Agent call starts with a fresh context unless it asks for `subagent_type: "fork"`, so a typed dispatch already gets what the sentence asks for. Per site:

- `dev/code-review`: finders are `Explore` agents in a single foreground message (`skills/dev/code-review/SKILL.md:81`; `docs/workflow.md:547,648,684`). Already fresh. Skip.
- `codebase-design/DESIGN-IT-TWICE.md:21`: `subagent_type: "general-purpose"`. Skip.
- `improve-codebase-architecture/SKILL.md:27`: `subagent_type=Explore`. Skip.
- `research/SKILL.md:6`: `subagent_type: "general-purpose"`. Skip.
- `learning/grilling/SKILL.md:57`: `subagent_type: "Explore"`. Skip.
- `implement-spec`: covered by item 9.
- `wayfinder/SKILL.md:121`: "spin up a `/research` subagent" names no type. ADAPT: "spin up a `general-purpose` subagent (`subagent_type: "general-purpose"`) that runs `/research`". This is the only untyped dispatch among the eight sites, and the fix follows `7426dc8`'s convention rather than upstream's wording. Wayfinder's step 5 already carries the "open no PR" guardrail from `8295b8e`.
- `chief-of-staff`: no counterpart.

### Item 11 — `chief-of-staff` wiki memory (SKIP)

Upstream `5beb35b` gives `skills/in-progress/chief-of-staff/SKILL.md` a "Wiki" section (an `index.md` plus one page per topic, maintained by ingest, query and lint) and a "Write history, not the present" rule: date every claim, cite the commit that a claim about code was true at, never write "currently" without a date or commit, and supersede rather than rewrite. ADR-0078 §4 and "Considered Options" rejected adding `chief-of-staff`: upstream marks it experimental, and it overlaps `task-execution` and `goal-loop`. The skill is still under `in-progress/`, so the reason holds. The "write history, not the present" rule is a good idea for any long-lived agent memory. Neither `skills/planning/goal-loop/SKILL.md` nor `skills/planning/task-execution/SKILL.md` keeps persistent memory today (no matches for wiki, memory or dated claims), so there is no skill to host it now. Record it as inspiration only.

### Items 12 to 15 — Governance, docs, release, wizard (SKIP)

- `59db609` issue forms (`.github/ISSUE_TEMPLATE/bug.yml`, `config.yml`, `idea.yml`) and the new `CONTRIBUTING.md` route upstream's own public issue traffic. ADR-0078 §4 skips "upstream governance scaffolding (`SCOPE.md`, `.out-of-scope/`, issue forms)".
- `ed0de59` `docs/engineering/domain-modeling.md` fixes a FAQ heading that read "`GLOSSARY.md` and not `GLOSSARY.md`" (a rename artefact) and points users at the new setup migration. skills-dev has no user-facing `docs/engineering/` tree, and its migration is already documented (item 7).
- `d1478fc` bumps `package.json` and `.claude-plugin/plugin.json` to 1.3.2, writes the CHANGELOG and deletes consumed changesets. ADR-0078 §4 skips plugin and release tooling.
- `wizard/template.sh`: no change in `49dd158..a496f55`. skills-dev already carries `c20facd`'s bash 3.2 apostrophe fix (ADR-0078 §1), which upstream `main` has not merged. Nothing to do; recheck at the next sync whether upstream merges `origin/wizard-bash32-apostrophe` in some other form.

## 5. Port-today shortlist (prioritized)

1. `setup-skills/issue-tracker-github.md`: move **Blocking** into Conventions with the `gh` 2.94+ `--blocked-by` / `--add-blocked-by` forms and add **Count open blockers**; point the Wayfinding entries at them (item 3, `ed0de59`).
2. `setup-skills/issue-tracker-github.md`: comment-then-close in **Close** (item 1, `ed0de59`).
3. `setup-skills/issue-tracker-github.md`: read a PR with `gh pr view` and then `--comments` (item 2, `ed0de59`).
4. `setup-skills/issue-tracker-github.md`: check `gh repo view --json nameWithOwner` before the first `gh issue create`, without the upstream repo name (item 8, `59db609`).
5. `setup-skills/SKILL.md` Section A: wire up and verify a reachable remote before recording a GitHub/GitLab tracker (item 6, `ed0de59`).
6. `setup-skills/issue-tracker-gitlab.md`: `glab mr list -O json`, and link wayfinder children with `--linked-issues` plus a links-based frontier listing, in the Wayfinding section only (items 4 and 5, `ed0de59`).
7. `implement-spec/SKILL.md`: a fresh typed implementer per ticket and a fresh integration fixer, never `"fork"` or a resumed implementer; merger unchanged (item 9, `a496f55`).
8. `wayfinder/SKILL.md:121`: give the research dispatch an explicit `general-purpose` type (item 10, `7739eae`).

Items 1 to 6 all touch `skills/engineering/setup-skills/` and can ship as one change. Item 7 is independent. Item 8 is a one-line follow-up. Repos set up earlier keep their old `docs/agents/issue-tracker.md` until they rerun `/setup-skills`, whose seed-sync step (`ef4940c`) merges the new lines in. That includes skills-dev's own `docs/agents/issue-tracker.md`.

## 6. Open questions

1. **Baseline wording.** ADR-0078 names `c20facd` as the next baseline, but `c20facd` is not on upstream `main`. Should the sync record for this window (a new ADR, by the pattern of ADR-0078, or an amendment) name `a496f55` as the next baseline and note that `c20facd` stays a skills-dev-only fix until upstream merges it?
2. **`glab` flags.** `glab mr list -O json`, `glab issue create --linked-issues … --link-type relates_to` and `glab api projects/:id/issues/<map>/links` were not verified here, because `glab` is not installed. Verify them against `glab --help` or the glab docs before shipping items 4 and 5, or ship them on upstream's word as ADR-0078 did for the earlier `glab` fixes.
3. **`implement-spec` frontier on GitHub.** With **Count open blockers** in the tracker doc, should `implement-spec` step 1 or 6 cite it by name as the frontier test? That would add a new `implement-spec` → `setup-skills` contract entry to `docs/agents/skill-dependencies.md`. It is out of scope for a straight port.
4. **`to-tickets` pass 2.** Should pass 2 ("create native blocking links", `to-tickets/SKILL.md:152`) cite the **Blocking** operation by name once it sits in Conventions, the same way pass 3 cites the sub-issue operations? Same contract consideration as question 3.
5. **"Write history, not the present".** Is there a skills-dev home for `5beb35b`'s dated, commit-cited claim rule? Candidates are auto-memory guidance or a future `goal-loop` memory section. No action proposed today.
