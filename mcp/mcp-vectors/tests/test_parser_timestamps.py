"""
Regression tests: DocumentParser.parse_file() must store modified_time as a
timezone-aware UTC ISO 8601 string (ending in 'Z'), not a naive local-time string.
"""

import re
import tempfile
from pathlib import Path

_ISO_UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def test_modified_time_is_utc_iso_string():
    """parse_file must produce a UTC ISO+Z modified_time, never a naive local datetime."""
    from vectors.parser import DocumentParser

    parser = DocumentParser()
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("hello world\n")
        tmp_path = Path(f.name)

    try:
        doc = parser.parse_file(tmp_path)
        val = doc.modified_time
        assert isinstance(val, str), f"Expected str, got {type(val).__name__}: {val!r}"
        assert _ISO_UTC_Z_RE.match(val), (
            f"modified_time does not match UTC ISO+Z format: {val!r}. "
            "Got a naive or local datetime — must be UTC-aware."
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def test_modified_time_ends_with_Z():
    """Shorthand check: modified_time ends with 'Z' (UTC suffix)."""
    from vectors.parser import DocumentParser

    parser = DocumentParser()
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write("# heading\n\nsome text\n")
        tmp_path = Path(f.name)

    try:
        doc = parser.parse_file(tmp_path)
        assert doc.modified_time.endswith("Z"), (
            f"modified_time must end with 'Z' for UTC. Got: {doc.modified_time!r}"
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def test_modified_time_contains_T_separator():
    """modified_time must use T separator (ISO 8601)."""
    from vectors.parser import DocumentParser

    parser = DocumentParser()
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def foo(): pass\n")
        tmp_path = Path(f.name)

    try:
        doc = parser.parse_file(tmp_path)
        assert "T" in doc.modified_time, (
            f"modified_time must contain 'T' separator. Got: {doc.modified_time!r}"
        )
    finally:
        tmp_path.unlink(missing_ok=True)
