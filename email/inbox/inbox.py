#!/usr/bin/env python3
"""
inbox.py — preference store and report generator for the inbox skill.

Touches only ~/.claude/skills/inbox/prefs.json. No IMAP, no credentials.

Subcommands:
  load-prefs              -> prints prefs.json (or an empty template if absent)
  save-prefs              -> reads full prefs JSON from stdin, writes atomically
  generate-report-md      -> reads session JSON from stdin, writes Markdown to stdout

All output is JSON on stdout (except generate-report-md which writes Markdown).
Errors: {"error":..,"detail":..} + exit 1.
"""
import json
import os
import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).parent
_PREFS_FILE = _SKILL_DIR / "prefs.json"
_TMP_FILE = _SKILL_DIR / ".prefs.json.tmp"

_EMPTY = {"version": 1, "last_updated": None, "categories": {}}


def _out(data):
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _exit_error(error, detail=""):
    print(json.dumps({"error": error, "detail": detail}))
    sys.exit(1)


def cmd_load_prefs(_args):
    if not _PREFS_FILE.exists():
        _out(_EMPTY)
        return
    try:
        data = json.loads(_PREFS_FILE.read_text())
    except json.JSONDecodeError as e:
        _exit_error("prefs_corrupt", f"{_PREFS_FILE} is not valid JSON: {e}")
    # tolerate a missing categories key
    if "categories" not in data:
        data["categories"] = {}
    _out(data)


def cmd_save_prefs(args):
    if getattr(args, "from_file", None):
        path = Path(args.from_file)
        if not path.exists():
            _exit_error("file_not_found", f"--from-file path does not exist: {path}")
        raw = path.read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()

    if not raw.strip():
        _exit_error(
            "empty_input",
            "save-prefs expects a JSON object on stdin or via --from-file <path>.",
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        _exit_error("invalid_json", f"Input is not valid JSON: {e}")
    if not isinstance(data, dict) or "categories" not in data:
        _exit_error("bad_schema", 'prefs must be an object with a "categories" key.')

    data.setdefault("version", 1)
    # atomic write: tmp then rename
    _TMP_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(_TMP_FILE, _PREFS_FILE)
    print(json.dumps({"status": "saved", "path": str(_PREFS_FILE)}))


_ACTION_LABELS = {
    "mark_read": "Marked as read",
    "trash":     "Moved to Trash",
    "archive":   "Archived",
    "summary":   "Summarized",
    "dive_deep": "Deep-dived",
    "skip":      "Left untouched",
}

_BULLET_CAP = 50


def cmd_generate_report_md(_args):
    raw = sys.stdin.read()
    if not raw.strip():
        _exit_error("empty_input", "generate-report-md expects a JSON object on stdin.")
    try:
        session = json.loads(raw)
    except json.JSONDecodeError as e:
        _exit_error("invalid_json", f"stdin is not valid JSON: {e}")
    if not isinstance(session, dict) or "categories" not in session:
        _exit_error("bad_schema", 'session JSON must be an object with a "categories" key.')

    lines = []
    summary_rows = []

    for cat in session["categories"]:
        name = cat.get("name", "Unknown")
        action = cat.get("action", "skip")
        count = cat.get("count", 0)
        messages = cat.get("messages") or []
        digest = cat.get("digest")
        label = _ACTION_LABELS.get(action, action)

        lines.append(f"# {name}")
        lines.append(f"## {label} — {count} messages")
        lines.append("")

        if action in ("summary", "dive_deep") and digest:
            lines.append(digest)
        elif action == "skip":
            lines.append(f"These {count} messages were left untouched.")
        else:
            shown = messages[:_BULLET_CAP]
            for msg in shown:
                frm = msg.get("from", "")
                subj = msg.get("subject", "")
                lines.append(f"- From: {frm} · Subject: {subj}")
            if len(messages) > _BULLET_CAP:
                lines.append(f"+ {len(messages) - _BULLET_CAP} more")

        lines.append("")
        summary_rows.append((name, label, count))

    lines.append("# Session Summary")
    lines.append("## Totals")
    lines.append("")
    lines.append("| Category | Action | Count |")
    lines.append("|---|---|---|")
    for name, label, count in summary_rows:
        lines.append(f"| {name} | {label} | {count} |")
    lines.append("")

    print("\n".join(lines))


def main():
    import argparse
    p = argparse.ArgumentParser(description="Preference store and report generator for the inbox skill.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("load-prefs", help="Print prefs.json (or empty template)").set_defaults(func=cmd_load_prefs)
    sp = sub.add_parser("save-prefs", help="Write prefs JSON atomically (stdin or --from-file)")
    sp.add_argument("--from-file", metavar="PATH",
                    help="Read JSON from this file instead of stdin (avoids shell escaping issues)")
    sp.set_defaults(func=cmd_save_prefs)
    sub.add_parser("generate-report-md", help="Write Markdown report from session JSON on stdin").set_defaults(func=cmd_generate_report_md)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
