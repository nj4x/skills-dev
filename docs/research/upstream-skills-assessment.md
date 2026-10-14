# Upstream skills assessment — `mattpocock/skills` → `skills-dev` (2026-10-13)

## Question

What changes in `/Users/roman/projects/skills` (upstream, `https://github.com/mattpocock/skills.git`) should `/Users/roman/projects/skills-dev` adopt? Which upstream-only skills are worth adding? What else (repo docs, conventions, hooks, MCP packages, install scripts, `AGENTS.md`/`CLAUDE.md` guidance) differs in a way that matters?

## Short answer

Nearly everything upstream shipped since the last sync is small and surgical: one-sentence guardrails in skills that skills-dev already carries, plus tracker-command fixes in the `setup-skills` seed docs. None of it conflicts with skills-dev's deliberate divergences (requirements corpus, lineage, critic hand-offs, mcp-vectors search, say-cue hooks). The one new upstream skill (`chief-of-staff`) is an experimental in-progress stub and should not be added. No upstream-only skill is newly worth adding; `ask-matt` remains "inspiration, not a port".

Prioritized recommendations:

| # | Action | Upstream commit(s) | skills-dev target | Class | Priority |
|---|---|---|---|---|---|
| 1 | Fix GitHub/GitLab tracker commands in the seed docs (issue read via `--json`, external-PR list via REST, `glab -O json`, `<child-iid>`) and add the "make a sub-issue" operation | `5b7cade`, `e0efb6e`, `cffab50` | `skills/engineering/setup-skills/issue-tracker-github.md`, `issue-tracker-gitlab.md` | Port | High |
| 2 | `setup-skills`: create configured triage labels the tracker lacks | `5b7cade` | `skills/engineering/setup-skills/SKILL.md:128-130` | Port | High |
| 3 | `wizard/template.sh`: readline input, `.env` quoting/decoding, mode-0600 env file, symlink-safe writes, EOF handling | `868c4cf`, `49dd158` | `skills/engineering/wizard/template.sh` | Port verbatim | High |
| 4 | `code-review`: discover the repo's own standards files (`CODING_STANDARDS.md`, `CONTRIBUTING.md`, …) and feed them to the Standards finder | `3da8c01` | `skills/dev/code-review/docs/workflow.md` (Finder C, L526+) | Adapt | High |
| 5 | `wayfinder`: no triage labels on map/tickets; real ids (no placeholder `#<n>`); push research branch, no PR; resolve by the `wayfinder:<type>` label | `8295b8e` | `skills/engineering/wayfinder/SKILL.md:71,120,121,130` | Port | Medium |
| 6 | `diagnosing-bugs`: prove a forced mutation landed (diff vs pristine copy) before trusting the red | `f3fc563` | `skills/engineering/diagnosing-bugs/SKILL.md:125` | Port | Medium |
| 7 | `tdd`: one-line "catches / misses" note per proposed seam | `3f59913` | `skills/engineering/tdd/SKILL.md:25` | Port | Medium |
| 8 | `grilling`: word each question so "yes" accepts the recommendation | `95249b0` | `skills/learning/grilling/SKILL.md:39` | Adapt (multi-question rounds) | Medium |
| 9 | `to-tickets`: when the source is an existing issue, publish tickets as its sub-issues | `cffab50`, `9e2abf8` | `skills/engineering/to-tickets/SKILL.md:146` | Adapt (keep `Blocked by` body section) | Medium |
| 10 | `teach`: anchor workspace paths to the invocation directory; vary correct-answer position in quizzes | `ad5400b` | `skills/learning/teach/SKILL.md:16,93` | Port | Low |
| 11 | `implement`: when passed a ticket reference, fetch it and state its title before starting | `6d6a5b9` | `skills/engineering/implement/SKILL.md` | Adapt (fold into existing ticket-read rule) | Low |

Skip: `chief-of-staff`, `claude-handoff` changes, upstream `implement`'s Skill-tool wording, `handoff` temp-dir fix (already equivalent locally), `SCOPE.md`/`.out-of-scope/`/issue-form/triage-workflow scaffolding, plugin-marketplace/changeset release machinery, `resolving-merge-conflicts` removal.

## 1. Repo relationship

The two repos share **no git history**. skills-dev's root commit is `ff52648` (2026-07-24, "Initial commit: skills-dev curated collection with 20 original + 26 adapted skills"); upstream's is `985d8fc` (2026-02-03, "Initial commit"). skills-dev is a curated copy that cherry-picks upstream by hand and records each sync in `docs/research/`:

- `docs/research/upstream-skills-sync-2026-08-20.md` — window `8b36d4f..0ab1b63`, landed as skills-dev `9d4ae99` and `11e8fee`.
- `docs/research/upstream-skills-sync-2026-09-29.md` — window `0ab1b63..d81f3a1`, landed as skills-dev `0816eb5` (2026-09-29, "feat: adopt upstream GLOSSARY.md convention and port skill fixes…").

So the **sync baseline is upstream `d81f3a1`** (2026-09-29). `git -C /Users/roman/projects/skills merge-base --is-ancestor d81f3a1 HEAD` succeeds, and the unsynced window is `d81f3a1..49dd158` (upstream HEAD, 2026-10-09): 37 non-merge commits, 96 files, +1276/−706. Of those, only 18 files are under `skills/`; most of the rest are `docs/engineering/*.md` page rewrites (`dfe7549`, "docs: unslop every docs page"), changesets, `CHANGELOG.md`, `README.md`, and new repo-governance files.

To catch anything earlier syncs missed, I also diffed every paired skill directory with em-dashes normalized (skills-dev keeps em-dashes by decision, `docs/agents/skill-authoring.md`, "Em-dash removal"). Every residual difference outside the `d81f3a1..HEAD` window traces to a recorded local divergence or an em-dash rewrite, not to an unported upstream change. Notably `engineering/retro` ↔ `session/retro` and `productivity/to-questionnaire` ↔ `publishing/to-questionnaire` are identical modulo em-dashes, and `wizard/SKILL.md` is byte-identical.

## 2. Skill-to-skill map

Upstream skills (38, `fd SKILL.md skills` in upstream) against skills-dev (53):

| Upstream | skills-dev | Status in window `d81f3a1..HEAD` |
|---|---|---|
| `engineering/ask-matt` | — | upstream-only; 2 small edits (`954ee7f`, `c5b9869`) |
| `engineering/code-review` | `dev/code-review` | local rewrite; upstream `3da8c01` worth adapting |
| `engineering/codebase-design` | same path | no change |
| `engineering/diagnosing-bugs` | same path | upstream `f3fc563` to port |
| `engineering/domain-modeling` | same path | no change |
| `engineering/grill-with-docs` | same path | no change |
| `engineering/implement` | same path | local rewrite; upstream `6d6a5b9`, `e48341a`, `04320ee` |
| `engineering/implement-spec` | same path | no change upstream; local rewrite (`80865d7`) |
| `engineering/improve-codebase-architecture` | same path | no change |
| `engineering/pr` | `publishing/pr` | no change (local "Before writing" section is ahead) |
| `engineering/prototype` | same path | no change |
| `engineering/research` | same path | no change |
| `engineering/retro` | `session/retro` | no change; identical |
| `engineering/setup-matt-pocock-skills` | `engineering/setup-skills` | `5b7cade`, `e0efb6e`, `cffab50` to port |
| `engineering/tdd` | same path | `3f59913` to port |
| `engineering/to-spec` | same path | no change |
| `engineering/to-tickets` | same path | `cffab50`, `9e2abf8` to adapt |
| `engineering/triage` | same path | no change (local diff: tracker pointer + search guidance) |
| `engineering/wayfinder` | same path | `8295b8e` to port |
| `engineering/wizard` | same path | `868c4cf`, `49dd158` (`template.sh`) to port |
| `productivity/grilling` | `learning/grilling` | `95249b0` to adapt |
| `productivity/handoff` | `session/handoff` | `4f4e943`, `0f5e033` — already equivalent locally |
| `productivity/teach` | `learning/teach` | `ad5400b` to port |
| `productivity/to-questionnaire` | `publishing/to-questionnaire` | identical |
| `productivity/wait-what` | `session/wait-what` | no change |
| `productivity/writing-for-agents` | `dev/writing-for-agents` | no change |
| `productivity/grill-me` | — | deliberately dropped (`docs/agents/disposition-20260724-190949.md`) |
| `misc/git-guardrails-claude-code` | `dev/git-guardrails-claude-code` | no change |
| `misc/migrate-to-shoehorn`, `misc/scaffold-exercises`, `misc/setup-pre-commit` | — | skip (TS/course-specific; upstream now declares `misc/` frozen, `.out-of-scope/frozen-misc-skills.md`) |
| `in-progress/chief-of-staff` | — | **new** upstream-only (`e47c149`…`6fd9479`) |
| `in-progress/claude-handoff`, `loop-me`, `setup-ts-deep-modules`, `writing-beats`, `writing-fragments`, `writing-shape` | — | skip (unfinished; overlaps noted in the 08-20 sync) |
| — (removed upstream `daa01d8`, 2026-09-24) | `engineering/resolving-merge-conflicts` | local-only now |

skills-dev-only skills (critic, repeat, goal-loop, task-execution, testing, refactor-tests, refactor-agents-md, setup-lineage, requirements/*, email/*, notifications/*, session/{continue,hs,mark}, dev/{prompt-authoring,skill-authoring,test-mcp,tool-authoring}, publishing/{html-view,interview-style-doc-building}, research/search-codebase) have no upstream counterpart and are out of scope here.

## 3. Changes to adopt in paired skills

### 3.1 setup-skills tracker seed docs (Port, High)

Upstream `5b7cade` and `e0efb6e` fix commands that are wrong or fragile; `cffab50` adds a sub-issue operation that `to-tickets` and `wayfinder` then reference.

- **Read an issue.** Upstream now reads `gh issue view <number> --json number,title,body,labels,comments` (`skills/engineering/setup-matt-pocock-skills/issue-tracker-github.md:8`). skills-dev still says `gh issue view <number> --comments`, "filtering comments by `jq`" (`skills/engineering/setup-skills/issue-tracker-github.md:8`) — `--comments` output is not JSON, so the `jq` instruction cannot work as written. The "fetch the relevant ticket" section repeats the old command (`skills/engineering/setup-skills/issue-tracker-github.md:34`); upstream points it back to **Read an issue**.
- **External PRs for triage.** Upstream switched to `gh api --paginate 'repos/{owner}/{repo}/pulls?state=open' --jq '… select(.author_association | IN("OWNER","MEMBER","COLLABORATOR") | not) …'` (upstream `issue-tracker-github.md:24`). skills-dev keeps `gh pr list … authorAssociation` (`skills/engineering/setup-skills/issue-tracker-github.md:23`). The change came from upstream branch `fix/468-github-external-pr-list` (merge `93497a8`); the REST endpoint exposes `author_association` directly, so the filter runs inside `--jq` instead of being left to the agent.
- **Sub-issues.** New bullet "Make an issue a sub-issue of a parent" (`gh issue create --parent`, `gh issue edit --add-sub-issue`, REST fallback with the database id; upstream `issue-tracker-github.md:10`), and the wayfinder **Child ticket** bullet now points to it (upstream L42) instead of the vague "`gh api` on the sub-issues endpoint" still in skills-dev (`issue-tracker-github.md:41`).
- **GitLab.** `glab issue list -F json` → `-O json` and `:iid` → `<child-iid>` (upstream `issue-tracker-gitlab.md:9,44`). skills-dev still has `-F json` at `skills/engineering/setup-skills/issue-tracker-gitlab.md:9,44`.
- **triage-labels.md.** "Edit the right-hand column" → "Edit the 'Label in our tracker' column" (upstream `triage-labels.md:15`; skills-dev `skills/engineering/setup-skills/triage-labels.md:15`). Cosmetic, port with the rest.

These are seed templates copied into target repos, so a fix here propagates to every repo that runs `/setup-skills` afterwards. Repos already set up keep the old text in their own `docs/agents/issue-tracker.md`.

### 3.2 setup-skills: create missing triage labels (Port, High)

Upstream `5b7cade` adds one sentence: "When Section B ran on GitHub or GitLab, create each configured label the tracker lacks (`gh label create` / `glab label create`)" (upstream `skills/engineering/setup-matt-pocock-skills/SKILL.md:104`). skills-dev's Section B collects label strings (`skills/engineering/setup-skills/SKILL.md:55-61`) but never creates them, so `triage` and `to-tickets` (which applies `ready-for-agent`) can hit a missing-label error on first use. Insert after `skills/engineering/setup-skills/SKILL.md:128`.

### 3.3 wizard template.sh (Port verbatim, High)

skills-dev's `skills/engineering/wizard/template.sh` is the unmodified upstream copy from the 08-20 sync (`11e8fee`; only moved since, `e42e1dd`), and `SKILL.md` is byte-identical. Upstream `868c4cf` (fixes #741 #770 #774 #811 #852) and `49dd158` (fixes #1220 #1142 #1081 #1041 #1003) change the template:

- `ask` uses `read -e` (Readline) with colour codes wrapped in `\001…\002` so the cursor lands correctly, and fails at EOF with no input instead of looping.
- `write_env` writes `KEY='VALUE'` (single-quoted, embedded quotes escaped), creates the env file at mode 0600 (`umask 077`), and writes through a symlink while keeping the existing mode.
- `_existing` decodes single-quoted values and plain double-quoted dotenv values, and refuses to decode values containing `\`, `$` or `"` (asks again instead).
- `clear` falls back cleanly when `tput clear` fails.

Since there is no local modification to preserve, copy the upstream file over. The local file still contains the old opener warning (`warn "couldn't open a browser…"`) that upstream replaced; check the opener section of the new file when porting.

### 3.4 code-review: discover the repo's standards files (Adapt, High)

Upstream `3da8c01` changes step 3 to "Search the repo for every file that documents how code should be written. When `CODING_STANDARDS.md` or `CONTRIBUTING.md` exists, it must be on the list" (upstream `skills/engineering/code-review/SKILL.md:36`), and adds "Issue both sub-agent calls together, in the foreground" (L60).

skills-dev's `dev/code-review` already has the foreground rule, more strictly ("Dispatch all finders in a single foreground message…", `skills/dev/code-review/SKILL.md:80`; "Fan-out dispatch rule", `skills/dev/code-review/docs/workflow.md:484`). But it ships its own bundled standards (`docs/kotlin-standards.md`, `python-standards.md`, `testing-standards.md`; table at `skills/dev/code-review/SKILL.md:168-170`) and has no step that searches the target repo for its standards documents. `rg -i 'CODING_STANDARDS|CONTRIBUTING' skills/dev/code-review` finds only `docs/smell-baseline.md:7`, which says a documented repo standard overrides the smell baseline — without any step that would find one. Also relevant: upstream `retro` (identical to `skills/session/retro/SKILL.md`) routes judgement-call findings into `CODING_STANDARDS.md`, so a reviewer that never reads that file breaks the retro→review loop.

Adapt: add a discovery step to the orchestrator (before Step 4.1 in `docs/workflow.md`) that lists repo standards files (`CODING_STANDARDS.md`, `CONTRIBUTING.md`, `AGENTS.md`/`CLAUDE.md` coding sections, `docs/**/standards*`), and pass the list to Finder C ("Quality & Standards", `docs/workflow.md:526`) and the low-effort single-agent brief. Keep the bundled language standards as the fallback.

### 3.5 wayfinder guardrails (Port, Medium)

Upstream `8295b8e` adds four one-line rules to `skills/engineering/wayfinder/SKILL.md`:

1. `wayfinder:` labels are the only labels a map and its tickets carry, never a triage label like `ready-for-agent` (upstream L65). Insert at skills-dev L71. This matters more here than upstream: skills-dev's `to-tickets` applies `ready-for-agent`, and an AFK agent polling that label would pick up decision tickets.
2. In the wiring pass, write cross-references with real ids: a placeholder `#<n>` auto-links to an unrelated issue (upstream L114). skills-dev L120.
3. Push the research branch but open no PR: it is never merged (upstream L115). skills-dev L121.
4. Resolve a ticket as the type its `wayfinder:<type>` label names; the body never states the type (upstream L124). skills-dev L130 — prepend to the existing step, keep the local ADR/critic text.

Keep skills-dev's `/research`, `/grilling` phrasing rather than upstream's "call the Skill tool with …" (see §5).

### 3.6 diagnosing-bugs: prove the forced mutation landed (Port, Medium)

Upstream `f3fc563`: step 2 of the seam fix becomes "Watch it fail. If you forced the red by mutating code or a fixture, `diff` against a pristine copy to prove the mutation landed before you trust it" (upstream `skills/engineering/diagnosing-bugs/SKILL.md:125`). skills-dev still has the bare "Watch it fail." (`skills/engineering/diagnosing-bugs/SKILL.md:125`). One-sentence port; no contract impact.

### 3.7 tdd: catches/misses note per seam (Port, Medium)

Upstream `3f59913` adds "Give each proposed seam a one-line note on what it catches and what it misses" after the seam question (upstream `skills/engineering/tdd/SKILL.md:24`). skills-dev's line is conditional — "When no seam is agreed, ask: …" (`skills/engineering/tdd/SKILL.md:25`) because seams can come pre-agreed from a ticket or `implement` brief. Append the sentence there; it applies only on the asking path, which is the right scope.

### 3.8 grilling: "yes" accepts the recommendation (Adapt, Medium)

Upstream `95249b0` (#706) adds "Word each question so 'yes' accepts your recommended answer" (upstream `skills/productivity/grilling/SKILL.md:24`). skills-dev's round format allows several questions per round (`skills/learning/grilling/SKILL.md:39-51`), so a bare "yes" to a multi-question round is ambiguous. Adapt to "Word each question so 'yes' accepts its ➡️ recommendation; a bare 'yes' to a round accepts every recommendation in it", or drop the second clause if that is not the intended semantics. Contract check: `grilling` → `critic` (`docs/agents/skill-dependencies.md`) is unaffected.

### 3.9 to-tickets: sub-issues under the source issue (Adapt, Medium)

Upstream `cffab50` + `9e2abf8`: "If the source was an existing issue, make each ticket its sub-issue (tracker doc's operation)", and the template's "Blocked by" section is omitted "when blockers were set as native edges" (upstream `skills/engineering/to-tickets/SKILL.md:63,101`).

Adopt the sub-issue part in skills-dev's real-tracker publish step (`skills/engineering/to-tickets/SKILL.md:146`) as a third pass after native blocking links, using the operation from §3.1. It also gives `implement-spec` a reliable way to enumerate a spec's tickets (its precondition only says tickets are "linked to it", `skills/engineering/implement-spec/SKILL.md:28`).

**Do not** adopt the "omit Blocked by" part. skills-dev's critic review validates the `Blocked by` graph in the draft files (`skills/engineering/to-tickets/SKILL.md:139`), the local tracker uses that field as the task graph (`skills/engineering/implement-spec/SKILL.md:27`), and on a partial publish the body text is the only surviving record of edges that never got created.

### 3.10 teach (Port, Low)

Upstream `ad5400b`: workspace paths resolve from the directory `/teach` was run in, only `*-FORMAT.md` links resolve from the skill folder (upstream `skills/productivity/teach/SKILL.md:12`); and "Vary which position holds the correct answer across questions… formatting or order" (L110). skills-dev equivalents: `skills/learning/teach/SKILL.md:16` and `:93`. The first matters for a symlinked install like skills-dev's, where the skill folder is not the workspace.

### 3.11 implement: state the ticket title (Adapt, Low)

Upstream `6d6a5b9`: "If the user passes a ticket reference, fetch it from the issue tracker and state its title before starting. If the reference is ambiguous, ask" (upstream `skills/engineering/implement/SKILL.md:9`). skills-dev's `implement` is a local rewrite and already fetches GitHub tickets (`skills/engineering/implement/SKILL.md:54`), but only in the checklist workflow, late. A one-line addition near the top (before the branch check, L7) catches a wrong ticket number before any edit. Upstream's other `implement` changes (`e48341a`, `04320ee`: "call the Skill tool with 'tdd'/'code-review'") are wording only and conflict with local convention — skip.

## 4. Upstream-only skills

| Skill | Purpose | Depends on | Fit with skills-dev | Recommendation |
|---|---|---|---|---|
| `in-progress/chief-of-staff` (new, `e47c149`…`6fd9479`, 45 lines) | Long-running single-session coordinator: all work in background subagents, communicate via context pointers, improve the environment ("pit of success", "no workarounds") on every turn | none named | Overlaps `planning/task-execution` (fan-out to sub-agents) and `planning/goal-loop` (persistent loop). Upstream marks it experimental; five commits in two days, last titled "Updates" | **Skip.** Revisit if it graduates. Its "Strategic View" checklist (constrained APIs, lint rules, `CODING_STANDARDS.md`, log/DB/browser access) could inspire a section in `session/retro` or `task-execution`, but nothing to port yet |
| `engineering/ask-matt` (97 lines + `PHASE-BOUNDARIES.md`) | Router over the upstream catalogue | the catalogue | skills-dev has no router and 53 skills. Content is upstream's catalogue | **Adapt later, as inspiration** (unchanged from `docs/research/upstream-skills-sync-2026-08-20.md` item 16). One new idea worth stealing if a router is written: "read that skill's SKILL.md before stating what it does" (`954ee7f`, upstream `ask-matt/SKILL.md:11`) |
| `in-progress/claude-handoff` | Handoff via `claude --bg` | — | Overlaps `session/handoff` | Skip. Its fix `07b7105` (pass the summary via a temp file, `-- "$(cat file)"`, to avoid shell interpolation of backticks and `$`) is the right pattern if skills-dev ever adds a `--bg` launch |
| `productivity/grill-me` | Grilling alias | grilling | Deliberately dropped | Skip (do not reopen) |
| `misc/*` (3) | TS/course tooling | — | No fit; upstream froze `misc/` (`.out-of-scope/frozen-misc-skills.md`) | Skip |
| other `in-progress/*` (5) | Unfinished | — | Overlaps noted 08-20 | Skip |

## 5. Intentional divergences to keep

These differences showed up in the diff and are deliberate; future syncs should filter them out.

- **Cross-skill invocation phrasing.** Upstream writes "call the Skill tool with 'x'" (e.g. `e48341a`, wayfinder `8295b8e`). skills-dev uses `/skill-name` in prose and `Skill(name, args: …)` for programmatic hand-offs (`docs/agents/skill-authoring.md`, "Cross-skill invocation policy"). Port the substance of each change, not its wording.
- **Em-dashes.** Kept by decision (`docs/agents/skill-authoring.md`, "Em-dash removal"); upstream's `CLAUDE.md` still bans them.
- **`implement` and `implement-spec`.** Local rewrites with gated Test → Review → Checklist → Commit, fresh-agent review via `render_review_brief.py`, and implement-spec delegating each ticket to `Skill("implement")` (`80865d7`, `b171a39`; contracts in `docs/agents/skill-dependencies.md`). Upstream's versions are far simpler; do not re-sync.
- **`dev/code-review`.** Local rewrite (effort levels, four finders, adversarial verify, mutating modes, Kotlin/Python standards). Only the standards-discovery idea from `3da8c01` crosses over (§3.4).
- **`diagnosing-bugs` Phase 6 hand-off to `/improve-codebase-architecture`** (`skills/engineering/diagnosing-bugs/SKILL.md:130,140`). Upstream removed it and now routes post-bug reflection to `/retro` through `ask-matt` (`c5b9869`). Keep the local hand-off (recorded in `skill-authoring.md`). Optionally add one clause suggesting `/retro` after the fix, since skills-dev has `session/retro`.
- **`resolving-merge-conflicts`.** Upstream deleted it as "No longer needed" (`daa01d8`). skills-dev keeps it and it is installed in this session. No reason to follow.
- **`handoff` temp dir.** Upstream `4f4e943`/`0f5e033` resolve `$TMPDIR`, else `/tmp`, else `%TEMP%`. skills-dev already computes `${TMPDIR:-/tmp}/handoff-…md` with a no-pre-create rule (`skills/session/handoff/SKILL.md:93-103`), which is stricter. Nothing to port.
- **Local search guidance** (mcp-vectors conceptual search lines in `diagnosing-bugs`, `research`, `triage`), **requirements corpus**, **lineage**, **critic hand-offs**, **say-cue hooks** (`hooks/`), and **MCP packages** (`mcp/mcp-vectors`, `mcp/mcp-wrapper`, `mcp/mcp_common`). Upstream has no `hooks/` or `mcp/` directories at all, so there is nothing to compare.
- **Native question tool.** Upstream's new `.out-of-scope/native-question-tool.md` rules out `AskUserQuestion` for grilling. skills-dev grilling already asks in plain text; `to-spec`/`to-tickets` use `AskUserQuestion` only as a headless-detection probe (`skills/engineering/to-spec/SKILL.md:14`, `skills/engineering/to-tickets/SKILL.md:24`). No conflict.

## 6. Repo-level differences

- **Governance scaffolding** — `SCOPE.md`, `.out-of-scope/*.md` (9 records), `.github/ISSUE_TEMPLATE/{bug,idea,config}.yml`, `.github/workflows/{triage-label,needs-info}.yml`, `docs/agents/triage-labels.md` (`f0588cd`, `423ed08`, `4d04daa`, `8267225`). These serve a public repo with outside issue traffic. skills-dev is a personal workspace with no `.github/` directory and records rejected upstream directions in `docs/agents/skill-authoring.md` instead. **Skip.** Two small follow-ons are worth considering: skills-dev ships `engineering/triage` but has no `docs/agents/triage-labels.md` and no "Triage labels" block in `AGENTS.md` (compare upstream `CLAUDE.md`, "## Agent skills / ### Triage labels"); running `/setup-skills` on skills-dev itself would add both if triage is used here.
- **Install route.** Upstream ships a Claude Code plugin with marketplace and self-updating installs (`README.md`, `b0618bc`, `542543a`; `.agents/adr/0002-ship-as-a-claude-code-plugin.md`, updates of 2026-10-07/08) plus a dev-only `scripts/link-skills.sh` that symlinks every non-`misc`/`deprecated` skill into `~/.claude/skills` and `~/.agents/skills`, with a guard against a destination that is itself a symlink into the repo. skills-dev's `README.md` "Installation" says to ask the agent to link skills, or use `npx skills add`. **Optional adapt (Low):** a local `scripts/link-skills.sh` (Claude-only destination, category-aware, skipping nothing or a configurable list) would make the documented `ln -s` loop in `docs/agents/skill-authoring.md` reproducible. The plugin/marketplace/changeset/version machinery (`package.json`, `.changeset/`, `scripts/sync-plugin-version.mjs`) is release tooling for a published package: skip.
- **`.out-of-scope/subagent-recursion.md`** (`4d04daa`) argues skills should not carry guards against sub-agents re-invoking skills. skills-dev's `implement` and `code-review` carry dispatch rules ("never `fork`", "never an inline `Skill("code-review")`", foreground-only fan-out) whose purpose is fresh context and correct waiting, not recursion depth. They are not the kind of guard upstream rejects; keep them.
- **`.out-of-scope/lazy-load-writing-for-agents.md`** (`8267225`) confirms `retro` must load `writing-for-agents` on every run. skills-dev's `session/retro` is identical to upstream, so this already holds. Keep it if `retro` is edited.

## 7. Dependency-contract and risk notes

Checked against `docs/agents/skill-dependencies.md`:

- `to-tickets` → `setup-skills`: §3.1 and §3.9 must land together. If `to-tickets` starts calling "the tracker doc's sub-issue operation" before the seed doc has one, existing target repos (whose `docs/agents/issue-tracker.md` was written from the old seed) will lack it. Phrase the `to-tickets` step with a fallback: "use the tracker doc's sub-issue operation if it has one; otherwise put `Part of #<parent>` at the top of each ticket body".
- `implement-spec` → `to-spec` + `to-tickets`: unaffected by sub-issues (additive). Unaffected by `Blocked by` as long as the omit-section change is not ported (§3.9).
- `implement` → `testing` + `dev/code-review` + `publishing/pr`: §3.11 adds a read before the first edit only; the review brief and gates are untouched.
- `dev/code-review` standards discovery (§3.4) changes the finder prompts that `render_review_brief.py` hands off to. The brief text lives in `skills/engineering/implement/review-brief.md`; no brief change is needed if discovery happens inside code-review's own orchestrator.
- `learning/grilling` → `planning/critic` and `engineering/grill-with-docs` → `learning/grilling`: §3.8 changes question wording only.
- `engineering/wayfinder`: §3.5 adds a label prohibition. skills-dev's `to-tickets` applies `ready-for-agent`; nothing in wayfinder currently applies triage labels (`rg ready-for skills/engineering/wayfinder` is empty), so the rule is a guardrail, not a behaviour change.
- `wizard/template.sh` (§3.3) changes `.env` quoting to `KEY='VALUE'`. Wizards generated from the old template and re-run against an env file the old template wrote will still read it (the new `_existing` passes unquoted values through). New files are mode 0600, which can surprise a tool that reads `.env` as another user.

## 8. Sync record (2026-10-13)

This document is the sync note for this window (ADR-0078, Consequences). The sync was applied through spec #100 and its tickets 01–06 (#102–#107).

- **Synced window:** upstream `d81f3a1..c20facd`. The assessment above was written against `49dd158`. During implementation the wizard pin moved one commit later, to `c20facd` (2026-10-13, "wizard: keep apostrophes intact on bash 3.2 when Enter keeps current"). At `49dd158` the template fails the single-quote round-trip on macOS bash 3.2. `49dd158..c20facd` changes only `skills/engineering/wizard/template.sh` and one changeset file. The user approved the new pin on 2026-10-13.
- **Next sync baseline:** upstream `c20facd`. The next assessment starts from `git log --no-merges c20facd..HEAD`.

Recommendations from the "Short answer" table, as applied:

| # | Item | Class | Result | Applied by |
|---|---|---|---|---|
| 1 | Tracker seed-doc command fixes and the "make a sub-issue" operation | Port | Applied | 01 (#102) |
| 2 | `setup-skills` creates missing triage labels | Port | Applied | 02 (#103) |
| 3 | `wizard/template.sh` replaced with upstream `c20facd`, plus `tests/wizard/template_test.sh` | Port verbatim | Applied | 03 (#104) |
| 4 | `code-review` repo standards discovery | Adapt | Applied | 04 (#105) |
| 5 | `wayfinder` guardrails | Port | Applied | 05 (#106) |
| 6 | `diagnosing-bugs` forced-mutation diff | Port | Applied | 06 (#107) |
| 7 | `tdd` catches/misses note per seam | Port | Applied | 06 (#107) |
| 8 | `grilling` "yes" accepts the recommendation | Adapt | Applied | 06 (#107) |
| 9 | `to-tickets` sub-issues under the source issue, `Blocked by` kept | Adapt | Applied | 01 (#102) |
| 10 | `teach` invocation-directory paths and varied answer position | Port | Applied | 06 (#107) |
| 11 | `implement` states the ticket title before the first edit | Adapt | Applied | 06 (#107) |

Skip and keep items are unchanged by this sync: `chief-of-staff` and the other `in-progress/*` and `misc/*` skills, `ask-matt`, `claude-handoff`, upstream's "call the Skill tool" wording, upstream's `implement` rewrites, the `handoff` temp-dir change, the `resolving-merge-conflicts` removal, governance scaffolding (`SCOPE.md`, `.out-of-scope/`, issue forms, triage workflows), plugin/marketplace/changeset release tooling, the optional `scripts/link-skills.sh`, the optional `/retro` clause in `diagnosing-bugs`, and every divergence listed in §5.

## Sources

- Upstream repo: `/Users/roman/projects/skills`, HEAD `49dd158` (2026-10-09) at assessment time; window `git log --no-merges d81f3a1..HEAD` and `git diff d81f3a1..HEAD`. Synced to `c20facd` (§8).
- skills-dev: `/Users/roman/projects/skills-dev`, HEAD `f0c36fd` (2026-10-12); last sync commit `0816eb5`.
- Prior sync notes: `docs/research/upstream-skills-sync-2026-08-20.md`, `docs/research/upstream-skills-sync-2026-09-29.md`.
- Conventions: `AGENTS.md`, `docs/agents/skill-authoring.md`, `docs/agents/skill-dependencies.md`.
