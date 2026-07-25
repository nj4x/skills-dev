# Improve mcp-vectors Tool Engagement via Trigger-First Descriptions and Planning-Phase Pre-conditions

Agents under-use the entity-graph and community tools (`search_global`, `get_entity_callers`, `get_entity_neighbors`, `search_entities`) despite guidance in CLAUDE.md. Tool descriptions currently describe mechanics ("Locate a code symbol by name in the entity graph…") rather than trigger conditions, so the call-time decision defaults to grep or `search_code` even when the graph tools are the right choice.

We decided to make two complementary, scope-separated changes:

1. **MCP tool descriptions (server.py)** — rewrite each description with trigger-first framing: lead with the agent question that should route to this tool, follow with a "not for" contrast against the common wrong choice. Pattern: *"Use this when [problem]. Not for [wrong choice] — use [alternative] instead."* This activates at call-selection time and helps any MCP client, not just Claude Code.

2. **CLAUDE.md pre-conditions** — add imperative workflow-gated rules ("Before X, always call Y") that fire during task planning. These are distinct from the existing tool→use-case reference table, which is passive; pre-conditions create hard gates before mutations or architecture claims.

The two layers say different things and activate at different moments; the overlap is intentional.

## Considered Options

- **CLAUDE.md only** — loses discoverability for agents that don't load this project context.
- **Tool descriptions only** — no planning-phase gate; agent may still reach for grep before consulting the tool list.
- **Both, scoped differently** *(chosen)* — descriptions = call-time self-service; CLAUDE.md = planning-time mandate.

## Consequences

- Tool descriptions in server.py become the authoritative "when to use" guide for any MCP client.
- CLAUDE.md pre-conditions create explicit obligations that are harder to skip than a passive reference table.
- Pre-conditions are *strong rules*, not suggestions, reflecting the low cost of a graph call vs. the blast radius of missing an impacted caller.

## Sync and Ownership

**Server.py descriptions are the canonical source of truth.** Pre-conditions live in the user's session context (CLAUDE.md in ~/.claude/ and project CLAUDE.md), and are derived from server.py tool descriptions. An automated pytest parity test asserts: (1) the four targeted engagement tools (`search_global`, `get_entity_callers`, `get_entity_neighbors`, `search_entities`) each have a pre-condition entry in the project CLAUDE.md, (2) every pre-condition entry in project CLAUDE.md names a tool that exists in server.py (catching orphans if a tool is renamed), and (3) each targeted tool's server.py description contains the pattern "Not for ... use ..." and each corresponding CLAUDE.md pre-condition contains a similar pattern. The test runs in CI against the repo-tracked project CLAUDE.md; drift is caught before merge. Note: the user's private ~/.claude/CLAUDE.md is out of scope for CI enforcement; it is supplementary guidance.

**Contrast consistency (procedural + structural):** The "not for X — use Y" contrasts in server.py descriptions and CLAUDE.md pre-conditions should remain consistent. A lightweight parity test (item 3 above) catches completely missing contrasts via pattern matching. For semantic drift of the contrast text itself (e.g., "use ripgrep" becoming "use rg"), this is a residual risk caught by code review: when a PR changes a tool's contrast in server.py, the commit message checklist requires an explicit audit of CLAUDE.md and notation of both changes in the commit body. Code review verifies the consistency. Hint: use `git diff server.py CLAUDE.md` to spot-check contrasts side-by-side.

**PR workflow:** When a PR touches tool descriptions in server.py, the parity test will fail if the project CLAUDE.md is not updated in the same commit (for the four targeted tools). This enforces synchronization without manual review burden.

**Token cost trade-off and efficacy metric:** Trigger-first descriptions are longer than mechanics-first descriptions. The added per-call context cost is accepted because tool discovery and correct routing have higher priority than shaving tokens off every call to a tool that's under-engaged anyway. Efficacy is measured via a metrics database (separate SQLite file, `metrics.db`), not logs. Each tool call (`search_global`, `get_entity_callers`, `get_entity_neighbors`, `search_entities`) records the following fields: `timestamp` (ISO-8601), `tool_name` (string), `session_id` (string), `root_path` (string), `outcome` (enum: `success` | `zero_result` | `error`). Table: `tool_calls`. Metrics writes are best-effort and non-blocking; a write failure never blocks a tool call (see ADR-0004 "Metrics and observability" for details). A management CLI (`mcp-vectors metrics query --tool <name> --since <period>`) retrieves call frequency and outcome distribution over time.

The first month post-ship establishes a baseline of actual call frequency and outcome mix. After that period, metrics are compared month-over-month to detect trends in both volume and quality (success rate). The token trade-off is justified by improved tool discoverability; retrospective efficacy is measured as a trend (increasing or stable call frequency, maintained or improving success rate), not as a causal claim of improvement, given that task mix and model capabilities also vary over time. This metric detects observable engagement trends but cannot prove agents are selecting tools for the right reasons; manual spot-checks of session logs may be needed to validate behavioral correctness.

**Action threshold:** if, after 60 days of baseline data, call frequency has not increased and success rate has not improved relative to the first 30 days, the token trade-off is revisited: descriptions may be shortened or the approach revised. No hard numeric threshold is defined; the review is qualitative, conducted at the 60-day mark.
