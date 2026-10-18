"""Seam tests for hotspot_probe.py (Step 8, ADR-0080): candidate selection and the hotspot rule.

Profiles are written as pstats marshal files, so shares are exact.
Run: uv run --with pytest pytest reference/python/tests
"""
import json
import marshal
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hotspot_probe import analyze, main, needed_hits, select  # conftest.py puts HELPERS on sys.path

ROOT = "/proj"
RUNNER = ("/venv/lib/python3.12/site-packages/_pytest/runner.py", 110, "runtestprotocol")
TOTAL = 10.0


def _test_id(i):
    return f"tests/pkg/test_mod.py::test_{i}"


def _write(tmp_path, test_id, funcs, spawns=0, wrapper=None):
    """A profile totalling TOTAL s; `funcs` maps a src/mod.py function to its cumulative time.

    `funcs` values may be `(ct, caller_name)` to nest a function under another of `funcs`.
    Self times are set so the profile's total time is TOTAL.
    """
    file, rest = test_id.split("::", 1)
    test_fn = (f"{ROOT}/{file}", 1, rest.split("[")[0].rsplit("::", 1)[-1])
    top = RUNNER
    stats = {RUNNER: (1, 1, 0.0, TOTAL, {})}
    if wrapper:  # a decorator frame between pytest and the test function
        stats[wrapper] = (1, 1, 0.0, TOTAL, {RUNNER: (1, 1, 0.0, TOTAL)})
        top = wrapper
    keys = {name: (f"{ROOT}/src/mod.py", sum(map(ord, name)), name) for name in funcs}  # one line per name in every profile
    specs = {name: spec if isinstance(spec, tuple) else (spec, None) for name, spec in funcs.items()}
    children = {}
    for _name, (ct, parent) in specs.items():
        children[parent] = children.get(parent, 0.0) + ct
    stats[test_fn] = (1, 1, TOTAL - children.get(None, 0.0), TOTAL, {top: (1, 1, 0.0, TOTAL)})
    for name, (ct, parent) in specs.items():
        caller = keys[parent] if parent else test_fn
        tt = ct - children.get(name, 0.0)
        stats[keys[name]] = (1, 1, tt, ct, {caller: (1, 1, tt, ct)})
    if spawns:
        stats[("~", 0, "<built-in method _posixsubprocess.fork_exec>")] = (
            spawns, spawns, 0.0, 0.0, {test_fn: (spawns, spawns, 0.0, 0.0)})
    path = tmp_path / f"{test_id.replace('/', '_').replace('::', '_')}.prof"
    path.write_bytes(marshal.dumps(stats))
    return str(path)


def _run(tmp_path, per_test, failed=None, **kw):
    profiles = {_test_id(i): _write(tmp_path, _test_id(i), funcs, **kw) for i, funcs in enumerate(per_test)}
    return analyze(ROOT, profiles, failed or {})


def _hot(out):
    return [h["function"] for h in out["hotspots"]]


def test_needed_hits_is_half_the_usable_profiles_but_never_one():
    assert [needed_hits(n) for n in (2, 3, 4, 5)] == [2, 2, 2, 3]


def test_exactly_half_share_in_exactly_half_the_profiles_is_a_hotspot(tmp_path):
    out = _run(tmp_path, [{"connect": 5.0}, {"connect": 5.0}, {"connect": 1.0}, {}])
    assert out["n"] == 4
    assert out["hotspots"] == [{"criterion": "hotspot", "function": "src/mod.py:connect", "share": 0.5,
                                "tests": [_test_id(0), _test_id(1)],
                                "subprocess_spawns": {_test_id(i): 0 for i in range(4)}, "via": []}]


def test_49_percent_share_is_not_a_hotspot(tmp_path):
    out = _run(tmp_path, [{"connect": 4.9}] * 4)
    assert out["hotspots"] == [] and out["warnings"] == []


@pytest.mark.parametrize("hits,expected", [(2, ["src/mod.py:connect"]), (1, [])])
def test_three_usable_profiles_need_two_hits(tmp_path, hits, expected):
    out = _run(tmp_path, [{"connect": 6.0}] * hits + [{"connect": 1.0}] * (3 - hits))
    assert out["n"] == 3 and _hot(out) == expected


@pytest.mark.parametrize("hits,expected", [(2, ["src/mod.py:connect"]), (1, [])])
def test_two_usable_profiles_need_two_hits(tmp_path, hits, expected):
    out = _run(tmp_path, [{"connect": 9.0}] * hits + [{}] * (2 - hits))
    assert out["n"] == 2 and _hot(out) == expected


def test_fewer_than_five_cost_candidates_are_all_profiled():
    cost = [{"file": "tests/t.py", "test_name": f"test_{i}", "criterion": "cost", "call_s": 1.0 + i} for i in range(3)]
    subset = [{"file": "tests/t.py", "test_name": "test_x", "criterion": "coverage-subset", "call_s": 99.0}]
    assert select(cost + subset) == {"profile": ["tests/t.py::test_2", "tests/t.py::test_1", "tests/t.py::test_0"],
                                     "cost_candidates": 3, "warnings": []}


def test_a_single_cost_candidate_skips_the_probe_with_a_warning():
    out = select([{"file": "tests/t.py", "test_name": "test_0", "criterion": "cost", "call_s": 3.0}])
    assert out == {"profile": [], "cost_candidates": 1,
                   "warnings": ["fewer than 2 cost candidates (1); hotspot probe skipped, no hotspot emitted"]}


def test_more_than_five_cost_candidates_profile_the_top_five_from_a_plan():
    cost = [{"file": "tests/t.py", "test_name": f"test_{i}", "criterion": "cost", "call_s": float(i)} for i in range(7)]
    out = select({"review_candidates": cost})
    assert out["profile"] == [f"tests/t.py::test_{i}" for i in (6, 5, 4, 3, 2)] and out["cost_candidates"] == 7


def test_failed_profiles_leave_n_and_are_named(tmp_path):
    bad = tmp_path / "bad.prof"
    bad.write_bytes(b"not a profile")
    profiles = {_test_id(i): _write(tmp_path, _test_id(i), {"connect": 8.0}) for i in range(2)}
    profiles[_test_id(2)] = str(bad)
    out = analyze(ROOT, profiles, {_test_id(3): "pytest exit 1"})
    assert out["n"] == 2 and out["profiled"] == [_test_id(0), _test_id(1)]
    assert {f["id"] for f in out["failed"]} == {_test_id(2), _test_id(3)}
    assert any(_test_id(3) in w and "pytest exit 1" in w for w in out["warnings"])
    assert _hot(out) == ["src/mod.py:connect"]
    assert set(out["hotspots"][0]["subprocess_spawns"]) == {_test_id(0), _test_id(1)}


def test_fewer_than_two_usable_profiles_emit_no_hotspot_and_warn(tmp_path):
    out = _run(tmp_path, [{"connect": 9.0}], failed={_test_id(5): "no profile file"})
    assert out["n"] == 1 and out["hotspots"] == []
    assert "fewer than 2 usable profiles (1); no hotspot emitted" in out["warnings"]


def test_missing_and_empty_profiles_are_failed(tmp_path):
    empty = tmp_path / "empty.prof"
    empty.write_bytes(marshal.dumps({("~", 0, "<method 'disable' of '_lsprof.Profiler' objects>"): (1, 1, 0.0, 0.0, {})}))
    out = analyze(ROOT, {_test_id(0): str(empty), _test_id(1): str(tmp_path / "none.prof")}, {})
    assert out["failed"] == [{"id": _test_id(0), "reason": "empty profile"},
                             {"id": _test_id(1), "reason": "no profile file"}]


def test_wrappers_of_the_test_are_not_hotspots_and_a_called_hotspot_is_listed_via_its_caller(tmp_path):
    wrapper = ("/usr/lib/python3.12/unittest/mock.py", 1390, "patched")
    out = _run(tmp_path, [{"connect": 8.0, "keychain": (7.0, "connect")}] * 3, spawns=4, wrapper=wrapper)
    assert _hot(out) == ["src/mod.py:connect"]
    hot = out["hotspots"][0]
    assert hot["via"] == ["src/mod.py:keychain"] and hot["share"] == 0.8
    assert hot["subprocess_spawns"] == {_test_id(i): 4 for i in range(3)}


def test_yield_fixture_dispatch_through_builtins_next_is_never_the_hotspot(tmp_path):
    nxt = ("~", 0, "<built-in method builtins.next>")
    fixture = (f"{ROOT}/tests/conftest.py", 5, "db")
    connect = (f"{ROOT}/src/mod.py", 10, "connect")
    profiles = {}
    for i in range(2):
        test_id = _test_id(i)
        test_fn = (f"{ROOT}/tests/pkg/test_mod.py", 1, f"test_{i}")
        stats = {
            RUNNER: (1, 1, 0.0, TOTAL, {}),
            test_fn: (1, 1, 1.0, 1.0, {RUNNER: (1, 1, 0.0, 1.0)}),
            nxt: (1, 1, 0.0, 9.0, {RUNNER: (1, 1, 0.0, 9.0)}),
            fixture: (1, 1, 1.0, 9.0, {nxt: (1, 1, 1.0, 9.0)}),
            connect: (1, 1, 8.0, 8.0, {fixture: (1, 1, 8.0, 8.0)}),
        }
        path = tmp_path / f"fx{i}.prof"
        path.write_bytes(marshal.dumps(stats))
        profiles[test_id] = str(path)
    out = analyze(ROOT, profiles, {})
    assert _hot(out) == ["tests/conftest.py:db"]
    assert out["hotspots"][0]["via"] == ["src/mod.py:connect"]


def _same_name_profile(tmp_path, i, lines):
    """Test i spends 6 of 10 s in an `__init__` at each of `lines` in src/db.py."""
    test_fn = (f"{ROOT}/tests/pkg/test_mod.py", 1, f"test_{i}")
    stats = {RUNNER: (1, 1, 0.0, TOTAL, {}), test_fn: (1, 1, 4.0, TOTAL, {RUNNER: (1, 1, 0.0, TOTAL)})}
    for line in lines:
        stats[(f"{ROOT}/src/db.py", line, "__init__")] = (1, 1, 6.0, 6.0, {test_fn: (1, 1, 6.0, 6.0)})
    path = tmp_path / f"same{i}.prof"
    path.write_bytes(marshal.dumps(stats))
    return str(path)


def test_same_named_functions_in_one_file_never_add_their_hits(tmp_path):
    # Connection.__init__ (line 10) holds 60% of test 0, Pool.__init__ (line 40) 60% of test 1: one hit each
    profiles = {_test_id(0): _same_name_profile(tmp_path, 0, [10]), _test_id(1): _same_name_profile(tmp_path, 1, [40])}
    assert analyze(ROOT, profiles, {})["hotspots"] == []


def test_same_named_hotspot_prints_its_line_only_when_names_collide(tmp_path):
    profiles = {_test_id(i): _same_name_profile(tmp_path, i, [10]) for i in range(2)}
    profiles[_test_id(2)] = _same_name_profile(tmp_path, 2, [40])
    assert _hot(analyze(ROOT, profiles, {})) == ["src/db.py:__init__:10"]
    profiles = {_test_id(i): _same_name_profile(tmp_path, i, [10]) for i in range(2)}
    assert _hot(analyze(ROOT, profiles, {})) == ["src/db.py:__init__"]


def test_a_folded_hotspot_keeps_its_own_tests_with_the_top(tmp_path):
    def prof(name, funcs):
        return _write(tmp_path, f"tests/{name}/test_mod.py::test_x", funcs)

    # c calls a in tests/a and tests/d, so a folds under c. c is hot alone in tests/b and a is hot alone in
    # tests/e: only the union of both hit lists reaches tests/e.
    a_under_c = {"c": 6.0, "a": (5.0, "c")}
    profiles = {
        "tests/a/test_mod.py::test_x": prof("a", a_under_c),
        "tests/d/test_mod.py::test_x": prof("d", a_under_c),
        "tests/b/test_mod.py::test_x": prof("b", {"c": 6.0}),
        "tests/e/test_mod.py::test_x": prof("e", {"a": 5.0}),
    }
    out = analyze(ROOT, profiles, {})
    (hot,) = out["hotspots"]
    assert hot["function"] == "src/mod.py:c" and hot["via"] == ["src/mod.py:a"]
    assert hot["tests"] == [f"tests/{d}/test_mod.py::test_x" for d in "abde"]


SLOW_TESTS = '''import subprocess
import sys


def slow():
    subprocess.run([sys.executable, "-c", "import time; time.sleep(0.2)"], check=True)


def test_one():
    slow()


def test_two():
    slow()
'''


def test_plugin_profiles_one_test_and_the_shared_helper_is_a_hotspot(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_slow.py").write_text(SLOW_TESTS)
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    helpers = str(Path(__file__).resolve().parent.parent)
    profiles = {}
    for name in ("test_one", "test_two"):
        test_id, prof = f"tests/test_slow.py::{name}", tmp_path / f"{name}.prof"
        env = {**os.environ, "PYTHONPATH": helpers, "HOTSPOT_PROFILE": str(prof)}
        env.pop("PYTEST_CURRENT_TEST", None)
        run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "hotspot_profile", test_id],
                             cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
        assert run.returncode == 0, run.stdout + run.stderr
        profiles[test_id] = str(prof)
    out = analyze(tmp_path.resolve(), profiles, {})
    assert out["n"] == 2 and _hot(out) == ["tests/test_slow.py:slow"]
    assert out["hotspots"][0]["subprocess_spawns"] == {t: 1 for t in sorted(profiles)}
    assert "subprocess.py:run" in out["hotspots"][0]["via"]


def test_cli_splits_ids_whose_params_hold_equals(tmp_path, capsys):
    tid = "tests/pkg/test_mod.py::test_p[a=1]"
    path = _write(tmp_path, tid, {"connect": 8.0})
    other = "tests/pkg/test_mod.py::test_q[b=2]"
    main(["analyze", "--root", ROOT, "--profile", f"{tid}={path}", "--failed", f"{other}=pytest exit 1 (a=b)"])
    out = json.loads(capsys.readouterr().out)
    assert out["profiled"] == [tid]
    assert out["failed"] == [{"id": other, "reason": "pytest exit 1 (a=b)"}]
