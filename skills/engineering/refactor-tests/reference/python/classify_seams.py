"""Propose Python seams and classify tests against them (static, from the AST).

Usage:
  python classify_seams.py propose --root PROJECT --source-root src [--source-root ...]
  python classify_seams.py classify --root PROJECT --source-root src \
      --seams seams.json --tests tests [--tests ...] [--evidence test-evidence.json]
  python classify_seams.py reuse --root PROJECT --proposed seams-proposed.json \
      [--confirmed .scratch/refactor-tests/seams-confirmed.json]

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
Coverage plays no part in that split. A patch or setattr target that names a module
attribute bound by an import (not defined in the module) is a test double: it is listed
under `doubles`, not `internals`. A double of a name imported from outside the project's
source files (third-party or stdlib: a system boundary) has kind `boundary-double`; a double
of a name imported from a project module keeps `collaborator-double`. Outside the project means a
module that is not a source file and has a `vendor`, `vendored`, `_vendor`, or `_vendored` segment (a
source file with such a name stays project), or that resolves to no `.py` file under a source root; a
`build` subpackage below the first segment counts as project, a top-level `build` does not.
Each pinning candidate has a `kind`, the strictest over all the test's non-seam references:
`public-non-seam` > `private` > `collaborator-double` > `constant` > `boundary-double` > `other`.

`reuse` merges the `propose` output with an earlier run's seams-confirmed file and prints
the difference the confirm round shows; see `reuse()`.

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
import functools
import json
import os
import sys
from pathlib import Path

from refactor_tests_shared import is_variant

NOTE_COVERED = "lines covered by one interface test (assertions not compared)"
NOTE_MOVE = "move the assertion to the interface"
NOTE_DOUBLE = "re-point the stub (deps injection or a checked patch); do not delete"
NOTE_BOUNDARY = "double of a system boundary: keep, no deletion"
DOUBLE_KINDS = ("collaborator-double", "boundary-double")
KINDS = ("public-non-seam", "private", "collaborator-double", "constant", "boundary-double", "other")  # strictest first
CONFIRMED = ".scratch/refactor-tests/seams-confirmed.json"


def _is_dunder(name):
    return name.startswith("__") and name.endswith("__")


def _public(name):
    return not name.startswith("_")


_SKIP_NAMES = {"vendor", "node_modules", ".venv", "build", ".scratch", ".reference-projects", "__pycache__"}
_SKIP_NAMES_BELOW_ROOT = _SKIP_NAMES - {"build"}  # first-party generated code may sit in a nested `build`


def _skip_dir(parts):
    return any(p in _SKIP_NAMES for p in parts)


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


_COMPOUND = (ast.If, ast.Try, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith) + (
    (ast.TryStar,) if hasattr(ast, "TryStar") else ())


def _module_statements(body):
    """Module-scope statements, also those nested in if/try/for/while/with (not in def or class bodies)."""
    for node in body:
        yield node
        if isinstance(node, _COMPOUND):
            for field in ("body", "orelse", "finalbody"):
                yield from _module_statements(getattr(node, field, []))
            for handler in getattr(node, "handlers", []):
                yield from _module_statements(handler.body)


def _target_names(target):
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for e in target.elts:
            yield from _target_names(e)
    elif isinstance(target, ast.Starred):
        yield from _target_names(target.value)


_BINDING_RANK = {"import": 0, "constant": 1, "callable": 2}  # a name defined in the module beats its import


def module_table(tree):
    """Top-level name -> how the module binds it: `import`, `callable` (def, class, lambda) or `constant`.

    A name both imported and defined counts as defined: a patch on it replaces the module's own code.
    """
    table = {}

    def bind(name, how):
        if _BINDING_RANK[how] >= _BINDING_RANK.get(table.get(name), -1):
            table[name] = how

    for node in _module_statements(tree.body):
        if isinstance(node, ast.Import):
            for a in node.names:
                bind(a.asname or a.name.split(".")[0], "import")
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name != "*":
                    bind(a.asname or a.name, "import")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bind(node.name, "callable")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and getattr(node, "value", None) is not None:
            how = "callable" if isinstance(node.value, ast.Lambda) else "constant"
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                for name in _target_names(t):
                    bind(name, how)
    return table


def _bound_names(tree):
    """Every name a seam entry may hold for this module: top-level bindings, `__all__` names, `Class.method`.

    None when the module binds names it does not spell out (`from x import *`, a module
    `__getattr__`): its seams cannot be checked.
    """
    names = set(module_table(tree))
    names |= set(_all_names(tree)[0] or ())
    for node in _module_statements(tree.body):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            return None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__getattr__":
            return None
        if isinstance(node, ast.ClassDef):
            names |= {f"{node.name}.{i.name}" for i in node.body
                      if isinstance(i, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return names


@functools.cache
def _holds_module(base, parts):
    """True when `base/<parts>` is a directory holding a `.py` file at any depth (skipping `_SKIP_NAMES_BELOW_ROOT` directories; `build` is walked), or a `<parts>.py` file."""
    folder = base.joinpath(*parts)
    if folder.is_dir():
        for _, dirs, names in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in _SKIP_NAMES_BELOW_ROOT]
            if any(n.endswith(".py") for n in names):
                return True
    return base.joinpath(*parts[:-1], parts[-1] + ".py").is_file()


def _is_vendored(segment):
    return segment in ("vendor", "vendored", "_vendor", "_vendored")


def _resolves_under_source(root, source_roots, module):
    """True when `module` is a `.py` file or a directory holding one under a source root, though `files` omits it.

    Only a `build` segment below the first (first-party generated code) overrides `_skip_dir`: a
    top-level `build` (setuptools output, the PyPA frontend), `vendor`, `node_modules`, `.venv` and the
    other skipped names stay outside the project. A directory with no `.py` file is no module.
    """
    parts = tuple(module.split("."))
    if parts[0] in _SKIP_NAMES or any(p in _SKIP_NAMES_BELOW_ROOT for p in parts[1:]):
        return False
    return any(_holds_module(root / sr, parts) for sr in source_roots)


def boundary_names(tree, importer, importer_is_pkg, files, root, source_roots):
    """Names the module binds only by imports that do not refer to a project module (third-party or stdlib).

    A name refers to a project module when it is a source file, or a package (also a namespace
    package without `__init__.py`) holding one, or a `.py` file or a directory holding one under a
    source root of `root` (a subpackage named like `build`, absent from `files`, is still the
    project's own). A vendored segment (`vendor`, `vendored`, `_vendor`, `_vendored`, matched whole) marks third-party code.
    `import a.b.c` binds `a`, so `a` decides; `import a.b.c as x` and `from a.b import c` bind the
    full module. A name rebound from a project source is not a boundary.
    """
    def own_file(module):
        """A first-party source file: a vendored parent segment, or a vendored package name, marks third-party code."""
        parts = module.split(".")
        return (module in files and not any(_is_vendored(p) for p in parts[:-1])
                and not (_is_vendored(parts[-1]) and files[module][1]))

    def project(module):
        if module is None:
            return False
        if own_file(module):
            return True
        if any(_is_vendored(p) for p in module.split(".")):
            return False
        if any(k.startswith(module + ".") for k in files):
            return True
        return _resolves_under_source(root, source_roots, module)

    external, internal = set(), set()
    for node in _module_statements(tree.body):
        if isinstance(node, ast.Import):
            for a in node.names:
                bound = a.asname or a.name.split(".")[0]
                (internal if project(a.name if a.asname else bound) else external).add(bound)
        elif isinstance(node, ast.ImportFrom):
            src = _resolve_from(importer, importer_is_pkg, node.level, node.module)
            for a in node.names:
                if a.name != "*":
                    first_party = project(src) and (own_file(f"{src}.{a.name}") or not _is_vendored(a.name))
                    (internal if first_party else external).add(a.asname or a.name)
    return external - internal


def ref_kind(rest, table, patched, boundary=()):
    """Pinning kind of one non-seam reference `rest` (dotted name inside a module).

    `patched` is True when the test names it as a patch or setattr target. `boundary` holds
    the imported names whose source lies outside the project: patching one is a `boundary-double`.
    """
    head = rest.partition(".")[0]
    bound = table.get(head)
    if bound == "import":
        if not patched:
            return "other"
        return "boundary-double" if head in boundary else "collaborator-double"
    if bound == "constant":
        return "constant"
    if bound == "callable":
        private = any(p.startswith("_") and not _is_dunder(p) for p in rest.split("."))
        return "private" if private else "public-non-seam"
    return "other"


def strictest(kinds):
    return min(kinds, key=KINDS.index)


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
        self.patched = set()  # the refs named as patch or setattr targets

    def _add(self, dotted, patched=False):
        # longest project-module prefix, remainder = name inside it
        parts = dotted.split(".")
        for i in range(len(parts), 0, -1):
            mod = ".".join(parts[:i])
            if mod in self.modules:
                rest = ".".join(parts[i : i + 2])
                if rest:
                    self.refs.add((mod, rest))
                    if patched:
                        self.patched.add((mod, rest))
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
            self._add(target, patched=True)
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
        if is_variant(tid, file_id):
            lines |= set(entry.get("covered", {}).get(rel_src, {}).get("lines", []))
    return lines


def _test_id(rec):
    return f"{rec['file']}::{rec['test_name']}"


def _confirmed_seams(seams_doc):
    """Source path -> confirmed seam entries, for modules with at least one."""
    out = {}
    for rel, entry in seams_doc.get("modules", {}).items():
        confirmed = [s for s in entry["seams"] if s.get("status") == "confirmed"]
        if confirmed:
            out[rel] = {"seams": confirmed}
    return out


def _split_tests(root, test_paths, files, seam_sets, tables, warnings, boundaries):
    """(interface, pinning_raw, all_refs): each test split per source module it references.

    A non-seam reference that is a patch target bound by an import in the module is a test
    double: it goes to `doubles`, not `internals`. Each pinning record carries `kind`, the
    strictest kind of its non-seam references (`classify` then widens it to the whole test).
    `boundaries` maps a module to its imported names that come from outside the project
    (kind `boundary-double` when patched).
    """
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
                table = tables.get(mod, {})
                kinds = {r: ref_kind(r, table, (mod, r) in visitor.patched, boundaries.get(mod, ()))
                         for r in rests if not _seam_ok(r, seam_sets[mod])}
                rec = {"file": tpath, "test_name": tname, "module": files[mod][0]}
                if kinds:
                    pinning_raw.append({
                        **rec,
                        "internals": sorted(r for r, k in kinds.items() if k not in DOUBLE_KINDS),
                        "doubles": sorted(r for r, k in kinds.items() if k in DOUBLE_KINDS),
                        "kind": strictest(kinds.values()),
                    })
                else:
                    interface.append(rec)
    return interface, pinning_raw, all_refs


def _add_candidates(root, files, rel_to_mod, modules_out, interface, all_refs, evidence, warnings):
    """Confirmed seams no interface test reaches; warns on re-exported candidates."""
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
            reached = any(lines & _evidence_lines(evidence, _test_id(r), rel) for r in tests_here)
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
    return add


def _pinning_candidates(pinning_raw, interface, evidence, evidence_ok, warnings):
    """Pinning records with their note, plus `covered_through_interface` when evidence is ok."""
    pinning = []
    for rec in pinning_raw:
        item = dict(rec)
        if evidence_ok:
            mine = _evidence_lines(evidence, _test_id(rec), rec["module"])
            covered = bool(mine) and any(
                mine <= _evidence_lines(evidence, _test_id(r), rec["module"])
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
        if not item["internals"] and item["kind"] in DOUBLE_KINDS:
            # only doubles in this module, and no stricter kind elsewhere: nothing to move
            item["note"] = NOTE_DOUBLE if item["kind"] == "collaborator-double" else NOTE_BOUNDARY
        pinning.append(item)
    return pinning


def _widen_kinds(pinning_raw):
    """Give every record of one test the strictest kind over all its records (one review item per test)."""
    per_test = {}
    for rec in pinning_raw:
        per_test.setdefault(_test_id(rec), []).append(rec["kind"])
    for rec in pinning_raw:
        rec["kind"] = strictest(per_test[_test_id(rec)])


def classify(root, source_roots, seams_doc, test_paths, evidence=None):
    files = source_files(root, source_roots)
    rel_to_mod = {rel: name for name, (rel, _) in files.items()}
    modules_out = _confirmed_seams(seams_doc)
    seam_sets = {
        rel_to_mod[rel]: {s["name"] for s in entry["seams"]}
        for rel, entry in modules_out.items()
        if rel in rel_to_mod
    }
    warnings = []
    if not seam_sets:
        warnings.append("no confirmed seams: no test classified")
    evidence_ok = bool(evidence) and evidence.get("status") == "ok"
    if not evidence_ok:
        warnings.append(
            "evidence status is not ok: add_candidates and covered_through_interface omitted"
        )

    tables, boundaries = {}, {}
    for mod in seam_sets:
        tree = _parse(root / files[mod][0])
        tables[mod] = module_table(tree) if tree is not None else {}
        boundaries[mod] = boundary_names(tree, mod, files[mod][1], files, root, source_roots) if tree is not None else set()
    interface, pinning_raw, all_refs = _split_tests(root, test_paths, files, seam_sets, tables, warnings, boundaries)
    _widen_kinds(pinning_raw)
    out = {"modules": modules_out}
    if evidence_ok:
        out["add_candidates"] = _add_candidates(
            root, files, rel_to_mod, modules_out, interface, all_refs, evidence, warnings
        )
    out["pinning_candidates"] = _pinning_candidates(
        pinning_raw, interface, evidence, evidence_ok, warnings
    )
    return {"seams": out, "interface_tests": interface, "warnings": warnings}


def _schema_problem(doc):
    """Why `doc` is not a seams-confirmed document, or None when it is one."""
    if not isinstance(doc, dict) or "modules" not in doc:
        return "no `modules` key"
    if not isinstance(doc["modules"], dict):
        return "`modules` is not an object"
    for rel, entry in doc["modules"].items():
        if not isinstance(entry, dict) or not isinstance(entry.get("seams"), list):
            return f"module {rel} has no `seams` list"
        for s in entry["seams"]:
            if not isinstance(s, dict) or not isinstance(s.get("name"), str) or not isinstance(s.get("status"), str):
                return f"module {rel} has a seam without a string `name` and `status`"
    return None


def load_confirmed(path):
    """(doc, status, warnings) for a seams-confirmed file; status is `ok`, `absent` or `ignored`.

    A file that cannot be read, is not JSON, or has the wrong shape is ignored with a warning,
    and the run behaves as with no file.
    """
    path = Path(path)
    if not path.exists():
        return None, "absent", []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        problem = f"not readable JSON ({e})"
    else:
        problem = _schema_problem(doc)
    if problem:
        return None, "ignored", [f"{path.name}: {problem}; ignored, the run behaves as with no confirmed seams"]
    return doc, "ok", []


def reuse(root, proposed, confirmed_path):
    """Merge this run's `propose` output with the confirmed seams of an earlier run.

    Returns {status, modules, diff: {new_modules, added, removed}, review_modules,
    public_api_modules, warnings}. `modules` keeps each earlier seam with its status
    (`confirmed` or `rejected`) and adds the newly proposed names as `proposed`. A confirmed
    module whose file is gone, or a seam name the module no longer binds, is dropped with a
    warning; a module with a star import or a module `__getattr__` keeps its seams unchecked.
    `removed` lists confirmed names this run no longer proposes, except `signal: user` names
    (added by the user, never proposed); they stay confirmed.
    `review_modules` (new or changed) are the only ones the confirm round shows;
    `public_api_modules` are those of them with a `public-api` proposal.
    """
    doc, status, warnings = load_confirmed(confirmed_path)
    prev = (doc or {}).get("modules", {})
    now = proposed.get("modules", {})
    modules, new_modules, added, removed = {}, [], {}, {}
    for rel in sorted(set(prev) | set(now)):
        proposals = (now.get(rel) or {}).get("seams", [])
        if rel not in prev:
            new_modules.append(rel)
            modules[rel] = {"seams": [dict(s) for s in proposals]}
            continue
        if not (root / rel).is_file():
            warnings.append(f"{rel}: confirmed module no longer exists; dropped")
            continue
        tree = _parse(root / rel)
        bound = _bound_names(tree) if tree is not None else None
        if tree is None:
            warnings.append(f"{rel}: cannot parse; its confirmed seams are kept unchecked")
        elif bound is None:
            warnings.append(f"{rel}: star import or module __getattr__; its confirmed seams are kept unchecked")
        kept = []
        for s in prev[rel]["seams"]:
            if bound is not None and s["name"] not in bound:
                warnings.append(f"{rel}: {s['status']} seam {s['name']} no longer exists in the module; dropped")
            else:
                kept.append(dict(s))
        known = {s["name"] for s in kept}
        fresh = [dict(s) for s in proposals if s["name"] not in known]
        proposed_names = {p["name"] for p in proposals}
        # a `user` name was never proposed: its absence from the proposal is no change
        gone = [s["name"] for s in kept if s["status"] == "confirmed" and s.get("signal") != "user"
                and s["name"] not in proposed_names]
        if fresh:
            added[rel] = [s["name"] for s in fresh]
        if gone:
            removed[rel] = gone
        if kept or fresh:
            modules[rel] = {"seams": kept + fresh}
    review = sorted(set(new_modules) | set(added) | set(removed))
    public_api = [rel for rel in review
                  if any(s.get("signal") == "public-api" and s.get("status") == "proposed"
                         for s in modules.get(rel, {}).get("seams", []))]
    return {"status": status, "modules": modules,
            "diff": {"new_modules": new_modules, "added": added, "removed": removed},
            "review_modules": review, "public_api_modules": public_api, "warnings": warnings}


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
    r = sub.add_parser("reuse")
    r.add_argument("--root", required=True)
    r.add_argument("--proposed", required=True, help="the `propose` output (seams-proposed.json)")
    r.add_argument("--confirmed", default=CONFIRMED, help="relative paths resolve against --root")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if args.cmd == "propose":
        result = propose(root, args.source_root)
    elif args.cmd == "reuse":
        proposed = json.loads((root / args.proposed).read_text())
        result = reuse(root, proposed, root / args.confirmed)
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
