# Research: Top five skills needing refinement

**Date:** 2026-08-02
**Scope:** all 51 real `SKILL.md` files (excluding `.claude/worktrees/`, `.venv/`, `node_modules/`, `site-packages/`).

## Rubric (derived from the repo's own standards)

Criteria and the primary sources they come from:

1. **Description triggers, no synonym-piles.** A model-invoked description must state what the skill is and list *one trigger per branch*; "synonyms that rename a single branch are duplication" (`dev/writing-great-skills/SKILL.md:24-28`). Model-invoked skills that omit `Use when…` trigger phrases mis-fire (`dev/skill-authoring/SKILL.md:35-40`).
2. **Progressive disclosure / no sprawl.** Keep `SKILL.md` lean; push reference into linked files (`dev/skill-authoring/SKILL.md:121-147`; `dev/writing-great-skills/SKILL.md:30-45,81`). Sprawl = "a skill simply too long" (`:81`).
3. **Prompt the positive, not the prohibition.** Negation backfires: "*don't think of an elephant* names the elephant" (`dev/writing-great-skills/SKILL.md:83`).
4. **Shared language / live cross-references.** Skill names used across skills must resolve; dependency contracts are real (`docs/agents/skill-dependencies.md:1-14`). Shared vocabulary is what makes an agent fire the right skill (`dev/writing-great-skills/SKILL.md:63-65`).
5. **Consistency with siblings + repo product.** Single source of truth, no duplicated topics (`dev/writing-great-skills/SKILL.md:55,79`); name field must match (`dev/skill-authoring/SKILL.md:42-56`).

**Method:** read the five standard docs above, enumerated all 51 skills, captured every frontmatter description + line/word count, then read fully any skill that looked problematic and grepped to confirm each defect (Cline references, dangling skill names, negation density, name/heading mismatches).

---

## Ranked top five

### 1. `dev/skill-authoring` — written for the wrong product, duplicates the repo's own standard

Path: `dev/skill-authoring/SKILL.md`

- **Wrong product throughout.** The skill is about *Cline*, not Claude Code: "Guide for creating effective **Cline** Skills" (`:3`), "determines when **Cline** activates your skill" (`:11`), "**Cline** reads SKILL.md sequentially" (`:59`), "Use clear section headers so **Cline** can scan" (`:66`), "Verify skill triggers in **Cline**" (`:215`). `git log` shows a single "Initial commit … 26 adapted skills" (`ff52648`) — it was imported and never adapted to this workspace.
- **Duplicates / conflicts with the repo's own authority.** This repo already has `dev/writing-great-skills/SKILL.md`, which the task itself names as the authoritative skill-quality doc. The two coexist unlinked (grep for `writing-great-skills` in `dev/skill-authoring/` returns nothing) and use *different, competing* vocabularies for the same topic: `skill-authoring` teaches "Keep SKILL.md Under 5k Tokens" and "Progressive Loading — Three Levels" (`:121-147`) while `writing-great-skills` teaches the *information hierarchy* / *context load* / *cognitive load* model (`:30-52`). Two sources of truth for one concept violates `dev/writing-great-skills/SKILL.md:55` ("single source of truth") and `:79` (duplication).
- **Longest of the two.** 256 lines / 1463 words vs. writing-great-skills' 83 lines.

**Refinement:** Either retire `skill-authoring` in favor of `writing-great-skills`, or repurpose it as the "installation & structure" companion (the SKILL.md-contract mechanics that `writing-great-skills` deliberately omits) — and in that case strip all five Cline references and re-point them at Claude Code + this repo's install model (`docs/agents/skill-authoring.md:9-17`).

### 2. `requirements/SRS-skill` — sprawl, negation-heavy, name mismatch, broken inbound reference

Path: `requirements/SRS-skill/SKILL.md`

- **Sprawl.** 574 lines / 3112 words, the largest skill in the repo, entirely inline — no progressive disclosure. Directly the "Sprawl" failure mode (`dev/writing-great-skills/SKILL.md:81`); the cure named there is "disclose reference behind pointers."
- **Steers by prohibition.** 20 lines carry `STOP`/`MANDATORY`/`BLOCKING`/`do not`/`WAIT`/`⛔`/`⚠`, e.g. "**⛔ STOP - Do not proceed without user confirmation**" (`:70`), "CHECKPOINT #1 … Condition: WAIT for explicit user confirmation" (`:23-26`). This is the Negation anti-pattern (`dev/writing-great-skills/SKILL.md:83`): prompt the positive gate instead of shouting the prohibition.
- **Name/heading mismatch.** Frontmatter `name: SRS-skill` (`:2`) but the H1 and body call it "**FS-to-SRS Skill**" (`:7,24,73,81,520`). Names must match (`dev/skill-authoring/SKILL.md:42-56`).
- **Broken inbound reference.** `requirements/FS-skill/SKILL.md:3` tells users "use the **FS-to-SRS skill** instead" — but no skill is named `FS-to-SRS` (grep for `name: FS-to-SRS` returns nothing; the target is this skill, named `SRS-skill`). A dead cross-skill reference (`docs/agents/skill-dependencies.md`).

**Refinement:** rename consistently to one of `SRS-skill`/`FS-to-SRS` and fix `FS-skill:3`; disclose the per-step SRS-structure detail and Appendix A traceability into a `docs/` file; convert the `⛔ STOP`/`WAIT` checkpoints into positive gates ("Confirm the source FS document, then proceed").

### 3. `dev/prompt-authoring` — dangling skill names break shared-language invocation

Path: `dev/prompt-authoring/SKILL.md`

- **References skills that do not exist under those names.** It repeatedly names `plan-with-critic` (`:3,29,49,69`), `grill-me` (`:79`), and `data-view skill` (`:32,49,69,87`). The actual skills are `critic`, `grilling`, and `data-view-skill` — grep for `name: plan-with-critic`, `name: grill-me`, `name: data-view` returns nothing. Because the description tells the agent to *emit these names into authored prompts as loop steps with round counts* (`:26-35`), the wrong name propagates into every generated artifact. This defeats the shared-language mechanism (`dev/writing-great-skills/SKILL.md:63-65`) and violates the dependency-contract expectation (`docs/agents/skill-dependencies.md`).
- **Internal inconsistency.** The same document calls the critic step both "plan-with-critic" and "critic rounds" (`:49`) — one concept, two names.
- **Description bloat.** 874-word body with the 5-question intake bank duplicated inline (`:45-51`) *and* pointed at `references/question-bank.md` as "authoritative" (`:103`) — two sources of truth for the same list (`dev/writing-great-skills/SKILL.md:55`).

**Refinement:** replace `plan-with-critic`→`critic`, `grill-me`→`grilling`, `data-view skill`→`data-view-skill` everywhere; drop the inline question copy or the pointer (keep one).

### 4. `requirements/FS-skill` — synonym-pile description + prohibition-heavy body

Path: `requirements/FS-skill/SKILL.md`

- **Description restates one branch many times.** "Use this skill when user asks to **build, write, create, generate, analyze, review, or modify** requirements … or feature set (FS) specifications" (`:3`) — and the same verb set reappears in the frontmatter's second sentence. That is exactly "synonyms that rename a single branch are duplication" (`dev/writing-great-skills/SKILL.md:27`). One real branch (author/revise FS requirements) is written as seven.
- **Negation density.** 110 grep hits for `MANDATORY`/`CHECKPOINT`/`WAIT`/`do not`/`STOP`/`REQUIRES` across the file, e.g. the description itself ends "This skill **REQUIRES** user confirmation at multiple checkpoints" (`:3`). Same Negation anti-pattern as SRS-skill (`dev/writing-great-skills/SKILL.md:83`).
- **Broken outbound reference** to the non-existent `FS-to-SRS skill` (`:3`, see item 2).
- 292 lines, fully inline (sprawl, `:81`).

**Refinement:** collapse the description to one trigger clause ("Author or revise Feature-Set (FS) requirements in EARS format. Use when…"); fix the `FS-to-SRS` name; disclose the phase-by-phase checkpoint tables into `docs/` and phrase gates positively.

### 5. `engineering/implement` — model-invoked but description carries zero trigger phrases

Path: `engineering/implement/SKILL.md`

- **No triggers.** Description is a bare identity statement: "Implement a piece of work based on a spec or set of tickets." (`:3`) — grep for `Use when` returns 0. It is model-invoked (no `disable-model-invocation`), so the description is its only invocation hook, yet it omits the trigger phrases the standard requires (`dev/skill-authoring/SKILL.md:37` "List trigger phrases"; formula at `:34-40`). Sibling model-invoked skills carry rich `Use when…` lists (e.g. `engineering/tdd`, `research/search-codebase`).
- Contrast with the *description* rule in `dev/writing-great-skills/SKILL.md:24` — a model-invoked description must "list the branches that should trigger it"; this one lists none.

**Refinement:** add branch triggers, e.g. "Use when the user says 'implement this', wants a ticket/spec worked to a tested + reviewed state, or asks to build the next slice."

---

## Also considered

- `engineering/testing` (`SKILL.md:3`) — description "Use when running tests, or committing the changes" bundles two distinct branches (test-running + git-commit) into one skill; thinner triggering than siblings (`dev/skill-authoring/SKILL.md:34-40`). Didn't crack top five because the body is otherwise tight.
- `research/research-and-web/deepapi` (`SKILL.md:3`) — weak, non-`Use when` description ("Use DeepAPI for scraping and safe email with DEEPAPI_API_BASE_URL and DEEPAPI_API_KEY") and 483 inline lines with no progressive disclosure; **excluded** because the skill is vendor-synced (`:11-17` overwrites itself from deepapi.co), so local refinement would be wiped.
- `planning/critic` (315 lines) and `planning/repeat` (210 lines) — large but actively maintained flagships with recent refactors; length appears load-bearing rather than sediment.
- `learning/teach` and `session/continue` (219 lines) — long but user-invoked (`disable-model-invocation`), so no description context-load cost; lower priority.
