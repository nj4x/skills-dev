#!/usr/bin/env python3
"""
PR helper utilities for the code-review skill.

This script centralizes repetitive GitHub CLI interactions:
- discover related PR + unresolved review threads
- advisory triage of unresolved threads against local diff
- finding/thread de-duplication
- draft PR comments
- consent-gated publish comments and PR approval

Dependencies:
- python3 stdlib
- gh CLI authenticated for target host
- git repository context
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


CONFIRM_POST = "I_UNDERSTAND_POST_TO_PR"
CONFIRM_APPROVE = "I_UNDERSTAND_APPROVE_PR"

# Host override for gh subprocess calls. Populated by ensure_gh_available()
# once the repo's host is parsed from the remote URL. Ensures all subsequent
# `gh` invocations (including `gh api graphql`, which has no --repo flag)
# target the correct host — e.g. a GitHub Enterprise instance like
# github.your-company.com — instead of silently defaulting to github.com and
# failing auth with HTTP 401.
_GH_ENV: dict[str, str] = {}


class CommandError(RuntimeError):
    pass


def run(cmd: list[str], check: bool = True) -> str:
    env = None
    if _GH_ENV:
        env = {**os.environ, **_GH_ENV}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        raise CommandError(
            f"Command failed ({proc.returncode}): {' '.join(shlex.quote(c) for c in cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc.stdout.strip()


def run_json(cmd: list[str]) -> Any:
    out = run(cmd)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise CommandError(f"Failed to decode JSON from command output: {exc}\nOutput:\n{out}")


def ensure_git_repo() -> None:
    inside = run(["git", "rev-parse", "--is-inside-work-tree"])
    if inside != "true":
        raise CommandError("Current directory is not a git repository.")


@dataclass
class RepoInfo:
    host: str
    owner: str
    name: str


def parse_remote_url(remote_url: str) -> RepoInfo:
    # SSH format: git@host:owner/repo.git
    ssh_match = re.match(r"^git@([^:]+):([^/]+)/(.+?)(?:\.git)?$", remote_url)
    if ssh_match:
        return RepoInfo(host=ssh_match.group(1), owner=ssh_match.group(2), name=ssh_match.group(3))

    # HTTPS format: https://host/owner/repo.git
    https_match = re.match(r"^https?://([^/]+)/([^/]+)/(.+?)(?:\.git)?$", remote_url)
    if https_match:
        return RepoInfo(host=https_match.group(1), owner=https_match.group(2), name=https_match.group(3))

    raise CommandError(f"Unsupported git remote URL format: {remote_url}")


def detect_repo(remote: str = "origin") -> RepoInfo:
    remote_url = run(["git", "remote", "get-url", remote])
    return parse_remote_url(remote_url)


def ensure_gh_available(host: str) -> None:
    try:
        run(["gh", "--version"])
    except CommandError as exc:
        raise CommandError(f"gh CLI is not available: {exc}")
    try:
        run(["gh", "auth", "status", "--hostname", host])
    except CommandError as exc:
        raise CommandError(f"gh auth is not ready for host '{host}': {exc}")
    # Pin all subsequent `gh` calls in this process to the detected host so
    # commands without a --repo flag (e.g. `gh api graphql`) don't fall back
    # to github.com and fail with a 401 on enterprise deployments.
    _GH_ENV["GH_HOST"] = host


def current_branch() -> str:
    return run(["git", "branch", "--show-current"])


def find_pr(repo: RepoInfo, branch: str | None, pr_number: int | None, state: str) -> dict[str, Any]:
    fields = [
        "number",
        "title",
        "url",
        "state",
        "isDraft",
        "reviewDecision",
        "baseRefName",
        "headRefName",
        "headRefOid",
    ]
    repo_slug = f"{repo.owner}/{repo.name}"

    if pr_number is not None:
        return run_json(["gh", "pr", "view", str(pr_number), "--repo", repo_slug, "--json", ",".join(fields)])

    if not branch:
        branch = current_branch()

    items = run_json(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo_slug,
            "--head",
            branch,
            "--state",
            state,
            "--json",
            ",".join(fields),
        ]
    )

    if not items:
        raise CommandError(
            f"No PR found for branch '{branch}'. Provide --pr <number> or open/create PR first."
        )
    if len(items) > 1:
        numbers = ", ".join(str(i["number"]) for i in items)
        raise CommandError(f"Multiple PRs found for branch '{branch}' ({numbers}). Re-run with --pr <number>.")
    return items[0]


def get_review_threads(repo: RepoInfo, pr_number: int) -> list[dict[str, Any]]:
    query = (
        "query($owner:String!, $name:String!, $number:Int!) {"
        " repository(owner:$owner, name:$name) {"
        "  pullRequest(number:$number) {"
        "   reviewThreads(first:100) {"
        "    nodes {"
        "     isResolved isOutdated path line originalLine"
        "     comments(first:100) {"
        "      nodes { author { login } body url createdAt }"
        "     }"
        "    }"
        "   }"
        "  }"
        " }"
        "}"
    )
    payload = run_json(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"owner={repo.owner}",
            "-f",
            f"name={repo.name}",
            "-F",
            f"number={pr_number}",
            "-f",
            f"query={query}",
        ]
    )

    try:
        return payload["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    except Exception as exc:  # noqa: BLE001
        raise CommandError(f"Unexpected GraphQL response shape: {exc}\nPayload: {json.dumps(payload)[:1000]}")


def normalize_threads(threads: list[dict[str, Any]]) -> dict[str, Any]:
    unresolved: list[dict[str, Any]] = []
    for t in threads:
        if t.get("isResolved"):
            continue
        comments = t.get("comments", {}).get("nodes", [])
        latest = comments[-1] if comments else None
        unresolved.append(
            {
                "path": t.get("path"),
                "line": t.get("line"),
                "originalLine": t.get("originalLine"),
                "isOutdated": t.get("isOutdated", False),
                "commentCount": len(comments),
                "latestComment": {
                    "author": latest.get("author", {}).get("login") if latest else None,
                    "createdAt": latest.get("createdAt") if latest else None,
                    "url": latest.get("url") if latest else None,
                    "body": latest.get("body") if latest else None,
                },
            }
        )
    return {"totalThreads": len(threads), "unresolved": unresolved}


def cmd_discover(args: argparse.Namespace) -> dict[str, Any]:
    ensure_git_repo()
    repo = detect_repo(args.remote)
    ensure_gh_available(repo.host)

    pr = find_pr(repo, args.branch, args.pr, args.state)
    threads = get_review_threads(repo, pr["number"])
    normalized = normalize_threads(threads)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "repo": {"host": repo.host, "owner": repo.owner, "name": repo.name},
        "pr": pr,
        "threads": normalized,
    }


def parse_diff_changed_lines(base_ref: str) -> dict[str, list[tuple[int, int]]]:
    # Three-dot (merge-base) range so the triage line-ranges describe exactly the
    # lines this branch authored, matching the review diff and the GitHub PR view.
    # Two-dot here would absorb target-branch commits added after divergence and
    # mis-classify threads on base-only lines as touched by this branch.
    remote_base = f"origin/{base_ref}"
    merge_base = run(["git", "merge-base", "HEAD", remote_base], check=False)
    if not merge_base:
        merge_base = run(["git", "merge-base", "HEAD", base_ref], check=False)
    if not merge_base:
        raise CommandError(
            f"Unable to compute merge base for base ref '{base_ref}'. "
            "Ensure the branch is fetched and has a common ancestor."
        )

    try:
        diff = run(["git", "--no-pager", "diff", "--unified=0", f"{remote_base}...HEAD"])
    except CommandError:
        diff = run(["git", "--no-pager", "diff", "--unified=0", f"{base_ref}...HEAD"])
    changed: dict[str, list[tuple[int, int]]] = defaultdict(list)
    current_file: str | None = None

    file_re = re.compile(r"^diff --git a/(.+) b/(.+)$")
    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for line in diff.splitlines():
        fm = file_re.match(line)
        if fm:
            current_file = fm.group(2)
            continue
        hm = hunk_re.match(line)
        if hm and current_file:
            start = int(hm.group(1))
            count = int(hm.group(2) or "1")
            if count <= 0:
                continue
            end = start + count - 1
            changed[current_file].append((start, end))

    return dict(changed)


def line_in_ranges(line_num: int, ranges: list[tuple[int, int]], fuzz: int = 2) -> bool:
    for s, e in ranges:
        if (s - fuzz) <= line_num <= (e + fuzz):
            return True
    return False


def cmd_triage(args: argparse.Namespace) -> dict[str, Any]:
    payload = load_or_discover(args)
    base_ref = payload["pr"].get("baseRefName") or "main"
    changed = parse_diff_changed_lines(base_ref)

    triaged: list[dict[str, Any]] = []
    counts = {"likely_addressed": 0, "still_open": 0, "needs_confirmation": 0}

    for t in payload["threads"]["unresolved"]:
        path = t.get("path")
        line = t.get("line") or t.get("originalLine")
        status = "still_open"
        rationale = "Thread remains unresolved and file/line not touched by local diff."

        if t.get("isOutdated"):
            status = "likely_addressed"
            rationale = "Thread is marked outdated by platform."
        elif path in changed and line and line_in_ranges(int(line), changed[path]):
            status = "needs_confirmation"
            rationale = "Thread line appears touched by local diff; manual verification required."
        elif path in changed:
            status = "needs_confirmation"
            rationale = "File changed but thread line was not directly touched; manual verification recommended."

        counts[status] += 1
        triaged.append({**t, "triageStatus": status, "triageRationale": rationale})

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "repo": payload["repo"],
        "pr": payload["pr"],
        "summary": {
            "unresolvedCount": len(payload["threads"]["unresolved"]),
            **counts,
        },
        "threads": triaged,
    }


def load_findings(path: str) -> list[dict[str, Any]]:
    data = json.load(open(path, "r", encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("findings"), list):
        return data["findings"]
    raise CommandError("Findings JSON must be a list or an object with 'findings' list.")


def normalize_text(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def keyword_set(s: str | None) -> set[str]:
    words = re.findall(r"[a-z0-9_]+", normalize_text(s))
    return {w for w in words if len(w) >= 4}


def cmd_dedupe(args: argparse.Namespace) -> dict[str, Any]:
    findings = load_findings(args.findings)
    payload = load_or_discover(args)
    threads = payload["threads"]["unresolved"]

    tracked: list[dict[str, Any]] = []
    untracked: list[dict[str, Any]] = []

    for f in findings:
        f_path = f.get("path")
        f_line = f.get("line")
        f_text = " ".join(filter(None, [str(f.get("title") or ""), str(f.get("description") or "")]))
        f_kw = keyword_set(f_text)

        matched = None
        for t in threads:
            t_path = t.get("path")
            t_line = t.get("line") or t.get("originalLine")
            body = (t.get("latestComment") or {}).get("body")
            t_kw = keyword_set(body)

            same_path = f_path and t_path and f_path == t_path
            line_close = (
                same_path
                and f_line is not None
                and t_line is not None
                and abs(int(f_line) - int(t_line)) <= args.line_tolerance
            )
            kw_overlap = len(f_kw.intersection(t_kw)) >= args.keyword_overlap

            if line_close or (same_path and kw_overlap):
                matched = t
                break

        if matched:
            tracked.append({"finding": f, "thread": matched})
        else:
            untracked.append(f)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "repo": payload["repo"],
        "pr": payload["pr"],
        "summary": {
            "totalFindings": len(findings),
            "tracked": len(tracked),
            "untracked": len(untracked),
        },
        "tracked": tracked,
        "untracked": untracked,
    }


def finding_to_comment(f: dict[str, Any]) -> dict[str, Any]:
    sev = f.get("severity", "UNSPECIFIED")
    title = f.get("title", "Review finding")
    desc = f.get("description") or f.get("detail") or ""
    fix = f.get("fix")

    lines = [f"[{sev}] {title}"]
    if desc:
        lines.append("")
        lines.append(str(desc).strip())
    if fix:
        lines.append("")
        lines.append(f"Suggested fix: {fix}")

    return {
        "path": f.get("path"),
        "line": f.get("line"),
        "body": "\n".join(lines).strip(),
        "sourceFinding": f,
    }


def cmd_draft_comments(args: argparse.Namespace) -> dict[str, Any]:
    data = json.load(open(args.input, "r", encoding="utf-8"))
    findings: list[dict[str, Any]]
    if isinstance(data, dict) and "untracked" in data and args.only_untracked:
        findings = data["untracked"]
    elif isinstance(data, dict) and "findings" in data:
        findings = data["findings"]
    elif isinstance(data, list):
        findings = data
    else:
        findings = data.get("untracked", data.get("tracked", [])) if isinstance(data, dict) else []

    drafts = [finding_to_comment(f) for f in findings]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {"totalDrafts": len(drafts)},
        "drafts": drafts,
    }


def post_inline_comment(repo: RepoInfo, pr: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    endpoint = f"repos/{repo.owner}/{repo.name}/pulls/{pr['number']}/comments"
    cmd = [
        "gh",
        "api",
        endpoint,
        "-X",
        "POST",
        "-f",
        f"body={draft['body']}",
        "-f",
        f"commit_id={pr['headRefOid']}",
        "-f",
        f"path={draft['path']}",
        "-F",
        f"line={int(draft['line'])}",
        "-f",
        "side=RIGHT",
    ]
    return run_json(cmd)


def post_pr_comment(repo: RepoInfo, pr_number: int, body: str) -> None:
    run(["gh", "pr", "comment", str(pr_number), "--repo", f"{repo.owner}/{repo.name}", "--body", body])


def load_or_discover(args: argparse.Namespace) -> dict[str, Any]:
    if args.discover_json:
        return json.load(open(args.discover_json, "r", encoding="utf-8"))
    # Build a shallow args object for discover
    dargs = argparse.Namespace(remote=args.remote, branch=args.branch, pr=args.pr, state="all")
    return cmd_discover(dargs)


def cmd_publish_comments(args: argparse.Namespace) -> dict[str, Any]:
    if args.confirm != CONFIRM_POST:
        raise CommandError(
            "Publish action requires explicit confirmation token. "
            f"Re-run with --confirm {CONFIRM_POST}"
        )

    payload = load_or_discover(args)
    repo = RepoInfo(**payload["repo"])
    pr = payload["pr"]

    data = json.load(open(args.drafts, "r", encoding="utf-8"))
    drafts = data.get("drafts", data if isinstance(data, list) else [])

    posted_inline = []
    posted_summary = []
    fallback_for_summary: list[dict[str, Any]] = []

    for d in drafts:
        path = d.get("path")
        line = d.get("line")
        if path and line is not None:
            try:
                res = post_inline_comment(repo, pr, d)
                posted_inline.append(
                    {
                        "path": path,
                        "line": line,
                        "url": res.get("html_url"),
                        "id": res.get("id"),
                    }
                )
                continue
            except Exception as exc:  # noqa: BLE001
                fallback_for_summary.append({"draft": d, "reason": str(exc)})
        else:
            fallback_for_summary.append({"draft": d, "reason": "No path/line for inline comment."})

    if fallback_for_summary:
        lines = ["Posting remaining review notes as summary comments (inline unavailable):"]
        for item in fallback_for_summary:
            d = item["draft"]
            lines.append("\n---\n")
            if d.get("path"):
                lines.append(f"File: `{d.get('path')}` line `{d.get('line')}`")
            lines.append(d.get("body", ""))
        summary_body = "\n".join(lines).strip()
        post_pr_comment(repo, pr["number"], summary_body)
        posted_summary.append({"type": "pr_comment", "length": len(summary_body)})

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "pr": {"number": pr["number"], "url": pr["url"]},
        "summary": {
            "attempted": len(drafts),
            "postedInline": len(posted_inline),
            "postedSummary": len(posted_summary),
        },
        "postedInline": posted_inline,
        "postedSummary": posted_summary,
    }


def cmd_approve(args: argparse.Namespace) -> dict[str, Any]:
    if args.confirm != CONFIRM_APPROVE:
        raise CommandError(
            "Approve action requires explicit confirmation token. "
            f"Re-run with --confirm {CONFIRM_APPROVE}"
        )

    payload = load_or_discover(args)
    repo = payload["repo"]
    pr = payload["pr"]
    message = args.message or "Reviewed and approved."

    run(
        [
            "gh",
            "pr",
            "review",
            str(pr["number"]),
            "--repo",
            f"{repo['owner']}/{repo['name']}",
            "--approve",
            "--body",
            message,
        ]
    )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "approved": True,
        "pr": {"number": pr["number"], "url": pr["url"]},
        "message": message,
    }


def emit(data: dict[str, Any], output: str | None) -> None:
    rendered = json.dumps(data, indent=2, ensure_ascii=False)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
    print(rendered)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="PR helper for code-review skill")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--remote", default="origin", help="Git remote name (default: origin)")
        sp.add_argument("--branch", help="Branch name (default: current branch)")
        sp.add_argument("--pr", type=int, help="PR number override")
        sp.add_argument("--output", help="Write JSON output to file")

    # discover
    sp = sub.add_parser("discover", help="Discover PR and unresolved threads")
    add_common(sp)
    sp.add_argument("--state", default="all", choices=["all", "open", "closed"], help="PR list state")

    # triage
    sp = sub.add_parser("triage", help="Advisory triage of unresolved threads")
    add_common(sp)
    sp.add_argument("--discover-json", help="Use existing discover JSON input")

    # dedupe
    sp = sub.add_parser("dedupe", help="Deduplicate findings against unresolved threads")
    add_common(sp)
    sp.add_argument("--discover-json", help="Use existing discover JSON input")
    sp.add_argument("--findings", required=True, help="Findings JSON file")
    sp.add_argument("--line-tolerance", type=int, default=3)
    sp.add_argument("--keyword-overlap", type=int, default=2)

    # draft-comments
    sp = sub.add_parser("draft-comments", help="Generate comment drafts from findings JSON")
    sp.add_argument("--input", required=True, help="Findings or dedupe JSON input")
    sp.add_argument("--only-untracked", action="store_true", help="Use dedupe.untracked only")
    sp.add_argument("--output", help="Write JSON output to file")

    # publish-comments
    sp = sub.add_parser("publish-comments", help="Publish drafts to PR (explicit consent required)")
    add_common(sp)
    sp.add_argument("--discover-json", help="Use existing discover JSON input")
    sp.add_argument("--drafts", required=True, help="Draft comments JSON (from draft-comments)")
    sp.add_argument("--confirm", required=True, help=f"Required token: {CONFIRM_POST}")

    # approve
    sp = sub.add_parser("approve", help="Approve PR (explicit consent required)")
    add_common(sp)
    sp.add_argument("--discover-json", help="Use existing discover JSON input")
    sp.add_argument("--message", help="Approval message")
    sp.add_argument("--confirm", required=True, help=f"Required token: {CONFIRM_APPROVE}")

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "discover":
            out = cmd_discover(args)
        elif args.command == "triage":
            out = cmd_triage(args)
        elif args.command == "dedupe":
            out = cmd_dedupe(args)
        elif args.command == "draft-comments":
            out = cmd_draft_comments(args)
        elif args.command == "publish-comments":
            out = cmd_publish_comments(args)
        elif args.command == "approve":
            out = cmd_approve(args)
        else:
            parser.error(f"Unknown command: {args.command}")
            return 2
    except CommandError as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    emit(out, getattr(args, "output", None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
