"""GraphRAG-inspired entity and relationship extractor for parsed documents."""

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vectors.lm_studio import LMStudioClient
    from vectors.extraction_cache import ExtractionCache

logger = logging.getLogger(__name__)

MAX_CHUNKS_PER_EXTRACT = int(os.getenv("MAX_CHUNKS_PER_EXTRACT", "100"))

# Batch-extraction: group N chunks into one LLM call to reduce total call count.
# Set ENTITY_EXTRACTION_BATCH_SIZE=1 to restore the original one-call-per-chunk path.
ENTITY_EXTRACTION_BATCH_SIZE = int(os.getenv("ENTITY_EXTRACTION_BATCH_SIZE", "4"))

# Maximum combined character length of all chunks in one batch.
# When a batch would exceed this limit a new batch is started early.
# Default is 3× the default chunk_size (3 × 512 = 1536, rounded to 3000 for headroom).
_LLM_MAX_PROMPT_CHARS = int(os.getenv("LLM_MAX_PROMPT_CHARS", "30000"))

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Entity:
    name: str
    type: str  # person|organization|technology|file|function|class|concept
    description: str
    chunk_ids: list[int] = field(default_factory=list)
    descriptions: list[str] = field(default_factory=list)
    frequency: int = 1
    _raw_ordinals: list[int] = field(default_factory=list)


@dataclass
class Edge:
    source: str
    target: str
    edge_type: str = "related"  # imports|calls|inherits|defines|references|related
    weight: float = 1.0
    description: str = ""
    source_type: str = ""
    target_type: str = ""


@dataclass
class EntityMap:
    entities: list[Entity] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompts  (GraphRAG's exact <|> / ## delimiter scheme)
# ---------------------------------------------------------------------------

ENTITY_EXTRACTION_SYSTEM_PROMPT = """You are an expert knowledge graph extractor.
Identify ALL entities and relationships in the text.

For each entity output one line:
  ("entity"<|>NAME<|>TYPE<|>DESCRIPTION<|>CHUNK_IDS)##
CHUNK_IDS is a comma-separated list of chunk numbers (e.g. 1 or 1,3) where this entity appears.
When the text has no === CHUNK N === delimiters, use 1.
Entity types: person, organization, technology, file, function, class, concept

For each relationship output one line:
  ("relationship"<|>SOURCE_NAME<|>TARGET_NAME<|>DESCRIPTION<|>STRENGTH)##
STRENGTH is 1-10 (integer).

End your ENTIRE response with: <|COMPLETE|>
"""

CONTINUE_PROMPT = """Many entities and relationships were missed. Remember to ONLY emit
entities that were EXPLICITLY mentioned in the original text.
Add any missing entities or relationships using the same format."""

LOOP_PROMPT = "Are there still more entities or relationships to add? Answer Y or N only."

SUMMARIZE_SYSTEM_PROMPT = "You are a precise technical summarizer."


# ---------------------------------------------------------------------------
# Parser — NEVER abort on malformed records
# ---------------------------------------------------------------------------


def _parse_extraction_result(raw: str) -> tuple[list[Entity], list[Edge]]:
    entities, edges = [], []
    for rec in raw.split("##"):
        rec = rec.strip()
        # Strip exactly one leading "(" and one trailing ")"
        if rec.startswith("("):
            rec = rec[1:]
        if rec.endswith(")"):
            rec = rec[:-1]
        parts = [p.strip() for p in rec.split("<|>")]
        try:
            tag = parts[0].strip('"')
            if tag == "entity" and len(parts) >= 4:
                raw_ordinals: list[int] = []
                if len(parts) >= 5:
                    for tok in parts[4].split(","):
                        tok = tok.strip()
                        if tok.isdigit():
                            raw_ordinals.append(int(tok))
                entities.append(Entity(
                    name=parts[1], type=parts[2], description=parts[3],
                    _raw_ordinals=raw_ordinals,
                ))
            elif tag == "relationship" and len(parts) >= 5:
                edges.append(Edge(
                    source=parts[1], target=parts[2],
                    description=parts[3], weight=float(parts[4])
                ))
        except (IndexError, ValueError):
            continue
    # Resolve edge endpoint types from co-extracted entities
    entity_type_map = {e.name.lower(): e.type for e in entities}
    for edge in edges:
        if not edge.source_type:
            edge.source_type = entity_type_map.get(edge.source.lower(), "")
        if not edge.target_type:
            edge.target_type = entity_type_map.get(edge.target.lower(), "")
    return entities, edges


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------


async def _llm_with_retry(coro_fn, max_attempts: int = 3):
    for attempt in range(max_attempts):
        try:
            return await coro_fn()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            await asyncio.sleep(2 ** attempt)


# ---------------------------------------------------------------------------
# tree-sitter AST overlay (optional — soft dependency)
# ---------------------------------------------------------------------------

HAS_TREE_SITTER = False
_python_parser = None
try:
    from tree_sitter import Language, Parser as _TSParser
    import tree_sitter_python as _tspy
    _python_parser = _TSParser(Language(_tspy.language()))
    HAS_TREE_SITTER = True
except ImportError:
    pass


def _extract_ast_entities_for_file(file_path: str, parsed_doc) -> EntityMap:
    if not HAS_TREE_SITTER:
        return EntityMap()
    ext = os.path.splitext(file_path)[1].lower()
    if ext != ".py" or _python_parser is None:
        return EntityMap()
    try:
        content = "".join(c["text"] for c in parsed_doc.chunks)
        tree = _python_parser.parse(bytes(content, "utf-8"))
        return _walk_python_ast(tree, file_path)
    except Exception as e:
        logger.debug(f"AST extraction failed for {file_path}: {e}")
        return EntityMap()


def _walk_python_ast(tree, file_path: str) -> EntityMap:
    entities, edges = [], []

    def _node_text(node) -> str:
        return node.text.decode("utf-8") if node.text else ""

    def _visit(node):
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                cls_name = _node_text(name_node)
                entities.append(Entity(
                    name=cls_name, type="class",
                    description=f"Class {cls_name} in {file_path}"
                ))
                # Inheritance edges
                for base in (node.child_by_field_name("superclasses") or []):
                    base_name = _node_text(base)
                    if base_name:
                        edges.append(Edge(
                            source=cls_name, target=base_name,
                            edge_type="inherits"
                        ))
        elif node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                fn_name = _node_text(name_node)
                entities.append(Entity(
                    name=fn_name, type="function",
                    description=f"Function {fn_name} in {file_path}"
                ))
        elif node.type == "import_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    mod = _node_text(child)
                    edges.append(Edge(
                        source=file_path, target=mod, edge_type="imports"
                    ))
        elif node.type == "import_from_statement":
            mod_node = node.child_by_field_name("module_name")
            if mod_node:
                mod = _node_text(mod_node)
                edges.append(Edge(
                    source=file_path, target=mod, edge_type="imports"
                ))

        for child in node.children:
            _visit(child)

    _visit(tree.root_node)
    return EntityMap(entities=entities, edges=edges)


# ---------------------------------------------------------------------------
# Batch-prompt builder
# ---------------------------------------------------------------------------


def _build_batch_prompt(chunk_texts: list[str]) -> str:
    """Concatenate *chunk_texts* into a labeled prompt for batch extraction.

    Each chunk is prefixed with ``=== CHUNK N ===`` so the LLM has clear
    boundaries.  Triple-equals does not appear in standard Markdown or Python
    syntax, so the delimiter cannot collide with normal chunk content.
    The existing ``_parse_extraction_result`` parser works unchanged on the
    mixed output.
    """
    parts = [f"=== CHUNK {i} ===\n{text}" for i, text in enumerate(chunk_texts, 1)]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# EntityExtractor
# ---------------------------------------------------------------------------


class EntityExtractor:
    def __init__(
        self,
        lm_client: "LMStudioClient",
        extraction_cache: "ExtractionCache",
        max_gleanings: int = 1,
        batch_size: int = ENTITY_EXTRACTION_BATCH_SIZE,
        max_prompt_chars: int = _LLM_MAX_PROMPT_CHARS,
    ):
        self.lm_client = lm_client
        self.extraction_cache = extraction_cache
        self.max_gleanings = max_gleanings
        self._batch_size = batch_size
        self._max_prompt_chars = max_prompt_chars

    async def _extract_chunk(
        self, chunk_text: str, chunk_idx: int, semaphore: asyncio.Semaphore
    ) -> tuple[list[Entity], list[Edge]]:
        async with semaphore:
            messages = [
                {"role": "system", "content": ENTITY_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"Text to analyze:\n\n{chunk_text}"},
            ]
            raw = await _llm_with_retry(
                lambda: self.lm_client.generate_response_with_history(messages)
            )
            entities, edges = _parse_extraction_result(raw)
            messages.append({"role": "assistant", "content": raw})

            for _ in range(self.max_gleanings):
                messages.append({"role": "user", "content": CONTINUE_PROMPT})
                cont = await _llm_with_retry(
                    lambda: self.lm_client.generate_response_with_history(messages)
                )
                more_e, more_r = _parse_extraction_result(cont)
                entities.extend(more_e)
                edges.extend(more_r)
                messages.append({"role": "assistant", "content": cont})

                messages.append({"role": "user", "content": LOOP_PROMPT})
                loop_ans = await _llm_with_retry(
                    lambda: self.lm_client.generate_response_with_history(
                        messages, max_tokens=4
                    )
                )
                messages.append({"role": "assistant", "content": loop_ans})
                if not loop_ans.strip().upper().startswith("Y"):
                    break

            for e in entities:
                e.chunk_ids = [chunk_idx]
                e.descriptions = [e.description]

            return entities, edges

    async def _extract_chunk_cached(
        self, chunk_text: str, chunk_idx: int, semaphore: asyncio.Semaphore
    ) -> tuple[list[Entity], list[Edge]]:
        chunk_hash = hashlib.sha256(chunk_text.encode()).hexdigest()
        model = getattr(self.lm_client, "_llm_model", "unknown")
        cached = self.extraction_cache.get(model, chunk_hash)
        if cached:
            # Re-stamp chunk_ids for this index position
            entities = [
                Entity(**{**vars(e), "chunk_ids": [chunk_idx], "descriptions": list(e.descriptions)})
                for e in cached["entities"]
            ]
            return entities, list(cached["edges"])

        entities, edges = await self._extract_chunk(chunk_text, chunk_idx, semaphore)
        self.extraction_cache.set(model, chunk_hash, {
            "entities": entities, "edges": edges
        })
        return entities, edges

    def _make_batches(self, chunks: list[dict]) -> list[list[dict]]:
        """Partition *chunks* into batches for batch entity extraction.

        Each batch contains at most ``self._batch_size`` chunks
        and its combined text stays under ``_LLM_MAX_PROMPT_CHARS``.
        When ``self._batch_size == 1`` every chunk forms its own
        batch, preserving the original one-call-per-chunk behaviour.
        """
        batches: list[list[dict]] = []
        current: list[dict] = []
        current_chars = 0

        for chunk in chunks:
            text_len = len(chunk["text"])
            if current and (
                len(current) >= self._batch_size
                or current_chars + text_len > self._max_prompt_chars
            ):
                batches.append(current)
                current = []
                current_chars = 0
            if not current and text_len > self._max_prompt_chars:
                logger.warning(
                    "Chunk %s (%d chars) exceeds max_prompt_chars=%d; "
                    "forming its own oversized batch.",
                    chunk.get("chunk_id", "?"), text_len, self._max_prompt_chars,
                )
            current.append(chunk)
            current_chars += text_len

        if current:
            batches.append(current)
        return batches

    async def _extract_batch(
        self, chunks: list[dict], semaphore: asyncio.Semaphore
    ) -> tuple[list[Entity], list[Edge]]:
        """Extract entities from *chunks* in a single LLM call.

        All extracted entities receive ``chunk_ids`` set to the IDs of every
        chunk in the batch — a deliberate accuracy trade-off that lets us cut
        total LLM calls by up to ``ENTITY_EXTRACTION_BATCH_SIZE``.
        """
        chunk_ids = [c["chunk_id"] for c in chunks]
        batch_text = _build_batch_prompt([c["text"] for c in chunks])

        async with semaphore:
            messages = [
                {"role": "system", "content": ENTITY_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"Text to analyze:\n\n{batch_text}"},
            ]
            raw = await _llm_with_retry(
                lambda: self.lm_client.generate_response_with_history(messages)
            )
            entities, edges = _parse_extraction_result(raw)
            messages.append({"role": "assistant", "content": raw})

            for _ in range(self.max_gleanings):
                messages.append({"role": "user", "content": CONTINUE_PROMPT})
                cont = await _llm_with_retry(
                    lambda: self.lm_client.generate_response_with_history(messages)
                )
                more_e, more_r = _parse_extraction_result(cont)
                entities.extend(more_e)
                edges.extend(more_r)
                messages.append({"role": "assistant", "content": cont})

                messages.append({"role": "user", "content": LOOP_PROMPT})
                loop_ans = await _llm_with_retry(
                    lambda: self.lm_client.generate_response_with_history(
                        messages, max_tokens=4
                    )
                )
                messages.append({"role": "assistant", "content": loop_ans})
                if not loop_ans.strip().upper().startswith("Y"):
                    break

            # Map LLM-reported ordinals (1-indexed) to actual chunk IDs.
            # Falls back to all chunk IDs when ordinals are absent or unknown.
            ordinal_to_id = {i + 1: cid for i, cid in enumerate(chunk_ids)}
            for e in entities:
                if e._raw_ordinals:
                    resolved = [ordinal_to_id[o] for o in e._raw_ordinals if o in ordinal_to_id]
                    e.chunk_ids = resolved if resolved else list(chunk_ids)
                else:
                    e.chunk_ids = list(chunk_ids)
                e.descriptions = [e.description]

            return entities, edges

    async def _extract_batch_cached(
        self, chunks: list[dict], semaphore: asyncio.Semaphore
    ) -> tuple[list[Entity], list[Edge]]:
        """Cache-aware entry point for batch (or single-chunk) extraction.

        Single-element batches are forwarded to the original
        ``_extract_chunk_cached`` to maximise cache hit rate when the same
        chunk appears in a single-file re-index after earlier batch runs.
        """
        if len(chunks) == 1:
            c = chunks[0]
            return await self._extract_chunk_cached(c["text"], c["chunk_id"], semaphore)

        # Hash all chunk texts together to form the cache key.
        # The len(text):text prefix makes the encoding bijective: two different
        # sequences of chunk texts cannot produce the same combined string,
        # regardless of whether the texts contain the \x00 separator.
        combined = "\x00".join(
            f"{len(c['text'])}:{c['text']}" for c in chunks
        )
        batch_hash = hashlib.sha256(combined.encode()).hexdigest()
        model = getattr(self.lm_client, "_llm_model", "unknown")
        chunk_ids = [c["chunk_id"] for c in chunks]

        cached = self.extraction_cache.get(model, batch_hash)
        if cached:
            ordinal_to_id = {i + 1: cid for i, cid in enumerate(chunk_ids)}
            entities = []
            for e in cached["entities"]:
                if e._raw_ordinals:
                    resolved = [ordinal_to_id[o] for o in e._raw_ordinals if o in ordinal_to_id]
                    resolved_ids = resolved if resolved else list(chunk_ids)
                else:
                    resolved_ids = list(chunk_ids)
                entities.append(Entity(
                    **{**vars(e), "chunk_ids": resolved_ids,
                       "descriptions": list(e.descriptions)}
                ))
            return entities, list(cached["edges"])

        entities, edges = await self._extract_batch(chunks, semaphore)
        self.extraction_cache.set(model, batch_hash, {"entities": entities, "edges": edges})
        return entities, edges

    def _merge_entities(self, all_entities: list[Entity], root_id: str) -> list[Entity]:
        """Deduplicate by (name.lower(), type), merging chunk_ids and descriptions."""
        merged: dict[str, Entity] = {}
        for e in all_entities:
            key = hashlib.sha256(
                f"{e.name.lower()}|{e.type}|{root_id}".encode()
            ).hexdigest()
            if key in merged:
                merged[key].chunk_ids.extend(e.chunk_ids)
                merged[key].descriptions.extend(e.descriptions)
                merged[key].frequency = len(set(merged[key].chunk_ids))
            else:
                merged[key] = Entity(
                    name=e.name, type=e.type, description=e.description,
                    chunk_ids=list(e.chunk_ids), descriptions=list(e.descriptions)
                )
        return list(merged.values())

    async def _summarize_entity(self, entity: Entity) -> None:
        """Collapse multi-chunk descriptions into one via LLM (in-place)."""
        if len(entity.descriptions) <= 1:
            return
        combined = "\n\n".join(entity.descriptions)
        try:
            summary = await _llm_with_retry(
                lambda: self.lm_client.generate_response(
                    query=f"Summarize these descriptions of '{entity.name}' into one concise paragraph:",
                    context=combined,
                    max_tokens=300,
                )
            )
            entity.description = summary
        except Exception as e:
            logger.warning(f"Description summarization failed for '{entity.name}': {e}")
            entity.description = entity.descriptions[0]

    async def extract_file(
        self,
        file_path: str,
        parsed_doc,
        root_id: str,
        chunk_semaphore: asyncio.Semaphore,
    ) -> EntityMap:
        chunks = parsed_doc.chunks
        if len(chunks) > MAX_CHUNKS_PER_EXTRACT:
            logger.warning(
                f"Entity extraction capped at {MAX_CHUNKS_PER_EXTRACT}/{len(chunks)} "
                f"chunks for {file_path}. Set MAX_CHUNKS_PER_EXTRACT to override."
            )
            chunks = chunks[:MAX_CHUNKS_PER_EXTRACT]

        # Use chunk["chunk_id"] (set by parser as positional index) so entity.chunk_ids
        # match the point IDs stored in Qdrant via make_chunk_point_id.
        #
        # Batch extraction: group chunks so we make fewer LLM calls.
        # _make_batches() honours ENTITY_EXTRACTION_BATCH_SIZE and
        # _LLM_MAX_PROMPT_CHARS. When batch_size==1 every batch has one
        # chunk and _extract_batch_cached() delegates to the original
        # single-chunk cached path — no behaviour change.
        batches = self._make_batches(chunks)
        if len(batches) < len(chunks):
            logger.debug(
                "Batching %d chunks into %d LLM calls (batch_size=%d)",
                len(chunks), len(batches), self._batch_size,
            )
        tasks = [
            self._extract_batch_cached(batch, chunk_semaphore)
            for batch in batches
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_entities: list[Entity] = []
        all_edges: list[Edge] = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"Chunk extraction error: {r}")
                continue
            all_entities.extend(r[0])
            all_edges.extend(r[1])

        # Merge + summarize
        merged = self._merge_entities(all_entities, root_id)

        # Try AST overlay for code files
        ast_map = _extract_ast_entities_for_file(file_path, parsed_doc)
        merged.extend(ast_map.entities)
        all_edges.extend(ast_map.edges)
        merged = self._merge_entities(merged, root_id)

        # Summarize descriptions concurrently (bounded)
        summarize_sem = asyncio.Semaphore(4)

        async def _sum(e):
            async with summarize_sem:
                await self._summarize_entity(e)

        await asyncio.gather(
            *[_sum(e) for e in merged if len(e.descriptions) > 1],
            return_exceptions=True,
        )

        return EntityMap(entities=merged, edges=all_edges)


# ---------------------------------------------------------------------------
# annotate_chunks — standalone helper
# ---------------------------------------------------------------------------


def annotate_chunks(parsed_doc, entity_map: EntityMap):
    """Annotate each chunk with entity names found in it.

    Uses Entity.chunk_ids for the mapping — no text re-scan needed.
    Chunks are dicts; writes to chunk["entity_names"].
    """
    chunk_names: dict[int, list[str]] = {}
    for entity in entity_map.entities:
        for idx in entity.chunk_ids:
            chunk_names.setdefault(idx, []).append(entity.name)

    for chunk in parsed_doc.chunks:
        chunk["entity_names"] = chunk_names.get(chunk["chunk_id"], [])

    return parsed_doc
