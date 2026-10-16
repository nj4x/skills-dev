"""Seam tests for the refactor-tests evidence pass helpers.

Run: uv run --with pytest --with pytest-cov --with coverage pytest reference/python/tests
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parent.parent  # conftest.py puts this on sys.path

from assemble_evidence import assemble  # noqa: E402 (after conftest path setup)
from extract_arcs import extract_arcs  # noqa: E402

CALC = '''def add(a, b):
    return a + b


def div(a, b):
    if b == 0:
        raise ZeroDivisionError("b is zero")
    return a / b
'''

TESTS = '''import pytest
from pkg.calc import add, div


def test_add():
    assert add(1, 2) == 3


@pytest.mark.parametrize("a,b,r", [(4, 2, 2), (9, 3, 3)])
def test_div(a, b, r):
    assert div(a, b) == r


def test_div_zero():
    with pytest.raises(ZeroDivisionError):
        div(1, 0)


def test_broken():
    assert add(1, 1) == 3


@pytest.fixture
def needs_missing():
    raise RuntimeError("setup boom")


def test_setup_error(needs_missing):
    assert True


@pytest.mark.skip(reason="not now")
def test_skipped_at_setup():
    assert True


@pytest.fixture
def bad_teardown():
    yield
    raise RuntimeError("teardown boom")


def test_teardown_error(bad_teardown):
    assert add(2, 2) == 4
'''

SUITE_IDS = {
    "tests/test_calc.py::test_add",
    "tests/test_calc.py::test_div[4-2-2]",
    "tests/test_calc.py::test_div[9-3-3]",
    "tests/test_calc.py::test_div_zero",
    "tests/test_calc.py::test_broken",
    "tests/test_calc.py::test_setup_error",
    "tests/test_calc.py::test_skipped_at_setup",
    "tests/test_calc.py::test_teardown_error",
}


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    proj = tmp_path_factory.mktemp("proj")
    (proj / "pkg").mkdir()
    (proj / "pkg" / "__init__.py").write_text("")
    (proj / "pkg" / "calc.py").write_text(CALC)
    (proj / "tests").mkdir()
    (proj / "tests" / "test_calc.py").write_text(TESTS)
    (proj / "pytest.ini").write_text("[pytest]\ntestpaths = tests\npythonpath = .\n")
    out = proj / "out"
    out.mkdir()
    env = {**os.environ, "COVERAGE_CORE": "ctrace", "COVERAGE_FILE": str(out / ".coverage")}
    env.pop("PYTEST_CURRENT_TEST", None)
    base = [sys.executable, "-m", "pytest", "-p", "no:randomly", "-q"]
    # Exit 1 is expected: test_broken, test_setup_error fail. Anything else is a broken run.
    cov = subprocess.run(
        base + ["--cov=pkg", "--cov-branch", "--cov-context=test"],
        cwd=proj, env=env, capture_output=True, check=False,
    )
    assert cov.returncode == 1, cov.stdout + cov.stderr
    timing_env = {
        **os.environ,
        "PYTHONPATH": str(HELPERS),
        "CALLTIME_FILE": str(out / "calltime.json"),
    }
    timing = subprocess.run(
        base + ["-p", "calltime"], cwd=proj, env=timing_env, capture_output=True, check=False,
    )
    assert timing.returncode == 1, timing.stdout + timing.stderr
    return proj, out


def test_calltime_hook_writes_rows_keyed_by_nodeid_including_setup_outcomes(runs):
    _, out = runs
    rows = json.loads((out / "calltime.json").read_text())
    assert set(rows) == SUITE_IDS
    assert rows["tests/test_calc.py::test_add"]["outcome"] == "passed"
    assert rows["tests/test_calc.py::test_add"]["duration"] >= 0
    assert rows["tests/test_calc.py::test_broken"]["outcome"] == "failed"
    assert rows["tests/test_calc.py::test_setup_error"]["outcome"] == "failed"
    assert rows["tests/test_calc.py::test_skipped_at_setup"]["outcome"] == "skipped"
    assert rows["tests/test_calc.py::test_skipped_at_setup"]["duration"] is None
    # call passed, teardown failed: outcome flips to failed, call duration kept
    assert rows["tests/test_calc.py::test_teardown_error"]["outcome"] == "failed"
    assert rows["tests/test_calc.py::test_teardown_error"]["duration"] >= 0


def test_extract_arcs_emits_per_test_lines_and_arcs(runs):
    proj, out = runs
    arcs = extract_arcs(str(out / ".coverage"), root=str(proj))
    add = arcs["tests/test_calc.py::test_add"]["pkg/calc.py"]
    assert add["lines"] == [2]
    assert [-1, 2] in add["arcs"] and [2, -1] in add["arcs"]
    zero = arcs["tests/test_calc.py::test_div_zero"]["pkg/calc.py"]
    assert zero["lines"] == [6, 7]
    assert [6, 7] in zero["arcs"]
    # parametrize cases are separate contexts with the same coverage
    d1 = arcs["tests/test_calc.py::test_div[4-2-2]"]["pkg/calc.py"]
    d2 = arcs["tests/test_calc.py::test_div[9-3-3]"]["pkg/calc.py"]
    assert d1 == d2 and d1["lines"] == [6, 8]


def test_extract_arcs_keeps_only_run_contexts(runs):
    proj, out = runs
    arcs = extract_arcs(str(out / ".coverage"), root=str(proj))
    # Only tests that reached the call phase open a |run context. Setup-error and
    # setup-skipped tests have none, so they are absent here (and listed as excluded
    # in the timing file). No setup/teardown/empty-context leakage.
    assert set(arcs) == SUITE_IDS - {
        "tests/test_calc.py::test_setup_error",
        "tests/test_calc.py::test_skipped_at_setup",
    }
    assert "" not in arcs


def test_extract_arcs_fails_loudly_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_arcs(str(tmp_path / "nope.cov"))
    assert not (tmp_path / "nope.cov").exists()


def test_extract_arcs_fails_loudly_without_run_contexts(tmp_path):
    from coverage import CoverageData

    data = CoverageData(str(tmp_path / ".coverage"))
    data.add_lines({str(tmp_path / "m.py"): [1, 2]})
    data.write()
    with pytest.raises(ValueError, match="no '\\|run' contexts"):
        extract_arcs(str(tmp_path / ".coverage"))


def test_assemble_matches_schema_v1_and_lists_non_passed(runs):
    proj, out = runs
    arcs = extract_arcs(str(out / ".coverage"), root=str(proj))
    calltime = json.loads((out / "calltime.json").read_text())
    doc = assemble(
        arcs, calltime,
        tools={"coverage": "x", "pytest-cov": "y"},
        commands={"coverage": "cov cmd", "timing": "time cmd"},
    )
    assert doc["schema_version"] == 1
    assert doc["id_basis"] == "post-layout"
    assert "kill_set" not in doc  # reserved, not written in v1
    py = doc["languages"]["python"]
    assert py["status"] == "ok"
    assert py["tools"] == {"coverage": "x", "pytest-cov": "y"}
    assert py["commands"]["timing"] == "time cmd"
    assert "tests/test_calc.py::test_broken" not in py["tests"]
    assert {"id": "tests/test_calc.py::test_broken", "outcome": "failed"} in py["excluded"]
    assert {"id": "tests/test_calc.py::test_skipped_at_setup", "outcome": "skipped"} in py["excluded"]
    assert {"id": "tests/test_calc.py::test_teardown_error", "outcome": "failed"} in py["excluded"]
    assert "tests/test_calc.py::test_teardown_error" not in py["tests"]
    entry = py["tests"]["tests/test_calc.py::test_add"]
    assert entry["outcome"] == "passed"
    assert isinstance(entry["call_s"], float)
    assert entry["covered"]["pkg/calc.py"]["lines"] == [2]
    json.dumps(doc)


def test_assemble_lists_passed_test_without_coverage_context():
    calltime = {"t::a": {"outcome": "passed", "duration": 0.1}}
    doc = assemble({}, calltime, tools={}, commands={})
    py = doc["languages"]["python"]
    assert py["tests"] == {}
    assert py["excluded"] == [{"id": "t::a", "outcome": "no-coverage"}]


def test_assemble_lists_covered_test_without_timing_row():
    arcs = {"t::b": {"m.py": {"lines": [1], "arcs": [[-1, 1]]}}}
    doc = assemble(arcs, {}, tools={}, commands={})
    py = doc["languages"]["python"]
    assert py["tests"] == {}
    assert py["excluded"] == [{"id": "t::b", "outcome": "no-timing"}]


def test_assemble_degraded_status_has_no_tests():
    doc = assemble({}, {}, tools={}, commands={}, status="failed", reason="pytest-cov missing")
    py = doc["languages"]["python"]
    assert py["status"] == "failed"
    assert py["reason"] == "pytest-cov missing"
    assert py["tests"] == {}


def test_assemble_degraded_status_requires_reason():
    with pytest.raises(ValueError):
        assemble({}, {}, tools={}, commands={}, status="skipped")


def test_assemble_cli_writes_out_and_merges_existing(runs, tmp_path):
    proj, out = runs
    extract = subprocess.run(
        [sys.executable, str(HELPERS / "extract_arcs.py"), str(out / ".coverage"), "--root", str(proj)],
        capture_output=True, text=True, check=False,
    )
    assert extract.returncode == 0, extract.stderr
    arcs_file = tmp_path / "arcs.json"
    arcs_file.write_text(extract.stdout)
    target = tmp_path / "test-evidence.json"
    base_cmd = [
        sys.executable, str(HELPERS / "assemble_evidence.py"),
        "--arcs", str(arcs_file), "--calltime", str(out / "calltime.json"),
        "--tool", "coverage=7.16.2", "--command", "coverage=c",
        "--out", str(target),
    ]
    first = subprocess.run(base_cmd + ["--language", "python"], capture_output=True, check=False)
    assert first.returncode == 0, first.stderr
    second = subprocess.run(
        [sys.executable, str(HELPERS / "assemble_evidence.py"), "--calltime", str(out / "calltime.json"),
         "--status", "skipped", "--reason", "no tooling for go", "--language", "go",
         "--existing", str(target), "--out", str(target)],
        capture_output=True, check=False,
    )
    assert second.returncode == 0, second.stderr
    doc = json.loads(target.read_text())
    assert doc["languages"]["python"]["status"] == "ok"
    assert doc["languages"]["go"] == {
        "status": "skipped", "reason": "no tooling for go", "tools": {}, "commands": {},
        "tests": {}, "excluded": [],
    }
    assert not (tmp_path / "test-evidence.json.tmp").exists()

