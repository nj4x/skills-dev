#!/usr/bin/env python3
"""Critic loop helpers: validate agent JSON and maintain the issue ledger.

  critic_ledger.py validate <verdict-file>
  critic_ledger.py flagged <flagged-file>
  critic_ledger.py upsert <ledger-file> <verdict-file> --groups A,B,C,F [--prior-major N]

Exit 1 with a one-line reason on stderr on any invalid input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_ISSUE = re.compile(r"^\[(?P<group>[A-Z])\]\[(?P<severity>major|minor|critical)\]\s*(?P<body>.*)$", re.DOTALL)


def _fail(reason: str) -> None:
    print(reason, file=sys.stderr)
    sys.exit(1)


def _strip_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _load_json(path: str) -> object:
    try:
        return json.loads(_strip_fence(Path(path).read_text()))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"PARSE_ERROR: {exc}")
        raise


def validate_verdict(data: object) -> dict:
    if not isinstance(data, dict):
        _fail("PARSE_ERROR: expected a JSON object")
    for key, valid in (("verdict", {"approve", "revise"}), ("severity", {"none", "minor", "major"})):
        if key not in data:
            _fail(f"MISSING_FIELD: {key}")
        if data[key] not in valid:
            _fail(f"INVALID_VALUE: {key}={data[key]!r}")
    if data["verdict"] == "approve" and data["severity"] == "major":
        _fail("INVALID_COMBINATION: verdict=approve cannot have severity=major")
    if data["verdict"] == "revise" and data["severity"] == "none":
        _fail("INVALID_COMBINATION: verdict=revise cannot have severity=none")
    for key in ("top_issues", "suggested_fixes"):
        if not isinstance(data.get(key), list):
            _fail(f"MISSING_OR_INVALID: {key}")
    return data


def validate_flagged(data: object) -> list:
    if not isinstance(data, list):
        _fail("FLAGGED_DECISIONS_PARSE_ERROR: expected array")
    for item in data:
        if not isinstance(item, dict) or "decision" not in item or "why_flagged" not in item:
            _fail(f"FLAGGED_DECISIONS_PARSE_ERROR: missing key in {item}")
    return data


def _claim_key(text: str) -> str:
    claim = text.split(" — ")[0]
    return re.sub(r"\W+", " ", claim).strip().lower()


def upsert(ledger: list[dict], verdict: dict, groups: set[str]) -> list[dict]:
    by_key = {_claim_key(rec["claim"]): rec for rec in ledger}
    seen: set[str] = set()
    next_id = len(ledger) + 1
    for issue in verdict["top_issues"]:
        match = _ISSUE.match(issue.strip())
        if match is None:
            _fail(f"UNPREFIXED_ISSUE: {issue[:80]!r}")
        claim, _, evidence = match["body"].partition(" — ")
        key = _claim_key(claim)
        seen.add(key)
        severity = "major" if match["severity"] == "critical" else match["severity"]
        record = by_key.get(key)
        if record is None:
            record = {
                "id": f"ID-{next_id:03d}", "group": match["group"], "claim": claim.strip(),
                "evidence": evidence.strip(), "severity": severity, "fix": "", "status": "open",
                "introduced_pass": None,
            }
            next_id += 1
            ledger.append(record)
            by_key[key] = record
        else:
            record.update(evidence=evidence.strip(), severity=severity)
            if record["status"] == "fixed":
                record["status"] = "open"
    for record in ledger:
        if record["status"] == "open" and record["group"] in groups and _claim_key(record["claim"]) not in seen:
            record["status"] = "fixed"
    return ledger


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate").add_argument("verdict_file")
    sub.add_parser("flagged").add_argument("flagged_file")
    up = sub.add_parser("upsert")
    up.add_argument("ledger_file")
    up.add_argument("verdict_file")
    up.add_argument("--groups", required=True)
    up.add_argument("--prior-major", type=int)
    args = parser.parse_args()

    if args.cmd == "validate":
        print(json.dumps(validate_verdict(_load_json(args.verdict_file))))
    elif args.cmd == "flagged":
        print(json.dumps(validate_flagged(_load_json(args.flagged_file))))
    else:
        verdict = validate_verdict(_load_json(args.verdict_file))
        path = Path(args.ledger_file)
        ledger = json.loads(path.read_text()) if path.exists() else []
        ledger = upsert(ledger, verdict, set(args.groups.split(",")))
        path.write_text(json.dumps(ledger, indent=2) + "\n")
        open_major = sum(1 for r in ledger if r["status"] == "open" and r["severity"] == "major")
        halt = args.prior_major is not None and open_major >= args.prior_major
        print(json.dumps({"open_major": open_major, "halt": halt}))


if __name__ == "__main__":
    main()
