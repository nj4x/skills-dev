"""Payload metadata helpers for backwards-compatible mcp-vectors chunks."""

from __future__ import annotations

import datetime as _dt
import hashlib
from pathlib import Path
from typing import Optional

from .paths import PathPolicy

SCHEMA_NAME = "mcp-vectors.chunk.v2"
METADATA_VERSION = 2


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def build_chunk_payload_v2(
    *,
    file_path: str,
    file_name: str,
    chunk: dict,
    file_metadata: Optional[dict] = None,
    root_path: str | None = None,
    index_run_id: str | None = None,
    indexed_at: float | str | None = None,
) -> dict:
    """Build a metadata v2 payload while preserving existing v1 fields."""
    file_metadata = file_metadata or {}
    info = PathPolicy.info(file_path, root_path)
    chunk_text = chunk.get("text", "")
    extension = Path(file_path).suffix.lower()
    payload = {
        # v1 compatibility fields
        "file_path": info.path_key,
        "file_name": file_name,
        "chunk_id": chunk.get("chunk_id", 0),
        "chunk_text": chunk_text,
        "start_char": chunk.get("start_char", 0),
        "end_char": chunk.get("end_char", len(chunk_text)),
        # v2 fields
        "metadata_version": METADATA_VERSION,
        "schema": SCHEMA_NAME,
        "doc_id": info.path_key,
        "path_key": info.path_key,
        "display_path": info.display_path,
        "relative_path": info.relative_path,
        "root_path": info.root_path,
        "root_id": info.root_id,
        "extension": extension,
        "file_type": file_metadata.get("file_type") or file_metadata.get("type") or extension.lstrip(".") or "text",
        "file_hash": file_metadata.get("file_hash"),
        "file_size": file_metadata.get("file_size"),
        "mtime_ns": file_metadata.get("mtime_ns"),
        "modified_time": file_metadata.get("modified_time"),
        "indexed_at": (
            indexed_at if indexed_at is not None
            else _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "indexed_time": file_metadata.get("indexed_time"),
        "index_run_id": index_run_id,
        "chunk_hash": stable_hash(chunk_text),
        "chunk_count": file_metadata.get("chunk_count"),
    }
    for key, value in file_metadata.items():
        payload.setdefault(key, value)
    return payload


def build_chunk_payload_v3(
    *,
    # --- all v2 params ---
    file_path: str,
    file_name: str,
    chunk: dict,
    file_metadata: Optional[dict] = None,
    root_path: str | None = None,
    index_run_id: str | None = None,
    indexed_at: float | str | None = None,
    # --- v3-only params ---
    entity_names: list | None = None,
    imported_modules: list | None = None,
    called_symbols: list | None = None,
    parent_symbol: str | None = None,
    symbol_type: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
) -> dict:
    """Schema v3: extends v2 with entity/graph annotations and line numbers."""
    payload = build_chunk_payload_v2(
        file_path=file_path,
        file_name=file_name,
        chunk=chunk,
        file_metadata=file_metadata,
        root_path=root_path,
        index_run_id=index_run_id,
        indexed_at=indexed_at,
    )
    # Override version fields
    payload["metadata_version"] = 3
    payload["schema"] = "mcp-vectors.chunk.v3"
    # Add new fields
    payload["entity_names"]     = entity_names or []
    payload["imported_modules"] = imported_modules or []
    payload["called_symbols"]   = called_symbols or []
    payload["parent_symbol"]    = parent_symbol
    payload["symbol_type"]      = symbol_type
    payload["line_start"]       = line_start
    payload["line_end"]         = line_end
    return payload


def get_metadata_version(payload: dict) -> int:
    return int(payload.get("metadata_version", 1))


def is_v2_payload(payload: dict) -> bool:
    return int(payload.get("metadata_version", 1)) >= 2


def extract_file_record_from_payload(payload: dict) -> dict:
    """Extract file-level metadata from either v1 or v2 payloads."""
    file_path = payload.get("path_key") or payload.get("file_path") or ""
    path_key = payload.get("path_key") or (PathPolicy.path_key(file_path) if file_path else "")
    return {
        "file_path": file_path or path_key,
        "path_key": path_key,
        "file_name": payload.get("file_name") or Path(file_path).name,
        "display_path": payload.get("display_path") or file_path or path_key,
        "relative_path": payload.get("relative_path"),
        "root_path": payload.get("root_path"),
        "root_id": payload.get("root_id"),
        "file_type": payload.get("file_type"),
        "extension": payload.get("extension") or Path(file_path).suffix.lower(),
        "file_hash": payload.get("file_hash"),
        "file_size": payload.get("file_size"),
        "mtime_ns": payload.get("mtime_ns"),
        "last_updated": payload.get("modified_time") or payload.get("indexed_at") or payload.get("indexed_time"),
        "metadata_version": payload.get("metadata_version", 1),
        "legacy_metadata": not is_v2_payload(payload),
        "chunk_count": payload.get("chunk_count"),
    }
