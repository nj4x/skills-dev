# Use discriminated union dataclasses for community-query results

`RAGPipeline.list_communities` and `RAGPipeline.get_community_report` (ADR-0024) must
signal three outcomes to their callers: data is ready, data is rebuilding, or a hard
error occurred. `server.py`'s current pattern constructs dicts inline
(`{"success": bool, "mode": str, ...}`), which bakes the MCP wire shape into the
pipeline. We decided to return a **genuine discriminated union**: a closed set of variant
subclasses per query, where each variant carries exactly the fields valid for its case and
nothing more. Illegal combinations (e.g. "ready but no data", "rebuilding with an error")
are unrepresentable because the fields simply do not exist on the other variants. There is
no `success` boolean — the variant *is* the outcome, so there is no redundant flag to keep
in sync with the mode and no way to express a contradictory state such as
`success=True, mode="rebuilding"`.

```python
# CommunitiesQueryResult := Ready | Rebuilding | Error   (per query type)

@dataclass(frozen=True)
class CommunitiesReady:
    communities: list           # always present; [] means "no communities", not "not ready"
    def to_dict(self) -> dict: ...

@dataclass(frozen=True)
class CommunitiesRebuilding:
    reason: str                 # e.g. "reports_dirty" | "detection_pending"
    def to_dict(self) -> dict: ...

@dataclass(frozen=True)
class CommunitiesError:
    error: dict                 # {"code": str, "message": str}
    def to_dict(self) -> dict: ...

CommunitiesQueryResult = CommunitiesReady | CommunitiesRebuilding | CommunitiesError
```

`CommunityReportResult` is the identical three-variant shape, with `CommunityReportReady`
carrying a single `report: dict` instead of a list. Callers discriminate with
`match`/`isinstance` on the variant type; each variant's `to_dict()` emits the MCP wire
shape (including the `mode` string) so the pipeline never constructs MCP-shaped dicts
itself. The wire format keeps a `mode` field with three values — `"ready"`,
`"rebuilding"`, `"error"` — derived from the variant, so the boundary contract still has a
single discriminant and the old redundant `success` flag disappears from the wire too.

`to_dict()` is a deliberate, thin translation layer *owned by the pipeline*. The seam is
not "the pipeline knows MCP format" — it is "the pipeline defines the boundary vocabulary
(the `mode` strings, the `error` shape) and `to_dict()` renders that vocabulary into a
plain dict." `server.py` gains zero knowledge of wire format; it passes the dict through.
This is distinct from the rejected "return dict directly" option, where wire shape would be
constructed inline at call sites with no typed variant guarding it. A separate MCP-adapter
layer translating variants to dicts was considered and rejected: it adds a module for a
one-line mapping, and the variant type — not the dict — is the contract every non-MCP
caller consumes.

## Considered Options

**Return dict directly (mirror current server.py shape):** Minimal change, but bakes the
MCP wire format into `RAGPipeline`. Any non-MCP caller (CLI, gRPC, tests) would need to
parse `{"success": True, "mode": "ready", ...}` instead of a typed object. Rejected.

**Single flat dataclass with `success: bool` + `mode: str` + nullable `data`/`error`:**
The shape originally proposed here. Rejected because `success` is redundant with `mode`
and the four fields admit contradictory states (`success=True` with `mode="rebuilding"`,
or `mode="ready"` with `data=None`) — precisely the illegality a discriminated union
exists to prevent. Every consumer would need defensive checks to reject combinations the
type nominally permits.

**Return data or raise exception:** `list_communities` returns `list[dict]` on ready,
`None` on rebuilding, raises on failure. Mixes data and control flow; tests must
distinguish `None` (rebuilding) from `[]` (empty community list). Rejected.
