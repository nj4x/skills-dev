---
name: search-codebase
description: Use when searching the codebase/repository. Also use before changing a signature, during code review blast-radius checks, or when planning multi-file work.
---

| Tool | Use for |
|---|---|
| `Bash(fd)` / `Bash(rg)` / `Read` | Exact symbol, literal, or filename lookup. |
| `search_root` | Conceptual, cross-file, exploratory retrieval — semantic, entity-graph, and architecture-level in one call. |

## Pre-condition gate

`search_root` requires the root to be indexed. Pass `dry_run=true` to `index_codebase` to check status without indexing. A missing index causes a tool error — fall back to `rg`/`fd` and offer indexing when the search is substantial.

## Task-shaped triggers

- Before changing a function/class signature: `search_root` for callers/usages first.
- During code review, for each modified public entity: blast-radius check via `search_root`.
- When asked "how does X relate to Y": `search_root` on both concepts before reading files.
- When planning multi-file work: `search_root` on central concepts to get the file map.

Never index or search any path under `.claude/` with `mcp-vectors`; use filesystem tools directly for worktree-specific inspection.
