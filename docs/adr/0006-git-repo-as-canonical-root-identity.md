# Use a supported Git working-tree root as the canonical vector-index identity

The graph registry accumulated 73 roots because `root_id` was derived from whichever arbitrary directory a caller supplied (or from `file.parent`). Only three of those roots were real repositories; the rest were overlapping subdirectories with fragmented graphs.

We decided that `PathPolicy.root_id()` accepts only a **supported Git working tree** (or an explicit non-Git allowlist root from ADR-0007). A supplied file or subdirectory still scopes which files are indexed, but its identity resolves to the supported repository's working-tree root. This makes the repository—not caller-selected directory—the graph and vector namespace. Qdrant `base_dirs` continues to provide subdirectory search scope.

## Use Git plumbing, never `.git` shape heuristics

The resolver physical-resolves the input path (using a file's parent as the Git probe) and invokes Git with a sanitized environment that removes `GIT_DIR`, `GIT_WORK_TREE`, and `GIT_COMMON_DIR`. It obtains `--show-toplevel`, `--absolute-git-dir`, `--git-common-dir`, and `--is-bare-repository`, normalizes the returned paths, and classifies the result from those authoritative values. We do not manually parse `gitdir:` files or infer type from a `worktrees/` or `modules/` path.

There is deliberately **no filesystem-only fallback**. Without Git's discovery semantics, strict Git-over-allowlist precedence cannot be proven safely. A missing Git executable, timeout, malformed output, malformed Git metadata, dubious ownership, permission failure, or other Git error is an **unknown resolution**, not evidence that the path is non-Git.

### Exact resolver state machine

The controlled resolver uses a **two-phase probe** so that bare repositories can be classified without `--show-toplevel`, which forces a nonzero exit on bare repos and would make their branch unreachable.

**Phase 1** — runs unconditionally:

```
git -C <probe> rev-parse --is-inside-work-tree --is-bare-repository
                          --absolute-git-dir --git-common-dir
```

A zero exit yields four parseable lines. Normalize `--git-common-dir` against the probe working directory before comparing, because Git returns it as a **relative path** for the main checkout (e.g. `.git`) but as an absolute path for linked worktrees and separate-git-dir repositories; without normalization a main checkout could be misidentified as a linked worktree.

Classification at phase 1:

- `is-bare-repository=true` on any exit → **bare repository** → `unsupported_bare_repository` immediately; do not proceed to phase 2.
- Zero exit, `is-inside-work-tree=true`, `abs-git-dir ≠ normalized-common-dir` → **linked worktree** → `unsupported_linked_worktree`.
- Zero exit, `is-inside-work-tree=true`, `abs-git-dir == normalized-common-dir` → non-bare, non-linked working tree; proceed to phase 2.
- Zero exit, `is-inside-work-tree=false`, `is-bare-repository=false` (probe is inside a `.git` directory itself, or other edge layout) → **unknown**; preserved, never purged or allowlist-consulted.

A nonzero exit after classifying bare is **definitively no repository** only when all three hold: (1) the physical ancestor scan found no `.git` file or directory at any ancestor; (2) the C-locale stderr exactly matches the version-tested no-repository diagnostic `fatal: not a git repository (or any of the parent directories): .git`; and (3) stdout is empty. Every other nonzero result is unknown.

**Phase 2** — runs only for confirmed non-bare, non-linked working trees:

```
git -C <probe> rev-parse --show-toplevel --absolute-git-dir --git-common-dir
```

Normalize common-dir as above. Classification:

- `abs-git-dir == normalized-common-dir` and `abs-git-dir` does **not** end with `/.git/modules/<name>` → **normal working tree** (covers both `<super>/.git`-resident and `--separate-git-dir` external Git directories, since linked worktrees are already excluded in phase 1); use `--show-toplevel` as canonical root.
- `abs-git-dir` lives under `<super>/.git/modules/` (i.e. ends with `/.git/modules/<name>`) → **submodule**; use `--show-toplevel` as its own canonical root.

Any phase-2 nonzero exit or unexpected field layout is unknown.

The resolver records the Git binary version in its result and refuses an untested version for mutating operations until the no-repository compatibility test passes (reads may report unknown). Tests enumerate all accepted field layouts for every supported Git-version range, pin the sole accepted no-repository diagnostic, and cover the relative-common-dir normalization case explicitly. A bare repository with a malformed or empty git-dir field falls into unknown at phase 1 and is not purged.


| Git-plumbing result | Root behavior |
| --- | --- |
| Normal working tree | Use `--show-toplevel`. |
| Submodule | Use the submodule's own `--show-toplevel`; it is an independent repository. |
| `--separate-git-dir` working tree | Use `--show-toplevel`, not the external Git directory. |
| Linked worktree (`git-dir != common-dir`) | Reject indexing and all content mutations with `unsupported_linked_worktree`. |
| Bare repository | Reject source indexing with `unsupported_bare_repository`; it has no working tree. |
| Discovery/tool failure | Return a directed unknown-resolution error; do not write, remap, purge, or consult an allowlist. |

### Linked worktrees are not merged

Linked worktrees can hold different commits, branches, indexes, and uncommitted contents. Collapsing their arbitrary checkout paths into one graph would combine incompatible repository-relative files; their absolute paths would not reliably deduplicate either. They therefore receive no content `root_id`, cannot be indexed, and are never remapped into a primary checkout. ADR-0008 quarantines legacy linked-worktree roots for operator action. The common Git directory is diagnostic metadata only, never authority to merge checkout contents.

## Atomic vector generations

The prior `(file_path, root_path)` dedup rule was insufficient: it could combine chunks from unrelated indexing runs or preserve stale chunks. A **vector generation** is the complete output of one file-indexing run, identified by canonical file path, content hash, ordered chunk hashes and expected chunk count, parser/chunker schema version, embedding model/vector schema, and an `index_run_id` (or equivalent generation ID).

A legacy generation is eligible only when all its chunks are present, unique, schema-compatible, and provably belong to that one generation. Incomplete or ambiguous groups are quarantined; they are never mixed with another generation. For each `(file_path, canonical_root)`, migration selects exactly one full generation in this deterministic order:

1. Exclude incomplete or vector-schema-incompatible generations.
2. Prefer a generation whose content hash matches the accepted supported checkout, when available.
3. Prefer the newest indexed timestamp.
4. Prefer one already under the canonical destination.
5. Break remaining ties by normalized source root and generation ID lexically.

The selected generation is staged and validated as a whole. Its points include the generation ID, and searches consult an atomically published active-generation manifest. Losers are deleted only after that manifest commits. Thus no active file consists of mixed chunks, and re-keying does not invoke an embedding model.

## Cache only validated resolutions

A cached resolution stores a fingerprint of the probe path, resolved top-level path, `.git` entry metadata, absolute Git directory metadata, common Git directory metadata, Git classification, and the canonical generation of `allowed_non_git_roots` configuration.

Before **every** vector, graph, registry, reconciliation, or deletion mutation, the operation performs an uncached Git-plumbing resolution and recomputes this complete fingerprint. No root write proceeds until it matches the operation's resolution token. A mismatch discards cached state and restarts resolution; bounded repeated changes return retryable `root_resolution_changed` without writing. This prevents `git init`, Git-directory relocation, worktree conversion, or allowlist edits from sending a write to a stale root.

## Considered Options

- **Arbitrary caller directory (rejected):** fragments overlapping graphs and duplicates data.
- **Require callers to discover repo roots (rejected):** breaks ergonomic file and subdirectory indexing.
- **Collapse all linked worktrees through `commondir` (rejected):** conflates divergent checkout content.
- **Manual `.git` pointer parsing (rejected):** mishandles submodules, separate Git directories, malformed pointers, and Git-specific discovery rules.
- **Supported Git working-tree root via Git plumbing (chosen):** preserves ergonomic scoped indexing while giving each accepted path one authoritative identity.

## Consequences

- Every accepted Git path in a normal checkout, submodule, or separate-Git-directory checkout maps to its working-tree root; submodules remain separate repositories.
- Linked worktrees and bare repositories are deliberately rejected for source indexing rather than silently merged or assigned an arbitrary root.
- Vector migration and ordinary replacement operate on complete, atomic file generations, with deterministic survivor selection and no re-embedding during remap.
- A cached resolution is a performance optimization only; pre-mutation validation makes it impossible for a stale cache entry to authorize a root write.
- ADR-0008 defines reconciliation of legacy roots across Qdrant and SQLite graph state.

## Resolver protocol and requested scope

The resolver runs Git with an explicit allowlisted environment: `PATH`, a controlled `HOME`, and `LC_ALL=C`/`LANG=C`; it removes every inherited `GIT_*` variable, including discovery-affecting variables such as `GIT_CEILING_DIRECTORIES` and `GIT_DISCOVERY_ACROSS_FILESYSTEM`. It requests absolute output. It treats a path as **definitively non-Git** only when (a) a physical upward scan finds no `.git` entry at any ancestor and (b) the controlled Git invocation yields no supported working-tree result. A `.git` entry with any non-successful or unrecognized Git result is unknown, never non-Git. This avoids locale-dependent diagnostic parsing and makes all other nonzero outcomes—including malformed metadata and permissions—safe failures.

Root identity never replaces the caller's path selector. Every operation carries an immutable `OperationScope { canonical_root_id, requested_path }`, where `requested_path` is physical-resolved and component-wise contained by the root. `canonical_root_id` selects graph/vector namespace; `requested_path` selects the intended file or subtree. Indexing, watching, searching, synchronization, cleanup, and deletion must apply the selector after namespace resolution. A root-level destructive action requires an explicit requested path equal to the root; a subdirectory operation cannot affect siblings or the full repository.

## Epoch fencing for mutations and reads

An operation captures the registry epoch generation while resolving its scope and rechecks it immediately before every mutation and immediately before returning a read result. If the generation changed, it discards partial work and retries or returns `reconciliation_in_progress`; writers additionally acquire the registry fence for their final commit. Epoch publication increments the generation before destination manifests or graphs can change, so a pre-existing read cannot return a mixed pre/post-epoch view. These rules apply even if a process has a different local resolver or allowlist fingerprint from the epoch: affected traffic blocks rather than trusting local membership alone.

Rootless and cross-root APIs obtain one registry snapshot of root serving state. They return only roots marked active with published manifests and graphs; reconciling, quarantined, and retained-legacy roots are excluded. If that filter cannot be applied atomically for an API, the API returns `reconciliation_in_progress` rather than leaking partial state.
