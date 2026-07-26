# Search strategy

This project centers on `mcp/mcp-vectors`, so semantic search is available and cheap. Use it liberally for understanding; use `rg`/`fd` for surgical lookups.

## Choosing a tool

**For exact, single-site lookups** (known filename, known symbol name, literal string): use `fd`, `rg`, and `Read`.

**For conceptual, cross-file, or exploratory retrieval** (looking for code that does X, understanding architecture): use `mcp-vectors` — specifically `search_root`, which fans out across chunks, entities, and communities in a single call.

## Pre-conditions (mandatory workflow gates)

- **`search_root`**: Before calling, ensure the root is indexed (`index_codebase`). Use this for semantic, entity-graph, and architecture-level questions all at once. Not for exact symbol/string literals — use ripgrep/fd instead; not for cross-root document search — use `index_codebase` to add other roots.
