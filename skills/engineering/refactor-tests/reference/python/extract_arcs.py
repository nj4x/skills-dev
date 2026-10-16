"""Extract per-test covered lines and arcs from a coverage data file.

Usage: python extract_arcs.py <coverage-data-file> [--root DIR] > arcs.json

The data file comes from `pytest --cov-branch --cov-context=test`. Only `|run`
contexts count: setup and teardown coverage belongs to fixtures, not tests.
Output: { nodeid: { file: { "lines": [int], "arcs": [[int, int]] } } }, with
file paths relative to --root when the file lives under it. Every `|run` context
gets an entry, even when it covered nothing (then the value is {}).
Exits non-zero when the data file is missing or holds no `|run` context.
"""
import argparse
import json
import os
import re

from coverage import CoverageData

RUN_SUFFIX = "|run"


def _rel(path, root):
    if root:
        rel = os.path.relpath(path, root)
        if not rel.startswith(".."):
            return rel
    return path


def extract_arcs(data_file, root=None):
    if not os.path.isfile(data_file):
        raise FileNotFoundError(f"coverage data file not found: {data_file}")
    data = CoverageData(data_file)
    data.read()
    run_contexts = [c for c in sorted(data.measured_contexts()) if c.endswith(RUN_SUFFIX)]
    if not run_contexts:
        raise ValueError(f"no '{RUN_SUFFIX}' contexts in {data_file}; was --cov-context=test used?")
    result = {}
    for ctx in run_contexts:
        nodeid = ctx[: -len(RUN_SUFFIX)]
        # set_query_contexts takes regexes: anchor and escape the node id.
        data.set_query_contexts([f"^{re.escape(ctx)}$"])
        covered = {}
        for path in sorted(data.measured_files()):
            lines = sorted(data.lines(path) or [])
            arcs = sorted(data.arcs(path) or [])
            if lines or arcs:
                covered[_rel(path, root)] = {
                    "lines": lines,
                    "arcs": [list(a) for a in arcs],
                }
        result[nodeid] = covered
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data_file")
    ap.add_argument("--root", default=None)
    args = ap.parse_args()
    print(json.dumps(extract_arcs(args.data_file, args.root), indent=1, sort_keys=True))
