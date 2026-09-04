# Research: mcp-vectors Stalling and Ignore Rules

**Date:** 2026-09-03  
**Scope:** Index staleness detection, incremental re-indexing, stalling mechanisms, `.gitignore` vs `.git/info/exclude` separation

---

## Summary

### A. Staleness & Incremental Indexing

**How staleness is detected:** `get_indexing_status()` delegates to `vector_store.get_file_metadata_summary()`, which queries Qdrant payloads for `indexed_at` (ISO 8601 timestamp set at index time). There is **no automatic incremental re-index**; the user must notice and manually call `index_codebase(force=true)` to wipe and rebuild. The `force=true` flag triggers "replace-safe indexing" — a staged upsert that embeds chunks first, then deletes old chunks after the new ones are safely in Qdrant, so queries stay live during re-index.

**Stale index problem:** A ~4-week-old index remains in Qdrant with no auto-refresh. `index_codebase` on a stale root will return `indexed=False, status="indexed"` and decline to re-index unless `force=true` is set (server.py:834-841).

### B. Stalling Root Causes

Indexing is **not run in the background by the MCP server itself**. The caller (`index_codebase`) is an async function that runs to completion in the main event loop. However, **entity extraction is backgrounded as fire-and-forget asyncio tasks** (rag.py:716-722), so when entity extraction fails or stalls, the task may hang silently and not propagate completion/error to the user.

**Specific stalling points:**

1. **Model loading on cold start** — LM Studio embedding model load can take seconds to minutes; `_detect_embedding_dimension()` retries up to 3 times with exponential backoff (2s, 4s, 6s delays) but ultimately blocks initialization (lm_studio.py:329-355).

2. **Qdrant Docker autostart** — When Qdrant is localhost and unavailable, `ensure_qdrant_running()` attempts Docker startup and waits up to 30 seconds with health polling every 1 second (qdrant_autostart.py:79-128). If Docker isn't available or Qdrant fails to start, this can block initialization.

3. **Background entity extraction tasks** — Extraction tasks are spawned as `asyncio.ensure_future()` and tracked in a weak set (rag.py:716-722). If an extraction task hits an LLM timeout or fails, it logs a warning but doesn't fail the index operation (rag.py:904-910). The index call returns success, but extraction silently stalls in the background. No timeout is enforced on extraction; it can wait indefinitely for LLM response.

4. **Batch embedding concurrency limits** — Embeddings are batched and parallelized with a 4-concurrent-request semaphore (rag.py:958), but if a batch hangs, all subsequent embeddings are blocked. Batches use `asyncio.gather(..., return_exceptions=False)` (rag.py:965), which means a single embedding failure cancels all remaining batches.

5. **Community detection on large graphs** — Detection uses graspologic hierarchical Leiden or falls back to NetworkX greedy modularity. Large entity graphs (thousands of nodes) can spend minutes in community detection without any visible progress (community_detector.py:79-190). This runs in a background task per root, triggered after indexing.

6. **Qdrant upsert batching and polling** — Large indexing operations send many upsert requests to Qdrant. If Qdrant responds slowly or hits internal limits, the `gather` can stall waiting for all responses.

**Why the session showed "MCP task still running":** The MCP server's event loop was probably blocked waiting for:
- The `index_codebase` coroutine itself (if embedding or Qdrant upsert hung), or
- A background extraction or community-detection task that never completed, preventing the lifespan cleanup from finishing.

### C. Ignore Rules (.gitignore vs .git/info/exclude)

**Current behavior:** Both `.gitignore` and `.git/info/exclude` are loaded and merged into a single `pathspec.PathSpec` object (gitignore.py:60-61). When `respect_gitignore=true`, both are honored. When `respect_gitignore=false`, neither is checked — **there is no separate flag to honor one and skip the other**.

**Proposed fix:** Add a new parameter `respect_git_exclude` (boolean, default to `True` if not specified) to decouple the two. The split would be:

- `respect_gitignore=True, respect_git_exclude=True` (current "both honored" behavior)
- `respect_gitignore=True, respect_git_exclude=False` (new: honor `.gitignore` only)
- `respect_gitignore=False, respect_git_exclude=True` (new: honor `.git/info/exclude` only)
- `respect_gitignore=False, respect_git_exclude=False` (honor neither)

**Concrete implementation:** In `gitignore.py`, split `_load_repo_root_spec()` into `_load_gitignore()` and `_load_git_exclude()`, each returning a separate `pathspec.PathSpec`. In `GitignoreMatcher.__init__()`, accept both flags and load only the requested specs. In `rag.py.collect_indexable_files()`, pass both flags through.

**Repo impact today:**
- `.gitignore` excludes: `.DS_Store`, `.claude/*` (except `.claude/agents/`), `__pycache__`, `.pytest_cache`, `.data`, `.env`, `email/inbox/prefs.json`, `.venv/`, `*.pyc`, `*.pyo`, `.scratch`.
- `.git/info/exclude` excludes: `mcp/cline-bridge/.workspace_rag/indexing_jobs.db`, `.workspace_rag/indexing_jobs.db`, `.claude/.caveman-mode`, `.claude/.peer-agent-mode`, `.workspace_rag/`.

If `.git/info/exclude` entries were indexed with `respect_gitignore=false`, the user would get:
- `.workspace_rag/` directories (stale RAG job state databases)
- `.claude/` mode files (ephemeral user session state)

These are both safe-to-index (not secrets) but ephemeral, so exclusion makes sense.

---

## A. Staleness / Incremental Indexing

### How "already indexed" is detected

**Detection logic** (server.py:830, rag.py:1622-1630):
1. `index_codebase()` calls `await pipeline.get_indexing_status(root)`.
2. `get_indexing_status()` queries `vector_store.get_file_metadata_summary(root_path)`, which hits Qdrant payload fields.
3. The payload includes `indexed_at` (ISO 8601 timestamp, set at chunk upsert time via metadata.py:58-61).
4. Status is determined by `file_count` and `legacy_file_count`:
   - `file_count == 0` → `status="not_found"`
   - `legacy_file_count > 0` and `legacy_file_count == file_count` → `status="legacy_metadata"`
   - Otherwise `status="indexed"`

**Timestamp storage:** Timestamps live only in Qdrant chunk payloads (metadata.py:44-66, rag.py:687-707), not in a separate manifest or SQLite record. Every chunk carries `indexed_at`, but there is no global root-level "last indexed" timestamp; staleness is inferred from the presence of *any* chunks.

**No auto-refresh:** There is no scheduled or triggered incremental re-index. Once indexed, a root stays in the index unless:
- `index_codebase(force=true)` is called (user-initiated full re-index), or
- `clear_index()` is called (manual deletion from Qdrant), or
- `sync_directory()` is called (reconciliation against disk, updating only changed files).

### What "replace-safe indexing" does

When `force=true`, the pipeline calls `index_directory()` normally, but each call to `index_file()` employs a two-stage upsert (rag.py:687-712):

1. **Stage 1 — embed and upsert new chunks:** Parse file, generate embeddings, upsert chunks into Qdrant *before* deleting old chunks.
   ```python
   embeddings = await self.lm_client.get_embeddings_batch(chunk_texts)  # rag.py:689
   await self.vector_store.upsert_document_chunks(...)  # rag.py:700-707
   ```

2. **Stage 2 — delete only after new chunks are safe:** Once the new chunks are in Qdrant and queryable, delete the surplus old chunks.
   ```python
   await self.vector_store.delete_document_chunks_from(path_key, len(doc.chunks))  # rag.py:712
   ```

This ordering ensures that queries remain live and consistent even if the operation is interrupted; readers see either all-old or all-new, never a partially-deleted state.

---

## B. Stalling — End-to-End Pipeline and Blocking Points

### Indexing is not backgrounded by the MCP server

The MCP tool `index_codebase()` (server.py:815-862) is an async coroutine that runs to completion in the main event loop. It does not spawn a background thread or detach a subprocess. Callers block until indexing is done or an error is raised.

**Exception:** Entity extraction is **fully backgrounded** after chunk embedding (rag.py:716-722):
```python
if ENTITY_EXTRACTION and self._graph_store and root_id_for_graph:
    _task = asyncio.ensure_future(
        self._extract_and_merge(file_path, doc, root_id_for_graph, path_key)
    )
    _tasks_set = getattr(self, "_extraction_tasks", None)
    if _tasks_set is not None:
        _tasks_set.add(_task)
        _task.add_done_callback(_tasks_set.discard)
```

Extraction (LLM-powered entity and edge detection) runs as fire-and-forget asyncio tasks. Failures and timeouts are logged as warnings but do not block or fail the index operation.

### Full pipeline trace with blocking points

```
index_codebase (server.py:815)
├─ get_indexing_status (rag.py:1622)
│  └─ vector_store.get_file_metadata_summary(root)  [Qdrant scroll query, bounded]
├─ preview_reindex (rag.py:1605)
│  └─ collect_indexable_files (rag.py:1134)  [Filesystem walk, bounded by max_files/max_dirs/max_seconds]
└─ index_directory (rag.py:912)
   ├─ collect_indexable_files (second call, same walk)
   └─ if async Qdrant client available (config.qdrant_url):
      └─ _index_directory_parallel (rag.py:956)
         ├─ Semaphore(4) for concurrent embedding
         └─ for each file, await index_file (rag.py:628)
            ├─ Lock acquisition (locks.py:76-99)  [fcntl-based file lock]
            ├─ Parse file (parser.py:933)  [Tokenize + chunk]
            ├─ Embed chunks (lm_studio.py:411-450)  [Batched, concurrent calls to LM Studio]
            │  ├─ cold-start model load can take 30s-5m (lm_studio.py:329-355)
            │  └─ retry loop with backoff (lm_studio.py:330-355)
            ├─ Upsert chunks into Qdrant (qdrant.py)  [Batch request, Qdrant response]
            ├─ Delete old chunks (qdrant.py)  [Batch request]
            └─ [🔥 Fire-and-forget] _extract_and_merge (rag.py:849)
               ├─ Extract entities (entity_extractor.py:587)  [LLM call, unbounded timeout]
               ├─ Embed entities (rag.py:735-847)  [Concurrent embedding, bounded by semaphore]
               └─ schedule_detection (rag.py:356)
                  └─ CommunityOrchestrator.schedule_detection (community_orchestrator.py:170)
                     └─ _run_detection (community_orchestrator.py:184)
                        ├─ Get graph snapshot (graph_store.py)  [SQLite read]
                        ├─ detect_communities (community_detector.py:220-250)  [CPU-bound, no timeout]
                        │  ├─ graspologic hierarchical Leiden (O(n) to O(n²) for large graphs)
                        │  └─ fallback: NetworkX greedy modularity
                        └─ Upsert communities (qdrant.py)

  [All of the above runs in the event loop. Blocking happens at:
   - Synchronous subprocess calls (subprocess.run timeout=5 for docker)
   - Qdrant autostart (qdrant_autostart.py:88-128) runs via asyncio.to_thread
     but blocks on Docker I/O (30s startup + 2s health checks)]
```

### Specific stalling scenarios

#### 1. Model loading on cold start (lm_studio.py:323-355)

When LM Studio has not yet loaded the embedding model, the first `index_codebase()` call will block in `initialize()` → `lm_client.initialize()` → `_detect_embedding_dimension()`.

**Path:** server.py:319-342 → rag.py:279-313 → lm_studio.py:169-200 (initialize) → lm_studio.py:323-355 (_detect_embedding_dimension).

**Mechanism:** Sends an embedding probe to LM Studio (lm_studio.py:369-374). If the model is not loaded, LM Studio will load it on-demand. This can take 30 seconds to several minutes depending on model size and hardware.

**Retry logic:** Up to 3 attempts with exponential backoff (2s, 4s, 6s) if the error contains "canceled" or "failed to load" (lm_studio.py:345-352). Non-retryable errors are raised immediately.

**No timeout override:** The OpenAI SDK client has a default 120-second timeout (anthproxy_client.py:28), but there is no user-facing config to adjust LM Studio timeouts. If model loading exceeds 120s, the call fails and the server enters an error state.

#### 2. Qdrant Docker autostart (qdrant_autostart.py:88-128)

When `QDRANT_URL` points to localhost and Qdrant is unreachable, `ensure_qdrant_running()` (called via `asyncio.to_thread` in rag.py:284) will:

1. Check Docker availability (5s timeout).
2. Try to start a container (60s timeout for `docker run`).
3. Poll for health every 1 second, up to 30 seconds.

**Total blocking time:** Up to 60s + 30s = 90s (plus subprocess overhead).

**No override:** There is no config to skip autostart or adjust timeouts. If Docker is broken or the user prefers manual Qdrant setup, the 90s delay is unavoidable.

#### 3. Background entity extraction stalling (rag.py:849-910)

Entity extraction runs fire-and-forget after chunk embedding completes. If the LLM call hangs, the task stalls indefinitely.

**Path:** rag.py:849 (_extract_and_merge) → entity_extractor.py:587 (extract_file) → call to LLM.

**Timeout:** None. The LLM client (anthproxy or lm_studio) has its own HTTP timeout (120s), but there is no per-file or per-root extraction timeout. If a file has very large chunks or the LLM is slow, extraction can hang.

**Impact on reported success:** `index_codebase()` returns success even if extraction is still pending (rag.py:844-852). The user sees "files_indexed: X" and has no indication that extraction is ongoing. Later, if extraction fails, the error is logged as a warning (rag.py:904-910) but never surfaced to the user.

**Example of silence:**
```
File 1: chunks embedded → extract_and_merge spawned as background task
File 2: chunks embedded → extract_and_merge spawned
...
File N: chunks embedded → extract_and_merge spawned
→ index_codebase() returns {"success": True, "files_indexed": N, ...}
→ User thinks indexing is done
→ Meanwhile, File 5's extraction is stuck in entity_extractor.py, waiting for LLM response
→ No notification to user; only a log line "Background entity extraction failed"
```

#### 4. Community detection on large graphs (community_detector.py:79-190)

After all files are indexed and a certain threshold of entities is reached, `schedule_detection()` is called (rag.py:899), which runs `_run_detection()` (community_orchestrator.py:184).

**CPU-bound work:** Leiden or NetworkX modularity is O(n log n) to O(n²) depending on graph density and algorithm. For a graph with 10,000 entities, this can take 10-30 seconds.

**No timeout or cancellation:** Detection runs to completion in a background task. If the graph is extremely large or densely connected, it can stall for minutes (community_detector.py:92, 171).

**Detection result is cached:** Once detection completes, results are cached in `_graph_stats` (rag.py:618-626) and community reports are generated lazily on demand (rag.py:439-494). If the user calls `get_community_report()` before detection finishes, they get an error.

### Why "1 MCP task still running" appears

The Claude Code session likely hit one or more of the above:

1. Extraction task was backgrounded and stalled waiting for LLM response, preventing `index_codebase()` from completing.
2. Community detection was running in the background, blocking the CommunityOrchestrator's event loop.
3. Qdrant Autostart was in progress (Docker startup, health polling).
4. A Qdrant upsert batched request was hanging (network or Qdrant overload).

The MCP server's event loop was blocked waiting for these operations, so other concurrent requests (like status checks) also appeared to hang or queue.

### Logs and diagnostics

**Log file location:** `~/.mcp-vectors/logs/mcp-vectors.log` (rotating, 10 MB max, 3 backup files) (server.py:91-114).

**Log level:** INFO by default. Search for:
- `"[<req_id>] index_codebase start"` — when indexing starts.
- `"[<req_id>] index_codebase done (<ms>ms)"` — when indexing finishes (if successful).
- `"[<req_id>] index_codebase raised (<ms>ms)"` — when indexing fails.
- `"Background entity extraction failed"` — extraction task stalled or failed.
- `"Startup sync:"` — reconciliation against disk (if watcher is enabled).
- `"Qdrant not reachable"` — autostart is attempting Docker.

**Request ID format:** 12-character hex string (UUID truncated), e.g., `a1b2c3d4e5f6`. Every MCP tool call gets a unique ID for tracing (server.py:562-577).

**How to check if stuck:** Look at the log's latest entry timestamp. If the last timestamp is many seconds/minutes old and there are no "done" or "raised" lines after a "start" line, the indexing task is hung.

### Cancellation and status

**No built-in cancellation:** There is no way to cancel an in-flight `index_codebase()` call. To stop a stalled indexing:
1. Kill the MCP server process (`kill -9 <pid>`).
2. Or wait for graceful shutdown (60-second timeout by default, configurable via `GRACEFUL_SHUTDOWN_TIMEOUT`).

**No status endpoint:** There is no MCP tool to check the status of an in-flight indexing operation. The only way to infer progress is by watching logs in real-time.

---

## C. Ignore Rules: .gitignore vs .git/info/exclude

### Current implementation (pathspec library)

**Pathspec merging** (gitignore.py:58-62):
```python
def _load_repo_root_spec(self) -> None:
    lines: list[str] = []
    lines.extend(self._read_lines(self.repo_root / ".gitignore"))
    lines.extend(self._read_lines(self.repo_root / ".git" / "info" / "exclude"))
    self._specs[self.repo_root] = self._compile(lines)
```

Both files' lines are concatenated into a single list and compiled into one `pathspec.GitIgnoreSpec` object. Matching is done line-by-line using git's wildcard semantics (pathspec library, version ≥0.12.0).

**Conditional behavior:**
- `respect_gitignore=True` → Use the merged spec (both files honored).
- `respect_gitignore=False` → Skip matching entirely (neither file consulted).

**No separate flag:** There is no way to honor `.gitignore` but skip `.git/info/exclude`, or vice versa.

### Proposed separation

**New API:**
```python
class GitignoreMatcher:
    def __init__(self, repo_root: Path, respect_gitignore: bool = True, respect_git_exclude: bool = True):
        self.repo_root = repo_root
        self.respect_gitignore = respect_gitignore
        self.respect_git_exclude = respect_git_exclude
        self._specs: dict[Path, Optional["pathspec.PathSpec"]] = {}
        self._load_repo_root_spec()

    def _load_repo_root_spec(self) -> None:
        lines: list[str] = []
        if self.respect_gitignore:
            lines.extend(self._read_lines(self.repo_root / ".gitignore"))
        if self.respect_git_exclude:
            lines.extend(self._read_lines(self.repo_root / ".git" / "info" / "exclude"))
        self._specs[self.repo_root] = self._compile(lines)
```

**Integration:**
1. Update `RAGPipeline.collect_indexable_files()` (rag.py:1134-1240) to accept both flags.
2. Update `GitignoreMatcher.for_path()` class method to accept both flags (currently only takes `path`).
3. Update all call sites in `rag.py` (index_directory, sync_directory) to pass both flags through.
4. Update server.py tools (`index_codebase`, deprecated `index_files`) to expose `respect_git_exclude` parameter.

**Backward compatibility:** If `respect_git_exclude` is not provided, default to `True` (current "both honored" behavior). Existing code that only specifies `respect_gitignore` will continue to work.

### Files excluded today (concrete impact)

**`.gitignore` entries:**
```
.DS_Store
.claude/*
!.claude/agents/        # exception: DO index .claude/agents/
__pycache__
.pytest_cache
.data
.env
email/inbox/prefs.json
.venv/
*.pyc
*.pyo
.scratch
```

**`.git/info/exclude` entries:**
```
mcp/cline-bridge/.workspace_rag/indexing_jobs.db
.workspace_rag/indexing_jobs.db
.claude/.caveman-mode
.claude/.peer-agent-mode
.workspace_rag/
```

**If `.git/info/exclude` were *not* honored (new mode `respect_gitignore=True, respect_git_exclude=False`):**
- `.workspace_rag/` directories would be indexed (stale RAG state databases, ephemeral).
- `.claude/.caveman-mode` and `.claude/.peer-agent-mode` would be indexed (user session state, ephemeral).
- Impact: Search results would include irrelevant session-state files. Safe from a secrets perspective (no credentials), but clutter.

**If `.gitignore` were *not* honored (new mode `respect_gitignore=False, respect_git_exclude=True`):**
- `.DS_Store`, `__pycache__`, `.pytest_cache`, `.venv/`, `*.pyc`, `*.pyo` would be indexed.
- Impact: Search results would include build artifacts, Python cache, macOS metadata. Very noisy.

### Implementation details (file paths and functions)

**Files to modify:**

1. **gitignore.py:35-62** — `GitignoreMatcher.__init__()` and `_load_repo_root_spec()`: Add `respect_gitignore` and `respect_git_exclude` params.

2. **gitignore.py:42-56** — `GitignoreMatcher.for_path()`: Add both params to the class method signature and pass to `__init__()`.

3. **rag.py:1134-1240** — `RAGPipeline.collect_indexable_files()`: Accept both params (currently has `respect_gitignore: Optional[bool] = None`), pass to `GitignoreMatcher.for_path()`.

4. **rag.py:912-935** — `RAGPipeline.index_directory()`: Accept both params (currently has `respect_gitignore: Optional[bool] = None`), pass to `collect_indexable_files()`.

5. **rag.py:980-1014** — `RAGPipeline.sync_directory()`: Accept both params, pass through.

6. **server.py:815-862** — `index_codebase()` MCP tool: Add `respect_git_exclude` parameter (Annotated field), pass to `pipeline.index_directory()`.

7. (Deprecated) **server.py:603-666** — `index_files()` (pending deletion per ADR-0052): Add `respect_git_exclude` param for consistency, pass through.

---

## D. Practical Recommendations

### When indexing appears stalled

**Step 1: Check the log**
```bash
tail -f ~/.mcp-vectors/logs/mcp-vectors.log
```
Look for:
- Request ID and operation name (e.g., `[a1b2c3d4e5f6] index_codebase start`).
- Elapsed time: if "start" has no matching "done" or "raised" within 30+ seconds, the operation is hung.
- LLM timeouts: search for "timeout" or "failed to load".
- Qdrant issues: search for "not reachable" or "collection missing".

**Step 2: Identify the blocking component**
- If logs show `"LM Studio embedding dimension probe failed"`, the model is not loaded or LM Studio is offline. Restart LM Studio and retry.
- If logs show `"Qdrant not reachable"` and then Docker startup attempts, Qdrant autostart is in progress; wait 90 seconds.
- If logs show entity extraction warnings after indexing completes, extraction stalled in background; check if LLM service is responsive.

**Step 3: Recovery options**
- **Model loading stuck:** Kill the MCP server, ensure LM Studio is running and model is loaded, restart the server.
- **Qdrant unavailable:** Start Qdrant manually or ensure Docker daemon is running (`docker ps`).
- **Extraction stalled:** No user action needed; extraction runs in background and failures are logged. The index is already complete; search will work.
- **Community detection stalled:** Wait or ignore; detection is lazy and on-demand. The index is complete. Calling `get_community_report()` will trigger or wait for detection.

### Configuration knobs

**Environment variables affecting indexing performance/timeouts:**

| Variable | Purpose | Default | Impact |
|---|---|---|---|
| `GRACEFUL_SHUTDOWN_TIMEOUT` | Max time to wait for in-flight ops before killing server | 60s | Higher values allow long-running indexing to complete before shutdown. |
| `QDRANT_DOCKER_AUTOSTART` | Whether to auto-start Qdrant in Docker | `true` | Set to `false` if managing Qdrant manually. |
| `QDRANT_URL` | Qdrant connection URL | (none; in-memory mode) | Set to `http://localhost:6333` to use external Qdrant. |
| `SEARCH_ROOT_TIMEOUT_SECONDS` | Timeout for `search_root` tool channels (chunks, entities, communities) | 60s | Increase if searches hang on large indexes. |
| `LM_STUDIO_HOST`, `LM_STUDIO_PORT` | LM Studio connection | `localhost:1234` | Point to remote LM Studio if needed. |
| `ENTITY_EXTRACTION` | Enable/disable entity and graph features | (auto-detected by model availability) | Set to `false` to skip extraction and community detection. Speeds up indexing. |

**Config file (`~/.config/mcp-vectors/config.toml` or env):**
- `chunk_size`, `chunk_overlap`: Smaller chunks reduce embedding latency but increase Qdrant upserts.
- `max_file_size_mb`: Files larger than this are skipped. Default 100 MB.
- `max_files_per_scan`, `max_dirs_per_scan`: Bounds on directory walk to prevent OOM or timeouts on large repos.
- `respect_gitignore`: Boolean; set to `false` if you want to index everything.

### Avoiding stalls in production

1. **Pre-warm the embedding model:** Before calling `index_codebase()`, ensure LM Studio has loaded the embedding model. You can do this by manually sending one embedding request via LM Studio's UI or API.

2. **Use `sync_directory()` instead of `force=true` re-index:** `sync_directory()` only re-embeds changed files (by mtime and content hash), whereas `force=true` re-indexes everything. For large repos, sync is much faster.

3. **Disable entity extraction for initial indexing:** Set `ENTITY_EXTRACTION=false` to skip LLM extraction and community detection. You can enable it later after the initial index is complete.

4. **Increase timeouts if on slow hardware:** Set `GRACEFUL_SHUTDOWN_TIMEOUT=180` and increase search channel timeouts via `SEARCH_ROOT_TIMEOUT_SECONDS=120`.

5. **Monitor logs during first run:** Watch `~/.mcp-vectors/logs/mcp-vectors.log` to identify bottlenecks (model load, Qdrant startup, LLM response time) and adjust configuration before running on large codebases.

6. **Use smaller codebases for testing:** Start with a single repo or a subset of files to understand baseline performance, then scale up.

---

## File References

- **Staleness detection:** server.py:830, rag.py:1622-1630, metadata.py:44-66
- **Replace-safe indexing:** rag.py:687-712
- **Background extraction:** rag.py:716-722, rag.py:849-910
- **Model loading:** lm_studio.py:323-355
- **Qdrant autostart:** qdrant_autostart.py:88-128, rag.py:284
- **Community detection:** community_detector.py:79-190, rag.py:356-364
- **Logging setup:** server.py:87-127
- **.gitignore parsing:** gitignore.py:58-62, gitignore.py:27-139
- **Config schema:** vectors/config.py (all timeout/size/concurrency settings)
- **Locks:** vectors/locks.py (fcntl-based per-operation locks)
