"""Convert a pytest JUnit XML into passed/failed/skipped pytest node-id lists.

Usage:
  python junit_to_nodeids.py --junit run.xml --collected collected.txt [--out FILE]

JUnit names a test `classname` + `name` (`tests.a.test_x.Cls` + `test[p]`), not by node
id. `--collected` is the stdout of `pytest --collect-only -q` with the same runner
command and rootdir: every line holding `::` is a node id, the rest (summary, warnings)
is ignored. Each collected id is converted to JUnit form (`order_gate.normalize_id`) and
each JUnit testcase is mapped back through that table.

Prints (or writes atomically to --out) JSON with sorted keys:
  {"passed": [ids], "failed": [ids], "skipped": [ids], "unmapped": [junit ids],
   "counts": {"passed": N, "failed": N, "skipped": N, "unmapped": N}}
An `error` testcase counts as failed. `unmapped` lists JUnit ids no collected id converts
to (a different rootdir, or a test collected only in one run); they are never guessed.
Two collected ids with one JUnit form are ambiguous: exit 2, nothing written.
"""
import argparse
import json
import sys

from order_gate import normalize_id, read_junit
from refactor_tests_shared import write_atomic

BUCKET = {"passed": "passed", "failed": "failed", "error": "failed", "skipped": "skipped"}


def read_collected(text):
    """Node ids from `pytest --collect-only -q` output, in order, duplicates dropped."""
    seen = []
    for line in text.splitlines():
        line = line.strip()
        if "::" in line and not line.startswith(("=", "-")) and line not in seen:
            seen.append(line)
    return seen


def junit_index(node_ids):
    """Map JUnit-form id to node id; raise ValueError when two node ids share a form."""
    index = {}
    for nid in node_ids:
        key = normalize_id(nid)
        if key in index and index[key] != nid:
            raise ValueError(f"ambiguous JUnit id {key}: {index[key]} and {nid}")
        index[key] = nid
    return index


def convert(outcomes, node_ids):
    """Bucket JUnit outcomes (`order_gate.read_junit` shape) into node-id lists."""
    index = junit_index(node_ids)
    result = {"passed": [], "failed": [], "skipped": [], "unmapped": []}
    for jid, outcome in outcomes.items():
        nid = index.get(jid)
        if nid is None:
            result["unmapped"].append(jid)
        else:
            result[BUCKET[outcome]].append(nid)
    for key in result:
        result[key].sort()
    result["counts"] = {k: len(v) for k, v in result.items()}
    return result


def main(argv=None):
    """CLI entry point; returns the process exit code."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--junit", required=True)
    ap.add_argument("--collected", required=True)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    with open(args.collected, encoding="utf-8") as fh:
        node_ids = read_collected(fh.read())
    try:
        result = convert(read_junit(args.junit), node_ids)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.out:
        write_atomic(args.out, result)
    else:
        sys.stdout.write(json.dumps(result, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
