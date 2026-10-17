"""Assemble test-evidence.json (schema v1) for one language from the two runs.

Usage:
  python assemble_evidence.py --arcs arcs.json --calltime calltime.json \
      --id-basis post-layout|pre-layout \
      --tool coverage=7.16.2 --command coverage='<cmd>' --command timing='<cmd>' \
      [--status ok|skipped|failed --reason TEXT] [--existing FILE] --out FILE

Only tests whose call outcome is `passed` get an entry; the others are listed
under `excluded` with their outcome. Ids seen by only one run are excluded too:
a passed test with no `|run` context in --arcs gets outcome `no-coverage`, and
an id in --arcs with no timing row gets `no-timing`. With --status
skipped|failed, `tests` stays empty and --reason is required. --existing merges
into an evidence file already holding another language; a missing --existing
file counts as empty. --id-basis is required: `post-layout` when ledger
`simplification.post_layout_baseline` is set (Phase A moved the tests),
`pre-layout` when it is not (`--dry-run` or `--phases=B`: no file moved).
Read the ledger, not the flags. An --existing file with another id_basis is
refused. --out is written atomically (temp file, then rename).
`kill_set` is reserved for a later version and not written in v1.
"""
import argparse
import json
import os
import sys

ID_BASES = ("post-layout", "pre-layout")


def _language_block(arcs, calltime, tools, commands, status, reason):
    block = {"status": status, "tools": tools, "commands": commands, "tests": {}, "excluded": []}
    if reason:
        block["reason"] = reason
    if status != "ok":
        return block
    for nodeid, row in sorted(calltime.items()):
        if row.get("outcome") != "passed":
            block["excluded"].append({"id": nodeid, "outcome": row.get("outcome")})
            continue
        if nodeid not in arcs:
            block["excluded"].append({"id": nodeid, "outcome": "no-coverage"})
            continue
        block["tests"][nodeid] = {
            "outcome": "passed",
            "call_s": round(row["duration"], 6),
            "covered": arcs[nodeid],
        }
    for nodeid in sorted(set(arcs) - set(calltime)):
        block["excluded"].append({"id": nodeid, "outcome": "no-timing"})
    return block


def assemble(arcs, calltime, *, tools, commands, id_basis, status="ok", reason=None,
             language="python", existing=None):
    if id_basis not in ID_BASES:
        raise ValueError(f"id_basis {id_basis!r} is not one of {ID_BASES}")
    if status != "ok" and not reason:
        raise ValueError(f"status {status!r} requires a reason")
    if existing and existing.get("id_basis") != id_basis:
        raise ValueError(
            f"existing id_basis {existing.get('id_basis')!r} differs from {id_basis!r}"
        )
    doc = existing or {
        "schema_version": 1,
        "id_basis": id_basis,
        "languages": {},
    }
    doc["languages"][language] = _language_block(
        arcs or {}, calltime or {}, tools, commands, status, reason
    )
    return doc


def _pairs(items):
    return dict(item.split("=", 1) for item in items or [])


def _load(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_atomic(path, doc):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arcs")
    ap.add_argument("--calltime")
    ap.add_argument("--language", default="python")
    ap.add_argument("--id-basis", required=True, choices=ID_BASES)
    ap.add_argument("--tool", action="append")
    ap.add_argument("--command", action="append")
    ap.add_argument("--status", default="ok", choices=["ok", "skipped", "failed"])
    ap.add_argument("--reason")
    ap.add_argument("--existing")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    existing = _load(a.existing) or None
    try:
        doc = assemble(
            _load(a.arcs), _load(a.calltime),
            tools=_pairs(a.tool), commands=_pairs(a.command),
            id_basis=a.id_basis, status=a.status, reason=a.reason,
            language=a.language, existing=existing,
        )
    except ValueError as e:
        sys.exit(f"assemble_evidence: {e}")
    _write_atomic(a.out, doc)
    sys.stderr.write(f"wrote {a.out}\n")
