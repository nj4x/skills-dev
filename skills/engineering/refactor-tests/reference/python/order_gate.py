"""Random-order gate for refactor-tests: plugin choice, classification, plan demotion.

Usage:
  python order_gate.py plugin --random-order-present yes|no --randomly-present yes|no [--seed N]
  python order_gate.py classify --baseline baseline.json --gate gate.xml [--rerun rerun.xml] --seed N
  python order_gate.py demote --plan simplification-plan.json --gate-result result.json [--out FILE]

`plugin` prints {plugin, with, args, seed}. A project that already has
pytest-random-order keeps it with `--random-order-bucket=global` (plus `-p no:randomly`
when pytest-randomly is installed too); otherwise pytest-randomly runs, installed only
for the gate run when `with` names it. Exactly one shuffler is ever active. Without
--seed a seed is drawn.

`classify` reads the baseline ({"passed": [ids] | count, "failed": [ids]}, the ledger
shape) and the JUnit XML of the seeded gate run and, when given, of the same-seed full
re-run. Ids are compared as JUnit `classname::name`; node-id baselines (`path.py::Class::name`) are converted. A test that is not passing in the baseline is
excluded and listed (`failed`, or `not-in-baseline` when the baseline lists passing ids
and the id is absent). A baseline-passing test that fails (or errors) in the gate run
is a candidate: without --rerun the output sets `rerun_required: true`; with it, a
candidate that does not pass in the re-run is `order-dependent`, one that passes is
`flaky`.

`demote` moves every planned removal, parametrize merge, or kept duplicate
(`duplicate_of`, with `duplicate_of_file` when elsewhere, on an exact-duplicate removal) that involves an `order-dependent` or
`flaky` test to `review_candidates`, one entry per involved test and criterion, with
`seed` and `failing_ids`. The plan is rewritten atomically (to --out, default --plan).
"""
import argparse
import copy
import json
import os
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CRITERIA = ("order-dependent", "flaky")
FAILING = ("failed", "error")


def choose_plugin(random_order_present, randomly_present, seed):
    if random_order_present:
        args = ["-p", "no:randomly"] if randomly_present else []
        args += ["--random-order-bucket=global", f"--random-order-seed={seed}"]
        return {"plugin": "pytest-random-order", "with": [], "args": args, "seed": seed}
    return {
        "plugin": "pytest-randomly",
        "with": [] if randomly_present else ["pytest-randomly"],
        "args": [f"--randomly-seed={seed}"],
        "seed": seed,
    }


def read_junit(path):
    outcomes = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        tid = f"{case.get('classname', '')}::{case.get('name', '')}"
        if case.find("error") is not None:
            outcome = "error"
        elif case.find("failure") is not None:
            outcome = "failed"
        elif case.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        outcomes[tid] = outcome
    return outcomes


def classify(baseline, gate, rerun, seed):
    # Baseline ids may be node ids (ledger, baseline-ids.json) or JUnit ids; compare in JUnit form.
    failed = {normalize_id(t) for t in baseline.get("failed") or []}
    passed = baseline.get("passed")
    pass_list = {normalize_id(t) for t in passed} if isinstance(passed, list) else None
    gate = {normalize_id(t): o for t, o in gate.items()}
    rerun = None if rerun is None else {normalize_id(t): o for t, o in rerun.items()}

    def baseline_status(tid):
        if tid in failed:
            return "failed"
        if pass_list is not None and tid not in pass_list:
            return "not-in-baseline"
        return "passed"

    excluded = []
    candidates = []
    for tid in sorted(gate):
        status = baseline_status(tid)
        if status != "passed":
            excluded.append({"id": tid, "baseline": status})
        elif gate[tid] in FAILING:
            candidates.append(tid)
    for tid in sorted(failed - set(gate)):
        excluded.append({"id": tid, "baseline": "failed"})
    excluded.sort(key=lambda e: e["id"])

    result = {"seed": seed, "order_dependent": [], "flaky": [], "excluded": excluded,
              "candidates": candidates, "rerun_required": False}
    if not candidates:
        return result
    if rerun is None:
        result["rerun_required"] = True
        return result
    for tid in candidates:
        key = "flaky" if rerun.get(tid) == "passed" else "order_dependent"
        result[key].append(tid)
    return result


def _strip_params(test_id):
    base, bracket, params = test_id.partition("[")
    return base, bracket + params


def _split(test_id):
    """Return (head, name) with the `[params]` suffix removed before any split."""
    base, _ = _strip_params(test_id)
    parts = base.split("::")
    return parts[0], parts[-1]


def _module(file):
    p = file[:-3] if file.endswith(".py") else file
    return p.replace("/", ".").replace("\\", ".")


def normalize_id(test_id):
    """Node id (`tests/a/test_x.py::Cls::test[p]`) to JUnit form (`tests.a.test_x.Cls::test[p]`).

    A JUnit-form id passes through unchanged.
    """
    base, params = _strip_params(test_id)
    parts = base.split("::")
    if not parts[0].endswith(".py"):
        return test_id
    classname = ".".join([_module(parts[0])] + parts[1:-1])
    return f"{classname}::{parts[-1]}{params}"


def matches(test_id, file, test_name):
    head, name = _split(test_id)
    want = _strip_params(test_name.split("::")[-1].split(".")[-1])[0]
    if name != want:
        return False
    if head.endswith(".py"):
        return head == file
    mod = _module(file)
    return head == mod or head.startswith(mod + ".")


def _involved(entry, kind):
    """(file, test name) pairs a planned change involves."""
    if kind == "parametrizations":
        return [(entry["file"], n) for n in entry.get("tests") or []]
    pairs = [(entry["file"], entry["test_name"])]
    if entry.get("duplicate_of"):
        pairs.append((entry.get("duplicate_of_file") or entry["file"], entry["duplicate_of"]))
    return pairs


def demote(plan, gate_result):
    out = copy.deepcopy(plan)
    seed = gate_result.get("seed")
    flagged = {
        "order-dependent": list(gate_result.get("order_dependent") or []),
        "flaky": list(gate_result.get("flaky") or []),
    }
    review = out.setdefault("review_candidates", [])
    for kind in ("removals", "parametrizations"):
        kept = []
        for entry in out.get(kind) or []:
            pairs = _involved(entry, kind)
            hits = {}
            for crit in CRITERIA:
                ids = [t for t in flagged[crit] if any(matches(t, f, n) for f, n in pairs)]
                if ids:
                    hits[crit] = ids
            if not hits:
                kept.append(entry)
                continue
            change = "parametrize merge" if kind == "parametrizations" else "removal"
            for crit, ids in hits.items():
                for f, n in pairs:
                    review.append({
                        "file": f,
                        "test_name": n,
                        "criterion": crit,
                        "evidence": f"planned {change} ({entry.get('criterion')}) involves a {crit} test "
                                    f"under random order, seed {seed}",
                        "seed": seed,
                        "failing_ids": ids,
                    })
        if kind in out:
            out[kind] = kept
    if not review and "review_candidates" not in plan:
        del out["review_candidates"]
    return out


def _write_atomic(path, doc):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n")
    os.replace(tmp, path)


def _yes(v):
    return v == "yes"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plugin")
    p.add_argument("--random-order-present", choices=("yes", "no"), required=True)
    p.add_argument("--randomly-present", choices=("yes", "no"), required=True)
    p.add_argument("--seed", type=int)
    c = sub.add_parser("classify")
    c.add_argument("--baseline", required=True)
    c.add_argument("--gate", required=True)
    c.add_argument("--rerun")
    c.add_argument("--seed", type=int, required=True)
    d = sub.add_parser("demote")
    d.add_argument("--plan", required=True)
    d.add_argument("--gate-result", required=True)
    d.add_argument("--out")
    a = ap.parse_args(argv)

    if a.cmd == "plugin":
        seed = a.seed if a.seed is not None else random.randint(1, 2**31 - 1)
        doc = choose_plugin(_yes(a.random_order_present), _yes(a.randomly_present), seed)
    elif a.cmd == "classify":
        baseline = json.loads(Path(a.baseline).read_text())
        rerun = read_junit(a.rerun) if a.rerun else None
        doc = classify(baseline, read_junit(a.gate), rerun, a.seed)
    else:
        plan = json.loads(Path(a.plan).read_text())
        gate = json.loads(Path(a.gate_result).read_text())
        _write_atomic(a.out or a.plan, demote(plan, gate))
        return 0
    json.dump(doc, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
