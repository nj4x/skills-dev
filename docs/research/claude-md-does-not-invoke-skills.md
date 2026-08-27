# CLAUDE.md Text Does Not Invoke Skills: The `Talk like caveman.` Case

## Executive Summary

**Verdict: the `Talk like caveman.` line in `/Users/r.herasymenk/.claude/CLAUDE.md` does NOT cause a `Skill(caveman)` tool call. Not once, ever, in any recorded session on this machine.**

Across **1,798 session transcripts** under `/Users/r.herasymenk/.claude/projects/`, there are **zero** occurrences of `"skill":"caveman"`. Over the last 7 days (627 transcripts) there were 54 `Skill` tool invocations across 8 distinct skills — `caveman` is not among them. Today (2026-08-26, 19 top-level sessions + 35 subagent transcripts) there were exactly 3 `Skill` calls: `writing-for-agents`, `grilling`, `critic`.

The caveman *skill body* has loaded in only **4 real sessions ever**, and in every case the trigger was the explicit `/caveman` slash command typed by the user — never a model-initiated `Skill` tool call, and never as a downstream effect of the CLAUDE.md line.

Meanwhile, caveman-register assistant text **does** appear in sessions with no `Skill` call and no skill body in context. That is imitation-without-invocation, and it is the normal case.

---

## What Was Observed (Transcript Evidence)

### 1. Zero `Skill(caveman)` calls, all-time

**Command:** `grep -rl '"skill":"caveman"' --include='*.jsonl' /Users/r.herasymenk/.claude/projects/`
**Result:** 0 files.

Corpus size: 1,798 `.jsonl` transcripts (`find . -name '*.jsonl' | wc -l`).

### 2. Skill invocations that *did* happen (last 7 days)

**Command:** `find . -name '*.jsonl' -newermt '2026-08-19 00:00' -exec grep -oh '"name":"Skill","input":{"skill":"[^"]*"' {} \;` over 627 transcripts.

| Skill | Invocations |
|---|---|
| code-review | 26 |
| critic | 12 |
| grilling | 5 |
| search-codebase | 4 |
| domain-modeling | 3 |
| writing-for-agents | 2 |
| tdd | 1 |
| task-execution | 1 |
| **caveman** | **0** |

Today's 3 calls, with sources:

- `/Users/r.herasymenk/.claude/projects/-Users-r-herasymenk-workspace-anthproxy/7f731e41-315c-4514-aed3-16a2a4d86387.jsonl` — `{"skill":"writing-for-agents"}`
- `/Users/r.herasymenk/.claude/projects/-Users-r-herasymenk-workspace-group-management/f6609f26-8e6a-4b23-8ac3-e73b8cb7263b.jsonl` — `{"skill":"grilling"}` and `{"skill":"critic","args":"pickup:plans/pr282-labels-review-followup-adr-manifest.md"}`

### 3. The skill body loads only via `/caveman`, and it is not a `Skill` call

The distinctive SKILL.md body string `ACTIVE EVERY RESPONSE` (line 15 of `/Users/r.herasymenk/.claude/skills/caveman/SKILL.md`) appears in exactly 5 transcripts. One of those five is this research agent's own transcript (`-Users-r-herasymenk-workspace-skills-dev/a2bcb349-.../subagents/agent-a4732c5b9106c4ea7.jsonl`) — self-contamination from reading the file during this investigation; discount it. The 4 genuine ones:

- `-Users-r-herasymenk-workspace-federation/79c7ae79-5850-405e-b1b5-85d12ec3224c.jsonl`
- `-Users-r-herasymenk-workspace-caveman/9497d43b-6076-4383-ba7a-e71d1d2f6f5b.jsonl`
- `-Users-r-herasymenk-workspace-anthproxy/43122da7-0361-41d1-b558-51343ca08380.jsonl`
- `-Users-r-herasymenk-workspace-anthproxy/7f731e41-315c-4514-aed3-16a2a4d86387.jsonl`

All four are exactly the set of transcripts containing `<command-name>/caveman</command-name>`. The overlap is total.

**Mechanism, observed verbatim** in `7f731e41-315c-4514-aed3-16a2a4d86387.jsonl`:

- Line 7, `type: "user"`, `origin.kind: "human"`, `timestamp: 2026-08-26T06:55:28.503Z`:
  ```
  "content":"<command-message>caveman</command-message>\n<command-name>/caveman</command-name>"
  ```
- Line 8, the immediately following entry, also `type: "user"` (synthetic, same `promptId` `9adc5561-...`):
  ```
  "text":"Base directory for this skill: /Users/r.herasymenk/.claude/skills/caveman\n\nRespond terse like smart caveman. All technical substance stay. Only fluff die.\n\n## Persistence\n\nACTIVE EVERY RESPONSE. ..."
  ```

The slash command expands the SKILL.md body **into a user-role message**. There is no `tool_use` block, no `"name":"Skill"`, no tool result. So even the one path that *does* load caveman is not a `Skill` tool call.

Corroboration from `/Users/r.herasymenk/.claude.json`: `skillUsage.caveman` = `{usageCount: 4, lastUsedAt: 1787813728479}` → `2026-08-26T06:55:28.479Z`. That is 24 ms before the `/caveman` command entry at line 7. The counter tracks slash-command expansion, and it stands at 4 — matching the 4 genuine transcripts above, not 0 and not 19.

There is no `/Users/r.herasymenk/.claude/commands/` directory on this machine (verified: `ls -d` returns nothing), so `/caveman` is Claude Code's auto-generated skill slash command, not a hand-written command file.

### 4. Imitation without invocation — the crux, observed today

Session `/Users/r.herasymenk/.claude/projects/-Users-r-herasymenk-workspace-skills-dev/a2bcb349-2d25-4d8e-b913-cc72cd014f24.jsonl` (cwd `skills-dev`, 2026-08-26). Grep for `"name":"Skill"` in this file returns **0**. Grep for `ACTIVE EVERY RESPONSE` returns **0** — the skill body was never in context.

Assistant text at line 27, `timestamp: 2026-08-26T22:42:41`:

> Agent hunt through today session logs. Look for `Skill(caveman)` calls, compare against caveman-style text with no call. Write findings to `docs/research/`. Me ping you when back.

Dropped articles, fragments, "Me ping you" — textbook caveman register. Produced with the skill neither invoked nor loaded. This is the hypothesis confirmed in a single entry.

Two more from today, same pattern (no `Skill` call, no skill body):

- `-Users-r-herasymenk-workspace-identity/37234683-990e-46c2-a878-feb18747b8cc.jsonl`, line 18, `2026-08-26T18:04:15`: *"Lock file blocks it: `.git/index.lock` exists. Check no git process is running first."*
- `-Users-r-herasymenk-workspace-anthproxy/8f9338cc-e5d5-4f9b-87d7-641e8265f4da.jsonl`, line 38, `2026-08-26T22:08:55`: *"File copied ok. Now drop commit from anthproxy repo (git status clean check first, then reset)."*

### 5. And in most sessions the line is not even imitated

A crude register proxy — article density (`the|a|an` as a fraction of words) over all assistant text per session, today's 15 sessions that produced prose:

| Session (prefix) | Skill calls | Assistant texts | Article ratio | Register |
|---|---|---|---|---|
| a2bcb349 | 0 | 1 | 0.000 | caveman |
| e0d78b9e | 0 | 1 | 0.000 | normal (see below) |
| e1924604 | 0 | 4 | 0.017 | compressed |
| 37234683 | 0 | 3 | 0.018 | compressed |
| 8f9338cc | 0 | 5 | 0.025 | compressed |
| c069a69f | 0 | 9 | 0.033 | mixed |
| 93d5daf5 | 0 | 24 | 0.052 | normal |
| 6adff7bd | 0 | 17 | 0.055 | normal |
| c1a7f2e7 | 0 | 18 | 0.074 | normal |
| 21617e65 | 0 | 21 | 0.075 | normal |
| 48212f9f | 0 | 45 | 0.075 | normal |
| **7f731e41** | **1** (`writing-for-agents`) | 11 | 0.075 | **caveman — body loaded via `/caveman`** |
| be29b23c | 0 | 53 | 0.080 | normal |
| 5c6fd201 | 0 | 11 | 0.080 | normal |
| f6609f26 | 2 (`grilling`, `critic`) | 32 | 0.082 | normal |

The sharpest counterexample is `-Users-r-herasymenk-workspace-identity/e0d78b9e-6767-4bf1-bf7f-9ab2e338d7ce.jsonl`, line 11, `2026-08-26T20:23:25`, the session's only assistant text:

> hey 👋 what's up? what can I help with?

Emoji, full pleasantry, zero compression — the exact opposite of the SKILL.md rule *"no decorative tables/emoji"* and the CLAUDE.md line. If the skill had loaded, this output would violate it outright. It did not load, and the CLAUDE.md line alone did not carry.

Likewise `-Users-r-herasymenk-workspace-identity/5c6fd201-...jsonl`, line 14: *"I'll search the codebase for definitions of "standard type" of a group."* — and this is a transcript where the CLAUDE.md injection is verifiably present (see §6).

---

## What Was Inferred (Mechanism)

Two different delivery channels, both visible in transcripts, with different semantics.

### Channel A — CLAUDE.md: auto-applied instruction text

Observed verbatim in `-Users-r-herasymenk-workspace-identity/5c6fd201-5e2a-44ba-9857-7692bb0a29a2.jsonl`, line 81, `type: "user"`, `2026-08-26T17:11:18`:

> Codebase and user instructions are shown below. Be sure to adhere to these instructions. IMPORTANT: These instructions OVERRIDE any default behavior and you MUST follow them exactly as written.
>
> Contents of /Users/r.herasymenk/workspace/identity/CLAUDE.md (project instructions, checked into the codebase): ...

Same structure in `-Users-r-herasymenk-workspace-group-management/c1a7f2e7-73d8-46ca-8f06-76ea73cc022b.jsonl`, line 212, `2026-08-26T19:03:01` (for `CLAUDE.local.md`).

The global `/Users/r.herasymenk/.claude/CLAUDE.md` is concatenated into the same block, labelled *"(user's private global instructions for all projects)"*. Its first line is literally `Talk like caveman.` (verified: `head -3` on that file).

**This is prose the model reads and follows directly.** It names no tool, exposes no handle, and expands to nothing. `Talk like caveman.` is a style directive, not a dispatch.

### Channel B — skill listing: an invitation to call a tool

Skills arrive as a transcript attachment record. In `-Users-r-herasymenk-workspace-identity/6adff7bd-609a-4c17-b4ef-36201227ba51.jsonl`, line 11:

```
"attachment":{"type":"skill_listing" ... "skillCount":26,"isInitial":true,
"names":["ac-req-skill","api-skill","caveman","code-review", ...]
```

It renders as a `<system-reminder>` reading *"The following skills are available for use with the Skill tool:"* followed by one line per skill — **name plus frontmatter `description` only**. For caveman that is lines 3–8 of `/Users/r.herasymenk/.claude/skills/caveman/SKILL.md`:

> caveman: Ultra-compressed communication mode. Cuts output tokens 65% (measured) by speaking like caveman while keeping full technical accuracy. Supports intensity levels: lite, full (default), ultra, wenyan-lite, wenyan-full, wenyan-ultra. Use when user says "caveman mode", "talk like caveman", "use caveman", "less tokens", "be brief", or invokes /caveman. Also auto-triggers when token efficiency is requested.

The 100+ lines of actual instruction — the intensity table, the Auto-Clarity rules, the Boundaries section — are **not** in that listing. They only enter context when something expands them.

### Why one auto-applies and the other does not

- CLAUDE.md text is framed as **binding instruction** ("you MUST follow them exactly as written"). Compliance means *changing how you write*. No action required, so no action is recorded.
- The skill listing is framed as **an inventory of callable things**. Compliance means *emitting a `Skill` tool-use block*, which is a discrete decision the model must take and which leaves a trace.

`Talk like caveman.` therefore satisfies itself the instant it is read. There is nothing left for a tool call to accomplish. The model complies (when it complies) by imitating the register, which is exactly what the transcripts show — and it never has to notice that a skill with the same name exists.

Note also that the frontmatter says the skill fires when the user *says* "talk like caveman". A line sitting in a persistent instructions file is not a user utterance in the current turn; it is ambient configuration. That framing mismatch is a second reason the trigger never reads as live.

---

## Confounds and Caveats

1. **Both texts sit in context simultaneously.** The `Talk like caveman.` instruction and the caveman skill description are in every session's context together. The model could plausibly bridge them and call the skill. It has an obvious motive and an obvious handle. **In practice, across 1,798 transcripts, it never did.** This is the strongest form of the result: not "the mechanism forbids it" but "the mechanism permits it and it still does not happen."

2. **`grep caveman` over-counts badly.** Raw `caveman` hits in transcripts are inflated by an unrelated product: `/Users/r.herasymenk/.caveman/bin/caveman-proxy` and `@caveman-ai/cli/dist/native-hook-fast.js` appear in every `hook_success` attachment on this machine, and `mcp__caveman__caveman_stats` / `caveman_toon_encode` MCP tools appear in tool listings. Sessions showing "15 caveman mentions" mostly mean "15 hook log lines". Only `"skill":"caveman"` and the SKILL.md body markers are meaningful.

3. **Article ratio is a rough proxy, not a measurement.** Session `7f731e41` scores 0.075 (normal-looking) despite genuinely running in caveman mode, because most of its assistant text is quoted document content, which is not compressed. Read the table as a screen for manual inspection, not as a register classifier. The qualitative excerpts in §4 and §5 are the actual evidence.

4. **Transcripts do not persist the system prompt.** `Talk like caveman` appears in only 2 `.jsonl` files, and the `claudeMd` block in only 8 — and those are cases where a `/cd` re-injected it mid-session, or a subagent received it inline. So "the string is absent from this transcript" does **not** mean CLAUDE.md was inactive there. The mechanism claim in §Channel A rests on the 8 transcripts where the injection *is* captured, plus direct observation of the live system prompt.

5. **Scoping.** Today's sample (54 transcripts) is thin for a negative result, so the all-time corpus (1,798) was used for the zero-invocation claim. The 7-day window (627 transcripts) was used for the comparative skill tally.

6. **The caveman skill is not a skills-dev artifact.** It is installed at `/Users/r.herasymenk/.claude/skills/caveman/` and sourced from the separate `/Users/r.herasymenk/workspace/caveman` repository (the `caveman-ai` project). Nothing in skills-dev owns it.

---

## Conclusion

The hypothesis holds without qualification. `Talk like caveman.` in CLAUDE.md is injected as instruction prose and produces, at best, stylistic imitation — often not even that (see the emoji greeting in `e0d78b9e`). It has never produced a `Skill(caveman)` tool call. The skill's real instructions — persistence rules, intensity levels, Auto-Clarity carve-outs for security warnings and irreversible actions, the Boundaries rule that commits and issue bodies stay in normal prose — load only when the user types `/caveman`, which has happened 4 times in the machine's recorded history.

**Practical consequence:** the CLAUDE.md one-liner buys an unreliable impression of the style and none of the safety rails. If the intent is the actual skill, `/caveman` at session start is the only path that loads it.
