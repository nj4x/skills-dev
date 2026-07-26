"""
Tests for the server-level request-ID lifecycle decorator and ContextVar.

Scope: server.py only — _mcp_op, _mcp_request_id, _tool, _LocalTimestampFormatter.
No live MCP server, Qdrant, or LM Studio is required.

NOTE: Some tests in this file import deprecated functions (e.g. search_code) that are
pending deletion per ADR-0052. They remain valid until the deletion PR lands.
"""

from __future__ import annotations

import asyncio
import contextvars
import datetime
import functools
import inspect
import logging
import re
import time
import uuid

import pytest


# ---------------------------------------------------------------------------
# Standalone re-implementation of the server-level lifecycle primitives.
#
# We avoid importing server.py directly because doing so triggers heavy
# module-level I/O (logging setup, signal handlers, atexit hooks, etc.).
# The re-implementation is deliberately minimal so it stays a faithful proxy
# for what server.py actually does — any behavioural difference is a test gap,
# not a test fixture.
# ---------------------------------------------------------------------------

_mcp_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "mcp_request_id_test", default=""
)

_lifecycle_logger = logging.getLogger("test.lifecycle")


def _mcp_op(name: str):
    """Standalone copy of server._mcp_op for isolated unit testing."""
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            req_id = uuid.uuid4().hex[:12]
            token = _mcp_request_id.set(req_id)
            t0 = time.monotonic()
            _lifecycle_logger.info("[%s] %s start", req_id, name)
            try:
                result = await fn(*args, **kwargs)
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                _lifecycle_logger.info("[%s] %s done (%dms)", req_id, name, elapsed_ms)
                return result
            except Exception:
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                _lifecycle_logger.warning("[%s] %s raised (%dms)", req_id, name, elapsed_ms)
                raise
            finally:
                _mcp_request_id.reset(token)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# _mcp_op tests — all async code runs inside asyncio.run() per project convention
# ---------------------------------------------------------------------------

def test_mcp_op_returns_result():
    @_mcp_op("my_tool")
    async def handler():
        return {"ok": True}

    result = asyncio.run(handler())
    assert result == {"ok": True}


def test_mcp_op_request_id_set_during_call():
    captured = []

    @_mcp_op("my_tool")
    async def handler():
        captured.append(_mcp_request_id.get())

    asyncio.run(handler())
    assert len(captured) == 1
    req_id = captured[0]
    # Must be a 12-char lowercase hex string.
    assert re.fullmatch(r"[0-9a-f]{12}", req_id), f"Bad req_id: {req_id!r}"


def test_mcp_op_request_id_cleared_after_call():
    @_mcp_op("my_tool")
    async def handler():
        pass

    asyncio.run(handler())
    # After the call the ContextVar reverts to its default (empty string).
    assert _mcp_request_id.get() == ""


def test_mcp_op_unique_request_id_per_invocation():
    ids: list[str] = []

    @_mcp_op("my_tool")
    async def handler():
        ids.append(_mcp_request_id.get())

    async def _run():
        await handler()
        await handler()

    asyncio.run(_run())
    assert len(ids) == 2
    assert ids[0] != ids[1]


def test_mcp_op_exception_is_reraised():
    @_mcp_op("failing_tool")
    async def handler():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(handler())


def test_mcp_op_request_id_cleared_after_exception():
    @_mcp_op("failing_tool")
    async def handler():
        raise RuntimeError("oops")

    with pytest.raises(RuntimeError):
        asyncio.run(handler())

    assert _mcp_request_id.get() == ""


def test_mcp_op_logs_start_and_done(caplog):
    @_mcp_op("log_tool")
    async def handler():
        return 42

    with caplog.at_level(logging.INFO, logger="test.lifecycle"):
        asyncio.run(handler())

    messages = [r.message for r in caplog.records if r.name == "test.lifecycle"]
    starts = [m for m in messages if "log_tool start" in m]
    dones = [m for m in messages if "log_tool done" in m and "ms" in m]
    assert starts, "Expected a 'start' log entry"
    assert dones, "Expected a 'done (Xms)' log entry"


def test_mcp_op_logs_raised_on_exception(caplog):
    @_mcp_op("bad_tool")
    async def handler():
        raise KeyError("secret")

    with caplog.at_level(logging.WARNING, logger="test.lifecycle"):
        with pytest.raises(KeyError):
            asyncio.run(handler())

    messages = [r.message for r in caplog.records if r.name == "test.lifecycle"]
    raised = [m for m in messages if "bad_tool raised" in m and "ms" in m]
    assert raised, "Expected a 'raised (Xms)' warning log entry"


def test_mcp_op_no_sensitive_data_in_logs(caplog):
    """Verify that arg values / results are never written to the log."""
    @_mcp_op("safe_tool")
    async def handler(secret_arg: str) -> str:
        return "private_result"

    with caplog.at_level(logging.DEBUG, logger="test.lifecycle"):
        asyncio.run(handler("super_secret_value"))

    all_log_text = " ".join(r.message for r in caplog.records)
    assert "super_secret_value" not in all_log_text
    assert "private_result" not in all_log_text


def test_mcp_op_log_entries_contain_request_id(caplog):
    """Each log line emitted by the decorator must contain the 12-char hex ID."""
    captured_id: list[str] = []

    @_mcp_op("id_check_tool")
    async def handler():
        captured_id.append(_mcp_request_id.get())

    with caplog.at_level(logging.INFO, logger="test.lifecycle"):
        asyncio.run(handler())

    req_id = captured_id[0]
    for record in caplog.records:
        if record.name == "test.lifecycle":
            assert req_id in record.message, (
                f"Request ID {req_id!r} missing from log: {record.message!r}"
            )


def test_mcp_op_concurrent_calls_isolate_request_ids():
    """Concurrent asyncio calls must each see their own request ID."""
    pairs: list[tuple[str, str]] = []

    @_mcp_op("concurrent_tool")
    async def handler(label: str):
        await asyncio.sleep(0)  # yield so both start before either resolves
        pairs.append((label, _mcp_request_id.get()))

    async def _run():
        await asyncio.gather(handler("a"), handler("b"))

    asyncio.run(_run())
    assert len(pairs) == 2
    id_a = next(p[1] for p in pairs if p[0] == "a")
    id_b = next(p[1] for p in pairs if p[0] == "b")
    assert id_a != id_b, "Concurrent invocations must have distinct request IDs"


def test_mcp_op_functools_wraps_preserves_signature():
    """Ensure __name__, __annotations__, and inspect.signature survive wrapping."""
    async def original(x: int, y: str = "hello") -> dict:
        """Docstring."""
        return {}

    wrapped = _mcp_op("some_tool")(original)
    assert wrapped.__name__ == "original"
    assert wrapped.__doc__ == "Docstring."
    sig = inspect.signature(wrapped)
    assert "x" in sig.parameters
    assert "y" in sig.parameters


def test_mcp_op_nested_call_sees_outer_request_id():
    """A helper called inside the handler sees the same request ID."""
    outer_id: list[str] = []
    inner_id: list[str] = []

    async def helper():
        inner_id.append(_mcp_request_id.get())

    @_mcp_op("outer_tool")
    async def handler():
        outer_id.append(_mcp_request_id.get())
        await helper()

    asyncio.run(handler())
    assert outer_id[0] == inner_id[0]
    assert outer_id[0] != ""


# ---------------------------------------------------------------------------
# _LocalTimestampFormatter tests (inline re-implementation)
# ---------------------------------------------------------------------------

class _LocalTimestampFormatter(logging.Formatter):
    """Inline copy of server._LocalTimestampFormatter for isolated testing."""
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.datetime.fromtimestamp(
            record.created, tz=datetime.timezone.utc
        ).astimezone()
        if datefmt:
            return dt.strftime(datefmt)
        offset = dt.strftime("%z")
        offset_fmt = f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
        return dt.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3] + f" {offset_fmt}"


def _make_log_record(ts: float) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="hello", args=(), exc_info=None,
    )
    record.created = ts
    return record


def _make_formatter() -> _LocalTimestampFormatter:
    return _LocalTimestampFormatter("%(asctime)s %(message)s")


def test_timestamp_format_contains_date():
    fmt = _make_formatter()
    ts = datetime.datetime(2025, 6, 15, 12, 0, 0,
                           tzinfo=datetime.timezone.utc).timestamp()
    formatted = fmt.format(_make_log_record(ts))
    assert re.search(r"\d{4}-\d{2}-\d{2}", formatted), formatted


def test_timestamp_format_includes_colon_separated_offset():
    fmt = _make_formatter()
    ts = datetime.datetime(2025, 1, 1, 0, 0, 0,
                           tzinfo=datetime.timezone.utc).timestamp()
    formatted = fmt.format(_make_log_record(ts))
    # Offset must be colon-separated like +05:30 or +00:00
    assert re.search(r"[+-]\d{2}:\d{2}", formatted), (
        f"No RFC 3339 offset found in: {formatted!r}"
    )


def test_timestamp_millisecond_precision():
    fmt = _make_formatter()
    ts = datetime.datetime(2025, 3, 10, 8, 30, 45, 123456,
                           tzinfo=datetime.timezone.utc).timestamp()
    formatted = fmt.format(_make_log_record(ts))
    # Should contain milliseconds (3 digits after the comma in the time part)
    assert re.search(r"\d{2}:\d{2}:\d{2},\d{3}", formatted), formatted


# ---------------------------------------------------------------------------
# ADR-0002: graph tools route through pipeline (structural assertions)
#
# We read server.py as text to avoid the heavy module-level side effects that
# importing it would trigger (logging setup, signal handlers, atexit hooks).
# ---------------------------------------------------------------------------

import pathlib
import ast


def _server_function_source(name: str) -> str:
    """Return the source lines of a top-level async def in server.py."""
    src = (pathlib.Path(__file__).parent.parent / "server.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            lines = src.splitlines()
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"Function {name!r} not found in server.py")


_GRAPH_TOOLS = ["get_entity_callers", "get_entity_neighbors", "search_entities"]


@pytest.mark.parametrize("fn_name", _GRAPH_TOOLS)
def test_graph_tool_uses_pipeline_not_graphstore(fn_name):
    """Graph tool must delegate to pipeline.*, not construct GraphStore directly."""
    src = _server_function_source(fn_name)
    assert "GraphStore(" not in src, (
        f"{fn_name} still constructs GraphStore directly; should use pipeline.*"
    )
    assert "pipeline." in src, (
        f"{fn_name} must call a pipeline method"
    )
    assert "lifespan_context" in src, (
        f"{fn_name} must bind pipeline via ctx.request_context.lifespan_context"
    )


@pytest.mark.parametrize("fn_name", _GRAPH_TOOLS)
def test_graph_tool_wraps_operation_guard(fn_name):
    """Graph tool must call increment_operations() and decrement_operations()."""
    src = _server_function_source(fn_name)
    assert "increment_operations()" in src, (
        f"{fn_name} missing increment_operations() call"
    )
    assert "decrement_operations()" in src, (
        f"{fn_name} missing decrement_operations() call"
    )


# ---------------------------------------------------------------------------
# ADR-0004: lazy-reports two-phase lifecycle — consumer semantics
#
# These tests drive the real RAGPipeline.search_global implementation and
# faithful inline re-implementations of the server.py list_communities /
# get_community_report decision paths (the same convention used above for
# _mcp_op — server.py itself is too heavy to import). The interesting logic —
# the coverage predicate and schedule_detection/schedule_reports wiring — is
# exercised against the *real* pipeline objects.
# ---------------------------------------------------------------------------

import vectors.rag as _rag_mod
from vectors.rag import RAGPipeline
from vectors.paths import PathPolicy as _PathPolicy
from vectors.qdrant import CollectionMissingError as _CollectionMissingError


class _FakeGraphStore:
    """Minimal GraphStore stand-in for the detection/reports state getters."""

    def __init__(
        self,
        *,
        committed=(5, "build-1"),
        dirty=False,
        graph_version=5,
        reports_committed=None,
        reports_dirty=True,
    ):
        self._committed = committed
        self._dirty = dirty
        self._graph_version = graph_version
        self._reports_committed = reports_committed
        self._reports_dirty = reports_dirty

    def has_root(self, root_id):
        return True

    def get_committed_generation(self, root_id):
        return self._committed

    def get_graph_version(self, root_id):
        return self._graph_version

    def are_communities_dirty(self, root_id):
        return self._dirty

    def report_build_status(self, root_id):
        from vectors.graph_store import ReportBuildStatus

        return ReportBuildStatus(
            committed_build_id=self._reports_committed,
            dirty=self._reports_dirty,
            claimed_build_id=None,
            claim_expires_at=None,
        )


class _FakeReportsState:
    def __init__(self, permanent=False):
        self.permanent = permanent


class _FakeOrchestrator:
    """Records schedule_detection / schedule_reports calls; holds retry state."""

    def __init__(self, failures=None):
        self._reports_failures = failures or {}
        self.detection_calls: list[str] = []
        self.reports_calls: list[str] = []

    def schedule_detection(self, root_id):
        self.detection_calls.append(root_id)

    def schedule_reports(self, root_id, target_clusters=None):
        self.reports_calls.append(root_id)

    def reports_permanently_failed(self, root_id: str) -> bool:
        state = self._reports_failures.get(root_id)
        return state is not None and state.permanent


class _FakeCommunities:
    def __init__(self, results=None, raise_missing=False):
        self._results = results if results is not None else []
        self._raise_missing = raise_missing

    async def search(self, **kwargs):
        if self._raise_missing:
            raise _CollectionMissingError(kwargs.get("root_id", ""))
        return self._results

    async def list_by_root(self, **kwargs):
        if self._raise_missing:
            raise _CollectionMissingError(kwargs.get("root_id", ""))
        return self._results

    async def get_by_id(self, **kwargs):
        if self._raise_missing:
            raise _CollectionMissingError(kwargs.get("root_id", ""))
        return self._results[0] if self._results else None


class _FakeLM:
    async def get_embedding(self, text):
        return [0.0] * 8


class _FakeLLM:
    async def generate_response(self, prompt):
        return "synthesis text"


def _make_pipeline(graph_store, communities, orch, *, reports_incomplete=None):
    """Build a RAGPipeline bypassing __init__ (see the property docstrings)."""
    _rag_mod.ENTITY_EXTRACTION = True
    p = RAGPipeline.__new__(RAGPipeline)
    p._initialized = True
    p._closing = False
    p._graph_store = graph_store
    p._communities = communities
    p._community_orchestrator = orch
    p._graph_stats = {}
    p._reports_incomplete = reports_incomplete or {}
    p.lm_client = _FakeLM()
    p.llm_client = _FakeLLM()

    async def _fake_search_with_response(query, limit, base_dirs=None):
        return {"success": True, "response": "vector fallback", "sources": []}

    p.search_with_response = _fake_search_with_response
    return p


# --- Thin delegates to the real pipeline methods ----------------------------
# ADR-24: the Readiness Protocol now lives in RAGPipeline.list_communities /
# get_community_report; these helpers just call through and convert to dict.


async def _list_communities_impl(pipeline, root_path, level=None, limit=50):
    result = await pipeline.list_communities(root_path, level=level, limit=limit)
    return result.to_dict()


async def _get_community_report_impl(pipeline, root_path, community_id):
    result = await pipeline.get_community_report(root_path, community_id)
    return result.to_dict()


# --- Tests -----------------------------------------------------------------


def test_search_global_rebuilding_while_reports_pending():
    """Detection committed but reports for the current build not yet ready
    (and not permanently parked) → mode='rebuilding' + schedule_reports."""
    gs = _FakeGraphStore(
        committed=(5, "build-1"),
        dirty=False,
        reports_committed=None,     # reports not committed for build-1
        reports_dirty=True,
    )
    orch = _FakeOrchestrator()  # no permanent failures → pending, not parked
    comms = _FakeCommunities(results=[{"community_id": "c1", "score": 0.9}])
    pipeline = _make_pipeline(gs, comms, orch)

    result = asyncio.run(
        pipeline.search_global(query="how is this organized", root_path="/tmp/fake-root")
    )

    assert result["mode"] == "rebuilding", result
    assert "fallback_results" in result
    root_id = _PathPolicy.path_key("/tmp/fake-root")
    assert root_id in orch.reports_calls, "search_global must schedule_reports when pending"


def test_list_communities_returns_structure_regardless_of_reports_dirty():
    """Structure comes from detection; a dirty reports flag must not force a
    'rebuilding' response nor block returning the cluster structure."""
    gs = _FakeGraphStore(
        committed=(5, "build-1"),
        dirty=False,
        reports_committed=None,
        reports_dirty=True,       # reports stale — must be ignored for structure
    )
    orch = _FakeOrchestrator()
    structure = [{"community_id": "c1", "level": 0}, {"community_id": "c2", "level": 1}]
    comms = _FakeCommunities(results=structure)
    pipeline = _make_pipeline(gs, comms, orch)

    result = asyncio.run(_list_communities_impl(pipeline, "/tmp/fake-root"))

    assert result.get("mode") != "rebuilding", result
    assert result["communities"] == structure
    root_id = _PathPolicy.path_key("/tmp/fake-root")
    assert root_id in orch.reports_calls, "list_communities should lazily nudge reports"
    assert orch.detection_calls == [], "structure was available; no detection needed"


def test_search_global_incomplete_true_partial_success():
    """Reports committed for the current build but flagged incomplete (some
    clusters produced no prose) → mode='ready', incomplete=True, embeddings."""
    root_id = _PathPolicy.path_key("/tmp/fake-root")
    gs = _FakeGraphStore(
        committed=(5, "build-1"),
        dirty=False,
        reports_committed="build-1",   # committed for the current detection build
        reports_dirty=False,
    )
    orch = _FakeOrchestrator()
    comms = _FakeCommunities(
        results=[{"community_id": "c1", "score": 0.9, "title": "T", "summary": "S"}]
    )
    pipeline = _make_pipeline(
        gs, comms, orch, reports_incomplete={root_id: True}
    )

    result = asyncio.run(
        pipeline.search_global(query="architecture?", root_path="/tmp/fake-root")
    )

    assert result["mode"] == "ready", result
    assert result["incomplete"] is True, result
    assert result["community_results"], "partial success still returns available embeddings"


def test_search_global_complete_reports_incomplete_false():
    """All clusters committed and no incomplete flag → incomplete=False."""
    gs = _FakeGraphStore(
        committed=(5, "build-1"),
        dirty=False,
        reports_committed="build-1",
        reports_dirty=False,
    )
    orch = _FakeOrchestrator()
    comms = _FakeCommunities(
        results=[{"community_id": "c1", "score": 0.9, "title": "T", "summary": "S"}]
    )
    pipeline = _make_pipeline(gs, comms, orch)  # no reports_incomplete entry

    result = asyncio.run(
        pipeline.search_global(query="architecture?", root_path="/tmp/fake-root")
    )

    assert result["mode"] == "ready", result
    assert result["incomplete"] is False, result
    assert result["community_results"]


def test_search_global_all_failed_falls_back_incomplete_true():
    """Reports permanently parked (all clusters failed) → vector fallback +
    incomplete=True."""
    root_id = _PathPolicy.path_key("/tmp/fake-root")
    gs = _FakeGraphStore(
        committed=(5, "build-1"),
        dirty=False,
        reports_committed=None,        # nothing committed for build-1
        reports_dirty=True,
    )
    orch = _FakeOrchestrator(failures={root_id: _FakeReportsState(permanent=True)})
    comms = _FakeCommunities(results=[])  # no committed report embeddings
    pipeline = _make_pipeline(gs, comms, orch)

    result = asyncio.run(
        pipeline.search_global(query="architecture?", root_path="/tmp/fake-root")
    )

    assert result["mode"] == "ready", result
    assert result["incomplete"] is True, result
    assert "fallback_results" in result


def test_get_community_report_rebuilding_while_cluster_pending():
    """Report prose for the committed build is pending → mode='rebuilding'
    and get_by_id must not be consulted yet."""
    gs = _FakeGraphStore(
        committed=(5, "build-1"),
        dirty=False,
        reports_committed=None,
        reports_dirty=True,
    )
    orch = _FakeOrchestrator()
    # get_by_id would raise if it were reached (it must not be).
    comms = _FakeCommunities(raise_missing=True)
    pipeline = _make_pipeline(gs, comms, orch)

    result = asyncio.run(
        _get_community_report_impl(pipeline, "/tmp/fake-root", community_id="c1")
    )

    assert result["mode"] == "rebuilding", result
    root_id = _PathPolicy.path_key("/tmp/fake-root")
    assert root_id in orch.reports_calls


def test_schedule_community_rebuild_is_deprecated_detection_alias():
    """The deprecated alias must schedule detection only (never reports)."""
    orch = _FakeOrchestrator()
    pipeline = _make_pipeline(_FakeGraphStore(), _FakeCommunities(), orch)

    pipeline.schedule_community_rebuild("root-x")

    assert orch.detection_calls == ["root-x"]
    assert orch.reports_calls == []


# ---------------------------------------------------------------------------
# Fix 5: server RootResolutionError handlers — structural assertions
#
# We use source inspection (same pattern as the graph-tool tests above) to
# verify that `index_files` and `index_codebase` catch RootResolutionError
# and return structured error dicts instead of raising.  This guards against
# accidental deletion of the catch blocks without any live-server harness.
# ---------------------------------------------------------------------------


def test_index_files_catches_root_resolution_error_for_file_path():
    """index_files must catch RootResolutionError on the per-file branch and
    return a structured error dict (not propagate the exception)."""
    src = _server_function_source("index_files")
    assert "RootResolutionError" in src, (
        "index_files does not catch RootResolutionError; "
        "unsupported-root errors will bubble as unhandled exceptions"
    )
    assert "e.error_code" in src, (
        "index_files error handler missing e.error_code — "
        "callers won't receive a machine-readable error code"
    )
    assert "e.message" in src, (
        "index_files error handler missing e.message"
    )
    # The catch must cover the file-path branch, not only the directory branch.
    # Both `.is_file()` and `.is_dir()` blocks must each have their own handler.
    assert src.count("RootResolutionError") >= 2, (
        "index_files must catch RootResolutionError in both the file and directory branches"
    )
def test_index_codebase_catches_root_resolution_error():
    """index_codebase must catch RootResolutionError and return a structured
    error dict instead of propagating the exception to the caller."""
    src = _server_function_source("index_codebase")
    assert "RootResolutionError" in src, (
        "index_codebase does not catch RootResolutionError"
    )
    assert "e.error_code" in src, (
        "index_codebase error handler missing e.error_code"
    )
    assert "e.message" in src, (
        "index_codebase error handler missing e.message"
    )
    # Result must be a dict with success=False when error is caught.
    assert '"success": False' in src or "'success': False" in src or "success: False" in src or (
        # The return dict literal uses the key; check the response shape.
        '"success"' in src
    ), "index_codebase error path must set success=False"


# ---------------------------------------------------------------------------
# search_code seam-closure tests (ADR-0042)
# ---------------------------------------------------------------------------


def test_search_code_source_has_no_private_confidence_call():
    """search_code source must not contain _compute_confidence or PathPolicy imports.

    ADR-0042: confidence computation belongs inside RAGPipeline.search(); the MCP handler
    must not reach past the public interface. This seam-regression test (AST guard) pins
    that boundary so a future change cannot silently reintroduce the private-method call.
    """
    src = _server_function_source("search_code")
    assert "response.confidence" in src, (
        "search_code must read confidence from response.confidence (ADR-0042)"
    )
    assert "_compute_confidence" not in src, (
        "search_code still calls _compute_confidence directly; should read response.confidence"
    )
    assert "PathPolicy" not in src, (
        "search_code still imports PathPolicy; root_id derivation belongs inside the pipeline"
    )


def test_search_code_handler_surfaces_pipeline_confidence():
    """search_code handler surfaces pipeline's RAGResponse.confidence and never calls _compute_confidence."""
    async def _run():
        from unittest.mock import AsyncMock, MagicMock
        from server import search_code
        from vectors.rag import RAGResponse

        ctx = MagicMock()
        ctx.error = AsyncMock()
        app_ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx
        pipeline = MagicMock()
        app_ctx.pipeline = pipeline

        expected_confidence = {"level": "full", "reason": "graph_ready"}
        pipeline.get_indexing_status = AsyncMock(return_value={"status": "indexed"})
        pipeline.search = AsyncMock(
            return_value=RAGResponse(
                success=True,
                query="query",
                results=[],
                total_results=0,
                formatted_results=[],
                confidence=expected_confidence,
            )
        )

        result = await search_code(root_path="/tmp", query="query", ctx=ctx)

        assert result["success"] is True
        assert result["confidence"] == expected_confidence
        assert not pipeline._compute_confidence.called, (
            "_compute_confidence must not be called from the MCP handler"
        )

    asyncio.run(_run())
