import re

from vectors.metadata import build_chunk_payload_v2, extract_file_record_from_payload, is_v2_payload

_ISO_UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")

_CHUNK_KWARGS = dict(
    file_path="/tmp/project/src/app.py",
    file_name="app.py",
    chunk={"chunk_id": 0, "text": "print('hi')", "start_char": 0, "end_char": 11},
    file_metadata={"file_type": "python", "file_hash": "abc", "file_size": 11, "chunk_count": 1},
    root_path="/tmp/project",
    index_run_id="run-1",
)


def test_build_payload_v2_preserves_v1_fields():
    payload = build_chunk_payload_v2(**_CHUNK_KWARGS)
    assert payload["file_path"].endswith("/tmp/project/src/app.py")
    assert payload["chunk_text"] == "print('hi')"
    assert payload["metadata_version"] == 2
    assert payload["relative_path"] == "src/app.py"
    assert payload["root_id"].endswith("/tmp/project")
    assert is_v2_payload(payload)


def test_extract_file_record_from_v1_payload():
    record = extract_file_record_from_payload({"file_path": "/tmp/legacy.md", "file_name": "legacy.md", "chunk_id": 1})
    assert record["file_path"] == "/tmp/legacy.md"
    assert record["metadata_version"] == 1
    assert record["legacy_metadata"] is True


# ---------------------------------------------------------------------------
# Timestamp normalization tests
# ---------------------------------------------------------------------------

def test_indexed_at_default_is_utc_iso_string():
    """When indexed_at is not supplied, the payload must contain a UTC ISO+Z string."""
    payload = build_chunk_payload_v2(**_CHUNK_KWARGS)
    val = payload["indexed_at"]
    assert isinstance(val, str), f"Expected str, got {type(val).__name__}: {val!r}"
    assert _ISO_UTC_Z_RE.match(val), f"indexed_at does not match UTC ISO+Z format: {val!r}"


def test_indexed_at_passthrough_float_is_preserved():
    """When a float indexed_at is supplied by the caller it must be stored as-is."""
    sentinel = 1_700_000_000.5
    payload = build_chunk_payload_v2(**_CHUNK_KWARGS, indexed_at=sentinel)
    assert payload["indexed_at"] == sentinel


def test_indexed_at_passthrough_string_is_preserved():
    """When a string indexed_at is supplied by the caller it must be stored as-is."""
    sentinel = "2024-01-15T08:00:00Z"
    payload = build_chunk_payload_v2(**_CHUNK_KWARGS, indexed_at=sentinel)
    assert payload["indexed_at"] == sentinel
