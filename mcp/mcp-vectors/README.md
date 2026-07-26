# MCP Vectors

Local semantic-search and GraphRAG MCP server. It uses Qdrant for vector storage and an OpenAI-compatible local model endpoint—LM Studio by default—for embeddings and optional LLM-assisted graph extraction and synthesis.

It is designed for private, local retrieval over documents and codebases. Index mutation and cleanup operations are explicit, previewable, and scoped to Qdrant; the server never deletes filesystem files.

## Features

- **Unified search**: `search_root` fans out across chunks (code + docs), entities (symbol graph with callers/neighbors), and communities (architecture synthesis) in one call — 3 exposed tools total.
- **Semantic search**: retrieve documents and code by meaning rather than exact keywords.
- **Codebase workflow**: `index_codebase` and `search_root` provide root-scoped retrieval suitable for coding agents.
- **Safe indexing**: a re-index replaces existing chunks only after parsing, embedding, and upsert succeed.
- **Git-aware scanning**: honors `.gitignore` by default and skips excluded binary, cache, and secret-like paths.
- **Bounded operations**: large Qdrant scans report when their result is partial or truncated.
- **File watching**: optionally reconcile and watch an already-indexed launch directory or explicit `WATCH_DIR` paths.
- **Same-host mutation locks**: coordinate indexing and cleanup through `/tmp/mcp-vectors-locks`.
- **GraphRAG**: optionally extract entities and relationships, detect communities, generate community reports, and surface them through the `entities` and `communities` channels of `search_root`.

## When to use semantic search

Use this server for conceptual, cross-file, exploratory retrieval and synthesis. Exact search and file-reading tools are better for known symbols, literals, and line-by-line inspection.

## Requirements

- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/)
- A Qdrant instance for persistent storage (optional; without `QDRANT_URL`, the server uses in-memory storage)
- An OpenAI-compatible local endpoint for embeddings, such as [LM Studio](https://lmstudio.ai/)
- A chat-capable model at the same endpoint when GraphRAG is enabled

### LM Studio

1. Start LM Studio's local API server (default: `http://localhost:1234`).
2. Load an embedding model, such as `text-embedding-nomic-embed-text-v1.5` or `all-MiniLM-L6-v2`.
3. For GraphRAG, also load a chat-capable model.

### Qdrant

For persistent storage, set `QDRANT_URL=http://localhost:6333` when starting the server. If Qdrant is not already running and Docker is available, the server starts it automatically and stores data in `~/.mcp-vectors/qdrant`. Set `QDRANT_DOCKER_AUTOSTART=false` to disable this behavior and manage Qdrant manually.

Without `QDRANT_URL`, the index is held in memory and disappears on shutdown.

## Install and run

From this repository:

```bash
cd mcp/mcp-vectors
uv sync
uv run mcp-vectors
```

The server communicates over stdio by default. The package also supports streamable HTTP options exposed by `uv run mcp-vectors --help`.

### Claude Code configuration

Add an MCP server entry that runs the package from its installed location:

```json
{
  "mcpServers": {
    "mcp-vectors": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/skills-dev/mcp/mcp-vectors",
        "mcp-vectors"
      ],
      "env": {
        "QDRANT_URL": "http://localhost:6333"
      }
    }
  }
}
```

Replace `/path/to/skills-dev` with the actual path where this repository is cloned. Configure the entry in the scope appropriate for the client that will launch it.

## GraphRAG

GraphRAG is disabled by default. Set `ENTITY_EXTRACTION=true` before starting the server to enable it:

```bash
ENTITY_EXTRACTION=true \
QDRANT_URL=http://localhost:6333 \
uv run mcp-vectors
```

During indexing, the server extracts named entities and relationships from each chunk, including optional Python AST relationships. It persists the per-root entity graph in SQLite under `~/.mcp-vectors/graphs` by default (`GRAPH_DB_DIR` overrides this location).

The graph pipeline then:

1. Detects hierarchical entity communities using Leiden when available, with a NetworkX fallback.
2. Generates LLM-backed reports summarizing each community.
3. Embeds those reports in a dedicated Qdrant collection.
4. Uses the relevant reports for repository-level answers through the `communities` channel of `search_root`.

Graph capabilities are surfaced through the `entities` and `communities` channels of `search_root`:

- **`entities` channel** — semantic entity search (ANN or substring fallback) plus automatic enrichment: callers and neighbors are fetched and attached for the top matched entities.
- **`communities` channel** — architecture-level synthesis over community reports; answers big-picture questions about how a repository is organized.

All graph channels require `ENTITY_EXTRACTION=true` and an indexed entity graph for the target root. When disabled, the channels return empty results and `search_root` still succeeds via the `chunks` channel.

Set `ENTITY_RERANK_ALPHA` above `0.0` to blend graph proximity into ordinary semantic-search ranking. `MAX_GLEANINGS` controls extra LLM extraction passes; `MAX_CHUNKS_PER_EXTRACT` limits chunks processed per extraction request.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `LM_STUDIO_URL` | `http://localhost:1234/v1` | OpenAI-compatible model endpoint |
| `EMBEDDING_MODEL` | `auto` | Embedding model name or auto-detect |
| `LLM_MODEL` | `auto` | Chat model name or auto-detect |
| `QDRANT_URL` | unset | Qdrant URL; unset uses in-memory storage |
| `QDRANT_DOCKER_AUTOSTART` | `true` | Auto-start Qdrant via Docker when `QDRANT_URL` points to localhost and Qdrant is not reachable |
| `QDRANT_COLLECTION` | `mcp_vectors` | Document-vector collection name |
| `WATCH_DIR` | unset | Comma-separated directories to watch; overrides launch-directory detection |
| `WATCH_ENABLED` | `true` | Enable active file watching and startup auto-maintain |
| `WATCH_DEBOUNCE` | `2.0` | Seconds to debounce watcher events |
| `WATCH_BATCH_INTERVAL` | `10.0` | Maximum seconds to batch watcher events |
| `AUTO_SYNC` | `true` | Reconcile and watch the already-indexed launch directory on startup |
| `RESPECT_GITIGNORE` | `true` | Exclude files matched by `.gitignore` during directory scans |
| `CHUNK_SIZE` | `512` | Characters per chunk |
| `CHUNK_OVERLAP` | `128` | Characters shared by adjacent chunks |
| `MAX_FILE_SIZE_MB` | `50.0` | Maximum file size to index |
| `MAX_SEARCH_LIMIT` | `100` | Tool/schema search-limit ceiling |
| `MAX_SCROLL_POINTS` | `50000` | Default bounded Qdrant scan size |
| `SCROLL_PAGE_SIZE` | `1000` | Qdrant scroll page size |
| `MAX_FILES_PER_SCAN` | `10000` | Filesystem scan file cap |
| `MAX_DIRS_PER_SCAN` | `2000` | Filesystem scan directory cap |
| `GRACEFUL_SHUTDOWN_TIMEOUT` | `60` | Shutdown wait time for active operations |
| `RECONCILE_ON_STARTUP` | `true` | Run registry reconciliation and cleanup on server startup |
| `AUTO_PURGE_NON_GIT_ROOTS` | `true` | During reconciliation, purge vectors and registry entries for non-git roots not in `ALLOWED_NON_GIT_ROOTS`; set to `false` to preserve legacy non-git-indexed content |
| `ALLOWED_NON_GIT_ROOTS` | (empty) | Comma-separated paths of non-git directories to preserve during reconciliation (e.g. `ALLOWED_NON_GIT_ROOTS=/opt/docs,/tmp/scratch`) |
| `ENTITY_EXTRACTION` | `false` | Enable entity graph extraction, communities, and GraphRAG tools |
| `GRAPH_DB_DIR` | `~/.mcp-vectors/graphs` | SQLite directory for per-root entity graphs |
| `ENTITY_RERANK_ALPHA` | `0.0` | Graph-proximity weight for semantic search reranking; `0.0` disables it |
| `MAX_GLEANINGS` | `0` | Additional LLM extraction passes per chunk |
| `MAX_CHUNKS_PER_EXTRACT` | `100` | Maximum chunks processed by one extraction request |
| `SEARCH_ROOT_TIMEOUT_SECONDS` | `60` | Per-call timeout for `search_root` fan-out across all three channels; invalid or zero values default to 60 |

## Core tools

Three exposed tools:

- **`index_codebase`** — index a project root. Pass `dry_run=true` to check status without indexing. If the root is already indexed, returns `indexed=false`; use `force=true` to re-index.
- **`search_root`** — search semantically across chunks (code + docs), entities (symbol graph with callers/neighbors), and communities (architecture). Returns per-channel results; top-level `success` is true if at least one channel succeeds. Not for exact symbol/string lookups — use ripgrep/fd instead.
- **`clear_index`** — preview then confirm removal of indexed data for a path from Qdrant (never touches the filesystem).

Run `uv run mcp-vectors --help` to inspect the server's transport options. MCP clients expose tool schemas and parameter descriptions when connected.

## Safety notes

- Secret-like paths are skipped prospectively during indexing; that does not remove data indexed before the rule existed. Secret remediation is out-of-band.
- Cleanup tools only change Qdrant data; they never delete local files.
- `/tmp/mcp-vectors-locks` coordinates processes on the same host only. A remote Qdrant collection shared across hosts needs external coordination.
- PDFs remain excluded by default for safety and performance, even though PDF parsing support exists.

## Development

```bash
cd mcp/mcp-vectors
uv sync --extra dev
uv run python -m compileall server.py vectors
uv run --extra dev pytest
```

## Troubleshooting

### Cannot connect to LM Studio

- Start the local API server.
- Verify `LM_STUDIO_URL`.
- Load the configured embedding model.
- When GraphRAG is enabled, load the configured chat model too.

### Qdrant connection failed

- If `QDRANT_URL` points to localhost, the server tries to auto-start Qdrant via Docker. Ensure Docker is running or start Qdrant manually.
- Verify `QDRANT_URL` is set correctly.
- Set `QDRANT_DOCKER_AUTOSTART=false` if you manage Qdrant yourself.
- Unset `QDRANT_URL` entirely to use in-memory storage for a temporary session.

### Search returns no results

- Call `index_codebase` with `dry_run=true` to check whether the root is indexed.
- If it is not indexed, call `index_codebase` without `dry_run` to index it.
- For exploratory search, lower `min_score`.

### GraphRAG tools report that the feature is disabled

Restart the server with `ENTITY_EXTRACTION=true`. The target root must be indexed before graph entities and communities can be created.

## License

MIT
