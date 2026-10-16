"""Report serial call time before -> after simplification, per removed test.

Usage:
  python calltime_delta.py --evidence .scratch/refactor-tests/test-evidence.json \
      --calltime .scratch/refactor-tests/calltime-after-python.json \
      [--removed <file>::<test_name> ...] [--language python]

Prints `{ label, before_s, after_s, delta_s, removed, warning }` as JSON.
Before: total `call_s` of the evidence pass timing run (passed tests in
test-evidence.json). After: total call duration of passed rows in the
`calltime` hook file written by the simplify validation run, minus ids listed
under the evidence block's `excluded` (so both totals cover one population). Each --removed
id is `<file>::<test_name>`; it matches the evidence id exactly or any of its
parametrized ids (`<id>[...]`). A removed id with no evidence entry gets
`call_s: null`; a bare `<file>::<test>` with no exact match falls back to
`<file>::<Class>::<test>` and its parametrized ids. A missing --calltime file (None) omits all figures
with a warning, never `after_s` 0; `{}` is valid (every test removed). When the language's evidence status is not `ok`, every figure
is null and `warning` says why.
"""
import argparse
import json
import sys

LABEL = "serial call time, not wall time"


def _r(x):
    return round(x, 6)


def _matches(nodeid, rid, class_fallback=False):
    """True when evidence id `nodeid` is the removed test `rid` or a parametrized id of it.

    With `class_fallback`, a bare `<file>::<test>` also names a method `<file>::<Class>::<test>`.
    """
    base = nodeid.partition("[")[0]
    if base == rid:
        return True
    if not class_fallback:
        return False
    file, _, name = rid.partition("::")
    return base.startswith(file + "::") and base.endswith("::" + name) and "::" not in name


def call_time_delta(evidence, after_calltime, removed_ids, language="python"):
    """`after_calltime` is the hook's rows, or None when the file is missing."""
    block = evidence.get("languages", {}).get(language, {})
    if block.get("status") != "ok":
        reason = block.get("reason") or "no evidence block"
        return {
            "label": LABEL, "before_s": None, "after_s": None, "delta_s": None,
            "removed": [],
            "warning": f"serial call time omitted: {language} evidence "
                       f"{block.get('status', 'missing')} ({reason})",
        }
    if after_calltime is None:
        return {
            "label": LABEL, "before_s": None, "after_s": None, "delta_s": None,
            "removed": [],
            "warning": "serial call time omitted: no calltime file from the validation run",
        }
    tests = block.get("tests", {})
    before = sum(t["call_s"] for t in tests.values())
    # Tests the evidence pass excluded (no-coverage, no-timing, failed) have no
    # `before` figure, so they stay out of `after` too: same population.
    excluded = {e["id"] for e in block.get("excluded", [])}
    after = sum(
        row["duration"] for nodeid, row in after_calltime.items()
        if row.get("outcome") == "passed" and row.get("duration") is not None
        and nodeid not in excluded
    )
    removed = []
    for rid in removed_ids:
        # Class fallback only when no top-level id matches: never charge a sibling method.
        hits = sorted(n for n in tests if _matches(n, rid)) or sorted(
            n for n in tests if _matches(n, rid, class_fallback=True)
        )
        if not hits:
            removed.append({"id": rid, "call_s": None})
        removed.extend({"id": n, "call_s": tests[n]["call_s"]} for n in hits)
    return {
        "label": LABEL,
        "before_s": _r(before),
        "after_s": _r(after),
        "delta_s": _r(after - before),
        "removed": removed,
        "warning": None,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--calltime", required=True)
    ap.add_argument("--removed", action="append", default=[])
    ap.add_argument("--language", default="python")
    a = ap.parse_args()
    with open(a.evidence, encoding="utf-8") as f:
        evidence = json.load(f)
    try:
        with open(a.calltime, encoding="utf-8") as f:
            after = json.load(f)
    except FileNotFoundError:
        after = None  # no hook output: figures are omitted with a warning
    json.dump(call_time_delta(evidence, after, a.removed, a.language), sys.stdout, indent=1)
    sys.stdout.write("\n")
