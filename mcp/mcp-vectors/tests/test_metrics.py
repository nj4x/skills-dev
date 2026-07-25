"""
Tests for the tool-engagement metrics infrastructure (ticket 06).

Covers:
- metrics.db is created on first write (idempotent schema)
- a tool call records a row in tool_calls
- best-effort writes never raise, even when the DB layer fails
- the outcome column is constrained to success | zero_result | error
- the management CLI (`mcp-vectors metrics query`) returns correct fields
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from vectors import metrics
from vectors.metrics import (
    MetricsStore,
    OUTCOME_ERROR,
    OUTCOME_SUCCESS,
    OUTCOME_ZERO_RESULT,
    VALID_OUTCOMES,
    parse_since,
    record_tool_call,
    run_cli,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store(tmp_path: Path) -> MetricsStore:
    return MetricsStore(str(tmp_path / "metrics.db"))


def _rows(db_path: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM tool_calls ORDER BY id").fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. Database creation
# ---------------------------------------------------------------------------

def test_metrics_db_created_on_first_write(tmp_path):
    db_path = tmp_path / "sub" / "metrics.db"
    assert not db_path.exists()

    store = MetricsStore(str(db_path))
    store.record("search_global", "sess-1", "/repo", OUTCOME_SUCCESS)

    assert db_path.exists()
    # Table + index exist and the row is present.
    rows = _rows(str(db_path))
    assert len(rows) == 1


def test_schema_creation_is_idempotent(tmp_path):
    store = _store(tmp_path)
    store.record("search_global", "s", "/repo", OUTCOME_SUCCESS)
    # A second write must not fail on the already-existing schema.
    store.record("search_entities", "s", "/repo", OUTCOME_ZERO_RESULT)
    assert len(_rows(store.db_path)) == 2


# ---------------------------------------------------------------------------
# 2. Tool call recording
# ---------------------------------------------------------------------------

def test_record_tool_call_writes_row(tmp_path):
    store = _store(tmp_path)
    ok = record_tool_call(
        "search_global", "session-abc", "/some/root", OUTCOME_SUCCESS, store=store
    )
    assert ok is True

    rows = _rows(store.db_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["tool_name"] == "search_global"
    assert row["session_id"] == "session-abc"
    assert row["root_path"] == "/some/root"
    assert row["outcome"] == OUTCOME_SUCCESS
    # timestamp is ISO-8601 parseable
    assert datetime.fromisoformat(row["timestamp"])


# ---------------------------------------------------------------------------
# 3. Non-blocking write failure
# ---------------------------------------------------------------------------

def test_record_tool_call_never_raises_on_failure(tmp_path):
    class ExplodingStore(MetricsStore):
        def record(self, *args, **kwargs):  # noqa: D401
            raise sqlite3.OperationalError("database is locked")

    store = ExplodingStore(str(tmp_path / "metrics.db"))
    # Must swallow the exception and report failure rather than propagate.
    ok = record_tool_call("search_global", "s", "/repo", OUTCOME_SUCCESS, store=store)
    assert ok is False


def test_record_tool_call_failure_does_not_interrupt_caller(tmp_path, monkeypatch):
    # Simulate a metrics write that fails and confirm the calling flow continues.
    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    store = _store(tmp_path)
    monkeypatch.setattr(store, "record", boom)

    completed = False
    ok = record_tool_call("search_entities", "s", "/repo", OUTCOME_ERROR, store=store)
    completed = True  # reached only if record_tool_call returned normally

    assert ok is False
    assert completed is True


# ---------------------------------------------------------------------------
# 4. Outcome enum validation
# ---------------------------------------------------------------------------

def test_valid_outcomes_are_exactly_three():
    assert VALID_OUTCOMES == {OUTCOME_SUCCESS, OUTCOME_ZERO_RESULT, OUTCOME_ERROR}
    assert VALID_OUTCOMES == {"success", "zero_result", "error"}


def test_record_rejects_invalid_outcome(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.record("search_global", "s", "/repo", "bogus")
    # Nothing persisted.
    store.record("search_global", "s", "/repo", OUTCOME_SUCCESS)  # create schema
    rows = _rows(store.db_path)
    assert all(r["outcome"] in VALID_OUTCOMES for r in rows)


def test_db_check_constraint_blocks_invalid_outcome(tmp_path):
    store = _store(tmp_path)
    store.record("search_global", "s", "/repo", OUTCOME_SUCCESS)  # create schema
    conn = sqlite3.connect(store.db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tool_calls (timestamp, tool_name, session_id, root_path, outcome) "
                "VALUES (?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), "t", "s", "/r", "invalid"),
            )
            conn.commit()
    finally:
        conn.close()


def test_best_effort_writer_drops_invalid_outcome(tmp_path):
    store = _store(tmp_path)
    # Best-effort writer swallows the ValueError; row must not be written.
    ok = record_tool_call("search_global", "s", "/repo", "nope", store=store)
    assert ok is False
    # Force schema creation with a valid write, then confirm only valid rows exist.
    record_tool_call("search_global", "s", "/repo", OUTCOME_SUCCESS, store=store)
    rows = _rows(store.db_path)
    assert [r["outcome"] for r in rows] == [OUTCOME_SUCCESS]


# ---------------------------------------------------------------------------
# 5. Query aggregation + --since parsing
# ---------------------------------------------------------------------------

def test_query_aggregates_outcomes(tmp_path):
    store = _store(tmp_path)
    for _ in range(3):
        store.record("search_global", "s", "/repo", OUTCOME_SUCCESS)
    store.record("search_global", "s", "/repo", OUTCOME_ZERO_RESULT)
    store.record("search_global", "s", "/repo", OUTCOME_ERROR)
    store.record("search_entities", "s", "/repo", OUTCOME_SUCCESS)

    result = store.query(tool_name="search_global")
    bucket = result["tools"]["search_global"]
    assert bucket[OUTCOME_SUCCESS] == 3
    assert bucket[OUTCOME_ZERO_RESULT] == 1
    assert bucket[OUTCOME_ERROR] == 1
    assert bucket["total"] == 5
    assert bucket["success_rate"] == 60.0
    # Filtered to one tool.
    assert "search_entities" not in result["tools"]


def test_query_since_filters_old_rows(tmp_path):
    store = _store(tmp_path)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    new_ts = datetime.now(timezone.utc).isoformat()
    store.record("search_global", "s", "/repo", OUTCOME_SUCCESS, timestamp=old_ts)
    store.record("search_global", "s", "/repo", OUTCOME_SUCCESS, timestamp=new_ts)

    since = datetime.now(timezone.utc) - timedelta(days=30)
    result = store.query(since=since)
    assert result["tools"]["search_global"]["total"] == 1


def test_parse_since_relative_and_iso():
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    assert parse_since("7d", now=now) == now - timedelta(days=7)
    assert parse_since(None, now=now) == now - timedelta(days=30)
    iso = parse_since("2026-07-20", now=now)
    assert iso.year == 2026 and iso.month == 7 and iso.day == 20
    with pytest.raises(ValueError):
        parse_since("garbage", now=now)


# ---------------------------------------------------------------------------
# 6. Management CLI
# ---------------------------------------------------------------------------

def test_run_cli_json_output(tmp_path, capsys):
    db_path = tmp_path / "metrics.db"
    store = MetricsStore(str(db_path))
    for _ in range(2):
        store.record("search_global", "s", "/repo", OUTCOME_SUCCESS)
    store.record("search_global", "s", "/repo", OUTCOME_ERROR)

    rc = run_cli(["query", "--tool", "search_global", "--since", "7d", "--json",
                  "--db-path", str(db_path)])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    bucket = payload["tools"]["search_global"]
    assert bucket["success"] == 2
    assert bucket["error"] == 1
    assert bucket["total"] == 3


def test_run_cli_table_output(tmp_path, capsys):
    db_path = tmp_path / "metrics.db"
    store = MetricsStore(str(db_path))
    store.record("search_global", "s", "/repo", OUTCOME_SUCCESS)

    rc = run_cli(["query", "--tool", "search_global", "--db-path", str(db_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "tool_name: search_global" in out
    assert "success: 1" in out
    assert "success_rate:" in out


def test_metrics_cli_end_to_end_via_subprocess(tmp_path):
    """Exercise the wired `mcp-vectors metrics` entry point through server.main."""
    db_path = tmp_path / "metrics.db"
    store = MetricsStore(str(db_path))
    store.record("search_global", "s", "/repo", OUTCOME_SUCCESS)
    store.record("search_global", "s", "/repo", OUTCOME_ZERO_RESULT)

    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["ENTITY_EXTRACTION"] = "false"  # avoid heavy startup side effects
    proc = subprocess.run(
        [sys.executable, "server.py", "metrics", "query",
         "--tool", "search_global", "--json", "--db-path", str(db_path)],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    bucket = payload["tools"]["search_global"]
    assert bucket["total"] == 2
    assert bucket["success"] == 1
    assert bucket["zero_result"] == 1
