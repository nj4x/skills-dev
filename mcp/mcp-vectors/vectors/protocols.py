"""Protocol interfaces for vector and community stores."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from .qdrant import SearchResult


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """Async protocol for chunk-vector storage."""

    def update_vector_size(self, new_size: int) -> None: ...

    async def initialize(self) -> None: ...

    async def upsert_chunks(
        self,
        file_path: str,
        file_name: str,
        chunks: list[dict],
        embeddings: list[list[float]],
        file_metadata: Optional[dict] = None,
        root_path: str | None = None,
        index_run_id: str | None = None,
    ) -> int: ...

    async def update_chunk_entities(self, file_path: str, chunks: list[dict]) -> None: ...

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
    ) -> list[SearchResult]: ...

    async def get_points_by_ids(self, point_ids: list[str]) -> list[dict]: ...

    async def list_indexed_files(
        self,
        skip: int = 0,
        limit: int = 100,
        base_dirs: Optional[list[str]] = None,
        max_scan_points: Optional[int] = None,
    ) -> dict: ...

    async def get_file_metadata_summary(self, base_path: Optional[str] = None) -> dict: ...

    async def is_path_indexed(self, path: str) -> bool: ...

    async def delete_document_by_path_key(self, path_key: str) -> int: ...

    async def delete_document_chunks_from(self, path_key: str, min_chunk_id: int) -> int: ...

    async def remap_root(self, source_root_id: str, dest_root_id: str, dest_root_path: str) -> int: ...

    async def delete_root(self, root_id: str) -> int: ...

    async def scroll_points_bounded(
        self,
        *,
        with_payload: bool | list[str] = True,
        scroll_filter=None,
        page_size: Optional[int] = None,
        max_points: Optional[int] = None,
    ) -> dict: ...

    async def audit_payloads_for_secrets(
        self,
        policy,
        max_scan_points: Optional[int] = None,
        include_content_scan: bool = False,
    ) -> dict: ...

    async def get_stats(self) -> dict: ...

    async def reset_collection(self) -> dict: ...

    async def close(self) -> None: ...


@runtime_checkable
class CommunityVectorStoreProtocol(Protocol):
    """Async protocol for community-report vector storage."""

    async def initialize(self, embedding_dimension: int) -> None: ...

    async def ensure_collection(self) -> None: ...

    async def upsert_generation(
        self,
        root_id: str,
        graph_version: int,
        build_id: str,
        community_reports: list[dict],
    ) -> None: ...

    async def search(
        self,
        root_id: str,
        query_vector: list[float],
        committed_version: int,
        committed_build_id: str,
        limit: int = 5,
    ) -> list[dict]: ...

    async def list_by_root(
        self,
        root_id: str,
        committed_version: int,
        committed_build_id: str,
        level: int | None = None,
        limit: int = 50,
    ) -> list[dict]: ...

    async def get_by_id(
        self,
        root_id: str,
        community_id: str,
        committed_version: int,
        committed_build_id: str,
    ) -> dict | None: ...

    async def delete_generation(self, root_id: str, graph_version: int, build_id: str) -> None: ...

    async def delete_all_except(self, root_id: str, keep_version: int, keep_build_id: str) -> None: ...

    async def close(self) -> None: ...
