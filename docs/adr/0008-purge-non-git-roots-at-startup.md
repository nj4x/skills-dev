# Reconcile legacy roots through a durable startup epoch

The registry contained roughly 70 arbitrary subdirectory roots in addition to three repository roots. We decided to reconcile this legacy state during startup: supported-checkout subdirectory roots move to their canonical repository root; confirmed non-Git roots may be purged only with operator opt-in; linked-worktree and bare-repository roots are quarantined rather than merged or deleted. The pass must converge Qdrant vectors and SQLite graph state together.

## One atomic reconciliation epoch

A reconciliation is represented by one durable **epoch** in the registry coordinator. Its transactionally published record contains:

- epoch ID, schema version, owner lease and heartbeat;
- root-resolution and allowlist fingerprints;
- every legacy source root and every canonical destination root;
- source-to-destination mappings and quarantined roots;
- candidate and selected vector generations for each destination;
- per-destination vector and graph phases; and
- retry/failure metadata.

The membership set includes **both** legacy source identities and canonical destinations. Before any pass starts, the complete epoch is published atomically. Every index, search, graph, watcher, and cleanup operation resolves its supplied path using the current resolver, checks whether either its supplied/stored source identity **or its current destination identity** belongs to an active epoch, and returns retryable `reconciliation_in_progress` if so. A lock-losing server serves only roots absent from that complete set; it cannot skip the pass and serve a destination currently being modified.

The owner holds the registry's exclusive single-writer lock and performs reconciliation before accepting ordinary traffic. A failure to acquire the lock does not bypass the epoch guard.

### Crash recovery

The owner refreshes a lease/heartbeat. After lease expiry, a process holding the writer lock claims the same epoch using compare-and-swap; it never clears or replaces it blindly. Recovery uses durable vector active-generation manifests and graph phase markers:

- unpublished vector staging is discarded or resumed;
- a published active generation is never reconstructed by mixing staged chunks;
- unpublished shadow graphs are discarded or resumed;
- source stores remain intact until their destination vectors and graph both publish;
- if current resolver or allowlist fingerprints differ, the epoch is atomically replanned while old and newly discovered source/destination roots remain blocked.

The epoch clears only in the same registry transaction that records every destination's completion and every source's retirement, transient preservation, or quarantine.

## Reconcile complete vector generations

A source root resolving to a supported Git checkout is not re-embedded. ADR-0006 selects one complete eligible vector generation per `(file_path, canonical_root)` using its deterministic precedence. The pass stages each selected whole generation, validates expected chunk count/schema/content metadata, and atomically publishes the active-generation manifest before retiring losing generations. This is O(existing vectors), not O(source-file re-embedding), and never exposes a mixed chunk generation.

A source classified as a linked worktree or bare repository is **quarantined**: it is neither remapped into a different checkout nor automatically purged. The two-phase resolver (ADR-0006) reaches this classification before the unknown branch, so bare repositories are durably quarantined rather than perpetually retried as transient. A missing, unreadable, malformed, or otherwise unknown source is transient and preserved for a later attempt.

## Rebuild graph state before completion

Dropping a legacy SQLite graph without constructing a canonical graph would make "reconciliation complete" false. The destination graph is rebuilt from the selected vector-generation manifest, never from an arbitrary union of legacy graphs. For each selected generation, graph input uses this priority:

1. a per-file entity/edge contribution tagged with the same generation ID;
2. a durable extraction artifact for that exact generation;
3. entity extraction over the generation's stored ordered chunk text; or
4. the source file only when its current content hash matches the generation.

These approaches avoid recomputing embeddings. The graph builds into a shadow SQLite database, validates canonical root IDs and expected generation coverage, then publishes atomically. Community detection and reports are lazy derived state: graph publication marks them dirty but does not require LLM report generation before reconciliation completes.

A destination is complete and may be served only after its selected vector manifests and shadow graph both publish, every graph-eligible selected file has either a matching contribution or a recorded extraction outcome, its registry mapping is canonical, and its source roots have been retired, preserved transiently, or quarantined. If graph construction/publish fails, the epoch stays pending, sources stay intact, the destination remains blocked, and the error is logged for retry. A vector-complete but graph-incomplete destination is never reported as reconciled.

## Purge only confirmed non-Git roots

A root is eligible for purge only when its stored path exists, the current resolver meets ADR-0006's positive three-part definitive-no-Git proof (no physical `.git` ancestor, exactly the version-tested C-locale no-repository diagnostic, and empty stdout), it is not allowlisted, and it is not part of a transient, quarantined, or unsupported classification. Any generic/unrecognized Git failure is unknown and preserved. Purge removes the registry entry, SQLite graph state, and all of its full vector generations, preventing orphaned vectors.

Because deletion discards costly LLM-generated reports, `auto_purge_non_git_roots` defaults to **off**. With the default, confirmed non-Git roots are flagged but retained; operator opt-in enables purge. Subdirectory-to-supported-checkout remapping runs automatically. All reconciliation audit output—including epoch ID, roots, generation decisions, retries, quarantines, and purge counts—uses the file logger at WARN for destructive actions. Structured status exposes epoch state and remapped/purged/skipped/quarantined counts but does not replace the file audit trail.

## Considered Options

- **Keep legacy roots (rejected):** preserves two incompatible identity systems indefinitely.
- **Blindly delete roots without `.git` (rejected):** turns moved, unreadable, malformed, or unsupported Git state into data loss.
- **Merge linked-worktree contents into the main checkout (rejected):** combines divergent commits and uncommitted contents.
- **Lock only (rejected):** a second server could still serve a destination mid-remap.
- **Source-only pending list (rejected):** callers now resolve to destinations, so it leaves the mutated destination exposed.
- **Durable source-and-destination epoch with generation-safe vectors and shadow graph publication (chosen):** makes cross-store migration recoverable, observable, and complete before it becomes visible.

## Consequences

- Supported legacy subdirectory roots converge onto their canonical repository root without re-embedding or mixed vector chunks.
- Every reconciliation destination remains blocked until both its vector and graph state have been atomically published.
- Linked-worktree and bare-repository data is preserved but quarantined; uncertain paths are preserved and retried, never purged.
- A crashed reconciler can resume the same epoch without exposing a partial migration or deleting source state.
- Purge remains an explicit operator opt-in, while the system reports precisely what it remapped, skipped, quarantined, or would purge.

## Required verification

Tests cover normal repositories, submodules, `--separate-git-dir`, linked worktrees (including divergent commits and bare-repo worktrees), bare repositories, malformed Git metadata, unavailable Git/timeout/permissions/dubious ownership, Git-over-allowlist precedence, nested allowlists, resolver/config changes between lookup and mutation, partial generation rejection and deterministic ties, crashes at every vector/graph publication phase, stale-epoch recovery, lock losers checking source and destination membership, graph-build failure retaining sources and blocking the destination, and transient paths never being purged.

## Legacy evidence and serving-state boundaries

The migration does not assume legacy points already contain the generation fields introduced by ADR-0006. It first inventories which legacy fields actually exist (point ID, file path, root path, timestamp, chunk ordinal/count, content hash, parser/schema, and embedding schema). A file is remappable only when those fields prove one complete, schema-compatible ordered vector set under the deterministic selection rules. Absent proof, it is a **file-level quarantine**: its source root and graph remain intact, its vectors are not copied, and it is excluded from serving. The epoch can complete after every source is either remapped, preserved transiently, purged with opt-in, or quarantined; it must report per-file and per-root quarantine counts and reasons. Recovery is an operator-initiated verified re-index from a supported checkout, with normal explicit embedding work; no guessed grouping or silent re-embedding occurs. Thus automatic convergence applies only to proven complete legacy generations.

The epoch adds durable serving states—`active`, `reconciling`, `quarantined`, `retained_legacy`, and `transient`. Registry generation is a fence, not merely metadata: each read and mutation captures it before resolving scope, revalidates it immediately before committing or returning, and retries/rejects if it changed. Epoch publication increments the fence before any staged destination can be visible. Rootless listings, exports, and cross-root searches read one serving-state snapshot and return only active roots; if a store cannot apply that snapshot atomically, it returns `reconciliation_in_progress`. Operations retain both `canonical_root_id` and the caller's component-safe requested path, so path-scoped cleanup/deletion cannot expand from a subtree to the entire repository.

The resolver environment is controlled and locale-stable: only required variables such as `PATH`, controlled `HOME`, and `LC_ALL=C`/`LANG=C` are supplied, while all inherited `GIT_*` variables are removed. A result is definitively non-Git only when a physical ancestor scan finds no `.git` entry and controlled Git yields no working tree; a present `.git` entry plus any failing/unrecognized Git result is unknown and preserved. This is tested with discovery-affecting environment variables, invalid Git metadata, and non-English inherited locale settings.
