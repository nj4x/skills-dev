#!/usr/bin/env python3
"""Render review-brief.md into the prompt for the fresh review agent.

Usage:
    python3 render_review_brief.py --ticket 435 \
        --worktree /abs/path --branch 435-slug --git "/usr/bin/git" \
        --build-cmd "uv run ruff check . && uv run pyright" \
        --test-evidence "7916 passed, 12 skipped in 677.42s (full suite: python -m pytest)" \
        --check "Does <symbol> do <ticket requirement>?" --check "Does <decision beyond the ticket> hold on <input>?"

Integration review (implement-spec): add --spec and repeat --ticket once per merged ticket.

Each --spec and --ticket value is a GitHub issue number (all digits) or a file path, resolved against --worktree when relative.
Fixed text comes from review-brief.md; only the slots take input, so the brief carries no paraphrase of the diff. Works with any test runner. Exits 1 with the reason when the test evidence holds no digit, no check is given, a check is not a question (ends without `?`), --git is not a single git binary path, or a pointer is not an existing file.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TEMPLATE = Path(__file__).with_name("review-brief.md")
# Runner-neutral: every runner's summary line carries a count; a paraphrase like "all green" does not.
SUMMARY = re.compile(r"\d|docs-only: lint only")


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _is_issue(value: str) -> bool:
    return value.isascii() and value.isdigit()


def _pointer(value: str, worktree: str) -> str:
    if _is_issue(value):
        return value
    path = Path(value)
    if not path.is_absolute():
        path = Path(worktree) / path
    if not path.is_file():
        sys.exit(f"pointer is neither an issue number nor an existing file: {path}")
    return str(path)


def _label(pointer: str) -> str:
    return f"#{pointer}" if _is_issue(pointer) else pointer


def _source(pointer: str) -> str:
    if _is_issue(pointer):
        return f"{_label(pointer)} (`gh issue view {pointer} --json body -q .body`)"
    return f"`{pointer}` (Read tool)"


def _slots(args: argparse.Namespace) -> dict[str, str]:
    if not SUMMARY.search(args.test_evidence):
        sys.exit(
            "--test-evidence quotes the Test step's summary line verbatim from the test runner, counts included "
            "(`7916 passed in 677s`, `Tests run: 12, Failures: 0`, `ok ./... 0.4s`), or reads `docs-only: lint only`"
        )
    git_form = args.git.strip().split()
    if len(git_form) != 1 or Path(git_form[0]).name != "git":
        sys.exit(
            "--git is the git binary the reviewer prefixes to each subcommand, e.g. `git` or `/usr/bin/git`: "
            "a single path whose basename is `git`"
        )
    checks = [c.strip() for c in args.check if c.strip()]
    if not checks:
        sys.exit("give at least one --check: a ticket requirement the diff must satisfy, phrased as a question")
    claims = [c for c in checks if not c.endswith("?")]
    if claims:
        sys.exit(
            "each --check is a question the reviewer answers from code, ending in `?`; a claim invites "
            f"confirmation instead of a check. Rephrase: {claims}"
        )
    spec = _pointer(args.spec, args.worktree) if args.spec else None
    tickets = [_pointer(t, args.worktree) for t in args.ticket]
    names = ", ".join(_label(t) for t in tickets)
    if spec:
        subject = f"spec {_label(spec)} and tickets {names}"
    else:
        subject = f"{'ticket' if len(tickets) == 1 else 'tickets'} {names}"
    sources = ([f"spec {_source(spec)}"] if spec else []) + [f"ticket {_source(t)}" for t in tickets]
    return {
        "scope": args.scope,
        "subject": subject,
        "sources": ", ".join(sources),
        "worktree": args.worktree,
        "branch": args.branch,
        "effort": args.effort,
        "git": git_form[0],
        "build_cmd": _escape(_escape(args.build_cmd)),
        "test_evidence": args.test_evidence.strip(),
        "diff_changed": args.diff_changed.strip(),
        "checks": "\n".join(f"{n}. {c}" for n, c in enumerate(checks, start=1)),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry: print the filled brief."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--spec", help="spec pointer: GitHub issue number or file path")
    parser.add_argument(
        "--ticket", action="append", required=True, help="ticket pointer: GitHub issue number or file path; repeat"
    )
    parser.add_argument("--worktree", required=True, help="absolute worktree path")
    parser.add_argument("--branch", required=True)
    parser.add_argument("--git", default="git", help="git binary the repo requires, e.g. /usr/bin/git")
    parser.add_argument("--build-cmd", required=True, help="lint && type-check; tests belong to the Test step")
    parser.add_argument("--test-evidence", required=True)
    parser.add_argument("--scope", choices=["working-tree", "committed"], default="working-tree")
    parser.add_argument("--effort", choices=["high", "low"], default="high")
    parser.add_argument("--diff-changed", default="none (first review)")
    parser.add_argument("--check", action="append", default=[], help="one specific check; repeat")
    args = parser.parse_args(argv)
    slots = _slots(args)
    body = TEMPLATE.read_text().split("\n---\n", 1)[1].lstrip("\n")
    missing = set(re.findall(r"\{\{(\w+)\}\}", body)) - slots.keys()
    if missing:
        sys.exit(f"template slots without a value: {sorted(missing)}")
    sys.stdout.write(re.sub(r"\{\{(\w+)\}\}", lambda m: slots[m.group(1)], body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
