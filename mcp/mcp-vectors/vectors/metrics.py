"""
Best-effort tool-engagement metrics stored in a dedicated SQLite database.

This store is intentionally separate from the GraphRAG graph store: it records
one row per instrumented MCP tool call so that engagement (call frequency and
outcome distribution) can be queried later via the management CLI.

Writes are best-effort and non-blocking: ``record_tool_call`` swallows every
exception (DB locked, disk full, schema error) and logs it to the file-only
logger. A failed metrics write must never interrupt the tool call that
triggered it.

The database path follows the same convention as ``GRAPH_DB_DIR`` (see
``vectors/rag.py``): it is configurable via the ``METRICS_DB_DIR`` environment
variable and defaults to a local data directory alongside the graph store.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Outcome enum
# ---------------------------------------------------------------------------

OUTCOME_SUCCESS = "success"
OUTCOME_ZERO_RESULT = "zero_result"
OUTCOME_ERROR = "error"

#: The only outcome values allowed in the ``tool_calls.outcome`` column.
VALID_OUTCOMES = frozenset({OUTCOME_SUCCESS, OUTCOME_ZERO_RESULT, OUTCOME_ERROR})


# ---------------------------------------------------------------------------
# Path configuration (mirrors GRAPH_DB_DIR convention in vectors/rag.py)
# ---------------------------------------------------------------------------

def _default_metrics_db_dir() -> str:
    return os.path.expanduser(os.getenv("METRICS_DB_DIR", "~/.mcp-vectors/metrics"))


def default_metrics_db_path() -> str:
    """Resolve the default ``metrics.db`` path from the environment.

    Read lazily so tests (and callers) that set ``METRICS_DB_DIR`` after import
    still get the overridden location.
    """
    return os.path.join(_default_metrics_db_dir(), "metrics.db")


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS tool_calls (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp  TEXT NOT NULL,
  tool_name  TEXT NOT NULL,
  session_id TEXT NOT NULL,
  root_path  TEXT NOT NULL,
  outcome    TEXT NOT NULL CHECK (outcome IN ('success', 'zero_result', 'error'))
);
CREATE INDEX IF NOT EXISTS idx_tool_name_timestamp ON tool_calls(tool_name, timestamp);
"""


# ---------------------------------------------------------------------------
# MetricsStore
# ---------------------------------------------------------------------------

class MetricsStore:
    """SQLite-backed writer/reader for tool-engagement metrics.

    A single ``metrics.db`` file holds all rows (unlike the per-root graph
    store). The schema is created idempotently on first write. ``record`` may
    raise; use the module-level :func:`record_tool_call` for the best-effort,
    non-blocking path used by the server.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = os.path.expanduser(db_path or default_metrics_db_path())
        self._write_lock = threading.Lock()

    @property
    def db_path(self) -> str:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(_DDL)

    def record(
        self,
        tool_name: str,
        session_id: str,
        root_path: str,
        outcome: str,
        *,
        timestamp: Optional[str] = None,
    ) -> None:
        """Insert one row into ``tool_calls``. Creates the DB/schema if missing.

        Raises ``ValueError`` for an invalid ``outcome`` and propagates any
        SQLite error. Callers that need non-blocking behaviour should use
        :func:`record_tool_call`.
        """
        if outcome not in VALID_OUTCOMES:
            raise ValueError(
                f"invalid outcome {outcome!r}; expected one of {sorted(VALID_OUTCOMES)}"
            )
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        with self._write_lock:
            conn = self._connect()
            try:
                self._ensure_schema(conn)
                conn.execute(
                    "INSERT INTO tool_calls (timestamp, tool_name, session_id, root_path, outcome) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (ts, tool_name, session_id, root_path, outcome),
                )
                conn.commit()
            finally:
                conn.close()

    def query(
        self,
        tool_name: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> dict:
        """Aggregate outcome counts, optionally filtered by tool and time.

        Returns a dict::

            {
              "since": "<iso or null>",
              "tool_name": "<name or null>",
              "tools": {
                 "search_global": {
                    "success": 42, "zero_result": 5, "error": 2,
                    "total": 49, "success_rate": 85.7,
                 },
                 ...
              },
            }
        """
        clauses: list[str] = []
        params: list[str] = []
        if tool_name:
            clauses.append("tool_name = ?")
            params.append(tool_name)
        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(_to_utc_iso(since))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

        conn = self._connect()
        try:
            self._ensure_schema(conn)
            rows = conn.execute(
                f"SELECT tool_name, outcome, COUNT(*) AS c FROM tool_calls{where} "
                "GROUP BY tool_name, outcome",
                params,
            ).fetchall()
        finally:
            conn.close()

        tools: dict[str, dict] = {}
        for row in rows:
            name = row["tool_name"]
            bucket = tools.setdefault(
                name,
                {OUTCOME_SUCCESS: 0, OUTCOME_ZERO_RESULT: 0, OUTCOME_ERROR: 0},
            )
            bucket[row["outcome"]] = row["c"]

        for name, bucket in tools.items():
            total = bucket[OUTCOME_SUCCESS] + bucket[OUTCOME_ZERO_RESULT] + bucket[OUTCOME_ERROR]
            bucket["total"] = total
            bucket["success_rate"] = (
                round(100.0 * bucket[OUTCOME_SUCCESS] / total, 1) if total else 0.0
            )

        return {
            "since": since.isoformat() if since is not None else None,
            "tool_name": tool_name,
            "tools": tools,
        }


# ---------------------------------------------------------------------------
# Module-level best-effort writer
# ---------------------------------------------------------------------------

_default_store: Optional[MetricsStore] = None
_store_lock = threading.Lock()


def get_default_store() -> MetricsStore:
    """Return a process-wide :class:`MetricsStore` bound to the configured path."""
    global _default_store
    if _default_store is None:
        with _store_lock:
            if _default_store is None:
                _default_store = MetricsStore()
    return _default_store


def record_tool_call(
    tool_name: str,
    session_id: str,
    root_path: str,
    outcome: str,
    *,
    store: Optional[MetricsStore] = None,
) -> bool:
    """Best-effort, non-blocking metrics write.

    Catches every exception, logs it to the file-only logger, and returns
    ``False`` on failure so the caller (a tool handler) proceeds regardless.
    Never raises.
    """
    try:
        (store or get_default_store()).record(tool_name, session_id, root_path, outcome)
        return True
    except Exception:  # noqa: BLE001 - metrics must never break the tool call
        logger.warning("metrics write failed for tool=%s", tool_name, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# --since parsing
# ---------------------------------------------------------------------------

def _to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_since(value: Optional[str], *, now: Optional[datetime] = None) -> datetime:
    """Parse a ``--since`` value into an aware UTC datetime.

    Accepts a relative period (``7d``, ``30d``) or an ISO date/datetime
    (``2026-07-20`` or ``2026-07-20T12:00:00``). ``None`` or empty defaults to
    30 days ago.
    """
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    if value is None or not str(value).strip():
        return reference - timedelta(days=30)

    text = str(value).strip()

    # Relative form: <int>d
    if text.lower().endswith("d") and text[:-1].isdigit():
        return reference - timedelta(days=int(text[:-1]))

    # ISO date or datetime
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"invalid --since {value!r}; use an ISO date (2026-07-20) or a period (7d, 30d)"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ---------------------------------------------------------------------------
# Management CLI
# ---------------------------------------------------------------------------

def _format_report(result: dict) -> str:
    tools = result.get("tools", {})
    lines: list[str] = []
    since = result.get("since")
    header = "Tool engagement"
    if result.get("tool_name"):
        header += f" for {result['tool_name']}"
    if since:
        header += f" since {since}"
    lines.append(header)
    lines.append("=" * len(header))
    if not tools:
        lines.append("(no recorded tool calls for this filter)")
        return "\n".join(lines)
    for name in sorted(tools):
        bucket = tools[name]
        lines.append("")
        lines.append(f"tool_name: {name}")
        lines.append(f"  success: {bucket[OUTCOME_SUCCESS]}")
        lines.append(f"  zero_result: {bucket[OUTCOME_ZERO_RESULT]}")
        lines.append(f"  error: {bucket[OUTCOME_ERROR]}")
        lines.append(f"  total: {bucket['total']}")
        lines.append(f"  success_rate: {bucket['success_rate']}%")
    return "\n".join(lines)


def run_cli(argv: list[str]) -> int:
    """Entry point for ``mcp-vectors metrics ...``.

    ``argv`` is the argument list *after* the ``metrics`` token.
    Returns a process exit code.
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(
        prog="mcp-vectors metrics",
        description="Query tool-engagement metrics recorded in metrics.db.",
    )
    sub = parser.add_subparsers(dest="command")

    query = sub.add_parser("query", help="Show call frequency and outcome distribution.")
    query.add_argument("--tool", default=None, help="Filter to one tool (e.g. search_global).")
    query.add_argument(
        "--since",
        default=None,
        help="ISO date (2026-07-20) or relative period (7d, 30d). Default: 30d.",
    )
    query.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    query.add_argument(
        "--db-path",
        default=None,
        help="Override the metrics.db path (defaults to METRICS_DB_DIR/metrics.db).",
    )

    args = parser.parse_args(argv)
    if args.command != "query":
        parser.print_help()
        return 2

    try:
        since = parse_since(args.since)
    except ValueError as exc:
        print(str(exc))
        return 2

    store = MetricsStore(args.db_path) if args.db_path else get_default_store()
    result = store.query(tool_name=args.tool, since=since)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(_format_report(result))
    return 0
