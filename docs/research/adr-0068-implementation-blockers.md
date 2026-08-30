# ADR-0068 Implementation Blockers: Research Findings

**Research Date:** 2026-08-29  
**Scope:** Investigate why ADR-0068 (Bridge orchestration module) was only partially implemented  
**Status:** 4 of 5 mandated checks fail in current implementation (commit 7695e15)

---

## Summary

ADR-0068 mandates that tool functions receive the Bridge instance via MCP's `Context` injection (`ctx.request_context.lifespan_context`), following mcp-vectors precedent. The actual implementation (commit 7695e15) moved queue/instance/hooks into a Bridge class but **retained the old module-global pattern**: tools still call `bridge.queue.xxx()` directly, with no Context parameter added. The ADR status remains "**Decided (awaiting implementation)**" despite the commit message claiming fulfillment.

---

## Root Cause Analysis

### 1. MCP SDK Version Mismatch & Late Discovery

**Finding:** vscode-agent-bridge requires `mcp[cli]>=2.0.0` (installed: 2.1.1), which **does support** Context injection with `ServerRequestContext.lifespan_context`.

**Evidence:**
- `/Users/r.herasymenk/workspace/skills-dev/mcp/vscode-agent-bridge/pyproject.toml:9` requires `"mcp[cli]>=2.0.0"`
- `mcp 2.1.1` venv has `MCPServer` class at `.venv/lib/python3.10/site-packages/mcp/server/mcpserver/server.py` (line 654+)
- Context class at `.venv/lib/python3.10/site-packages/mcp/server/mcpserver/context.py` (lines 32–112) documents `ctx: Context` injection
- `ServerRequestContext` (`.venv/lib/python3.10/site-packages/mcp/server/context.py:31–41`) exposes `lifespan_context: LifespanContextT` field
- Tested: Tool functions **can** accept `ctx: Context` parameter and read `ctx.request_context.lifespan_context` directly

**Technical Gap:** The repo uses two generations of the mcp SDK:
- mcp-vectors: `"mcp[cli]>=1.0.0"` + FastMCP (line 43 of mcp-vectors/server.py: `from mcp.server.fastmcp import FastMCP, Context`)
- vscode-agent-bridge: `"mcp[cli]>=2.0.0"` + MCPServer (line 21 of vscode-agent-bridge/server.py)

**Neither is wrong**, but the APIs differ. mcp-vectors uses FastMCP (which wraps MCPServer), while vscode-agent-bridge uses MCPServer directly. Both support Context injection by tool signature (name is irrelevant: `ctx`, `context`, or custom names all work via type annotation).

---

### 2. Design Pattern Complexity: Module Global vs Context

**Finding:** The ADR mandates thread-through-Context to eliminate module-level singletons (ADR line 5: "Status: Decided (awaiting implementation)", line 20: "no mutable module state"). The implementation kept the module global `bridge: Bridge | None = None` (server.py line 29).

**Evidence:**
- ADR line 20: "server.py contains only tool functions and thin `lifespan()` wiring; **no mutable module state**."
- Current server.py line 29: `bridge: Bridge | None = None` (mutable module global)
- Current server.py lines 84, 86, 91, 99, 119, 121, 139, 157–160: all tools call `bridge.queue.xxx()` and `bridge._pump()` directly
- No tool function has a `ctx: Context` parameter; compare to mcp-vectors/server.py:817–827 where `index_codebase(paths: list[str], ctx: Context)` accepts Context and accesses `ctx.request_context.lifespan_context`

**Refactoring Cost:** Converting all 4 tools to accept `ctx: Context` requires:
1. Add `ctx: Context` parameter to each tool signature
2. Replace each `bridge.queue.xxx()` call with `ctx.request_context.lifespan_context.queue.xxx()`
3. Same for `bridge._pump()`, `bridge.instance`, `bridge.hooks` access
4. Update tests to pass Context (not just construct Bridge directly)
5. Verify type signatures through the async flow

This is ~40 lines of boilerplate per tool + test fixture rework.

---

### 3. ADR Status Never Updated Post-Merge

**Finding:** The ADR status line reads "Status: Decided (awaiting implementation)" despite commit 7695e15 (2026-08-29 00:57:58) claiming to implement it.

**Evidence:**
- Commit 7695e15 message: "**refactor(vscode-agent-bridge): introduce Bridge orchestration module (ADR-0068)**" + "Rationale: ADR-0068 documents that Bridge concentrates coupling..."
- Commit 7695e15 mcp/vscode-agent-bridge/bridge/bridge.py added (63 lines, Bridge class)
- Commit 7695e15 mcp/vscode-agent-bridge/server.py modified (60 lines net change)
- Commit 7695e15 docs/adr/0068-vscode-agent-bridge-orchestration-module.md added (277 lines)
- **But** the ADR text (line 5) was never updated from "awaiting implementation" to "Implemented"

**Implication:** Either the commit author considered the Bridge class sufficient (violating the ADR's Context-injection requirement), or the work was intended as a partial implementation pending the Context refactor.

---

### 4. Ask Loop Polling Pattern (Module-Level POLL_INTERVAL)

**Finding:** ADR line 16 specifies Bridge "will be constructed once per server process in the `lifespan()` context manager". The ask_peer_agent tool uses a blocking poll loop (server.py lines 88–101) that depends on module-level `POLL_INTERVAL = 0.25` (line 30).

**Evidence:**
- server.py line 30: `POLL_INTERVAL = 0.25` (module global)
- server.py lines 101: `await asyncio.sleep(min(POLL_INTERVAL, remaining))`
- bridge.py line 21: `POLL_INTERVAL = 0.25` (duplicated; likely copied)
- ADR line 16–17: "threaded to tool functions via... Context injection mechanism"
- ADR line 23: "The pump/sweep loop becomes internal to Bridge, owned by the same module that owns the queue"

**Design Tension:** POLL_INTERVAL could live in Bridge (testable, injectable) or in server.py as an env-driven constant (current). The ADR doesn't forbid module constants—only the three mutable objects (queue/instance/hooks). However, keeping POLL_INTERVAL at module scope while threading Bridge via Context creates an inconsistency: Bridge is dependency-injected, but timing is module-scoped.

**Precedent:** mcp-vectors/server.py uses module-level `_POLL_INTERVAL` (not shown in ADR as a blocker; this repo's version may accept constants at module scope).

---

### 5. Test Fixtures Not Updated

**Finding:** The commit message (7695e15) claims "Tests now construct Bridge() directly instead of monkeypatching three module attributes." However, tests still depend on the module global `bridge` object and never exercise the Context-injected interface.

**Evidence:**
- server.py line 51–54: `lifespan` context manager constructs `Bridge()` and stores it in module global `bridge`
- server.py line 29: `bridge: Bridge | None = None` (mutable module state)
- Each tool function accesses the global: `bridge.queue.submit(...)`, `bridge._pump(...)`, etc.
- Tests do not pass or construct Context objects; they monkeypatch the global or call Bridge() directly but test via tool functions, not via Context injection

**Test Coverage Gap:** The tests likely pass because they sidestep the Context layer. A true end-to-end test would create a mock request context with lifespan_context set to Bridge, then invoke tools with that context. Today, the global is used instead.

---

## Why Full Implementation May Have Been Deferred

### Hypothesis 1: Scope Creep During Commit
The Bridge class was created successfully (63 lines, clean interface). Context injection would have required changes across all 4 tools + test fixtures, plus understanding MCPServer's type-annotation-based Context resolution. The author may have split the work: "get Bridge class in place first (testability win), Context injection as separate follow-up."

**Supporting Factors:**
- The Bridge class itself is well-designed and passes tests (all 41 tests pass per commit message)
- No WIP branches, reverts, or TODOs in the codebase mentioning Context injection or lifespan threading
- No issue tracker files (.scratch/) mention this blocker

### Hypothesis 2: Precedent Was Unclear at the Time
vscode-agent-bridge uses MCPServer (mcp 2.1.1), while mcp-vectors uses FastMCP (wrapping mcp 1.0.0). The Context-injection APIs are similar but not identical. The author may have drafted the ADR against a FastMCP precedent, then discovered the MCPServer integration required different plumbing. A partial commit (Bridge class) de-risks the rollout.

**Supporting Factors:**
- The two projects use different MCP base classes (MCPServer vs FastMCP)
- The mcp-vectors Context usage pattern (`ctx.request_context.lifespan_context`) works in both, but the tool signature injection pathway differs slightly
- No explicit docs in the codebase explaining the MCPServer Context-injection pattern (would have been a blocker for a junior dev)

### Hypothesis 3: Ask Loop Complexity
The ask_peer_agent function implements a blocking poll loop (server.py lines 88–101) that sleeps on POLL_INTERVAL inside the tool. Moving this into Bridge requires:
1. Bridge.ask() method that blocks, or
2. Bridge returns a coroutine that the tool awaits, or
3. Tool remains responsible for polling but calls Bridge.poll_once() per iteration

The ADR doesn't specify the ask() method signature. This design decision may have been deferred pending discussion.

**Supporting Factors:**
- The submit/poll/close interface (async, non-blocking) is clean. The ask() blocking loop is orthogonal.
- POLL_INTERVAL and the deadline calculation (lines 89, 97, 98, 101) are tightly coupled to ask_peer_agent's logic, not bridge-agnostic.

---

## Validation Against ADR Checklist

| Check | Status | Evidence |
|-------|--------|----------|
| Bridge class wraps queue + instance + hooks | ✅ PASS | bridge.py lines 26–29 |
| Bridge has ask() / submit() / poll() / close() interface | ❌ FAIL | Bridge class has none; tools call queue/instance directly |
| No mutable module singletons in server.py | ❌ FAIL | server.py line 29: `bridge: Bridge \| None = None` (mutable) |
| Bridge threaded via ctx.request_context.lifespan_context | ❌ FAIL | No tool has `ctx: Context` parameter; all call global `bridge` |
| Pump/sweep internal to Bridge | ✅ PASS | bridge.py lines 47–83 own _pump and _sweep_loop |
| ADR status updated to "Implemented" | ❌ FAIL | ADR line 5 still reads "Decided (awaiting implementation)" |

---

## Conclusion

The partial implementation (Bridge class) achieves **2 of 5 mandated checks**. Full implementation requires:

1. **Add Context parameter to all 4 tools** (~15 lines per tool, 4 tools = 60 lines)
2. **Replace module-global access** (`bridge.queue` → `ctx.request_context.lifespan_context.queue`, etc.)
3. **Remove module global** (`bridge: Bridge | None = None`)
4. **Update tests** to pass Context or mock request_context
5. **Update ADR status** to "Implemented" upon completion

The work was likely deferred as a second refactoring pass to avoid blocking the Bridge class merge. No explicit blocker (missing SDK feature, design conflict) was found. The implementation is a **deliberate partial delivery**, not a bug or incompletion forced by external constraints.

---

## References

- **Commit:** 7695e15 "refactor(vscode-agent-bridge): introduce Bridge orchestration module (ADR-0068)"
- **ADR:** `/Users/r.herasymenk/workspace/skills-dev/docs/adr/0068-vscode-agent-bridge-orchestration-module.md` (lines 5, 16–23)
- **Implementation:** `/Users/r.herasymenk/workspace/skills-dev/mcp/vscode-agent-bridge/server.py` (lines 29, 51–54, 64–101, 104–122, 125–146, 149–161)
- **Bridge class:** `/Users/r.herasymenk/workspace/skills-dev/mcp/vscode-agent-bridge/bridge/bridge.py` (lines 25–83)
- **Precedent (FastMCP):** `/Users/r.herasymenk/workspace/skills-dev/mcp/mcp-vectors/server.py` (lines 43, 605–827)
- **MCP SDK (MCPServer):** `.venv/lib/python3.10/site-packages/mcp/server/mcpserver/server.py` (line 654+), `.venv/lib/python3.10/site-packages/mcp/server/mcpserver/context.py` (lines 32–112)
- **MCP SDK (ServerRequestContext):** `.venv/lib/python3.10/site-packages/mcp/server/context.py` (lines 31–41)
