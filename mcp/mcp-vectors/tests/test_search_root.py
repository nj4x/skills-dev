"""
Runtime tests for the search_root tool handler.

Covers:
- three-channel dispatch: all channels succeed
- timeout path: pending tasks are cancelled; timed-out channels return success=False
- partial success: one channel errors, top-level success=True if others succeed
- ENTITY_EXTRACTION=false: entities and communities channels return empty results,
  chunks channel still runs
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(pipeline, timeout_seconds=30):
    ctx = MagicMock()
    ctx.error = AsyncMock()
    ctx.client_id = "test-session"
    app_ctx = MagicMock()
    ctx.request_context.lifespan_context = app_ctx
    app_ctx.pipeline = pipeline
    app_ctx.config = MagicMock()
    app_ctx.config.search_root_timeout_seconds = timeout_seconds
    return ctx


def _make_pipeline():
    from vectors.rag import RAGResponse, SearchResultWithSummary

    pipeline = MagicMock()
    pipeline.search = AsyncMock(
        return_value=RAGResponse(
            success=True,
            query="test",
            results=[
                SearchResultWithSummary(
                    file_path="/root/file.py",
                    file_name="file.py",
                    score=0.9,
                    chunks=[{"text": "code"}],
                )
            ],
            total_results=1,
            formatted_results=[],
        )
    )
    pipeline.search_entities_semantic = AsyncMock(return_value=[])
    pipeline.search_global = AsyncMock(return_value={"success": True, "results": []})
    pipeline.get_callers = MagicMock(return_value=[])
    pipeline.get_neighbors = MagicMock(return_value={"neighbors": []})
    return pipeline


# ---------------------------------------------------------------------------
# 1. Three-channel dispatch — all channels succeed
# ---------------------------------------------------------------------------


def test_search_root_all_channels_succeed():
    """When all three channels return success, top-level success is True and all
    three channel keys are present in the response."""

    async def _run():
        from server import search_root

        pipeline = _make_pipeline()
        ctx = _make_ctx(pipeline)

        with patch("server.increment_operations", return_value=True), \
             patch("server.decrement_operations"), \
             patch("server.record_tool_call"), \
             patch("server.ENTITY_EXTRACTION", True):
            result = await search_root(root_path="/root", query="test query", ctx=ctx)

        assert result["success"] is True
        assert "chunks" in result
        assert "entities" in result
        assert "communities" in result
        assert result["chunks"]["success"] is True
        assert result["entities"]["success"] is True

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 2. Timeout path
# ---------------------------------------------------------------------------


def test_search_root_timeout_cancels_pending_channels():
    """When channels do not finish within the timeout, they are marked as
    timed-out errors and the top-level success reflects remaining channels."""

    async def _run():
        import asyncio
        from server import search_root

        pipeline = _make_pipeline()
        # Make all channels hang indefinitely
        async def _hang(*args, **kwargs):
            await asyncio.sleep(9999)

        pipeline.search = _hang
        pipeline.search_entities_semantic = _hang
        pipeline.search_global = _hang

        ctx = _make_ctx(pipeline, timeout_seconds=0.05)

        with patch("server.increment_operations", return_value=True), \
             patch("server.decrement_operations"), \
             patch("server.record_tool_call"), \
             patch("server.ENTITY_EXTRACTION", True):
            result = await search_root(root_path="/root", query="test query", ctx=ctx)

        assert result["success"] is False
        assert result["chunks"]["error"] == "timeout"
        assert result["entities"]["error"] == "timeout"
        assert result["communities"]["error"] == "timeout"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. Partial success — one channel errors, others succeed
# ---------------------------------------------------------------------------


def test_search_root_partial_success():
    """When the entities channel raises but chunks succeeds, top-level success
    is still True (at-least-one-success contract)."""

    async def _run():
        from server import search_root
        from vectors.rag import RAGResponse, SearchResultWithSummary

        pipeline = _make_pipeline()
        pipeline.search = AsyncMock(
            return_value=RAGResponse(
                success=True,
                query="test",
                results=[
                    SearchResultWithSummary(
                        file_path="/root/file.py",
                        file_name="file.py",
                        score=0.8,
                        chunks=[],
                    )
                ],
                total_results=1,
                formatted_results=[],
            )
        )
        pipeline.search_entities_semantic = AsyncMock(side_effect=RuntimeError("entity failure"))

        ctx = _make_ctx(pipeline)

        with patch("server.increment_operations", return_value=True), \
             patch("server.decrement_operations"), \
             patch("server.record_tool_call"), \
             patch("server.ENTITY_EXTRACTION", True):
            result = await search_root(root_path="/root", query="test query", ctx=ctx)

        assert result["success"] is True
        assert result["chunks"]["success"] is True
        assert result["entities"]["success"] is False

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. ENTITY_EXTRACTION=false
# ---------------------------------------------------------------------------


def test_search_root_entity_extraction_disabled():
    """With ENTITY_EXTRACTION=false, entities and communities return empty results
    with a warning; chunks channel still runs and the call still succeeds."""

    async def _run():
        from server import search_root

        pipeline = _make_pipeline()
        ctx = _make_ctx(pipeline)

        with patch("server.increment_operations", return_value=True), \
             patch("server.decrement_operations"), \
             patch("server.record_tool_call"), \
             patch("server.ENTITY_EXTRACTION", False):
            result = await search_root(root_path="/root", query="test query", ctx=ctx)

        assert result["success"] is True
        assert result["chunks"]["success"] is True
        assert result["entities"]["results"] == []
        assert "warning" in result["entities"]
        assert result["communities"]["results"] == []
        assert "warning" in result["communities"]
        # entities/communities channels bypass the real pipeline when disabled
        pipeline.search_entities_semantic.assert_not_called()
        pipeline.search_global.assert_not_called()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. Counter leak guard — app_ctx access is inside the try/finally
# ---------------------------------------------------------------------------


def test_search_root_decrement_called_on_inner_exception():
    """decrement_operations is called via finally even when an exception fires
    inside the try block after increment_operations — verifying the counter-leak
    fix from ADR-0052 review (app_ctx/pipeline/timeout now live inside try)."""

    async def _run():
        from server import search_root

        pipeline = _make_pipeline()
        ctx = _make_ctx(pipeline)

        decrement = MagicMock()
        # Force an exception inside the try block by making asyncio.ensure_future raise.
        with patch("server.increment_operations", return_value=True), \
             patch("server.decrement_operations", decrement), \
             patch("server.record_tool_call"), \
             patch("server.ENTITY_EXTRACTION", False), \
             patch("asyncio.ensure_future", side_effect=RuntimeError("task creation failure")):
            result = await search_root(root_path="/root", query="test query", ctx=ctx)

        assert result["success"] is False
        decrement.assert_called_once()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 6. root_path filter — base_dirs only (no root_path kwarg passed to pipeline)
# ---------------------------------------------------------------------------


def test_search_root_chunks_channel_does_not_pass_root_path_to_pipeline():
    """_chunks_channel must call pipeline.search with base_dirs only, not root_path,
    per ADR-0052 requirement (avoids engaging root_id Qdrant filter)."""

    async def _run():
        from server import search_root
        from vectors.rag import RAGResponse

        pipeline = _make_pipeline()
        ctx = _make_ctx(pipeline)

        with patch("server.increment_operations", return_value=True), \
             patch("server.decrement_operations"), \
             patch("server.record_tool_call"), \
             patch("server.ENTITY_EXTRACTION", False):
            await search_root(root_path="/root", query="test", ctx=ctx)

        call_kwargs = pipeline.search.call_args.kwargs
        assert "root_path" not in call_kwargs, (
            "_chunks_channel must not pass root_path= to pipeline.search"
        )
        assert call_kwargs.get("base_dirs") == ["/root"]

    asyncio.run(_run())
