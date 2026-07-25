# Why `~/.mcp-vectors/graphs/` accumulates many separate graph stores

Investigation of the `mcp-vectors` package at `/Users/roman/projects/skills-dev/mcp/mcp-vectors`.
All citations are to source lines (primary sources).

## TL;DR

- The graph store is **one SQLite file per `root_id`**, and `root_id` is the **resolved absolute
  path string** of the indexed root — not a per-repo identity by construction.
  (`vectors/graph_store.py:189-208`, `vectors/rag.py:643-650`, `vectors/paths.py:42-43`)
- Files are named `sha256(root_id)[:16] + "_graph.sqlite"`, which is exactly the 16-hex-prefix
  filenames observed live. (`vectors/graph_store.py:206-208`)
- The MANY subdirectory-scoped stores are the **known "fragmented overlapping subdirectories"
  footgun** that ADR-0006 was written to eliminate: historically `root_id` came from "whichever
  arbitrary directory a caller supplied (or from `file.parent`)", producing dozens of overlapping
  roots for a handful of real repositories. The live registry reproduces this exactly.
  (`docs/adr/0006-git-repo-as-canonical-root-identity.md:3`)
- ADR-0006 collapse **is wired** into the normal directory-indexing path (subdir folds into the
  git working-tree root), and startup reconciliation (default ON) remaps subdir roots and drops
  their sqlite. So fresh indexing via the public tools should NOT create subdir stores anymore.
  (`vectors/rag.py:810-827`, `vectors/reconciliation.py:314-319,358-372`, `vectors/config.py:198`)
- The stores that remain / recur are **legacy residue plus non-collapsed cases**: (a) non-git or
  unknown-resolution roots are RETAINED, not dropped, unless `AUTO_PURGE_NON_GIT_ROOTS=true`
  (default false); (b) a caller that passes an explicit subdir `root_path` to `index_file` is
  used verbatim — the canonical-root substitution only fires when `root_path is None`.
  (`vectors/config.py:197`, `vectors/reconciliation.py:324-327,365`, `vectors/rag.py:619-624,646-650`)

## 1. What determines the on-disk path

Base directory:

```
GRAPH_DB_DIR = os.path.expanduser(os.getenv("GRAPH_DB_DIR", "~/.mcp-vectors/graphs"))
```
`vectors/rag.py:70` (documented in `mcp/mcp-vectors/README.md:97,143`).

Per-store filename (`GraphStore._db_path`):

```python
def _db_path(self, root_id: str) -> str:
    safe_id = hashlib.sha256(root_id.encode()).hexdigest()[:16]
    return os.path.join(self._db_dir, f"{safe_id}_graph.sqlite")
```
`vectors/graph_store.py:206-208`. Class docstring confirms intent: *"Per-root SQLite graph store.
Each root_id gets its own .sqlite file in db_dir, named after the first 16 characters of root_id."*
`vectors/graph_store.py:189-195`.

So `<something>` = `sha256(root_id)[:16]`. The 16-hex prefixes in the live directory are these hashes.

## 2. What `root_id` actually is (the crux)

At graph-build time during indexing:

```python
root_id_for_graph = (
    PathPolicy.path_key(root_path)
    if root_path
    else PathPolicy.path_key(file_path.parent)
)
```
`vectors/rag.py:646-650`.

And `path_key` is just the resolved absolute path as a POSIX string — no hashing, no git identity:

```python
@staticmethod
def path_key(path):
    return PathPolicy.resolve(path).as_posix()   # resolve() = expanduser + resolve(strict=False)
```
`vectors/paths.py:34-43`.

Therefore **each distinct absolute root-path spelling is a distinct `root_id`, hence a distinct
sqlite file.** `PathPolicy.root_id()` is intentionally unimplemented and points callers at the git
resolver instead: `raise NotImplementedError("use GitResolver.resolve_root instead")`
(`vectors/paths.py:45-47`).

The community/graph query paths key the same way: `root_id = PathPolicy.path_key(root_path)`
(`vectors/rag.py:398,439,529,544,558`).

The registry file that maps `root_id -> filename` is written on every schema-ensure:
`vectors/graph_store.py:312-330` (`registry.txt`, tab-separated).

## 3. Why there are MANY subdirectories — root cause

There is one store per indexed root path. The store count explodes when **subdirectories of the
same repository are indexed as independent roots**. ADR-0006 states the exact failure mode and its
scale:

> "The graph registry accumulated 73 roots because `root_id` was derived from whichever arbitrary
> directory a caller supplied (or from `file.parent`). Only three of those roots were real
> repositories; the rest were overlapping subdirectories with fragmented graphs."
> — `docs/adr/0006-git-repo-as-canonical-root-identity.md:3`

The live registry (below) is the same shape: 41 roots, but only ~4 real top-level projects
(`skills-dev`, `pro-trading`, `anthproxy`, `Downloads/skills/moomooapi`). Everything else is a
subtree (`docs/adr`, `engineering/to-spec`, `planning/critic`, `src/protrading/...`,
`.data/...`, `.scratch/...`, `tests`, ...), each with its own `_graph.sqlite`.

Note: **git worktrees are NOT the cause here** — no live entry is under `.claude/worktrees/`.
(ADR-0006 in fact rejects linked worktrees for indexing entirely: `git_resolver.py:140-154`,
`docs/adr/0006...md:60-62`.) The cause is plain subdirectory-as-root fragmentation.

## 4. Intended or footgun?

**Per-root store is intended** (`graph_store.py:189-195`). **Proliferation from arbitrary subdirs
is the documented footgun** ADR-0006 exists to fix, by resolving identity to the git working-tree
root. That fix is implemented on the normal indexing path:

- `index_directory` resolves the git root and persists under it, not the caller's subdir:
  ```python
  # Persist under the canonical git root, not the caller-supplied directory
  # (ADR-0006): indexing a subdirectory must not create a subdir-scoped root.
  canonical_root = dir_resolution.canonical_root or directory
  ```
  `vectors/rag.py:810-827`.
- `index_file` substitutes the canonical root **only when no root_path was supplied**:
  ```python
  resolution = GitResolver.resolve_root(file_path, self.config)
  ...
  if root_path is None and canonical_root is not None:
      root_path = canonical_root
  ```
  `vectors/rag.py:618-624`.
- Both public MCP tools route directories through `index_directory`:
  `server.py:644` (`index_files`) and `server.py:850` (`index_codebase`).

Startup reconciliation (ADR-0008) folds legacy subdir roots into their canonical root and **drops
the subdir sqlite**:

- Classification: a supported-git subdir whose canonical root differs from itself is
  `SERVING_REMAPPED` — *"subdir folds into its canonical root."* `vectors/reconciliation.py:314-319`.
- Graph phase drops the sqlite for `SERVING_PURGED` and `SERVING_REMAPPED` source roots:
  `vectors/reconciliation.py:358-372` (`self._graph_store.drop_root(source_root)`).
- Runs by default: `reconcile_on_startup: bool = True` (`vectors/config.py:198`; invoked at
  `vectors/rag.py:305-306`).

### Why stores still persist / recur ("again")

1. **Non-git / unknown roots are retained, not dropped.** For `no_repository` the serving state is
   `SERVING_PURGED` only if `auto_purge_non_git_roots` is set, else `SERVING_RETAINED_LEGACY`
   (`vectors/reconciliation.py:324-327`); the graph phase drops **only** PURGED/REMAPPED
   (`vectors/reconciliation.py:365`). Default is `auto_purge_non_git_roots = False`
   (`vectors/config.py:197`). So any indexed folder that is a **separate nested repo** (e.g. a
   `.data/` or `.scratch/` tree with its own `.git`, which legitimately resolves to its own
   toplevel = `SERVING_ACTIVE`) or that is **not a git tree** keeps its own store indefinitely.
2. **Explicit subdir `root_path` bypasses collapse.** `index_file` only overrides `root_path` when
   it is `None` (`vectors/rag.py:623`); a caller passing an explicit subdir path lands at
   `rag.py:646-647` and is used verbatim, minting a subdir store.
3. **Legacy accumulation.** Entries created before ADR-0006/0008 shipped only clear once startup
   reconciliation actually runs against the current registry and classifies them REMAPPED/PURGED
   (requires a server restart with reconciliation enabled).

"Again" = the exact 73-roots fragmentation ADR-0006 fixed has resurfaced on disk, because
consolidation depends on (a) reconciliation running and (b) `AUTO_PURGE_NON_GIT_ROOTS`, and neither
removes legitimately-distinct nested-repo/non-git subtrees.

## 5. Relevant settings / env vars

- `GRAPH_DB_DIR` (default `~/.mcp-vectors/graphs`) — relocates the store directory; does **not**
  consolidate. `vectors/rag.py:70`, `README.md:143`.
- `RECONCILE_ON_STARTUP` (default `true`) — runs startup remap+drop of REMAPPED/PURGED roots.
  `vectors/config.py:198,256`, `vectors/rag.py:305-306`.
- `AUTO_PURGE_NON_GIT_ROOTS` (default `false`) — purges (deletes store for) `no_repository` roots
  instead of retaining them. `vectors/config.py:197,255`.
- `ALLOWED_NON_GIT_ROOTS` — allowlist that gives a non-git directory a stable canonical identity so
  its subdirs fold into it instead of each becoming a root. `vectors/config.py:196,254`,
  `vectors/git_resolver.py:259-282`.
- `ENTITY_EXTRACTION` (default `true`) — when false, no graph is built at all, so no stores are
  created. `vectors/rag.py:67`, `vectors/rag.py:645,680`.

### Consolidation levers grounded in the code

- Restart the server with `RECONCILE_ON_STARTUP=true` (default) so startup reconciliation remaps
  supported-git subdir roots into their working-tree root and drops the subdir sqlite files
  (`vectors/reconciliation.py:314-319,358-372`).
- Set `AUTO_PURGE_NON_GIT_ROOTS=true` to also delete stores for confirmed non-git roots
  (`vectors/reconciliation.py:324-327,365`). Note this is destructive to those graphs.
- Index whole repositories (pass the repo root, or any path with `root_path=None`) rather than
  handing `index_file` an explicit subdirectory `root_path`, so canonical-root substitution applies
  (`vectors/rag.py:619-624`).
- Genuinely separate nested git repos (their own `.git`) will always get their own store by design
  — that is correct behavior, not a leak (`git_resolver.py` phase-2 uses each `--show-toplevel`).

No setting collapses distinct git repositories into a single store; that is intentional
(`docs/adr/0006...md:94`, submodules/nested repos remain independent).

## Live evidence

`ls -la ~/.mcp-vectors/graphs/` — 41 `<16hex>_graph.sqlite` files plus `registry.txt`,
`reconciliation.json`, `.DS_Store` (sizes 124K–34.6M). Sample:

```
091c0b79d3f761f8_graph.sqlite   400K
356ce8a532856c81_graph.sqlite   1.7M
862b18e695556536_graph.sqlite   18.1M
905d374a8dd6aab7_graph.sqlite   34.6M
... (41 total *_graph.sqlite files)
registry.txt
reconciliation.json
```

`registry.txt` (root_id -> filename) confirms root_id = literal absolute path, dominated by
subdirectories of ~4 real projects:

```
/Users/roman/Downloads/skills/moomooapi                     48db42a7642e922c_graph.sqlite
/Users/roman/projects/anthproxy                             862b18e695556536_graph.sqlite
/Users/roman/projects/anthproxy/docs/agents                 92c6c8410a14cc88_graph.sqlite
/Users/roman/projects/pro-trading                           e7a968d3598850c3_graph.sqlite
/Users/roman/projects/pro-trading/.data/plans               46466a607cdc9e8d_graph.sqlite
/Users/roman/projects/pro-trading/.scratch/amon-activation  531ce07732961334_graph.sqlite
/Users/roman/projects/pro-trading/src/protrading/cli        dfb57aa96e689fd9_graph.sqlite
/Users/roman/projects/pro-trading/tests                     aaa72beb5fcbd6e4_graph.sqlite
/Users/roman/projects/skills-dev                            905d374a8dd6aab7_graph.sqlite
/Users/roman/projects/skills-dev/docs/adr                   356ce8a532856c81_graph.sqlite
/Users/roman/projects/skills-dev/engineering/to-spec        fd28effafe805177_graph.sqlite
/Users/roman/projects/skills-dev/planning/critic            5c86b4e9ef5eeba9_graph.sqlite
... (41 entries; the majority are subdirectories, not repository roots)
```

Verify a mapping directly:
`python3 -c "import hashlib;print(hashlib.sha256(b'/Users/roman/projects/skills-dev').hexdigest()[:16])"`
→ `905d374a8dd6aab7`, matching the `skills-dev` row above.
