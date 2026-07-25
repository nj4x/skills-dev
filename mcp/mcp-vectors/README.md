# MCP Vectors

Local semantic-search and GraphRAG MCP server. It uses Qdrant for vector storage and an OpenAI-compatible local model endpoint—LM Studio by default—for embeddings and optional LLM-assisted graph extraction and synthesis.

It is designed for private, local retrieval over documents and codebases. Index mutation and cleanup operations are explicit, previewable, and scoped to Qdrant; the server never deletes filesystem files.

## Features

- **Semantic search**: retrieve documents and code by meaning rather than exact keywords.
- **Codebase workflow**: `index_codebase`, `search_code`, and `get_indexing_status` provide root-scoped retrieval suitable for coding agents.
- **Safe indexing**: a re-index replaces existing chunks only after parsing, embedding, and upsert succeed.
- **Git-aware scanning**: honors `.gitignore` by default and skips excluded binary, cache, and secret-like paths.
- **Secret safeguards**: audit existing indexed payloads without exposing values, then explicitly purge exact paths from Qdrant.
- **Bounded operations**: large Qdrant scans report when their result is partial or truncated.
- **File watching**: optionally reconcile and watch an already-indexed launch directory or explicit `WATCH_DIR` paths.
- **Same-host mutation locks**: coordinate indexing and cleanup through `/tmp/mcp-vectors-locks`.
- **GraphRAG**: optionally extract entities and relationships, detect communities, generate community reports, and use them for repository-level synthesis and graph-aware reranking.

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
4. Uses the relevant reports for repository-level answers through `search_global`.

Graph-specific tools include:

- `search_entities` — case-insensitive substring lookup of code symbols by name (not semantic search); use to locate a symbol before calling the graph traversal tools.
- `get_entity_callers` — exact-name reverse call-graph lookup; returns functions/methods that call a given entity.
- `get_entity_neighbors` — BFS traversal of graph edges (imports, calls, inherits, defines, references, related) from a named entity up to a configurable hop depth.
- `list_communities` and `get_community_report` — inspect detected entity communities; may return `mode:"rebuilding"` on first use or after graph changes.
- `search_global` — architecture-level synthesis over community reports; prefer over `search_code`/`search_documents` for big-picture questions.

All entity and community tools require `ENTITY_EXTRACTION=true` and an indexed entity graph for the target root.

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

## Core tools

### Indexing and status

- `index_files` indexes explicit files or directories with replace-safe behavior.
- `index_codebase` indexes a root and reports the next safe action for already-indexed roots. Pass `dry_run=true` to preview what would be indexed without mutation.
- `get_indexing_status` reports a root's index status, metadata version, secret-audit warning, and recommended next step.
- `list_indexed_files` lists indexed files through a bounded Qdrant scan.

### Search

- `search_documents` — semantic search across **all** indexed documents (no root scoping); filter with `base_dirs`, `extensions`, or `file_types`. Use for conceptual retrieval over docs, config, or mixed content.
- `search_code` — semantic code search scoped to a single indexed root (`root_path` required). Use for meaning-based code retrieval within one project.
- `search_global` — architecture-level synthesis over GraphRAG community reports (`ENTITY_EXTRACTION=true` required). Prefer over `search_code`/`search_documents` for big-picture questions about how a repository is organized.

### Cleanup

- `clear_index` previews removal by exact file or component-safe directory path, then requires the preview's exact file and chunk counts for confirmation.

### Secret audit

- `audit_indexed_secrets` reports paths and rule IDs for potential indexed secrets, without returning secret values.
- `purge_indexed_secret_files` removes only the supplied exact indexed paths after explicit confirmation.

Run `uv run mcp-vectors --help` to inspect the server's transport options. MCP clients expose tool schemas and parameter descriptions when connected.

## Safety notes

- Secret-like paths are skipped prospectively; that does not remove data indexed before the rule existed.
- Use `audit_indexed_secrets`, then `purge_indexed_secret_files`, to clean existing indexed secret-like files.
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

- Run `get_indexing_status` for the target root.
- If it returns `not_found`, call `index_codebase` or `index_files`.
- For exploratory search, lower `min_score`.

### GraphRAG tools report that the feature is disabled

Restart the server with `ENTITY_EXTRACTION=true`. The target root must be indexed before graph entities and communities can be created.

## License

MIT
