"""Tests for ExtractionCache (LRU, key collisions, hit/miss)."""

import pytest
from vectors.extraction_cache import ExtractionCache, PROMPT_VERSION


def _make_cache(max_size=None) -> ExtractionCache:
    cache = ExtractionCache()
    if max_size is not None:
        cache._MAX_SIZE = max_size
    return cache


def _payload(tag: str = "a") -> dict:
    return {"entities": [], "edges": [], "tag": tag}


# ---------------------------------------------------------------------------
# Basic hit / miss
# ---------------------------------------------------------------------------


def test_miss_on_empty_cache():
    cache = _make_cache()
    assert cache.get("model-a", "abc123") is None


def test_set_then_hit():
    cache = _make_cache()
    p = _payload("hit")
    cache.set("model-a", "abc123", p)
    result = cache.get("model-a", "abc123")
    assert result is p


def test_miss_wrong_chunk_hash():
    cache = _make_cache()
    cache.set("model-a", "hash1", _payload())
    assert cache.get("model-a", "hash2") is None


# ---------------------------------------------------------------------------
# Key collision: different models → different keys
# ---------------------------------------------------------------------------


def test_different_models_do_not_share_entries():
    cache = _make_cache()
    p1 = _payload("model1-result")
    p2 = _payload("model2-result")
    cache.set("model-a", "same_hash", p1)
    cache.set("model-b", "same_hash", p2)

    assert cache.get("model-a", "same_hash") is p1
    assert cache.get("model-b", "same_hash") is p2
    assert cache.size() == 2


def test_same_model_same_hash_overwrites():
    cache = _make_cache()
    p1 = _payload("first")
    p2 = _payload("second")
    cache.set("model-a", "hash1", p1)
    cache.set("model-a", "hash1", p2)
    # Second write should overwrite
    assert cache.get("model-a", "hash1") is p2
    assert cache.size() == 1


# ---------------------------------------------------------------------------
# LRU eviction at max size
# ---------------------------------------------------------------------------


def test_lru_eviction_removes_oldest():
    cache = _make_cache(max_size=3)
    cache.set("m", "h1", _payload("1"))
    cache.set("m", "h2", _payload("2"))
    cache.set("m", "h3", _payload("3"))
    assert cache.size() == 3

    # Insert a 4th entry → h1 (oldest) should be evicted
    cache.set("m", "h4", _payload("4"))
    assert cache.size() == 3
    assert cache.get("m", "h1") is None  # evicted
    assert cache.get("m", "h2") is not None
    assert cache.get("m", "h3") is not None
    assert cache.get("m", "h4") is not None


def test_lru_access_refreshes_order():
    cache = _make_cache(max_size=3)
    cache.set("m", "h1", _payload("1"))
    cache.set("m", "h2", _payload("2"))
    cache.set("m", "h3", _payload("3"))

    # Access h1 so it becomes most-recently-used
    cache.get("m", "h1")

    # Insert h4 → h2 (now oldest) should be evicted, not h1
    cache.set("m", "h4", _payload("4"))
    assert cache.size() == 3
    assert cache.get("m", "h1") is not None  # still present
    assert cache.get("m", "h2") is None       # evicted
    assert cache.get("m", "h3") is not None
    assert cache.get("m", "h4") is not None


# ---------------------------------------------------------------------------
# size()
# ---------------------------------------------------------------------------


def test_size_reflects_contents():
    cache = _make_cache()
    assert cache.size() == 0
    cache.set("m", "h1", _payload())
    assert cache.size() == 1
    cache.set("m", "h2", _payload())
    assert cache.size() == 2
    # Overwrite should NOT increase size
    cache.set("m", "h1", _payload())
    assert cache.size() == 2


# ---------------------------------------------------------------------------
# PROMPT_VERSION is embedded in key (different version → miss)
# ---------------------------------------------------------------------------


def test_prompt_version_in_key():
    """Changing PROMPT_VERSION constant should effectively invalidate cache keys."""
    import vectors.extraction_cache as _mod
    original = _mod.PROMPT_VERSION
    cache = _make_cache()
    cache.set("m", "h1", _payload("v1-result"))

    try:
        _mod.PROMPT_VERSION = "v999"
        # The cache stores the key with the old version; new key won't match
        result = cache.get("m", "h1")
        # Should be None because key now uses v999, but stored key used original
        assert result is None
    finally:
        _mod.PROMPT_VERSION = original
