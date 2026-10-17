"""Step 9 parametrize edit: apply `simplification-plan.json` parametrizations, one file write each.

Usage:
  python apply_param.py --root <project> [--plan .scratch/refactor-tests/simplification-plan.json] \
      [--ledger .scratch/refactor-tests/ledger.json] [--index <n> …]

Relative paths resolve against `--root`. Without `--index`, every `parametrizations`
entry runs, in plan order. Prints one JSON object per entry, as a list:
`{ index, file, consolidated_name, status, reason }`, where `status` is one of:

- `applied`: in a single file write, the N original test functions (decorators
  included, with the blank lines after each) are deleted, `consolidated_body` is
  inserted at the first original's position, re-indented to its scope, and each
  `required_imports` module missing a top-level `import <name>` is imported.
  The ledger entry `{ file, replaced, consolidated_name }` is written right after.
- `recorded`: the ledger already holds this `file` and `consolidated_name` (applied
  or `skipped`): nothing is edited (Step 9 → Resume).
- `already-applied`: not in the ledger, but the file holds `consolidated_name` and none
  of `tests`: the write happened before the run stopped. The entry is recorded with
  `replaced` set to `tests`, and nothing is edited.
- `skipped`: the file does not parse, an original is missing, `consolidated_name` is
  already defined in the scope, or the edited text does not parse or lacks the
  consolidated test. The file is left unchanged, and the ledger
  records `{ file, tests, consolidated_name, skipped: "<error>" }`.

Test names follow the plan: `Class::test` for a method, the bare name for a top-level
test. The ledger is rewritten atomically after every entry. An edited file keeps its
line ends (LF or CRLF) and permission bits.
"""
import argparse
import ast
import json
import os
import shutil
import sys
import textwrap
from pathlib import Path

from refactor_tests_shared import write_atomic

PLAN = ".scratch/refactor-tests/simplification-plan.json"
LEDGER = ".scratch/refactor-tests/ledger.json"


class EditError(Exception):
    pass


def _split(name):
    cls, _, base = name.rpartition("::")
    return cls or None, base


def _scope(tree, cls):
    if cls is None:
        return tree.body
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            return node.body
    return None


def _functions(scope):
    return {n.name: n for n in scope or [] if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _state(text, entry):
    """(consolidated present, originals present) in `text`; None when it does not parse."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    cls, name = _split(entry["consolidated_name"])
    have = _functions(_scope(tree, cls))
    originals = [t for t in entry["tests"] if _split(t)[1] in _functions(_scope(tree, _split(t)[0]))]
    return name in have, originals


def _add_imports(text, modules):
    tree = ast.parse(text)
    present = {a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names if a.asname is None}
    missing = [m for m in modules if m not in present]
    if not missing:
        return text
    lines = text.splitlines(keepends=True)
    at = 0
    for i, node in enumerate(tree.body):
        is_doc = i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
            and isinstance(node.value.value, str)
        if is_doc or isinstance(node, (ast.Import, ast.ImportFrom)):
            at = node.end_lineno
        else:
            break
    block = "".join(f"import {m}\n" for m in missing)
    if at and lines and not lines[at - 1].endswith("\n"):
        lines[at - 1] += "\n"
    return "".join(lines[:at]) + block + "".join(lines[at:])


def edit(text, entry):
    """The file text with one parametrization applied. Raises EditError."""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise EditError(f"file does not parse: {exc}") from exc
    lines = text.splitlines(keepends=True)
    cls, name = _split(entry["consolidated_name"])
    if name in _functions(_scope(tree, cls)) and name not in {
            _split(t)[1] for t in entry["tests"] if _split(t)[0] == cls}:
        raise EditError(f"{entry['consolidated_name']} is already defined; the edit would shadow it")
    ranges = []
    for t in entry["tests"]:
        cls, name = _split(t)
        fn = _functions(_scope(tree, cls)).get(name)
        if fn is None:
            raise EditError(f"test function {t} not found")
        start = min([fn.lineno] + [d.lineno for d in fn.decorator_list]) - 1
        end = fn.end_lineno
        while end < len(lines) and lines[end].strip() == "":
            end += 1
        ranges.append((start, end, fn.col_offset))
    ranges.sort()
    for (_, e1, _), (s2, _, _) in zip(ranges, ranges[1:]):
        if s2 < e1:
            raise EditError("original test functions overlap")
    indent = " " * ranges[0][2]
    body = textwrap.dedent(entry["consolidated_body"]).strip("\n")
    body = textwrap.indent(body, indent) + "\n"
    gap = "\n" if cls else "\n\n"
    out, i = [], 0
    for n, (start, end, _) in enumerate(ranges):
        out.extend(lines[i:start])
        if n == 0:
            out.append(body + (gap if end < len(lines) else ""))
        i = end
    out.extend(lines[i:])
    new_text = "".join(out)
    try:
        new_text = _add_imports(new_text, entry.get("required_imports") or [])
    except SyntaxError as exc:
        raise EditError(f"edited text does not parse: {exc}") from exc
    state = _state(new_text, entry)
    if state is None:
        raise EditError("edited text does not parse")
    present, originals = state
    if not present:
        raise EditError(f"edited text lacks {entry['consolidated_name']}")
    if originals:
        raise EditError(f"edited text still holds {', '.join(originals)}")
    return new_text


def _read_text(path):
    """(text with LF line ends, original line end)."""
    with open(path, encoding="utf-8", newline="") as f:
        raw = f.read()
    return raw.replace("\r\n", "\n"), "\r\n" if "\r\n" in raw else "\n"


def _write_text(path, text, newline="\n"):
    """Atomic write that keeps the file's line ends and permission bits."""
    tmp = f"{path}.rt-tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\n", newline) if newline != "\n" else text)
    shutil.copymode(path, tmp)
    os.replace(tmp, path)


def apply_entry(root, entry, ledger):
    """(status, reason). Mutates `ledger`; the caller writes it."""
    done = ledger.setdefault("simplification", {}).setdefault("parametrizations", [])
    if any(d.get("file") == entry["file"] and d.get("consolidated_name") == entry["consolidated_name"]
           for d in done):
        return "recorded", None
    path = root / entry["file"]
    record = {"file": entry["file"], "consolidated_name": entry["consolidated_name"]}
    try:
        text, newline = _read_text(path)
    except (OSError, UnicodeDecodeError) as exc:
        done.append({**record, "tests": entry["tests"], "skipped": f"cannot read file: {exc}"})
        return "skipped", done[-1]["skipped"]
    state = _state(text, entry)
    if state is not None and state[0] and not state[1]:
        done.append({**record, "replaced": entry["tests"]})
        return "already-applied", None
    try:
        new_text = edit(text, entry)
    except EditError as exc:
        done.append({**record, "tests": entry["tests"], "skipped": str(exc)})
        return "skipped", str(exc)
    _write_text(path, new_text, newline)
    done.append({**record, "replaced": entry["tests"]})
    return "applied", None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--plan", default=PLAN)
    ap.add_argument("--ledger", default=LEDGER)
    ap.add_argument("--index", type=int, action="append", help="plan entry to apply; repeat the flag")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    plan = json.loads((root / args.plan).read_text())
    ledger_path = root / args.ledger
    ledger = json.loads(ledger_path.read_text())
    entries = plan.get("parametrizations") or []
    indexes = args.index if args.index is not None else range(len(entries))
    results = []
    for i in indexes:
        entry = entries[i]
        status, reason = apply_entry(root, entry, ledger)
        if status != "recorded":
            write_atomic(ledger_path, ledger)
        results.append({"index": i, "file": entry["file"], "consolidated_name": entry["consolidated_name"],
                        "status": status, "reason": reason})
    json.dump(results, sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
