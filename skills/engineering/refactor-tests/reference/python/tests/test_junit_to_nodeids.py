"""Seam tests for the refactor-tests JUnit-to-node-id helper.

Run: uv run --with pytest pytest reference/python/tests/test_junit_to_nodeids.py
"""
import json
import subprocess
import sys
from pathlib import Path

from junit_to_nodeids import convert, read_collected  # conftest.py puts HELPERS on sys.path

HELPERS = Path(__file__).resolve().parent.parent

COLLECTED = """\
tests/pkg/test_a.py::test_one
tests/pkg/test_a.py::test_two
tests/pkg/test_b.py::TestX::test_three[1]
tests/pkg/test_b.py::test_four
tests/pkg/test_b.py::test_five

5 tests collected in 0.01s
"""

JUNIT = """\
<testsuites><testsuite name="pytest">
 <testcase classname="tests.pkg.test_a" name="test_one"/>
 <testcase classname="tests.pkg.test_a" name="test_two"><failure message="x"/></testcase>
 <testcase classname="tests.pkg.test_b.TestX" name="test_three[1]"><error message="e"/></testcase>
 <testcase classname="tests.pkg.test_b" name="test_four"><skipped message="s"/></testcase>
 <testcase classname="tests.other" name="test_gone"/>
</testsuite></testsuites>
"""


def test_collect_only_output_keeps_node_ids_and_drops_summary():
    assert read_collected(COLLECTED + "tests/pkg/test_a.py::test_one\n") == [
        "tests/pkg/test_a.py::test_one",
        "tests/pkg/test_a.py::test_two",
        "tests/pkg/test_b.py::TestX::test_three[1]",
        "tests/pkg/test_b.py::test_four",
        "tests/pkg/test_b.py::test_five",
    ]


def test_outcomes_map_to_node_ids_error_is_failed_and_unknown_is_unmapped():
    outcomes = {
        "tests.pkg.test_a::test_one": "passed",
        "tests.pkg.test_a::test_two": "failed",
        "tests.pkg.test_b.TestX::test_three[1]": "error",
        "tests.pkg.test_b::test_four": "skipped",
        "tests.other::test_gone": "passed",
    }
    r = convert(outcomes, read_collected(COLLECTED))
    assert r["passed"] == ["tests/pkg/test_a.py::test_one"]
    assert r["failed"] == ["tests/pkg/test_a.py::test_two", "tests/pkg/test_b.py::TestX::test_three[1]"]
    assert r["skipped"] == ["tests/pkg/test_b.py::test_four"]
    assert r["unmapped"] == ["tests.other::test_gone"]
    assert r["counts"] == {"passed": 1, "failed": 2, "skipped": 1, "unmapped": 1}


def test_cli_reads_junit_and_writes_out(tmp_path):
    (tmp_path / "run.xml").write_text(JUNIT)
    (tmp_path / "collected.txt").write_text(COLLECTED)
    out = tmp_path / "ids.json"
    proc = subprocess.run(
        [sys.executable, str(HELPERS / "junit_to_nodeids.py"), "--junit", str(tmp_path / "run.xml"),
         "--collected", str(tmp_path / "collected.txt"), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    r = json.loads(out.read_text())
    assert r["counts"] == {"passed": 1, "failed": 2, "skipped": 1, "unmapped": 1}


def test_ambiguous_collected_ids_exit_2_and_write_nothing(tmp_path):
    (tmp_path / "run.xml").write_text(JUNIT)
    (tmp_path / "collected.txt").write_text("tests/a.py::test_x\ntests/a/__init__.py::x\ntests.a.py::test_x\n")
    out = tmp_path / "ids.json"
    proc = subprocess.run(
        [sys.executable, str(HELPERS / "junit_to_nodeids.py"), "--junit", str(tmp_path / "run.xml"),
         "--collected", str(tmp_path / "collected.txt"), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "ambiguous" in proc.stderr
    assert not out.exists()
