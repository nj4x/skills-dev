from vectors.metadata import build_chunk_payload_v3, get_metadata_version

_MINIMAL_KWARGS = dict(
    file_path="/tmp/project/src/app.py",
    file_name="app.py",
    chunk={"chunk_id": 0, "text": "def foo(): pass", "start_char": 0, "end_char": 15},
    file_metadata={"file_type": "python", "file_hash": "abc", "file_size": 15, "chunk_count": 1},
    root_path="/tmp/project",
    index_run_id="run-v3",
)


def test_v3_has_all_new_fields():
    payload = build_chunk_payload_v3(
        **_MINIMAL_KWARGS,
        entity_names=["AuthService", "process_payment"],
        symbol_type="function",
        line_start=42,
        line_end=60,
    )
    assert payload["metadata_version"] == 3
    assert payload["schema"] == "mcp-vectors.chunk.v3"
    assert "AuthService" in payload["entity_names"]
    assert "process_payment" in payload["entity_names"]
    assert payload["symbol_type"] == "function"
    assert payload["line_start"] == 42
    assert payload["line_end"] == 60


def test_v3_preserves_v2_fields():
    payload = build_chunk_payload_v3(**_MINIMAL_KWARGS)
    # Core v1-compat fields must still be present
    assert payload["file_name"] == "app.py"
    assert payload["chunk_text"] == "def foo(): pass"
    assert payload["chunk_id"] == 0
    # v2 path fields
    assert payload["relative_path"] == "src/app.py"
    assert payload["file_type"] == "python"


def test_v3_defaults_empty_lists():
    payload = build_chunk_payload_v3(**_MINIMAL_KWARGS)
    assert payload["entity_names"] == []
    assert payload["imported_modules"] == []
    assert payload["called_symbols"] == []
    assert payload["parent_symbol"] is None
    assert payload["symbol_type"] is None
    assert payload["line_start"] is None
    assert payload["line_end"] is None


def test_v3_all_new_fields_populated():
    payload = build_chunk_payload_v3(
        **_MINIMAL_KWARGS,
        entity_names=["Foo"],
        imported_modules=["os", "sys"],
        called_symbols=["bar", "baz"],
        parent_symbol="MyClass",
        symbol_type="method",
        line_start=1,
        line_end=10,
    )
    assert payload["imported_modules"] == ["os", "sys"]
    assert payload["called_symbols"] == ["bar", "baz"]
    assert payload["parent_symbol"] == "MyClass"


def test_get_metadata_version():
    assert get_metadata_version({"metadata_version": 3}) == 3
    assert get_metadata_version({"metadata_version": 2}) == 2
    assert get_metadata_version({}) == 1  # default for missing field
