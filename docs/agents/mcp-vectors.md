# mcp-vectors package

`mcp/mcp-vectors` is the repository's standalone Python package: a local semantic-search and optional GraphRAG MCP server. `server.py` exposes the MCP tools; `vectors/` separates configuration, parsing/chunking, Qdrant storage, safety and path filtering, watchers, LLM integration, and entity/community graph operations. `mcp/mcp_common` provides shared MCP helpers and is consumed as a local `uv` source dependency.

## Development commands

Run from `mcp/mcp-vectors`:

```sh
uv sync --extra dev
uv run python -m compileall server.py vectors
uv run --extra dev pytest
uv run --extra dev pytest tests/test_safety.py
uv run --extra dev pytest tests/test_safety.py::test_name
```

The test suite is scoped to `mcp/mcp-vectors/tests`; replace `test_name` with an actual test function. No lint command is configured in the tracked Python project metadata. To run the MCP server locally, use `uv run mcp-vectors`; see `mcp/mcp-vectors/README.md` for required local model/Qdrant configuration and optional GraphRAG settings.

## Storage model

The server keeps vector data in Qdrant and graph data in local SQLite. Index mutation and cleanup are deliberately explicit and scoped to those stores; they never delete indexed filesystem paths.
