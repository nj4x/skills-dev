---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0070: Cline Bridge MCP Tool Interface

> Lineage exempt: this repository is the skills-dev tooling workspace itself and carries no
> `.data/requirements/` FS/SRS corpus. This ADR records a decision about the workspace's own
> internal tooling, not a product capability traceable to a requirement.

**Status**: Approved

**Context**

The capable, MCP-equipped agent needs a tool to reach the Cline-side worker across the queue designed in ADR-0069, under the durability policy of ADR-0068. Both those ADRs referred to the tool provisionally as `submit_request` and assumed a blocking `{status, answer}` shape, but left the concrete name, inputs, outputs, and error surface to this ticket (#40).

**Decision**

## Package

The tool ships in a new package, `mcp/cline-bridge`, not folded into `mcp-vectors`. The bridge shares no runtime dependency with vector search — no Qdrant, no embeddings — and mcp-vectors' tool list is already large enough that an unrelated tool would dilute it.

## Tool name and description

The tool is `ask_peer_model`, not `submit_request`. `submit_request` reads like a queue primitive and invites fire-and-forget use, which it is not — it blocks the calling turn for up to 180 seconds. The description tells the calling model:

- it reaches a *different* LLM, unreachable by any API key from this side
- that model has bash only — no repo access, no tools, no ability to look anything up
- the call blocks for up to 180 seconds
- each call costs a full turn on the far side: expensive, not for trivia

This supersedes the provisional name `submit_request` used in ADR-0068 point 5/6 and ADR-0069's CLI surface section; those ADRs' behavioral claims (blocking, 180s timeout, failed-on-expiry) are unchanged, only the name changes.

## Input

```python
def ask_peer_model(question: str) -> dict: ...
```

`question` only. The far model has no repo and no tools, so all context the calling model wants considered must already be inline in `question` — a separate `context` parameter would just split one string into two and invite under-filling. Timeout is fixed at 180 seconds per ADR-0068 point 5, tunable by environment variable, not per call.

An empty or whitespace-only `question` raises a validation error — this is the caller's own bug, distinct from a runtime failure, and should surface as one.

## Output

```python
{
    "id": str,        # queue record id, for tracing/debugging only
    "status": "answered" | "failed",
    "answer": str | None,   # None when status is "failed"
    "reason": str | None,   # None when answered; else a short code
}
```

`reason` is one of: `timeout`, `worker_offline`, `queue_unavailable`. The tool never raises for a runtime condition (timeout, dead worker, unwritable queue directory) — a raised exception gives the calling model less to act on than a status field it can branch on.

## Fail fast on a dead worker

Before enqueuing, `ask_peer_model` checks `worker.alive`'s mtime (ADR-0069's heartbeat file). If it is missing or older than the 5-minute staleness threshold from ADR-0068 point 3, the call returns `{status: "failed", reason: "worker_offline"}` immediately, without enqueuing and without waiting out the 180-second timeout. Blocking the capable agent for three minutes to discover nobody was listening is the worst outcome this interface can produce, and the check costs one `stat` call.

## No separate status tool

No `bridge_status` tool is exposed to the capable agent for v1. The one liveness signal that matters to the calling model is already surfaced through the fail-fast path above; a broader status view (pending/claimed/answered/failed counts) is for a human debugging the queue, and a human has ADR-0069's CLI `status` subcommand.

## No idempotency / dedupe

Repeated identical questions are not deduplicated. The call is blocking and single-shot: the caller holds no id to resubmit against, so a repeated question is a genuinely new request for a fresh answer, not a retry. Deduplication would require an index and a staleness policy for a scenario no caller in this design produces.

## Worked example

**Healthy round trip**:

```python
ask_peer_model("Explain the claim primitive in ADR-0069.")
# -> {
#      "id": "1756205412345-a3f9c2d1",
#      "status": "answered",
#      "answer": "The claim primitive is an atomic claim operation...",
#      "reason": None,
#    }
```

**Worker dead, caught at the door**:

```python
ask_peer_model("What does this function do?")
# -> {"id": None, "status": "failed", "answer": None, "reason": "worker_offline"}
```

Returns in one `stat` call, not after 180 seconds.

**Worker alive at submission, dies mid-round**:

```python
ask_peer_model("Refactor this per the style guide.")
# -> {"id": "1756205490112-b7e1f004", "status": "failed", "answer": None, "reason": "timeout"}
```

Returns after 180 seconds per ADR-0068 point 5; the queue record is moved to `failed/` as part of the same timeout.

**Malformed input**:

```python
ask_peer_model("   ")
# raises ValueError — caller's own bug, not a runtime status
```

## Consequences

- Callers get a uniform, branchable result for every runtime failure mode, at the cost of the calling model needing to check `status` rather than relying on exception handling — consistent with ADR-0068 point 5's uniform failed-on-timeout marking.
- The fail-fast liveness check adds one filesystem `stat` to every call, trading a few milliseconds for avoiding a 180-second stall in the single most common failure mode (nobody started the worker).
- `question`-only input means the calling model is fully responsible for inlining any context the far model needs; a future ticket could add a `context` field if this proves insufficient in practice, but v1 does not speculate on that need.
- Renaming `submit_request` to `ask_peer_model` leaves ADR-0068 and ADR-0069's prose referring to the old name in places; those references describe behavior, not the interface itself, and are not being edited retroactively — this ADR is the naming source of truth going forward.
