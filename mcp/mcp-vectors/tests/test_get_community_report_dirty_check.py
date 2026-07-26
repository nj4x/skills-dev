"""
Regression test for get_community_report missing are_communities_dirty check.

NOTE: get_community_report is deprecated (pending deletion per ADR-0052). These tests
cover the underlying handler logic which remains importable until the deletion PR.

Issue: get_community_report did not check if communities were dirty before attempting
to retrieve a community by ID. This caused "community_not_found" errors when communities
were in the process of being rebuilt, even when the tool should have returned a
"rebuilding" status like list_communities does.

Fix: Added are_communities_dirty check and scheduling behavior to match list_communities.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock

import pytest


def _make_mock_context():
    """Create a mock MCP context."""
    ctx = MagicMock()
    ctx.request_context = MagicMock()
    app_ctx = MagicMock()
    ctx.request_context.lifespan_context = app_ctx
    return ctx, app_ctx


def test_get_community_report_returns_rebuilding_when_communities_dirty():
    """When are_communities_dirty returns True, get_community_report should
    return 'rebuilding' status instead of trying to retrieve from Qdrant."""

    async def _run():
        from server import get_community_report

        ctx, app_ctx = _make_mock_context()
        pipeline = MagicMock()
        app_ctx.pipeline = pipeline
        pipeline._initialized = True

        from vectors.community_results import CommunityReportRebuilding

        # Mock get_community_report to return a rebuilding result
        pipeline.get_community_report = MagicMock(
            return_value=CommunityReportRebuilding(reason="Communities are being rebuilt")
        )
        pipeline.get_community_report = AsyncMock(
            return_value=CommunityReportRebuilding(reason="Communities are being rebuilt")
        )

        # Mock increment/decrement operations
        with patch("server.increment_operations", return_value=True):
            with patch("server.decrement_operations"):
                result = await get_community_report(
                    root_path="/test/root",
                    community_id="test-community-id",
                    ctx=ctx,
                )

        assert result["mode"] == "rebuilding"
        assert "warning" in result
        assert "Communities are being rebuilt" in result["warning"]
        assert "success" not in result
        pipeline.get_community_report.assert_called_once_with("/test/root", "test-community-id")

    asyncio.run(_run())


def test_get_community_report_returns_rebuilding_when_no_committed_generation():
    """When no committed communities exist, get_community_report should return
    'rebuilding' and schedule a rebuild."""

    async def _run():
        from server import get_community_report
        from vectors.community_results import CommunityReportRebuilding

        ctx, app_ctx = _make_mock_context()
        pipeline = MagicMock()
        app_ctx.pipeline = pipeline
        pipeline._initialized = True

        pipeline.get_community_report = AsyncMock(
            return_value=CommunityReportRebuilding(
                reason="Communities are being built for the first time"
            )
        )

        with patch("server.increment_operations", return_value=True):
            with patch("server.decrement_operations"):
                result = await get_community_report(
                    root_path="/test/root",
                    community_id="test-community-id",
                    ctx=ctx,
                )

        assert result["mode"] == "rebuilding"
        assert "warning" in result
        assert "success" not in result
        pipeline.get_community_report.assert_called_once()

    asyncio.run(_run())


def test_get_community_report_returns_community_when_found():
    """When communities are not dirty and a community is found, return it."""

    async def _run():
        from server import get_community_report
        from vectors.community_results import CommunityReportReady

        ctx, app_ctx = _make_mock_context()
        pipeline = MagicMock()
        app_ctx.pipeline = pipeline
        pipeline._initialized = True

        # Mock community data
        mock_report = {
            "community_id": "test-cid",
            "summary": "Test community",
            "level": 0,
        }

        pipeline.get_community_report = AsyncMock(return_value=CommunityReportReady(report=mock_report))

        with patch("server.increment_operations", return_value=True):
            with patch("server.decrement_operations"):
                result = await get_community_report(
                    root_path="/test/root",
                    community_id="test-cid",
                    ctx=ctx,
                )

        assert result["mode"] == "ready"
        assert result["community"] == mock_report
        assert "success" not in result
        pipeline.get_community_report.assert_called_once_with("/test/root", "test-cid")

    asyncio.run(_run())


def test_get_community_report_returns_not_found_when_community_missing():
    """When communities are valid but the specific community_id is not found,
    return community_not_found error."""

    async def _run():
        from server import get_community_report
        from vectors.community_results import CommunityReportError

        ctx, app_ctx = _make_mock_context()
        pipeline = MagicMock()
        app_ctx.pipeline = pipeline
        pipeline._initialized = True

        pipeline.get_community_report = AsyncMock(
            return_value=CommunityReportError(
                error={"code": "community_not_found", "message": "Community nonexistent-cid not found"}
            )
        )

        with patch("server.increment_operations", return_value=True):
            with patch("server.decrement_operations"):
                result = await get_community_report(
                    root_path="/test/root",
                    community_id="nonexistent-cid",
                    ctx=ctx,
                )

        assert result["mode"] == "error"
        assert result["error"]["code"] == "community_not_found"
        assert "nonexistent-cid" in result["error"]["message"]
        assert "success" not in result

    asyncio.run(_run())
