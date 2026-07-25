"""Tests for startup registry reconciliation (ticket 04 / ADR-0008)."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess

import pytest

from vectors.config import Config
from vectors.graph_store import GraphStore
from vectors.paths import PathPolicy
from vectors.reconciliation import (
    RegistryReconciler,
    ReconciliationEpoch,
    ReconciliationInProgress,
    read_registry,
    write_registry,
)
from vectors.testing import InMemoryVectorStore


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _git_init_commit(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "T"], check=True)
    (path / "f.txt").write_text("hi")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)
    return path.resolve()


async def _index_file(store, root_path, file_path):
    await store.upsert_chunks(
        file_path=str(file_path),
        file_name=file_path.name,
        chunks=[{"chunk_id": 0, "text": "code", "start_char": 0, "end_char": 4}],
        embeddings=[[0.1, 0.2, 0.3, 0.4]],
        root_path=str(root_path),
    )


def _key(p) -> str:
    return PathPolicy.path_key(p)


class _Scenario:
    """A realistic legacy registry: main repo + subdir + worktree + bare + non-git + unknown."""

    def __init__(self, tmp_path):
        self.db_dir = tmp_path / "graphs"
        self.db_dir.mkdir()
        self.store = InMemoryVectorStore(vector_size=4)

        # Real git main checkout with a subdirectory.
        self.main = _git_init_commit(tmp_path / "main")
        self.sub = self.main / "pkg"
        self.sub.mkdir()
        (self.sub / "mod.py").write_text("x = 1")
        (self.main / "top.py").write_text("y = 2")

        # Linked worktree of main.
        self.worktree = (tmp_path / "wt").resolve()
        subprocess.run(
            ["git", "-C", str(self.main), "worktree", "add", "-q", str(self.worktree), "-b", "wt"],
            check=True,
        )

        # Bare repo.
        self.bare = (tmp_path / "repo.git").resolve()
        self.bare.mkdir()
        subprocess.run(["git", "init", "--bare", "-q", str(self.bare)], check=True)

        # Non-git plain directory.
        self.nongit = (tmp_path / "plain").resolve()
        self.nongit.mkdir()
        (self.nongit / "notes.md").write_text("hello")

        # Unknown: the .git directory itself is inside-repo but not a work tree.
        self.unknown = (self.main / ".git").resolve()

        self.roots = {
            _key(self.main): "main_graph.sqlite",
            _key(self.sub): "sub_graph.sqlite",
            _key(self.worktree): "wt_graph.sqlite",
            _key(self.bare): "bare_graph.sqlite",
            _key(self.nongit): "plain_graph.sqlite",
            _key(self.unknown): "unknown_graph.sqlite",
        }
        write_registry(str(self.db_dir), self.roots)

    def config(self, **overrides):
        return Config(**overrides)

    def reconciler(self, config=None, **kwargs):
        return RegistryReconciler(
            str(self.db_dir),
            config or self.config(),
            self.store,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_subdir_root_remapped_to_canonical(tmp_path):
    sc = _Scenario(tmp_path)
    # Index the subdir file under BOTH the subdir root and the main root (legacy dup).
    asyncio.run(_index_file(sc.store, sc.sub, sc.sub / "mod.py"))
    epoch = asyncio.run(sc.reconciler().reconcile())

    assert epoch.serving_state(_key(sc.sub)) == "remapped"
    assert epoch.classifications[_key(sc.sub)].destination_root == _key(sc.main)
    # The vector point moved onto the canonical root.
    listing = asyncio.run(sc.store.list_indexed_files())
    root_ids = {f["root_id"] for f in listing["files"]}
    assert root_ids == {_key(sc.main)}


def test_remap_when_canonical_root_not_separately_registered(tmp_path):
    # Regression: only the subdir root is registered; the canonical repo root is
    # synthesised mid-reconciliation. Must not crash on dict-mutation-during-iteration.
    db_dir = tmp_path / "graphs"
    db_dir.mkdir()
    store = InMemoryVectorStore(vector_size=4)
    main = _git_init_commit(tmp_path / "main")
    sub = main / "pkg"
    sub.mkdir()
    (sub / "mod.py").write_text("x = 1")
    asyncio.run(_index_file(store, sub, sub / "mod.py"))
    write_registry(str(db_dir), {_key(sub): "sub_graph.sqlite"})  # canonical NOT registered

    reconciler = RegistryReconciler(str(db_dir), Config(), store)
    epoch = asyncio.run(reconciler.reconcile())

    assert epoch.serving_state(_key(sub)) == "remapped"
    assert epoch.serving_state(_key(main)) == "active"
    assert _key(main) in epoch.active_roots()
    listing = asyncio.run(store.list_indexed_files())
    assert {f["root_id"] for f in listing["files"]} == {_key(main)}
    # Canonical root now carries a registry entry with the correct derived db name.
    from vectors.reconciliation import graph_db_name
    reg = read_registry(str(db_dir))
    assert reg.get(_key(main)) == graph_db_name(_key(main))
    assert _key(sub) not in reg


def test_dedup_collapses_duplicate_file_root_pairs(tmp_path):
    sc = _Scenario(tmp_path)
    modfile = sc.sub / "mod.py"
    # Same file indexed twice: once under subdir root, once under main root.
    asyncio.run(_index_file(sc.store, sc.sub, modfile))
    asyncio.run(_index_file(sc.store, sc.main, modfile))
    asyncio.run(sc.reconciler().reconcile())

    listing = asyncio.run(sc.store.list_indexed_files())
    pairs = [(f["path_key"], f["root_id"]) for f in listing["files"]]
    # Exactly one (file_path, canonical_root) entry — no duplicate under two roots.
    assert pairs.count((_key(modfile), _key(sc.main))) == 1
    assert len({p for p in pairs if p[0] == _key(modfile)}) == 1


def test_linked_worktree_and_bare_quarantined(tmp_path):
    sc = _Scenario(tmp_path)
    # Disable auto-purge so nongit entries don't pollute the purged count; this
    # test is scoped to worktree/bare quarantine behaviour only.
    epoch = asyncio.run(sc.reconciler(sc.config(auto_purge_non_git_roots=False)).reconcile())
    assert epoch.serving_state(_key(sc.worktree)) == "quarantined"
    assert epoch.serving_state(_key(sc.bare)) == "quarantined"
    assert epoch.counts["quarantined"] == 2
    assert epoch.counts["purged"] == 0


def test_non_git_purged_by_default(tmp_path):
    """Default behaviour since AUTO_PURGE_NON_GIT_ROOTS flipped to True: purge."""
    sc = _Scenario(tmp_path)
    asyncio.run(_index_file(sc.store, sc.nongit, sc.nongit / "notes.md"))
    epoch = asyncio.run(sc.reconciler().reconcile())

    assert epoch.serving_state(_key(sc.nongit)) == "purged"
    assert epoch.counts["purged"] == 1
    # Vectors removed.
    listing = asyncio.run(sc.store.list_indexed_files())
    assert not any(f["root_id"] == _key(sc.nongit) for f in listing["files"])
    # Registry entry removed.
    assert _key(sc.nongit) not in read_registry(str(sc.db_dir))


def test_non_git_retained_when_purge_disabled(tmp_path):
    """Explicit opt-out (auto_purge_non_git_roots=False) preserves legacy behaviour."""
    sc = _Scenario(tmp_path)
    asyncio.run(_index_file(sc.store, sc.nongit, sc.nongit / "notes.md"))
    epoch = asyncio.run(sc.reconciler(sc.config(auto_purge_non_git_roots=False)).reconcile())

    assert epoch.serving_state(_key(sc.nongit)) == "retained_legacy"
    assert epoch.counts["purged"] == 0
    listing = asyncio.run(sc.store.list_indexed_files())
    assert any(f["root_id"] == _key(sc.nongit) for f in listing["files"])
    assert _key(sc.nongit) in read_registry(str(sc.db_dir))


def test_non_git_purged_when_enabled(tmp_path):
    sc = _Scenario(tmp_path)
    asyncio.run(_index_file(sc.store, sc.nongit, sc.nongit / "notes.md"))
    cfg = sc.config(auto_purge_non_git_roots=True)
    epoch = asyncio.run(sc.reconciler(cfg).reconcile())

    assert epoch.serving_state(_key(sc.nongit)) == "purged"
    assert epoch.counts["purged"] == 1
    listing = asyncio.run(sc.store.list_indexed_files())
    assert not any(f["root_id"] == _key(sc.nongit) for f in listing["files"])
    assert _key(sc.nongit) not in read_registry(str(sc.db_dir))


def test_unknown_root_preserved(tmp_path):
    sc = _Scenario(tmp_path)
    # Run with auto_purge_non_git_roots=True to prove unknown roots are never
    # purged even when the purge flag is on (only no_repository roots get purged).
    epoch = asyncio.run(sc.reconciler(config=sc.config(auto_purge_non_git_roots=True)).reconcile())
    assert epoch.serving_state(_key(sc.unknown)) == "transient"
    # Even with purge enabled, the unknown root must remain in the registry.
    assert _key(sc.unknown) in read_registry(str(sc.db_dir))


def test_active_roots_excludes_non_active(tmp_path):
    sc = _Scenario(tmp_path)
    epoch = asyncio.run(sc.reconciler().reconcile())
    active = epoch.active_roots()
    assert _key(sc.main) in active
    assert _key(sc.sub) not in active
    assert _key(sc.worktree) not in active
    assert _key(sc.bare) not in active
    assert _key(sc.nongit) not in active


# ---------------------------------------------------------------------------
# Durability / crash recovery
# ---------------------------------------------------------------------------


def test_epoch_is_persisted_and_completes(tmp_path):
    sc = _Scenario(tmp_path)
    epoch = asyncio.run(sc.reconciler().reconcile())
    persisted = json.loads((sc.db_dir / "reconciliation.json").read_text())
    assert persisted["status"] == "completed"
    assert persisted["epoch_id"] == epoch.epoch_id


def test_completed_epoch_is_not_rerun(tmp_path):
    sc = _Scenario(tmp_path)
    first = asyncio.run(sc.reconciler().reconcile())
    second = asyncio.run(sc.reconciler().reconcile())
    # Same epoch returned unchanged (idempotent; generation not bumped again).
    assert second.epoch_id == first.epoch_id
    assert second.generation == first.generation


def test_new_registry_entry_after_complete_epoch_triggers_fresh_epoch(tmp_path):
    sc = _Scenario(tmp_path)
    first = asyncio.run(sc.reconciler().reconcile())
    assert first.is_complete()

    # Simulate a new subdir path added to the registry after reconciliation completed
    # (e.g., by a legacy _update_registry call during entity extraction).
    new_subdir = sc.main / "new_pkg"
    new_subdir.mkdir()
    (new_subdir / "x.py").write_text("z = 3")
    current = read_registry(str(sc.db_dir))
    current[_key(new_subdir)] = "new_pkg_graph.sqlite"
    write_registry(str(sc.db_dir), current)

    second = asyncio.run(sc.reconciler().reconcile())
    # A fresh epoch should start because new_pkg is not in first's classifications.
    assert second.epoch_id != first.epoch_id
    assert second.is_complete()
    # The new subdir should be classified as remapped (it's inside the main git repo).
    assert _key(new_subdir) in second.classifications
    assert second.classifications[_key(new_subdir)].serving_state == "remapped"


def test_crash_mid_run_resumes_via_cas(tmp_path):
    sc = _Scenario(tmp_path)
    # Simulate a crashed run: an incomplete epoch with an expired lease.
    stale = ReconciliationEpoch(
        epoch_id="stale-epoch",
        schema_version=1,
        owner_lease="dead-owner",
        heartbeat_at=0.0,
        lease_expires_at=1.0,  # long expired
        resolver_fingerprint="",
        config_fingerprint="",
        generation=3,
        status="reconciling",
        classifications={},
        counts={},
    )
    (sc.db_dir / "reconciliation.json").write_text(json.dumps(stale.to_dict()))

    resumed = asyncio.run(sc.reconciler().reconcile())
    assert resumed.epoch_id == "stale-epoch"  # same epoch reclaimed via CAS
    assert resumed.status == "completed"
    assert resumed.generation == 4  # fenced forward from the stale generation


def test_live_lease_blocks_second_writer(tmp_path):
    sc = _Scenario(tmp_path)
    live = ReconciliationEpoch(
        epoch_id="live-epoch",
        schema_version=1,
        owner_lease="other-owner",
        heartbeat_at=10_000_000_000.0,
        lease_expires_at=10_000_000_000.0,  # far future
        resolver_fingerprint="",
        config_fingerprint="",
        generation=0,
        status="reconciling",
        classifications={},
        counts={},
    )
    (sc.db_dir / "reconciliation.json").write_text(json.dumps(live.to_dict()))

    # Freeze "now" before the live lease expiry.
    r = sc.reconciler(now=lambda: 1000.0)
    with pytest.raises(ReconciliationInProgress):
        asyncio.run(r.reconcile())


# ---------------------------------------------------------------------------
# Epoch-fence generation
# ---------------------------------------------------------------------------


def test_generation_advances_on_completion(tmp_path):
    sc = _Scenario(tmp_path)
    r = sc.reconciler()
    before = r.current_generation()
    epoch = asyncio.run(r.reconcile())
    assert epoch.generation > before
    assert r.revalidate_generation(before) is False
    assert r.revalidate_generation(epoch.generation) is True


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def test_registry_roundtrip(tmp_path):
    d = tmp_path / "g"
    d.mkdir()
    entries = {"/a/b": "x.sqlite", "/c/d": "y.sqlite"}
    write_registry(str(d), entries)
    assert read_registry(str(d)) == entries


# ---------------------------------------------------------------------------
# Rootless API guard (pipeline integration)
# ---------------------------------------------------------------------------


def _make_pipeline(store):
    from vectors.rag import RAGPipeline

    pipeline = RAGPipeline(Config(), lm_client=object(), vector_store=store)
    pipeline._initialized = True
    return pipeline


def test_list_indexed_files_filters_to_active_roots(tmp_path):
    sc = _Scenario(tmp_path)
    asyncio.run(_index_file(sc.store, sc.main, sc.main / "top.py"))
    # A file that stays under a quarantined (linked-worktree) root.
    (sc.worktree / "wtcode.py").write_text("z = 3")
    asyncio.run(_index_file(sc.store, sc.worktree, sc.worktree / "wtcode.py"))

    epoch = asyncio.run(sc.reconciler().reconcile())
    pipeline = _make_pipeline(sc.store)
    pipeline._reconciliation = epoch

    listing = asyncio.run(pipeline.list_indexed_files())
    root_ids = {f["root_id"] for f in listing["files"]}
    assert _key(sc.main) in root_ids
    assert _key(sc.worktree) not in root_ids  # quarantined root filtered out


def test_list_indexed_files_no_filter_without_epoch(tmp_path):
    sc = _Scenario(tmp_path)
    asyncio.run(_index_file(sc.store, sc.worktree, sc.main / "top.py"))
    pipeline = _make_pipeline(sc.store)
    # No reconciliation epoch → no filtering, everything enumerated.
    listing = asyncio.run(pipeline.list_indexed_files())
    assert len(listing["files"]) == 1


# ---------------------------------------------------------------------------
# Fix 3 regression: reconcile_registry surfaces failures as status="failed"
# ---------------------------------------------------------------------------


def test_reconcile_registry_returns_failed_on_exception(tmp_path, monkeypatch):
    """Regression: before Fix 3, reconcile_registry caught all exceptions and
    silently returned ``{"status": "ok"}``-style summary.  The fix surfaces the
    error as ``{"status": "failed", "error": ...}`` and logs at ERROR level so
    operators know that destructive work may be partially applied."""
    from vectors.rag import RAGPipeline

    pipeline = RAGPipeline(Config(), lm_client=object(), vector_store=InMemoryVectorStore(vector_size=4))
    pipeline._initialized = True

    # Patch RegistryReconciler.reconcile to raise mid-run.
    import vectors.rag as rag_module

    class _BrokenReconciler:
        def __init__(self, *args, **kwargs):
            pass

        async def reconcile(self):
            raise RuntimeError("simulated mid-run crash")

        def summary(self, epoch):
            return {}

    monkeypatch.setattr(rag_module, "RegistryReconciler", _BrokenReconciler)

    result = asyncio.run(pipeline.reconcile_registry())

    assert result["status"] == "failed", (
        "reconcile_registry must return {'status': 'failed', ...} on exception, "
        "not swallow the error silently (Fix 3 regression)"
    )
    assert "error" in result
    assert "simulated mid-run crash" in result["error"]


# ---------------------------------------------------------------------------
# Graph phase: graph sqlite files are cleaned up during reconciliation
# ---------------------------------------------------------------------------


def _seed_graph(graph_store: GraphStore, root_id: str) -> str:
    """Write one entity into root_id and return the db path."""
    graph_store.merge_entity("Seed", "function", "", root_id, "/seed.py")
    return graph_store._db_path(root_id)


def test_graph_phase_purged_root_sqlite_deleted(tmp_path):
    """Reconciliation deletes the graph sqlite file for a PURGED non-git root."""
    sc = _Scenario(tmp_path)
    graph_store = GraphStore(str(sc.db_dir))
    nongit_key = _key(sc.nongit)
    db_path = _seed_graph(graph_store, nongit_key)
    assert graph_store.has_root(nongit_key)

    asyncio.run(_index_file(sc.store, sc.nongit, sc.nongit / "notes.md"))
    cfg = sc.config(auto_purge_non_git_roots=True)
    asyncio.run(sc.reconciler(cfg, graph_store=graph_store).reconcile())

    assert not graph_store.has_root(nongit_key), "graph sqlite must be removed for purged root"
    assert not os.path.exists(db_path)


def test_graph_phase_remapped_root_sqlite_deleted(tmp_path):
    """Reconciliation deletes the graph sqlite file for a REMAPPED subdir root."""
    sc = _Scenario(tmp_path)
    graph_store = GraphStore(str(sc.db_dir))
    sub_key = _key(sc.sub)
    db_path = _seed_graph(graph_store, sub_key)
    assert graph_store.has_root(sub_key)

    asyncio.run(_index_file(sc.store, sc.sub, sc.sub / "mod.py"))
    asyncio.run(sc.reconciler(graph_store=graph_store).reconcile())

    assert not graph_store.has_root(sub_key), "graph sqlite must be removed for remapped subdir root"
    assert not os.path.exists(db_path)


def test_graph_phase_active_root_sqlite_kept(tmp_path):
    """Reconciliation does NOT delete the graph sqlite file for an ACTIVE root."""
    sc = _Scenario(tmp_path)
    graph_store = GraphStore(str(sc.db_dir))
    main_key = _key(sc.main)
    db_path = _seed_graph(graph_store, main_key)
    assert graph_store.has_root(main_key)

    asyncio.run(sc.reconciler(graph_store=graph_store).reconcile())

    assert graph_store.has_root(main_key), "graph sqlite must be kept for active root"
    assert os.path.exists(db_path)


def test_graph_phase_no_graph_store_skipped(tmp_path):
    """Reconciliation without a graph_store completes without error (graph phase skipped)."""
    sc = _Scenario(tmp_path)
    epoch = asyncio.run(sc.reconciler().reconcile())
    assert epoch.is_complete()


def test_graph_phase_committed_persisted_in_epoch(tmp_path):
    """graph_phase is persisted as 'committed' in the epoch JSON for processed roots."""
    sc = _Scenario(tmp_path)
    graph_store = GraphStore(str(sc.db_dir))
    asyncio.run(sc.reconciler(graph_store=graph_store).reconcile())

    persisted = json.loads((sc.db_dir / "reconciliation.json").read_text())
    for root_key, cls_dict in persisted["classifications"].items():
        assert cls_dict["graph_phase"] == "committed", (
            f"Expected graph_phase='committed' for {root_key}, got {cls_dict['graph_phase']!r}"
        )


def test_graph_phase_skip_on_resume(tmp_path):
    """Completed graph_phase entries are skipped on a resumed epoch (no redundant drop call)."""
    sc = _Scenario(tmp_path)
    graph_store = GraphStore(str(sc.db_dir))

    drop_calls: list[str] = []
    original_drop = graph_store.drop_root

    def _tracking_drop(root_id: str) -> None:
        drop_calls.append(root_id)
        original_drop(root_id)

    graph_store.drop_root = _tracking_drop  # type: ignore[method-assign]

    asyncio.run(sc.reconciler(graph_store=graph_store).reconcile())
    first_run_count = len(drop_calls)

    # Run again — completed epoch is returned immediately, so no drops should happen.
    asyncio.run(sc.reconciler(graph_store=graph_store).reconcile())
    assert len(drop_calls) == first_run_count, "drop_root must not be called on a second reconcile run"
