"""Tests for indexed_at absent fallback and oldest_indexed_at producer (ticket 04)."""

import asyncio
import datetime
import time
from vectors.metadata import (
    coerce_epoch_seconds,
    oldest_indexed_at,
    build_chunk_payload_v2,
    extract_file_record_from_payload,
)
from vectors.testing import InMemoryVectorStore
from vectors.rag import RAGPipeline
from vectors.config import Config


# ---------------------------------------------------------------------------
# coerce_epoch_seconds tests
# ---------------------------------------------------------------------------

def test_coerce_epoch_seconds_float_passthrough():
    """Float values are passed through unchanged."""
    assert coerce_epoch_seconds(1700000000.5) == 1700000000.5


def test_coerce_epoch_seconds_int_to_float():
    """Int values are converted to float."""
    assert coerce_epoch_seconds(1700000000) == 1700000000.0


def test_coerce_epoch_seconds_iso_string_with_z():
    """ISO-8601 string with trailing Z is parsed correctly."""
    result = coerce_epoch_seconds("2024-01-15T08:00:00Z")
    expected = datetime.datetime(2024, 1, 15, 8, 0, 0, tzinfo=datetime.timezone.utc).timestamp()
    assert result == expected


def test_coerce_epoch_seconds_iso_string_with_offset():
    """ISO-8601 string with +00:00 offset is parsed correctly."""
    result = coerce_epoch_seconds("2024-01-15T08:00:00+00:00")
    expected = datetime.datetime(2024, 1, 15, 8, 0, 0, tzinfo=datetime.timezone.utc).timestamp()
    assert result == expected


def test_coerce_epoch_seconds_naive_iso_treated_as_utc():
    """Naive ISO-8601 string (no tzinfo) is treated as UTC."""
    result = coerce_epoch_seconds("2024-01-15T08:00:00")
    expected = datetime.datetime(2024, 1, 15, 8, 0, 0, tzinfo=datetime.timezone.utc).timestamp()
    assert result == expected


def test_coerce_epoch_seconds_none_input():
    """None input returns None."""
    assert coerce_epoch_seconds(None) is None


def test_coerce_epoch_seconds_garbage_string():
    """Unparseable string returns None."""
    assert coerce_epoch_seconds("not-a-date") is None


def test_coerce_epoch_seconds_true_is_not_number():
    """Boolean True is not treated as a number."""
    assert coerce_epoch_seconds(True) is None


def test_coerce_epoch_seconds_false_is_not_number():
    """Boolean False is not treated as a number."""
    assert coerce_epoch_seconds(False) is None


def test_coerce_epoch_seconds_empty_string():
    """Empty string returns None."""
    assert coerce_epoch_seconds("") is None


# ---------------------------------------------------------------------------
# oldest_indexed_at tests
# ---------------------------------------------------------------------------

def test_oldest_indexed_at_empty_list():
    """Empty list returns None."""
    assert oldest_indexed_at([]) is None


def test_oldest_indexed_at_single_record():
    """Single record returns its timestamp."""
    records = [{"indexed_at": 1700000000.0}]
    assert oldest_indexed_at(records) == 1700000000.0


def test_oldest_indexed_at_returns_minimum():
    """Returns the oldest (minimum) timestamp from multiple records."""
    records = [
        {"indexed_at": 1700000000.0},
        {"indexed_at": 1600000000.0},
        {"indexed_at": 1800000000.0},
    ]
    assert oldest_indexed_at(records) == 1600000000.0


def test_oldest_indexed_at_mixed_presence_returns_none():
    """Fix 2: Mixed presence (some with timestamps, some without) returns None (conservative fallback per ADR-0072)."""
    records = [
        {"indexed_at": 1700000000.0},
        {"indexed_at": None},
        {"indexed_at": "invalid"},
    ]
    # Conservative fallback: ANY missing/unparseable timestamp means return None
    assert oldest_indexed_at(records) is None


def test_oldest_indexed_at_all_invalid():
    """All invalid timestamps returns None."""
    records = [
        {"indexed_at": None},
        {"indexed_at": "invalid"},
    ]
    assert oldest_indexed_at(records) is None


# ---------------------------------------------------------------------------
# extract_file_record_from_payload tests for indexed_at field
# ---------------------------------------------------------------------------

def test_extract_file_record_includes_indexed_at():
    """extract_file_record_from_payload includes indexed_at field."""
    payload = build_chunk_payload_v2(
        file_path="/tmp/test.py",
        file_name="test.py",
        chunk={"chunk_id": 0, "text": "print('hi')", "start_char": 0, "end_char": 11},
        file_metadata={"file_type": "python"},
        root_path="/tmp",
        indexed_at=1700000000.0,
    )
    record = extract_file_record_from_payload(payload)
    assert record["indexed_at"] == 1700000000.0


def test_extract_file_record_indexed_at_fallback_to_indexed_time():
    """indexed_at falls back to indexed_time if absent in payload."""
    # Test direct fallback: when payload has indexed_time but no indexed_at
    payload_no_indexed_at = {
        "file_path": "/tmp/test.py",
        "path_key": "/tmp/test.py",
        "file_name": "test.py",
        "indexed_time": 1600000000.0,
        "metadata_version": 2,
    }
    record = extract_file_record_from_payload(payload_no_indexed_at)
    assert record["indexed_at"] == 1600000000.0


# ---------------------------------------------------------------------------
# InMemoryVectorStore oldest_indexed_at integration tests
# ---------------------------------------------------------------------------

def test_inmemory_vectorstore_oldest_indexed_at():
    """InMemoryVectorStore.get_file_metadata_summary includes oldest_indexed_at."""
    async def _run():
        store = InMemoryVectorStore(vector_size=384)
        await store.initialize()
        
        before = time.time()
        await store.upsert_chunks(
            file_path="/tmp/file1.py",
            file_name="file1.py",
            chunks=[{"chunk_id": 0, "text": "content1", "start_char": 0, "end_char": 8}],
            embeddings=[[0.1] * 384],
            file_metadata={"file_type": "python"},
            root_path="/tmp",
        )
        await store.upsert_chunks(
            file_path="/tmp/file2.py",
            file_name="file2.py",
            chunks=[{"chunk_id": 0, "text": "content2", "start_char": 0, "end_char": 8}],
            embeddings=[[0.2] * 384],
            file_metadata={"file_type": "python"},
            root_path="/tmp",
        )
        after = time.time()
        
        summary = await store.get_file_metadata_summary()
        assert "oldest_indexed_at" in summary
        assert summary["oldest_indexed_at"] is not None
        # The oldest_indexed_at should be between before and after (within reason)
        assert before - 1 <= summary["oldest_indexed_at"] <= after + 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# RAGPipeline get_indexing_status staleness tests (isolated with fresh store)
# ---------------------------------------------------------------------------

def test_indexing_status_no_timestamps_treated_as_stale():
    """Migration scenario: root with file_count > 0 but no indexed_at is stale."""
    async def _run():
        store = InMemoryVectorStore(vector_size=384)
        await store.initialize()
        
        # Manually inject a record without indexed_at to simulate pre-upgrade metadata
        unique_path = "/tmp/test_legacy_migration"
        store._points.append({
            "id": "test-point-legacy",
            "vector": [0.1] * 384,
            "payload": {
                "file_path": unique_path,
                "path_key": unique_path,
                "file_name": "legacy.py",
                "chunk_id": 0,
                "chunk_text": "print('legacy')",
                "start_char": 0,
                "end_char": 14,
                "root_path": "/tmp",
                "root_id": "/tmp",
                "file_type": "python",
                "extension": ".py",
                "metadata_version": 1,  # legacy
                # Note: no indexed_at field
            },
        })
        
        config = Config()
        config.reconcile_on_startup = False  # Disable reconciliation for isolation
        pipeline = RAGPipeline(config=config, vector_store=store)
        await pipeline.initialize()
        
        try:
            result = await pipeline.get_indexing_status(root_path="/tmp")
            # Status could be "indexed" or "legacy_metadata" depending on metadata_version
            assert result["status"] in ("indexed", "legacy_metadata", "partially_indexed")
            assert result["metadata"]["file_count"] > 0
            # Should be marked as stale due to missing timestamp
            assert "stale_since" in result
            assert result["stale_since"] is not None
            assert result["staleness_message"] == "Index has no timestamp metadata; treating as stale for safety"
            # Verify stale_since is close to now (fallback branch uses current time)
            stale_since = result["stale_since"]
            parsed = datetime.datetime.strptime(stale_since, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
            assert abs(parsed.timestamp() - time.time()) < 5
        finally:
            await pipeline.close()

    asyncio.run(_run())


def test_indexing_status_recent_timestamp_not_stale():
    """Normal scenario: root with recent indexed_at is NOT stale."""
    async def _run():
        store = InMemoryVectorStore(vector_size=384)
        await store.initialize()
        
        await store.upsert_chunks(
            file_path="/tmp/recent_test.py",
            file_name="recent_test.py",
            chunks=[{"chunk_id": 0, "text": "print('recent')", "start_char": 0, "end_char": 14}],
            embeddings=[[0.1] * 384],
            file_metadata={"file_type": "python"},
            root_path="/tmp",
        )
        
        config = Config()
        config.reconcile_on_startup = False  # Disable reconciliation for isolation
        pipeline = RAGPipeline(config=config, vector_store=store)
        await pipeline.initialize()
        
        try:
            result = await pipeline.get_indexing_status(root_path="/tmp")
            assert result["status"] == "indexed"
            # Recent index should not be stale
            assert "stale_since" not in result
            assert "staleness_message" not in result
        finally:
            await pipeline.close()

    asyncio.run(_run())


def test_indexing_status_old_timestamp_is_stale():
    """Normal scenario: root with old indexed_at IS stale."""
    async def _run():
        store = InMemoryVectorStore(vector_size=384)
        await store.initialize()
        
        # Inject a record with an old timestamp (30 days ago)
        old_timestamp = time.time() - (30 * 24 * 3600)  # 30 days ago
        unique_path = "/tmp/old_test"
        store._points.append({
            "id": "test-point-old",
            "vector": [0.1] * 384,
            "payload": {
                "file_path": unique_path,
                "path_key": unique_path,
                "file_name": "old.py",
                "chunk_id": 0,
                "chunk_text": "print('old')",
                "start_char": 0,
                "end_char": 11,
                "root_path": "/tmp",
                "root_id": "/tmp",
                "file_type": "python",
                "extension": ".py",
                "metadata_version": 2,
                "indexed_at": old_timestamp,
            },
        })
        
        config = Config()
        config.reconcile_on_startup = False  # Disable reconciliation for isolation
        config.stale_index_threshold_days = 7  # Default is 7 days
        pipeline = RAGPipeline(config=config, vector_store=store)
        await pipeline.initialize()
        
        try:
            result = await pipeline.get_indexing_status(root_path="/tmp")
            assert result["status"] == "indexed"
            assert "stale_since" in result
            assert result["stale_since"] is not None
            # Verify stale_since encodes the chunk's timestamp, not current time
            expected_stale_since = datetime.datetime.fromtimestamp(old_timestamp, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            assert result["stale_since"] == expected_stale_since
            assert "stale" in result["staleness_message"].lower()
            # The message should mention the age (around 30 days)
            assert "days ago" in result["staleness_message"]
        finally:
            await pipeline.close()

    asyncio.run(_run())


def test_indexing_status_zero_file_count_not_stale():
    """Root with file_count == 0 is not_found, never stale."""
    async def _run():
        store = InMemoryVectorStore(vector_size=384)
        await store.initialize()
        
        config = Config()
        config.reconcile_on_startup = False  # Disable reconciliation for isolation
        pipeline = RAGPipeline(config=config, vector_store=store)
        await pipeline.initialize()
        
        try:
            result = await pipeline.get_indexing_status(root_path="/tmp/nonexistent")
            assert result["status"] == "not_found"
            assert "stale_since" not in result
            assert "staleness_message" not in result
        finally:
            await pipeline.close()

    asyncio.run(_run())


def test_indexing_status_scan_truncated_flag():
    """Fix 1: When metadata scan is truncated, oldest_indexed_at_truncated flag is set."""
    async def _run():
        store = InMemoryVectorStore(vector_size=384)
        await store.initialize()
        
        # Inject a record with a recent timestamp
        recent_timestamp = time.time()
        unique_path = "/tmp/truncated_test"
        store._points.append({
            "id": "test-point-truncated",
            "vector": [0.1] * 384,
            "payload": {
                "file_path": unique_path,
                "path_key": unique_path,
                "file_name": "truncated.py",
                "chunk_id": 0,
                "chunk_text": "print('truncated')",
                "start_char": 0,
                "end_char": 17,
                "root_path": "/tmp",
                "root_id": "/tmp",
                "file_type": "python",
                "extension": ".py",
                "metadata_version": 2,
                "indexed_at": recent_timestamp,
            },
        })
        
        # Monkeypatch get_file_metadata_summary to return scan_truncated=True
        original_get_summary = store.get_file_metadata_summary
        async def patched_get_summary(base_path=None):
            result = await original_get_summary(base_path)
            result["scan_truncated"] = True
            result["partial"] = True
            return result
        store.get_file_metadata_summary = patched_get_summary
        
        config = Config()
        config.reconcile_on_startup = False
        pipeline = RAGPipeline(config=config, vector_store=store)
        await pipeline.initialize()
        
        try:
            result = await pipeline.get_indexing_status(root_path="/tmp")
            # The truncation flag should be set
            assert result.get("oldest_indexed_at_truncated") is True
        finally:
            await pipeline.close()

    asyncio.run(_run())


def test_indexing_status_mixed_timestamps_treated_as_stale():
    """Fix 2: Mixed presence (some files with timestamps, some without) is treated as stale."""
    async def _run():
        store = InMemoryVectorStore(vector_size=384)
        await store.initialize()
        
        # Inject two records: one with timestamp, one without
        recent_timestamp = time.time()
        store._points.append({
            "id": "test-point-with-ts",
            "vector": [0.1] * 384,
            "payload": {
                "file_path": "/tmp/with_timestamp.py",
                "path_key": "/tmp/with_timestamp.py",
                "file_name": "with_timestamp.py",
                "chunk_id": 0,
                "chunk_text": "print('has ts')",
                "start_char": 0,
                "end_char": 14,
                "root_path": "/tmp",
                "root_id": "/tmp",
                "file_type": "python",
                "extension": ".py",
                "metadata_version": 2,
                "indexed_at": recent_timestamp,
            },
        })
        store._points.append({
            "id": "test-point-no-ts",
            "vector": [0.1] * 384,
            "payload": {
                "file_path": "/tmp/without_timestamp.py",
                "path_key": "/tmp/without_timestamp.py",
                "file_name": "without_timestamp.py",
                "chunk_id": 0,
                "chunk_text": "print('no ts')",
                "start_char": 0,
                "end_char": 13,
                "root_path": "/tmp",
                "root_id": "/tmp",
                "file_type": "python",
                "extension": ".py",
                "metadata_version": 2,
                # No indexed_at field
            },
        })
        
        config = Config()
        config.reconcile_on_startup = False
        pipeline = RAGPipeline(config=config, vector_store=store)
        await pipeline.initialize()
        
        try:
            result = await pipeline.get_indexing_status(root_path="/tmp")
            # Should be marked as stale due to mixed timestamps (conservative fallback)
            assert "stale_since" in result
            assert result["stale_since"] is not None
            assert "staleness_message" in result
            assert "no timestamp" in result["staleness_message"].lower()
        finally:
            await pipeline.close()

    asyncio.run(_run())
