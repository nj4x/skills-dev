"""Seam tests for the evidence-based Phase B criteria helpers.

select_candidates.py: coverage-subset (greedy, slowest first) and cost (top decile).
calltime_delta.py: serial call time before -> after, per removed test.

Run: uv run --with pytest --with pytest-cov --with coverage pytest reference/python/tests
"""
import json
import subprocess
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent.parent  # conftest.py puts this on sys.path

from calltime_delta import call_time_delta  # noqa: E402 (after conftest path setup)
from select_candidates import select_candidates  # noqa: E402

F = "src/pkg/calc.py"


def _cov(lines, arcs=()):
    return {F: {"lines": list(lines), "arcs": [list(a) for a in arcs]}}


def _evidence(tests, status="ok"):
    block = {"status": status, "tests": {}, "excluded": []}
    if status != "ok":
        block["reason"] = "coverage run crashed"
    for nodeid, (call_s, covered) in tests.items():
        block["tests"][nodeid] = {"outcome": "passed", "call_s": call_s, "covered": covered}
    return {"schema_version": 1, "id_basis": "post-layout", "languages": {"python": block}}


def _by(entries, criterion):
    return [e for e in entries if e["criterion"] == criterion]


def _ids(entries):
    return [f"{e['file']}::{e['test_name']}" for e in entries]


# --- coverage-subset ---------------------------------------------------------


def test_subset_flags_test_whose_lines_and_arcs_others_cover():
    ev = _evidence({
        "tests/t.py::test_big": (0.01, _cov([1, 2, 3], [(1, 2), (2, 3)])),
        "tests/t.py::test_small": (0.02, _cov([1, 2], [(1, 2)])),
    })
    subset = _by(select_candidates(ev), "coverage-subset")
    assert _ids(subset) == ["tests/t.py::test_small"]
    entry = subset[0]
    assert entry["file"] == "tests/t.py"
    assert entry["test_name"] == "test_small"
    assert entry["call_s"] == 0.02
    assert entry["time_saved_s"] == 0.02
    assert entry["evidence"]


def test_subset_requires_arcs_too_not_only_lines():
    ev = _evidence({
        "tests/t.py::test_a": (0.01, _cov([1, 2, 3], [(1, 2), (2, 3)])),
        "tests/t.py::test_b": (0.02, _cov([1, 3], [(1, 3)])),  # lines covered, arc (1,3) unique
    })
    assert _by(select_candidates(ev), "coverage-subset") == []


def test_subset_union_spans_several_other_tests_and_files():
    other = "src/pkg/other.py"
    ev = _evidence({
        "tests/t.py::test_a": (0.01, _cov([1], [(1, -1)])),
        "tests/t.py::test_b": (0.01, {other: {"lines": [5], "arcs": [[5, -4]]}}),
        "tests/t.py::test_both": (0.03, {
            F: {"lines": [1], "arcs": [[1, -1]]},
            other: {"lines": [5], "arcs": [[5, -4]]},
        }),
    })
    assert _ids(_by(select_candidates(ev), "coverage-subset")) == ["tests/t.py::test_both"]


def test_subset_of_mutual_pair_flags_only_the_slower():
    ev = _evidence({
        "tests/t.py::test_fast": (0.1, _cov([1, 2], [(1, 2)])),
        "tests/t.py::test_slow": (0.9, _cov([1, 2], [(1, 2)])),
    })
    assert _ids(_by(select_candidates(ev), "coverage-subset")) == ["tests/t.py::test_slow"]


def test_subset_processes_slowest_first_and_excludes_flagged_from_union():
    # Three identical tests: the two slowest are flagged, the fastest keeps the coverage.
    ev = _evidence({
        "tests/t.py::test_a": (0.3, _cov([1])),
        "tests/t.py::test_b": (0.7, _cov([1])),
        "tests/t.py::test_c": (0.5, _cov([1])),
    })
    assert _ids(_by(select_candidates(ev), "coverage-subset")) == [
        "tests/t.py::test_b",
        "tests/t.py::test_c",
    ]


def test_subset_never_flags_empty_covered():
    ev = _evidence({
        "tests/t.py::test_a": (0.9, {}),
        "tests/t.py::test_b": (0.8, {F: {"lines": [], "arcs": []}}),
        "tests/t.py::test_c": (0.1, _cov([1])),
    })
    assert select_candidates(ev) == []


def test_subset_keeps_class_and_param_parts_in_test_name():
    ev = _evidence({
        "tests/t.py::TestCalc::test_add[1-2]": (0.2, _cov([1])),
        "tests/t.py::TestCalc::test_add[3-4]": (0.1, _cov([1])),
    })
    (entry,) = _by(select_candidates(ev), "coverage-subset")
    assert entry["file"] == "tests/t.py"
    assert entry["test_name"] == "TestCalc::test_add[1-2]"


def test_no_candidates_when_evidence_not_ok():
    ev = _evidence({"t::a": (0.9, _cov([1])), "t::b": (0.9, _cov([1]))}, status="failed")
    assert select_candidates(ev) == []


def test_candidates_come_from_every_ok_language_block():
    ev = _evidence({"t::a": (0.1, _cov([1])), "t::b": (0.2, _cov([1]))})
    ev["languages"]["go"] = _evidence({"u::a": (0.1, _cov([1])), "u::b": (0.3, _cov([1]))})["languages"]["python"]
    assert _ids(_by(select_candidates(ev), "coverage-subset")) == ["t::b", "u::b"]


# --- cost --------------------------------------------------------------------


def _many_subset_candidates(call_times):
    # One keeper with the shared coverage, plus one subset candidate per call time.
    tests = {"tests/t.py::test_keeper": (0.0, _cov([1]))}
    for i, call_s in enumerate(call_times):
        tests[f"tests/t.py::test_{i:02d}"] = (call_s, _cov([1]))
    return _evidence(tests)


def test_cost_flags_top_decile_ceiling_of_candidates():
    # 11 candidates (keeper has call_s 0.0, so it is never flagged): ceil(11/10) = 2.
    times = [3.0, 2.0, 1.5] + [0.6] * 8
    entries = select_candidates(_many_subset_candidates(times))
    assert len(_by(entries, "coverage-subset")) == 11
    cost = _by(entries, "cost")
    assert _ids(cost) == ["tests/t.py::test_00", "tests/t.py::test_01"]
    assert [e["call_s"] for e in cost] == [3.0, 2.0]
    assert [e["time_saved_s"] for e in cost] == [3.0, 2.0]
    assert all(e["evidence"] for e in cost)


def test_cost_decile_of_thirty_is_three_not_four():
    # Guards the float trap: math.ceil(0.1 * 30) == 4.
    times = [float(30 - i) for i in range(30)]
    entries = select_candidates(_many_subset_candidates(times))
    assert len(_by(entries, "coverage-subset")) == 30
    assert len(_by(entries, "cost")) == 3


def test_cost_minimum_one_flag():
    entries = select_candidates(_many_subset_candidates([0.8, 0.2]))
    assert _ids(_by(entries, "cost")) == ["tests/t.py::test_00"]


def test_cost_skips_top_decile_below_half_second():
    entries = select_candidates(_many_subset_candidates([0.49, 0.2]))
    assert len(_by(entries, "coverage-subset")) == 2
    assert _by(entries, "cost") == []


def test_cost_threshold_is_inclusive():
    entries = select_candidates(_many_subset_candidates([0.5]))
    assert _ids(_by(entries, "cost")) == ["tests/t.py::test_00"]


def test_cost_ignores_slow_test_with_unique_coverage():
    ev = _evidence({
        "tests/t.py::test_unique_slow": (5.0, _cov([1, 2])),
        "tests/t.py::test_other": (0.1, _cov([1])),
    })
    entries = select_candidates(ev)
    assert _ids(_by(entries, "coverage-subset")) == ["tests/t.py::test_other"]
    assert _by(entries, "cost") == []


def test_select_cli_prints_entries(tmp_path):
    path = tmp_path / "test-evidence.json"
    path.write_text(json.dumps(_many_subset_candidates([0.8])))
    out = subprocess.run(
        [sys.executable, str(HELPERS / "select_candidates.py"), "--evidence", str(path)],
        capture_output=True, text=True, check=True,
    )
    entries = json.loads(out.stdout)
    assert [e["criterion"] for e in entries] == ["coverage-subset", "cost"]


# --- serial call time before / after -----------------------------------------


def test_call_time_delta_totals_and_removed_tests():
    ev = _evidence({
        "tests/t.py::test_a": (0.5, _cov([1])),
        "tests/t.py::test_b[1]": (0.25, _cov([1])),
        "tests/t.py::test_b[2]": (0.25, _cov([1])),
        "tests/t.py::test_c": (1.0, _cov([1])),
    })
    after = {
        "tests/t.py::test_a": {"duration": 0.5, "outcome": "passed"},
        "tests/t.py::test_c": {"duration": 0.75, "outcome": "passed"},
        "tests/t.py::test_x": {"duration": 9.0, "outcome": "failed"},
        "tests/t.py::test_y": {"duration": None, "outcome": "skipped"},
    }
    result = call_time_delta(ev, after, ["tests/t.py::test_b", "tests/t.py::test_gone"])
    assert result["label"] == "serial call time, not wall time"
    assert result["before_s"] == 2.0
    assert result["after_s"] == 1.25
    assert result["delta_s"] == -0.75
    assert result["removed"] == [
        {"id": "tests/t.py::test_b[1]", "call_s": 0.25},
        {"id": "tests/t.py::test_b[2]", "call_s": 0.25},
        {"id": "tests/t.py::test_gone", "call_s": None},
    ]
    assert result["warning"] is None


def test_call_time_delta_omitted_with_warning_when_evidence_not_ok():
    result = call_time_delta(_evidence({}, status="skipped"), {}, [])
    assert result["before_s"] is None
    assert result["after_s"] is None
    assert result["delta_s"] is None
    assert result["removed"] == []
    assert "evidence" in result["warning"]


def test_call_time_delta_cli(tmp_path):
    ev_path = tmp_path / "test-evidence.json"
    ev_path.write_text(json.dumps(_evidence({"tests/t.py::test_a": (0.5, _cov([1]))})))
    after_path = tmp_path / "calltime-after.json"
    after_path.write_text(json.dumps({"tests/t.py::test_b": {"duration": 0.125, "outcome": "passed"}}))
    out = subprocess.run(
        [sys.executable, str(HELPERS / "calltime_delta.py"),
         "--evidence", str(ev_path), "--calltime", str(after_path),
         "--removed", "tests/t.py::test_a"],
        capture_output=True, text=True, check=True,
    )
    result = json.loads(out.stdout)
    assert result["before_s"] == 0.5
    assert result["after_s"] == 0.125
    assert result["delta_s"] == -0.375
    assert result["removed"] == [{"id": "tests/t.py::test_a", "call_s": 0.5}]


def test_call_time_delta_cli_missing_calltime_file_on_degraded_evidence(tmp_path):
    ev_path = tmp_path / "test-evidence.json"
    ev_path.write_text(json.dumps(_evidence({}, status="skipped")))
    out = subprocess.run(
        [sys.executable, str(HELPERS / "calltime_delta.py"),
         "--evidence", str(ev_path), "--calltime", str(tmp_path / "absent.json")],
        capture_output=True, text=True, check=True,
    )
    result = json.loads(out.stdout)
    assert result["before_s"] is None and result["warning"]


def test_call_time_delta_ignores_passed_tests_the_evidence_excluded():
    ev = _evidence({"tests/t.py::test_a": (0.5, _cov([1]))})
    ev["languages"]["python"]["excluded"] = [{"id": "tests/t.py::test_nocov", "outcome": "no-coverage"}]
    after = {
        "tests/t.py::test_a": {"duration": 0.5, "outcome": "passed"},
        "tests/t.py::test_nocov": {"duration": 2.0, "outcome": "passed"},
    }
    result = call_time_delta(ev, after, [])
    assert (result["before_s"], result["after_s"], result["delta_s"]) == (0.5, 0.5, 0.0)


def test_call_time_delta_missing_calltime_is_omitted_not_zero():
    ev = _evidence({"tests/t.py::test_a": (0.5, _cov([1]))})
    result = call_time_delta(ev, None, [])
    assert result["before_s"] is None and result["delta_s"] is None
    assert "calltime" in result["warning"]


def test_call_time_delta_empty_calltime_is_valid_after_zero():
    ev = _evidence({"tests/t.py::test_a": (0.5, _cov([1]))})
    assert call_time_delta(ev, {}, ["tests/t.py::test_a"])["after_s"] == 0.0


def test_removed_matches_class_method_and_params_but_not_prefix_siblings():
    ev = _evidence({
        "tests/t.py::TestK::test_b[1]": (0.1, _cov([1])),
        "tests/t.py::test_b2": (0.2, _cov([1])),
        "tests/t.py::test_b": (0.3, _cov([1])),
    })
    ids = [r["id"] for r in call_time_delta(ev, {}, ["tests/t.py::test_b"])["removed"]]
    assert ids == ["tests/t.py::TestK::test_b[1]", "tests/t.py::test_b"]
