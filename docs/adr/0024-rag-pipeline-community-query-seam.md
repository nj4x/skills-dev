# Close RAGPipeline seam — add community-query interface

`server.py`'s `list_communities` and `get_community_report` tool handlers reached past
`RAGPipeline`'s public interface into private attributes (`_graph_store`, `_communities`,
`_reports_coverage`), duplicating ~40 lines of Readiness Protocol logic in each handler.
The protocol — check dirty → schedule detection → get Committed Generation → schedule
reports → gate on Report Coverage — had no single owner. We decided to add two public
async methods to `RAGPipeline`:

```python
async def list_communities(
    self, root_path: str, level: int | None, limit: int
) -> CommunitiesQueryResult

async def get_community_report(
    self, root_path: str, community_id: str
) -> CommunityReportResult
```

Each method owns the complete Readiness Protocol for its use case. The MCP tool handlers
become thin dispatchers: validate MCP input, call the pipeline method, return
`result.to_dict()`. All private-attribute access is removed from `server.py`.

`RAGPipeline` is already the coordinator for indexing, search, entity extraction, and
community scheduling; owning community query readiness is consistent with that role. The
Readiness Protocol is a lifecycle concern, not a dispatcher concern.

## Consequences

- `_reports_coverage` becomes a private implementation detail called only from within
  `RAGPipeline.get_community_report`. It is not exposed.
- `CollectionMissingError` handling (currently caught in `server.py`) moves inside the
  two pipeline methods.
- Tests for community query behaviour now test through `RAGPipeline`, not through the MCP
  server layer. This improves locality: a test no longer needs to stand up an MCP context
  to verify readiness logic.
- `search_global` in `server.py` uses its own readiness check (simpler: only detection
  readiness, not report coverage). It is left out of scope for this change, but this
  leaves two parallel readiness implementations — a live drift risk against the very
  seam-consolidation this change achieves. **Tracked follow-up:** fold `search_global`
  into a third pipeline method (e.g. `search_global(root_path, query, limit)`) so all
  Readiness Protocol logic lives in `RAGPipeline`.
