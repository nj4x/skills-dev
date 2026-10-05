#!/usr/bin/env python3
"""Render review-brief.md into the prompt for the fresh review agent.

Usage:
    python3 render_review_brief.py --ticket 435 \
        --worktree /abs/path --branch 435-slug --git "/usr/bin/git" \
        --build-cmd "uv run ruff check . && uv run pyright" \
        --test-evidence "7916 passed, 12 skipped in 677.42s (full suite: python -m pytest)" \
        --check "Does <symbol> do <ticket requirement>?" --check "Does <decision beyond the ticket> hold on <input>?"

Fixed text comes from review-brief.md; only the slots take input, so the brief carries no
paraphrase of the diff. Works with any test runner. Exits 1 with the reason when the test evidence holds no count,
no check is given, or a check is not a question (ends without `?`).
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


def _slots(args: argparse.Namespace) -> dict[str, str]:
    if not SUMMARY.search(args.test_evidence):
        sys.exit(
            "--test-evidence quotes the Test step's summary line verbatim from the test runner, counts included "
            "(`7916 passed in 677s`, `Tests run: 12, Failures: 0`, `ok ./... 0.4s`), or reads `docs-only: lint only`"
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
    return {
        "scope": args.scope,
        "ticket": str(args.ticket),
        "worktree": args.worktree,
        "branch": args.branch,
        "effort": args.effort,
        "git": args.git,
        "build_cmd": _escape(_escape(args.build_cmd)),
        "test_evidence": args.test_evidence.strip(),
        "diff_changed": args.diff_changed.strip(),
        "checks": "\n".join(f"{n}. {c}" for n, c in enumerate(checks, start=1)),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry: print the filled brief."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ticket", type=int, required=True)
    parser.add_argument("--worktree", required=True, help="absolute worktree path")
    parser.add_argument("--branch", required=True)
    parser.add_argument("--git", default="git", help="git command form the repo requires")
    parser.add_argument("--build-cmd", required=True, help="lint && type-check; tests belong to the Test step")
    parser.add_argument("--test-evidence", required=True)
    parser.add_argument("--scope", choices=["working-tree", "committed"], default="working-tree")
    parser.add_argument("--effort", choices=["normal", "low"], default="normal")
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
