"""Qdrant vector database client for document storage and search."""

from __future__ import annotations

import logging
import hashlib
import uuid
from dataclasses import dataclass
from typing import Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    MatchAny,
    Range,
)

from .config import sanitize_for_log
from .metadata import build_chunk_payload_v2, build_chunk_payload_v3, extract_file_record_from_payload, oldest_indexed_at
from .paths import PathPolicy

logger = logging.getLogger(__name__)


def make_chunk_point_id(file_path: str, chunk_id: int) -> str:
    """Return the deterministic Qdrant point ID for a (file_path, chunk_id) pair."""
    content = f"{PathPolicy.path_key(file_path)}:{chunk_id}"
    return hashlib.md5(content.encode()).hexdigest()


@dataclass
class SearchResult:
    """A single search result from Qdrant."""

    id: str
    score: float
    file_path: str
    file_name: str
    chunk_id: int
    chunk_text: str
    start_char: int
    end_char: int
    metadata: dict


class QdrantVectorStore:
    """Vector store using Qdrant for document embeddings."""

    def __init__(
        self,
        url: Optional[str] = None,
        collection_name: str = "mcp_vectors",
        vector_size: int = 384,
        max_scroll_points: int = 50_000,
        scroll_page_size: int = 1_000,
    ):
        self.url = url
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.max_scroll_points = max_scroll_points
        self.scroll_page_size = scroll_page_size
        self._client: Optional[AsyncQdrantClient] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the connection and ensure collection exists."""
        if self._initialized:
            return

        if self.url:
            logger.info(f"Connecting to Qdrant at {self.url}")
            self._client = AsyncQdrantClient(url=self.url)
        else:
            logger.info("Using in-memory Qdrant storage")
            self._client = AsyncQdrantClient(":memory:")

        await self._ensure_collection()
        await self._ensure_payload_indexes()
        self._initialized = True
        logger.info(f"Qdrant initialized with collection: {self.collection_name}")

    async def _ensure_collection(self) -> None:
        """Create the collection if it doesn't exist or recreate if vector size changed."""
        try:
            collections = await self._client.get_collections()
            exists = any(c.name == self.collection_name for c in collections.collections)

            if exists:
                info = await self._client.get_collection(self.collection_name)

                current_size = None
                try:
                    if hasattr(info, "config") and hasattr(info.config, "params"):
                        params = info.config.params
                        if hasattr(params, "vectors"):
                            vectors = params.vectors
                            if hasattr(vectors, "size"):
                                current_size = vectors.size
                            elif isinstance(vectors, dict) and "size" in vectors:
                                current_size = vectors["size"]
                    if current_size is None:
                        info_dict = info.model_dump() if hasattr(info, "model_dump") else info.dict() if hasattr(info, "dict") else {}
                        vectors_config = info_dict.get("config", {}).get("params", {}).get("vectors", {})
                        if isinstance(vectors_config, dict):
                            current_size = vectors_config.get("size")
                except Exception as e:
                    logger.warning(f"Could not extract vector size from collection config: {e}")

                logger.info(f"Collection {self.collection_name}: current_size={current_size}, expected={self.vector_size}")
                if current_size is not None and current_size != self.vector_size:
                    logger.warning(
                        f"Collection vector size mismatch: expected {self.vector_size}, got {current_size}. Recreating collection."
                    )
                    await self._client.delete_collection(self.collection_name)
                    exists = False
                elif current_size is None:
                    logger.warning(f"Could not determine collection vector size, assuming correct: {self.collection_name}")
                else:
                    logger.info(f"Collection exists with correct vector size: {self.collection_name}")

            if not exists:
                logger.info(f"Creating collection: {self.collection_name} with vector_size={self.vector_size}")
                try:
                    await self._client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
                    )
                    logger.info(f"Collection created: {self.collection_name}")
                except Exception as create_error:
                    error_str = str(create_error).lower()
                    if "already exists" in error_str or "409" in error_str:
                        logger.info(f"Collection {self.collection_name} was created by another instance")
                    else:
                        raise
        except Exception as e:
            logger.error(f"Failed to ensure collection: {e} | {type(e).__module__}.{type(e).__name__}: {e}")
            raise

    async def _ensure_payload_indexes(self) -> None:
        """Create best-effort payload indexes for metadata filters."""
        fields = {
            "file_path": models.PayloadSchemaType.KEYWORD,
            "path_key": models.PayloadSchemaType.KEYWORD,
            "doc_id": models.PayloadSchemaType.KEYWORD,
            "root_id": models.PayloadSchemaType.KEYWORD,
            "metadata_version": models.PayloadSchemaType.INTEGER,
            "chunk_id": models.PayloadSchemaType.INTEGER,
            "file_type": models.PayloadSchemaType.KEYWORD,
            "extension": models.PayloadSchemaType.KEYWORD,
            # v3 entity graph fields
            "entity_names": models.PayloadSchemaType.KEYWORD,
            "parent_symbol": models.PayloadSchemaType.KEYWORD,
            "symbol_type": models.PayloadSchemaType.KEYWORD,
        }
        for field_name, schema in fields.items():
            try:
                await self._client.create_payload_index(self.collection_name, field_name, field_schema=schema)
            except Exception as e:
                logger.debug(f"Payload index unavailable/exists for {field_name}: {e}")

    def update_vector_size(self, new_size: int) -> None:
        """Update the vector size before initialization."""
        if self._initialized:
            logger.warning("Cannot change vector size after initialization")
            return
        self.vector_size = new_size

    def _generate_point_id(self, file_path: str, chunk_id: int) -> str:
        return make_chunk_point_id(file_path, chunk_id)

    async def upsert_chunks(
        self,
        file_path: str,
        file_name: str,
        chunks: list[dict],
        embeddings: list[list[float]],
        file_metadata: Optional[dict] = None,
        root_path: str | None = None,
        index_run_id: str | None = None,
    ) -> int:
        """Insert or update document chunks with their embeddings."""
        if not self._initialized:
            await self.initialize()
        if len(chunks) != len(embeddings):
            raise ValueError(f"Chunks ({len(chunks)}) and embeddings ({len(embeddings)}) count mismatch")
        if not chunks:
            return 0

        canonical_path = PathPolicy.path_key(file_path)
        file_metadata = dict(file_metadata or {})
        file_metadata.setdefault("chunk_count", len(chunks))
        points = []
        for chunk, embedding in zip(chunks, embeddings):
            point_id = self._generate_point_id(canonical_path, chunk["chunk_id"])
            if chunk.get("entity_names") is not None:
                payload = build_chunk_payload_v3(
                    file_path=canonical_path,
                    file_name=file_name,
                    chunk=chunk,
                    file_metadata=file_metadata,
                    root_path=root_path,
                    index_run_id=index_run_id,
                    entity_names=chunk.get("entity_names", []),
                    imported_modules=chunk.get("imported_modules", []),
                    called_symbols=chunk.get("called_symbols", []),
                    parent_symbol=chunk.get("parent_symbol"),
                    symbol_type=chunk.get("symbol_type"),
                    line_start=chunk.get("line_start"),
                    line_end=chunk.get("line_end"),
                )
            else:
                payload = build_chunk_payload_v2(
                    file_path=canonical_path,
                    file_name=file_name,
                    chunk=chunk,
                    file_metadata=file_metadata,
                    root_path=root_path,
                    index_run_id=index_run_id,
                )
            points.append(PointStruct(id=point_id, vector=embedding, payload=payload))

        _SAMPLE_LIMIT = 10
        sample_ids = [p.id for p in points[:_SAMPLE_LIMIT]]
        logger.info(
            f"qdrant.upsert_chunks: starting "
            f"reason=index_document collection={self.collection_name} "
            f"file_name={sanitize_for_log(file_name)} "
            f"point_count={len(points)} sample_ids={sample_ids}"
            + (" sample_truncated=true" if len(points) > _SAMPLE_LIMIT else "")
        )
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            await self._client.upsert(collection_name=self.collection_name, points=batch)

        logger.info(
            f"qdrant.upsert_chunks: done "
            f"collection={self.collection_name} file_name={sanitize_for_log(file_name)} "
            f"point_count={len(points)} status=success"
        )
        return len(points)

    async def update_chunk_entities(self, file_path: str, chunks: list[dict]) -> None:
        """Set the entity_names payload field on already-stored points without re-embedding.

        Called after async entity extraction completes to back-fill entity_names into
        Qdrant payloads so that entity-graph reranking can use them immediately.
        Uses the same point-id derivation as upsert_chunks (make_chunk_point_id with
        the canonical path_key) so the exact existing points are targeted.
        """
        if not chunks:
            return
        if not self._initialized:
            await self.initialize()
        canonical = PathPolicy.path_key(file_path)
        for chunk in chunks:
            point_id = self._generate_point_id(canonical, chunk["chunk_id"])
            payload = {"entity_names": chunk.get("entity_names") or []}
            await self._client.set_payload(
                collection_name=self.collection_name,
                payload=payload,
                points=[point_id],
            )
        logger.debug(
            f"Back-filled entity_names payload for {len(chunks)} chunks of "
            f"{sanitize_for_log(file_path)}"
        )

    def _matches_base_dirs(self, file_path: str, base_dirs: Optional[list[str]]) -> bool:
        """Check if file_path is within any base_dirs with component-safe matching."""
        if not base_dirs:
            return True
        return any(PathPolicy.is_within(file_path, base_dir) for base_dir in base_dirs)

    def _build_search_filter(
        self,
        *,
        file_filter: Optional[str] = None,
        exclude_files: Optional[list[str]] = None,
        root_path: Optional[str] = None,
        extensions: Optional[list[str]] = None,
        file_types: Optional[list[str]] = None,
    ) -> Optional[Filter]:
        must_conditions = []
        must_not_conditions = []

        if file_filter:
            canonical = PathPolicy.path_key(file_filter)
            must_conditions.append(FieldCondition(key="file_path", match=MatchValue(value=canonical)))

        if root_path:
            root_id = PathPolicy.path_key(root_path)
            must_conditions.append(FieldCondition(key="root_id", match=MatchValue(value=root_id)))

        if extensions:
            values = [ext if ext.startswith(".") else f".{ext}" for ext in extensions]
            must_conditions.append(FieldCondition(key="extension", match=MatchAny(any=values)))

        if file_types:
            must_conditions.append(FieldCondition(key="file_type", match=MatchAny(any=file_types)))

        if exclude_files:
            for file_path in exclude_files:
                canonical = PathPolicy.path_key(file_path)
                must_not_conditions.append(FieldCondition(key="file_path", match=MatchValue(value=canonical)))
                must_not_conditions.append(FieldCondition(key="path_key", match=MatchValue(value=canonical)))

        if not must_conditions and not must_not_conditions:
            return None
        return Filter(must=must_conditions or None, must_not=must_not_conditions or None)

    async def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        file_filter: Optional[str] = None,
        base_dirs: Optional[list[str]] = None,
        exclude_files: Optional[list[str]] = None,
        min_score: Optional[float] = None,
        root_path: Optional[str] = None,
        extensions: Optional[list[str]] = None,
        file_types: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """Search for similar documents."""
        if not self._initialized:
            await self.initialize()

        search_filter = self._build_search_filter(
            file_filter=file_filter,
            exclude_files=exclude_files,
            root_path=root_path,
            extensions=extensions,
            file_types=file_types,
        )
        search_limit = limit * 5 if base_dirs else limit
        filter_summary = (
            f"root_path_filter={'yes' if root_path else 'no'} "
            f"file_filter={'yes' if file_filter else 'no'} "
            f"extensions={'yes' if extensions else 'no'} "
            f"file_types={'yes' if file_types else 'no'} "
            f"exclude_files_count={len(exclude_files) if exclude_files else 0}"
        )
        logger.debug(
            f"qdrant.search: starting "
            f"reason=semantic_search collection={self.collection_name} "
            f"limit={limit} scan_limit={search_limit} {filter_summary}"
        )

        response = await self._client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=search_limit,
            query_filter=search_filter,
            with_payload=True,
        )
        results = response.points

        search_results = []
        for hit in results:
            payload = hit.payload or {}
            file_path = payload.get("file_path", "")
            if not self._matches_base_dirs(file_path, base_dirs):
                continue
            if min_score is not None and hit.score < min_score:
                continue
            search_results.append(
                SearchResult(
                    id=str(hit.id),
                    score=hit.score,
                    file_path=file_path,
                    file_name=payload.get("file_name", ""),
                    chunk_id=payload.get("chunk_id", 0),
                    chunk_text=payload.get("chunk_text", ""),
                    start_char=payload.get("start_char", 0),
                    end_char=payload.get("end_char", 0),
                    metadata={
                        k: v
                        for k, v in payload.items()
                        if k not in ["file_path", "file_name", "chunk_id", "chunk_text", "start_char", "end_char"]
                    },
                )
            )
            if len(search_results) >= limit:
                break
        return search_results

    async def get_points_by_ids(self, point_ids: list[str]) -> list[dict]:
        """Fetch Qdrant points by exact ID list (entity-grounded lookup, no ANN).

        Qdrant silently drops IDs that are not present, so the returned list may be
        shorter than point_ids. Callers must check len(result) vs len(point_ids) to
        detect missing points (B7 eventual-consistency: an entity may exist in SQLite
        before its chunk vector has been upserted, or after a collection reset).
        """
        if not point_ids:
            return []
        if not self._initialized:
            await self.initialize()
        results = await self._client.retrieve(
            collection_name=self.collection_name,
            ids=point_ids,
            with_payload=True,
            with_vectors=False,
        )
        return [
            {
                "id":      str(p.id),
                "score":   1.0,
                "payload": p.payload or {},
            }
            for p in results
        ]

    async def scroll_points_bounded(
        self,
        *,
        with_payload: bool | list[str] = True,
        scroll_filter: Optional[Filter] = None,
        page_size: Optional[int] = None,
        max_points: Optional[int] = None,
    ) -> dict:
        """Scroll points with explicit bounds and truncation metadata."""
        if not self._initialized:
            await self.initialize()
        page_size = page_size or self.scroll_page_size
        max_points = max_points or self.max_scroll_points
        points = []
        scanned = 0
        offset = None
        partial = False

        while scanned < max_points:
            current_limit = min(page_size, max_points - scanned)
            result = await self._client.scroll(
                collection_name=self.collection_name,
                limit=current_limit,
                offset=offset,
                scroll_filter=scroll_filter,
                with_payload=with_payload,
            )
            batch, offset = result
            points.extend(batch)
            scanned += len(batch)
            if offset is None or not batch:
                break
        else:
            partial = True

        if offset is not None and scanned >= max_points:
            partial = True

        return {"points": points, "scanned_points": scanned, "partial": partial, "scan_truncated": partial, "next_offset": offset}

    async def delete_document(self, file_path: str) -> int:
        """Delete all chunks for a document by exact v1 file_path."""
        if not self._initialized:
            await self.initialize()
        count_before = await self.get_document_chunk_count(file_path)
        logger.info(
            f"qdrant.delete_document: starting "
            f"reason=remove_document collection={self.collection_name} "
            f"file_path={sanitize_for_log(file_path)} chunk_count={count_before}"
        )
        await self._delete_by_filter(Filter(must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]))
        logger.info(
            f"qdrant.delete_document: done "
            f"collection={self.collection_name} file_path={sanitize_for_log(file_path)} "
            f"deleted_count={count_before} status=success"
        )
        return count_before

    async def delete_document_by_path_key(self, path_key: str) -> int:
        """Delete all chunks for a document by canonical v2 path_key or v1 file_path fallback."""
        if not self._initialized:
            await self.initialize()
        canonical = PathPolicy.path_key(path_key)
        count_before = await self.get_document_chunk_count_by_path_key(canonical)
        logger.info(
            f"qdrant.delete_document_by_path_key: starting "
            f"reason=remove_document collection={self.collection_name} "
            f"path_key={sanitize_for_log(canonical)} chunk_count={count_before}"
        )
        await self._delete_by_filter(
            Filter(
                should=[
                    FieldCondition(key="path_key", match=MatchValue(value=canonical)),
                    FieldCondition(key="file_path", match=MatchValue(value=canonical)),
                ]
            )
        )
        logger.info(
            f"qdrant.delete_document_by_path_key: done "
            f"collection={self.collection_name} path_key={sanitize_for_log(canonical)} "
            f"deleted_count={count_before} status=success"
        )
        return count_before

    async def delete_document_chunks_from(self, path_key: str, min_chunk_id: int) -> int:
        """Delete chunks with chunk_id >= min_chunk_id for a path_key after successful replacement."""
        canonical = PathPolicy.path_key(path_key)
        before = await self.get_document_chunk_count_by_path_key(canonical)
        await self._delete_by_filter(
            Filter(
                must=[
                    FieldCondition(key="path_key", match=MatchValue(value=canonical)),
                    FieldCondition(key="chunk_id", range=Range(gte=min_chunk_id)),
                ]
            )
        )
        after = await self.get_document_chunk_count_by_path_key(canonical)
        return max(0, before - after)

    async def _delete_by_filter(self, delete_filter: Filter) -> None:
        selector = models.FilterSelector(filter=delete_filter)
        await self._client.delete(collection_name=self.collection_name, points_selector=selector)

    async def remap_root(self, source_root_id: str, dest_root_id: str, dest_root_path: str) -> int:
        """Rewrite root_id/root_path for every point tagged with source_root_id (ADR-0008 remap)."""
        if not self._initialized:
            await self.initialize()
        root_filter = Filter(must=[FieldCondition(key="root_id", match=MatchValue(value=source_root_id))])
        count = await self._count(root_filter)
        if count == 0:
            return 0
        await self._client.set_payload(
            collection_name=self.collection_name,
            payload={"root_id": dest_root_id, "root_path": dest_root_path},
            points=models.FilterSelector(filter=root_filter),
        )
        return count

    async def delete_root(self, root_id: str) -> int:
        """Delete every point tagged with root_id (ADR-0008 purge). Returns the count removed."""
        if not self._initialized:
            await self.initialize()
        root_filter = Filter(must=[FieldCondition(key="root_id", match=MatchValue(value=root_id))])
        count = await self._count(root_filter)
        if count:
            await self._delete_by_filter(root_filter)
        return count

    async def get_document_chunk_count(self, file_path: str) -> int:
        """Get the number of chunks indexed for a v1 file_path."""
        if not self._initialized:
            await self.initialize()
        return await self._count(Filter(must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]))

    async def get_document_chunk_count_by_path_key(self, path_key: str) -> int:
        """Get chunk count for a canonical path using v2 and v1 fallback fields."""
        if not self._initialized:
            await self.initialize()
        canonical = PathPolicy.path_key(path_key)
        return await self._count(
            Filter(
                should=[
                    FieldCondition(key="path_key", match=MatchValue(value=canonical)),
                    FieldCondition(key="file_path", match=MatchValue(value=canonical)),
                ]
            )
        )

    async def _count(self, count_filter: Filter) -> int:
        result = await self._client.count(collection_name=self.collection_name, count_filter=count_filter)
        return result.count

    async def list_indexed_files(
        self,
        skip: int = 0,
        limit: int = 100,
        base_dirs: Optional[list[str]] = None,
        max_scan_points: Optional[int] = None,
    ) -> dict:
        """List indexed files with bounded scan metadata."""
        if not self._initialized:
            await self.initialize()

        scroll = await self.scroll_points_bounded(
            with_payload=[
                "file_path",
                "file_name",
                "modified_time",
                "indexed_at",
                "indexed_time",
                "path_key",
                "display_path",
                "relative_path",
                "root_path",
                "root_id",
                "file_type",
                "extension",
                "metadata_version",
                "chunk_count",
                "file_hash",
                "file_size",
                "mtime_ns",
            ],
            max_points=max_scan_points,
        )
        files = {}
        for point in scroll["points"]:
            payload = point.payload or {}
            record = extract_file_record_from_payload(payload)
            file_path = record.get("file_path") or record.get("path_key")
            if not file_path or not self._matches_base_dirs(file_path, base_dirs):
                continue
            key = record.get("path_key") or file_path
            if key not in files:
                record["chunk_count"] = 0
                record["metadata_versions"] = {}
                files[key] = record
            files[key]["chunk_count"] += 1
            version = str(payload.get("metadata_version", 1))
            files[key]["metadata_versions"][version] = files[key]["metadata_versions"].get(version, 0) + 1
            last_updated = record.get("last_updated")
            if last_updated and (not files[key].get("last_updated") or last_updated > files[key]["last_updated"]):
                files[key]["last_updated"] = last_updated

        non_none = [f for f in files.values() if f.get("last_updated") is not None]
        none_files = [f for f in files.values() if f.get("last_updated") is None]
        sorted_files = sorted(non_none, key=lambda x: x.get("last_updated"), reverse=True) + none_files
        return {
            "files": sorted_files[skip : skip + limit],
            "total_unique_files_scanned": len(sorted_files),
            "skip": skip,
            "limit": limit,
            "scanned_points": scroll["scanned_points"],
            "partial": scroll["partial"],
            "scan_truncated": scroll["scan_truncated"],
        }

    async def get_file_metadata_summary(self, base_path: Optional[str] = None) -> dict:
        listing = await self.list_indexed_files(skip=0, limit=10_000, base_dirs=[base_path] if base_path else None)
        distribution: dict[str, int] = {}
        legacy_files = 0
        for file in listing["files"]:
            versions = file.get("metadata_versions", {})
            for version, count in versions.items():
                distribution[version] = distribution.get(version, 0) + count
            if file.get("legacy_metadata") or "1" in versions:
                legacy_files += 1
        return {
            "file_count": listing["total_unique_files_scanned"],
            "sample_files": listing["files"][:20],
            "metadata_version_distribution": distribution,
            "legacy_file_count": legacy_files,
            "oldest_indexed_at": oldest_indexed_at(listing["files"]),
            "partial": listing["partial"],
            "scan_truncated": listing["scan_truncated"],
        }

    async def is_path_indexed(self, path: str) -> bool:
        return await self.get_document_chunk_count_by_path_key(path) > 0

    async def audit_payloads_for_secrets(self, policy, max_scan_points: Optional[int] = None, include_content_scan: bool = False) -> dict:
        payload_fields = ["file_path", "path_key", "file_name"]
        if include_content_scan:
            payload_fields.append("chunk_text")
        scroll = await self.scroll_points_bounded(with_payload=payload_fields, max_points=max_scan_points)
        by_file: dict[str, dict] = {}
        for point in scroll["points"]:
            payload = point.payload or {}
            reasons = policy.payload_secret_reasons(payload)
            if not reasons:
                continue
            file_path = payload.get("file_path") or payload.get("path_key") or ""
            if file_path not in by_file:
                by_file[file_path] = {"file_path": file_path, "reason_codes": [], "chunk_hits": 0}
            by_file[file_path]["chunk_hits"] += 1
            by_file[file_path]["reason_codes"] = list(dict.fromkeys(by_file[file_path]["reason_codes"] + reasons))
        return {
            "files": list(by_file.values()),
            "file_count": len(by_file),
            "scanned_points": scroll["scanned_points"],
            "partial": scroll["partial"],
            "scan_truncated": scroll["scan_truncated"],
            "content_scan": include_content_scan,
        }

    async def get_stats(self) -> dict:
        """Get statistics about the vector store."""
        if not self._initialized:
            await self.initialize()
        try:
            info = await self._client.get_collection(self.collection_name)
            info_dict = {}
            try:
                info_dict = info.model_dump() if hasattr(info, "model_dump") else info.dict() if hasattr(info, "dict") else {}
            except Exception:
                pass
            points_count = info_dict.get("points_count", 0) or 0
            status = info_dict.get("status", "unknown")
            return {
                "collection_name": self.collection_name,
                "total_points": points_count,
                "status": str(status) if status else "unknown",
                "vector_size": self.vector_size,
                "storage_mode": "remote" if self.url else "in-memory",
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {
                "collection_name": self.collection_name,
                "total_points": 0,
                "status": "error",
                "vector_size": self.vector_size,
                "storage_mode": "remote" if self.url else "in-memory",
                "error": str(e),
            }

    async def reset_collection(self) -> dict:
        """Delete and recreate the collection, removing all indexed data."""
        if not self._initialized:
            await self.initialize()
        try:
            logger.info(f"Resetting collection: {self.collection_name}")
            await self._client.delete_collection(self.collection_name)
            await self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
            await self._ensure_payload_indexes()
            logger.info(f"Collection reset complete: {self.collection_name}")
            return {"success": True, "collection_name": self.collection_name, "message": "Collection reset successfully"}
        except Exception as e:
            logger.error(f"Failed to reset collection: {e}")
            return {"success": False, "error": str(e)}

    async def close(self) -> None:
        """Close the connection."""
        if self._client:
            await self._client.close()
            self._client = None
        self._initialized = False


# ---------------------------------------------------------------------------
# Community collection exceptions and helpers
# ---------------------------------------------------------------------------


class CommunityCollectionConfigError(Exception):
    """Raised when the community collection has incompatible config (dimension/distance mismatch)."""
    pass


class CollectionMissingError(Exception):
    """Raised when the community Qdrant collection is missing after initialization."""

    def __init__(self, root_id: str):
        super().__init__(f"Community collection missing for root {root_id!r}")
        self.root_id = root_id


COMMUNITIES_COLLECTION = "mcp_vectors_communities"


def _make_community_point_id(root_id: str, graph_version: int, build_id: str, community_id: str) -> str:
    """Generate a deterministic UUID v4-formatted point ID for a community report.

    Qdrant requires point IDs to be either unsigned integers or RFC 4122 UUID
    strings.  Formatting the MD5 digest as a UUID satisfies that constraint while
    keeping the ID deterministic and collision-resistant.
    """
    hex_digest = hashlib.md5(f"{root_id}|{graph_version}|{build_id}|{community_id}".encode()).hexdigest()
    return str(uuid.UUID(hex=hex_digest))


# ---------------------------------------------------------------------------
# QdrantCommunities
# ---------------------------------------------------------------------------


class QdrantCommunities:
    """Manages a dedicated Qdrant collection for community vectors."""

    def __init__(self, url: str | None = None, api_key: str | None = None):
        self.url = url
        self.api_key = api_key
        self.collection_name = COMMUNITIES_COLLECTION
        self._client: AsyncQdrantClient | None = None
        self._initialized = False
        self.vector_size: int | None = None

    async def initialize(self, embedding_dimension: int) -> None:
        """Initialize clients and ensure the collection exists."""
        self.vector_size = embedding_dimension
        if self.url:
            logger.info(f"QdrantCommunities: connecting to Qdrant at {self.url}")
            self._client = AsyncQdrantClient(url=self.url, api_key=self.api_key)
        else:
            logger.info("QdrantCommunities: using in-memory Qdrant storage")
            self._client = AsyncQdrantClient(":memory:")
        await self.ensure_collection()
        self._initialized = True
        logger.info(f"QdrantCommunities initialized: {self.collection_name}, dim={self.vector_size}")

    async def ensure_collection(self) -> None:
        """Ensure the community collection exists with correct config.  Never recreates."""
        try:
            info = await self._client.get_collection(self.collection_name)

            # Collection exists — validate dimensions.
            actual_size: int | None = None
            try:
                if hasattr(info, "config") and hasattr(info.config, "params"):
                    params = info.config.params
                    if hasattr(params, "vectors"):
                        vectors = params.vectors
                        if hasattr(vectors, "size"):
                            actual_size = vectors.size
                        elif isinstance(vectors, dict) and "size" in vectors:
                            actual_size = vectors["size"]
                if actual_size is None:
                    info_dict = info.model_dump() if hasattr(info, "model_dump") else {}
                    vectors_config = info_dict.get("config", {}).get("params", {}).get("vectors", {})
                    if isinstance(vectors_config, dict):
                        actual_size = vectors_config.get("size")
            except Exception as ex:
                logger.warning(f"QdrantCommunities: could not extract vector size: {ex}")

            if actual_size is not None and actual_size != self.vector_size:
                raise CommunityCollectionConfigError(
                    f"Community collection dimension mismatch: expected {self.vector_size}, got {actual_size}. "
                    f"Delete the '{COMMUNITIES_COLLECTION}' collection manually and restart."
                )
            logger.info(f"QdrantCommunities: collection exists: {self.collection_name} (dim={actual_size})")

        except CommunityCollectionConfigError:
            raise
        except Exception as e:
            error_str = str(e).lower()
            is_not_found = (
                "not found" in error_str
                or "404" in error_str
                or "doesn't exist" in error_str
                or "does not exist" in error_str
            )
            if is_not_found:
                logger.info(f"QdrantCommunities: creating collection {self.collection_name} dim={self.vector_size}")
                try:
                    await self._client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
                    )
                    logger.info(f"QdrantCommunities: collection created: {self.collection_name}")
                except Exception as create_err:
                    create_str = str(create_err).lower()
                    if "already exists" in create_str or "409" in create_str:
                        logger.info("QdrantCommunities: collection created concurrently")
                    else:
                        raise
                await self._ensure_community_payload_indexes()
            else:
                raise

    async def _ensure_community_payload_indexes(self) -> None:
        """Create payload indexes for efficient filtering (best-effort)."""
        fields = {
            "root_id": models.PayloadSchemaType.KEYWORD,
            "graph_version": models.PayloadSchemaType.INTEGER,
            "build_id": models.PayloadSchemaType.KEYWORD,
            "community_id": models.PayloadSchemaType.KEYWORD,
            "level": models.PayloadSchemaType.INTEGER,
        }
        for field_name, schema in fields.items():
            try:
                await self._client.create_payload_index(
                    self.collection_name, field_name, field_schema=schema
                )
            except Exception as e:
                logger.debug(f"QdrantCommunities: payload index unavailable/exists for {field_name}: {e}")

    async def upsert_generation(
        self,
        root_id: str,
        graph_version: int,
        build_id: str,
        community_reports: list[dict],
    ) -> None:
        """Upsert a set of community reports for a named generation.

        Each report dict must have a ``vector`` key (list[float]) and a
        ``community_id`` key; all other keys are stored as payload.
        """
        points = []
        for report in community_reports:
            community_id = report.get("community_id", "")
            vector = report["vector"]
            point_id = _make_community_point_id(root_id, graph_version, build_id, community_id)
            payload = {k: v for k, v in report.items() if k != "vector"}
            payload["root_id"] = root_id
            payload["graph_version"] = graph_version
            payload["build_id"] = build_id
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        logger.info(
            f"QdrantCommunities.upsert_generation: starting "
            f"reason=store_community_reports collection={self.collection_name} "
            f"root_id={root_id!r} graph_version={graph_version} build_id={build_id!r} "
            f"report_count={len(points)}"
        )
        try:
            batch_size = 100
            for i in range(0, len(points), batch_size):
                batch = points[i : i + batch_size]
                await self._client.upsert(collection_name=self.collection_name, points=batch)
        except Exception as e:
            error_str = str(e).lower()
            if (
                "not found" in error_str
                or "404" in error_str
                or "doesn't exist" in error_str
                or "does not exist" in error_str
            ):
                raise CollectionMissingError(root_id) from e
            raise

        logger.info(
            f"QdrantCommunities: upserted {len(points)} reports "
            f"root_id={root_id!r}, version={graph_version}, build_id={build_id!r}"
        )

    async def search(
        self,
        root_id: str,
        query_vector: list[float],
        committed_version: int,
        committed_build_id: str,
        limit: int = 5,
    ) -> list[dict]:
        """ANN search restricted to the committed generation.

        Returns payload dicts with ``score`` added, sorted by score desc then
        ``community_id`` for determinism.

        Raises :class:`CollectionMissingError` if the collection is gone.
        """
        try:
            search_filter = Filter(
                must=[
                    FieldCondition(key="root_id", match=MatchValue(value=root_id)),
                    FieldCondition(key="graph_version", match=MatchValue(value=committed_version)),
                    FieldCondition(key="build_id", match=MatchValue(value=committed_build_id)),
                ]
            )
            response = await self._client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                query_filter=search_filter,
                with_payload=True,
            )
            hits = response.points

            results = []
            for hit in hits:
                payload = dict(hit.payload or {})
                payload["score"] = hit.score
                results.append(payload)

            results.sort(key=lambda x: (-x.get("score", 0.0), x.get("community_id", "")))
            return results
        except Exception as e:
            error_str = str(e).lower()
            if (
                "not found" in error_str
                or "404" in error_str
                or "doesn't exist" in error_str
                or "does not exist" in error_str
            ):
                raise CollectionMissingError(root_id)
            raise

    async def list_by_root(
        self,
        root_id: str,
        committed_version: int,
        committed_build_id: str,
        level: int | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List community reports for the committed generation.

        Optionally filter by ``level``.  Results are sorted by
        ``(level, community_id)`` for determinism.

        Raises :class:`CollectionMissingError` if the collection is gone.
        """
        try:
            must = [
                FieldCondition(key="root_id", match=MatchValue(value=root_id)),
                FieldCondition(key="graph_version", match=MatchValue(value=committed_version)),
                FieldCondition(key="build_id", match=MatchValue(value=committed_build_id)),
            ]
            if level is not None:
                must.append(FieldCondition(key="level", match=MatchValue(value=level)))

            scroll_filter = Filter(must=must)
            all_points = []
            offset = None

            while len(all_points) < limit:
                page_limit = min(100, limit - len(all_points))
                result = await self._client.scroll(
                    collection_name=self.collection_name,
                    limit=page_limit,
                    offset=offset,
                    scroll_filter=scroll_filter,
                    with_payload=True,
                    with_vectors=False,
                )
                batch, offset = result
                all_points.extend(batch)
                if offset is None or not batch:
                    break

            payloads = [dict(p.payload or {}) for p in all_points]
            payloads.sort(key=lambda x: (x.get("level", 0), x.get("community_id", "")))
            return payloads
        except Exception as e:
            error_str = str(e).lower()
            if (
                "not found" in error_str
                or "404" in error_str
                or "doesn't exist" in error_str
                or "does not exist" in error_str
            ):
                raise CollectionMissingError(root_id)
            raise

    async def get_by_id(
        self,
        root_id: str,
        community_id: str,
        committed_version: int,
        committed_build_id: str,
    ) -> dict | None:
        """Retrieve a single community report by its natural key.

        Returns the payload dict or ``None`` if not found.
        Raises :class:`CollectionMissingError` if the collection is gone.
        """
        try:
            point_id = _make_community_point_id(root_id, committed_version, committed_build_id, community_id)
            results = await self._client.retrieve(
                collection_name=self.collection_name,
                ids=[point_id],
                with_payload=True,
                with_vectors=False,
            )
            if not results:
                return None
            return dict(results[0].payload or {})
        except Exception as e:
            error_str = str(e).lower()
            if (
                "not found" in error_str
                or "404" in error_str
                or "doesn't exist" in error_str
                or "does not exist" in error_str
            ):
                raise CollectionMissingError(root_id)
            raise

    async def delete_generation(self, root_id: str, graph_version: int, build_id: str) -> None:
        """Delete all community points for a specific generation (best-effort)."""
        try:
            delete_filter = Filter(
                must=[
                    FieldCondition(key="root_id", match=MatchValue(value=root_id)),
                    FieldCondition(key="graph_version", match=MatchValue(value=graph_version)),
                    FieldCondition(key="build_id", match=MatchValue(value=build_id)),
                ]
            )
            selector = models.FilterSelector(filter=delete_filter)
            await self._client.delete(collection_name=self.collection_name, points_selector=selector)
            logger.info(
                f"QdrantCommunities: deleted generation root_id={root_id!r}, "
                f"version={graph_version}, build_id={build_id!r}"
            )
        except Exception as e:
            logger.warning(f"QdrantCommunities: delete_generation failed (best-effort): {e}")

    async def delete_all_except(self, root_id: str, keep_version: int, keep_build_id: str) -> None:
        """Delete all community points for root_id that are not the committed generation.

        This is best-effort: exceptions are logged and swallowed.
        """
        try:
            # Scroll all points for this root, collect IDs to delete.
            scroll_filter = Filter(
                must=[FieldCondition(key="root_id", match=MatchValue(value=root_id))]
            )
            ids_to_delete: list = []
            offset = None

            while True:
                result = await self._client.scroll(
                    collection_name=self.collection_name,
                    limit=1000,
                    offset=offset,
                    scroll_filter=scroll_filter,
                    with_payload=["graph_version", "build_id"],
                    with_vectors=False,
                )
                batch, offset = result
                for point in batch:
                    payload = point.payload or {}
                    if payload.get("graph_version") != keep_version or payload.get("build_id") != keep_build_id:
                        ids_to_delete.append(point.id)
                if offset is None or not batch:
                    break

            if ids_to_delete:
                selector = models.PointIdsList(points=ids_to_delete)
                await self._client.delete(collection_name=self.collection_name, points_selector=selector)
                logger.info(
                    f"QdrantCommunities: deleted {len(ids_to_delete)} stale points "
                    f"root_id={root_id!r}, kept version={keep_version}, build_id={keep_build_id!r}"
                )
        except Exception as e:
            logger.warning(f"QdrantCommunities: delete_all_except failed (best-effort): {e}")

    async def all_points_exist(
        self,
        root_id: str,
        graph_version: int,
        build_id: str,
        community_ids: list[str],
    ) -> bool:
        """Return True if every specified community_id has a committed report point.

        Uses deterministic point IDs so no payload scan is needed.
        Returns False on any retrieval error (safe degradation).
        """
        if not community_ids:
            return False
        point_ids = [
            _make_community_point_id(root_id, graph_version, build_id, cid)
            for cid in community_ids
        ]
        try:
            results = await self._client.retrieve(
                collection_name=self.collection_name,
                ids=point_ids,
                with_payload=False,
                with_vectors=False,
            )
            return len(results) == len(point_ids)
        except Exception as e:
            logger.debug(f"QdrantCommunities.all_points_exist: retrieval failed: {e}")
            return False

    async def search_filtered(
        self,
        root_id: str,
        query_vector: list[float],
        committed_version: int,
        committed_build_id: str,
        community_ids: list[str],
        limit: int = 5,
    ) -> list[dict]:
        """Vector search filtered to a specific set of community_ids.

        Returns the same payload dicts as :meth:`search`.
        Returns an empty list on error (safe degradation).
        """
        if not community_ids:
            return []
        try:
            must_conditions = [
                FieldCondition(key="root_id", match=MatchValue(value=root_id)),
                FieldCondition(key="graph_version", match=MatchValue(value=committed_version)),
                FieldCondition(key="build_id", match=MatchValue(value=committed_build_id)),
                FieldCondition(key="community_id", match=models.MatchAny(any=community_ids)),
            ]
            results = await self._client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=Filter(must=must_conditions),
                limit=limit,
                with_payload=True,
            )
            return [dict(r.payload or {}) | {"score": r.score} for r in results]
        except Exception as e:
            logger.warning(f"QdrantCommunities.search_filtered failed: {e}")
            return []

    async def close(self) -> None:
        """Close Qdrant clients (idempotent)."""
        if self._client:
            await self._client.close()
            self._client = None
        self._initialized = False


# ---------------------------------------------------------------------------
# QdrantEntities
# ---------------------------------------------------------------------------

ENTITIES_COLLECTION = "mcp_vectors_entities"


def _make_entity_point_id(entity_id: str, root_id: str) -> str:
    """Deterministic UUID for an entity point."""
    hex_digest = hashlib.md5(f"{entity_id}|{root_id}".encode()).hexdigest()
    return str(uuid.UUID(hex=hex_digest))


class QdrantEntities:
    """Manages a dedicated Qdrant collection for entity embeddings."""

    def __init__(self, url: str | None = None, api_key: str | None = None):
        self.url = url
        self.api_key = api_key
        self.collection_name = ENTITIES_COLLECTION
        self._client: AsyncQdrantClient | None = None
        self._initialized = False
        self.vector_size: int | None = None

    async def initialize(self, embedding_dimension: int) -> None:
        """Initialize client and ensure collection exists."""
        self.vector_size = embedding_dimension
        if self.url:
            self._client = AsyncQdrantClient(url=self.url, api_key=self.api_key)
        else:
            self._client = AsyncQdrantClient(":memory:")
        await self._ensure_collection()
        self._initialized = True
        logger.info(f"QdrantEntities initialized: {self.collection_name}, dim={self.vector_size}")

    async def _ensure_collection(self) -> None:
        """Ensure the entity collection exists with correct config. Never recreates."""
        try:
            info = await self._client.get_collection(self.collection_name)
            actual_size: int | None = None
            try:
                if hasattr(info, "config") and hasattr(info.config, "params"):
                    params = info.config.params
                    if hasattr(params, "vectors"):
                        vectors = params.vectors
                        if hasattr(vectors, "size"):
                            actual_size = vectors.size
                        elif isinstance(vectors, dict) and "size" in vectors:
                            actual_size = vectors["size"]
                if actual_size is None:
                    info_dict = info.model_dump() if hasattr(info, "model_dump") else {}
                    vectors_config = info_dict.get("config", {}).get("params", {}).get("vectors", {})
                    if isinstance(vectors_config, dict):
                        actual_size = vectors_config.get("size")
            except Exception as ex:
                logger.warning(f"QdrantEntities: could not extract vector size: {ex}")
            logger.info(f"QdrantEntities: collection exists: {self.collection_name} (dim={actual_size})")
        except Exception as e:
            error_str = str(e).lower()
            is_not_found = (
                "not found" in error_str
                or "404" in error_str
                or "doesn't exist" in error_str
                or "does not exist" in error_str
            )
            if is_not_found:
                logger.info(f"QdrantEntities: creating collection {self.collection_name} dim={self.vector_size}")
                try:
                    await self._client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
                    )
                    logger.info(f"QdrantEntities: collection created: {self.collection_name}")
                except Exception as create_err:
                    create_str = str(create_err).lower()
                    if "already exists" in create_str or "409" in create_str:
                        logger.info("QdrantEntities: collection created concurrently")
                    else:
                        raise
                await self._ensure_entity_payload_indexes()
            else:
                raise

    async def _ensure_entity_payload_indexes(self) -> None:
        """Create payload indexes for efficient filtering (best-effort)."""
        fields = {
            "entity_id": models.PayloadSchemaType.KEYWORD,
            "root_id": models.PayloadSchemaType.KEYWORD,
            "name": models.PayloadSchemaType.KEYWORD,
            "type": models.PayloadSchemaType.KEYWORD,
        }
        for field_name, schema in fields.items():
            try:
                await self._client.create_payload_index(
                    self.collection_name, field_name, field_schema=schema
                )
            except Exception as e:
                logger.debug(f"QdrantEntities: payload index unavailable/exists for {field_name}: {e}")

    async def upsert(
        self,
        entity_id: str,
        root_id: str,
        name: str,
        type_: str,
        embedding: list[float],
    ) -> None:
        """Upsert one entity point. Idempotent via deterministic point ID."""
        if not self._initialized:
            await self.initialize(len(embedding))
        point_id = _make_entity_point_id(entity_id, root_id)
        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload={"entity_id": entity_id, "root_id": root_id, "name": name, "type": type_},
        )
        await self._client.upsert(collection_name=self.collection_name, points=[point])

    async def search(
        self,
        root_id: str,
        query_embedding: list[float],
        limit: int = 20,
    ) -> list[dict]:
        """ANN search for top-K entities most similar to query_embedding.

        Returns list of dicts with keys: entity_id, name, type, score.
        """
        if not self._initialized:
            raise RuntimeError("QdrantEntities not initialized")
        search_filter = Filter(
            must=[FieldCondition(key="root_id", match=MatchValue(value=root_id))]
        )
        try:
            response = await self._client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                limit=limit,
                query_filter=search_filter,
                with_payload=True,
            )
        except Exception as e:
            error_str = str(e).lower()
            if (
                "not found" in error_str
                or "404" in error_str
                or "doesn't exist" in error_str
                or "does not exist" in error_str
            ):
                return []
            raise
        results = []
        for hit in response.points:
            payload = hit.payload or {}
            results.append({
                "entity_id": payload.get("entity_id", ""),
                "name": payload.get("name", ""),
                "type": payload.get("type", ""),
                "score": hit.score,
            })
        return results

    async def delete_by_root_id(self, root_id: str) -> None:
        """Delete all entity points for root_id (used by clear_index)."""
        if not self._initialized:
            return
        try:
            delete_filter = Filter(
                must=[FieldCondition(key="root_id", match=MatchValue(value=root_id))]
            )
            await self._client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(filter=delete_filter),
            )
            logger.info(f"QdrantEntities: deleted all points for root_id={root_id!r}")
        except Exception as e:
            logger.warning(f"QdrantEntities: delete_by_root_id failed (best-effort): {e}")

    async def delete_by_entity_ids(self, root_id: str, entity_ids: list[str]) -> None:
        """Delete specific entity points by their entity_ids (reserved for future use)."""
        if not entity_ids or not self._initialized:
            return
        try:
            point_ids = [_make_entity_point_id(eid, root_id) for eid in entity_ids]
            await self._client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=point_ids),
            )
        except Exception as e:
            logger.warning(f"QdrantEntities: delete_by_entity_ids failed (best-effort): {e}")

    async def close(self) -> None:
        """Close Qdrant client (idempotent)."""
        if self._client:
            await self._client.close()
            self._client = None
        self._initialized = False
