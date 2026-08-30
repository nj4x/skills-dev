# ADR-0068: Introduce Bridge orchestration module in vscode-agent-bridge

**Date:** 2026-08-29

**Status:** Implemented

## Context

The vscode-agent-bridge MCP server coordinates three tightly coupled objects — `BridgeQueue`, `InstanceManager`, and `HookServer` — across four MCP tool functions (`ask_peer_agent`, `submit_to_peer_agent`, `poll_peer_agent`, `close_peer_agent`) and a background pump/sweep loop. Today all three are module-level singletons in `server.py`, and test fixtures rebuild them by hand via `monkeypatch.setattr(srv, "queue", ...)`.

This creates two seams where there should be one:
1. **Tool functions reach directly past their interface into module internals** — they depend on private globals, not on the MCP framework's actual seam (the tool contract).
2. **Tests can only reset state by mutating module attributes** — the same seam the production code uses — making it unclear whether tests exercise the public interface or just the fixture's wiring.

## Decision

Introduce one **Bridge** module (a class wrapping queue + instance + hooks + pump/sweep logic) with a small interface: `ask()`, `submit()`, `poll()`, `close()`. This module will be constructed once per server process in the `lifespan()` context manager and threaded to tool functions via the MCP framework's `Context` injection mechanism (`ctx.request_context.lifespan_context`), following the precedent in `mcp-vectors/server.py`.

After this change:
- `server.py` contains only tool functions and thin `lifespan()` wiring; no mutable module state.
- Tests construct a `Bridge()` directly and call its methods, exercising the actual interface.
- The pump/sweep loop becomes internal to `Bridge`, owned by the same module that owns the queue.

## Consequences

**Positive:**
- Locality: queue/instance/hooks wiring lives in one place, not re-derived per test file.
- Leverage: one interface backs 4 tools + pump + sweep.
- Testability: fixture construction becomes `Bridge()` instead of three `monkeypatch.setattr()` calls.
- Deletion test passes: removing `Bridge` redistributes its orchestration logic across all callers (ask/submit/poll/close + pump + sweep), proving it concentrates complexity.

**Negative:**
- Adds one class and moves ~100 lines of code.
- Requires learning MCPServer's `Context` injection pattern (but precedent exists in the repo).

## Appendix: End-to-End Sequence Diagrams

The integration flow between Claude Code and the cline-sr peer agent is split into separate diagrams by use case. Participants are grouped by process boundary:
- **Claude Code** — MCP client that invokes tools
- **MCP Server (Bridge)** — Bridge process containing MCP tools, Bridge orchestrator, Queue, HookServer, and Instance manager
- **VS Code** — Extension, cline-sr peer agent, and hook scripts

---

### Diagram 1: Server Lifespan / Startup

One-time initialization when the MCP server starts. The Bridge orchestrator is created, HookServer begins listening, and the sweeper loop starts.

```mermaid
sequenceDiagram
    autonumber
    box LightBlue Claude Code
        participant Client as MCP Client
    end
    box LightGreen MCP Server (Bridge)
        participant MCP as MCP Tools
        participant Bridge as Bridge (Orchestrator)
        participant HookServer as Hook Server (HTTP + WS)
    end
    box LightYellow VS Code
        participant Extension as Extension
        participant Cline as cline-sr (Peer Agent)
    end

    rect rgb(245,245,245)
    Note over MCP,Bridge: Server Lifespan (one-time startup)
    MCP->>Bridge: start()
    activate Bridge
    Bridge->>HookServer: start()
    HookServer-->>MCP: port (BRIDGE_PORT)
    Bridge->>Bridge: start sweeper loop
    Bridge-->>MCP: ready
    deactivate Bridge
    end

    Note right of HookServer: HookServer exposes:<br/>- HTTP POST /hook (lifecycle events)<br/>- WebSocket /ws (liveness + task submission)
```

---

### Diagram 2: Path A — ask_peer_agent (Blocking)

Covers the blocking call path with 180s timeout. Includes dispatch logic and instance spawn/reuse decision.

```mermaid
sequenceDiagram
    autonumber
    box LightBlue Claude Code
        participant Client as MCP Client
    end
    box LightGreen MCP Server (Bridge)
        participant MCP as MCP Tools
        participant Bridge as Bridge (Orchestrator)
        participant Queue as Queue (BridgeQueue)
        participant HookServer as Hook Server (HTTP + WS)
        participant Instance as Instance (VS Code Manager)
    end
    box LightYellow VS Code
        participant Extension as Extension
        participant Cline as cline-sr (Peer Agent)
    end

    rect rgb(235,245,255)
    Note over Client,HookServer: PATH A - ask_peer_agent (blocking, 180s timeout)
    Client->>MCP: ask_peer_agent(question, workspace)
    activate MCP
    MCP->>Queue: submit(question, workspace)
    activate Queue
    Queue-->>MCP: Record(id, status=queued)
    deactivate Queue
    MCP->>Bridge: _pump(async_timeout)
    activate Bridge
    Bridge->>Queue: next_dispatchable()
    activate Queue
    Queue-->>Bridge: Record (status=dispatched)
    deactivate Queue
    Bridge->>Instance: ensure_ready(workspace, port)
    activate Instance
    alt Instance not alive or different workspace
        Instance->>Instance: spawn code --user-data-dir workspace
        Instance->>Extension: WebSocket connect /ws
        activate Extension
        Extension->>HookServer: WS open (liveness signal)
        HookServer->>Instance: mark_connected()
        Extension-->>Instance: connected
        deactivate Extension
    else Instance already ready
        Instance-->>Bridge: ready (reuse)
    end
    Instance-->>Bridge: ready
    deactivate Instance
    Bridge->>HookServer: dispatch(question)
    HookServer->>Extension: WS send {type:submit, prompt}
    Extension->>Extension: invoke URI handler
    Extension->>Cline: vscode://cline-sr.cline-sr/task?prompt=...
    activate Cline
    Cline-->>Extension: task accepted
    deactivate Cline
    Bridge-->>MCP: dispatched
    deactivate Bridge
    deactivate MCP
    end

    Note over HookServer,Queue: All hook POSTs log with task_id= field (ADR-0069)
```

---

### Diagram 3: Task Execution + Hook Events Flow

Covers the hook event flow from cline-sr back to the Bridge: TaskStart binding, tool-use loop (PreToolUse/PostToolUse), and TaskComplete with filter/recovery branches. Also includes the answer retrieval polling loop.

```mermaid
sequenceDiagram
    autonumber
    box LightBlue Claude Code
        participant Client as MCP Client
    end
    box LightGreen MCP Server (Bridge)
        participant MCP as MCP Tools
        participant Queue as Queue (BridgeQueue)
        participant HookServer as Hook Server (HTTP + WS)
    end
    box LightYellow VS Code
        participant Cline as cline-sr (Peer Agent)
        participant Hooks as Hook Scripts
    end

    Note over Cline,Hooks: Task Execution & Hook Events Flow
    Cline->>Cline: task starts
    Cline->>Hooks: TaskStart hook
    activate Hooks
    Hooks->>HookServer: POST /hook {hookName:TaskStart, taskStart:{taskMetadata:{taskId}}}
    HookServer->>Queue: bind_cline_task(taskId)
    activate Queue
    Queue-->>HookServer: bound (record.cline_task_id = taskId)
    deactivate Queue
    HookServer-->>Hooks: {ok:true}
    deactivate Hooks

    loop Tool Use Cycle (0..N times)
        Cline->>Cline: about to use tool
        Cline->>Hooks: PreToolUse hook
        activate Hooks
        Hooks->>HookServer: POST /hook {hookName:PreToolUse}
        HookServer->>Queue: record_tool_use()
        activate Queue
        Queue-->>HookServer: updated
        deactivate Queue
        HookServer-->>Hooks: {ok:true}
        deactivate Hooks

        Cline->>Cline: execute tool
        Cline->>Hooks: PostToolUse hook
        activate Hooks
        Hooks->>HookServer: POST /hook {hookName:PostToolUse}
        HookServer->>Queue: record_tool_use()
        activate Queue
        Queue-->>HookServer: updated
        deactivate Queue
        HookServer-->>Hooks: {ok:true}
        deactivate Hooks
    end

    Cline->>Cline: task complete
    Cline->>Hooks: TaskComplete hook
    activate Hooks
    Hooks->>HookServer: POST /hook {hookName:TaskComplete, taskComplete:{taskMetadata:{taskId}, result, command}}
    HookServer->>Queue: complete(answer, command, cline_task_id=taskId)
    activate Queue
    alt record.cline_task_id matches payload taskId
        Queue-->>HookServer: status=answered
    else record unbound or mismatch + failed record exists
        Queue->>Queue: _recover_completion(taskId) - linear scan
        Queue-->>HookServer: resurrected failed->answered
    else mismatch, no recovery
        Queue-->>HookServer: answer dropped (logged warning)
    end
    deactivate Queue
    HookServer-->>Hooks: {ok:true}
    deactivate Hooks

    Note over MCP,Queue: Answer Retrieval (polling loop)
    activate MCP
    loop Poll until answered/failed/timeout
        MCP->>Queue: get(record.id)
        activate Queue
        alt status == answered
            Queue-->>MCP: Record(status=answered, answer, command)
            MCP-->>Client: {id, status:answered, answer, command, reason:null}
        else status == failed
            Queue-->>MCP: Record(status=failed, reason)
            MCP-->>Client: {id, status:failed, answer:null, reason}
        else remaining > 0
            Queue-->>MCP: Record(status=dispatched/pending)
            MCP->>MCP: sleep(POLL_INTERVAL)
        else timeout expired
            MCP->>Queue: fail(record.id, "timeout")
            Queue-->>MCP: status=failed
            MCP-->>Client: {id, status:failed, reason:timeout}
        end
        deactivate Queue
    end
    deactivate MCP
```

---

### Diagram 4: Path B — submit_to_peer_agent + poll_peer_agent (Async)

Covers the async submission path (non-blocking) and later polling for the answer.

```mermaid
sequenceDiagram
    autonumber
    box LightBlue Claude Code
        participant Client as MCP Client
    end
    box LightGreen MCP Server (Bridge)
        participant MCP as MCP Tools
        participant Bridge as Bridge (Orchestrator)
        participant Queue as Queue (BridgeQueue)
        participant HookServer as Hook Server (HTTP + WS)
        participant Instance as Instance (VS Code Manager)
    end
    box LightYellow VS Code
        participant Extension as Extension
        participant Cline as cline-sr (Peer Agent)
    end

    rect rgb(235,255,235)
    Note over Client,Cline: PATH B - submit_to_peer_agent (async) + poll_peer_agent
    Client->>MCP: submit_to_peer_agent(question, workspace)
    activate MCP
    MCP->>Queue: submit(question, workspace)
    activate Queue
    Queue-->>MCP: Record(id, status=queued)
    deactivate Queue
    MCP->>Bridge: _pump(async_timeout)
    activate Bridge
    Bridge->>Queue: next_dispatchable()
    activate Queue
    Queue-->>Bridge: Record (status=dispatched)
    deactivate Queue
    Bridge->>Instance: ensure_ready(workspace, port)
    activate Instance
    Instance-->>Bridge: ready
    deactivate Instance
    Bridge->>HookServer: dispatch(question)
    HookServer->>Extension: WS send {type:submit, prompt}
    Extension->>Cline: vscode://cline-sr.cline-sr/task?prompt=...
    activate Cline
    Cline-->>Extension: task accepted
    deactivate Cline
    MCP-->>Client: {handle:id, status:submitted, reason:null}
    deactivate Bridge
    deactivate MCP

    Note over Client,Queue: Later - Poll for Answer
    Client->>MCP: poll_peer_agent(handle)
    activate MCP
    MCP->>Queue: get(handle)
    activate Queue
    alt unknown_handle
        Queue-->>MCP: null
        MCP-->>Client: {status:failed, reason:unknown_handle}
    else status == pending
        Queue-->>MCP: Record(status=dispatched, tool_uses, last_event_at)
        MCP-->>Client: {status:pending, tool_uses, last_event_at}
    else status == answered
        Queue-->>MCP: Record(status=answered, answer, command, tool_uses)
        MCP-->>Client: {status:answered, answer, command, tool_uses, last_event_at}
    else status == failed
        Queue-->>MCP: Record(status=failed, reason, tool_uses)
        MCP-->>Client: {status:failed, reason, tool_uses, last_event_at}
    end
    deactivate Queue
    deactivate MCP
    end
```

---

### Diagram 5: Path C — close_peer_agent (Cleanup)

Covers graceful shutdown of the VS Code instance. Checks queue is empty before terminating.

```mermaid
sequenceDiagram
    autonumber
    box LightBlue Claude Code
        participant Client as MCP Client
    end
    box LightGreen MCP Server (Bridge)
        participant MCP as MCP Tools
        participant Queue as Queue (BridgeQueue)
        participant Instance as Instance (VS Code Manager)
    end
    box LightYellow VS Code
        participant Extension as Extension
    end

    rect rgb(255,245,235)
    Note over Client,Instance: PATH C - close_peer_agent
    Client->>MCP: close_peer_agent()
    activate MCP
    MCP->>Queue: in_flight()
    activate Queue
    Queue-->>MCP: null or Record
    alt queue not empty (busy)
        MCP-->>Client: {status:busy}
    else queue empty
        MCP->>Instance: close()
        activate Instance
        Instance->>Instance: terminate VS Code process
        Instance-->>MCP: closed
        deactivate Instance
        MCP-->>Client: {status:closed}
    end
    deactivate Queue
    deactivate MCP
    end
```

---

### Diagram 6: Failure Paths

Covers three failure scenarios: sweep timeout (async expiration), instance_down (WS disconnect), and TaskCancel with pre-bind/match/mismatch branches.

```mermaid
sequenceDiagram
    autonumber
    box LightBlue Claude Code
        participant Client as MCP Client
    end
    box LightGreen MCP Server (Bridge)
        participant Bridge as Bridge (Orchestrator)
        participant Queue as Queue (BridgeQueue)
        participant HookServer as Hook Server (HTTP + WS)
    end
    box LightYellow VS Code
        participant Extension as Extension
        participant Cline as cline-sr (Peer Agent)
        participant Hooks as Hook Scripts
    end

    rect rgb(255,235,235)
    Note over Bridge,Hooks: FAILURE PATHS

    Note over Bridge,Queue: Timeout (async expiration)
    Bridge->>Bridge: sweep_loop (every 5s)
    Bridge->>Queue: sweep_expired(async_timeout=1800s)
    activate Queue
    Queue->>Queue: mark expired records as failed(timeout)
    Queue-->>Bridge: swept
    deactivate Queue

    Note over Extension,Queue: Instance Down (WS disconnect)
    Extension->>HookServer: WS close/error
    HookServer->>HookServer: mark_disconnected()
    HookServer->>Queue: fail_in_flight("instance_down")
    activate Queue
    Queue-->>HookServer: status=failed
    deactivate Queue

    alt TaskCancel hook received
        Cline->>Hooks: TaskCancel hook
        activate Hooks
        Hooks->>HookServer: POST /hook {hookName:TaskCancel, taskCancel:{taskMetadata:{taskId, completionStatus}}}
        HookServer->>Queue: cancel(reason="cancelled", cline_task_id=taskId)
        activate Queue
        alt record.cline_task_id is None (pre-bind)
            Note right of Queue: Previous-task teardown: ignored (ADR-0070)
            Queue-->>HookServer: ignored (logged warning)
        else record.cline_task_id matches payload taskId
            Queue-->>HookServer: status=failed
        else mismatch
            Note right of Queue: Mismatch: ignored (logged warning)
            Queue-->>HookServer: ignored
        end
        deactivate Queue
        HookServer-->>Hooks: {ok:true}
        deactivate Hooks
    end
    end

    Note right of Client: Claude Code MCP client.<br/>Uses ask_peer_agent (blocking),<br/>submit_to_peer_agent + poll_peer_agent (async),<br/>close_peer_agent (cleanup).
    Note right of HookServer: Two channels:<br/>HTTP POST /hook - lifecycle events<br/>WebSocket /ws - liveness + task submission
    Note right of Cline: Peer agent in separate VS Code window.<br/>Workspace is LIVE tree (edits show in git diff).<br/>Never delegate production credentials.
```

Source: `docs/diagrams/vscode-agent-bridge-e2e.puml` (PlantUML original, split into 6 diagrams).
