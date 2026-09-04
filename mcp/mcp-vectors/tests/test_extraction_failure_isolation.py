"""Tests that extraction timeouts are counted separately from other failures (ADR-0069)."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from vectors.config import Config
from vectors.rag import RAGPipeline

ROOT_ID = "root-1"


def _make_pipeline() -> RAGPipeline:
    config = Config()
    config.extraction_timeout_seconds = 0.05
    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.config = config
    pipeline.lm_client = object()
    pipeline._extraction_cache = None
    pipeline._graph_stats = {}
    return pipeline


def _install_failing_extractor(monkeypatch, exc: BaseException | None, hang: bool = False):
    class FakeExtractor:
        def __init__(self, *args, **kwargs):
            pass

        async def extract_file(self, *args, **kwargs):
            if hang:
                await asyncio.sleep(10)
            raise exc

    monkeypatch.setattr("vectors.rag.EntityExtractor", FakeExtractor)


def _run(pipeline: RAGPipeline) -> None:
    asyncio.run(
        pipeline._extract_and_merge(Path("/tmp/example.py"), object(), ROOT_ID, "example.py")
    )


def test_timeout_increments_only_timeout_counter(monkeypatch, caplog):
    pipeline = _make_pipeline()
    _install_failing_extractor(monkeypatch, None, hang=True)

    with caplog.at_level(logging.WARNING, logger="vectors.rag"):
        _run(pipeline)

    stats = pipeline._graph_stats[ROOT_ID]
    assert stats.extraction_timeouts == 1
    assert stats.extraction_other_failures == 0
    assert stats.files_pending_extraction == 0
    assert any("timed out" in r.getMessage() for r in caplog.records)


def test_non_timeout_exception_increments_only_other_counter(monkeypatch, caplog):
    pipeline = _make_pipeline()
    _install_failing_extractor(monkeypatch, ValueError("bad parse"))

    with caplog.at_level(logging.WARNING, logger="vectors.rag"):
        _run(pipeline)

    stats = pipeline._graph_stats[ROOT_ID]
    assert stats.extraction_other_failures == 1
    assert stats.extraction_timeouts == 0
    assert stats.files_pending_extraction == 0
    assert any("ValueError: bad parse" in r.getMessage() for r in caplog.records)


def test_get_graph_stats_reports_both_counters(monkeypatch):
    pipeline = _make_pipeline()
    _install_failing_extractor(monkeypatch, ValueError("bad parse"))
    _run(pipeline)
    _install_failing_extractor(monkeypatch, None, hang=True)
    _run(pipeline)

    reported = pipeline.get_graph_stats(ROOT_ID)
    assert reported["extraction_timeouts"] == 1
    assert reported["extraction_other_failures"] == 1
