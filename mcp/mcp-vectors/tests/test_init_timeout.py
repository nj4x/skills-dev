"""Tests for the RAG pipeline initialization timeout bound (ADR-0071)."""
from __future__ import annotations

import asyncio
import logging
import re

import pytest

from vectors.config import Config
from vectors.rag import RAGPipeline


def _make_pipeline(init_timeout_seconds: float) -> RAGPipeline:
    config = Config()
    config.init_timeout_seconds = init_timeout_seconds
    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.config = config
    pipeline._initialized = False
    pipeline._init_phase = "not started"
    return pipeline


def test_initialize_timeout_propagates_and_logs_elapsed(caplog):
    pipeline = _make_pipeline(init_timeout_seconds=0.05)

    async def slow_impl():
        await asyncio.sleep(10)

    pipeline._initialize_impl = slow_impl

    async def _run():
        with pytest.raises(asyncio.TimeoutError):
            await pipeline.initialize()

    with caplog.at_level(logging.ERROR, logger="vectors.rag"):
        asyncio.run(_run())

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any(
        re.search(r"not started exceeded 0\.05s timeout \(elapsed \d+\.\ds\)", m)
        for m in messages
    ), messages


def test_initialize_timeout_message_identifies_stalled_component(caplog):
    """ADR-0071: timeout error must name the component that stalled, not just the pipeline."""
    pipeline = _make_pipeline(init_timeout_seconds=0.05)

    async def slow_impl():
        pipeline._init_phase = "LM Studio model loading"
        await asyncio.sleep(10)

    pipeline._initialize_impl = slow_impl

    async def _run():
        with pytest.raises(asyncio.TimeoutError):
            await pipeline.initialize()

    with caplog.at_level(logging.ERROR, logger="vectors.rag"):
        asyncio.run(_run())

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any("LM Studio model loading exceeded 0.05s timeout" in m for m in messages), messages


def test_initialize_happy_path_logs_no_error(caplog):
    pipeline = _make_pipeline(init_timeout_seconds=60)

    async def fast_impl():
        pipeline._initialized = True

    pipeline._initialize_impl = fast_impl

    with caplog.at_level(logging.ERROR, logger="vectors.rag"):
        asyncio.run(pipeline.initialize())

    assert pipeline._initialized is True
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR] == []
