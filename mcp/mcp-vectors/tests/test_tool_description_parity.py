"""
Tests that enforce consistency between MCP tool descriptions in server.py
and the pre-conditions in the project CLAUDE.md.

All assertions use static file reads only — no server startup, no network
calls, no mock setup.

Four assertions:

1. test_targeted_tools_present_in_claude_md
   The named tool (search_root) appears somewhere in CLAUDE.md (presence check).

2. test_no_orphaned_tool_names_in_claude_md
   Every backtick-quoted snake_case identifier in the Pre-conditions section
   is a real tool defined in server.py.  Catches stale entries after a tool
   is renamed or removed.

3. test_server_descriptions_have_not_for_use_pattern
   Each targeted tool's server.py docstring contains "Not for" (case-insensitive)
   and "use", confirming the "Not for X — use Y" contrast is present.

4. test_claude_md_preconditions_have_not_for_use_pattern
   The CLAUDE.md pre-condition line for each targeted tool also contains
   "not for" (case-insensitive) and "use", mirroring the server.py contract.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (resolved relative to this test file, which lives in tests/)
# ---------------------------------------------------------------------------

# tests/ -> mcp-vectors/
SERVER_PY = Path(__file__).resolve().parents[1] / "server.py"

# tests/ -> mcp-vectors/ -> mcp/ -> skills-dev/
CLAUDE_MD = Path(__file__).resolve().parents[3] / "CLAUDE.md"

# The four tools that must be documented in CLAUDE.md and must carry the
# "Not for … use …" contrast in both server.py and CLAUDE.md.
TARGETED_TOOLS = frozenset({"search_root"})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_server_tools() -> dict[str, str]:
    """Return {tool_name: docstring} for every @_tool()-decorated function in server.py.

    Uses ast.parse() so no module-level I/O is triggered (server.py sets up
    logging, signal handlers, and atexit hooks on import).
    """
    source = SERVER_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)

    tools: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for dec in node.decorator_list:
            # Match @_tool()  — a Call node whose func is Name("_tool")
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Name)
                and dec.func.id == "_tool"
            ):
                tools[node.name] = ast.get_docstring(node) or ""
                break

    return tools


def _read_claude_md() -> str:
    return CLAUDE_MD.read_text(encoding="utf-8")


def _extract_preconditions_section(content: str) -> str:
    """Return the text block under the '## Pre-conditions' heading."""
    match = re.search(
        r"^## Pre-conditions.*?(?=^## |\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(0) if match else ""


# ---------------------------------------------------------------------------
# Test 1 — targeted tools present in CLAUDE.md
# ---------------------------------------------------------------------------


def test_targeted_tools_present_in_claude_md() -> None:
    """Assertion 1: All targeted tools appear by name in the project CLAUDE.md."""
    content = _read_claude_md()
    missing = [t for t in sorted(TARGETED_TOOLS) if t not in content]
    assert not missing, (
        f"These targeted tools are absent from CLAUDE.md — "
        f"each must have a pre-condition entry: {missing}"
    )


# ---------------------------------------------------------------------------
# Test 2 — no orphaned entries
# ---------------------------------------------------------------------------


def test_no_orphaned_tool_names_in_claude_md() -> None:
    """Assertion 2: Every backtick-quoted tool name in Pre-conditions is a real server.py tool.

    Scans backtick-delimited snake_case identifiers (no path separators or
    spaces) in the Pre-conditions section and cross-checks against the set of
    @_tool()-decorated functions in server.py.
    """
    server_tools = _parse_server_tools()
    content = _read_claude_md()
    preconditions = _extract_preconditions_section(content)

    assert preconditions, (
        "No '## Pre-conditions' section found in CLAUDE.md — "
        "add the section or correct the heading text."
    )

    # Backtick-quoted identifiers that look like tool function names:
    # contain an underscore, no path separators, no spaces.
    backtick_items = re.findall(r"`([^`]+)`", preconditions)
    tool_references = {
        item
        for item in backtick_items
        if "_" in item and "/" not in item and "." not in item and " " not in item
    }

    orphans = tool_references - set(server_tools.keys())
    assert not orphans, (
        f"These backtick-quoted identifiers in the CLAUDE.md Pre-conditions section "
        f"are not defined as tools in server.py: {sorted(orphans)}. "
        f"Remove the stale entry from CLAUDE.md or add the missing tool to server.py."
    )


# ---------------------------------------------------------------------------
# Test 3 — server.py descriptions have "Not for … use …"
# ---------------------------------------------------------------------------


def test_server_descriptions_have_not_for_use_pattern() -> None:
    """Assertion 3: Each targeted tool's server.py docstring has 'Not for' and 'use'."""
    server_tools = _parse_server_tools()

    absent = TARGETED_TOOLS - set(server_tools.keys())
    assert not absent, (
        f"These targeted tools are not defined in server.py at all: {sorted(absent)}"
    )

    failures: list[str] = []
    for tool in sorted(TARGETED_TOOLS):
        desc_lower = server_tools[tool].lower()
        missing: list[str] = []
        if "not for" not in desc_lower:
            missing.append('"not for"')
        if "use" not in desc_lower:
            missing.append('"use"')
        if missing:
            failures.append(
                f"  {tool!r}: docstring is missing {' and '.join(missing)}"
            )

    assert not failures, (
        "These server.py tool descriptions are missing the 'Not for … use …' contrast:\n"
        + "\n".join(failures)
    )


# ---------------------------------------------------------------------------
# Test 4 — CLAUDE.md pre-conditions have "Not for … use …"
# ---------------------------------------------------------------------------


def test_claude_md_preconditions_have_not_for_use_pattern() -> None:
    """Assertion 4: Each targeted tool's CLAUDE.md pre-condition entry has 'not for' and 'use'."""
    content = _read_claude_md()
    preconditions = _extract_preconditions_section(content)

    assert preconditions, (
        "No '## Pre-conditions' section found in CLAUDE.md — "
        "add the section or correct the heading text."
    )

    failures: list[str] = []
    for tool in sorted(TARGETED_TOOLS):
        # Collect every line in the pre-conditions section that mentions the tool
        # by its backtick-quoted name (e.g. `search_global`).
        tool_lines = [
            line
            for line in preconditions.splitlines()
            if f"`{tool}`" in line
        ]
        if not tool_lines:
            failures.append(
                f"  {tool!r}: no pre-condition entry (line containing `{tool}`) "
                f"found in CLAUDE.md Pre-conditions section"
            )
            continue

        entry_text = " ".join(tool_lines).lower()
        missing: list[str] = []
        if "not for" not in entry_text:
            missing.append('"not for"')
        if "use" not in entry_text:
            missing.append('"use"')
        if missing:
            failures.append(
                f"  {tool!r}: CLAUDE.md pre-condition entry is missing "
                f"{' and '.join(missing)}"
            )

    assert not failures, (
        "These CLAUDE.md pre-condition entries are missing the 'Not for … use …' pattern:\n"
        + "\n".join(failures)
    )
