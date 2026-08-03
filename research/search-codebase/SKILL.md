---
name: search-codebase
description: Use when the user wants to find code, asks how X works, where X is defined, or how X relates to Y. Also use before refactoring, changing a signature, implementing multi-file work, or during code review to check blast radius.
---

| Tool | Use for |
|---|---|
| `Bash(fd)` / `Bash(rg)` / `Read` | Exact symbol, literal, or filename lookup. |
| `search_root` | Conceptual, cross-file, exploratory retrieval — semantic, entity-graph, and architecture-level in one call. |

## Pre-condition gate

`search_root` requires the root indexed. Unindexed roots return `success: true` with empty results — not an error — making empty ambiguous. Disambiguate: `index_codebase dry_run=true` → `not_found` = unindexed. When unindexed, fall back to `rg`/`fd` and offer indexing if the query is conceptual or cross-file.

## Task-shaped triggers

- Before changing a function/class signature: `search_root` for callers/usages first.
- During code review, for each modified public entity: blast-radius check via `search_root`.
- When asked "how does X relate to Y": `search_root` on both concepts before reading files.
- When planning multi-file work: `search_root` on central concepts to get the file map.

Never index or search any path under `.claude/` with `mcp-vectors`; use filesystem tools directly.
