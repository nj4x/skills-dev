@AGENTS.md

## Pre-conditions

`search_root` requires the codebase to be indexed first (`index_codebase`).

- `search_root` — Use this when you need to search a codebase root semantically, by entity name, and architecturally all at once. Not for exact symbol/string literals — use ripgrep/fd instead; not for cross-root document search — use `index_codebase` to add other roots.
