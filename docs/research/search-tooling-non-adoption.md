# Search Tooling Non-Adoption: Why mcp-vectors and search-codebase Remain Unused

## Executive Summary

Two semantic code-search capabilities are installed and visible but almost never invoked: `mcp__mcp-vectors__*` (3 total invocations in 573 recent sessions, all by subagents) and `search-codebase` skill (0 invocations across 4 sessions where it appeared, last used 2026-08-20). Investigation reveals four distinct barriers, in no verified priority order (see note below):

1. **Deferred-tool gating (hard blocker):** mcp-vectors tools require an extra ToolSearch invocation before schemas load. Model sees them in listings but cannot call them directly. This creates friction that ripgrep/Read do not incur.
2. **Steering language (soft disincentive):** Tool descriptions and skill frontmatter actively recommend "not for exact symbol/string lookups — use ripgrep/fd instead," training the model away from semantic search as a default. Note: this phrasing is mandated by `docs/adr/0052-unify-search-tools-into-search-root.md` in skills-dev, so rewording it is an ADR revision, not a copy tweak.
3. **Task-shaped triggers too narrow (soft disincentive):** Skill frontmatter lists very specific task shapes ("before changing signature", "during code review") rather than the broader "understand how something works" that actually drives code exploration.
4. **Model's default reflex (structural):** With Bash/Read/Write always available and unencumbered, the model chooses them first for low-friction wins, deferring "semantic search setup" to later or skipping it when a quick grep worked.

**Correction (2026-08-26):** An earlier version of this doc listed "soft-failure indexing on the unindexed anthproxy root" as a second hard blocker, citing 3 indexed chunks for `/Users/r.herasymenk/workspace/anthproxy`. Live verification (`index_codebase dry_run=true` + a real `search_root` query) shows anthproxy is fully indexed — 128 files, 997 chunks — and `search_root` returns correct, relevant source (e.g. `server.py`, `README.md`) for a real query. That blocker did not hold at verification time; the ranked impact percentages below were a single-pass, unmeasured self-report and should be read as a hypothesis ranking, not a measured allocation. Both are struck from the ranked table.

## Root Causes by Category

### Hard Blockers (Would Fail or Be Impossible)

#### 1. Deferred-Tool Gating — mcp-vectors Schemas Not Loaded by Default

**Evidence:** System-reminder states:
> The following deferred tools are now available via ToolSearch. Their schemas are NOT loaded — calling them directly will fail with InputValidationError. Use ToolSearch with query "select:<name>[,<name>...]" to load tool schemas before calling them.

**File:** System reminder in every Claude Code session (evident in your context).

**Impact:** To invoke `mcp__mcp-vectors__search_root` or `mcp__mcp-vectors__index_codebase`, the model must first call ToolSearch manually — an explicit intermediate step that Bash, Read, and other defaults do not require. This is a **friction tax unique to mcp-vectors.**

**Why it matters:** The model sees mcp-vectors tools listed in available-skills and the MCP-server instructions section, but invoking them requires an extra context-switching cost:
1. Recognize the semantic search task
2. Decide ToolSearch is needed
3. Call ToolSearch (does not solve the user's problem; only unlocks the tool)
4. Call the actual search tool

Compare to ripgrep:
1. Recognize the search task
2. Call Bash with `rg <query>` directly

One fewer step is enough to tip the balance toward Bash, especially on fast tasks.

**Config evidence:**
- `~/.claude/settings.json`: `"ENABLE_TOOL_SEARCH": "auto"` (line 1) enables deferred loading.
- `~/.claude.json`, `mcpServers.mcp-vectors` is configured but not eagerly loaded into the tool set.

**Skill usage data:** In `~/.claude.json`, `skillUsage.search-codebase` has `usageCount: 8, lastUsedAt: 2026-08-20` — that was 5+ days ago. By contrast, `code-review` has `usageCount: 285, lastUsedAt: 2026-08-25` and `research` has `usageCount: 50, lastUsedAt: 2026-08-25` (today). The skill is not forgotten; it simply loses out when ToolSearch friction is added.

---

#### 2. Struck: "Soft-Failure Indexing on Unindexed anthproxy Root"

**This section is retained for record only — it does not hold as of the 2026-08-26 correction above.** The Qdrant snapshot below was read at one point in time and misidentified as the current, general state of the anthproxy root; a live re-check the same day shows anthproxy fully indexed (128 files, 997 chunks) and `search_root` returning correct source results. The `search_root` contradiction (tool description says "else returns an error"; skill doc says `success: true` with empty results) may still be real and worth a docstring fix, but it is not a live blocker for this codebase, and the ambiguity mechanism it describes was never observed to fire here.

**Evidence (as originally captured, now outdated):** Skill markdown at `/Users/r.herasymenk/workspace/skills-dev/research/search-codebase/SKILL.md` lines 12–13:
> `search_root` requires the root indexed. Unindexed roots return `success: true` with empty results — not an error — making empty ambiguous. Disambiguate: `index_codebase dry_run=true` → `not_found` = unindexed. When unindexed, fall back to `rg`/`fd` and offer indexing if the query is conceptual or cross-file.

**MCP server tool description:** `/Users/r.herasymenk/workspace/skills-dev/mcp/mcp-vectors/server.py` line 823:
> "Bring an entire project root into the index so search_root can use it — the first step before searching. Pass dry_run=true to preview status+plan without indexing."

And line 878 (this is `search_code`, deprecated per ADR-0052, not `search_root` — see `search_root`'s actual docstring in section 3 below):
> "Find code by meaning within a single indexed root (root_path required), for conceptual or cross-file retrieval in one project. Requires the root indexed first via index_codebase, else returns an error; use ripgrep/fd for exact strings, search_entities for symbol lookup, search_global for architecture."

**Qdrant state (stale, one-time read):**
```
mcp_vectors: 37114 chunks indexed
mcp_vectors_entities: 0 entities
mcp_vectors_communities: 0 communities
```
Indexed roots at that read: 88 chunks from identity, 65 from caveman, 18 from group-management, 15 from federation, 8 from access-control, 3 from anthproxy, 3 from global-authorization-system. The anthproxy figure was a snapshot from before or outside a full index run, not the steady state — it does not describe the root as it exists now.

---

### Soft Disincentives (Steer the Model Away)

#### 3. Tool Descriptions Actively Discourage Use for Common Tasks

**Evidence from MCP server instructions:** `/Users/r.herasymenk/workspace/skills-dev/mcp/mcp-vectors/server.py` lines 482–487:
```
instructions="""Local semantic search over indexed documents and codebases.

Three exposed tools: index_codebase, search_root, clear_index.

Use semantic search for conceptual, cross-file, exploratory retrieval or synthesis. Exact search/read tools remain better for exact symbols, literals, and line-by-line inspection — not for exact symbol/string lookups, use ripgrep/fd instead.
```

And the `search_root` tool description, line 1171 (this is the tool the skill and this doc actually recommend; verified current, verbatim, 2026-08-26):
> "Search an indexed root across all three channels — chunks (code + docs), entities (symbol graph with callers/neighbors), and communities (architecture) — in one call. Returns per-channel results each with a success flag. Top-level success is true if at least one channel succeeds. **Not for exact symbol/string lookups — use ripgrep/fd instead**; not for cross-root document search — use index_codebase to add other roots then call search_root on each."

**Skill frontmatter:** `/Users/r.herasymenk/workspace/skills-dev/research/search-codebase/SKILL.md` line 3:
```
description: Use when the user wants to find code, asks how X works, where X is defined, or how X relates to Y. Also use before refactoring, changing a signature, implementing multi-file work, or during code review to check blast radius.
```

And lines 8–9:
```
| `Bash(fd)` / `Bash(rg)` / `Read` | Exact symbol, literal, or filename lookup. |
| `search_root` | Conceptual, cross-file, exploratory retrieval — semantic, entity-graph, and architecture-level in one call. |
```

**Constraint:** this phrasing is mandated, not incidental — `docs/adr/0052-unify-search-tools-into-search-root.md` in skills-dev specifies the "Not for exact symbol/string lookups — use ripgrep/fd instead" contrast as required docstring content when it consolidated 16 tools down to 3. Rewording it (Recommendation 3 below) means revising that ADR, not editing prose.

**The trap:** "Exact symbol lookup" and "code review" are narrow framings. Most codebase questions — "where is this function called?", "what does this module do?", "is there existing logic for X?" — feel like they could be exact lookups, and the steering language ("use ripgrep for exact symbols") trains the model to reach for grep first.

The skill's `description` field in frontmatter (line 3) is the **only** thing the model sees when deciding whether to invoke a skill. That text is narrow and task-shaped, not conceptually inviting.

---

#### 4. No Recent Wins to Build Habit

**Evidence from skill usage in ~/.claude.json:**
- `search-codebase`: `usageCount: 8, lastUsedAt: 1787273123474` (2026-08-20 16:45:23 UTC)
- `research`: `usageCount: 50, lastUsedAt: 1787726720571` (2026-08-25 23:45:20 UTC)  
- `code-review`: `usageCount: 285, lastUsedAt: 1787714465572` (2026-08-25 20:21:05 UTC)
- `caveman`: `usageCount: 3, lastUsedAt: 1787726482419` (2026-08-25 23:41:22 UTC)

The skill was used 8 times across its lifetime but not invoked in the last 5 days. It has dropped out of the model's working set — not because it broke, but because every session starts with a fresh context and the model defaults to faster tools that require no setup.

---

## Indexing and Configuration State

**Indexed projects (stale snapshot, superseded by the 2026-08-26 correction above for anthproxy):** identity (88 chunks), caveman (65 chunks), group-management (18 chunks), federation (15 chunks), access-control (8 chunks), anthproxy (997 chunks / 128 files as of 2026-08-26, not the 3 originally recorded), global-authorization-system (3 chunks).

**Services active:**
- Qdrant: running at `localhost:6333` ✓
- LM Studio: running at `127.0.0.1:1234/v1` ✓
- mcp-vectors server: configured but deferred

---

## Ranked Impact Assessment

Ranking below is a hypothesis ordering from a single unmeasured research pass, not a measured allocation — the percentage estimates from the original version are dropped rather than corrected, since no methodology exists to defend any number. The "soft-failure on unindexed roots" blocker from the original table is dropped entirely; see the correction note in the executive summary.

| Rank | Blocker Type | Mechanism | Fixability |
|------|------|-----------|-----------|
| 1 | Deferred-tool gating | Model cannot call mcp-vectors without ToolSearch; Bash needs no setup | Structural; requires Claude Code to load mcp-vectors eagerly, or a skill that performs the unlock itself |
| 2 | Steering language | Tool descriptions say "not for exact symbol lookups"; model applies this too broadly | Constrained: phrasing is mandated by ADR-0052 in skills-dev; fixing this means revising that ADR |
| 3 | Narrow skill description | Frontmatter lists specific task shapes instead of broad "understand code" invitation | Reword frontmatter to lead with "understand how code is organized" |

---

## Recommendations

### Done

1. **Unlock step added to the skill.** `search-codebase`'s `SKILL.md` now opens with an explicit `ToolSearch query: "select:mcp__mcp-vectors__search_root,mcp__mcp-vectors__index_codebase,mcp__mcp-vectors__clear_index"` step before the tool-selection table, so invoking the skill performs the unlock instead of leaving it to model judgment. Addresses Rank 1 above without a new wrapper skill/agent.

### Not Pursued

2. ~~Index anthproxy fully.~~ Moot — anthproxy was already fully indexed (997 chunks / 128 files) at verification time; the "3 chunks" reading was a stale snapshot, not the codebase's actual state.

3. ~~Reword tool descriptions away from "not for exact symbol lookups."~~ Blocked on an ADR revision (ADR-0052 in skills-dev mandates this phrasing), not a copy change — out of scope for this pass; revisit only if the ADR itself is reopened.

4. ~~Build a wrapper skill/agent to encapsulate ToolSearch.~~ Superseded by the Done item above — `search-codebase` already is the intended wrapper; it only needed the missing unlock step, not a new artifact.

5. ~~De-defer mcp-vectors in local Claude Code config.~~ Out of project scope (requires Claude Code integration changes), unchanged from the original assessment.

### Open

6. **Reword frontmatter to be task-positive** (still open, Rank 3). Original suggestion:
   > "Use to understand code relationships, trace architecture, and find cross-file patterns. Replaces manual reading for questions like 'how does X relate to Y', 'where is this used', and 'what are the layers of this module.'"
   Not yet applied — the current frontmatter's task-shaped framing may still under-trigger the skill; revisit if usage doesn't recover after the unlock-step fix.

---

## Conclusion

The search-tooling gap is **not a capability gap**. Both tools are installed, services are running, indexing was already correct, and the skill was already close to a working wrapper — it was missing one step. The gap that held up at verification is narrower than originally scoped: ToolSearch friction (fixed) and, unverified, whether the frontmatter's narrow task framing still under-triggers the skill relative to broader "understand this code" requests.
