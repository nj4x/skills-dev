#!/usr/bin/env python3
"""Critic loop helpers: validate agent JSON and maintain the issue ledger.

  critic_ledger.py validate <verdict-file>
  critic_ledger.py flagged <flagged-file>
  critic_ledger.py upsert <ledger-file> <verdict-file> --groups A,B,C,F [--prior-major N]
  critic_ledger.py render-prompt --artifact-type T --iteration N --groups A,B,C,F --artifact-file F
      [--adr-file P ...] [--codebase-root P] [--group-g-ok] [--constructs-file F] [--ledger F]
      [--effort higher] [--verdict-out F] [--spec-ref TEXT] [--base-dir D] --out F

For --artifact-type tickets, --artifact-file is the manifest: the script appends the body of every
ticket file it lists (paths resolve against --base-dir, default the current directory).

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


_GROUP_HEADER = re.compile(r"^GROUP ([A-Z]) — ")
_LEFTOVER = re.compile(r"\[insert |\[IF |\[ELSE|\[END IF\]|<CODEBASE_ROOT|<artifact_type>|<groups>")


def _atom(atom: str, ctx: dict) -> bool:
    if m := re.fullmatch(r"artifact_type == (\S+)", atom):
        return ctx["artifact_type"] == m[1]
    if m := re.fullmatch(r"artifact_type IN \{([^}]*)\}", atom):
        return ctx["artifact_type"] in {v.strip() for v in m[1].split(",")}
    if m := re.fullmatch(r"iteration (>=|==) (\d+)", atom):
        return ctx["iteration"] >= int(m[2]) if m[1] == ">=" else ctx["iteration"] == int(m[2])
    if atom == "group_g_ok":
        return ctx["group_g_ok"]
    if atom == "spec_ref":
        return bool(ctx["spec_ref"])
    if atom == "critic_induced_constructs is non-empty":
        return bool(ctx["constructs"])
    _fail(f"UNKNOWN_CONDITION: {atom}")
    return False


def _cond(expr: str, ctx: dict) -> bool:
    return all(_atom(a.strip(), ctx) for a in re.split(r"\s+AND\s+", expr.strip()))


def _resolve_conditionals(text: str, ctx: dict) -> str:
    out: list[str] = []
    frames: list[dict] = []  # parent_active, matched, active
    for line in text.splitlines():
        s = line.strip()
        parent = frames[-1]["active"] if frames else True
        if s.startswith("[IF ") and s.endswith("]"):
            hit = parent and _cond(s[4:-1], ctx)
            frames.append({"parent": parent, "matched": hit, "active": hit})
        elif s.startswith("[ELSE IF ") and s.endswith("]") and frames:
            f = frames[-1]
            hit = f["parent"] and not f["matched"] and _cond(s[9:-1], ctx)
            f["matched"] |= hit
            f["active"] = hit
        elif s == "[ELSE]" and frames:
            f = frames[-1]
            f["active"] = f["parent"] and not f["matched"]
            f["matched"] = True
        elif s == "[END IF]" and frames:
            frames.pop()
        elif parent:
            out.append(line)
    if frames:
        _fail("UNBALANCED_CONDITIONALS: missing [END IF]")
    return "\n".join(out)


def _keep_groups(text: str, groups: set[str]) -> str:
    out: list[str] = []
    keep = True
    for line in text.splitlines():
        if m := _GROUP_HEADER.match(line):
            keep = m[1] in groups
        elif line.strip() == "---":
            keep = True
        if keep:
            out.append(line)
    return "\n".join(out)


_BAD_PATH = re.compile(r"[;|&$()`]")


def _expand_tickets(manifest: str, manifest_name: str, base: Path) -> str:
    """Append the body of every ticket file the manifest lists, in manifest order."""
    lines = manifest.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i, ln in enumerate(lines[1:], 1) if ln.strip() == "---"), 0)
        lines = lines[end + 1:]
    parts = [manifest]
    for line in lines:
        rel = line.strip()
        if not rel or rel.startswith("#"):
            continue
        if rel.startswith("/") or ".." in Path(rel).parts or _BAD_PATH.search(rel):
            raise ValueError(f"manifest {manifest_name}: invalid ticket path {rel!r}")
        path = base / rel
        if not path.is_file():
            raise ValueError(f"manifest {manifest_name}: missing ticket file {rel!r}")
        parts.append(f"===== {rel} =====\n{path.read_text().strip()}")
    return "\n\n".join(parts)


def render_prompt(args: argparse.Namespace) -> str:
    template = Path(args.template).read_text()
    start, end = template.index("```\n") + 4, template.rindex("\n```")
    body = template[start:end]
    groups = args.groups.split(",")
    constructs = Path(args.constructs_file).read_text().strip() if args.constructs_file else ""
    ctx = {
        "artifact_type": args.artifact_type, "iteration": args.iteration,
        "group_g_ok": args.group_g_ok, "constructs": constructs, "spec_ref": args.spec_ref,
    }
    text = _keep_groups(_resolve_conditionals(body, ctx), set(groups))
    artifact = Path(args.artifact_file).read_text().strip()
    if args.artifact_type == "tickets":
        artifact = _expand_tickets(artifact, args.artifact_file, Path(args.base_dir))
    text = text.replace("[insert spec_ref verbatim]", args.spec_ref)
    adr = "\n\n".join(f"=== {p} ===\n{Path(p).read_text().strip()}" for p in args.adr_file)
    text = text.replace("`<groups>`", ", ".join(groups)).replace("[plan|design]", "plan" if args.artifact_type == "plan" else "design")
    text = text.replace("<artifact_type>", args.artifact_type)
    text = re.sub(r"^\[insert each ledger construct.*\]$", lambda _: constructs, text, flags=re.MULTILINE)
    text = re.sub(r"^\[insert adr_content verbatim.*\]$", lambda _: adr, text, flags=re.MULTILINE)
    text = re.sub(r"^\[insert (artifact|content) verbatim.*\]$", lambda _: artifact, text, flags=re.MULTILINE)
    text = re.sub(r"^CODEBASE_ROOT: <.*>$", lambda _: f"CODEBASE_ROOT: {args.codebase_root}", text, flags=re.MULTILINE)
    if args.iteration >= 1 and args.ledger and Path(args.ledger).exists():
        open_major = [r for r in json.loads(Path(args.ledger).read_text()) if r["status"] == "open" and r["severity"] == "major"]
        lines = [f"- {r['id']} (group {r['group']}): {r['claim']}" + ("" if r["group"] in groups else " [group not running this pass]") for r in open_major]
        summary = "LEDGER SUMMARY (open majors from prior passes; a claim you no longer raise is recorded as fixed):\n" + ("\n".join(lines) or "- none")
        text = text.replace("---\n\nSUB-AGENT PROMPTS", f"{summary}\n\n---\n\nSUB-AGENT PROMPTS", 1)
    if left := _LEFTOVER.search(text):
        _fail(f"UNFILLED_DIRECTIVE: {left[0]!r}")
    if args.verdict_out:
        text += (
            f"\n\nVERDICT DELIVERY (overrides the reply format above): write the merged JSON object, "
            f"raw with no fences, to `{args.verdict_out}` with the Write tool. "
            f"Your final reply is only that path.\n"
        )
    if args.effort == "higher":
        text = "Think step by step and reason at maximum depth before producing your JSON verdict.\n\n" + text
    return re.sub(r"\n{3,}", "\n\n", text) + "\n"


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
    rp = sub.add_parser("render-prompt")
    rp.add_argument("--artifact-type", required=True, choices=["plan", "design-review", "spec", "tickets"])
    rp.add_argument("--iteration", type=int, required=True)
    rp.add_argument("--groups", required=True)
    rp.add_argument("--artifact-file", required=True)
    rp.add_argument("--adr-file", action="append", default=[])
    rp.add_argument("--codebase-root", default="")
    rp.add_argument("--group-g-ok", action="store_true")
    rp.add_argument("--constructs-file")
    rp.add_argument("--ledger")
    rp.add_argument("--effort", default="normal")
    rp.add_argument("--verdict-out")
    rp.add_argument("--spec-ref", default="")
    rp.add_argument("--base-dir", default=".")
    rp.add_argument("--template", default=str(Path(__file__).resolve().parent.parent / "docs" / "critic-prompt.md"))
    rp.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.cmd == "render-prompt":
        try:
            Path(args.out).write_text(render_prompt(args))
        except (OSError, ValueError) as exc:
            _fail(f"RENDER_ERROR: {exc}")
        print(json.dumps({"out": args.out}))
    elif args.cmd == "validate":
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
