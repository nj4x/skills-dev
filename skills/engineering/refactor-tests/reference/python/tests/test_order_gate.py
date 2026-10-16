"""Seam tests for the refactor-tests random-order gate helper (plugin, classify, demote).

Run: uv run --with pytest pytest reference/python/tests/test_order_gate.py
"""
import json
import subprocess
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent.parent  # conftest.py puts this on sys.path

from order_gate import choose_plugin, classify, demote, normalize_id, read_junit  # after conftest path setup

A = "tests.pkg.test_a::test_one"
B = "tests.pkg.test_a::test_two"
C = "tests.pkg.test_b.TestX::test_three[1]"
D = "tests.pkg.test_b::test_four"


# --- plugin choice -------------------------------------------------------------


def test_random_order_in_project_uses_global_bucket_and_no_ephemeral_install():
    p = choose_plugin(random_order_present=True, randomly_present=False, seed=7)
    assert p["plugin"] == "pytest-random-order"
    assert p["with"] == []
    assert p["args"] == ["--random-order-bucket=global", "--random-order-seed=7"]


def test_random_order_in_project_blocks_randomly_when_both_installed():
    p = choose_plugin(random_order_present=True, randomly_present=True, seed=7)
    assert p["plugin"] == "pytest-random-order"
    assert p["args"] == ["-p", "no:randomly", "--random-order-bucket=global", "--random-order-seed=7"]
    assert p["with"] == []


def test_without_random_order_installs_randomly_only_for_the_run():
    p = choose_plugin(random_order_present=False, randomly_present=False, seed=42)
    assert p["plugin"] == "pytest-randomly"
    assert p["with"] == ["pytest-randomly"]
    assert p["args"] == ["--randomly-seed=42"]


def test_randomly_already_installed_needs_no_ephemeral_install():
    p = choose_plugin(random_order_present=False, randomly_present=True, seed=42)
    assert p["plugin"] == "pytest-randomly"
    assert p["with"] == []
    assert p["args"] == ["--randomly-seed=42"]


def test_plugin_choice_never_enables_two_shufflers():
    for ro in (True, False):
        for rl in (True, False):
            p = choose_plugin(random_order_present=ro, randomly_present=rl, seed=1)
            random_order_on = any(a.startswith("--random-order") for a in p["args"])
            randomly_on = p["plugin"] == "pytest-randomly"
            assert random_order_on != randomly_on


# --- gate classification -------------------------------------------------------


def test_no_baseline_passing_failure_needs_no_rerun():
    r = classify({"passed": [A, B], "failed": []}, {A: "passed", B: "passed"}, None, seed=3)
    assert r["rerun_required"] is False
    assert r["order_dependent"] == [] and r["flaky"] == []
    assert r["seed"] == 3


def test_baseline_passing_failure_without_rerun_asks_for_rerun():
    r = classify({"passed": [A, B], "failed": []}, {A: "failed", B: "passed"}, None, seed=3)
    assert r["rerun_required"] is True
    assert r["candidates"] == [A]


def test_failing_in_both_runs_is_order_dependent():
    r = classify({"passed": [A, B], "failed": []}, {A: "failed", B: "passed"}, {A: "failed", B: "passed"}, seed=3)
    assert r["order_dependent"] == [A]
    assert r["flaky"] == []
    assert r["rerun_required"] is False


def test_failing_then_passing_is_flaky():
    r = classify({"passed": [A, B], "failed": []}, {A: "failed", B: "passed"}, {A: "passed", B: "passed"}, seed=3)
    assert r["flaky"] == [A]
    assert r["order_dependent"] == []


def test_missing_from_rerun_counts_as_still_failing():
    r = classify({"passed": [A], "failed": []}, {A: "failed"}, {}, seed=3)
    assert r["order_dependent"] == [A]


def test_baseline_non_passing_tests_are_excluded_and_listed():
    baseline = {"passed": [A], "failed": [B]}
    gate = {A: "passed", B: "failed", C: "failed"}
    r = classify(baseline, gate, None, seed=3)
    assert r["order_dependent"] == [] and r["flaky"] == []
    assert r["rerun_required"] is False
    assert r["excluded"] == [
        {"id": B, "baseline": "failed"},
        {"id": C, "baseline": "not-in-baseline"},
    ]


def test_ledger_baseline_with_pass_count_treats_unlisted_ids_as_passing():
    # Ledger post_layout_baseline stores a pass count and the failing ids only.
    baseline = {"passed": 2, "failed": [B]}
    r = classify(baseline, {A: "failed", B: "failed"}, {A: "failed", B: "failed"}, seed=3)
    assert r["order_dependent"] == [A]
    assert r["excluded"] == [{"id": B, "baseline": "failed"}]


def test_node_id_baseline_matches_junit_gate_ids():
    # Failing baseline ids in node-id form must still be excluded, passing ones still count as baseline.
    baseline = {
        "passed": ["tests/pkg/test_a.py::test_one", "tests/pkg/test_b.py::TestX::test_three[1]"],
        "failed": ["tests/pkg/test_a.py::test_two"],
    }
    gate = {
        "tests.pkg.test_a::test_one": "failed",
        "tests.pkg.test_a::test_two": "failed",
        "tests.pkg.test_b.TestX::test_three[1]": "passed",
    }
    r = classify(baseline, gate, {"tests.pkg.test_a::test_one": "failed"}, seed=3)
    assert r["order_dependent"] == ["tests.pkg.test_a::test_one"]
    assert r["excluded"] == [{"id": "tests.pkg.test_a::test_two", "baseline": "failed"}]


def test_normalize_id_converts_node_ids_and_keeps_junit_ids():
    assert normalize_id("tests/pkg/test_b.py::TestX::test_three[a::b]") == "tests.pkg.test_b.TestX::test_three[a::b]"
    assert normalize_id("tests.pkg.test_a::test_one") == "tests.pkg.test_a::test_one"


def test_rerun_skipped_is_still_order_dependent_and_gate_skipped_gets_no_label():
    r = classify({"passed": [A, B], "failed": []}, {A: "failed", B: "skipped"}, {A: "skipped"}, seed=3)
    assert r["order_dependent"] == [A]
    assert r["flaky"] == []


def test_error_outcome_counts_as_failure():
    r = classify({"passed": [A], "failed": []}, {A: "error"}, {A: "passed"}, seed=3)
    assert r["flaky"] == [A]


def test_read_junit_maps_outcomes(tmp_path):
    xml = tmp_path / "gate.xml"
    xml.write_text(
        '<?xml version="1.0"?><testsuites><testsuite>'
        '<testcase classname="tests.pkg.test_a" name="test_one"/>'
        '<testcase classname="tests.pkg.test_a" name="test_two"><failure message="x"/></testcase>'
        '<testcase classname="tests.pkg.test_b.TestX" name="test_three[1]"><error message="y"/></testcase>'
        '<testcase classname="tests.pkg.test_b" name="test_four"><skipped message="z"/></testcase>'
        "</testsuite></testsuites>"
    )
    assert read_junit(xml) == {
        "tests.pkg.test_a::test_one": "passed",
        "tests.pkg.test_a::test_two": "failed",
        "tests.pkg.test_b.TestX::test_three[1]": "error",
        "tests.pkg.test_b::test_four": "skipped",
    }


# --- plan demotion ---------------------------------------------------------------


def _plan():
    return {
        "schema_version": 2,
        "removals": [
            {"file": "tests/pkg/test_a.py", "test_name": "test_one", "criterion": "trivially-true", "evidence": "assert True"},
            {"file": "tests/pkg/test_a.py", "test_name": "test_two_copy", "criterion": "exact-duplicate",
             "evidence": "body identical to test_two", "duplicate_of": "test_two"},
            {"file": "tests/pkg/test_b.py", "test_name": "test_five", "criterion": "trivially-true", "evidence": "assert True"},
        ],
        "review_candidates": [
            {"file": "tests/pkg/test_b.py", "test_name": "test_dead", "criterion": "dead-test", "evidence": "no assert"},
        ],
        "parametrizations": [
            {"file": "tests/pkg/test_b.py", "tests": ["test_three", "test_four", "test_six"],
             "consolidated_name": "test_x", "criterion": "parametrize-cluster", "evidence": "same call"},
        ],
    }


def test_removal_of_order_dependent_test_moves_to_review():
    gate = {"seed": 9, "order_dependent": [A], "flaky": []}
    out = demote(_plan(), gate)
    names = [r["test_name"] for r in out["removals"]]
    assert "test_one" not in names
    entry = [r for r in out["review_candidates"] if r["test_name"] == "test_one"]
    assert entry == [{
        "file": "tests/pkg/test_a.py", "test_name": "test_one", "criterion": "order-dependent",
        "evidence": entry[0]["evidence"], "seed": 9, "failing_ids": [A],
    }]
    assert "trivially-true" in entry[0]["evidence"]


def test_kept_duplicate_that_is_flaky_demotes_the_removal():
    gate = {"seed": 9, "order_dependent": [], "flaky": [B]}
    out = demote(_plan(), gate)
    assert "test_two_copy" not in [r["test_name"] for r in out["removals"]]
    entries = [r for r in out["review_candidates"] if r["criterion"] == "flaky"]
    assert {r["test_name"] for r in entries} == {"test_two_copy", "test_two"}
    assert all(r["seed"] == 9 and r["failing_ids"] == [B] for r in entries)


def test_parametrize_merge_touching_flagged_test_moves_whole_merge_to_review():
    gate = {"seed": 9, "order_dependent": [C], "flaky": []}
    out = demote(_plan(), gate)
    assert out["parametrizations"] == []
    entries = [r for r in out["review_candidates"] if r["criterion"] == "order-dependent"]
    assert [r["test_name"] for r in entries] == ["test_three", "test_four", "test_six"]
    assert all(r["failing_ids"] == [C] and r["seed"] == 9 for r in entries)


def test_change_with_both_labels_gets_one_entry_per_criterion():
    gate = {"seed": 9, "order_dependent": [C], "flaky": [D]}
    out = demote(_plan(), gate)
    by_crit = {}
    for r in out["review_candidates"]:
        if r["test_name"] == "test_three":
            by_crit[r["criterion"]] = r["failing_ids"]
    assert by_crit == {"order-dependent": [C], "flaky": [D]}


def test_unrelated_changes_and_existing_review_entries_stay():
    gate = {"seed": 9, "order_dependent": [A], "flaky": []}
    out = demote(_plan(), gate)
    assert [r["test_name"] for r in out["removals"]] == ["test_two_copy", "test_five"]
    assert out["review_candidates"][0]["criterion"] == "dead-test"
    assert len(out["parametrizations"]) == 1


def test_no_flagged_tests_leaves_plan_unchanged():
    plan = _plan()
    assert demote(plan, {"seed": 9, "order_dependent": [], "flaky": []}) == _plan()


def test_junit_style_ids_match_plan_entries():
    gate = {"seed": 9, "order_dependent": ["tests.pkg.test_b.TestX::test_three[1]"], "flaky": []}
    out = demote(_plan(), gate)
    assert out["parametrizations"] == []


def test_parameter_with_separator_characters_still_matches():
    plan = {"removals": [{"file": "tests/pkg/test_a.py", "test_name": "test_p", "criterion": "trivially-true", "evidence": "e"}]}
    for flagged in ("tests.pkg.test_a::test_p[a::b]", "tests.pkg.test_a::test_p[1.5]"):
        out = demote(plan, {"seed": 1, "order_dependent": [flagged], "flaky": []})
        assert out["removals"] == []


def test_kept_duplicate_in_another_file_is_matched_by_duplicate_of_file():
    plan = {"removals": [{"file": "tests/pkg/test_a.py", "test_name": "test_copy", "criterion": "exact-duplicate",
                          "evidence": "e", "duplicate_of": "test_orig", "duplicate_of_file": "tests/pkg/test_b.py"}]}
    out = demote(plan, {"seed": 1, "order_dependent": [], "flaky": ["tests.pkg.test_b::test_orig"]})
    assert out["removals"] == []
    assert {(r["file"], r["test_name"]) for r in out["review_candidates"]} == {
        ("tests/pkg/test_a.py", "test_copy"), ("tests/pkg/test_b.py", "test_orig")}


def test_demote_is_idempotent():
    gate = {"seed": 9, "order_dependent": [A], "flaky": [D]}
    once = demote(_plan(), gate)
    assert demote(once, gate) == once


def test_same_name_in_other_file_does_not_match():
    gate = {"seed": 9, "order_dependent": ["tests/pkg/test_other.py::test_one"], "flaky": []}
    assert demote(_plan(), gate) == _plan()


# --- CLI ---------------------------------------------------------------------------


def _run(*args):
    return subprocess.run([sys.executable, str(HELPERS / "order_gate.py"), *args], capture_output=True, text=True)


def test_cli_classify_then_demote(tmp_path):
    (tmp_path / "baseline.json").write_text(json.dumps({"passed": 2, "failed": []}))
    junit = (
        '<?xml version="1.0"?><testsuite>'
        '<testcase classname="tests.pkg.test_a" name="test_one">{}</testcase>'
        '<testcase classname="tests.pkg.test_a" name="test_two"/>'
        "</testsuite>"
    )
    (tmp_path / "gate.xml").write_text(junit.format('<failure message="x"/>'))
    (tmp_path / "rerun.xml").write_text(junit.format(""))
    r = _run("classify", "--baseline", str(tmp_path / "baseline.json"), "--gate", str(tmp_path / "gate.xml"), "--seed", "5")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["rerun_required"] is True
    r = _run("classify", "--baseline", str(tmp_path / "baseline.json"), "--gate", str(tmp_path / "gate.xml"),
             "--rerun", str(tmp_path / "rerun.xml"), "--seed", "5")
    assert r.returncode == 0, r.stderr
    result = json.loads(r.stdout)
    assert result["flaky"] == ["tests.pkg.test_a::test_one"]
    (tmp_path / "result.json").write_text(r.stdout)
    (tmp_path / "plan.json").write_text(json.dumps(_plan()))
    r = _run("demote", "--plan", str(tmp_path / "plan.json"), "--gate-result", str(tmp_path / "result.json"))
    assert r.returncode == 0, r.stderr
    plan = json.loads((tmp_path / "plan.json").read_text())
    assert "test_one" not in [x["test_name"] for x in plan["removals"]]


def test_cli_plugin_prints_choice():
    r = _run("plugin", "--random-order-present", "no", "--randomly-present", "yes", "--seed", "11")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"plugin": "pytest-randomly", "with": [], "args": ["--randomly-seed=11"], "seed": 11}


def test_cli_plugin_draws_a_seed_when_none_given():
    r = _run("plugin", "--random-order-present", "no", "--randomly-present", "no")
    seed = json.loads(r.stdout)["seed"]
    assert isinstance(seed, int) and seed > 0
