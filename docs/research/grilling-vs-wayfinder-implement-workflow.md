# Grilling vs Wayfinder: why `implement` didn't grill a grilling ticket

## Question

"In one of my sessions I noticed that a grilling ticket produced by the Wayfinder, when I used the Implement skill against it, did not grill anything. Should I have used the grilling skill instead, or the wayfinder skill?"

## Short answer

You should have used the **wayfinder skill** in its "Work through the map" mode — that is the skill that owns the ticket and knows a `wayfinder:grilling` ticket is resolved by a live grilling conversation (it invokes `/grilling` + `/domain-modeling`, then records the resolution, closes the ticket, and updates the map). Invoking `/grilling` directly would also produce the interview, but it does none of the tracker bookkeeping (claim / resolution comment / close / append to Decisions-so-far), so within the wayfinder workflow the wayfinder skill is the correct entry point. `implement` "did not grill anything" because implement is a **build** skill (TDD → code-review → checklist verification); it has no grilling step and treats a ticket as work to execute, not a decision to interview. A grilling ticket has nothing to build, so implement correctly did nothing useful.

## What each skill does

### `grilling` — `/Users/roman/projects/skills-dev/learning/grilling/SKILL.md`
A relentless one-question-at-a-time design interview that walks each branch of the decision tree (lines 6–14). It captures decisions as ADRs via `/domain-modeling` (lines 16–18) and, on conclusion, automatically writes an ADR manifest and invokes `/critic` (lines 20–30). It is a conversation skill — it decides, it does not build.

### `implement` — `/Users/roman/projects/skills-dev/engineering/implement/SKILL.md`
Builds a piece of work from a spec or set of tickets to a "tested, reviewed state" (frontmatter, lines 1–4). Its entire body is execution: `/tdd` at named seams (line 6), typecheck + tests after each change (line 8), `code-review` when done (line 10), then a verify-then-check checklist pass that flips `- [ ]` items to `- [x]` and sets ticket `## Status` to `done` (lines 12–29). **There is no grilling step anywhere in it.** It presumes the decisions are already made and there is code to write.

### `wayfinder` (a.k.a. `/i`) — `/Users/roman/projects/skills-dev/engineering/wayfinder/SKILL.md`
Plans a large effort as a shared **map** of **decision tickets** on the issue tracker and resolves them one at a time (frontmatter lines 1–5). It is **planning by default — "Plan, don't do"** (lines 11–13): each ticket resolves a *decision*, not a slice of a build. Note `disable-model-invocation: true` (line 4) — which is why "wayfinder" does not appear in the model's available-skills list even though it is installed.

Two modes (lines 107–132):
- **Chart the map** — grill to name the destination and map the frontier, then create tickets.
- **Work through the map** — load the map, **claim** a ticket, **resolve it** by invoking the skills the ticket type / Notes call for, then post a resolution comment, close the issue, and append to Decisions-so-far (lines 122–130).

### Related ticket/spec skills (context)
- `to-tickets` / `to-spec` (`engineering/…`) — publish tickets/specs from a plan; both depend on `setup-skills`, and `to-tickets` Step 5 recommends `/implement` to work the ticket frontier (see `docs/agents/skill-dependencies.md` lines 11–13). These produce **build** tickets, which is exactly what `implement` is for — unlike wayfinder's **decision** tickets.
- `critic` / `task-execution` (`planning/…`) — critic audits plans/ADRs; task-execution covers multi-file/parallel execution. Not involved in resolving a grilling ticket.

## What "Wayfinder" actually is

"Wayfinder" **is a real, installed skill** — it just isn't in the model-invocable list because of `disable-model-invocation: true` (`engineering/wayfinder/SKILL.md` line 4). It is the skill formerly/also invoked as **`/i`**: the setup-skills tracker docs still describe its artifacts under "Used by `/i`" (`engineering/setup-skills/issue-tracker-github.md` line 38; `…-local.md` line 23; `…-gitlab.md` line 39), and the repo path is `engineering/wayfinder/`. (The README's `| i (engineering) | mattpocock/skills |` row at line 222 is a separate provenance note; the shipped skill here is `name: wayfinder`.)

Wayfinder's map produces **child tickets, each carrying a `wayfinder:<type>` label — one of `research`, `prototype`, `grilling`, `task`** (`engineering/wayfinder/SKILL.md` line 69; label form confirmed in `engineering/setup-skills/issue-tracker-github.md` line 41). So **"a grilling ticket produced by the Wayfinder" = a `wayfinder:grilling` decision ticket.**

Per Ticket Types (`engineering/wayfinder/SKILL.md` lines 77–84):
- A **grilling** ticket is **HITL** (human-in-the-loop), "the default case," resolved by "Conversation via the /grilling and /domain-modeling skills, one question at a time" (line 83).
- Only the **task** type "does" rather than decides (line 84) — and even that unblocks a decision, not the destination.

So a grilling ticket is a **question to be talked through with the human**, not a unit of code to build.

## Why `implement` didn't grill

1. **The two skills have opposite contracts.** implement executes ("build this to a tested, reviewed state"); a grilling ticket has nothing to build — it holds a `## Question` (`wayfinder/SKILL.md` lines 63–67) whose resolution is a *decision*.
2. **implement contains no grilling path.** Its steps are tdd/typecheck/tests/code-review/checklist (`implement/SKILL.md` lines 6–29). There is no branch that reads a ticket's type or invokes `/grilling`. So it cannot grill regardless of the ticket.
3. **Nothing wires implement to grilling.** The cross-skill dependency graph (`docs/agents/skill-dependencies.md`) lists every grilling dependency — `grilling → critic`, `grill-with-docs → grilling`, `improve-codebase-architecture → grilling`, `to-tickets → implement` — but **no `implement → grilling` edge exists**. Grilling is always a separately, explicitly invoked step; it is never triggered by implement.
4. Result: implement ran against a decision ticket, found no test seams / acceptance criteria / code to write, and produced nothing — which is the expected outcome, not a bug. "Did not grill anything" is implement behaving exactly to spec on the wrong kind of ticket.

## Recommended workflow

For a `wayfinder:grilling` ticket:

1. **Re-invoke wayfinder in "Work through the map" mode**, pointing it at the map (and optionally the ticket): it claims the ticket, then resolves it (`engineering/wayfinder/SKILL.md` lines 122–130).
2. During resolution it runs **`/grilling` (+ `/domain-modeling`)** as the ticket type dictates (line 83) — the actual interview happens here, one question at a time, HITL.
3. Wayfinder then **records the resolution**: posts the answer as a resolution comment, **closes** the ticket, and appends a context pointer to the map's **Decisions-so-far** (lines 129–130), graduating any newly specifiable fog into fresh tickets.
4. Only **after** the map's decisions are resolved and the effort produces build tickets (e.g. via `to-tickets`) do you reach for **`/implement`** — that is the phase implement is built for (`docs/agents/skill-dependencies.md` line 13).

Rule of thumb:
- **Decision ticket** (`wayfinder:grilling` / research / prototype / task) → **wayfinder** (which calls grilling). Grilling alone works but skips the tracker bookkeeping.
- **Build ticket / spec** (from `to-tickets` / `to-spec`) → **implement**.
- `implement` and grilling are never substitutes for each other, and implement never grills.

## Sources

- `/Users/roman/projects/skills-dev/learning/grilling/SKILL.md`
- `/Users/roman/projects/skills-dev/engineering/implement/SKILL.md`
- `/Users/roman/projects/skills-dev/engineering/wayfinder/SKILL.md`
- `/Users/roman/projects/skills-dev/engineering/research/SKILL.md`
- `/Users/roman/projects/skills-dev/docs/agents/skill-dependencies.md`
- `/Users/roman/projects/skills-dev/engineering/setup-skills/issue-tracker-github.md`
- `/Users/roman/projects/skills-dev/engineering/setup-skills/issue-tracker-local.md`
- `/Users/roman/projects/skills-dev/engineering/setup-skills/issue-tracker-gitlab.md`
- `/Users/roman/projects/skills-dev/README.md` (line 222 — `i`/mattpocock provenance note)
- `/Users/roman/projects/skills-dev/plans/lineage-system-adr-manifest.md`, `/Users/roman/projects/skills-dev/docs/adr/0054-lineage-chain-architecture.md` (cross-references to the `i` skill)
