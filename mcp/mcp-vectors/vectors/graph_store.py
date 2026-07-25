"""
SQLite-backed graph store for GraphRAG-inspired entity/edge tracking.

Stores entities, directed edges, community data, and a per-root dirty flag.
All operations are synchronous (sqlite3 is blocking); safe to call from async
code as individual operations are fast (WAL mode).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

MIGRATION_SENTINEL_FILE = ""

SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

def _entity_id(name: str, type_: str, root_id: str) -> str:
    return hashlib.sha256(f"{name.lower()}|{type_}|{root_id}".encode()).hexdigest()


def _edge_id(source_id: str, target_id: str, edge_type: str, root_id: str) -> str:
    return hashlib.sha256(f"{source_id}|{target_id}|{edge_type}|{root_id}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# GraphSnapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GraphSnapshot:
    root_id: str
    graph_version: int
    entities: tuple  # tuple of dicts with keys: id, name, type, description, degree, root_id, file_paths, chunk_ids
    edges: tuple     # tuple of dicts with keys: id, source_id, target_id, edge_type, weight, description, root_id


@dataclass(frozen=True)
class CommunityBuildState:
    """Durable rebuild ownership and retry state for one graph generation."""

    root_id: str
    graph_version: int
    attempts: int
    parked: bool
    warning_emitted: bool
    active_build_token: Optional[str]
    lease_expires_at: Optional[float]


@dataclass(frozen=True)
class ReportBuildStatus:
    committed_build_id: str | None
    dirty: bool
    claimed_build_id: str | None
    claim_expires_at: float | None


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS entities (
  id           TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  name_lower   TEXT NOT NULL,
  type         TEXT NOT NULL,
  description  TEXT DEFAULT '',
  frequency    INTEGER DEFAULT 1,
  degree       INTEGER DEFAULT 0,
  root_id      TEXT NOT NULL,
  file_paths   TEXT DEFAULT '[]',
  chunk_ids    TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS edges (
  id          TEXT PRIMARY KEY,
  source_id   TEXT REFERENCES entities(id),
  target_id   TEXT REFERENCES entities(id),
  edge_type   TEXT NOT NULL,
  description TEXT DEFAULT '',
  weight      REAL DEFAULT 1.0,
  root_id     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS communities (
  id              TEXT PRIMARY KEY,
  level           INTEGER NOT NULL DEFAULT 0,
  parent_id       TEXT,
  entity_ids      TEXT DEFAULT '[]',
  file_ids        TEXT DEFAULT '[]',
  report          TEXT,
  report_emb_id   TEXT,
  findings        TEXT DEFAULT NULL,
  root_id         TEXT NOT NULL DEFAULT '',
  graph_version   INTEGER NOT NULL DEFAULT 0,
  build_id        TEXT NOT NULL DEFAULT '',
  report_build_id TEXT
);

CREATE TABLE IF NOT EXISTS meta (
  root_id                     TEXT PRIMARY KEY,
  communities_dirty           INTEGER DEFAULT 0,
  graph_version               INTEGER NOT NULL DEFAULT 0,
  communities_version         INTEGER NOT NULL DEFAULT 0,
  committed_build_id          TEXT,
  reports_version             INTEGER DEFAULT 0,
  reports_dirty               INTEGER DEFAULT 1,
  reports_committed_build_id  TEXT,
  reports_claimed_build_id    TEXT,
  reports_claim_expires_at    REAL,
  reports_claim_token         TEXT
);

CREATE TABLE IF NOT EXISTS community_build_state (
  root_id            TEXT NOT NULL,
  graph_version      INTEGER NOT NULL,
  attempts           INTEGER NOT NULL DEFAULT 0,
  parked             INTEGER NOT NULL DEFAULT 0,
  warning_emitted    INTEGER NOT NULL DEFAULT 0,
  active_build_token TEXT,
  lease_expires_at   REAL,
  PRIMARY KEY (root_id, graph_version)
);

CREATE TABLE IF NOT EXISTS edge_contributions (
  root_id     TEXT NOT NULL,
  file_path   TEXT NOT NULL,
  edge_id     TEXT NOT NULL,
  source_id   TEXT NOT NULL,
  target_id   TEXT NOT NULL,
  edge_type   TEXT NOT NULL DEFAULT 'related',
  weight      REAL NOT NULL DEFAULT 1.0,
  description TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (root_id, file_path, edge_id)
);

CREATE TABLE IF NOT EXISTS entity_chunks (
  entity_id   TEXT NOT NULL,
  file_path   TEXT NOT NULL,
  chunk_id    INTEGER NOT NULL,
  root_id     TEXT NOT NULL,
  PRIMARY KEY (root_id, entity_id, file_path, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_entities_root       ON entities(root_id);
CREATE INDEX IF NOT EXISTS idx_entities_name_lower ON entities(name_lower, root_id);
CREATE INDEX IF NOT EXISTS idx_edges_source        ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_root_type     ON edges(root_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_target        ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_ec_root_file       ON edge_contributions(root_id, file_path);
CREATE INDEX IF NOT EXISTS idx_ec_edge_id         ON edge_contributions(root_id, edge_id);
CREATE INDEX IF NOT EXISTS idx_communities_root_version ON communities(root_id, graph_version, build_id);
CREATE INDEX IF NOT EXISTS idx_echunks_root_entity ON entity_chunks(root_id, entity_id);
CREATE INDEX IF NOT EXISTS idx_echunks_root_file   ON entity_chunks(root_id, file_path);
CREATE INDEX IF NOT EXISTS idx_build_state_current ON community_build_state(root_id, graph_version);

CREATE TABLE IF NOT EXISTS entity_community (
    entity_id    TEXT NOT NULL,
    community_id TEXT NOT NULL,
    root_id      TEXT NOT NULL,
    build_id     TEXT NOT NULL,
    PRIMARY KEY (entity_id, community_id, root_id, build_id)
);
CREATE INDEX IF NOT EXISTS idx_ec_entity_root
    ON entity_community (entity_id, root_id);
"""


# ---------------------------------------------------------------------------
# GraphStore
# ---------------------------------------------------------------------------

class GraphStore:
    """
    Per-root SQLite graph store.

    Each root_id gets its own .sqlite file in db_dir, named after the first
    16 characters of root_id to keep filenames short.
    """

    def __init__(self, db_dir: str) -> None:
        self._db_dir = os.path.expanduser(db_dir)
        os.makedirs(self._db_dir, exist_ok=True)
        self._write_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _db_path(self, root_id: str) -> str:
        safe_id = hashlib.sha256(root_id.encode()).hexdigest()[:16]
        return os.path.join(self._db_dir, f"{safe_id}_graph.sqlite")

    def _connect(self, root_id: str) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path(root_id), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    def _needs_migration(self, root_id: str) -> bool:
        """Return True if the root DB is at an old schema version."""
        db_path = self._db_path(root_id)
        if not os.path.exists(db_path):
            return False
        try:
            conn = sqlite3.connect(db_path, timeout=5.0)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute("PRAGMA table_info(meta)").fetchall()
                col_names = {r["name"] for r in rows}
                return "reports_claim_lease_seconds" in col_names
            except Exception:
                return False
            finally:
                conn.close()
        except Exception:
            return False

    def _drop_root_db(self, root_id: str) -> None:
        """Delete the per-root SQLite file and its WAL/SHM sidecars."""
        db_path = self._db_path(root_id)
        for p in (db_path, db_path + "-wal", db_path + "-shm"):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass

    def _ensure_schema(self, root_id: str) -> None:
        # Check for schema migration need under the write lock.
        with self._write_lock:
            if self._needs_migration(root_id):
                logger.info(
                    "Schema migration v%d: dropping and recreating %s",
                    SCHEMA_VERSION,
                    self._db_path(root_id),
                )
                self._drop_root_db(root_id)

        conn = self._connect(root_id)
        try:
            # Use explicit BEGIN IMMEDIATE so the full DDL + migration sequence is
            # atomic: two concurrent callers cannot interleave DDL and data migrations.
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.executescript(_DDL)
                # executescript issues an implicit COMMIT; begin a new transaction
                # for the migration steps that follow.
                conn.execute("BEGIN IMMEDIATE")
                self._migrate_meta(conn, root_id)
                self._migrate_communities(conn, root_id)
                self._migrate_community_build_state(conn)
                self._migrate_edge_contributions(conn, root_id)
                self._migrate_entity_community(conn)
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        finally:
            conn.close()
        self._update_registry(root_id)

    def _open_conn_for_entity(self, entity_id: str) -> Optional[sqlite3.Connection]:
        """
        Scan db_dir for the first database that contains entity_id and return
        an open connection to it (caller must close). Returns None if not found.
        """
        try:
            fnames = os.listdir(self._db_dir)
        except FileNotFoundError:
            return None

        for fname in sorted(fnames):
            if not fname.endswith("_graph.sqlite"):
                continue
            db_path = os.path.join(self._db_dir, fname)
            try:
                conn = sqlite3.connect(db_path, timeout=10.0)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT id FROM entities WHERE id = ?", (entity_id,)
                ).fetchone()
                if row:
                    return conn
                conn.close()
            except Exception:
                pass
        return None

    def _update_registry(self, root_id: str) -> None:
        """Upsert root_id → db_filename in registry.txt (tab-separated, one entry per line)."""
        registry_path = os.path.join(self._db_dir, "registry.txt")
        db_name = os.path.basename(self._db_path(root_id))
        with self._write_lock:
            entries: dict[str, str] = {}
            try:
                with open(registry_path, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.rstrip("\n")
                        if "\t" in line:
                            path, name = line.split("\t", 1)
                            entries[path] = name
            except FileNotFoundError:
                pass
            entries[root_id] = db_name
            with open(registry_path, "w", encoding="utf-8") as fh:
                for path, name in sorted(entries.items()):
                    fh.write(f"{path}\t{name}\n")

    def _column_exists(self, conn: sqlite3.Connection, table: str, column: str) -> bool:
        """Check if a column exists in a table via PRAGMA table_info."""
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(row["name"] == column for row in rows)

    def _migrate_meta(self, conn: sqlite3.Connection, root_id: str) -> None:
        """Migrate meta table: add graph_version, communities_version, committed_build_id columns."""
        if not self._column_exists(conn, "meta", "graph_version"):
            conn.execute("ALTER TABLE meta ADD COLUMN graph_version INTEGER NOT NULL DEFAULT 0")
        if not self._column_exists(conn, "meta", "communities_version"):
            conn.execute("ALTER TABLE meta ADD COLUMN communities_version INTEGER NOT NULL DEFAULT 0")
        if not self._column_exists(conn, "meta", "committed_build_id"):
            conn.execute("ALTER TABLE meta ADD COLUMN committed_build_id TEXT")
        if not self._column_exists(conn, "meta", "reports_version"):
            conn.execute("ALTER TABLE meta ADD COLUMN reports_version INTEGER DEFAULT 0")
        if not self._column_exists(conn, "meta", "reports_dirty"):
            conn.execute("ALTER TABLE meta ADD COLUMN reports_dirty INTEGER DEFAULT 1")
        if not self._column_exists(conn, "meta", "reports_committed_build_id"):
            conn.execute("ALTER TABLE meta ADD COLUMN reports_committed_build_id TEXT")
        if not self._column_exists(conn, "meta", "reports_claimed_build_id"):
            conn.execute("ALTER TABLE meta ADD COLUMN reports_claimed_build_id TEXT")
        if not self._column_exists(conn, "meta", "reports_claim_expires_at"):
            conn.execute("ALTER TABLE meta ADD COLUMN reports_claim_expires_at REAL")
        if not self._column_exists(conn, "meta", "reports_claim_token"):
            conn.execute("ALTER TABLE meta ADD COLUMN reports_claim_token TEXT")

        # Map legacy dirty state to graph_version
        conn.execute(
            "UPDATE meta SET graph_version=1, communities_version=0 WHERE communities_dirty=1 AND graph_version=0"
        )

        # Ensure a meta row exists for this root
        conn.execute(
            "INSERT OR IGNORE INTO meta(root_id, communities_dirty, graph_version, communities_version) VALUES(?,0,0,0)",
            (root_id,),
        )

    def _migrate_community_build_state(self, conn: sqlite3.Connection) -> None:
        """Add durable build-state columns when upgrading existing databases."""
        columns = {
            "attempts": "INTEGER NOT NULL DEFAULT 0",
            "parked": "INTEGER NOT NULL DEFAULT 0",
            "warning_emitted": "INTEGER NOT NULL DEFAULT 0",
            "active_build_token": "TEXT",
            "lease_expires_at": "REAL",
        }
        for column, definition in columns.items():
            if not self._column_exists(conn, "community_build_state", column):
                conn.execute(
                    f"ALTER TABLE community_build_state ADD COLUMN {column} {definition}"
                )

    def _migrate_communities(self, conn: sqlite3.Connection, root_id: str) -> None:
        """Migrate communities table: add root_id, graph_version, build_id columns."""
        if not self._column_exists(conn, "communities", "root_id"):
            conn.execute("ALTER TABLE communities ADD COLUMN root_id TEXT NOT NULL DEFAULT ''")
        if not self._column_exists(conn, "communities", "graph_version"):
            conn.execute("ALTER TABLE communities ADD COLUMN graph_version INTEGER NOT NULL DEFAULT 0")
        if not self._column_exists(conn, "communities", "build_id"):
            conn.execute("ALTER TABLE communities ADD COLUMN build_id TEXT NOT NULL DEFAULT ''")
        if not self._column_exists(conn, "communities", "findings"):
            conn.execute("ALTER TABLE communities ADD COLUMN findings TEXT DEFAULT NULL")
        if not self._column_exists(conn, "communities", "report_build_id"):
            conn.execute("ALTER TABLE communities ADD COLUMN report_build_id TEXT")

        # Backfill root_id for this root
        conn.execute("UPDATE communities SET root_id=? WHERE root_id=''", (root_id,))

        # Get current graph_version from meta and update communities
        meta_row = conn.execute(
            "SELECT graph_version FROM meta WHERE root_id=?", (root_id,)
        ).fetchone()
        current_version = meta_row["graph_version"] if meta_row else 0
        conn.execute("UPDATE communities SET graph_version=? WHERE root_id=? AND graph_version=0", (current_version, root_id))

    def _migrate_edge_contributions(self, conn: sqlite3.Connection, root_id: str) -> None:
        """Migrate edge_contributions table: backfill sentinel rows from edges if needed."""
        ec_count = conn.execute(
            "SELECT COUNT(*) FROM edge_contributions WHERE root_id=?", (root_id,)
        ).fetchone()[0]

        if ec_count == 0:
            # Check if edges exist for this root
            edge_count = conn.execute(
                "SELECT COUNT(*) FROM edges WHERE root_id=?", (root_id,)
            ).fetchone()[0]

            if edge_count > 0:
                # Insert sentinel rows for all edges
                conn.execute(
                    """
                    INSERT OR IGNORE INTO edge_contributions
                      (root_id, file_path, edge_id, source_id, target_id, edge_type, weight, description)
                    SELECT root_id, ?, id as edge_id, source_id, target_id, edge_type, weight, description
                    FROM edges WHERE root_id=?
                    """,
                    (MIGRATION_SENTINEL_FILE, root_id),
                )

    def _migrate_entity_community(self, conn: sqlite3.Connection) -> None:
        """Ensure entity_community table exists (created by DDL above; no-op on fresh schema)."""
        # The CREATE TABLE IF NOT EXISTS in _DDL handles creation; no column migrations needed.
        pass

    def _purge_file_contributions(self, conn: sqlite3.Connection, root_id: str, file_path: str) -> None:
        """Remove all prior contributions from file_path within an open transaction.

        Handles edge_contributions (non-sentinel), entity_chunks, and entity file_paths
        (deleting entities whose only source was this file). Called inside BEGIN IMMEDIATE
        so ROLLBACK on exception leaves everything unchanged.
        """
        # Remove non-sentinel edge contributions
        conn.execute(
            "DELETE FROM edge_contributions WHERE root_id=? AND file_path=? AND file_path != ?",
            (root_id, file_path, MIGRATION_SENTINEL_FILE),
        )

        # Remove entity_chunks rows scoped to this file
        conn.execute(
            "DELETE FROM entity_chunks WHERE root_id=? AND file_path=?",
            (root_id, file_path),
        )

        # Trim entity file_paths; delete entities whose only source was this file
        try:
            entity_rows = conn.execute(
                """
                SELECT e.id, e.file_paths, e.frequency
                FROM entities e, json_each(e.file_paths) jf
                WHERE e.root_id = ? AND jf.value = ?
                """,
                (root_id, file_path),
            ).fetchall()
        except sqlite3.OperationalError:
            all_rows = conn.execute(
                "SELECT id, file_paths, frequency FROM entities WHERE root_id = ?",
                (root_id,),
            ).fetchall()
            entity_rows = [
                r for r in all_rows
                if file_path in json.loads(r["file_paths"])
            ]

        delete_ids: list[str] = []
        for row in entity_rows:
            fps: list = json.loads(row["file_paths"])
            if len(fps) <= 1:
                delete_ids.append(row["id"])
            else:
                fps.remove(file_path)
                conn.execute(
                    "UPDATE entities SET file_paths=?, frequency=frequency-1 WHERE id=?",
                    (json.dumps(fps), row["id"]),
                )

        if delete_ids:
            ph = ",".join("?" * len(delete_ids))
            # Remove ALL contributions (any file) referencing entities that are being deleted.
            # Non-sentinel contributions from other files would become orphans after the entity
            # is deleted; sentinel contributions are no longer meaningful.
            conn.execute(
                f"DELETE FROM edge_contributions WHERE root_id=? AND (source_id IN ({ph}) OR target_id IN ({ph}))",
                [root_id] + list(delete_ids) + list(delete_ids),
            )
            for eid in delete_ids:
                conn.execute(
                    "DELETE FROM edges WHERE source_id = ? OR target_id = ?",
                    (eid, eid),
                )
                conn.execute("DELETE FROM entities WHERE id = ?", (eid,))

    # ------------------------------------------------------------------
    # Entity operations
    # ------------------------------------------------------------------

    def merge_entity(
        self,
        name: str,
        type_: str,
        description: str,
        root_id: str,
        file_path: str,
        chunk_ids: Optional[list] = None,
    ) -> str:
        """
        Upsert an entity. Returns the entity ID.

        If the entity already exists: increments frequency, appends file_path
        and chunk_ids if not already present.
        If new: inserts with frequency=1.
        Does NOT call mark_communities_dirty; callers handle that.
        """
        self._ensure_schema(root_id)
        eid = _entity_id(name, type_, root_id)
        conn = self._connect(root_id)
        try:
            with conn:
                row = conn.execute(
                    "SELECT id, file_paths, chunk_ids FROM entities WHERE id = ?",
                    (eid,),
                ).fetchone()

                if row:
                    file_paths: list = json.loads(row["file_paths"])
                    existing_chunk_ids: list = json.loads(row["chunk_ids"])
                    if file_path not in file_paths:
                        file_paths.append(file_path)
                    for cid in (chunk_ids or []):
                        if cid not in existing_chunk_ids:
                            existing_chunk_ids.append(cid)
                    conn.execute(
                        """
                        UPDATE entities
                        SET frequency  = frequency + 1,
                            file_paths = ?,
                            chunk_ids  = ?
                        WHERE id = ?
                        """,
                        (json.dumps(file_paths), json.dumps(existing_chunk_ids), eid),
                    )
                else:
                    file_paths = [file_path]
                    new_chunk_ids = list(chunk_ids) if chunk_ids else []
                    conn.execute(
                        """
                        INSERT INTO entities
                          (id, name, name_lower, type, description,
                           frequency, degree, root_id, file_paths, chunk_ids)
                        VALUES (?,?,?,?,?,1,0,?,?,?)
                        """,
                        (
                            eid,
                            name,
                            name.lower(),
                            type_,
                            description or "",
                            root_id,
                            json.dumps(file_paths),
                            json.dumps(new_chunk_ids),
                        ),
                    )
        finally:
            conn.close()

        return eid

    def merge_edge(
        self,
        source_name: str,
        target_name: str,
        source_type: str,
        target_type: str,
        edge_type: str,
        root_id: str,
        weight: float = 1.0,
        description: str = "",
        file_path: str = MIGRATION_SENTINEL_FILE,
    ) -> None:
        """
        Upsert a directed edge between two entities.

        If a source/target entity doesn't exist yet, a minimal stub record is
        created to maintain referential integrity.
        If the edge already exists, its weight is accumulated.
        Always writes an edge_contributions row with the given file_path (upsert).
        """
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            with conn:
                # Ensure both endpoints exist (minimal stubs if absent).
                for name, type_ in (
                    (source_name, source_type),
                    (target_name, target_type),
                ):
                    eid = _entity_id(name, type_, root_id)
                    exists = conn.execute(
                        "SELECT 1 FROM entities WHERE id = ?", (eid,)
                    ).fetchone()
                    if not exists:
                        conn.execute(
                            """
                            INSERT INTO entities
                              (id, name, name_lower, type, description,
                               frequency, degree, root_id, file_paths, chunk_ids)
                            VALUES (?,?,?,?,?,1,0,?,'[]','[]')
                            """,
                            (eid, name, name.lower(), type_, "", root_id),
                        )

                source_id = _entity_id(source_name, source_type, root_id)
                target_id = _entity_id(target_name, target_type, root_id)
                eid = _edge_id(source_id, target_id, edge_type, root_id)

                row = conn.execute(
                    "SELECT id FROM edges WHERE id = ?", (eid,)
                ).fetchone()
                if row:
                    conn.execute(
                        "UPDATE edges SET weight = weight + ? WHERE id = ?",
                        (weight, eid),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO edges
                          (id, source_id, target_id, edge_type,
                           description, weight, root_id)
                        VALUES (?,?,?,?,?,?,?)
                        """,
                        (eid, source_id, target_id, edge_type,
                         description or "", weight, root_id),
                    )

                # Write edge_contributions row (upsert)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO edge_contributions
                      (root_id, file_path, edge_id, source_id, target_id, edge_type, weight, description)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (root_id, file_path, eid, source_id, target_id, edge_type, weight, description or ""),
                )
        finally:
            conn.close()

    def merge_entity_map(self, entity_map, root_id: str, file_path: str) -> int:
        """
        Bulk-upsert entities and edges from an EntityMap-like object.

        Accepts any object with .entities and .edges attributes (duck typing).
        After bulk insert rebuilds degree counts and marks communities dirty.
        Delegates to replace_file_entity_map. Returns graph_version.
        """
        return self.replace_file_entity_map(entity_map, root_id, file_path)

    def _rebuild_materialized_edges(self, conn: sqlite3.Connection, root_id: str) -> None:
        """Rebuild materialized edges from edge_contributions by aggregating."""
        # Get all edge_ids and aggregate their contributions
        contrib_rows = conn.execute(
            """
            SELECT edge_id, source_id, target_id, edge_type,
                   SUM(weight) as total_weight,
                   GROUP_CONCAT(description, ' | ') as combined_desc
            FROM edge_contributions
            WHERE root_id = ?
            GROUP BY edge_id
            """,
            (root_id,),
        ).fetchall()

        # Clear existing edges for this root
        conn.execute("DELETE FROM edges WHERE root_id = ?", (root_id,))

        # Insert aggregated edges
        for row in contrib_rows:
            conn.execute(
                """
                INSERT INTO edges
                  (id, source_id, target_id, edge_type, description, weight, root_id)
                VALUES (?,?,?,?,?,?,?)
                """,
                (row["edge_id"], row["source_id"], row["target_id"], row["edge_type"],
                 row["combined_desc"] or "", row["total_weight"], root_id),
            )

    def replace_file_entity_map(self, entity_map, root_id: str, file_path: str) -> int:
        """
        Full transactional atomic replace of entities/edges for a file.

        In a single BEGIN IMMEDIATE transaction:
        1. Remove prior non-sentinel contributions for this file
        2. For each entity: compute entity_id, merge into entities (add file_path if not present, merge chunk_ids)
        3. Stub missing edge endpoints
        4. Insert edge_contributions for each edge
        5. Rebuild materialized edges
        6. rebuild_degree
        7. Increment graph_version, set communities_dirty
        8. Return new graph_version
        """
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            conn.isolation_level = None
            with self._write_lock:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    # Purge all prior contributions from this file (edges, entity_chunks, entity trim)
                    self._purge_file_contributions(conn, root_id, file_path)

                    # Process entities
                    entity_name_to_id = {}
                    for entity in entity_map.entities:
                        eid = _entity_id(entity.name, entity.type, root_id)
                        entity_name_to_id[entity.name.lower()] = eid

                        row = conn.execute(
                            "SELECT id, file_paths, chunk_ids FROM entities WHERE id = ?",
                            (eid,),
                        ).fetchone()

                        if row:
                            file_paths = json.loads(row["file_paths"])
                            chunk_ids_list = json.loads(row["chunk_ids"])
                            adding_file = file_path not in file_paths
                            if adding_file:
                                file_paths.append(file_path)
                            for cid in (getattr(entity, "chunk_ids", []) or []):
                                if cid not in chunk_ids_list:
                                    chunk_ids_list.append(cid)
                            if adding_file:
                                conn.execute(
                                    "UPDATE entities SET file_paths=?, chunk_ids=?, frequency=frequency+1 WHERE id=?",
                                    (json.dumps(file_paths), json.dumps(chunk_ids_list), eid),
                                )
                            else:
                                conn.execute(
                                    "UPDATE entities SET file_paths=?, chunk_ids=? WHERE id=?",
                                    (json.dumps(file_paths), json.dumps(chunk_ids_list), eid),
                                )
                        else:
                            file_paths = [file_path]
                            chunk_ids_list = list(getattr(entity, "chunk_ids", []) or [])
                            conn.execute(
                                """
                                INSERT INTO entities
                                  (id, name, name_lower, type, description, frequency, degree, root_id, file_paths, chunk_ids)
                                VALUES (?,?,?,?,?,1,0,?,?,?)
                                """,
                                (eid, entity.name, entity.name.lower(), entity.type,
                                 getattr(entity, "description", ""), root_id,
                                 json.dumps(file_paths), json.dumps(chunk_ids_list)),
                            )

                    # Populate entity_chunks for this file
                    for entity in entity_map.entities:
                        eid = _entity_id(entity.name, entity.type, root_id)
                        for cid in (getattr(entity, "chunk_ids", []) or []):
                            conn.execute(
                                "INSERT OR IGNORE INTO entity_chunks (entity_id, file_path, chunk_id, root_id) VALUES (?,?,?,?)",
                                (eid, file_path, cid, root_id),
                            )

                    # Process edges: build edge_ids and stub missing endpoints
                    new_edge_ids = set()
                    entity_type_map = {e.name.lower(): e.type for e in entity_map.entities}

                    for edge in entity_map.edges:
                        source_type = getattr(edge, "source_type", "") or entity_type_map.get(edge.source.lower(), "unknown")
                        target_type = getattr(edge, "target_type", "") or entity_type_map.get(edge.target.lower(), "unknown")

                        source_id = _entity_id(edge.source, source_type, root_id)
                        target_id = _entity_id(edge.target, target_type, root_id)
                        eid = _edge_id(source_id, target_id, edge.edge_type, root_id)
                        new_edge_ids.add(eid)

                        # Stub missing source
                        if not conn.execute("SELECT 1 FROM entities WHERE id=?", (source_id,)).fetchone():
                            conn.execute(
                                """
                                INSERT INTO entities
                                  (id, name, name_lower, type, description, frequency, degree, root_id, file_paths, chunk_ids)
                                VALUES (?,?,?,?,?,1,0,?,?,?)
                                """,
                                (source_id, edge.source, edge.source.lower(), source_type, "",
                                 root_id, json.dumps([file_path]), json.dumps([])),
                            )

                        # Stub missing target
                        if not conn.execute("SELECT 1 FROM entities WHERE id=?", (target_id,)).fetchone():
                            conn.execute(
                                """
                                INSERT INTO entities
                                  (id, name, name_lower, type, description, frequency, degree, root_id, file_paths, chunk_ids)
                                VALUES (?,?,?,?,?,1,0,?,?,?)
                                """,
                                (target_id, edge.target, edge.target.lower(), target_type, "",
                                 root_id, json.dumps([file_path]), json.dumps([])),
                            )

                        # Insert edge_contributions
                        weight = getattr(edge, "weight", 1.0)
                        description = getattr(edge, "description", "")
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO edge_contributions
                              (root_id, file_path, edge_id, source_id, target_id, edge_type, weight, description)
                            VALUES (?,?,?,?,?,?,?,?)
                            """,
                            (root_id, file_path, eid, source_id, target_id, edge.edge_type, weight, description or ""),
                        )

                    # Remove sentinel contributions whose edge_id is in new_edge_ids
                    sentinel_edges = conn.execute(
                        "SELECT edge_id FROM edge_contributions WHERE root_id=? AND file_path=?",
                        (root_id, MIGRATION_SENTINEL_FILE),
                    ).fetchall()
                    for srow in sentinel_edges:
                        if srow["edge_id"] in new_edge_ids:
                            conn.execute(
                                "DELETE FROM edge_contributions WHERE root_id=? AND edge_id=? AND file_path=?",
                                (root_id, srow["edge_id"], MIGRATION_SENTINEL_FILE),
                            )

                    # Rebuild materialized edges
                    self._rebuild_materialized_edges(conn, root_id)

                    # Rebuild degree
                    conn.execute(
                        """
                        UPDATE entities
                        SET degree = (
                            SELECT COUNT(*)
                            FROM edges
                            WHERE source_id = entities.id OR target_id = entities.id
                        )
                        WHERE root_id = ?
                        """,
                        (root_id,),
                    )

                    # Increment graph_version, reset committed_build_id so the next CAS
                    # guard sees a NULL and demands a fresh build.
                    conn.execute(
                        "UPDATE meta SET graph_version=graph_version+1, communities_version=0, committed_build_id=NULL, communities_dirty=1 WHERE root_id=?",
                        (root_id,),
                    )

                    # Get new version
                    version_row = conn.execute(
                        "SELECT graph_version FROM meta WHERE root_id=?", (root_id,)
                    ).fetchone()
                    new_version = version_row["graph_version"] if version_row else 0

                    conn.execute("COMMIT")
                    return new_version

                except Exception:
                    conn.execute("ROLLBACK")
                    raise

        finally:
            conn.close()

    def delete_file_entities(self, file_path: str, root_id: str) -> int:
        """
        Remove or trim entities whose source includes file_path.

        - If entity only references this file: delete entity + its edges.
        - If entity references multiple files: remove file from array, decrement frequency.

        In a single BEGIN IMMEDIATE transaction:
        1. Remove non-sentinel edge contributions for this file
        2. Rebuild materialized edges
        3. For each entity: remove file_path from file_paths, delete if empty
        4. rebuild_degree
        5. Increment graph_version, set communities_dirty
        6. Return new version, or 0 if nothing was deleted (no-op check)
        """
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            conn.isolation_level = None
            with self._write_lock:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    # No-op check: nothing to delete if this file left no trace.
                    contrib_count = conn.execute(
                        "SELECT COUNT(*) FROM edge_contributions WHERE root_id=? AND file_path=?",
                        (root_id, file_path),
                    ).fetchone()[0]
                    try:
                        entity_count = conn.execute(
                            """
                            SELECT COUNT(*)
                            FROM entities e, json_each(e.file_paths) jf
                            WHERE e.root_id = ? AND jf.value = ?
                            """,
                            (root_id, file_path),
                        ).fetchone()[0]
                    except sqlite3.OperationalError:
                        logger.warning(
                            "json_each TVF unavailable; falling back to Python filter "
                            "for delete_file_entities"
                        )
                        all_rows = conn.execute(
                            "SELECT file_paths FROM entities WHERE root_id = ?",
                            (root_id,),
                        ).fetchall()
                        entity_count = sum(
                            1 for r in all_rows if file_path in json.loads(r["file_paths"])
                        )
                    chunk_count = conn.execute(
                        "SELECT COUNT(*) FROM entity_chunks WHERE root_id=? AND file_path=?",
                        (root_id, file_path),
                    ).fetchone()[0]

                    if contrib_count == 0 and entity_count == 0 and chunk_count == 0:
                        conn.execute("COMMIT")
                        return 0  # No-op

                    # Purge edges/entity_chunks/entity file provenance for this file.
                    self._purge_file_contributions(conn, root_id, file_path)

                    # Rebuild materialized edges and degrees.
                    self._rebuild_materialized_edges(conn, root_id)
                    conn.execute(
                        """
                        UPDATE entities
                        SET degree = (
                            SELECT COUNT(*)
                            FROM edges
                            WHERE source_id = entities.id OR target_id = entities.id
                        )
                        WHERE root_id = ?
                        """,
                        (root_id,),
                    )

                    # Increment graph_version, reset committed_build_id so the next CAS
                    # guard sees a NULL and demands a fresh build.
                    conn.execute(
                        "UPDATE meta SET graph_version=graph_version+1, communities_version=0, communities_dirty=1, committed_build_id=NULL WHERE root_id=?",
                        (root_id,),
                    )

                    version_row = conn.execute(
                        "SELECT graph_version FROM meta WHERE root_id=?", (root_id,)
                    ).fetchone()
                    new_version = version_row["graph_version"] if version_row else 0

                    conn.execute("COMMIT")
                    return new_version

                except Exception:
                    conn.execute("ROLLBACK")
                    raise

        finally:
            conn.close()

    def find_entities(self, query: str, root_id: str, limit: int = 10) -> list[dict]:
        """LIKE search on entity name_lower. Returns list of entity dicts."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            rows = conn.execute(
                """
                SELECT * FROM entities
                WHERE name_lower LIKE ? AND root_id = ?
                LIMIT ?
                """,
                (f"%{query.lower()}%", root_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_neighbors(
        self,
        entity_id: str,
        max_depth: int = 1,
        edge_types: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        BFS up to max_depth hops from entity_id (both directions).

        Returns entity dicts for all reachable nodes, excluding the seed itself.
        """
        conn = self._open_conn_for_entity(entity_id)
        if conn is None:
            return []

        try:
            visited: set[str] = {entity_id}
            frontier: set[str] = {entity_id}
            result: list[dict] = []

            for _ in range(max_depth):
                if not frontier:
                    break
                frontier_list = list(frontier)
                ph = ",".join("?" * len(frontier_list))

                if edge_types:
                    et_ph = ",".join("?" * len(edge_types))
                    edge_filter = f"AND edge_type IN ({et_ph})"
                    # params: frontier (source IN) + frontier (target IN) + edge_types
                    query_params = frontier_list + frontier_list + list(edge_types)
                else:
                    edge_filter = ""
                    # params: frontier (source IN) + frontier (target IN)
                    query_params = frontier_list + frontier_list

                rows = conn.execute(
                    f"""
                    SELECT source_id, target_id FROM edges
                    WHERE (source_id IN ({ph}) OR target_id IN ({ph}))
                    {edge_filter}
                    """,
                    query_params,
                ).fetchall()

                next_frontier: set[str] = set()
                for row in rows:
                    for nid in (row["source_id"], row["target_id"]):
                        if nid not in visited:
                            visited.add(nid)
                            next_frontier.add(nid)

                if next_frontier:
                    nf_list = list(next_frontier)
                    nf_ph = ",".join("?" * len(nf_list))
                    entity_rows = conn.execute(
                        f"SELECT * FROM entities WHERE id IN ({nf_ph})",
                        nf_list,
                    ).fetchall()
                    result.extend(dict(r) for r in entity_rows)

                frontier = next_frontier

            return result
        finally:
            conn.close()

    def get_callers(self, function_name: str, root_id: str) -> list[dict]:
        """
        Find all entities that call function_name (via 'calls' edge type).
        """
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            target = conn.execute(
                "SELECT id FROM entities WHERE name_lower = ? AND root_id = ?",
                (function_name.lower(), root_id),
            ).fetchone()
            if not target:
                return []
            target_id = target["id"]

            rows = conn.execute(
                """
                SELECT e.* FROM entities e
                INNER JOIN edges ed ON ed.source_id = e.id
                WHERE ed.target_id = ? AND ed.edge_type = 'calls'
                """,
                (target_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Degree / community metadata
    # ------------------------------------------------------------------

    def rebuild_degree(self, root_id: str) -> None:
        """Recompute edge degree for every entity in root_id."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE entities
                    SET degree = (
                        SELECT COUNT(*)
                        FROM edges
                        WHERE source_id = entities.id OR target_id = entities.id
                    )
                    WHERE root_id = ?
                    """,
                    (root_id,),
                )
        finally:
            conn.close()

    def entities_exist(self, root_id: str) -> bool:
        """Return True if any entities are stored for root_id."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            row = conn.execute(
                "SELECT 1 FROM entities WHERE root_id=? LIMIT 1", (root_id,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def upsert_entity_community_rows(
        self,
        root_id: str,
        build_id: str,
        rows: list[tuple],
    ) -> None:
        """Batch-write (entity_id, community_id) pairs for a detection build.

        Each element of rows is a (entity_id, community_id) tuple.  Idempotent
        via the composite PRIMARY KEY.
        """
        if not rows:
            return
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            with conn:
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO entity_community
                      (entity_id, community_id, root_id, build_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    [(eid, cid, root_id, build_id) for eid, cid in rows],
                )
        finally:
            conn.close()

    def get_community_ids_for_entities(
        self, root_id: str, entity_ids: list[str]
    ) -> set[str]:
        """Return all community_ids associated with the given entity_ids for root_id.

        No build_id filter: returns union across all builds so stale rows are
        included (callers must validate against current build's communities table).
        """
        if not entity_ids:
            return set()
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            ph = ",".join("?" * len(entity_ids))
            rows = conn.execute(
                f"SELECT DISTINCT community_id FROM entity_community "
                f"WHERE root_id=? AND entity_id IN ({ph})",
                [root_id] + list(entity_ids),
            ).fetchall()
            return {row[0] for row in rows}
        finally:
            conn.close()

    def get_committed_community_ids(self, root_id: str, committed_build_id: str) -> list[str]:
        """Return all community_ids for the committed detection build."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            rows = conn.execute(
                "SELECT id FROM communities WHERE root_id=? AND build_id=?",
                (root_id, committed_build_id),
            ).fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    def delete_entity_community_stale(self, root_id: str, current_build_id: str) -> None:
        """Delete entity_community rows for root_id whose build_id != current_build_id."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            with conn:
                conn.execute(
                    "DELETE FROM entity_community WHERE root_id=? AND build_id!=?",
                    (root_id, current_build_id),
                )
        finally:
            conn.close()

    def mark_communities_dirty(self, root_id: str) -> int:
        """Flag community assignments as stale for root_id. Returns new graph_version."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            with conn:
                conn.execute(
                    "UPDATE meta SET graph_version=graph_version+1, communities_dirty=1, committed_build_id=NULL WHERE root_id=?",
                    (root_id,),
                )
                # Ensure row exists
                conn.execute(
                    "INSERT OR IGNORE INTO meta(root_id, communities_dirty, graph_version, communities_version) VALUES(?,1,1,0)",
                    (root_id,),
                )
                version_row = conn.execute(
                    "SELECT graph_version FROM meta WHERE root_id=?", (root_id,)
                ).fetchone()
            return version_row["graph_version"] if version_row else 1
        finally:
            conn.close()

    def are_communities_dirty(self, root_id: str) -> bool:
        """Return True if graph_version != communities_version or committed_build_id IS NULL."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            row = conn.execute(
                "SELECT graph_version, communities_version, committed_build_id FROM meta WHERE root_id = ?",
                (root_id,),
            ).fetchone()
            if not row:
                return True
            return row["graph_version"] != row["communities_version"] or row["committed_build_id"] is None
        finally:
            conn.close()

    def clear_communities_dirty(self, root_id: str) -> None:
        """Deprecated: no-op. Only replace_communities_if_current may mark a root fresh."""
        logger.warning("clear_communities_dirty is deprecated and has no effect; only replace_communities_if_current may mark a root fresh")

    def get_stats(self, root_id: str) -> dict:
        """Return entity_count, edge_count, community_count, communities_dirty, graph_version, communities_version."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            entity_count = conn.execute(
                "SELECT COUNT(*) FROM entities WHERE root_id = ?", (root_id,)
            ).fetchone()[0]
            edge_count = conn.execute(
                "SELECT COUNT(*) FROM edges WHERE root_id = ?", (root_id,)
            ).fetchone()[0]
            community_count = conn.execute(
                "SELECT COUNT(*) FROM communities WHERE root_id = ?", (root_id,)
            ).fetchone()[0]
            meta_row = conn.execute(
                "SELECT graph_version, communities_version, communities_dirty FROM meta WHERE root_id = ?",
                (root_id,),
            ).fetchone()
            graph_version = meta_row["graph_version"] if meta_row else 0
            communities_version = meta_row["communities_version"] if meta_row else 0
            communities_dirty = bool(meta_row and meta_row["communities_dirty"])
            return {
                "entity_count": entity_count,
                "edge_count": edge_count,
                "community_count": community_count,
                "communities_dirty": communities_dirty,
                "graph_version": graph_version,
                "communities_version": communities_version,
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Durable community build state
    # ------------------------------------------------------------------

    def get_community_build_state(
        self, root_id: str, graph_version: int
    ) -> Optional[CommunityBuildState]:
        """Return durable state for one generation, or None when never admitted."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            row = conn.execute(
                """
                SELECT root_id, graph_version, attempts, parked, warning_emitted,
                       active_build_token, lease_expires_at
                FROM community_build_state
                WHERE root_id=? AND graph_version=?
                """,
                (root_id, graph_version),
            ).fetchone()
            if not row:
                return None
            return CommunityBuildState(
                root_id=row["root_id"],
                graph_version=row["graph_version"],
                attempts=row["attempts"],
                parked=bool(row["parked"]),
                warning_emitted=bool(row["warning_emitted"]),
                active_build_token=row["active_build_token"],
                lease_expires_at=row["lease_expires_at"],
            )
        finally:
            conn.close()

    def claim_community_build(
        self,
        root_id: str,
        graph_version: int,
        build_token: str,
        lease_seconds: float,
        *,
        now: Optional[float] = None,
    ) -> bool:
        """Atomically claim a dirty, unparked current generation for rebuilding.

        A live claim blocks admission. An expired lease is safely reclaimed inside
        the same write transaction, so a process crash cannot park a generation
        forever.
        """
        if not build_token:
            raise ValueError("build_token must be non-empty")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        current_time = time.time() if now is None else now
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            conn.isolation_level = None
            with self._write_lock:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    meta = conn.execute(
                        """
                        SELECT graph_version, communities_version, committed_build_id
                        FROM meta WHERE root_id=?
                        """,
                        (root_id,),
                    ).fetchone()
                    dirty = bool(
                        meta
                        and (
                            meta["graph_version"] != meta["communities_version"]
                            or meta["committed_build_id"] is None
                        )
                    )
                    if not meta or meta["graph_version"] != graph_version or not dirty:
                        conn.execute("ROLLBACK")
                        return False

                    state = conn.execute(
                        """
                        SELECT parked, active_build_token, lease_expires_at
                        FROM community_build_state
                        WHERE root_id=? AND graph_version=?
                        """,
                        (root_id, graph_version),
                    ).fetchone()
                    if state and state["parked"]:
                        conn.execute("ROLLBACK")
                        return False
                    if (
                        state
                        and state["active_build_token"] is not None
                        and state["lease_expires_at"] is not None
                        and state["lease_expires_at"] > current_time
                    ):
                        conn.execute("ROLLBACK")
                        return False

                    conn.execute(
                        """
                        INSERT INTO community_build_state
                          (root_id, graph_version, active_build_token, lease_expires_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(root_id, graph_version) DO UPDATE SET
                          active_build_token=excluded.active_build_token,
                          lease_expires_at=excluded.lease_expires_at
                        """,
                        (root_id, graph_version, build_token, current_time + lease_seconds),
                    )
                    conn.execute("COMMIT")
                    return True
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        finally:
            conn.close()

    def complete_community_build(
        self, root_id: str, graph_version: int, build_token: str
    ) -> bool:
        """Release a build claim after success only when token and version match."""
        return self._finish_community_build(
            root_id, graph_version, build_token, failure=False
        )

    def fail_community_build(
        self, root_id: str, graph_version: int, build_token: str
    ) -> tuple[bool, bool]:
        """Record a matching failure and return ``(accepted, warning_transition)``.

        The fifth accepted failure parks the generation atomically. Exactly that
        transition sets ``warning_emitted`` and returns ``warning_transition``;
        later failures are rejected because a parked generation cannot remain
        claimed.
        """
        return self._finish_community_build(
            root_id, graph_version, build_token, failure=True
        )

    def _finish_community_build(
        self,
        root_id: str,
        graph_version: int,
        build_token: str,
        *,
        failure: bool,
    ) -> bool | tuple[bool, bool]:
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            conn.isolation_level = None
            with self._write_lock:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    meta = conn.execute(
                        "SELECT graph_version FROM meta WHERE root_id=?", (root_id,)
                    ).fetchone()
                    state = conn.execute(
                        """
                        SELECT attempts, parked, warning_emitted, active_build_token
                        FROM community_build_state
                        WHERE root_id=? AND graph_version=?
                        """,
                        (root_id, graph_version),
                    ).fetchone()
                    if (
                        not meta
                        or meta["graph_version"] != graph_version
                        or not state
                        or state["active_build_token"] != build_token
                    ):
                        conn.execute("ROLLBACK")
                        return (False, False) if failure else False

                    if not failure:
                        conn.execute(
                            """
                            UPDATE community_build_state
                            SET attempts=0, active_build_token=NULL, lease_expires_at=NULL
                            WHERE root_id=? AND graph_version=? AND active_build_token=?
                            """,
                            (root_id, graph_version, build_token),
                        )
                        conn.execute("COMMIT")
                        return True

                    attempts = state["attempts"] + 1
                    parked = attempts == 5
                    warning_transition = parked and not bool(state["warning_emitted"])
                    conn.execute(
                        """
                        UPDATE community_build_state
                        SET attempts=?, parked=?, warning_emitted=?,
                            active_build_token=NULL, lease_expires_at=NULL
                        WHERE root_id=? AND graph_version=? AND active_build_token=?
                        """,
                        (
                            attempts,
                            int(parked),
                            int(bool(state["warning_emitted"]) or warning_transition),
                            root_id,
                            graph_version,
                            build_token,
                        ),
                    )
                    conn.execute("COMMIT")
                    return (True, warning_transition)
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Graph snapshot and query methods
    # ------------------------------------------------------------------

    def read_graph_snapshot(self, root_id: str) -> GraphSnapshot:
        """Read graph in a single SQLite transaction."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            conn.isolation_level = None
            conn.execute("BEGIN")

            version_row = conn.execute(
                "SELECT graph_version FROM meta WHERE root_id=?", (root_id,)
            ).fetchone()
            graph_version = version_row["graph_version"] if version_row else 0

            entity_rows = conn.execute(
                "SELECT id, name, type, description, degree, root_id, file_paths, chunk_ids FROM entities WHERE root_id=?",
                (root_id,),
            ).fetchall()
            edge_rows = conn.execute(
                "SELECT id, source_id, target_id, edge_type, weight, description, root_id FROM edges WHERE root_id=?",
                (root_id,),
            ).fetchall()

            conn.execute("COMMIT")
            entities = tuple(dict(r) for r in entity_rows)
            edges = tuple(dict(r) for r in edge_rows)
            return GraphSnapshot(root_id=root_id, graph_version=graph_version, entities=entities, edges=edges)
        finally:
            conn.close()

    def to_networkx(self, snapshot: GraphSnapshot):
        """Export GraphSnapshot as networkx DiGraph for Leiden community detection."""
        try:
            import networkx as nx
        except ImportError:
            raise ImportError("networkx is required for to_networkx; install with: pip install networkx")

        g = nx.DiGraph()
        for e in snapshot.entities:
            g.add_node(e["id"], name=e["name"], type=e["type"], degree=e["degree"])
        for edge in snapshot.edges:
            g.add_edge(edge["source_id"], edge["target_id"], weight=edge["weight"], edge_type=edge["edge_type"])
        return g

    def get_graph_version(self, root_id: str) -> int:
        """Return meta.graph_version for root."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            row = conn.execute(
                "SELECT graph_version FROM meta WHERE root_id=?", (root_id,)
            ).fetchone()
            return row["graph_version"] if row else 0
        finally:
            conn.close()

    def get_committed_generation(self, root_id: str) -> tuple:
        """Return (communities_version, committed_build_id)."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            row = conn.execute(
                "SELECT communities_version, committed_build_id FROM meta WHERE root_id=?",
                (root_id,),
            ).fetchone()
            if row:
                return (row["communities_version"], row["committed_build_id"])
            return (0, None)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Report-generation state (atomic CAS ops, independent of detection)
    # ------------------------------------------------------------------

    def claim_report_build(self, root_id: str, build_id: str, lease_seconds: int) -> str | None:
        """CAS-claim the report-generation slot for build_id; returns claim token or None."""
        import uuid as _uuid
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            conn.isolation_level = None
            with self._write_lock:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    now = time.time()
                    row = conn.execute(
                        "SELECT reports_committed_build_id, reports_claimed_build_id, "
                        "reports_claim_expires_at, reports_claim_token FROM meta WHERE root_id=?",
                        (root_id,),
                    ).fetchone()
                    if not row:
                        conn.execute("ROLLBACK")
                        return None

                    committed = row["reports_committed_build_id"]
                    claimed_build = row["reports_claimed_build_id"]
                    expires_at = row["reports_claim_expires_at"]

                    # Already committed for this build_id — nothing to do.
                    if committed == build_id:
                        conn.execute("ROLLBACK")
                        return None

                    # Live same-generation claim exists — back off.
                    if (
                        claimed_build == build_id
                        and expires_at is not None
                        and expires_at > now
                    ):
                        conn.execute("ROLLBACK")
                        return None

                    # Prior-generation claim is superseded unconditionally (different build_id
                    # or expired same-generation). Mint fresh token and claim.
                    token = str(_uuid.uuid4())
                    conn.execute(
                        "UPDATE meta SET reports_claimed_build_id=?, reports_claim_expires_at=?, "
                        "reports_claim_token=? WHERE root_id=?",
                        (build_id, now + lease_seconds, token, root_id),
                    )
                    conn.execute("COMMIT")
                    return token
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        finally:
            conn.close()

    def commit_report_build(self, root_id: str, build_id: str, claim_token: str) -> bool:
        """Commit report build; verifies token ownership. Returns True on success."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            conn.isolation_level = None
            with self._write_lock:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    row = conn.execute(
                        "SELECT reports_claimed_build_id, reports_claim_token FROM meta WHERE root_id=?",
                        (root_id,),
                    ).fetchone()
                    if (
                        not row
                        or row["reports_claimed_build_id"] != build_id
                        or row["reports_claim_token"] != claim_token
                    ):
                        conn.execute("ROLLBACK")
                        return False
                    conn.execute(
                        "UPDATE meta SET reports_committed_build_id=?, reports_dirty=0, "
                        "reports_claimed_build_id=NULL, reports_claim_expires_at=NULL, "
                        "reports_claim_token=NULL WHERE root_id=?",
                        (build_id, root_id),
                    )
                    conn.execute("COMMIT")
                    return True
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        finally:
            conn.close()

    def clear_report_claim(self, root_id: str, claim_token: str) -> bool:
        """Release report claim; only clears when token matches. Returns True if cleared."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            conn.isolation_level = None
            with self._write_lock:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    row = conn.execute(
                        "SELECT reports_claim_token FROM meta WHERE root_id=?", (root_id,)
                    ).fetchone()
                    if not row or row["reports_claim_token"] != claim_token:
                        conn.execute("ROLLBACK")
                        return False
                    conn.execute(
                        "UPDATE meta SET reports_claimed_build_id=NULL, "
                        "reports_claim_expires_at=NULL, reports_claim_token=NULL WHERE root_id=?",
                        (root_id,),
                    )
                    conn.execute("COMMIT")
                    return True
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        finally:
            conn.close()

    def report_build_status(self, root_id: str) -> "ReportBuildStatus":
        """Return current report build status atomically."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            row = conn.execute(
                "SELECT reports_committed_build_id, reports_dirty, "
                "reports_claimed_build_id, reports_claim_expires_at FROM meta WHERE root_id=?",
                (root_id,),
            ).fetchone()
            if not row:
                return ReportBuildStatus(
                    committed_build_id=None,
                    dirty=True,
                    claimed_build_id=None,
                    claim_expires_at=None,
                )
            return ReportBuildStatus(
                committed_build_id=row["reports_committed_build_id"],
                dirty=bool(row["reports_dirty"]) if row["reports_dirty"] is not None else True,
                claimed_build_id=row["reports_claimed_build_id"],
                claim_expires_at=row["reports_claim_expires_at"],
            )
        finally:
            conn.close()

    def has_root(self, root_id: str) -> bool:
        """Return True if root's DB exists (non-creating)."""
        return os.path.exists(self._db_path(root_id))

    def drop_root(self, root_id: str) -> None:
        """Delete the graph sqlite file (and WAL/SHM sidecars) for root_id and remove its registry entry. Idempotent."""
        db_path = self._db_path(root_id)
        registry_path = os.path.join(self._db_dir, "registry.txt")
        with self._write_lock:
            for path in (db_path, db_path + "-wal", db_path + "-shm"):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
            entries: dict[str, str] = {}
            try:
                with open(registry_path, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.rstrip("\n")
                        if "\t" in line:
                            path, name = line.split("\t", 1)
                            entries[path] = name
            except FileNotFoundError:
                return
            if root_id not in entries:
                return
            del entries[root_id]
            with open(registry_path, "w", encoding="utf-8") as fh:
                for path, name in sorted(entries.items()):
                    fh.write(f"{path}\t{name}\n")

    def list_dirty_roots(self) -> list[str]:
        """Return list of roots where dirty (graph_version != communities_version or committed_build_id IS NULL)."""
        result = []
        try:
            fnames = os.listdir(self._db_dir)
        except FileNotFoundError:
            return result

        for fname in sorted(fnames):
            if not fname.endswith("_graph.sqlite"):
                continue
            db_path = os.path.join(self._db_dir, fname)
            try:
                conn = sqlite3.connect(db_path, timeout=5.0)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT root_id, graph_version, communities_version, committed_build_id FROM meta WHERE graph_version != communities_version OR committed_build_id IS NULL"
                ).fetchall()
                for row in rows:
                    result.append(row["root_id"])
                conn.close()
            except Exception:
                pass
        return result

    def invalidate_communities(self, root_id: str) -> None:
        """Clear committed community state without incrementing graph_version."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            with conn:
                conn.execute(
                    "UPDATE meta SET communities_version=0, committed_build_id=NULL, communities_dirty=1 WHERE root_id=?",
                    (root_id,),
                )
        finally:
            conn.close()

    def replace_communities_if_current(self, root_id: str, expected_version: int, build_id: str, communities: list) -> bool:
        """
        Replace communities if graph_version == expected_version and committed_build_id is NULL.
        Returns True if replaced, False if version mismatch or build already committed.

        communities is a list of dicts with keys: community_id, level, parent_id, entity_ids, summary, title,
        key_findings, entity_names, file_paths, edge_count, generated_at, generated_by
        """
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            # Use BEGIN IMMEDIATE to prevent a TOCTOU race: two concurrent callers
            # can both read graph_version==N before either writes, then both commit,
            # resulting in two different builds becoming "committed".  IMMEDIATE
            # acquires a write lock at transaction start so only one caller proceeds.
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                meta_row = conn.execute(
                    "SELECT graph_version, communities_version, committed_build_id FROM meta WHERE root_id=?",
                    (root_id,),
                ).fetchone()

                if not meta_row or meta_row["graph_version"] != expected_version or meta_row["committed_build_id"] is not None:
                    conn.execute("ROLLBACK")
                    return False

                # Delete existing community rows for this root
                conn.execute("DELETE FROM communities WHERE root_id=?", (root_id,))

                # Insert new rows
                for comm in communities:
                    conn.execute(
                        """
                        INSERT INTO communities
                          (id, level, parent_id, entity_ids, file_ids, report, report_emb_id,
                           findings, root_id, graph_version, build_id, report_build_id)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (comm.get("community_id"), comm.get("level", 0), comm.get("parent_id"),
                         json.dumps(comm.get("entity_ids", [])), json.dumps(comm.get("file_ids", [])),
                         comm.get("summary", ""), comm.get("report_emb_id"),
                         None if not comm.get("findings") else json.dumps(comm["findings"]),
                         root_id, expected_version, build_id, comm.get("report_build_id")),
                    )

                # Update meta
                new_communities_version = expected_version
                conn.execute(
                    "UPDATE meta SET communities_version=?, committed_build_id=?, communities_dirty=0 WHERE root_id=?",
                    (new_communities_version, build_id, root_id),
                )

                conn.execute("COMMIT")
                return True
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    def get_community_entities(self, community_id: str, root_id: str, graph_version: int, build_id: str) -> list[dict]:
        """Return entities in a community, filtered by root_id, graph_version, build_id."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            comm_row = conn.execute(
                "SELECT entity_ids FROM communities WHERE id=? AND root_id=? AND graph_version=? AND build_id=?",
                (community_id, root_id, graph_version, build_id),
            ).fetchone()

            if not comm_row:
                return []

            entity_ids = json.loads(comm_row["entity_ids"])
            if not entity_ids:
                return []

            ph = ",".join("?" * len(entity_ids))
            rows = conn.execute(
                f"SELECT * FROM entities WHERE id IN ({ph})",
                entity_ids,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_community_edges(self, community_id: str, root_id: str, graph_version: int, build_id: str) -> list[dict]:
        """Return edges where both endpoints are in community."""
        self._ensure_schema(root_id)
        conn = self._connect(root_id)
        try:
            comm_row = conn.execute(
                "SELECT entity_ids FROM communities WHERE id=? AND root_id=? AND graph_version=? AND build_id=?",
                (community_id, root_id, graph_version, build_id),
            ).fetchone()

            if not comm_row:
                return []

            entity_ids = json.loads(comm_row["entity_ids"])
            if not entity_ids:
                return []

            ph = ",".join("?" * len(entity_ids))
            rows = conn.execute(
                f"SELECT * FROM edges WHERE source_id IN ({ph}) AND target_id IN ({ph})",
                entity_ids + entity_ids,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
