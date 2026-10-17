"""Emit coverage-subset and cost review candidates from test-evidence.json.

Usage:
  python select_candidates.py --evidence .scratch/refactor-tests/test-evidence.json

Prints a JSON list of `review_candidates` entries
`{ file, test_name, criterion, evidence, call_s, time_saved_s }` to stdout.
Languages whose evidence status is not `ok` yield no entries.

coverage-subset: a test is a candidate when every line and arc in its `covered`
map is also in the union of the other passing tests' coverage. A test with an
empty `covered` map is never a candidate. Tests are processed in descending
`call_s` (ties by id), and a test already flagged leaves the union, so of two
tests that cover each other only the slower is flagged.

cost: of the coverage-subset candidates ranked by `call_s` descending, the top
decile (ceiling of 10%, minimum 1) is flagged when its `call_s` is at least
0.5 s. `time_saved_s` is the test's own `call_s`: serial time, not wall time.
"""
import argparse
import json
import sys
from collections import Counter

from refactor_tests_shared import split_file

MIN_COST_S = 0.5


def _points(covered):
    """Every covered line and arc of one test, as hashable (file, kind, value)."""
    points = set()
    for path, data in covered.items():
        points.update((path, "line", line) for line in data.get("lines", []))
        points.update((path, "arc", tuple(arc)) for arc in data.get("arcs", []))
    return points


def _entry(nodeid, criterion, call_s, evidence):
    file, test_name = split_file(nodeid)
    return {
        "file": file,
        "test_name": test_name,
        "criterion": criterion,
        "evidence": evidence,
        "call_s": call_s,
        "time_saved_s": call_s,
    }


def _coverage_subset(tests):
    points = {nodeid: _points(t.get("covered", {})) for nodeid, t in tests.items()}
    # Count of unflagged tests covering each point; T is a subset of the others
    # exactly when every point of T is held by at least one test besides T.
    held = Counter(p for ps in points.values() for p in ps)
    order = sorted(tests, key=lambda n: (-tests[n]["call_s"], n))
    flagged = []
    for nodeid in order:
        mine = points[nodeid]
        if mine and all(held[p] >= 2 for p in mine):
            flagged.append(nodeid)
            held.subtract(mine)
    return flagged


def _cost(candidates, tests):
    ranked = sorted(candidates, key=lambda n: (-tests[n]["call_s"], n))
    top = max(1, -(-len(ranked) // 10))  # integer ceiling: no float rounding
    return [n for n in ranked[:top] if tests[n]["call_s"] >= MIN_COST_S]


def select_candidates(evidence):
    entries = []
    for block in evidence.get("languages", {}).values():
        if block.get("status") != "ok":
            continue
        tests = block.get("tests", {})
        subset = _coverage_subset(tests)
        for nodeid in subset:
            lines = sum(len(d.get("lines", [])) for d in tests[nodeid]["covered"].values())
            arcs = sum(len(d.get("arcs", [])) for d in tests[nodeid]["covered"].values())
            entries.append(_entry(
                nodeid, "coverage-subset", tests[nodeid]["call_s"],
                f"all {lines} lines and {arcs} arcs also covered by other passing tests",
            ))
        for nodeid in _cost(subset, tests):
            entries.append(_entry(
                nodeid, "cost", tests[nodeid]["call_s"],
                f"call_s {tests[nodeid]['call_s']} s, top decile of {len(subset)} "
                f"coverage-subset candidates, at least {MIN_COST_S} s",
            ))
    return entries


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True)
    a = ap.parse_args()
    with open(a.evidence, encoding="utf-8") as f:
        doc = json.load(f)
    json.dump(select_candidates(doc), sys.stdout, indent=1)
    sys.stdout.write("\n")
