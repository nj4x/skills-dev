# Upstream skills sync — `mattpocock/skills` → `skills-dev` (2026-08-20)

Saved here because `docs/research/` is the existing convention in this repo
(`docs/research/code-review-group-c-lens.md`,
`docs/research/grilling-vs-wayfinder-implement-workflow.md`,
`docs/research/skills-needing-refinement.md`).

| | |
|---|---|
| Upstream repo | `/Users/roman/projects/skills` — `https://github.com/mattpocock/skills.git` |
| Upstream HEAD | `0ab1b63` (2026-08-20, "grilling: separate questions in a round with an HR") |
| Local repo | `/Users/roman/projects/skills-dev` — `https://github.com/nj4x/skills-dev.git` |
| Local HEAD | `7426dc8` (2026-08-06) |
| Last recorded sync | skills-dev `734e3f3` — "refactor(upstream-sync): port skills from ~/projects/skills 2ab9580..8b36d4f" |
| Unsynced upstream range | `8b36d4f..0ab1b63` — 22 non-merge commits, 15 of which touch `skills/` |

---

## Summary

skills-dev last pulled upstream at `8b36d4f` (2026-08-05). Since then upstream shipped
**one large mechanical change and six small substantive ones**. The mechanical change —
`3216582` "Remove all em-dashes from the repo" — rewrote punctuation in 56 files under
`skills/` and now dominates every `diff -r` between the two repos, making a naive `diff`
useless for spotting real change. Strip that out and the genuine upstream deltas are
small: a secrets-**Redact** section in `diagnosing-bugs`, harness-neutral subagent
dispatch, a standardised "call the Skill tool with \"name\"" invocation phrasing, a
policy reversal that *stops* skills invoking user-invoked skills, three
`domain-modeling` description rewrites, YAML-safe quoting of descriptions containing
colons, and a `grilling` round-format fix.

skills-dev has diverged far more heavily in the other direction: `to-spec`, `to-tickets`,
`grill-with-docs`, `wayfinder`, `implement` and `codebase-design` carry substantial local
content (lineage/SRS enforcement, `.scratch/<feature-slug>/` staging, `critic` loop
hand-offs, mcp-vectors search guidance) that upstream has no equivalent for. **This is not
a merge candidate; it is a cherry-pick list.** Roughly 8 upstream hunks are worth pulling;
everything else is either local-intentional or cosmetic.

---

## Inventory

Category paths differ: upstream lives under `skills/<category>/<skill>/`, skills-dev under
`<category>/<skill>/`.

| Skill | Upstream path | skills-dev path | Status |
|---|---|---|---|
| codebase-design | `skills/engineering/codebase-design` | `engineering/codebase-design` | diverged (local seam redefinition `c8747b7`; upstream harness-neutral dispatch) |
| diagnosing-bugs | `skills/engineering/diagnosing-bugs` | `engineering/diagnosing-bugs` | upstream-ahead (Redact section; Phase 6 hand-off removed) |
| domain-modeling | `skills/engineering/domain-modeling` | `engineering/domain-modeling` | diverged (upstream description rewrite; local lineage frontmatter in ADR-FORMAT.md) |
| grill-with-docs | `skills/engineering/grill-with-docs` (7 lines) | `engineering/grill-with-docs` (44 lines) | local-ahead |
| implement | `skills/engineering/implement` (15 lines) | `engineering/implement` (29 lines) | local-ahead |
| improve-codebase-architecture | `skills/engineering/improve-codebase-architecture` | `engineering/improve-codebase-architecture` | upstream-ahead (harness-neutral dispatch) |
| prototype | `skills/engineering/prototype` | `engineering/prototype` | diverged (em-dash only, 177-line diff) |
| research | `skills/engineering/research` | `engineering/research` | local-ahead (`subagent_type: "general-purpose"`, mcp-vectors guidance) |
| resolving-merge-conflicts | `skills/engineering/resolving-merge-conflicts` | `engineering/resolving-merge-conflicts` | local-ahead (conflict-marker done-criterion) |
| tdd | `skills/engineering/tdd` | `engineering/tdd` | diverged (local mcp-vectors guidance; upstream Skill-tool phrasing) |
| to-spec | `skills/engineering/to-spec` (75 lines) | `engineering/to-spec` (85 lines) | local-ahead / diverged |
| to-tickets | `skills/engineering/to-tickets` (105) | `engineering/to-tickets` (144) | local-ahead / diverged |
| wayfinder | `skills/engineering/wayfinder` | `engineering/wayfinder` | diverged (local lineage section; upstream Skill-tool phrasing) |
| setup-matt-pocock-skills / setup-skills | `skills/engineering/setup-matt-pocock-skills` | `engineering/setup-skills` | diverged (renamed locally; `triage-labels.md` present both sides) |
| grilling | `skills/productivity/grilling` | `learning/grilling` | diverged (upstream HR format fix; local critic hand-off + `Explore` subagent) |
| teach | `skills/productivity/teach` (140) | `learning/teach` (124) | diverged (local `PHILOSOPHY.md`; upstream 16 extra lines) |
| wait-what | `skills/productivity/wait-what` | `session/wait-what` | upstream-ahead (CONTEXT-MAP.md follow) |
| handoff | `skills/productivity/handoff` (16) | `session/handoff` (102) | local-ahead |
| writing-for-agents | `skills/productivity/writing-for-agents` | `dev/writing-for-agents` | diverged (em-dash only, 109-line diff) |
| git-guardrails-claude-code | `skills/misc/git-guardrails-claude-code` | `dev/git-guardrails-claude-code` | local-ahead (`disable-model-invocation: true`) |
| code-review | `skills/engineering/code-review` (SKILL.md, 6.4K) | `dev/code-review` (`skill.md`, 15.7K + `docs/`, `scripts/`) | diverged — effectively a local rewrite |
| ask-matt | `skills/engineering/ask-matt` | — | upstream-only |
| triage | `skills/engineering/triage` | — | upstream-only |
| wizard | `skills/engineering/wizard` | — | upstream-only |
| grill-me | `skills/productivity/grill-me` | — | upstream-only (skills-dev deliberately dropped it — see `docs/agents/disposition-20260724-190949.md` Gate 2 A2) |
| to-questionnaire | `skills/productivity/to-questionnaire` | — | upstream-only |
| migrate-to-shoehorn | `skills/misc/migrate-to-shoehorn` | — | upstream-only |
| scaffold-exercises | `skills/misc/scaffold-exercises` | — | upstream-only |
| setup-pre-commit | `skills/misc/setup-pre-commit` | — | upstream-only |
| claude-handoff, loop-me, setup-ts-deep-modules, writing-beats, writing-fragments, writing-shape | `skills/in-progress/*` | — | upstream-only (upstream marks them in-progress) |
| critic, repeat, goal-loop, task-execution | — | `planning/*` | local-only |
| testing, refactor-tests, refactor-claude-md, setup-lineage | — | `engineering/*` | local-only |
| FS-skill, SRS-skill, api-skill, data-view-skill | — | `requirements/*` | local-only |
| search-codebase, research-and-web/* (6 skills) | — | `research/*` | local-only |
| continue, hs, mark, short | — | `session/*` | local-only |
| html-view, interview-style-doc-building | — | `publishing/*` | local-only |
| inbox, mail | — | `email/*` | local-only |
| mute, setup-help | — | `notifications/*` | local-only |
| prompt-authoring, skill-authoring, test-mcp, tool-authoring | — | `dev/*` | local-only |

---

## Upstream changes worth pulling

### 1. `diagnosing-bugs` — secrets Redact section (`efce423`, trimmed by `bda79a3`)

Highest-value pull. Upstream added a `## Redact` section right after the CONTEXT.md
paragraph in `skills/engineering/diagnosing-bugs/SKILL.md`. Final trimmed text:

> This skill has you show commands, outputs and captured artifacts. **Redact every secret
> first** — write `<REDACTED>` in its place. Build loops against env vars, so the
> credential stays in the environment rather than in what you show. Captured artifacts
> carry auth headers: quote only the lines that carry the signal.
>
> If the redacted output is not enough to diagnose the bug, say so and ask the user.

Two supporting edits in the same commit:
- Phase 1 completion criterion: "paste the invocation and its output" → "show the
  invocation and its output, redacted".
- "ask the user for … (b) a captured artifact" → "(b) a **redacted** captured artifact".
- `scripts/hitl-loop.template.sh` header comment gains: "`capture` prints its value back
  to the terminal, where the agent reads it — so capture observations, and leave signing
  in to the user as a `step`."

skills-dev `engineering/diagnosing-bugs/SKILL.md` has none of this. **Pull as-is.**

### 2. Harness-neutral subagent dispatch (`14bfbbd`, trimmed by `c0d6901`)

Upstream removed hard references to Claude Code's `Agent` tool and its
`general-purpose`/`Explore` types because Codex has no such tool:

- `code-review/SKILL.md`: "Send a single message with two `Agent` tool calls. Use the
  `general-purpose` subagent for both." → "Dispatch both with your harness's subagent
  mechanism, in parallel — one message with two calls where the harness supports it."
- `codebase-design/DESIGN-IT-TWICE.md` step 2: "Spawn 3+ sub-agents in parallel using the
  Agent tool." → "…with your harness's subagent mechanism."
- `improve-codebase-architecture/SKILL.md`: "use the Agent tool with
  `subagent_type=Explore`" → "dispatch a subagent to walk the codebase — a read-only
  exploration agent if your harness has one."

**Conflict.** skills-dev commit `7426dc8` deliberately went the *opposite* way ("fix: add
missing `subagent_type` declarations across 7 skills"), e.g.
`skills-dev/engineering/codebase-design/DESIGN-IT-TWICE.md`: "Spawn 3+ sub-agents in
parallel using the Agent tool (`subagent_type: "general-purpose"`)", and
`skills-dev/learning/grilling/SKILL.md:20`: "dispatch an `Explore` sub-agent
(`subagent_type: "Explore"`)". skills-dev is Claude-Code-only, so **do not pull.**

### 3. `grilling` — round format shows two questions with an `---` (`85f83d3`, latest upstream commit)

Upstream changed the fenced example from a single-question template to a two-question one
separated by `---`, and retitled it "Format a round like so:". skills-dev
`learning/grilling/SKILL.md:11-17` still has the single-question form ("Each question
should be formatted like so:"). Cheap, purely additive to the fenced block. **Pull the
fenced block + heading only**; keep everything else local.

### 4. `wait-what` — follow `CONTEXT-MAP.md` (`d6cd26f`)

Upstream body now ends: "…use the ubiquitous language from `CONTEXT.md` (follow
`CONTEXT-MAP.md` to the right one if the repo has more than one)."
skills-dev `session/wait-what/SKILL.md:7` lacks the parenthetical. This is directly
consistent with skills-dev's own `docs/agents/domain.md`, which already documents
`CONTEXT-MAP.md`. **Pull.**

### 5. YAML-safe quoting of descriptions containing a colon (`5c89081`)

Upstream wrapped six descriptions in double quotes because an unquoted `: ` in a YAML
scalar is a parse error. skills-dev is immune today because it uses em-dashes instead of
colons in exactly those spots — verified: `rg -n '^description: [^"'"'"'].*: ' --glob
'SKILL.md'` returns zero hits across all 53 `SKILL.md` files. Nothing to pull; note the
hazard so future description edits avoid an unquoted `": "`.

### 6. `domain-modeling` — description rewrite (`bd8e81b` → `e12e7ec` → `54bc6b6`)

Ended at:

> `description: Build and sharpen a project's domain model. Use when discussing codebase
> terminology, writing or editing a CONTEXT.md, or recording or editing an ADR.`

skills-dev `engineering/domain-modeling/SKILL.md:3` still carries the pre-`bd8e81b` text
("…or when another skill needs to maintain the domain model"). **Judgment call**: upstream
dropped the "another skill needs to maintain" clause, but skills-dev *does* have skills
that call `domain-modeling` programmatically (`grill-with-docs`,
`improve-codebase-architecture`, `wayfinder`), so that clause is load-bearing here.
Recommend adopting the *added* triggers ("writing or editing a CONTEXT.md, or recording or
editing an ADR") and **keeping** the trailing clause.

### 7. `agents/openai.yaml` sidecars for five skills

Upstream ships an `agents/openai.yaml` display-name sidecar per skill, e.g.
`skills/productivity/grilling/agents/openai.yaml`:

```yaml
interface:
  display_name: "Grilling"
  short_description: "Stress-test thinking a round of questions at a time"
```

skills-dev has these for most `engineering/*` skills but is missing them for
`learning/grilling`, `learning/teach`, `session/wait-what`, `session/handoff`,
`dev/writing-for-agents`, and `engineering/wayfinder`. Low value if skills-dev never
targets Codex — see Open Questions.

### 8. Em-dash removal (`3216582`, 56 files under `skills/`)

Upstream converted every em-dash to a colon, comma, or sentence break, and added a rule to
its `CLAUDE.md` steering future writing away from them. skills-dev uses em-dashes
pervasively. **This is a style decision, not a bug** — but it is the single reason
`diff -r` between the repos is unreadable. If skills-dev ever wants low-friction future
syncs, adopting the convention would pay for itself; otherwise, all future diffs must be
filtered.

---

## Intentional local divergences to preserve

A naive `cp -r` would clobber all of these.

1. **Issue tracker is GitHub Issues via `gh issue create`**, not upstream's pluggable
   tracker. Documented in `CLAUDE.md` and `docs/agents/issue-tracker.md`. Upstream
   `setup-matt-pocock-skills` ships `issue-tracker-github.md` / `-gitlab.md` / `-local.md`
   as user choices; skills-dev renamed the skill to `setup-skills` and all references
   point at `/setup-skills` (`engineering/to-spec/SKILL.md:6`,
   `engineering/to-tickets/SKILL.md:6`, `engineering/wayfinder/SKILL.md:29`). Any pulled
   hunk mentioning `setup-matt-pocock-skills` must be renamed on the way in.

2. **`.scratch/<feature-slug>/` staging + `critic` loop.** `to-spec` steps 3–7
   (`engineering/to-spec/SKILL.md:20-75`) write `draft-spec.md` to `.scratch/`, run
   `Skill(critic, args: "pickup:.scratch/<feature-slug>/draft-spec.md 3 auto")` (line 58),
   and only publish on the `PLAN_APPROVED_READY_FOR_FINALIZATION` sentinel. `to-tickets`
   has the same shape (`engineering/to-tickets/SKILL.md:128`). Upstream has no critic
   skill at all.

3. **Requirements-lineage enforcement (ADR-0054…0067).** `grill-with-docs/SKILL.md:9-44`
   (SRS anchor pre-flight), `wayfinder/SKILL.md` "Requirements lineage when decisions
   create ADRs", `to-spec` step 3.5 (Source ADR resolution + `**Status**: Approved`
   check), and `domain-modeling/ADR-FORMAT.md` lineage frontmatter
   (`artifact-type: adr`, `lineage-rules`, `source-srs`). None of this exists upstream.

4. **mcp-vectors search guidance.** The sentence "Search source code conceptually and
   cross-file; search docs and requirements as a document corpus; for architecture-level
   questions start with a global search before reading individual files" is appended
   locally in `engineering/research/SKILL.md`, `engineering/tdd/SKILL.md`,
   `engineering/to-spec/SKILL.md`, `learning/grilling/SKILL.md:20`. Backed by
   `docs/agents/search-strategy.md`.

5. **Explicit `subagent_type` declarations** (`7426dc8`) — the direct inverse of upstream
   `14bfbbd`. See item 2 above.

6. **`disable-model-invocation` choices differ per skill.** skills-dev *added* it to
   `dev/git-guardrails-claude-code` and the research skills (`6d8f75d`), and *removed* it
   from `engineering/implement` and `engineering/to-spec` (both are model-invokable
   locally). Upstream has the opposite settings on all four.

7. **Headless-mode handling.** `to-spec` step 2's "Headless detection: check whether the
   `AskUserQuestion` tool is available… In headless mode, skip the seam-check user
   interaction" has no upstream counterpart.

8. **`codebase-design` seam definition** (`c8747b7`): local reads "A **Seam** is where a
   caller depends on a **Module**'s **Interface**"; upstream reads "A **Seam** is where a
   **Module**'s **Interface** lives." Deliberate local redefinition ("point of use, not
   declaration").

9. **`engineering/implement` post-review checklist** (`d435388`) — verify-then-check
   workflow, spec `Status` field, gate consistency. Upstream `implement` is 15 lines with
   none of it.

10. **`session/handoff` (102 lines) vs upstream `productivity/handoff` (16 lines)** and
    **`dev/code-review` (`skill.md`, 15.7K, plus `docs/` and `scripts/`) vs upstream
    `code-review/SKILL.md` (6.4K)** — both are local rewrites, not forks to re-merge.
    Note `dev/code-review` uses lowercase `skill.md`, which is worth checking against the
    frontmatter contract in `docs/agents/skill-authoring.md`.

11. **`hooks/` say-cue system** — `docs/agents/hooks.md` requires multi-turn skills to
    call `say_skill_start` / `say_skill_done` / `say_skill_cancel`. No upstream skill does
    this; any newly adopted skill must have cues added.

12. **`grill-me` was deliberately dropped.** `docs/agents/disposition-20260724-190949.md`
    Gate 2 A2 records the decision to standardise on `grilling`/`learning/grilling` and
    delete the `grill-me` alias. Do not re-adopt it.

---

## Sync plan

### Phase 1 — safe mechanical pulls (no judgment needed)

1. `engineering/diagnosing-bugs/SKILL.md` — insert the `## Redact` section (final trimmed
   form from `bda79a3`) after the CONTEXT.md paragraph; change the Phase 1 completion
   criterion to "(show the invocation and its output, redacted)"; change "a captured
   artifact" to "a **redacted** captured artifact".
2. `engineering/diagnosing-bugs/scripts/hitl-loop.template.sh` — add the `capture` header
   comment from `efce423`.
3. `session/wait-what/SKILL.md` — append "(follow `CONTEXT-MAP.md` to the right one if the
   repo has more than one)" to the body (`d6cd26f`).
4. `learning/grilling/SKILL.md` lines 11–17 — replace the single-question fenced example
   with upstream's two-question `---`-separated block and retitle to "Format a round like
   so:" (`85f83d3`).
5. `engineering/domain-modeling/SKILL.md:3` — extend the description with "writing or
   editing a CONTEXT.md, or recording or editing an ADR", keeping the existing "or when
   another skill needs to maintain the domain model" clause.

### Phase 2 — repo-wide hygiene sweep

6. Already clean — the unquoted-`": "` description sweep (`5c89081`'s bug class) returns
   zero hits in skills-dev. No action; keep the invariant in mind when editing
   descriptions.
7. Fix the one stale upstream name: `README.md` still contains a
   `setup-matt-pocock-skills` reference (`rg -c 'setup-matt-pocock-skills' README.md` → 1).
   Every `SKILL.md` already uses `setup-skills`. Reconcile
   `docs/agents/skill-dependencies.md:11` at the same time.
8. Check `dev/code-review/skill.md` filename casing against the `SKILL.md` contract in
   `docs/agents/skill-authoring.md`. Likely a pre-existing local bug, not an upstream
   issue.

### Phase 3 — judgment calls (do not auto-apply)

9. **Cross-skill invocation phrasing.** Upstream converged on `call the Skill tool with
   "name"` (`d28dfdc` → `fcf0071` → `447ca70`) and then *reversed policy* in `1dab982`:
   skills must **not** call user-invoked (`disable-model-invocation: true`) skills; they
   tell the user to run the slash command instead. skills-dev has 6 sites using old
   phrasing: `engineering/tdd/SKILL.md:26`, `engineering/grill-with-docs/SKILL.md:7`,
   `engineering/wayfinder/SKILL.md:29,83,115`,
   `engineering/improve-codebase-architecture/SKILL.md:13,71`,
   `engineering/to-spec/SKILL.md:6`, `engineering/to-tickets/SKILL.md:6`,
   `engineering/diagnosing-bugs/SKILL.md` (last line), `dev/tool-authoring/SKILL.md:114`,
   `session/continue/SKILL.md:84`. Decide one policy and apply it uniformly — this is the
   largest consistency win available and it interacts with skills-dev's own
   `Skill(critic, args: …)` and `Skill("code-review")` call sites
   (`engineering/implement/SKILL.md:10`).
10. **`diagnosing-bugs` Phase 6.** Upstream `1dab982` deleted the entire "Then ask: what
    would have prevented this bug?" hand-off to `improve-codebase-architecture` and
    retitled "Phase 6 — Cleanup + post-mortem" to "Phase 6 — Cleanup". skills-dev still
    has the hand-off. Keep or drop is a policy call, not a sync.
11. **Em-dash convention.** Decide whether skills-dev adopts upstream's no-em-dash rule.
    Adopting it makes every future upstream diff readable; not adopting it means all
    future syncs need `diff | grep -v '—'` filtering. Do not do this piecemeal.
12. **Explicitly reject upstream `14bfbbd`/`c0d6901`** (harness-neutral dispatch) and
    record the rejection, so a future sync doesn't reopen it. Candidate home:
    `docs/adr/` or a note in `docs/agents/skill-authoring.md`.

### Phase 4 — new-skill adoption

Ordered by fit with skills-dev conventions.

13. **`wizard`** (`skills/engineering/wizard`, 44 lines + `template.sh`) — generates an
    interactive bash wizard for human-only steps. Self-contained, no tracker or domain-doc
    dependency. Cleanest adoption; would go in `engineering/`. Needs: say-cue calls per
    `docs/agents/hooks.md` if treated as multi-turn.
14. **`to-questionnaire`** (`skills/productivity/to-questionnaire`, 54 lines) — turn a
    decision you can't answer into a questionnaire. No dependencies. Fits `planning/` or
    `publishing/`.
15. **`triage`** (`skills/engineering/triage`, 112 lines + `AGENT-BRIEF.md`,
    `OUT-OF-SCOPE.md`) — issue/PR state machine. `docs/agents/issue-tracker.md` already
    anticipates it ("Skills like `to-tickets`, `to-spec`, and `triage` create issues via
    `gh issue create`", and the `prs_as_requests` note) — so the tracker doc is *already
    written for a triage skill that doesn't exist yet*. Adoption requires rewriting all
    tracker operations to `gh`, and the label vocabulary to come from
    `engineering/setup-skills/triage-labels.md`.
16. **`ask-matt`** (`skills/engineering/ask-matt`, 90 lines + `PHASE-BOUNDARIES.md`) — a
    router over the skill catalogue. Valuable in principle given skills-dev has 53 skills
    vs upstream's 35, but its content is entirely upstream's catalogue; adopting it means
    rewriting it from scratch against skills-dev's own list. Treat as inspiration, not a
    port.
17. **Skip**: `migrate-to-shoehorn`, `scaffold-exercises`, `setup-pre-commit` (all
    TypeScript/course-specific, no fit), `grill-me` (deliberately dropped — see
    `docs/agents/disposition-20260724-190949.md`), `setup-matt-pocock-skills` (already
    forked as `setup-skills`), and all `skills/in-progress/*` (upstream itself marks them
    unfinished; `claude-handoff` overlaps `session/handoff`, `loop-me` overlaps
    `planning/goal-loop`).

### Phase 5 — record the sync

18. Commit with a message matching the prior convention:
    `refactor(upstream-sync): port skills from ~/projects/skills 8b36d4f..0ab1b63`
    (mirrors `734e3f3`). This is what makes the *next* sync findable.

---

## Open questions

1. **Em-dashes.** Adopt upstream's repo-wide no-em-dash rule (`3216582`, `e6e9577`), or
   keep them and filter every future diff? This decides how expensive every subsequent
   sync is.
2. **Cross-skill invocation policy.** Three candidate policies are live:
   (a) upstream's current one — never call a user-invoked skill, tell the user to run the
   slash command (`1dab982`/`6a34259`); (b) upstream's earlier one —
   `call the Skill tool with "name"` (`fcf0071`); (c) skills-dev's current mix of
   `` run `/skill` `` and `Skill(name, args: …)`. skills-dev's `critic` and `code-review`
   hand-offs are *programmatic* and depend on being callable, so (a) may be unworkable
   here. Which one?
3. **Codex / OpenAI support.** Does skills-dev care about non-Claude-Code harnesses? If
   no, reject upstream's harness-neutral direction outright and skip the
   `agents/openai.yaml` sidecars. If yes, the `subagent_type` work in `7426dc8` needs
   revisiting.
4. **`triage` adoption.** `docs/agents/issue-tracker.md` already documents a triage skill
   that doesn't exist locally. Adopt upstream's, write a `gh`-native one, or delete the
   forward reference from the doc?
5. **`dev/code-review` vs upstream `code-review`.** The local version is 2.5× the size
   with its own `docs/` and `scripts/`. Confirm the intent is permanent divergence so
   future syncs skip it entirely — and settle the `skill.md` vs `SKILL.md` filename.
6. **Upstream `teach` is 16 lines longer** than `learning/teach`, and local has an extra
   `PHILOSOPHY.md`. Not investigated in depth here. Worth a dedicated diff pass if `teach`
   is actively used.
