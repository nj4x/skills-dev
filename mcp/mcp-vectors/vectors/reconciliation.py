"""Durable startup reconciliation of legacy registry roots (ADR-0008).

New indexing is forced to canonical git roots by the resolver (ADR-0006/0007).
This module migrates the roots that were registered *before* enforcement: it
classifies every existing registry entry, remaps checkout-subdir roots onto
their canonical repository root (no re-embedding), quarantines linked-worktree
and bare-repo roots, and — by default — purges confirmed non-git roots (disable
with AUTO_PURGE_NON_GIT_ROOTS=false). The work is recorded in a single durable
``ReconciliationEpoch`` so a crashed run can be reclaimed via a compare-and-swap
lease and resumed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .git_resolver import GitResolver
from .graph_store import GraphStore
from .paths import PathPolicy
from .protocols import VectorStoreProtocol

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_LEASE_SECONDS = 300
_EPOCH_FILENAME = "reconciliation.json"
_REGISTRY_FILENAME = "registry.txt"

# Serving states recorded per root (ticket 04 / ADR-0008).
SERVING_ACTIVE = "active"
SERVING_RECONCILING = "reconciling"
SERVING_QUARANTINED = "quarantined"
SERVING_RETAINED_LEGACY = "retained_legacy"
SERVING_TRANSIENT = "transient"
SERVING_REMAPPED = "remapped"
SERVING_PURGED = "purged"

# Epoch lifecycle states.
STATUS_RECONCILING = "reconciling"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


@dataclass
class RootClassification:
    """How a single legacy registry root was resolved and what became of it."""

    source_root: str
    resolution_status: str
    destination_root: Optional[str]
    serving_state: str
    vector_phase: str = "pending"  # pending | staged | committed
    graph_phase: str = "pending"
    failure_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RootClassification":
        return cls(**data)


@dataclass
class ReconciliationEpoch:
    """Durable, crash-recoverable record of a reconciliation run."""

    epoch_id: str
    schema_version: int
    owner_lease: str
    heartbeat_at: float
    lease_expires_at: float
    resolver_fingerprint: str
    config_fingerprint: str
    generation: int
    status: str
    classifications: dict[str, RootClassification] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "epoch_id": self.epoch_id,
            "schema_version": self.schema_version,
            "owner_lease": self.owner_lease,
            "heartbeat_at": self.heartbeat_at,
            "lease_expires_at": self.lease_expires_at,
            "resolver_fingerprint": self.resolver_fingerprint,
            "config_fingerprint": self.config_fingerprint,
            "generation": self.generation,
            "status": self.status,
            "classifications": {k: v.to_dict() for k, v in self.classifications.items()},
            "counts": dict(self.counts),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReconciliationEpoch":
        return cls(
            epoch_id=data["epoch_id"],
            schema_version=data["schema_version"],
            owner_lease=data["owner_lease"],
            heartbeat_at=data["heartbeat_at"],
            lease_expires_at=data["lease_expires_at"],
            resolver_fingerprint=data["resolver_fingerprint"],
            config_fingerprint=data["config_fingerprint"],
            generation=data["generation"],
            status=data["status"],
            classifications={
                k: RootClassification.from_dict(v)
                for k, v in data.get("classifications", {}).items()
            },
            counts=dict(data.get("counts", {})),
        )

    def is_complete(self) -> bool:
        return self.status == STATUS_COMPLETED

    def active_roots(self) -> set[str]:
        return {
            rid
            for rid, c in self.classifications.items()
            if c.serving_state == SERVING_ACTIVE
        }

    def serving_state(self, root_id: str) -> Optional[str]:
        canonical = PathPolicy.path_key(root_id)
        entry = self.classifications.get(canonical)
        return entry.serving_state if entry else None


def graph_db_name(root_id: str) -> str:
    """Graph db filename GraphStore derives for root_id (kept in sync with GraphStore._db_path)."""
    return f"{hashlib.sha256(root_id.encode()).hexdigest()[:16]}_graph.sqlite"


def read_registry(db_dir: str) -> dict[str, str]:
    """Read registry.txt (root_id -> db filename). Missing file yields an empty map."""
    path = os.path.join(os.path.expanduser(db_dir), _REGISTRY_FILENAME)
    entries: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if "\t" in line:
                    root_id, db_name = line.split("\t", 1)
                    entries[root_id] = db_name
    except FileNotFoundError:
        pass
    return entries


def write_registry(db_dir: str, entries: dict[str, str]) -> None:
    """Atomically rewrite registry.txt from entries (root_id -> db filename)."""
    base = os.path.expanduser(db_dir)
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, _REGISTRY_FILENAME)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for root_id, db_name in sorted(entries.items()):
            fh.write(f"{root_id}\t{db_name}\n")
    os.replace(tmp, path)


class RegistryReconciler:
    """Single-writer, epoch-fenced reconciler for the legacy root registry (ADR-0008)."""

    def __init__(
        self,
        db_dir: str,
        config,
        vector_store: VectorStoreProtocol,
        *,
        graph_store: Optional[GraphStore] = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        now: Optional[Callable[[], float]] = None,
        resolver=GitResolver,
    ) -> None:
        self._db_dir = os.path.expanduser(db_dir)
        self._config = config
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._lease_seconds = lease_seconds
        self._now = now or time.time
        self._resolver = resolver
        self._owner = uuid.uuid4().hex
        os.makedirs(self._db_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Durable epoch persistence
    # ------------------------------------------------------------------

    @property
    def _epoch_path(self) -> str:
        return os.path.join(self._db_dir, _EPOCH_FILENAME)

    def load_epoch(self) -> Optional[ReconciliationEpoch]:
        try:
            with open(self._epoch_path, encoding="utf-8") as fh:
                return ReconciliationEpoch.from_dict(json.load(fh))
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None

    def _persist(self, epoch: ReconciliationEpoch) -> None:
        tmp = f"{self._epoch_path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(epoch.to_dict(), fh, indent=2)
        os.replace(tmp, self._epoch_path)

    def current_generation(self) -> int:
        epoch = self.load_epoch()
        return epoch.generation if epoch else 0

    def revalidate_generation(self, captured_generation: int) -> bool:
        """Epoch fence: a reader captured generation is still valid iff unchanged."""
        return self.current_generation() == captured_generation

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    async def reconcile(self) -> ReconciliationEpoch:
        """Run (or resume) reconciliation, returning the completed epoch."""
        epoch = self._claim_or_start()
        if epoch.is_complete():
            return epoch

        registry = read_registry(self._db_dir)
        self._inventory_and_classify(epoch, registry)
        self._persist(epoch)

        await self._apply_vector_phase(epoch)
        self._apply_graph_phase(epoch)
        self._rewrite_registry(epoch, registry)
        self._finalize(epoch)
        return epoch

    def _resolver_fingerprint(self) -> str:
        version = self._resolver.git_version() or "no-git"
        return f"resolver:v1|{version}"

    def _claim_or_start(self) -> ReconciliationEpoch:
        """Return an owned epoch: resume an existing incomplete one (CAS) or start fresh."""
        config_fp = getattr(self._config, "config_fingerprint", "")
        resolver_fp = self._resolver_fingerprint()
        existing = self.load_epoch()
        now = self._now()

        if existing is not None:
            fingerprints_match = (
                existing.config_fingerprint == config_fp
                and existing.resolver_fingerprint == resolver_fp
            )
            if existing.is_complete() and fingerprints_match:
                current_registry = read_registry(self._db_dir)
                unprocessed = [r for r in current_registry if r not in existing.classifications]
                if not unprocessed:
                    return existing
                logger.warning(
                    "reconciliation: %d new registry entries since last epoch, starting fresh epoch: %s",
                    len(unprocessed),
                    unprocessed,
                )
            if not existing.is_complete():
                lease_live = existing.lease_expires_at > now
                if lease_live and existing.owner_lease != self._owner:
                    # Another live writer owns the epoch; do not steal the lease.
                    raise ReconciliationInProgress(existing.epoch_id)
                # Stale lease (or ours): reclaim the same epoch via compare-and-swap.
                existing.owner_lease = self._owner
                existing.heartbeat_at = now
                existing.lease_expires_at = now + self._lease_seconds
                self._persist(existing)
                # Confirm the write won the race.
                reloaded = self.load_epoch()
                if reloaded is None or reloaded.owner_lease != self._owner:
                    raise ReconciliationInProgress(existing.epoch_id)
                logger.warning(
                    "reconciliation: reclaimed stale epoch %s via CAS", existing.epoch_id
                )
                return reloaded

        epoch = ReconciliationEpoch(
            epoch_id=uuid.uuid4().hex,
            schema_version=SCHEMA_VERSION,
            owner_lease=self._owner,
            heartbeat_at=now,
            lease_expires_at=now + self._lease_seconds,
            resolver_fingerprint=resolver_fp,
            config_fingerprint=config_fp,
            generation=(existing.generation if existing else 0),
            status=STATUS_RECONCILING,
            classifications={},
            counts={},
        )
        self._persist(epoch)
        return epoch

    def _inventory_and_classify(
        self, epoch: ReconciliationEpoch, registry: dict[str, str]
    ) -> None:
        """Resolve each registry root and assign its serving state (idempotent)."""
        for source_root in registry:
            if source_root in epoch.classifications:
                continue  # resume: keep durable classification from prior run
            resolution = self._resolver.resolve_root(Path(source_root), self._config)
            epoch.classifications[source_root] = self._classify(source_root, resolution)

    def _classify(self, source_root: str, resolution) -> RootClassification:
        status = resolution.status
        canonical = (
            PathPolicy.path_key(resolution.canonical_root)
            if resolution.canonical_root is not None
            else None
        )

        if status in ("supported_working_tree", "allowlisted_non_git"):
            if canonical == source_root:
                serving = SERVING_ACTIVE
            else:
                serving = SERVING_REMAPPED  # subdir folds into its canonical root
            return RootClassification(source_root, status, canonical, serving)

        if status in ("unsupported_linked_worktree", "unsupported_bare_repository"):
            return RootClassification(source_root, status, None, SERVING_QUARANTINED)

        if status == "no_repository":
            purge = getattr(self._config, "auto_purge_non_git_roots", True)
            serving = SERVING_PURGED if purge else SERVING_RETAINED_LEGACY
            return RootClassification(source_root, status, None, serving)

        # unknown / anything else: preserve, never destroy.
        return RootClassification(source_root, status, None, SERVING_TRANSIENT)

    async def _apply_vector_phase(self, epoch: ReconciliationEpoch) -> None:
        """Remap subdir roots onto canonical roots; purge confirmed non-git roots."""
        # Snapshot: _ensure_active may insert a new canonical key mid-loop.
        for source_root, c in list(epoch.classifications.items()):
            if c.vector_phase == "committed":
                continue
            if c.serving_state == SERVING_REMAPPED and c.destination_root:
                dest_path = str(PathPolicy.resolve(c.destination_root))
                moved = await self._vector_store.remap_root(
                    source_root, c.destination_root, dest_path
                )
                logger.warning(
                    "reconciliation: remapped %d vectors %s -> %s",
                    moved, source_root, c.destination_root,
                )
                # The destination canonical root is now active.
                self._ensure_active(epoch, c.destination_root)
            elif c.serving_state == SERVING_PURGED:
                removed = await self._vector_store.delete_root(source_root)
                logger.warning(
                    "reconciliation: purged %d vectors for non-git root %s",
                    removed, source_root,
                )
            c.vector_phase = "committed"
        self._persist(epoch)

    def _apply_graph_phase(self, epoch: ReconciliationEpoch) -> None:
        """Drop graph sqlite files for PURGED and REMAPPED source roots."""
        if self._graph_store is None:
            return
        for source_root, c in epoch.classifications.items():
            if c.graph_phase == "committed":
                continue
            if c.serving_state in (SERVING_PURGED, SERVING_REMAPPED):
                try:
                    self._graph_store.drop_root(source_root)
                except Exception as exc:
                    logger.warning("reconciliation: graph drop failed for %s: %s", source_root, exc)
                    continue
            c.graph_phase = "committed"
        self._persist(epoch)

    def _ensure_active(self, epoch: ReconciliationEpoch, canonical_root: str) -> None:
        entry = epoch.classifications.get(canonical_root)
        if entry is None:
            epoch.classifications[canonical_root] = RootClassification(
                canonical_root, "supported_working_tree", canonical_root, SERVING_ACTIVE,
                vector_phase="committed", graph_phase="committed",
            )
        elif entry.serving_state != SERVING_ACTIVE:
            entry.serving_state = SERVING_ACTIVE
            entry.destination_root = canonical_root

    def _rewrite_registry(
        self, epoch: ReconciliationEpoch, registry: dict[str, str]
    ) -> None:
        """Fold remapped sources into their canonical entry; drop purged roots."""
        new_entries = dict(registry)
        for source_root, c in epoch.classifications.items():
            if c.serving_state == SERVING_REMAPPED:
                new_entries.pop(source_root, None)
                # Point the canonical root at the graph db GraphStore derives for it,
                # not the subdir's db (whose name is hashed from the subdir root_id).
                if c.destination_root and c.destination_root not in new_entries:
                    new_entries[c.destination_root] = graph_db_name(c.destination_root)
            elif c.serving_state == SERVING_PURGED:
                new_entries.pop(source_root, None)
        write_registry(self._db_dir, new_entries)

    def _finalize(self, epoch: ReconciliationEpoch) -> None:
        counts = {
            SERVING_ACTIVE: 0,
            SERVING_REMAPPED: 0,
            SERVING_QUARANTINED: 0,
            SERVING_PURGED: 0,
            SERVING_RETAINED_LEGACY: 0,
            SERVING_TRANSIENT: 0,
        }
        for c in epoch.classifications.values():
            counts[c.serving_state] = counts.get(c.serving_state, 0) + 1
        epoch.counts = {
            "active": counts[SERVING_ACTIVE],
            "remapped": counts[SERVING_REMAPPED],
            "quarantined": counts[SERVING_QUARANTINED],
            "purged": counts[SERVING_PURGED],
            "retained_legacy": counts[SERVING_RETAINED_LEGACY],
            "transient": counts[SERVING_TRANSIENT],
            "skipped": counts[SERVING_RETAINED_LEGACY] + counts[SERVING_TRANSIENT],
        }
        # Epoch fence: bump generation before publishing the completed state so any
        # reader that captured the prior generation revalidates and retries.
        epoch.generation += 1
        epoch.status = STATUS_COMPLETED
        epoch.heartbeat_at = self._now()
        self._persist(epoch)
        logger.warning(
            "reconciliation complete: remapped %d, quarantined %d, purged %d, skipped %d",
            epoch.counts["remapped"],
            epoch.counts["quarantined"],
            epoch.counts["purged"],
            epoch.counts["skipped"],
        )

    def summary(self, epoch: ReconciliationEpoch) -> dict:
        return {
            "epoch_id": epoch.epoch_id,
            "status": epoch.status,
            "generation": epoch.generation,
            "counts": dict(epoch.counts),
            "active_roots": sorted(epoch.active_roots()),
        }


class ReconciliationInProgress(RuntimeError):
    """Raised when another live writer already owns the reconciliation epoch."""

    def __init__(self, epoch_id: str) -> None:
        super().__init__(f"reconciliation epoch {epoch_id} is owned by a live writer")
        self.epoch_id = epoch_id


def reconcile_blocking(reconciler: RegistryReconciler) -> ReconciliationEpoch:
    """Synchronous convenience wrapper for startup integration."""
    return asyncio.run(reconciler.reconcile())
