# mcp-vectors

A local MCP server providing semantic vector search and entity-graph (GraphRAG) capabilities over indexed codebases.

## Language

### Indexing

**Root** (Indexed Root):
A git repository path that has been indexed into the vector store. Identified by a stable `root_id` (a path key derived from the canonical repository root).
_Avoid_: workspace, project, corpus

**Chunk**:
A contiguous slice of a source file, stored as a vector embedding in Qdrant. The basic unit of semantic search.
_Avoid_: segment, passage, fragment

**Reconciliation**:
The startup process that aligns the vector store and graph store against currently-indexed roots, evicting stale roots and remapping moved ones.
_Avoid_: cleanup, sync, reindex

### Entity Graph

**Entity**:
A named code symbol (function, class, module, type) extracted from indexed chunks and stored in the entity graph.
_Avoid_: node, symbol (too narrow), token

**Community**:
A cluster of related entities produced by community detection on the entity graph. Has a `community_id`, a level (for hierarchical detection), and an optional parent community.
_Avoid_: cluster (use only as an informal synonym), group

**Community Report**:
LLM-generated prose summary of a community: a title and a paragraph describing the entities and their relationships.
_Avoid_: summary, description (too generic)

### Build lifecycle

**Detection Build**:
The fast, non-LLM phase that runs graph community detection and publishes cluster structure (community IDs, entity membership, file membership). Identified by a `build_id`. A new detection build fires whenever the entity graph changes.
_Avoid_: community build (ambiguous — there are two phases)

**Report Build**:
The LLM-driven phase that generates Community Reports for each community in a committed Detection Build. Lazy — only triggered when a consumer reads community data. Identified by the same `build_id` as the Detection Build it covers.
_Avoid_: summarization build, generation pass

**Committed Generation**:
The `(graph_version, build_id)` pair identifying the most recently committed Detection Build for a root. The source of truth for which community structure is currently visible to readers.
_Avoid_: published version, active build

**Report Build Claim**:
A cross-process exclusive lease on the Report Build slot for a given root. Stored durably in the graph store as `(claimed_build_id, claim_expires_at)`. Prevents duplicate LLM generation across processes.
_Avoid_: lock, reservation

### Query protocol

**Readiness Protocol**:
The decision logic that classifies community data availability into one of three modes — `ready`, `rebuilding`, or `failed` — for a given root. Owned by RAGPipeline; hidden from MCP tool handlers.
_Avoid_: availability check, status check

**Report Coverage**:
The classification of how complete a committed Report Build is: `complete` (all communities have prose), `partial` (some failed), `rebuilding` (prose not yet generated), or `failed` (permanently parked after retry exhaustion).
_Avoid_: report status, completeness

### vscode-agent-bridge

**Bridge**:
The single orchestration object per MCP server process owning the `BridgeQueue`, `InstanceManager`, and `HookServer`. Exposes `ask()` / `submit()` / `poll()` / `close()` methods for the four MCP tools and runs the pump/sweep loop that dispatches queued tasks to the dedicated VS Code window.
_Avoid_: orchestrator, facade, coordinator

**Session** (observability):
One MCP server process lifetime, identified by its start timestamp (`YYYYMMDDTHHMMSS`). Session-scoped events (WS connect/disconnect, sweep runs, instance spawn/exit) go to a global session log at `~/.vscode-agent-bridge/logs/<session-id>.log`, independent of any workspace.
_Avoid_: run, instance (conflicts with `InstanceManager`'s Instance)

**Task Log**:
The per-task log file under `~/.vscode-agent-bridge/<normalized-workspace-dir-name>/<task-id>.log`, recording queue status transitions and hook POSTs for one task. Its events are also mirrored into the current Session's log for a single chronological view.
_Avoid_: task file, record log
