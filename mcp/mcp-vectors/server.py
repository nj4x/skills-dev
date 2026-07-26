"""
MCP Vectors Server - Local semantic search using Qdrant and LM Studio.

Environment Variables:
    LM_STUDIO_URL: LM Studio API URL (default: http://localhost:1234/v1)
    EMBEDDING_MODEL: Embedding model name or "auto" for auto-detection
    LLM_MODEL: LLM model name or "auto" for auto-detection
    QDRANT_URL: Qdrant server URL (optional - uses in-memory if not set)
    QDRANT_COLLECTION: Qdrant collection name (default: mcp_vectors)
    WATCH_DIR: Directories to watch/index (comma-separated for multiple)
    WATCH_ENABLED: Enable active file watching (default: true if WATCH_DIR set)
    WATCH_DEBOUNCE: Debounce seconds for file changes (default: 2.0)
    WATCH_BATCH_INTERVAL: Max seconds to batch changes (default: 10.0)
    AUTO_SYNC: Auto-reconcile + watch the launch-dir project on startup if already
        indexed (default: true; set false to opt out)
    CHUNK_SIZE: Characters per chunk (default: 512)
    CHUNK_OVERLAP: Overlap between chunks (default: 128)
    MAX_FILE_SIZE_MB: Maximum file size to index (default: 50.0)
    GRACEFUL_SHUTDOWN_TIMEOUT: Shutdown timeout in seconds (default: 60)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import signal
import time
import logging
import threading
import atexit
import contextvars
import functools
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Optional
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pydantic import Field
from mcp.server.fastmcp import FastMCP, Context

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parents[1] / "mcp_common"))

from mcp_common.streamable_http import (  # noqa: E402
    build_streamable_http_parser,
    parse_streamable_http_args,
    run_with_streamable_http,
)
from vectors.config import Config, get_config, resolve_path, resolve_project_root, sanitize_for_log  # noqa: E402
from vectors.entity_extractor import EntityExtractor, annotate_chunks  # noqa: E402
from vectors.errors import RootResolutionError  # noqa: E402
from vectors.extraction_cache import ExtractionCache  # noqa: E402
from vectors.qdrant import CollectionMissingError  # noqa: E402
from vectors.rag import (  # noqa: E402
    RAGPipeline,
    ENTITY_EXTRACTION,
    MAX_GLEANINGS,
    MAX_CHUNKS_PER_EXTRACT,
)
from vectors.paths import PathPolicy  # noqa: E402
from vectors.safety import ExclusionPolicy  # noqa: E402
from vectors.watcher import FileWatcher  # noqa: E402
from vectors.metrics import (  # noqa: E402
    record_tool_call,
    OUTCOME_SUCCESS,
    OUTCOME_ZERO_RESULT,
    OUTCOME_ERROR,
)

class _LocalTimestampFormatter(logging.Formatter):
    """Formats asctime as local wall-clock time with numeric UTC offset (RFC 3339-ish)."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        import datetime
        dt = datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc).astimezone()
        if datefmt:
            return dt.strftime(datefmt)
        offset = dt.strftime("%z")
        offset_fmt = f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
        return dt.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3] + f" {offset_fmt}"


def _setup_logging() -> None:
    """Configure logging with a world-private rotating file handler."""
    from logging.handlers import RotatingFileHandler

    log_dir = Path.home() / ".mcp-vectors" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mcp-vectors.log"

    rotating = RotatingFileHandler(
        str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3,
    )
    # Restrict log file to owner-only access.
    try:
        log_file.touch(exist_ok=True)
        log_file.chmod(0o600)
    except OSError:
        pass

    fmt = "%(asctime)s [%(levelname)s] [PID:%(process)d] %(name)s: %(message)s"
    rotating.setFormatter(_LocalTimestampFormatter(fmt))

    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[logging.StreamHandler(sys.stderr), rotating],
    )
    # Silence routine httpx/httpcore transport chatter while preserving warnings/errors.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Override the formatter on all handlers installed by basicConfig to use local time.
    root = logging.getLogger()
    local_fmt = _LocalTimestampFormatter(fmt)
    for handler in root.handlers:
        if not isinstance(handler, type(rotating)):
            handler.setFormatter(local_fmt)


_setup_logging()
logger = logging.getLogger("mcp-vectors")


# ====================
# Graceful Shutdown
# ====================

_shutdown_event = threading.Event()
_active_operations = 0
_operations_lock = threading.Lock()
_shutdown_timeout = int(os.getenv("GRACEFUL_SHUTDOWN_TIMEOUT", "60"))
_shutdown_loop: asyncio.AbstractEventLoop | None = None
_shutdown_owner_task: asyncio.Task | None = None


def is_shutting_down() -> bool:
    """Check if server is in shutdown mode."""
    return _shutdown_event.is_set()


def increment_operations() -> bool:
    """Increment active operation counter. Returns False if shutdown is in progress."""
    global _active_operations
    with _operations_lock:
        if _shutdown_event.is_set():
            return False
        _active_operations += 1
        logger.debug(f"Operation started. Active: {_active_operations}")
        return True


def decrement_operations() -> None:
    """Decrement active operation counter."""
    global _active_operations
    with _operations_lock:
        _active_operations = max(0, _active_operations - 1)
        logger.debug(f"Operation completed. Active: {_active_operations}")


def get_active_operations() -> int:
    """Get current number of active operations."""
    with _operations_lock:
        return _active_operations


def graceful_shutdown_handler(signum, frame):
    """Notify the async lifecycle that shutdown was requested."""
    signal_name = signal.Signals(signum).name if signum else "unknown"
    logger.info(f"Received {signal_name} signal. Initiating graceful shutdown...")
    _shutdown_event.set()
    loop = _shutdown_loop
    owner = _shutdown_owner_task
    if loop is not None and owner is not None and not loop.is_closed():
        loop.call_soon_threadsafe(owner.cancel)


def setup_signal_handlers() -> None:
    """Set up signal handlers for graceful shutdown."""
    if os.getenv("MCP_ENABLE_SIGNAL_HANDLERS", "true").lower() == "false":
        logger.info("Skipping custom signal handlers (MCP_ENABLE_SIGNAL_HANDLERS=false)")
        return
    signal.signal(signal.SIGTERM, graceful_shutdown_handler)
    signal.signal(signal.SIGINT, graceful_shutdown_handler)
    logger.info("Signal handlers configured for graceful shutdown")


def cleanup_on_exit() -> None:
    """Cleanup function called on exit."""
    active = get_active_operations()
    if active > 0:
        logger.warning(f"Exiting with {active} operation(s) still active")
    else:
        logger.info("Server shutdown complete")


atexit.register(cleanup_on_exit)


# ====================
# Application Context
# ====================

@dataclass
class AppContext:
    """Application context with RAG pipeline and file watchers."""

    config: Config
    pipeline: RAGPipeline
    watchers: list[FileWatcher] = field(default_factory=list)


async def _run_startup_sync(pipeline: RAGPipeline, root: str) -> None:
    """Reconcile an already-indexed project against disk in the background.

    Runs only on the watcher lock-owner. Guarded by the graceful-shutdown counter so a
    SIGTERM mid-sync waits for it to finish (or times out) rather than tearing down the
    pipeline underneath it.
    """
    if not increment_operations():
        return
    try:
        logger.info(f"Startup sync: reconciling {sanitize_for_log(root)} against disk")
        result = await pipeline.sync_directory(root)
        if result.get("success"):
            logger.info(
                f"Startup sync complete for {sanitize_for_log(root)}: "
                f"+{result['new']} new, ~{result['updated']} updated, "
                f"-{result['removed']} removed, {result['unchanged']} unchanged"
            )
        else:
            logger.warning(f"Startup sync failed for {sanitize_for_log(root)}: {result.get('error')}")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Startup sync error for {sanitize_for_log(root)}: {e}")
    finally:
        decrement_operations()


def _should_index_directory_root(path: str | Path, config: Config) -> tuple[bool, list[str]]:
    decision = ExclusionPolicy(
        excluded_directories=config.excluded_directories,
        excluded_filenames=config.excluded_filenames,
        secret_filenames=config.secret_filenames,
        secret_path_patterns=config.secret_path_patterns,
    ).should_traverse_path(path)
    return decision.action == "index", decision.reason_codes


async def _await_cleanup(awaitable, deadline: float, name: str) -> None:
    """Run one cleanup step without letting cancellation skip later steps."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        logger.warning("Shutdown deadline reached before %s", name)
        return
    task = asyncio.ensure_future(awaitable)
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=remaining)
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None and hasattr(current, "uncancel"):
            current.uncancel()
        remaining = deadline - time.monotonic()
        if remaining > 0:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=remaining)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
                logger.warning("Shutdown cleanup timed out: %s", name)
            except Exception as exc:
                logger.warning("Shutdown cleanup failed: %s: %s", name, exc)
        else:
            task.cancel()
            logger.warning("Shutdown cleanup timed out: %s", name)
    except asyncio.TimeoutError:
        task.cancel()
        logger.warning("Shutdown cleanup timed out: %s", name)
    except Exception as exc:
        logger.warning("Shutdown cleanup failed: %s: %s", name, exc)


async def _shutdown_resources(
    pipeline: RAGPipeline,
    watchers: list[FileWatcher],
    background_tasks: list[asyncio.Task],
    timeout: float,
) -> None:
    """Stop background work and attempt every closer by one absolute deadline."""
    deadline = time.monotonic() + timeout
    _shutdown_event.set()
    pipeline._closing = True

    for task in background_tasks:
        task.cancel()
    if background_tasks:
        await _await_cleanup(
            asyncio.gather(*background_tasks, return_exceptions=True),
            deadline,
            "background tasks",
        )

    for watcher in watchers:
        if watcher.is_running:
            logger.info(f"Stopping watcher for: {watcher.watch_dir}")
            await _await_cleanup(watcher.stop(), deadline, f"watcher {watcher.watch_dir}")

    logger.info("Shutting down RAG pipeline...")
    await _await_cleanup(pipeline.close(), deadline, "RAG pipeline")


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Initialize RAG pipeline and file watchers on startup."""
    global _shutdown_loop, _shutdown_owner_task
    _shutdown_event.clear()
    _shutdown_loop = asyncio.get_running_loop()
    _shutdown_owner_task = asyncio.current_task()
    setup_signal_handlers()
    config = get_config()
    pipeline = RAGPipeline(config)
    watchers: list[FileWatcher] = []
    lock_retry_task = None
    sync_tasks: list[asyncio.Task] = []

    try:
        await pipeline.initialize()
        logger.info("MCP Vectors server started")
        logger.info(f"Embedding model: {pipeline.lm_client.embedding_model}")
        logger.info(f"LLM model: {pipeline.lm_client.llm_model}")
        logger.info(f"Vector store: {config.qdrant_url or 'in-memory'}")

        # Resolve the project this instance should auto-maintain. With WATCH_DIR set,
        # those dirs are used verbatim; otherwise the launch-dir project (from PWD) is
        # auto-detected (maintain-only: see per-root indexed gate below).
        if config.watch_dirs:
            candidate_roots = [str(Path(d).expanduser().resolve(strict=False)) for d in config.watch_dirs]
        else:
            detected = resolve_project_root(config.watch_dirs)
            candidate_roots = [str(detected)] if detected else []

        watch_enabled = os.getenv("WATCH_ENABLED", "true").lower() in ("true", "1", "yes")

        if candidate_roots and watch_enabled:
            debounce = float(os.getenv("WATCH_DEBOUNCE", "2.0"))
            batch_interval = float(os.getenv("WATCH_BATCH_INTERVAL", "10.0"))
            loop = asyncio.get_running_loop()

            for root in candidate_roots:
                watch_path = Path(root)
                if not watch_path.is_dir():
                    logger.warning(f"Watch directory not found: {root}")
                    continue
                allowed, reason_codes = _should_index_directory_root(watch_path, config)
                if not allowed:
                    logger.warning(
                        f"Skipping auto-maintain for excluded root {sanitize_for_log(root)}: {', '.join(reason_codes)}"
                    )
                    continue

                # Maintain-only: skip projects that have never been indexed.
                status = await pipeline.get_indexing_status(root)
                if status.get("metadata", {}).get("file_count", 0) == 0:
                    logger.info(f"Skipping auto-maintain (not indexed yet): {sanitize_for_log(root)}")
                    continue

                # Bind callbacks to this root so newly indexed files get the right root_path.
                def make_index_callback(root_arg: str):
                    async def on_files_changed(paths: list[Path]):
                        logger.info(f"Auto-indexing {len(paths)} changed file(s)")
                        for path in paths:
                            if path.is_file():
                                try:
                                    result = await pipeline.index_file(path, root_path=root_arg)
                                    if result.success:
                                        logger.info(f"Indexed: {path.name} ({result.chunks_indexed} chunks)")
                                    elif not result.skipped:
                                        logger.warning(f"Failed to index {path.name}: {result.error}")
                                except Exception as e:
                                    logger.error(f"Error indexing {path}: {e}")
                    return on_files_changed

                async def on_files_deleted(paths: list[Path]):
                    logger.info(f"Removing {len(paths)} deleted file(s) from index")
                    for path in paths:
                        try:
                            result = await pipeline.remove_document(str(path))
                            if result.get("success"):
                                logger.info(f"Removed from index: {path.name}")
                        except Exception as e:
                            logger.error(f"Error removing {path}: {e}")

                # Safety net: reconcile each touched directory (non-recursive) against
                # the index so files that appeared without a usable per-file event
                # (FSEvents coalescing) are still picked up.
                def make_reconcile_callback(root_arg: str):
                    async def on_dirs_touched(dirs: list[Path]):
                        for directory in dirs:
                            if not directory.is_dir():
                                continue
                            try:
                                await pipeline.sync_directory(str(directory), recursive=False)
                            except Exception as e:
                                logger.error(f"Error reconciling {directory}: {e}")
                    return on_dirs_touched

                watcher = FileWatcher(
                    watch_dir=watch_path,
                    index_callback=make_index_callback(root),
                    delete_callback=on_files_deleted,
                    reconcile_callback=make_reconcile_callback(root),
                    excluded_extensions=set(config.excluded_extensions),
                    excluded_directories=set(config.excluded_directories),
                    debounce_seconds=debounce,
                    batch_interval_seconds=batch_interval,
                    respect_gitignore=config.respect_gitignore,
                )
                watchers.append(watcher)
                if watcher.start(loop):
                    logger.info(f"Started watching: {root}")
                    # Only the lock-owning process runs the startup reconcile, so
                    # multiple instances on the same project don't double-sync.
                    if config.auto_sync:
                        sync_tasks.append(asyncio.create_task(_run_startup_sync(pipeline, root)))
                else:
                    logger.info(f"Another process is watching: {root} (will retry for failover)")

            active_watchers = sum(1 for w in watchers if w.has_lock)
            if active_watchers > 0:
                logger.info(f"Active file watching enabled for {active_watchers} directory(ies)")
            elif watchers:
                logger.info("File watchers created but locks held by another process")

            if watchers:
                async def lock_retry_loop():
                    retry_interval = 10
                    while not _shutdown_event.is_set():
                        await asyncio.sleep(retry_interval)
                        if _shutdown_event.is_set():
                            break
                        for watcher in watchers:
                            if not watcher.has_lock and not watcher.is_running:
                                if watcher.start(loop):
                                    logger.info(f"Acquired watch lock (failover): {watcher.watch_dir}")
                                    if config.auto_sync:
                                        sync_tasks.append(
                                            asyncio.create_task(_run_startup_sync(pipeline, str(watcher.watch_dir)))
                                        )

                lock_retry_task = asyncio.create_task(lock_retry_loop())
        elif candidate_roots and not watch_enabled:
            logger.info("Active file watching disabled (WATCH_ENABLED=false)")

        yield AppContext(config=config, pipeline=pipeline, watchers=watchers)

    finally:
        background_tasks = list(sync_tasks)
        if lock_retry_task is not None:
            background_tasks.append(lock_retry_task)
        await _shutdown_resources(
            pipeline,
            watchers,
            background_tasks,
            config.graceful_shutdown_timeout,
        )
        _shutdown_loop = None
        _shutdown_owner_task = None


# ====================
# Server Setup
# ====================

mcp = FastMCP(
    name="mcp-vectors",
    instructions="""Local semantic search over indexed documents and codebases.

Three exposed tools: index_codebase, search_root, clear_index.

Use semantic search for conceptual, cross-file, exploratory retrieval or synthesis. Exact search/read tools remain better for exact symbols, literals, and line-by-line inspection — not for exact symbol/string lookups, use ripgrep/fd instead.

Workflow:
1. Use index_codebase to index a project root (pass dry_run=true to check status without indexing).
2. Use search_root to search — it fans out across chunks (code + docs), entities (symbol graph), and communities (architecture) in one call.
3. Use clear_index to remove stale entries.

Destructive operations are explicit. clear_index previews unless confirm=true and expected counts match.
""",
    lifespan=app_lifespan,
)


def _operation_rejected() -> dict:
    return {"success": False, "error": "Server is shutting down. Please try again after restart."}


def _result_dict(result) -> dict:
    return {
        "file_path": result.file_path,
        "file_name": result.file_name,
        "success": result.success,
        "chunks_indexed": result.chunks_indexed,
        "error": result.error,
        "skipped": result.skipped,
        "reason_codes": result.reason_codes,
    }


# ====================
# Request Lifecycle
# ====================

#: Context variable holding the active request ID so nested helpers can read
#: it without being passed it explicitly.  Empty string when no request is
#: active (e.g. during startup / teardown code).
_mcp_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "mcp_request_id", default=""
)


def _metrics_session_id(ctx: Context) -> str:
    """Best-effort Claude Code / MCP session identifier for metrics rows.

    Never raises: falls back to the active request ID, then ``"unknown"``.
    """
    try:
        cid = getattr(ctx, "client_id", None)
        if cid:
            return str(cid)
    except Exception:
        pass
    try:
        rc = getattr(ctx, "request_context", None)
        session = getattr(rc, "session", None)
        sid = getattr(session, "session_id", None) or getattr(session, "client_id", None)
        if sid:
            return str(sid)
    except Exception:
        pass
    return _mcp_request_id.get() or "unknown"


def _mcp_op(name: str):
    """Wrap an async MCP tool with per-invocation request-ID correlation and timing.

    A 12-character hex request ID is generated for each call and stored in
    ``_mcp_request_id`` so any helper called within the same async context can
    correlate log lines to the triggering tool call.

    Logged fields: ``[<req_id>] <name> start | done (<ms>ms) | raised (<ms>ms)``.
    No argument values, result contents, or exception messages are ever logged.
    Timestamps use the local RFC 3339 format configured by ``_LocalTimestampFormatter``.
    """
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            req_id = uuid.uuid4().hex[:12]
            token = _mcp_request_id.set(req_id)
            t0 = time.monotonic()
            logger.info("[%s] %s start", req_id, name)
            try:
                result = await fn(*args, **kwargs)
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                logger.info("[%s] %s done (%dms)", req_id, name, elapsed_ms)
                return result
            except Exception:
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                logger.warning("[%s] %s raised (%dms)", req_id, name, elapsed_ms)
                raise
            finally:
                _mcp_request_id.reset(token)
        return wrapper
    return decorator


def _tool(**kwargs):
    """Combined ``@_tool()`` + request-ID lifecycle decorator.

    Use in place of ``@_tool()`` for every tool so that request IDs and
    timing are tracked uniformly without repeating boilerplate on each handler.
    ``**kwargs`` are forwarded verbatim to ``mcp.tool()``.
    """
    def decorator(fn):
        # Apply lifecycle tracking first (innermost), then register with FastMCP.
        # functools.wraps on the inner wrapper preserves __name__, __annotations__,
        # and __wrapped__ so FastMCP's signature introspection sees the real params.
        lifecycle_wrapped = _mcp_op(fn.__name__)(fn)
        return mcp.tool(**kwargs)(lifecycle_wrapped)
    return decorator


# ====================
# Tools
# ====================

# DEPRECATED — pending deletion per ADR-0052
async def index_files(
    paths: Annotated[list[str], Field(description="Non-empty list of file or directory paths to index", min_length=1)],
    ctx: Context,
    recursive: Annotated[bool, Field(description="Index directories recursively")] = True,
    respect_gitignore: Annotated[bool, Field(description="Skip files/dirs matched by .gitignore or .git/info/exclude when walking directories. Explicitly named file paths are always indexed.")] = True,
) -> dict:
    """Add specific files or directories to the semantic index on demand. Call after checking get_indexing_status, or use index_codebase instead to index a whole project root with status gating. Resolves and replace-indexes each path (dirs recurse, honoring .gitignore); marks missing paths reason_codes=["path_not_found"]."""
    if not increment_operations():
        return _operation_rejected()
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        pipeline = app_ctx.pipeline
        await ctx.info(f"Indexing {len(paths)} path(s)...")
        all_results = []
        for path_str in paths:
            base_dir = app_ctx.config.watch_dirs[0] if app_ctx.config.watch_dirs else None
            path = resolve_path(path_str, base_dir)
            if path.is_file():
                try:
                    all_results.append(_result_dict(await pipeline.index_file(path)))
                except RootResolutionError as e:
                    all_results.append({
                        "file_path": str(path),
                        "file_name": path.name,
                        "success": False,
                        "chunks_indexed": 0,
                        "error": {"code": e.error_code, "message": e.message},
                        "skipped": False,
                        "reason_codes": [e.error_code],
                    })
            elif path.is_dir():
                await ctx.info(f"Indexing directory: {path}")
                try:
                    all_results.extend(_result_dict(result) for result in await pipeline.index_directory(path, recursive=recursive, respect_gitignore=respect_gitignore))
                except RootResolutionError as e:
                    all_results.append({
                        "file_path": str(path),
                        "file_name": path.name,
                        "success": False,
                        "chunks_indexed": 0,
                        "error": {"code": e.error_code, "message": e.message},
                        "skipped": False,
                        "reason_codes": [e.error_code],
                    })
            else:
                all_results.append({
                    "file_path": str(path),
                    "file_name": path.name,
                    "success": False,
                    "chunks_indexed": 0,
                    "error": f"Path not found: {path}",
                    "skipped": False,
                    "reason_codes": ["path_not_found"],
                })
        successful = sum(1 for r in all_results if r["success"])
        total_chunks = sum(r["chunks_indexed"] for r in all_results)
        await ctx.info(f"Indexed {successful}/{len(all_results)} files, {total_chunks} total chunks")
        return {"success": True, "files_processed": len(all_results), "files_indexed": successful, "total_chunks": total_chunks, "results": all_results}
    except Exception as e:
        await ctx.error(f"Indexing failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        decrement_operations()


# DEPRECATED — pending deletion per ADR-0052
async def search_documents(
    query: Annotated[str, Field(description="Non-empty semantic search query", min_length=1)],
    ctx: Context,
    limit: Annotated[int, Field(description="Maximum number of file results", ge=1, le=100)] = 15,
    min_score: Annotated[Optional[float], Field(description="Minimum relevance score threshold (0.0-1.0)", ge=0.0, le=1.0)] = 0.35,
    exclude_files: Annotated[Optional[list[str]], Field(description="Exact file_path values from previous results to exclude")] = None,
    include_summary: Annotated[bool, Field(description="Include LLM-generated summary for each result")] = False,
    base_dirs: Annotated[Optional[list[str]], Field(description="Absolute directory paths to filter results")] = None,
    extensions: Annotated[Optional[list[str]], Field(description="Optional extensions such as .py or md")] = None,
    file_types: Annotated[Optional[list[str]], Field(description="Optional parser file types such as python, markdown, json")] = None,
    max_chunks_per_file: Annotated[Optional[int], Field(description="Maximum chunks returned per file", ge=1, le=20)] = 5,
    max_chunk_chars: Annotated[Optional[int], Field(description="Maximum characters per returned chunk", ge=80, le=10000)] = 2000,
    include_chunk_text: Annotated[bool, Field(description="Include chunk text in results")] = True,
    include_metadata: Annotated[bool, Field(description="Include payload metadata in results")] = False,
) -> dict:
    """Retrieve conceptually relevant passages across ALL indexed documents with no root scope, for cross-corpus questions over docs, config, or mixed content. Use search_code instead to scope to one codebase root."""
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        pipeline = app_ctx.pipeline
        if not query.strip():
            return {"success": False, "error": "Query cannot be empty"}
        await ctx.info(f"Searching for: {query}")
        response = await pipeline.search(
            query=query,
            limit=limit,
            min_score=min_score,
            exclude_files=exclude_files,
            include_summary=include_summary,
            base_dirs=base_dirs,
            extensions=extensions,
            file_types=file_types,
            max_chunks_per_file=max_chunks_per_file,
            max_chunk_chars=max_chunk_chars,
            include_chunk_text=include_chunk_text,
            include_metadata=include_metadata,
        )
        if not response.success:
            return {"success": False, "error": response.error}
        results = [
            {
                "file_path": result.file_path,
                "file_name": result.file_name,
                "score": result.score,
                "chunks": result.chunks,
                "summary": result.summary,
                "metadata": result.metadata,
            }
            for result in response.results
        ]
        await ctx.info(f"Found {len(results)} matching documents")
        return {
            "success": True,
            "query": query,
            "total_results": len(results),
            "results": results,
            "formatted_results": response.formatted_results,
            "filtering_mode": response.filtering_mode,
            "warnings": response.warnings,
        }
    except Exception as e:
        await ctx.error(f"Search failed: {e}")
        return {"success": False, "error": str(e)}


# DEPRECATED — pending deletion per ADR-0052
async def list_indexed_files(
    ctx: Context,
    skip: Annotated[int, Field(description="Number of files to skip", ge=0)] = 0,
    limit: Annotated[int, Field(description="Maximum number of files to return", ge=1, le=1000)] = 100,
    base_dirs: Annotated[Optional[list[str]], Field(description="Absolute directory paths to filter results")] = None,
) -> dict:
    """Enumerate what is currently indexed and obtain exact file_path/path_key values for later filtering, clear_index, or secret purge. Call to confirm coverage before searching or clearing."""
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        return await app_ctx.pipeline.list_indexed_files(skip=skip, limit=limit, base_dirs=base_dirs)
    except Exception as e:
        await ctx.error(f"Listing failed: {e}")
        return {"success": False, "error": str(e)}




@_tool()
async def clear_index(
    path: Annotated[str, Field(description="File or directory path to clear from Qdrant only", min_length=1)],
    ctx: Context,
    confirm: Annotated[bool, Field(description="False previews; true deletes only with matching expected counts")] = False,
    expected_files: Annotated[Optional[int], Field(description="Expected matched file count from preview", ge=0)] = None,
    expected_chunks: Annotated[Optional[int], Field(description="Expected matched chunk count from preview", ge=0)] = None,
    allow_large_scan: Annotated[bool, Field(description="Allow deletion after a scan beyond default bounds")] = False,
) -> dict:
    """Remove indexed data for one path from Qdrant only (never the filesystem), e.g. to drop stale entries. With confirm=false it previews matched counts; re-run with confirm=true plus expected_files/expected_chunks matching the preview to delete."""
    if confirm and not increment_operations():
        return _operation_rejected()
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        return await app_ctx.pipeline.clear_index(
            path,
            confirm=confirm,
            expected_files=expected_files,
            expected_chunks=expected_chunks,
            allow_large_scan=allow_large_scan,
        )
    except Exception as e:
        await ctx.error(f"Clear index failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if confirm:
            decrement_operations()


# DEPRECATED — pending deletion per ADR-0052
async def audit_indexed_secrets(
    ctx: Context,
    include_content_scan: Annotated[bool, Field(description="Scan bounded chunk text for secret-like signals; never returns values")] = False,
    max_scan_points: Annotated[Optional[int], Field(description="Maximum Qdrant points to scan", ge=1, le=200000)] = None,
) -> dict:
    """Detect secret-like material that was accidentally indexed without ever returning secret values. Run before purge_indexed_secret_files to get the exact offending paths."""
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        return await app_ctx.pipeline.audit_indexed_secrets(include_content_scan=include_content_scan, max_scan_points=max_scan_points)
    except Exception as e:
        await ctx.error(f"Secret audit failed: {e}")
        return {"success": False, "error": str(e)}


# DEPRECATED — pending deletion per ADR-0052
async def purge_indexed_secret_files(
    file_paths: Annotated[list[str], Field(description="Exact secret-like file paths to remove from Qdrant only", min_length=1)],
    ctx: Context,
    confirm_secret_cleanup: Annotated[bool, Field(description="Must be true to purge indexed secrets")] = False,
) -> dict:
    """Remediate indexed secrets by deleting exact files from the vector index only (filesystem files are never touched). Call after audit_indexed_secrets supplies the exact paths. Requires confirm_secret_cleanup=true and refuses any path the safety policy does not classify as secret-like."""
    if not increment_operations():
        return _operation_rejected()
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        return await app_ctx.pipeline.purge_indexed_secret_files(file_paths, confirm_secret_cleanup=confirm_secret_cleanup)
    except Exception as e:
        await ctx.error(f"Secret purge failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        decrement_operations()


@_tool()
async def index_codebase(
    root_path: Annotated[str, Field(description="Root directory or file to index", min_length=1)],
    ctx: Context,
    recursive: Annotated[bool, Field(description="Index directories recursively")] = True,
    force: Annotated[bool, Field(description="Re-index files even when already indexed; uses replace-safe indexing")] = False,
    dry_run: Annotated[bool, Field(description="Return plan without indexing")] = False,
    respect_gitignore: Annotated[bool, Field(description="Skip files/dirs matched by .gitignore or .git/info/exclude")] = True,
) -> dict:
    """Bring an entire project root into the index so search_root can use it — the first step before searching. Pass dry_run=true to preview status+plan without indexing. If the root already appears indexed it returns indexed=false with a message unless force=true triggers a replace-safe re-index."""
    if not dry_run and not increment_operations():
        return _operation_rejected()
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        pipeline = app_ctx.pipeline
        root = str(resolve_path(root_path))
        status = await pipeline.get_indexing_status(root)
        plan = await pipeline.preview_reindex([root], recursive=recursive, respect_gitignore=respect_gitignore)
        if dry_run:
            return {"success": True, "dry_run": True, "status": status, "plan": plan}
        if status.get("status") not in ("not_found", "legacy_metadata") and not force:
            return {
                "success": True,
                "indexed": False,
                "status": status,
                "plan": plan,
                "message": "Path already appears indexed. Re-run with force=true to replace-safe re-index.",
            }
        results = await pipeline.index_directory(root, recursive=recursive, respect_gitignore=respect_gitignore) if Path(root).is_dir() else [await pipeline.index_file(root)]
        successful = sum(1 for r in results if r.success)
        return {
            "success": True,
            "indexed": True,
            "files_processed": len(results),
            "files_indexed": successful,
            "total_chunks": sum(r.chunks_indexed for r in results),
            "status_before": status,
            "plan": plan,
            "results": [_result_dict(r) for r in results],
        }
    except RootResolutionError as e:
        await ctx.error(f"Codebase indexing rejected: {e}")
        return {"success": False, "error": {"code": e.error_code, "message": e.message}}
    except Exception as e:
        await ctx.error(f"Codebase indexing failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if not dry_run:
            decrement_operations()


# DEPRECATED — pending deletion per ADR-0052
async def search_code(
    root_path: Annotated[str, Field(description="Indexed codebase root to search", min_length=1)],
    query: Annotated[str, Field(description="Non-empty semantic code search query", min_length=1)],
    ctx: Context,
    limit: Annotated[int, Field(description="Maximum number of file results", ge=1, le=100)] = 10,
    extensions: Annotated[Optional[list[str]], Field(description="Optional extensions such as .py or ts")] = None,
    file_types: Annotated[Optional[list[str]], Field(description="Optional parser file types such as python or typescript")] = None,
    exclude_files: Annotated[Optional[list[str]], Field(description="Exact file_path values to exclude")] = None,
    min_score: Annotated[float, Field(description="Minimum relevance score", ge=0.0, le=1.0)] = 0.35,
    max_chunk_chars: Annotated[int, Field(description="Maximum characters per returned chunk", ge=80, le=10000)] = 1600,
    include_full_chunks: Annotated[bool, Field(description="Return full chunks instead of compact snippets")] = False,
) -> dict:
    """Find code by meaning within a single indexed root (root_path required), for conceptual or cross-file retrieval in one project. Requires the root indexed first via index_codebase, else returns an error; use ripgrep/fd for exact strings, search_entities for symbol lookup, search_global for architecture."""
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        pipeline = app_ctx.pipeline
        root = str(resolve_path(root_path))
        status = await pipeline.get_indexing_status(root)
        if status.get("status") == "not_found":
            return {"success": False, "error": "Root is not indexed. Call index_codebase first.", "status": status}
        response = await pipeline.search(
            query=query,
            limit=limit,
            min_score=min_score,
            exclude_files=exclude_files,
            root_path=root,
            extensions=extensions,
            file_types=file_types,
            max_chunk_chars=None if include_full_chunks else max_chunk_chars,
            include_metadata=False,
        )
        if not response.success:
            return {"success": False, "error": response.error, "status": status}
        return {
            "success": True,
            "query": query,
            "root_path": root,
            "status": status,
            "total_results": response.total_results,
            "formatted_results": response.formatted_results,
            "results": [
                {
                    "file_path": result.file_path,
                    "file_name": result.file_name,
                    "score": result.score,
                    "chunks": result.chunks,
                }
                for result in response.results
            ],
            "filtering_mode": response.filtering_mode,
            "confidence": response.confidence,
        }
    except Exception as e:
        await ctx.error(f"Code search failed: {e}")
        return {"success": False, "error": str(e)}


# DEPRECATED — pending deletion per ADR-0052
async def get_indexing_status(
    ctx: Context,
    root_path: Annotated[Optional[str], Field(description="Optional root path to inspect")] = None,
) -> dict:
    """Decide whether and how to index a root before searching — typically the first step. Returns status (not_found, indexed, legacy_metadata, or partially_indexed) and a recommended next_action."""
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        pipeline = app_ctx.pipeline
        result = await pipeline.get_indexing_status(root_path)
        # Merge graph_stats if available for this root
        if root_path:
            from vectors.paths import PathPolicy as _PathPolicy
            root_id = _PathPolicy.path_key(root_path)
            graph_stats = pipeline.get_graph_stats(root_id)
            if graph_stats is not None:
                result["graph_stats"] = graph_stats
        return result
    except Exception as e:
        await ctx.error(f"Status failed: {e}")
        return {"success": False, "error": str(e)}


# DEPRECATED — pending deletion per ADR-0052
async def get_stats(ctx: Context) -> dict:
    """Check overall server health and configuration; use get_indexing_status for per-root coverage."""
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        stats = await app_ctx.pipeline.get_stats()
        stats["watchers"] = {
            "enabled": bool(app_ctx.watchers),
            "count": len(app_ctx.watchers),
            "running": sum(1 for w in app_ctx.watchers if w.is_running),
            "has_lock": sum(1 for w in app_ctx.watchers if w.has_lock),
            "watch_dirs": [str(w.watch_dir) for w in app_ctx.watchers],
            "lock_scope": "same-host /tmp/mcp-vectors-locks only",
        }
        return stats
    except Exception as e:
        await ctx.error(f"Failed to get stats: {e}")
        return {"success": False, "error": str(e)}




# ====================
# Graph / Entity Tools
# ====================


# DEPRECATED — pending deletion per ADR-0052
async def get_entity_callers(
    root_path: Annotated[str, Field(description="Absolute path of the indexed codebase root (same value passed to search_code/index_codebase)", min_length=1)],
    entity_name: Annotated[str, Field(description="Function or entity name to look up callers for", min_length=1)],
    ctx: Context,
) -> dict:
    """Use before changing a function or class signature, renaming an entity, or assessing blast radius. Performs reverse call-graph analysis; confirm the exact name with search_entities first — an unknown name returns an empty callers list rather than an error. Not for discovering what a symbol does — use get_entity_neighbors or search_code instead."""
    if not ENTITY_EXTRACTION:
        return {"success": False, "error": "Graph features require ENTITY_EXTRACTION=true"}
    app_ctx: AppContext = ctx.request_context.lifespan_context
    pipeline = app_ctx.pipeline
    if not increment_operations():
        return {"success": False, "error": "Server is shutting down"}
    _outcome = OUTCOME_ERROR
    try:
        callers = pipeline.get_callers(root_path, entity_name)
        _outcome = OUTCOME_SUCCESS if callers else OUTCOME_ZERO_RESULT
        return {"success": True, "entity_name": entity_name, "callers": callers}
    except KeyError:
        return {
            "success": False,
            "error": {"code": "root_not_indexed", "message": f"Root not indexed: {root_path}"},
        }
    except Exception as e:
        logger.exception(f"Get callers failed for {entity_name}")
        await ctx.error(f"Get entity callers failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        record_tool_call("get_entity_callers", _metrics_session_id(ctx), root_path, _outcome)
        decrement_operations()


# DEPRECATED — pending deletion per ADR-0052
async def get_entity_neighbors(
    root_path: Annotated[str, Field(description="Absolute path of the indexed codebase root (same value passed to search_code/index_codebase)", min_length=1)],
    entity_name: Annotated[str, Field(description="Entity name to look up neighbors for", min_length=1)],
    ctx: Context,
    max_depth: Annotated[int, Field(description="BFS hop depth (1–5)", ge=1, le=5)] = 2,
    edge_types: Annotated[Optional[list[str]], Field(description="Filter by edge types (imports, calls, inherits, defines, references, related)")] = None,
) -> dict:
    """Use when tracing how a known symbol relates to or depends on other symbols (imports, calls, inheritance, definitions). Traverses the entity graph outward; resolves the seed by first name match — an unknown name returns entity=null with empty neighbors. Not for finding a symbol by approximate name — use search_entities first, then get_entity_neighbors."""
    if not ENTITY_EXTRACTION:
        return {"success": False, "error": "Graph features require ENTITY_EXTRACTION=true"}
    app_ctx: AppContext = ctx.request_context.lifespan_context
    pipeline = app_ctx.pipeline
    if not increment_operations():
        return {"success": False, "error": "Server is shutting down"}
    _outcome = OUTCOME_ERROR
    try:
        result = pipeline.get_neighbors(root_path, entity_name, max_depth=max_depth, edge_types=edge_types)
        _outcome = OUTCOME_SUCCESS if result.get("neighbors") else OUTCOME_ZERO_RESULT
        return {"success": True, **result}
    except KeyError:
        return {
            "success": False,
            "error": {"code": "root_not_indexed", "message": f"Root not indexed: {root_path}"},
        }
    except Exception as e:
        logger.exception(f"Get neighbors failed for {entity_name}")
        await ctx.error(f"Get entity neighbors failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        record_tool_call("get_entity_neighbors", _metrics_session_id(ctx), root_path, _outcome)
        decrement_operations()


# DEPRECATED — pending deletion per ADR-0052
async def search_entities(
    root_path: Annotated[str, Field(description="Absolute path of the indexed codebase root (same value passed to search_code/index_codebase)", min_length=1)],
    query: Annotated[str, Field(description="Entity name query (case-insensitive substring match)", min_length=1)],
    ctx: Context,
    limit: Annotated[int, Field(description="Maximum number of entities to return", ge=1, le=100)] = 10,
) -> dict:
    """Use to locate a named or partially-known code symbol in the entity graph before graph traversal. Case-insensitive substring match on symbol names, not semantic search. Not for conceptual or semantic code search — use search_code instead."""
    if not ENTITY_EXTRACTION:
        return {"success": False, "error": "Graph features require ENTITY_EXTRACTION=true"}
    app_ctx: AppContext = ctx.request_context.lifespan_context
    pipeline = app_ctx.pipeline
    if not increment_operations():
        return {"success": False, "error": "Server is shutting down"}
    _outcome = OUTCOME_ERROR
    try:
        entities = pipeline.find_entities(root_path, query, limit=limit)
        _outcome = OUTCOME_SUCCESS if entities else OUTCOME_ZERO_RESULT
        return {"success": True, "query": query, "entities": entities, "total": len(entities)}
    except KeyError:
        return {
            "success": False,
            "error": {"code": "root_not_indexed", "message": f"Root not indexed: {root_path}"},
        }
    except Exception as e:
        logger.exception(f"Search entities failed for query={query}")
        await ctx.error(f"Search entities failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        record_tool_call("search_entities", _metrics_session_id(ctx), root_path, _outcome)
        decrement_operations()


# DEPRECATED — pending deletion per ADR-0052
async def search_global(
    root_path: Annotated[str, Field(description="Absolute path of the indexed root directory", min_length=1)],
    query: Annotated[str, Field(description="Search query for global community-level synthesis", min_length=1)],
    ctx: Context,
    limit: Annotated[int, Field(description="Max community results to retrieve (1-20)", ge=1, le=20)] = 5,
) -> dict:
    """Use when asking architecture-level or 'how is this repo organized' questions that need synthesis across many files. Synthesizes GraphRAG community reports; while communities are dirty or unbuilt it schedules a rebuild and returns mode='rebuilding' with vector-search fallback results. Not for locating a specific symbol or file — use search_code or search_entities instead."""
    if not ENTITY_EXTRACTION:
        return {"success": False, "error": {"code": "feature_disabled", "message": "Graph features require ENTITY_EXTRACTION=true"}}
    if not increment_operations():
        return _operation_rejected()
    _outcome = OUTCOME_ERROR
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        pipeline = app_ctx.pipeline
        result = await pipeline.search_global(query=query, root_path=root_path, limit=limit)
        if not result.get("success"):
            _outcome = OUTCOME_ERROR
        elif result.get("community_results") or result.get("fallback_results"):
            _outcome = OUTCOME_SUCCESS
        else:
            _outcome = OUTCOME_ZERO_RESULT
        return result
    except Exception as e:
        await ctx.error(f"Global search failed: {e}")
        return {"success": False, "error": {"code": "invalid_root", "message": str(e)}}
    finally:
        record_tool_call("search_global", _metrics_session_id(ctx), root_path, _outcome)
        decrement_operations()


# DEPRECATED — pending deletion per ADR-0052
async def list_communities(
    root_path: Annotated[str, Field(description="Absolute path of the indexed root directory", min_length=1)],
    ctx: Context,
    level: Annotated[Optional[int], Field(description="Filter by hierarchy level (>=0)", ge=0)] = None,
    limit: Annotated[int, Field(description="Maximum communities to return (1-200)", ge=1, le=200)] = 50,
) -> dict:
    """Discover the module/cluster structure of an indexed root by listing detected entity communities, optionally filtered by hierarchy level. Feed a community_id to get_community_report for its full report. On first build or a dirty graph it schedules a rebuild and returns mode='rebuilding'."""
    if not ENTITY_EXTRACTION:
        return {"success": False, "error": {"code": "feature_disabled", "message": "Graph features require ENTITY_EXTRACTION=true"}}
    if not increment_operations():
        return _operation_rejected()
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        pipeline = app_ctx.pipeline
        if not pipeline._initialized:
            await pipeline.initialize()
        result = await pipeline.list_communities(root_path, level=level, limit=limit)
        return result.to_dict()
    except Exception as e:
        await ctx.error(f"List communities failed: {e}")
        return {"mode": "error", "error": {"code": "internal_error", "message": str(e)}}
    finally:
        decrement_operations()


# DEPRECATED — pending deletion per ADR-0052
async def get_community_report(
    root_path: Annotated[str, Field(description="Absolute path of the indexed root directory", min_length=1)],
    community_id: Annotated[str, Field(description="Community ID to retrieve report for", min_length=1)],
    ctx: Context,
) -> dict:
    """Read the detailed LLM-generated report for one community_id obtained from list_communities. If communities are stale or missing it schedules a rebuild and returns mode='rebuilding'; an unknown id returns community_not_found."""
    if not ENTITY_EXTRACTION:
        return {"success": False, "error": {"code": "feature_disabled", "message": "Graph features require ENTITY_EXTRACTION=true"}}
    if not increment_operations():
        return _operation_rejected()
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        pipeline = app_ctx.pipeline
        if not pipeline._initialized:
            await pipeline.initialize()
        result = await pipeline.get_community_report(root_path, community_id)
        return result.to_dict()
    except Exception as e:
        await ctx.error(f"Get community report failed: {e}")
        return {"mode": "error", "error": {"code": "internal_error", "message": str(e)}}
    finally:
        decrement_operations()


# ====================
# search_root — unified 3-channel search
# ====================

# Number of top matched entities to enrich with callers+neighbors.
_ENTITY_ENRICH_LIMIT = 5


@_tool()
async def search_root(
    root_path: Annotated[str, Field(description="Absolute path of the indexed codebase root", min_length=1)],
    query: Annotated[str, Field(description="Semantic search query — not for exact symbol/string lookups, use ripgrep/fd instead", min_length=1)],
    ctx: Context,
    limit: Annotated[int, Field(description="Max results per channel (1-100); total envelope is up to 3×limit", ge=1, le=100)] = 10,
    min_score: Annotated[float, Field(description="Minimum relevance score", ge=0.0, le=1.0)] = 0.35,
) -> dict:
    """Search an indexed root across all three channels — chunks (code + docs), entities (symbol graph with callers/neighbors), and communities (architecture) — in one call. Returns per-channel results each with a success flag. Top-level success is true if at least one channel succeeds. Not for exact symbol/string lookups — use ripgrep/fd instead; not for cross-root document search — use index_codebase to add other roots then call search_root on each."""
    if not query.strip():
        return {"success": False, "error": {"code": "empty_query", "message": "Query must not be empty"}}

    try:
        resolved_root = str(resolve_path(root_path))
    except Exception as e:
        return {"success": False, "error": {"code": "invalid_root_path", "message": str(e)}}
    if not resolved_root:
        return {"success": False, "error": {"code": "invalid_root_path", "message": "root_path could not be resolved"}}

    if not increment_operations():
        return _operation_rejected()

    _outcome = OUTCOME_ERROR
    try:
        app_ctx: AppContext = ctx.request_context.lifespan_context
        pipeline = app_ctx.pipeline
        timeout = app_ctx.config.search_root_timeout_seconds
        session_id = _metrics_session_id(ctx)

        async def _chunks_channel() -> dict:
            try:
                response = await pipeline.search(
                    query=query,
                    limit=limit,
                    min_score=min_score,
                    base_dirs=[resolved_root],
                )
                if not response.success:
                    r: dict = {"success": False, "error": response.error}
                else:
                    r = {
                        "success": True,
                        "results": [
                            {
                                "file_path": item.file_path,
                                "file_name": item.file_name,
                                "score": item.score,
                                "chunks": item.chunks,
                            }
                            for item in response.results
                        ],
                        "total_results": response.total_results,
                    }
            except Exception as e:
                r = {"success": False, "error": str(e)}
            record_tool_call(
                "search_root/chunks", session_id, resolved_root,
                OUTCOME_SUCCESS if r.get("success") else OUTCOME_ERROR,
            )
            return r

        async def _entities_channel() -> dict:
            if not ENTITY_EXTRACTION:
                return {"success": True, "results": [], "warning": "ENTITY_EXTRACTION disabled"}
            try:
                loop = asyncio.get_running_loop()
                matched = await pipeline.search_entities_semantic(resolved_root, query, limit)
                enrich_n = min(limit, _ENTITY_ENRICH_LIMIT)
                enriched = []
                for entity in matched[:enrich_n]:
                    eid = entity.get("entity_id") or entity.get("name", "")
                    try:
                        callers, neighbors_result = await asyncio.gather(
                            loop.run_in_executor(None, pipeline.get_callers, resolved_root, eid),
                            loop.run_in_executor(None, pipeline.get_neighbors, resolved_root, eid),
                            return_exceptions=True,
                        )
                        callers_list = callers if isinstance(callers, list) else []
                        neighbors_list = (
                            neighbors_result.get("neighbors", [])
                            if isinstance(neighbors_result, dict)
                            else []
                        )
                    except Exception:
                        callers_list = []
                        neighbors_list = []
                    enriched.append({**entity, "callers": callers_list, "neighbors": neighbors_list})
                enriched.extend(matched[enrich_n:])
                r: dict = {"success": True, "results": enriched}
            except Exception as e:
                r = {"success": False, "error": str(e)}
            record_tool_call(
                "search_root/entities", session_id, resolved_root,
                OUTCOME_SUCCESS if r.get("success") else OUTCOME_ERROR,
            )
            return r

        async def _communities_channel() -> dict:
            if not ENTITY_EXTRACTION:
                return {"success": True, "results": [], "warning": "ENTITY_EXTRACTION disabled"}
            try:
                result = await pipeline.search_global(query=query, root_path=resolved_root, limit=limit)
                r: dict = {"success": result.get("success", True), "results": result}
            except Exception as e:
                r = {"success": False, "error": str(e)}
            record_tool_call(
                "search_root/communities", session_id, resolved_root,
                OUTCOME_SUCCESS if r.get("success") else OUTCOME_ERROR,
            )
            return r

        tasks = {
            "chunks": asyncio.ensure_future(_chunks_channel()),
            "entities": asyncio.ensure_future(_entities_channel()),
            "communities": asyncio.ensure_future(_communities_channel()),
        }
        done, pending = await asyncio.wait(list(tasks.values()), timeout=timeout)

        # Cancel timed-out tasks
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        channel_results: dict[str, dict] = {}
        task_to_channel = {v: k for k, v in tasks.items()}
        for task in tasks.values():
            channel = task_to_channel[task]
            if task in done:
                try:
                    channel_results[channel] = task.result()
                except Exception as e:
                    channel_results[channel] = {"success": False, "error": str(e)}
            else:
                channel_results[channel] = {"success": False, "error": "timeout"}

        any_success = any(v.get("success") for v in channel_results.values())
        _outcome = OUTCOME_SUCCESS if any_success else OUTCOME_ERROR
        return {
            "success": any_success,
            "query": query,
            "root_path": resolved_root,
            **channel_results,
        }
    except Exception as e:
        await ctx.error(f"search_root failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        record_tool_call("search_root", _metrics_session_id(ctx), resolved_root, _outcome)
        decrement_operations()


# ====================
# Resources
# ====================

@mcp.resource("config://status")
def get_config_status() -> str:
    """Get the current configuration status."""
    config = get_config()
    watch_dirs_str = ", ".join(config.watch_dirs) if config.watch_dirs else "not configured"
    excluded_ext_preview = ", ".join(config.excluded_extensions[:10])
    excluded_dirs_preview = ", ".join(config.excluded_directories[:10])
    secret_patterns_preview = ", ".join(config.secret_path_patterns[:10])
    status_lines = [
        "MCP Vectors Configuration Status",
        "=" * 40,
        "",
        "LM Studio:",
        f"  URL: {config.lm_studio_url}",
        f"  Embedding Model: {config.embedding_model}",
        f"  LLM Model: {config.llm_model}",
        "",
        "Qdrant:",
        f"  URL: {config.qdrant_url or 'in-memory'}",
        f"  Collection: {config.qdrant_collection}",
        "",
        "Indexing:",
        f"  Watch Directories: {watch_dirs_str}",
        f"  Chunk Size: {config.chunk_size}",
        f"  Chunk Overlap: {config.chunk_overlap}",
        f"  Max File Size: {config.max_file_size_mb}MB",
        f"  Max Scroll Points: {config.max_scroll_points}",
        "",
        "Excluded Extensions (deny-list):",
        f"  {excluded_ext_preview}...",
        "",
        "Excluded Directories:",
        f"  {excluded_dirs_preview}...",
        "",
        "Secret Path Patterns (prospective skip only):",
        f"  {secret_patterns_preview}...",
    ]
    return "\n".join(status_lines)


# ====================
# Entry Point
# ====================

def main():
    """Main entry point for the server.

    Dispatches the ``metrics`` subcommand to the management CLI; otherwise runs
    the MCP server over streamable HTTP.
    """
    if len(sys.argv) > 1 and sys.argv[1] == "metrics":
        from vectors.metrics import run_cli
        raise SystemExit(run_cli(sys.argv[2:]))

    parser = build_streamable_http_parser(default_path="/mcp-vectors")
    args = parse_streamable_http_args(parser, default_path="/mcp-vectors")
    run_with_streamable_http(mcp, args, default_http_port=8002, default_https_port=4432)


if __name__ == "__main__":
    main()
