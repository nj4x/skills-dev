"""In-memory test adapters implementing VectorStoreProtocol and CommunityVectorStoreProtocol."""

from __future__ import annotations

import math
import time
from typing import Optional

from .metadata import oldest_indexed_at
from .paths import PathPolicy
from .qdrant import SearchResult, make_chunk_point_id


def _cosine_score(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class InMemoryVectorStore:
    """Dict-backed async façade implementing VectorStoreProtocol (for tests)."""

    def __init__(self, vector_size: int = 384) -> None:
        self.vector_size = vector_size
        self._points: list[dict] = []
        self._initialized = False

    def update_vector_size(self, new_size: int) -> None:
        self.vector_size = new_size

    async def initialize(self) -> None:
        self._initialized = True

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
        canonical = PathPolicy.path_key(file_path)
        fm = dict(file_metadata or {})
        fm.setdefault("chunk_count", len(chunks))
        now = time.time()
        for chunk, embedding in zip(chunks, embeddings):
            chunk_id = chunk["chunk_id"]
            point_id = make_chunk_point_id(canonical, chunk_id)
            # remove existing point for this id (replace semantics)
            self._points = [p for p in self._points if p["id"] != point_id]
            self._points.append({
                "id": point_id,
                "vector": embedding,
                "payload": {
                    "file_path": canonical,
                    "path_key": canonical,
                    "file_name": file_name,
                    "chunk_id": chunk_id,
                    "chunk_text": chunk.get("text", ""),
                    "start_char": chunk.get("start_char", 0),
                    "end_char": chunk.get("end_char", 0),
                    "root_path": root_path or "",
                    "root_id": PathPolicy.path_key(root_path) if root_path else "",
                    "file_type": fm.get("file_type", ""),
                    "extension": "",
                    "metadata_version": 2,
                    "indexed_at": now,
                    "indexed_time": now,
                    "file_size": fm.get("file_size", 0),
                    "file_hash": fm.get("file_hash", ""),
                    "mtime_ns": fm.get("mtime_ns", 0),
                    "modified_time": fm.get("modified_time", ""),
                    "entity_names": chunk.get("entity_names") or [],
                },
            })
        return len(chunks)

    async def update_chunk_entities(self, file_path: str, chunks: list[dict]) -> None:
        canonical = PathPolicy.path_key(file_path)
        for chunk in chunks:
            point_id = make_chunk_point_id(canonical, chunk["chunk_id"])
            for p in self._points:
                if p["id"] == point_id:
                    p["payload"]["entity_names"] = chunk.get("entity_names") or []

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
        exclude_keys = {PathPolicy.path_key(f) for f in (exclude_files or [])}
        root_id_filter = PathPolicy.path_key(root_path) if root_path else None

        scored = []
        for p in self._points:
            payload = p["payload"]
            path_key = payload.get("path_key") or payload.get("file_path", "")
            if file_filter and PathPolicy.path_key(file_filter) != path_key:
                continue
            if path_key in exclude_keys:
                continue
            if root_id_filter and payload.get("root_id") != root_id_filter:
                continue
            if extensions:
                ext = path_key.rsplit(".", 1)[-1] if "." in path_key else ""
                if f".{ext}" not in extensions and ext not in extensions:
                    continue
            if file_types:
                if payload.get("file_type") not in file_types:
                    continue
            if base_dirs and not any(PathPolicy.is_within(path_key, bd) for bd in base_dirs):
                continue
            score = _cosine_score(query_vector, p["vector"]) if p["vector"] else 0.0
            if min_score is not None and score < min_score:
                continue
            scored.append((score, p))

        scored.sort(key=lambda x: -x[0])
        results = []
        for score, p in scored[:limit]:
            payload = p["payload"]
            results.append(SearchResult(
                id=p["id"],
                score=score,
                file_path=payload.get("file_path", ""),
                file_name=payload.get("file_name", ""),
                chunk_id=payload.get("chunk_id", 0),
                chunk_text=payload.get("chunk_text", ""),
                start_char=payload.get("start_char", 0),
                end_char=payload.get("end_char", 0),
                metadata={k: v for k, v in payload.items()
                          if k not in {"file_path", "file_name", "chunk_id", "chunk_text",
                                       "start_char", "end_char"}},
            ))
        return results

    async def get_points_by_ids(self, point_ids: list[str]) -> list[dict]:
        if not point_ids:
            return []
        id_set = set(point_ids)
        return [
            {"id": p["id"], "score": 1.0, "payload": p["payload"]}
            for p in self._points if p["id"] in id_set
        ]

    async def list_indexed_files(
        self,
        skip: int = 0,
        limit: int = 100,
        base_dirs: Optional[list[str]] = None,
        max_scan_points: Optional[int] = None,
    ) -> dict:
        files: dict[str, dict] = {}
        for p in self._points:
            payload = p["payload"]
            path_key = payload.get("path_key") or payload.get("file_path", "")
            if not path_key:
                continue
            if base_dirs and not any(PathPolicy.is_within(path_key, bd) for bd in base_dirs):
                continue
            if path_key not in files:
                files[path_key] = {
                    "file_path": payload.get("file_path", path_key),
                    "path_key": path_key,
                    "file_name": payload.get("file_name", ""),
                    "root_path": payload.get("root_path", ""),
                    "root_id": payload.get("root_id", ""),
                    "file_type": payload.get("file_type", ""),
                    "extension": payload.get("extension", ""),
                    "file_hash": payload.get("file_hash", ""),
                    "file_size": payload.get("file_size", 0),
                    "mtime_ns": payload.get("mtime_ns", 0),
                    "modified_time": payload.get("modified_time", ""),
                    "last_updated": payload.get("indexed_at"),
                    "indexed_at": payload.get("indexed_at") if payload.get("indexed_at") is not None else payload.get("indexed_time"),
                    "chunk_count": 0,
                    "metadata_versions": {},
                    "metadata_version": payload.get("metadata_version", 2),
                }
            files[path_key]["chunk_count"] += 1
            version = str(payload.get("metadata_version", 2))
            mv = files[path_key]["metadata_versions"]
            mv[version] = mv.get(version, 0) + 1

        sorted_files = sorted(files.values(),
                              key=lambda x: x.get("last_updated") or 0, reverse=True)
        return {
            "files": sorted_files[skip: skip + limit],
            "total_unique_files_scanned": len(sorted_files),
            "skip": skip,
            "limit": limit,
            "scanned_points": len(self._points),
            "partial": False,
            "scan_truncated": False,
        }

    async def get_file_metadata_summary(self, base_path: Optional[str] = None) -> dict:
        listing = await self.list_indexed_files(
            skip=0, limit=10_000,
            base_dirs=[base_path] if base_path else None,
        )
        distribution: dict[str, int] = {}
        legacy_files = 0
        for file in listing["files"]:
            versions = file.get("metadata_versions", {})
            for version, count in versions.items():
                distribution[version] = distribution.get(version, 0) + count
            if "1" in versions:
                legacy_files += 1
        return {
            "file_count": listing["total_unique_files_scanned"],
            "sample_files": listing["files"][:20],
            "metadata_version_distribution": distribution,
            "legacy_file_count": legacy_files,
            "oldest_indexed_at": oldest_indexed_at(listing["files"]),
            "partial": False,
            "scan_truncated": False,
        }

    async def is_path_indexed(self, path: str) -> bool:
        canonical = PathPolicy.path_key(path)
        return any(p["payload"].get("path_key") == canonical for p in self._points)

    async def delete_document_by_path_key(self, path_key: str) -> int:
        canonical = PathPolicy.path_key(path_key)
        before = len(self._points)
        self._points = [
            p for p in self._points
            if p["payload"].get("path_key") != canonical
            and p["payload"].get("file_path") != canonical
        ]
        return before - len(self._points)

    async def remap_root(self, source_root_id: str, dest_root_id: str, dest_root_path: str) -> int:
        """Move every point tagged with source_root_id onto the destination canonical root."""
        moved = 0
        for p in self._points:
            if p["payload"].get("root_id") == source_root_id:
                p["payload"]["root_id"] = dest_root_id
                p["payload"]["root_path"] = dest_root_path
                moved += 1
        return moved

    async def delete_root(self, root_id: str) -> int:
        """Delete every point tagged with root_id. Returns the number removed."""
        before = len(self._points)
        self._points = [p for p in self._points if p["payload"].get("root_id") != root_id]
        return before - len(self._points)

    async def delete_document_chunks_from(self, path_key: str, min_chunk_id: int) -> int:
        canonical = PathPolicy.path_key(path_key)
        before = len(self._points)
        self._points = [
            p for p in self._points
            if not (
                (p["payload"].get("path_key") == canonical or p["payload"].get("file_path") == canonical)
                and p["payload"].get("chunk_id", 0) >= min_chunk_id
            )
        ]
        return before - len(self._points)

    async def scroll_points_bounded(
        self,
        *,
        with_payload: bool | list[str] = True,
        scroll_filter=None,
        page_size: Optional[int] = None,
        max_points: Optional[int] = None,
    ) -> dict:
        points = self._points if max_points is None else self._points[:max_points]
        partial = max_points is not None and len(self._points) > max_points

        class _FakePoint:
            def __init__(self, data: dict) -> None:
                self.id = data["id"]
                self.payload = data["payload"] if with_payload is True else (
                    {k: data["payload"][k] for k in (with_payload or []) if k in data["payload"]}
                    if isinstance(with_payload, list) else {}
                )

        fake_points = [_FakePoint(p) for p in points]
        return {
            "points": fake_points,
            "scanned_points": len(fake_points),
            "partial": partial,
            "scan_truncated": partial,
            "next_offset": None,
        }

    async def audit_payloads_for_secrets(
        self,
        policy,
        max_scan_points: Optional[int] = None,
        include_content_scan: bool = False,
    ) -> dict:
        points = self._points if max_scan_points is None else self._points[:max_scan_points]
        by_file: dict[str, dict] = {}
        for p in points:
            payload = p["payload"]
            reasons = policy.payload_secret_reasons(payload)
            if not reasons:
                continue
            file_path = payload.get("file_path") or ""
            if file_path not in by_file:
                by_file[file_path] = {"file_path": file_path, "reason_codes": [], "chunk_hits": 0}
            by_file[file_path]["chunk_hits"] += 1
            by_file[file_path]["reason_codes"] = list(dict.fromkeys(
                by_file[file_path]["reason_codes"] + reasons
            ))
        return {
            "files": list(by_file.values()),
            "file_count": len(by_file),
            "scanned_points": len(points),
            "partial": False,
            "scan_truncated": False,
            "content_scan": include_content_scan,
        }

    async def get_stats(self) -> dict:
        return {
            "collection_name": "in_memory",
            "total_points": len(self._points),
            "status": "green",
            "vector_size": self.vector_size,
            "storage_mode": "in-memory",
        }

    async def reset_collection(self) -> dict:
        self._points = []
        return {"success": True, "collection_name": "in_memory", "message": "Collection reset successfully"}

    async def close(self) -> None:
        self._initialized = False


class InMemoryCommunities:
    """Dict-backed async façade implementing CommunityVectorStoreProtocol (for tests)."""

    def __init__(self) -> None:
        self._reports: dict[tuple[str, int, str], list[dict]] = {}
        self._initialized = False
        self.vector_size: int | None = None

    async def initialize(self, embedding_dimension: int) -> None:
        self.vector_size = embedding_dimension
        self._initialized = True

    async def ensure_collection(self) -> None:
        pass

    async def upsert_generation(
        self,
        root_id: str,
        graph_version: int,
        build_id: str,
        community_reports: list[dict],
    ) -> None:
        key = (root_id, graph_version, build_id)
        self._reports[key] = [dict(r) for r in community_reports]

    async def search(
        self,
        root_id: str,
        query_vector: list[float],
        committed_version: int,
        committed_build_id: str,
        limit: int = 5,
    ) -> list[dict]:
        key = (root_id, committed_version, committed_build_id)
        reports = self._reports.get(key, [])
        scored = []
        for r in reports:
            vec = r.get("vector", [])
            score = _cosine_score(query_vector, vec) if vec else 0.0
            payload = {k: v for k, v in r.items() if k != "vector"}
            payload["score"] = score
            scored.append(payload)
        scored.sort(key=lambda x: (-x.get("score", 0.0), x.get("community_id", "")))
        return scored[:limit]

    async def list_by_root(
        self,
        root_id: str,
        committed_version: int,
        committed_build_id: str,
        level: int | None = None,
        limit: int = 50,
    ) -> list[dict]:
        key = (root_id, committed_version, committed_build_id)
        reports = self._reports.get(key, [])
        if level is not None:
            reports = [r for r in reports if r.get("level") == level]
        payloads = [{k: v for k, v in r.items() if k != "vector"} for r in reports]
        payloads.sort(key=lambda x: (x.get("level", 0), x.get("community_id", "")))
        return payloads[:limit]

    async def get_by_id(
        self,
        root_id: str,
        community_id: str,
        committed_version: int,
        committed_build_id: str,
    ) -> dict | None:
        key = (root_id, committed_version, committed_build_id)
        reports = self._reports.get(key, [])
        for r in reports:
            if r.get("community_id") == community_id:
                return {k: v for k, v in r.items() if k != "vector"}
        return None

    async def delete_generation(self, root_id: str, graph_version: int, build_id: str) -> None:
        self._reports.pop((root_id, graph_version, build_id), None)

    async def delete_all_except(self, root_id: str, keep_version: int, keep_build_id: str) -> None:
        to_delete = [
            k for k in self._reports
            if k[0] == root_id and (k[1] != keep_version or k[2] != keep_build_id)
        ]
        for k in to_delete:
            del self._reports[k]

    async def close(self) -> None:
        self._initialized = False
