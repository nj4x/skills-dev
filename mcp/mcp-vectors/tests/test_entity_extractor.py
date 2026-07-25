"""Tests for EntityExtractor, _parse_extraction_result, and annotate_chunks."""

import asyncio
import hashlib
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest

from vectors.entity_extractor import (
    Entity,
    Edge,
    EntityMap,
    EntityExtractor,
    _build_batch_prompt,
    _parse_extraction_result,
    annotate_chunks,
)
from vectors.extraction_cache import ExtractionCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parsed_doc(texts: list[str]):
    """Build a minimal fake ParsedDocument with dict-based chunks."""

    @dataclass
    class FakeDoc:
        chunks: list[dict] = field(default_factory=list)

    doc = FakeDoc()
    doc.chunks = [{"chunk_id": i, "text": t, "start_char": 0, "end_char": len(t)} for i, t in enumerate(texts)]
    return doc


def _make_lm_client(response: str = "") -> MagicMock:
    """Return a mock LMStudioClient with generate_response_with_history pre-wired."""
    client = MagicMock()
    client._llm_model = "test-model"
    client.generate_response_with_history = AsyncMock(return_value=response)
    client.generate_response = AsyncMock(return_value="summary text")
    return client


SAMPLE_EXTRACTION = (
    '("entity"<|>Alice<|>person<|>A software engineer<|>1)##'
    '("entity"<|>Python<|>technology<|>A programming language<|>1)##'
    '("relationship"<|>Alice<|>Python<|>Alice uses Python<|>8)##'
    "<|COMPLETE|>"
)


# ---------------------------------------------------------------------------
# _parse_extraction_result
# ---------------------------------------------------------------------------


class TestParseExtractionResult:
    def test_parses_entities(self):
        entities, edges = _parse_extraction_result(SAMPLE_EXTRACTION)
        assert len(entities) == 2
        names = {e.name for e in entities}
        assert names == {"Alice", "Python"}

    def test_parses_edges(self):
        entities, edges = _parse_extraction_result(SAMPLE_EXTRACTION)
        assert len(edges) == 1
        assert edges[0].source == "Alice"
        assert edges[0].target == "Python"
        assert edges[0].weight == 8.0

    def test_entity_fields(self):
        entities, _ = _parse_extraction_result(SAMPLE_EXTRACTION)
        alice = next(e for e in entities if e.name == "Alice")
        assert alice.type == "person"
        assert alice.description == "A software engineer"

    def test_skips_malformed_records(self):
        raw = (
            "##"
            "this is garbage##"
            '("entity"<|>OnlyTwoFields<|>)##'
            '("entity"<|>Good<|>concept<|>Valid entity)##'
            '("relationship"<|>A<|>B<|>missing_weight)##'
        )
        entities, edges = _parse_extraction_result(raw)
        assert len(entities) == 1
        assert entities[0].name == "Good"
        assert len(edges) == 0

    def test_empty_string_returns_empty(self):
        entities, edges = _parse_extraction_result("")
        assert entities == []
        assert edges == []

    def test_non_numeric_weight_skipped(self):
        raw = '("relationship"<|>A<|>B<|>desc<|>NOT_A_NUMBER)##'
        _, edges = _parse_extraction_result(raw)
        assert len(edges) == 0

    def test_complete_marker_is_ignored(self):
        raw = '("entity"<|>X<|>concept<|>desc)##<|COMPLETE|>'
        entities, _ = _parse_extraction_result(raw)
        assert len(entities) == 1
        assert entities[0].name == "X"

    def test_extra_whitespace_around_delimiters(self):
        raw = '( "entity" <|> Trimmed <|> concept <|> Spaces around delimiters )##'
        entities, _ = _parse_extraction_result(raw)
        assert len(entities) == 1
        assert entities[0].name == "Trimmed"


# ---------------------------------------------------------------------------
# annotate_chunks
# ---------------------------------------------------------------------------


class TestAnnotateChunks:
    def test_basic_annotation(self):
        doc = _make_parsed_doc(["chunk zero text", "chunk one text"])
        e1 = Entity(name="Alpha", type="concept", description="d", chunk_ids=[0])
        e2 = Entity(name="Beta", type="function", description="d", chunk_ids=[1])
        e3 = Entity(name="Gamma", type="class", description="d", chunk_ids=[0, 1])
        entity_map = EntityMap(entities=[e1, e2, e3])

        annotate_chunks(doc, entity_map)

        assert set(doc.chunks[0]["entity_names"]) == {"Alpha", "Gamma"}
        assert set(doc.chunks[1]["entity_names"]) == {"Beta", "Gamma"}

    def test_chunk_with_no_entities_gets_empty_list(self):
        doc = _make_parsed_doc(["a", "b", "c"])
        e1 = Entity(name="X", type="concept", description="d", chunk_ids=[0])
        entity_map = EntityMap(entities=[e1])

        annotate_chunks(doc, entity_map)

        assert doc.chunks[1]["entity_names"] == []
        assert doc.chunks[2]["entity_names"] == []

    def test_returns_same_doc(self):
        doc = _make_parsed_doc(["text"])
        result = annotate_chunks(doc, EntityMap())
        assert result is doc

    def test_empty_entity_map(self):
        doc = _make_parsed_doc(["some text"])
        annotate_chunks(doc, EntityMap())
        assert doc.chunks[0]["entity_names"] == []

    def test_out_of_range_chunk_ids_ignored(self):
        """Entity with chunk_id pointing beyond doc.chunks should not raise."""
        doc = _make_parsed_doc(["only one chunk"])
        e = Entity(name="X", type="concept", description="d", chunk_ids=[999])
        entity_map = EntityMap(entities=[e])
        # Should not raise; chunk 999 does not exist in doc
        annotate_chunks(doc, entity_map)
        assert doc.chunks[0]["entity_names"] == []


# ---------------------------------------------------------------------------
# EntityExtractor — unit tests with mocked LLM
# ---------------------------------------------------------------------------


class TestEntityExtractorExtractChunk:
    def _make_extractor(self, response: str) -> EntityExtractor:
        client = _make_lm_client(response)
        cache = ExtractionCache()
        return EntityExtractor(lm_client=client, extraction_cache=cache, max_gleanings=0)

    def test_extract_chunk_returns_entities_and_edges(self):
        extractor = self._make_extractor(SAMPLE_EXTRACTION)

        async def _run():
            sem = asyncio.Semaphore(4)
            return await extractor._extract_chunk("some text", chunk_idx=0, semaphore=sem)

        entities, edges = asyncio.run(_run())
        assert len(entities) == 2
        assert len(edges) == 1

    def test_chunk_ids_stamped_correctly(self):
        extractor = self._make_extractor(SAMPLE_EXTRACTION)

        async def _run():
            sem = asyncio.Semaphore(4)
            return await extractor._extract_chunk("some text", chunk_idx=5, semaphore=sem)

        entities, _ = asyncio.run(_run())
        for e in entities:
            assert e.chunk_ids == [5]
            assert e.descriptions == [e.description]


class TestEntityExtractorCaching:
    def _make_extractor(self, response: str) -> tuple[EntityExtractor, MagicMock]:
        client = _make_lm_client(response)
        cache = ExtractionCache()
        extractor = EntityExtractor(lm_client=client, extraction_cache=cache, max_gleanings=0)
        return extractor, client

    def test_cache_hit_avoids_llm_call(self):
        extractor, client = self._make_extractor(SAMPLE_EXTRACTION)

        async def _run():
            sem = asyncio.Semaphore(4)
            await extractor._extract_chunk_cached("hello world", 0, sem)
            first_count = client.generate_response_with_history.call_count
            await extractor._extract_chunk_cached("hello world", 1, sem)
            return first_count

        first_count = asyncio.run(_run())
        # After cache hit the call count should not have increased
        assert client.generate_response_with_history.call_count == first_count

    def test_cache_miss_calls_llm(self):
        extractor, client = self._make_extractor(SAMPLE_EXTRACTION)

        async def _run():
            sem = asyncio.Semaphore(4)
            await extractor._extract_chunk_cached("text A", 0, sem)
            await extractor._extract_chunk_cached("text B", 1, sem)

        asyncio.run(_run())
        # Two distinct texts → two LLM calls
        assert client.generate_response_with_history.call_count == 2

    def test_cache_hit_restamps_chunk_ids(self):
        extractor, _ = self._make_extractor(SAMPLE_EXTRACTION)

        async def _run():
            sem = asyncio.Semaphore(4)
            await extractor._extract_chunk_cached("same text", chunk_idx=0, semaphore=sem)
            entities2, _ = await extractor._extract_chunk_cached("same text", chunk_idx=7, semaphore=sem)
            return entities2

        entities2 = asyncio.run(_run())
        for e in entities2:
            assert e.chunk_ids == [7]


# ---------------------------------------------------------------------------
# EntityExtractor._merge_entities
# ---------------------------------------------------------------------------


class TestMergeEntities:
    def _extractor(self):
        return EntityExtractor(
            lm_client=_make_lm_client(),
            extraction_cache=ExtractionCache(),
        )

    def test_deduplicates_same_name_and_type(self):
        extractor = self._extractor()
        e1 = Entity(name="Alice", type="person", description="d1", chunk_ids=[0], descriptions=["d1"])
        e2 = Entity(name="Alice", type="person", description="d2", chunk_ids=[1], descriptions=["d2"])
        merged = extractor._merge_entities([e1, e2], root_id="root")
        assert len(merged) == 1
        assert set(merged[0].chunk_ids) == {0, 1}
        assert len(merged[0].descriptions) == 2

    def test_different_types_kept_separate(self):
        extractor = self._extractor()
        e1 = Entity(name="Alice", type="person", description="d", chunk_ids=[0], descriptions=["d"])
        e2 = Entity(name="Alice", type="function", description="d2", chunk_ids=[1], descriptions=["d2"])
        merged = extractor._merge_entities([e1, e2], root_id="root")
        assert len(merged) == 2

    def test_case_insensitive_dedup(self):
        extractor = self._extractor()
        e1 = Entity(name="MyClass", type="class", description="d", chunk_ids=[0], descriptions=["d"])
        e2 = Entity(name="myclass", type="class", description="d2", chunk_ids=[1], descriptions=["d2"])
        merged = extractor._merge_entities([e1, e2], root_id="root")
        assert len(merged) == 1

    def test_root_id_scopes_dedup(self):
        """Same entity under different root_ids should remain separate merges."""
        extractor = self._extractor()
        e = Entity(name="Foo", type="concept", description="d", chunk_ids=[0], descriptions=["d"])
        m1 = extractor._merge_entities([e], root_id="root1")
        m2 = extractor._merge_entities([e], root_id="root2")
        # Each merge is independent; no cross-contamination
        assert len(m1) == 1
        assert len(m2) == 1


# ---------------------------------------------------------------------------
# _build_batch_prompt
# ---------------------------------------------------------------------------


class TestBuildBatchPrompt:
    def test_empty_list_returns_empty_string(self):
        assert _build_batch_prompt([]) == ""

    def test_single_element_contains_chunk_header(self):
        result = _build_batch_prompt(["hello world"])
        assert "=== CHUNK 1 ===" in result
        assert "hello world" in result

    def test_multiple_elements_have_sequential_headers(self):
        result = _build_batch_prompt(["alpha", "beta", "gamma"])
        assert "=== CHUNK 1 ===" in result
        assert "=== CHUNK 2 ===" in result
        assert "=== CHUNK 3 ===" in result

    def test_element_containing_old_delimiter_does_not_confuse_format(self):
        """Chunk text that contains the old '--- CHUNK 1 ---' string should
        be embedded verbatim — the new delimiter is '=== CHUNK N ===' and
        will not collide with the embedded text."""
        tricky = "See --- CHUNK 1 --- for context"
        result = _build_batch_prompt([tricky])
        # The new delimiter format is present
        assert "=== CHUNK 1 ===" in result
        # The embedded old-style marker is also present — no confusion
        assert "--- CHUNK 1 ---" in result
        # They appear as distinct substrings
        assert result.index("=== CHUNK 1 ===") != result.index("--- CHUNK 1 ---")

    def test_new_delimiter_format_used_not_old(self):
        """Regression: verify the old '--- CHUNK N ---' delimiter is gone."""
        result = _build_batch_prompt(["x", "y"])
        assert "--- CHUNK 1 ---" not in result
        assert "--- CHUNK 2 ---" not in result


# ---------------------------------------------------------------------------
# EntityExtractor._make_batches
# ---------------------------------------------------------------------------


class TestMakeBatches:
    def _extractor(self, batch_size: int = 4, max_prompt_chars: int = 99999):
        return EntityExtractor(
            lm_client=_make_lm_client(),
            extraction_cache=ExtractionCache(),
            batch_size=batch_size,
            max_prompt_chars=max_prompt_chars,
        )

    def _chunks(self, texts: list[str]) -> list[dict]:
        return [{"chunk_id": i, "text": t} for i, t in enumerate(texts)]

    def test_batch_size_1_one_batch_per_chunk(self):
        extractor = self._extractor(batch_size=1)
        chunks = self._chunks(["a", "b", "c"])
        batches = extractor._make_batches(chunks)
        assert len(batches) == 3
        for batch in batches:
            assert len(batch) == 1

    def test_batch_size_2_with_5_chunks_produces_221(self):
        extractor = self._extractor(batch_size=2, max_prompt_chars=99999)
        chunks = self._chunks(["a", "b", "c", "d", "e"])
        batches = extractor._make_batches(chunks)
        assert [len(b) for b in batches] == [2, 2, 1]

    def test_oversized_single_chunk_forms_own_batch(self):
        """A chunk whose text alone exceeds max_prompt_chars is placed in
        its own batch rather than being skipped or merged incorrectly."""
        extractor = self._extractor(batch_size=4, max_prompt_chars=10)
        long_text = "x" * 200
        chunks = self._chunks([long_text])
        batches = extractor._make_batches(chunks)
        assert len(batches) == 1
        assert batches[0][0]["text"] == long_text

    def test_oversized_single_chunk_logs_warning(self, caplog):
        """_make_batches should emit a warning when a single chunk exceeds the
        character limit."""
        import logging
        extractor = self._extractor(batch_size=4, max_prompt_chars=10)
        long_text = "y" * 500
        chunks = self._chunks([long_text])
        with caplog.at_level(logging.WARNING, logger="vectors.entity_extractor"):
            extractor._make_batches(chunks)
        assert any("oversized" in r.message for r in caplog.records)

    def test_char_limit_triggers_before_count_limit(self):
        """When combined text would exceed max_prompt_chars a new batch starts
        even though the count limit hasn't been reached."""
        # Each chunk is 6 chars; limit is 10 → batch splits after 1 chunk
        extractor = self._extractor(batch_size=10, max_prompt_chars=10)
        chunks = self._chunks(["aaaaaa", "bbbbbb", "cccccc"])
        batches = extractor._make_batches(chunks)
        # Each chunk is 6 chars which already exceeds the limit of 10, so each
        # forms its own single-element batch.
        assert len(batches) == 3
        for batch in batches:
            assert len(batch) == 1

    def test_max_prompt_chars_constructor_param_controls_split(self):
        """max_prompt_chars passed to constructor is respected over the module default."""
        extractor = self._extractor(batch_size=50, max_prompt_chars=5)
        chunks = self._chunks(["abc", "def", "ghi"])
        batches = extractor._make_batches(chunks)
        # 3+3 = 6 > 5, so each chunk forms its own batch despite batch_size=50
        assert len(batches) == 3


# ---------------------------------------------------------------------------
# EntityExtractor._extract_batch_cached (multi-chunk path)
# ---------------------------------------------------------------------------


class TestExtractBatchCached:
    def _make_extractor(self, response: str = SAMPLE_EXTRACTION):
        client = _make_lm_client(response)
        cache = ExtractionCache()
        extractor = EntityExtractor(lm_client=client, extraction_cache=cache, max_gleanings=0)
        return extractor, client

    def _chunks(self, texts: list[str], id_offset: int = 0) -> list[dict]:
        return [{"chunk_id": i + id_offset, "text": t} for i, t in enumerate(texts)]

    def test_cache_miss_calls_llm_and_returns_entities(self):
        extractor, client = self._make_extractor()
        chunks = self._chunks(["chunk alpha", "chunk beta"])

        async def _run():
            sem = asyncio.Semaphore(4)
            return await extractor._extract_batch_cached(chunks, sem)

        entities, edges = asyncio.run(_run())
        assert client.generate_response_with_history.call_count >= 1
        assert len(entities) > 0

    def test_cache_hit_does_not_call_llm(self):
        extractor, client = self._make_extractor()
        chunks = self._chunks(["chunk one", "chunk two"])

        async def _run():
            sem = asyncio.Semaphore(4)
            await extractor._extract_batch_cached(chunks, sem)
            first_count = client.generate_response_with_history.call_count
            await extractor._extract_batch_cached(chunks, sem)
            return first_count

        first_count = asyncio.run(_run())
        assert client.generate_response_with_history.call_count == first_count

    def test_cache_hit_restamps_chunk_ids(self):
        extractor, _ = self._make_extractor()
        chunks_a = self._chunks(["same text A", "same text B"], id_offset=0)
        chunks_b = self._chunks(["same text A", "same text B"], id_offset=10)

        async def _run():
            sem = asyncio.Semaphore(4)
            await extractor._extract_batch_cached(chunks_a, sem)
            entities_b, _ = await extractor._extract_batch_cached(chunks_b, sem)
            return entities_b

        entities_b = asyncio.run(_run())
        expected_ids = {10}
        for e in entities_b:
            assert set(e.chunk_ids) == expected_ids

    def test_cache_hit_applies_ordinal_mapping_not_all_ids(self):
        """After a cache hit, _raw_ordinals must be re-applied to map to the
        current batch's chunk IDs rather than defaulting to all chunk IDs."""
        # Response: both entities report ordinal 1 only (single-chunk attribution)
        response = (
            '("entity"<|>X<|>concept<|>desc<|>1)##'
            '<|COMPLETE|>'
        )
        extractor, _ = self._make_extractor(response=response)
        # First call — populates cache with ordinal 1
        chunks_a = [{"chunk_id": 100, "text": "same text"}, {"chunk_id": 101, "text": "other text"}]
        # Second call — same text, different chunk IDs; ordinal 1 must map to 200, not 200+201
        chunks_b = [{"chunk_id": 200, "text": "same text"}, {"chunk_id": 201, "text": "other text"}]

        async def _run():
            sem = asyncio.Semaphore(4)
            await extractor._extract_batch_cached(chunks_a, sem)
            entities_b, _ = await extractor._extract_batch_cached(chunks_b, sem)
            return entities_b

        entities_b = asyncio.run(_run())
        for e in entities_b:
            assert e.chunk_ids == [200], f"Expected [200] (ordinal 1 → chunk_id 200), got {e.chunk_ids}"

    def test_different_batches_with_pipe_prefix_not_collision(self):
        """Regression: batches whose texts look alike under '|'.join must NOT
        share a cache entry.  e.g. ['a|', 'b'] vs ['a', '|b'] would collide
        with the old pipe separator but must not collide after the fix."""
        extractor, client = self._make_extractor()
        chunks_x = [{"chunk_id": 0, "text": "a|"}, {"chunk_id": 1, "text": "b"}]
        chunks_y = [{"chunk_id": 2, "text": "a"}, {"chunk_id": 3, "text": "|b"}]

        async def _run():
            sem = asyncio.Semaphore(4)
            await extractor._extract_batch_cached(chunks_x, sem)
            count_after_x = client.generate_response_with_history.call_count
            await extractor._extract_batch_cached(chunks_y, sem)
            count_after_y = client.generate_response_with_history.call_count
            return count_after_x, count_after_y

        count_after_x, count_after_y = asyncio.run(_run())
        # The second batch must have triggered a fresh LLM call (cache miss)
        assert count_after_y > count_after_x, (
            "Expected a cache miss for the second batch, but no new LLM call was made. "
            "This indicates a cache key collision."
        )


# ---------------------------------------------------------------------------
# _parse_extraction_result — CHUNK_IDS field parsing
# ---------------------------------------------------------------------------


class TestParseExtractionResultChunkIds:
    def test_single_ordinal_parsed(self):
        raw = '("entity"<|>Foo<|>concept<|>desc<|>2)##'
        entities, _ = _parse_extraction_result(raw)
        assert entities[0]._raw_ordinals == [2]

    def test_csv_ordinals_parsed(self):
        raw = '("entity"<|>Bar<|>function<|>desc<|>1,3)##'
        entities, _ = _parse_extraction_result(raw)
        assert entities[0]._raw_ordinals == [1, 3]

    def test_missing_ordinals_field_gives_empty(self):
        raw = '("entity"<|>Baz<|>class<|>desc)##'
        entities, _ = _parse_extraction_result(raw)
        assert entities[0]._raw_ordinals == []

    def test_non_numeric_ordinals_ignored(self):
        raw = '("entity"<|>Qux<|>class<|>desc<|>1,x,3)##'
        entities, _ = _parse_extraction_result(raw)
        assert entities[0]._raw_ordinals == [1, 3]


# ---------------------------------------------------------------------------
# EntityExtractor._extract_batch — ordinal-to-chunk-id attribution
# ---------------------------------------------------------------------------


class TestExtractBatchOrdinalAttribution:
    """Verify that _extract_batch maps LLM-reported ordinals to actual chunk IDs."""

    def _make_extractor(self, response: str):
        client = _make_lm_client(response)
        cache = ExtractionCache()
        return EntityExtractor(lm_client=client, extraction_cache=cache, max_gleanings=0)

    def test_ordinal_maps_to_correct_chunk_id(self):
        # LLM says entity "Alpha" is from CHUNK 1, "Beta" from CHUNK 2
        response = (
            '("entity"<|>Alpha<|>concept<|>desc<|>1)##'
            '("entity"<|>Beta<|>concept<|>desc<|>2)##'
            '<|COMPLETE|>'
        )
        extractor = self._make_extractor(response)
        # chunk_ids are 10 and 20 (not ordinals)
        chunks = [{"chunk_id": 10, "text": "alpha text"}, {"chunk_id": 20, "text": "beta text"}]

        async def _run():
            sem = asyncio.Semaphore(4)
            return await extractor._extract_batch(chunks, sem)

        entities, _ = asyncio.run(_run())
        alpha = next(e for e in entities if e.name == "Alpha")
        beta = next(e for e in entities if e.name == "Beta")
        assert alpha.chunk_ids == [10]
        assert beta.chunk_ids == [20]

    def test_missing_ordinals_falls_back_to_all_chunk_ids(self):
        # LLM response has no CHUNK_IDS field (backward compat)
        response = (
            '("entity"<|>Foo<|>concept<|>desc)##'
            '<|COMPLETE|>'
        )
        extractor = self._make_extractor(response)
        chunks = [{"chunk_id": 5, "text": "a"}, {"chunk_id": 6, "text": "b"}]

        async def _run():
            sem = asyncio.Semaphore(4)
            return await extractor._extract_batch(chunks, sem)

        entities, _ = asyncio.run(_run())
        assert set(entities[0].chunk_ids) == {5, 6}

    def test_unknown_ordinal_falls_back_to_all_chunk_ids(self):
        # LLM hallucinates ordinal 9 which doesn't exist in batch
        response = '("entity"<|>Foo<|>concept<|>desc<|>9)##<|COMPLETE|>'
        extractor = self._make_extractor(response)
        chunks = [{"chunk_id": 5, "text": "a"}, {"chunk_id": 6, "text": "b"}]

        async def _run():
            sem = asyncio.Semaphore(4)
            return await extractor._extract_batch(chunks, sem)

        entities, _ = asyncio.run(_run())
        assert set(entities[0].chunk_ids) == {5, 6}
