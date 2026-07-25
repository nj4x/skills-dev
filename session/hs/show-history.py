#!/usr/bin/env python3
"""Paginated prompt history for the current Claude Code project."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

PAGE_SIZE = 10
PREVIEW_CHARS = 300
SKIP_PREFIXES = ("<", "This session is being continued")
STATE_DIR = Path.home() / ".claude" / "hs-state"


def get_project_dir(cwd: str) -> Path | None:
    encoded = cwd.replace("/", "-")
    d = Path.home() / ".claude" / "projects" / encoded
    return d if d.exists() else None


def project_key(cwd: str) -> str:
    return cwd.replace("/", "-").strip("-")


def load_state(key: str) -> dict:
    f = STATE_DIR / f"{key}.json"
    try:
        return json.loads(f.read_text())
    except Exception:
        return {}


def save_state(key: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / f"{key}.json").write_text(json.dumps(state))


def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
        )
    return ""


def is_real_prompt(obj: dict, text: str) -> bool:
    if obj.get("isMeta") or obj.get("isSidechain"):
        return False
    s = text.strip()
    if not s:
        return False
    return not any(s.startswith(pfx) for pfx in SKIP_PREFIXES)


def fmt_ts(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts[:16] if len(ts) >= 16 else ts


def load_prompts(project_dir: Path) -> list:
    prompts = []
    for f in sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime):
        try:
            with open(f, encoding="utf-8", errors="replace") as fp:
                for raw in fp:
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") != "user":
                        continue
                    text = extract_text(obj.get("message", {}).get("content", ""))
                    if is_real_prompt(obj, text):
                        prompts.append((obj.get("timestamp", ""), text.strip()))
        except OSError:
            continue
    prompts.sort(key=lambda x: x[0])
    return prompts


def show_page(prompts: list, end_idx: int) -> int:
    """Show PAGE_SIZE prompts ending at end_idx (exclusive). Returns new end_idx."""
    total = len(prompts)
    start_idx = max(0, end_idx - PAGE_SIZE)
    page = prompts[start_idx:end_idx]

    more_available = start_idx > 0
    footer = "  /hs more for older" if more_available else ""
    print(f"Prompts {start_idx + 1}–{end_idx} of {total}{footer}\n")

    for global_i, (ts, text) in enumerate(page, start_idx + 1):
        if len(text) > PREVIEW_CHARS:
            preview = text[:PREVIEW_CHARS].rstrip() + f"\n     … [{len(text)} chars — /hs {global_i} to expand]"
        else:
            preview = text
        indented = ("\n     ").join(preview.split("\n"))
        print(f"{global_i:>3}. [{fmt_ts(ts)}]  {indented}")
        print()

    return start_idx  # next page ends here


def main():
    arg = sys.argv[1].strip() if len(sys.argv) > 1 else ""

    cwd = os.getcwd()
    project_dir = get_project_dir(cwd)
    if not project_dir:
        sys.exit(f"No Claude project found for: {cwd}")

    key = project_key(cwd)
    prompts = load_prompts(project_dir)
    total = len(prompts)

    if not arg:
        # Fresh start: latest 10
        end_idx = total
        new_end = show_page(prompts, end_idx)
        save_state(key, {"end_idx": new_end})

    elif arg == "more":
        state = load_state(key)
        end_idx = state.get("end_idx", total)
        if end_idx <= 0:
            print(f"Beginning of history reached ({total} prompts total).")
            return
        new_end = show_page(prompts, end_idx)
        save_state(key, {"end_idx": new_end})

    else:
        try:
            idx = int(arg)
        except ValueError:
            sys.exit(f"Unknown argument: {arg!r}. Use /hs, /hs more, or /hs <number>.")

        if idx < 1 or idx > total:
            sys.exit(f"Prompt #{idx} out of range (1–{total}).")

        ts, text = prompts[idx - 1]
        print(f"Prompt #{idx} of {total}  [{fmt_ts(ts)}]  ({len(text)} chars)\n")
        print(text)
        print()


if __name__ == "__main__":
    main()
