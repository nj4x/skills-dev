# Entity Extraction and Community Detection Run in Parallel

## Context

After a file is indexed, two background tasks fire: entity extraction (writes entities to SQLite and Qdrant) and community detection (clusters entities into communities, writes the `entity_community` join table). Detection's join-table write depends on knowing which entities exist — it iterates cluster assignments and writes `(entity_id, community_id, root_id, build_id)` tuples. If entity extraction hasn't completed when detection runs, some or all entities may be absent from SQLite.

A question arises: should detection wait for entity extraction to complete before writing the join table, or should both tasks run independently?

## Decision

Entity extraction and community detection spawn as independent background tasks (`asyncio.ensure_future`) with no explicit ordering between them. Detection writes the join table only for entities that are present in SQLite at commit time:

```python
# In detection, after clustering:
if graph_store.entities_exist(root_id):
    write_entity_community_join_table(...)
else:
    logger.info("Skipping entity_community join table; entities not yet available for root=%s", root_id)
```

If entities are absent (extraction still running or not yet triggered), detection skips the join table for this build. On the next detection run (after extraction completes), the join table is written.

## Considered Options

- **Parallel, detection skips join table if extraction isn't ready** *(chosen)* — no new blocking; both tasks proceed independently; join table arrives on the next detection build; targeting is eventually available.
- **Detection waits for extraction with timeout** — join table available sooner if extraction is fast; adds latency to detection; timeout is a tuning knob; introduces a new blocking path in the background task DAG.
- **Serial: extraction is a prerequisite for detection** — join table always populated on first detection build; sacrifices parallelism; extraction latency blocks detection; most conservative but least performant.

## Consequences

- The first detection build after a fresh index may not have a join table. Targeting falls back to full summarization (zero-match fallback, ADR-0011) until the next detection build.
- On subsequent detection runs (after extraction has completed), the join table is written and targeting becomes active.
- No new coordination primitives (events, locks, semaphores) are needed between extraction and detection.
- Extraction and detection remain independently restartable and observable; a failure in one does not block the other.
- The targeting log records `entities_found: 0` when the join table is absent, making the "extraction lag" pattern observable to operators.
