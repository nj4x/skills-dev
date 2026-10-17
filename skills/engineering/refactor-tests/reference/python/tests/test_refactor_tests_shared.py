"""Tests for refactor_tests_shared.py: test-id parsing and the atomic JSON writer the helpers share.

Run: uv run --with pytest --with pytest-cov --with coverage pytest reference/python/tests
"""
import json

from refactor_tests_shared import is_variant, split_file, strip_params, write_atomic  # conftest.py puts HELPERS on sys.path


def test_strip_params_splits_at_first_bracket():
    assert strip_params("tests/t.py::test_a[x::y.z[1]]") == ("tests/t.py::test_a", "[x::y.z[1]]")
    assert strip_params("tests/t.py::TestK::test_a") == ("tests/t.py::TestK::test_a", "")


def test_split_file_keeps_class_and_params_in_rest():
    assert split_file("tests/t.py::TestK::test_a[p]") == ("tests/t.py", "TestK::test_a[p]")
    assert split_file("tests/t.py") == ("tests/t.py", "")


def test_is_variant_matches_exact_and_parametrized_ids_only():
    assert is_variant("tests/t.py::test_a", "tests/t.py::test_a")
    assert is_variant("tests/t.py::test_a[1]", "tests/t.py::test_a")
    assert not is_variant("tests/t.py::test_ab", "tests/t.py::test_a")
    assert not is_variant("tests/t.py::TestK::test_a", "tests/t.py::test_a")
    assert is_variant("tests/[legacy]/t.py::test_a[1]", "tests/[legacy]/t.py::test_a")
    assert is_variant("tests/[legacy]/t.py::test_a", "tests/[legacy]/t.py::test_a")


def test_write_atomic_writes_sorted_indent_one_json_and_no_temp_file(tmp_path):
    out = tmp_path / "doc.json"
    write_atomic(str(out), {"b": [1], "a": {"d": 1, "c": 2}})
    assert out.read_text(encoding="utf-8") == (
        '{\n "a": {\n  "c": 2,\n  "d": 1\n },\n "b": [\n  1\n ]\n}\n'
    )
    assert json.loads(out.read_text(encoding="utf-8"))["a"] == {"c": 2, "d": 1}
    assert list(tmp_path.iterdir()) == [out]
