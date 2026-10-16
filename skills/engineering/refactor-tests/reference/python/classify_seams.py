"""Propose Python seams and classify tests against them (static, from the AST).

Usage:
  python classify_seams.py propose --root PROJECT --source-root src [--source-root ...]
  python classify_seams.py classify --root PROJECT --source-root src \
      --seams seams.json --tests tests [--tests ...] [--evidence test-evidence.json]

`propose` prints {"modules": {<source file>: {"seams": [{name, signal, status}]}},
"warnings": [...]} with status `proposed`. Signals, strongest first: `__all__`;
`cross-package-import` (a public name imported by a file in another package of the
project); `public-api` (only when the module has no `__all__`: public top-level
functions and classes, and the public methods of those classes, as `Class.method`).
Underscore names are never proposed. `__all__` built from literal lists with `+`, `+=`,
`.extend` or `.append` is evaluated; a computed part (`+ other.__all__`) keeps the
literal names, still counts as an `__all__` (no `public-api`), and adds a warning.
Any other change to `__all__` (`.remove`, `.insert` and other list mutators, `del
__all__[...]`, `__all__[:] = ...`, or an assignment or mutation nested in `if`/`try`/
a function) is treated the same way.

`classify` reads a seams file (the `propose` shape, edited by the user) and uses the
seams whose status is `confirmed`. It prints {"seams": {modules, add_candidates,
pinning_candidates}, "interface_tests": [...], "warnings": [...]}. Per test and per
source module: the test is an interface test when every name it references from that
module is a seam, and a pinning candidate when it references at least one non-seam
name. Referenced names come from imports, calls, attribute access on imported modules
and classes, `patch(...)` and `monkeypatch.setattr(...)` string targets, and the
object forms `patch.object(mod, "name")` and `monkeypatch.setattr(mod, "name", value)`.
Coverage plays no part in that split.

With --evidence at status `ok`, add_candidates (confirmed seams with no interface test
whose `covered` lines reach the seam's body) and `covered_through_interface` are
computed. Otherwise both are omitted and a warning says so. When a package `__init__`
re-exports an add candidate (`from .mod import name`, followed through every package
level, e.g. `pkg/sub/__init__.py` re-exported again by `pkg/__init__.py`) and a test
references it through that package, the test is linked to the `__init__`, not to the source module: a
warning names the candidate so it is checked by hand.
"""
import argparse
import ast
import json
import sys
from pathlib import Path

NOTE_COVERED = "covered through the interface"
NOTE_MOVE = "move the assertion to the interface"


def _is_dunder(name):
    return name.startswith("__") and name.endswith("__")


def _public(name):
    return not name.startswith("_")


def _skip_dir(parts):
    return any(p in {"vendor", "node_modules", ".venv", "build", ".scratch", ".reference-projects", "__pycache__"} for p in parts)


def _is_test_file(path):
    return path.name.startswith("test_") or path.name.endswith("_test.py") or path.name == "conftest.py"


def dotted_name(root, source_roots, path):
    """Dotted module name of a source file, relative to its source root; None if outside every root."""
    rel = path.relative_to(root)
    for sr in source_roots:
        base = Path(sr)
        try:
            sub = rel.relative_to(base)
        except ValueError:
            continue
        parts = list(sub.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else None
    return None


def source_files(root, source_roots):
    """Map dotted module name -> (relative posix path, is_package) for non-test source files."""
    found = {}
    for sr in source_roots:
        for path in sorted((root / sr).rglob("*.py")):
            rel = path.relative_to(root)
            if _skip_dir(rel.parts) or _is_test_file(path):
                continue
            name = dotted_name(root, source_roots, path)
            if name:
                found[name] = (rel.as_posix(), path.name == "__init__.py")
    return found


def _parse(path):
    try:
        return ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError, ValueError, OSError):
        return None


def _literal_names(node):
    """(names, complete) for a list/tuple literal or a `+` chain of them.

    `complete` is False when some part is not a literal of strings (e.g. `x.__all__`).
    """
    if isinstance(node, (ast.List, ast.Tuple)):
        names = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        return names, len(names) == len(node.elts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, lok = _literal_names(node.left)
        right, rok = _literal_names(node.right)
        return left + right, lok and rok
    return [], False


def _is_all(target):
    return isinstance(target, ast.Name) and target.id == "__all__"


_LIST_MUTATORS = {
    "append", "extend", "insert", "remove", "pop", "clear", "sort", "reverse",
    "__setitem__", "__delitem__", "__iadd__", "__imul__",
}


def _mutates_all(node):
    """True when `node` binds, deletes, or changes `__all__` in place."""
    if isinstance(node, ast.Name) and node.id == "__all__":
        return isinstance(node.ctx, (ast.Store, ast.Del))
    if isinstance(node, ast.Subscript) and _is_all(node.value):
        return isinstance(node.ctx, (ast.Store, ast.Del))
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and _is_all(node.func.value)
        and node.func.attr in _LIST_MUTATORS
    )


_OWN_SCOPE = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _module_scope_walk(node):
    """Like `ast.walk`, but skip function, lambda and class bodies and value-less annotations."""
    todo = [node]
    while todo:
        n = todo.pop()
        if isinstance(n, _OWN_SCOPE) or (isinstance(n, ast.AnnAssign) and n.value is None):
            continue
        yield n
        todo.extend(ast.iter_child_nodes(n))


def _all_names(tree):
    """(names, complete) for the module's top-level `__all__`; (None, True) when it has none.

    Top-level assignments, `+=`, and `__all__.extend/append(...)` of literals are evaluated
    in order. Any other change to `__all__` at module scope (a top-level statement, or one
    nested in a module-level if/try/for/while/with) makes the result incomplete (and means an
    `__all__` exists): the literal names found so far are kept. Function, lambda and class
    bodies have their own scope and are not read; a value-less `__all__: list[str]` binds
    nothing and is ignored.
    """
    names, complete = None, True
    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign) and any(_is_all(t) for t in node.targets):
            names, value = [], node.value
        elif isinstance(node, ast.AnnAssign) and _is_all(node.target) and node.value is not None:
            names, value = [], node.value
        elif isinstance(node, ast.AugAssign) and _is_all(node.target):
            if not isinstance(node.op, ast.Add):
                names, complete = names or [], False
                continue
            value = node.value
        elif (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and _is_all(node.value.func.value)
            and node.value.func.attr in ("extend", "append")
            and len(node.value.args) == 1
        ):
            arg = node.value.args[0]
            value = ast.List(elts=[arg], ctx=ast.Load()) if node.value.func.attr == "append" else arg
        else:
            # Any other change (remove, insert, del, slice assignment, or one nested in a
            # module-level if/try) cannot be evaluated: never pass it silently.
            if any(_mutates_all(n) for n in _module_scope_walk(node)):
                names, complete = names or [], False
            continue
        if names is None:
            names = []
        more, ok = _literal_names(value)
        names += more
        complete = complete and ok
    return names, complete


def _public_api(tree):
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _public(node.name):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef) and _public(node.name):
            names.append(node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and _public(item.name):
                    names.append(f"{node.name}.{item.name}")
    return names


def _defined_top_level(tree):
    return {
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def _resolve_from(importer, importer_is_pkg, level, module):
    """Absolute dotted module for `from <.*module> import ...` seen in `importer`."""
    if level == 0:
        return module
    pkg = importer.split(".") if importer_is_pkg else importer.split(".")[:-1]
    if level - 1 >= len(pkg):  # climbs past the top-level package: not a project module
        return None
    pkg = pkg[: len(pkg) - (level - 1)]
    return ".".join(pkg + ([module] if module else []))


def _package_of(name, is_pkg):
    return name if is_pkg else name.rpartition(".")[0]


def cross_package_imports(trees, files):
    """module -> set of public names imported from it by a file in another package."""
    imported = {}
    for importer, tree in trees.items():
        _, importer_is_pkg = files[importer]
        importer_pkg = _package_of(importer, importer_is_pkg)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            target = _resolve_from(importer, importer_is_pkg, node.level, node.module)
            if target not in files:
                continue
            target_pkg = _package_of(target, files[target][1])
            if target_pkg == importer_pkg:
                continue
            for alias in node.names:
                if _public(alias.name):
                    imported.setdefault(target, set()).add(alias.name)
    return imported


def propose(root, source_roots):
    files = source_files(root, source_roots)
    trees = {}
    for name, (rel, _) in files.items():
        tree = _parse(root / rel)
        if tree is not None:
            trees[name] = tree
    imported = cross_package_imports(trees, files)
    modules = {}
    warnings = []
    for name, tree in sorted(trees.items()):
        rel = files[name][0]
        proposals = {}
        declared, complete = _all_names(tree)
        if not complete:
            warnings.append(
                f"{rel}: __all__ is computed or mutated, not a literal list; only its literal names are "
                "proposed under __all__ and public-api is not used"
            )
        for n in declared or []:
            if _public(n):
                proposals.setdefault(n, "__all__")
        defined = _defined_top_level(tree)
        for n in sorted(imported.get(name, ())):
            if n in defined:
                proposals.setdefault(n, "cross-package-import")
        if declared is None:
            for n in _public_api(tree):
                proposals.setdefault(n, "public-api")
        if proposals:
            modules[rel] = {
                "seams": [{"name": n, "signal": s, "status": "proposed"} for n, s in proposals.items()]
            }
    return {"modules": modules, "warnings": warnings}


def _seam_ok(rest, seam_names):
    """True when `rest` (dotted name inside a module) belongs to the seam surface."""
    if rest in seam_names:
        return True
    head, _, tail = rest.partition(".")
    if head not in seam_names:
        return False
    return all(_public(p) or _is_dunder(p) for p in tail.split(".")) if tail else True


class _TestRefs(ast.NodeVisitor):
    """Collect (module, rest) project references inside one test function."""

    def __init__(self, aliases, modules):
        self.aliases = dict(aliases)  # local name -> (module, rest or "")
        self.modules = modules
        self.refs = set()

    def _add(self, dotted):
        # longest project-module prefix, remainder = name inside it
        parts = dotted.split(".")
        for i in range(len(parts), 0, -1):
            mod = ".".join(parts[:i])
            if mod in self.modules:
                rest = ".".join(parts[i : i + 2])
                if rest:
                    self.refs.add((mod, rest))
                return

    def _alias_chain(self, node):
        chain = []
        while isinstance(node, ast.Attribute):
            chain.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name) and node.id in self.aliases:
            mod, rest = self.aliases[node.id]
            base = ".".join(p for p in (mod, rest) if p)
            return ".".join([base] + list(reversed(chain)))
        return None

    def visit_Import(self, node):
        _bind_imports(node, self.aliases)

    def visit_ImportFrom(self, node):
        _bind_imports(node, self.aliases)

    def visit_Attribute(self, node):
        dotted = self._alias_chain(node)
        if dotted:
            self._add(dotted)
            return  # whole chain handled
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and node.id in self.aliases:
            mod, rest = self.aliases[node.id]
            if rest:
                self._add(f"{mod}.{rest}")

    def visit_Call(self, node):
        func = node.func
        target = None
        if isinstance(func, ast.Attribute) and func.attr == "object" and _is_patch(func.value):
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                base = self._expr_dotted(node.args[0])
                if base:
                    target = f"{base}.{node.args[1].value}"
        elif _is_patch(func) or (isinstance(func, ast.Attribute) and func.attr == "setattr"):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                target = node.args[0].value
            elif (
                not _is_patch(func)
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                # object form: monkeypatch.setattr(mod, "name", value)
                base = self._expr_dotted(node.args[0])
                if base:
                    target = f"{base}.{node.args[1].value}"
        if target:
            self._add(target)
        self.generic_visit(node)

    def _expr_dotted(self, node):
        if isinstance(node, ast.Name) and node.id in self.aliases:
            mod, rest = self.aliases[node.id]
            return ".".join(p for p in (mod, rest) if p)
        if isinstance(node, ast.Attribute):
            return self._alias_chain(node)
        return None


def _is_patch(node):
    return (isinstance(node, ast.Name) and node.id == "patch") or (
        isinstance(node, ast.Attribute) and node.attr == "patch"
    )


def _bind_imports(node, aliases):
    if isinstance(node, ast.Import):
        for a in node.names:
            if a.asname:
                aliases[a.asname] = (a.name, "")
            else:
                top = a.name.split(".")[0]
                aliases[top] = (top, "")
    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        for a in node.names:
            aliases[a.asname or a.name] = (node.module, a.name)


def _test_functions(tree):
    """Yield (test name, function node, decorators) for top-level tests and tests in Test* classes.

    The decorators are the function's own plus its class's: `@patch(...)` there is a reference too.
    """
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            yield node.name, node, node.decorator_list
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test"):
                    yield f"{node.name}::{item.name}", item, node.decorator_list + item.decorator_list


def _body_lines(tree, seam_name):
    """Lines of the seam's body statements (header and decorators excluded)."""
    head, _, tail = seam_name.partition(".")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == head:
            if tail:
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == tail:
                        return set(range(item.body[0].lineno, item.end_lineno + 1))
                return set()
            return set(range(node.body[0].lineno, node.end_lineno + 1))
    return set()


def _package_reexports(root, files):
    """(source module, name) -> {(package, exported name)} for `from ... import` in package `__init__`s.

    Chains are followed through every package level: when `pkg/sub/__init__.py` re-exports
    `name` from `.mod` and `pkg/__init__.py` re-exports it from `.sub`, `(pkg.sub.mod, name)`
    maps to both `(pkg.sub, name)` and `(pkg, name)`.
    """
    direct = {}
    for pkg, (rel, is_pkg) in files.items():
        if not is_pkg:
            continue
        tree = _parse(root / rel)
        if tree is None:
            continue
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            target = _resolve_from(pkg, True, node.level, node.module)
            if target not in files or target == pkg:
                continue
            for a in node.names:
                if a.name != "*":
                    direct.setdefault((target, a.name), set()).add((pkg, a.asname or a.name))
    found = {}
    for key, first in direct.items():
        seen, todo = set(), list(first)
        while todo:
            hop = todo.pop()
            if hop in seen:
                continue  # a cycle of re-exports ends here
            seen.add(hop)
            todo.extend(direct.get(hop, ()))
        found[key] = seen
    return found


def _evidence_lines(evidence, file_id, rel_src):
    """Covered line set of `rel_src` over all evidence ids of one test (parametrized ids merged)."""
    lines = set()
    for tid, entry in evidence["tests"].items():
        if tid == file_id or tid.startswith(file_id + "["):
            lines |= set(entry.get("covered", {}).get(rel_src, {}).get("lines", []))
    return lines


def classify(root, source_roots, seams_doc, test_paths, evidence=None):
    files = source_files(root, source_roots)
    rel_to_mod = {rel: name for name, (rel, _) in files.items()}
    seam_sets = {}
    for rel, entry in seams_doc.get("modules", {}).items():
        names = {s["name"] for s in entry["seams"] if s.get("status") == "confirmed"}
        if names and rel in rel_to_mod:
            seam_sets[rel_to_mod[rel]] = names
    warnings = []
    if not seam_sets:
        warnings.append("no confirmed seams: no test classified")
    evidence_ok = bool(evidence) and evidence.get("status") == "ok"
    if not evidence_ok:
        warnings.append(
            "evidence status is not ok: add_candidates and covered_through_interface omitted"
        )

    interface, pinning_raw = [], []
    all_refs = set()
    for tpath in sorted(test_paths):
        tree = _parse(root / tpath)
        if tree is None:
            warnings.append(f"{tpath}: cannot parse, skipped")
            continue
        module_aliases = {}
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                _bind_imports(node, module_aliases)
        for tname, fn, decorators in _test_functions(tree):
            visitor = _TestRefs(module_aliases, files)
            for stmt in [*decorators, *fn.body]:
                visitor.visit(stmt)
            all_refs |= visitor.refs
            by_module = {}
            for mod, rest in visitor.refs:
                by_module.setdefault(mod, set()).add(rest)
            for mod, rests in sorted(by_module.items()):
                if mod not in seam_sets:
                    continue
                internals = sorted(r for r in rests if not _seam_ok(r, seam_sets[mod]))
                rec = {"file": tpath, "test_name": tname, "module": files[mod][0]}
                if internals:
                    pinning_raw.append({**rec, "internals": internals})
                else:
                    interface.append(rec)

    modules_out = {}
    for rel, entry in seams_doc.get("modules", {}).items():
        confirmed = [s for s in entry["seams"] if s.get("status") == "confirmed"]
        if confirmed:
            modules_out[rel] = {"seams": confirmed}
    out = {"modules": modules_out}

    def test_id(rec):
        return f"{rec['file']}::{rec['test_name']}"

    if evidence_ok:
        add = []
        for rel, entry in modules_out.items():
            tree = _parse(root / rel)
            if tree is None:
                warnings.append(f"{rel}: cannot parse, add candidates skipped")
                continue
            tests_here = [r for r in interface if r["module"] == rel]
            for seam in entry["seams"]:
                lines = _body_lines(tree, seam["name"])
                if not lines:
                    warnings.append(
                        f"{rel}: seam {seam['name']} has no function or class body here "
                        "(re-export or constant): not an add candidate"
                    )
                    continue
                reached = any(lines & _evidence_lines(evidence, test_id(r), rel) for r in tests_here)
                if not reached:
                    add.append({"module": rel, "seam": seam["name"]})
        reexports = _package_reexports(root, files)
        for cand in add:
            head = cand["seam"].partition(".")[0]
            for pkg, exported in sorted(reexports.get((rel_to_mod[cand["module"]], head), ())):
                if any(m == pkg and r.partition(".")[0] == exported for m, r in all_refs):
                    warnings.append(
                        f"{cand['module']}: add candidate {cand['seam']} is re-exported by {files[pkg][0]} "
                        f"as {exported}, and tests import it from there; those tests are not linked to "
                        f"{cand['module']}, so check the candidate by hand"
                    )
        out["add_candidates"] = add
    pinning = []
    for rec in pinning_raw:
        item = dict(rec)
        if evidence_ok:
            mine = _evidence_lines(evidence, test_id(rec), rec["module"])
            covered = bool(mine) and any(
                mine <= _evidence_lines(evidence, test_id(r), rec["module"])
                for r in interface
                if r["module"] == rec["module"]
            )
            if not mine:
                warnings.append(
                    f"{rec['file']}::{rec['test_name']}: no coverage in evidence for {rec['module']}, "
                    "not covered through the interface"
                )
            item["covered_through_interface"] = covered
            item["note"] = NOTE_COVERED if covered else NOTE_MOVE
        else:
            item["note"] = NOTE_MOVE
        pinning.append(item)
    out["pinning_candidates"] = pinning
    return {"seams": out, "interface_tests": interface, "warnings": warnings}


def _find_tests(root, entries):
    found = []
    for e in entries:
        p = root / e
        paths = [p] if p.is_file() else sorted(p.rglob("*.py"))
        for path in paths:
            rel = path.relative_to(root)
            if not _skip_dir(rel.parts) and (path.name.startswith("test_") or path.name.endswith("_test.py")):
                found.append(rel.as_posix())
    return sorted(set(found))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("propose", "classify"):
        p = sub.add_parser(name)
        p.add_argument("--root", required=True)
        p.add_argument("--source-root", action="append", required=True)
        if name == "classify":
            p.add_argument("--seams", required=True)
            p.add_argument("--tests", action="append", required=True)
            p.add_argument("--evidence")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if args.cmd == "propose":
        result = propose(root, args.source_root)
    else:
        seams_doc = json.loads(Path(args.seams).read_text())
        evidence = None
        if args.evidence and Path(args.evidence).is_file():
            doc = json.loads(Path(args.evidence).read_text())
            evidence = doc.get("languages", {}).get("python")
        result = classify(root, args.source_root, seams_doc, _find_tests(root, args.tests), evidence)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
