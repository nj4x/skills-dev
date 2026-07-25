# Search strategy

This project centers on `mcp/mcp-vectors`, so semantic search is available and cheap. Use it liberally for understanding; use `rg`/`fd` for surgical lookups.

## Choosing a tool

**For exact, single-site lookups** (known filename, known symbol name, literal string): use `fd`, `rg`, and `Read`.

**For conceptual, cross-file, or exploratory retrieval** (looking for code that does X, understanding architecture): use `mcp-vectors` tools (`search_code`, `search_entities`, `get_entity_neighbors`, `get_entity_callers`, `search_global`).

## Pre-conditions (mandatory workflow gates)

- **`get_entity_callers`**: Before modifying a public function, method, or class signature, always call `get_entity_callers` first to identify all impacted call sites. Not for locating a specific symbol — use `search_entities` or `search_code` for that.
- **`get_entity_neighbors`**: Before answering "how does X relate to Y" or tracing a dependency chain, always call `get_entity_neighbors` (depth 2) before reading files. Not for finding a symbol by name — use `search_entities` first.
- **`search_entities`**: Before calling `get_entity_callers` or `get_entity_neighbors`, always call `search_entities` first to confirm the exact entity name. Not for conceptual or semantic retrieval — use `search_code` for that.
- **`search_global`**: Before making architecture-level claims about repository organization, always call `search_global` first. Not for locating a specific symbol or file — use `search_entities` or `search_code` for that.
