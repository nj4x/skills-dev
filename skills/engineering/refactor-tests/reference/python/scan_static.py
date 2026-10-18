"""Step 8 static scan: the evidence-free criteria of the simplification plan.

Usage:
  python scan_static.py --root <project> --source-root <root> [--source-root <root> …] \
      --tests <dir or file> [--tests <dir or file> …] [--raiser <name> …]

Prints `{ removals, review_candidates, parametrizations, unanalyzable }` to stdout, in
the shapes of `simplification-plan.json` schema v2 (`reference/patterns.md`). The
caller merges them into the plan with the evidence-based and pinning entries.

Criteria, in the order of SKILL.md Step 8:
- exact-duplicate (removal): same scope (file and class), same arguments, decorators
  and body, ignoring only name and docstring. The first test in the file stays and is
  named in `duplicate_of`. Tests in different files or classes are never compared:
  module globals, class fixtures and conftest may bind the same names differently.
- dead-test (review only): no assertion (Assertion vocabulary in patterns.md: `assert`,
  `raise`, `pytest.raises`/`warns`/`fail`/`deprecated_call`, a call whose name starts
  with an assertion prefix, or a fixture or helper from the test file or a conftest.py
  above it whose body asserts). `kind` is the first match of `no-raise-contract`,
  `fail-soft`, `never-fails`, `no-assertion`. `no-raise-contract` matches when the last
  call is a bare `validate(…)` or `<any receiver>.validate(…)`, or matches a `--raiser`: a
  bare call matches any raiser with that last name; a dotted call matches only when one
  dotted name ends with the other (`config.load` and `pkg.config.load`, never `other.load`).
- trivially-true (removal): every statement is `assert <truthy constant>`,
  `assert a == a` / `assert a is a`, `assertTrue(<truthy constant>)` or
  `assertEqual(a, a)` / `assertIs(a, a)`, where `a` holds no call. A test whose fixture
  asserts is not flagged trivially-true.
- parametrize-cluster (N >= 3) and parametrize-pair (N = 2, names differ only by a
  trailing integer or a `_<letter>` suffix): same scope, arguments and decorators, and
  bodies equal once constants are replaced by placeholders. Each differing constant
  becomes a parameter; its values must share one type across the tests.

Do not flag: tests with different fixtures, decorators or markers, different mock
configuration (a differing constant inside `patch(…)`, `monkeypatch.setattr(…)`,
`return_value` or `side_effect`), differing input types, differing docstrings, comments
in the body (regeneration would drop them), an existing `parametrize`, or a file the
parser cannot read (listed under `unanalyzable`).

`--source-root` resolves the source function a cluster calls: it names the
consolidated test when the test names share no useful prefix, and the evidence line.
"""
import argparse
import ast
import copy
import io
import json
import keyword
import math
import re
import sys
import tokenize
from pathlib import Path

from classify_seams import _skip_dir, source_files
from refactor_tests_shared import source_lines

ASSERT_PREFIXES = ("assert", "_assert", "check", "_check", "expect", "_expect", "verify", "_verify")
ASSERT_CALLS = {"raises", "warns", "fail", "deprecated_call"}
SKIP_CALLS = {"skip", "importorskip"}
NO_RAISE_PHRASES = ("does not raise", "must not raise")
MOCK_CALLS = {"patch", "object", "dict", "multiple", "setattr", "setitem", "setenv",
              "Mock", "MagicMock", "AsyncMock", "PropertyMock", "create_autospec"}
MOCK_ATTRS = {"return_value", "side_effect"}


# --- AST helpers -----------------------------------------------------------

def _call_name(call):
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _strip_docstring(body):
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def _sig(fn):
    return json.dumps([type(fn).__name__, ast.dump(fn.args), [ast.dump(d) for d in fn.decorator_list]])


def _body_dump(fn):
    return ast.dump(ast.Module(body=_strip_docstring(fn.body), type_ignores=[]))


def _is_parametrized(fn):
    for d in fn.decorator_list:
        node = d.func if isinstance(d, ast.Call) else d
        if isinstance(node, ast.Attribute) and node.attr == "parametrize":
            return True
    return False


def _is_fixture(fn):
    for d in fn.decorator_list:
        node = d.func if isinstance(d, ast.Call) else d
        if (_dotted(node) or "").split(".")[-1] == "fixture":
            return True
    return False


def _fixture_name(fn):
    for d in fn.decorator_list:
        if isinstance(d, ast.Call):
            for kw in d.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    return kw.value.value
    return fn.name


def _has_comments(lines, fn):
    start = min([fn.lineno] + [d.lineno for d in fn.decorator_list])
    seg = "\n".join(lines[start - 1:fn.end_lineno])
    try:
        return any(t.type == tokenize.COMMENT for t in tokenize.generate_tokens(io.StringIO(seg).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return True


def _is_test_class(node):
    if node.name.startswith("Test"):
        return True
    return any((_dotted(b) or "").endswith("TestCase") for b in node.bases)


def test_functions(tree):
    """(class name or None, function) for every collected test function, in file order."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            yield None, node
        elif isinstance(node, ast.ClassDef) and _is_test_class(node):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith("test"):
                    yield node.name, sub


def _tname(cls, name):
    return f"{cls}::{name}" if cls else name


def _excerpt(lines, fn, n=2):
    body = _strip_docstring(fn.body) or fn.body
    first = body[0].lineno
    return " | ".join(line.strip() for line in lines[first - 1:first - 1 + n])


# --- assertion vocabulary --------------------------------------------------

class Helpers:
    """Functions a test can reach by name: the test file, its class, and conftest.py files above it."""

    def __init__(self, root, path, tree, conftests):
        self.functions = {}
        self.fixtures = {}
        chain = []
        d = path.parent
        while True:
            if d in conftests:
                chain.append(conftests[d])
            if d == root or root not in d.parents:
                break
            d = d.parent
        for t in reversed(chain):
            self._add(t.body)
        self._add(tree.body)
        self.methods = {}
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                self.methods[node.name] = {
                    f.name: f for f in node.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self._memo = {}

    def _add(self, body):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[node.name] = node
                if _is_fixture(node):
                    self.fixtures[_fixture_name(node)] = node

    def asserts(self, fn, cls=None, seen=None):
        key = (cls, id(fn))
        if key in self._memo:
            return self._memo[key]
        top = seen is None
        seen = set() if top else seen
        if key in seen:
            return False
        seen.add(key)
        result = self._asserts(fn, cls, seen)
        # A False below the top call may come from the cycle guard cutting off a path that
        # asserts (A -> B -> A, A -> C asserts): only a top-level False is final.
        if result or top:
            self._memo[key] = result
        return result

    def fixture_asserts(self, fn, seen=None):
        """True when a fixture `fn` requests asserts."""
        seen = set() if seen is None else seen
        for a in fn.args.args + fn.args.kwonlyargs:
            fix = self.fixtures.get(a.arg)
            if fix is not None and fix is not fn and self.asserts(fix, None, seen):
                return True
        return False

    def _asserts(self, fn, cls, seen):
        if self.fixture_asserts(fn, seen):
            return True
        for node in ast.walk(fn):
            if isinstance(node, (ast.Assert, ast.Raise)):
                return True
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node) or ""
            if name in ASSERT_CALLS or name.startswith(ASSERT_PREFIXES):
                return True
            target = None
            if isinstance(node.func, ast.Name):
                target, tcls = self.functions.get(node.func.id), None
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) \
                    and node.func.value.id == "self" and cls:
                target, tcls = self.methods.get(cls, {}).get(node.func.attr), cls
            if target is not None and target is not fn and self.asserts(target, tcls, seen):
                return True
        return False


def _flat(stmts):
    """Statements in execution order; a `with` yields itself, then its body."""
    for s in stmts:
        yield s
        if isinstance(s, (ast.With, ast.AsyncWith)):
            yield from _flat(s.body)


def _last_call(stmts):
    if not stmts:
        return None
    s = stmts[-1]
    if isinstance(s, (ast.With, ast.AsyncWith)):
        return _last_call(s.body)
    value = getattr(s, "value", None)
    if isinstance(value, ast.Await):
        value = value.value
    if isinstance(s, (ast.Expr, ast.Assign, ast.AnnAssign, ast.Return)) and isinstance(value, ast.Call):
        return value
    return None


def _is_error(node):
    if isinstance(node, (ast.List, ast.Tuple)):
        return any(_is_error(e) for e in node.elts)
    if isinstance(node, ast.Call):
        node = node.func
    name = (_dotted(node) or "").split(".")[-1]
    return name.endswith(("Error", "Exception"))


def _sets_error(node):
    """True when `node` (a statement, or the items of a `with`) sets an error as a side effect."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.keyword) and sub.arg == "side_effect" and _is_error(sub.value):
            return True
        if isinstance(sub, ast.Assign) and any(
                isinstance(t, ast.Attribute) and t.attr == "side_effect" for t in sub.targets) \
                and _is_error(sub.value):
            return True
    return False


def _has_call(stmt):
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        return False
    return any(isinstance(n, ast.Call) for n in ast.walk(stmt))


def _raiser_match(func, dotted, raiser):
    """A bare `load()` (a from-import) matches any raiser named `….load`; `x.load()` matches
    only when one dotted name ends with the other (`config.load` and `pkg.config.load`)."""
    if not dotted:
        return False
    if isinstance(func, ast.Name):
        return raiser.split(".")[-1] == dotted
    return dotted == raiser or dotted.endswith("." + raiser) or raiser.endswith("." + dotted)


def dead_kind(fn, raisers=()):
    """`kind` of a test with no assertion: the first of Dead-test kinds that matches."""
    body = _strip_docstring(fn.body)
    last = _last_call(body)
    if last is not None:
        dotted = _dotted(last.func) or ""
        tail = dotted.split(".")[-1] if dotted else getattr(last.func, "attr", "")
        if tail == "validate" and isinstance(last.func, (ast.Name, ast.Attribute)):
            return "no-raise-contract"
        if any(_raiser_match(last.func, dotted, r) for r in raisers):
            return "no-raise-contract"
    text = fn.name.replace("_", " ").lower() + " " + (ast.get_docstring(fn) or "").lower()
    text = re.sub(r"\s+", " ", text)
    if any(p in text for p in NO_RAISE_PHRASES):
        return "no-raise-contract"
    flat = list(_flat(body))
    setup = any(_sets_error(d) for d in fn.decorator_list)
    for s in flat:
        if setup and _has_call(s):
            return "fail-soft"
        head = [i.context_expr for i in s.items] if isinstance(s, (ast.With, ast.AsyncWith)) else [s]
        if any(_sets_error(h) for h in head):
            setup = True
    if any(isinstance(n, ast.Call) and _call_name(n) in SKIP_CALLS for n in ast.walk(fn)):
        return "never-fails"
    return "no-assertion"


def trivially_true(fn):
    body = _strip_docstring(fn.body)
    if not body:
        return False
    for s in body:
        if isinstance(s, ast.Assert):
            if not _trivial_test(s.test):
                return False
        elif isinstance(s, ast.Expr) and isinstance(s.value, ast.Call):
            c = s.value
            name = _call_name(c)
            if name == "assertTrue" and len(c.args) >= 1 and _truthy_const(c.args[0]):
                continue
            if name in ("assertEqual", "assertEquals", "assertIs") and len(c.args) >= 2 \
                    and _same(c.args[0], c.args[1]):
                continue
            return False
        else:
            return False
    return True


def _truthy_const(node):
    return isinstance(node, ast.Constant) and bool(node.value)


def _same(a, b):
    return ast.dump(a) == ast.dump(b) and not any(isinstance(n, ast.Call) for n in ast.walk(a))


def _trivial_test(t):
    if _truthy_const(t):
        return True
    return isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], (ast.Eq, ast.Is)) \
        and _same(t.left, t.comparators[0])


# --- parametrize clusters --------------------------------------------------

class _Consts(ast.NodeTransformer):
    """Replace constants (outside f-strings) by placeholders; record value and context."""

    def __init__(self):
        self.slots = []  # (value, name hint, in mock config)
        self._fstring = 0
        self._stack = []

    def visit(self, node):
        self._stack.append(node)
        try:
            return super().visit(node)
        finally:
            self._stack.pop()

    def visit_JoinedStr(self, node):
        self._fstring += 1
        self.generic_visit(node)
        self._fstring -= 1
        return node

    def visit_UnaryOp(self, node):
        if isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) \
                and isinstance(node.operand.value, (int, float, complex)) \
                and not isinstance(node.operand.value, bool) and not self._fstring:
            return self._slot(-node.operand.value, node)
        self.generic_visit(node)
        return node

    def visit_Constant(self, node):
        if self._fstring:
            return node
        return self._slot(node.value, node)

    def _slot(self, value, node):
        parents = self._stack[:-1]
        parent = parents[-1] if parents else None
        hint = "value"
        if isinstance(parent, ast.keyword) and parent.arg:
            hint = parent.arg
        elif isinstance(parent, ast.Compare):
            hint = "expected" if any(c is node for c in parent.comparators) else "value"
        elif isinstance(parent, ast.Call) and any(a is node for a in parent.args):
            hint = "arg"
        self.slots.append((value, hint, self._in_mock(parents)))
        return ast.Name(id=f"__P{len(self.slots) - 1}__", ctx=ast.Load())

    @staticmethod
    def _in_mock(parents):
        for p in parents:
            if isinstance(p, ast.Call) and _call_name(p) in MOCK_CALLS:
                return True
            if isinstance(p, ast.keyword) and p.arg in MOCK_ATTRS:
                return True
            if isinstance(p, ast.Assign) and any(
                    isinstance(t, ast.Attribute) and t.attr in MOCK_ATTRS for t in p.targets):
                return True
        return False


def _normalized(fn):
    body = copy.deepcopy(_strip_docstring(fn.body))
    rep = _Consts()
    mod = ast.Module(body=[rep.visit(s) for s in body], type_ignores=[])
    return ast.dump(mod), rep.slots


def _pair_ok(a, b):
    ma = re.fullmatch(r"(.*?)(\d+|_[a-z])", a)
    mb = re.fullmatch(r"(.*?)(\d+|_[a-z])", b)
    return bool(ma and mb and ma.group(1) == mb.group(1) and ma.group(2) != mb.group(2))


def _common_prefix(names):
    p = names[0]
    for n in names[1:]:
        while not n.startswith(p):
            p = p[:-1]
    if not all(len(n) == len(p) or n[len(p)] in "_0123456789" for n in names):
        p = p[:p.rfind("_")] if "_" in p else ""
    return p.rstrip("_")


class SourceIndex:
    """Which call in a test resolves to a function under a source root."""

    def __init__(self, root, source_roots):
        self.modules = set(source_files(root, source_roots))

    def _is_source(self, module):
        return any(module == m or module.startswith(m + ".") or m.startswith(module + ".")
                   for m in self.modules) if module else False

    def callee(self, tree, fn):
        names, aliases = {}, {}
        for node in tree.body + [n for n in ast.walk(fn) if isinstance(n, (ast.Import, ast.ImportFrom))]:
            if isinstance(node, ast.ImportFrom) and node.level == 0 and self._is_source(node.module):
                for a in node.names:
                    names[a.asname or a.name] = a.name
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if self._is_source(a.name):
                        aliases[a.asname or a.name.split(".")[0]] = a.name
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id in names:
                return names[node.func.id]
            dotted = _dotted(node.func)
            if dotted and "." in dotted and dotted.split(".")[0] in aliases:
                return dotted.split(".")[-1]
        return None


def _scope_names(tree, cls):
    body = tree.body
    if cls:
        body = next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    return {n.name for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _consolidated_name(names, taken, callee):
    base = _common_prefix(names)
    candidates = []
    if base.startswith("test") and base != "test":
        candidates.append(base)
    if callee:
        candidates.append(f"test_{callee.lstrip('_')}")
    candidates.append(f"{base if base.startswith('test_') else names[0]}_parametrized")
    for c in candidates:
        if c not in taken:
            return c
    i = 2
    while f"{candidates[-1]}_{i}" in taken:
        i += 1
    return f"{candidates[-1]}_{i}"


def _param_names(hints, fn):
    used = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
    used |= {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    out = []
    for h in hints:
        base = h if h.isidentifier() and not keyword.iskeyword(h) else "value"
        cand, i = base, 2
        while cand in used:
            cand, i = f"{base}_{i}", i + 1
        used.add(cand)
        out.append(cand)
    return out


def _render(fn, positions, params, rows, ids, name):
    """Source of the consolidated test at column 0."""
    new = copy.deepcopy(fn)
    new.name = name
    rep = _Consts()
    body = _strip_docstring(new.body)
    doc = new.body[:len(new.body) - len(body)]
    replaced = [rep.visit(s) for s in body]
    names = {f"__P{p}__": params[k] for k, p in enumerate(positions)}
    values = {f"__P{i}__": slot[0] for i, slot in enumerate(rep.slots)}

    class Fill(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id in names:
                return ast.Name(id=names[node.id], ctx=ast.Load())
            if node.id in values:
                v = values[node.id]
                if isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
                    return ast.UnaryOp(op=ast.USub(), operand=ast.Constant(-v))
                return ast.Constant(v)
            return node

    new.body = doc + [Fill().visit(s) for s in replaced]
    new.args.args = new.args.args + [ast.arg(arg=p) for p in params]
    ast.fix_missing_locations(new)
    if len(params) == 1:
        rows_src = [f"        {r[0]!r}," for r in rows]
    else:
        rows_src = [f"        ({', '.join(repr(v) for v in r)})," for r in rows]
    deco = ["@pytest.mark.parametrize(", f"    {','.join(params)!r},", "    ["] + rows_src + ["    ],"]
    if ids:
        deco.append(f"    ids={ids!r},")
    deco.append(")")
    # ast.unparse puts the existing decorators first; parametrize goes right above the def line.
    out = ast.unparse(new).splitlines()
    def_at = next(i for i, line in enumerate(out) if line.startswith(("def ", "async def ")))
    return "\n".join(out[:def_at] + deco + out[def_at:]) + "\n"


def _literal_ok(v):
    if isinstance(v, float) and not math.isfinite(v):
        return False
    try:
        return ast.literal_eval(repr(v)) == v
    except (ValueError, SyntaxError):
        return False


def _cluster(rel, cls, members, lines, tree, sources, chosen):
    """(parametrizations entry, None) or (None, unanalyzable entry) or (None, None) when no candidate.

    `chosen` holds the names earlier clusters in this file and scope picked; the picked name is added.
    """
    fns = [f for f, _ in members]
    names = [f.name for f in fns]
    if len(fns) == 2 and not _pair_ok(*names):
        return None, None
    criterion = "parametrize-cluster" if len(fns) >= 3 else "parametrize-pair"
    tests = [_tname(cls, n) for n in names]

    def skip(reason):
        return None, {"file": rel, "tests": tests, "reason": reason}

    if any(_is_parametrized(f) for f in fns):
        return skip("already parametrized")
    if any(_has_comments(lines, f) for f in fns):
        return skip("comments in body would be lost by AST regeneration")
    if len({ast.get_docstring(f) for f in fns}) > 1:
        return skip("docstrings differ; consolidation would drop them")
    a = fns[0].args
    if a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs or a.defaults:
        return skip("signature has *args, **kwargs, keyword-only arguments or default values")
    slots = [s for _, s in members]
    positions = [i for i in range(len(slots[0])) if len({repr(s[i][0]) for s in slots}) > 1]
    if not positions:
        return skip("no differing constants")
    if any(slots[0][i][2] for i in positions):
        return skip("differing mock configuration")
    if any(len({type(s[i][0]) for s in slots}) > 1 for i in positions):
        return skip("differing constants of mixed types")
    if not all(_literal_ok(s[i][0]) for s in slots for i in positions):
        return skip("constant has no literal form")
    callee = sources.callee(tree, fns[0])
    taken = _scope_names(tree, cls) | set(names) | chosen
    name = _consolidated_name(names, taken, callee)
    chosen.add(name)
    params = _param_names([slots[0][i][1] for i in positions], fns[0])
    rows = [[s[i][0] for i in positions] for s in slots]
    prefix = _common_prefix(names)
    ids = [n[len(prefix):].strip("_") for n in names] if prefix else []
    if not all(ids) or len(set(ids)) != len(ids):
        ids = []
    body = _render(fns[0], positions, params, rows, ids, name)
    what = f"{callee}(…)" if callee else "the same code"
    return {
        "file": rel,
        "class": cls,
        "tests": tests,
        "consolidated_name": _tname(cls, name),
        "consolidated_body": body,
        "required_imports": ["pytest"],
        "criterion": criterion,
        "evidence": f"{len(fns)} tests call {what} under one assertion pattern; "
                    f"only {len(positions)} constant(s) differ ({', '.join(params)})",
    }, None


# --- scan ------------------------------------------------------------------

def find_tests(root, entries):
    found = set()
    for e in entries:
        p = (root / e)
        paths = [p] if p.is_file() else sorted(p.rglob("*.py"))
        for path in paths:
            rel = path.relative_to(root)
            if not _skip_dir(rel.parts) and (path.name.startswith("test_") or path.name.endswith("_test.py")):
                found.add(rel.as_posix())
    return sorted(found)


def _conftests(root, entries):
    """({directory: tree}, unanalyzable entries for conftest.py files that do not parse)."""
    out, bad = {}, []
    dirs = set()
    for e in entries:
        p = root / e
        dirs.add(p if p.is_dir() else p.parent)
    seen = set()
    for d in dirs:
        for path in list(d.rglob("conftest.py")) + [q / "conftest.py" for q in [d, *d.parents]
                                                    if q == root or root in q.parents]:
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            try:
                out[path.parent] = ast.parse(path.read_text())
            except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
                bad.append({"file": path.relative_to(root).as_posix(),
                            "reason": f"{type(exc).__name__}: {exc}; its helpers and fixtures are not "
                                      f"counted as assertions"})
    return out, sorted(bad, key=lambda e: e["file"])


def scan(root, source_roots, tests, raisers=()):
    root = Path(root).resolve()
    sources = SourceIndex(root, source_roots)
    conftests, bad_conftests = _conftests(root, tests)
    out = {"removals": [], "review_candidates": [], "parametrizations": [], "unanalyzable": bad_conftests}
    for rel in find_tests(root, tests):
        path = root / rel
        try:
            text = path.read_text()
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
            out["unanalyzable"].append({"file": rel, "reason": f"{type(exc).__name__}: {exc}"})
            continue
        lines = [line.rstrip("\r\n") for line in source_lines(text)]
        helpers = Helpers(root, path, tree, conftests)
        dups, norms, trivial = {}, {}, set()
        for cls, fn in test_functions(tree):
            if trivially_true(fn) and not helpers.fixture_asserts(fn):
                trivial.add((cls, fn.name))
                out["removals"].append({"file": rel, "test_name": _tname(cls, fn.name),
                                        "criterion": "trivially-true", "evidence": _excerpt(lines, fn)})
                continue
            dups.setdefault((cls, _sig(fn), _body_dump(fn)), []).append(fn)
        removed = set()
        for (cls, _s, _b), fns in dups.items():
            keep = fns[0]
            for fn in fns[1:]:
                removed.add((cls, fn.name))
                out["removals"].append({
                    "file": rel, "test_name": _tname(cls, fn.name), "criterion": "exact-duplicate",
                    "evidence": f"body identical to {keep.name} (lines {keep.lineno}-{keep.end_lineno} "
                                f"vs {fn.lineno}-{fn.end_lineno})",
                    "duplicate_of": _tname(cls, keep.name)})
        for cls, fn in test_functions(tree):
            key = (cls, fn.name)
            if key in trivial or key in removed:
                continue
            if not helpers.asserts(fn, cls):
                out["review_candidates"].append({
                    "file": rel, "test_name": _tname(cls, fn.name), "criterion": "dead-test",
                    "kind": dead_kind(fn, raisers),
                    "evidence": "no assertion statement in body: " + _excerpt(lines, fn)})
                continue
            norm, slots = _normalized(fn)
            norms.setdefault((cls, _sig(fn), norm), []).append((fn, slots))
        chosen = {}
        for (cls, _s, _n), members in norms.items():
            if len(members) < 2:
                continue
            entry, skipped = _cluster(rel, cls, members, lines, tree, sources, chosen.setdefault(cls, set()))
            if entry:
                out["parametrizations"].append(entry)
            if skipped:
                out["unanalyzable"].append(skipped)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--source-root", action="append", required=True)
    ap.add_argument("--tests", action="append", required=True, help="test directory or file; repeat the flag")
    ap.add_argument("--raiser", action="append", default=[],
                    help="a documented raiser beyond bare `validate(` and `*.validate(`; a dotted name matches "
                         "a dotted call only when one ends with the other; repeat the flag")
    args = ap.parse_args(argv)
    json.dump(scan(args.root, args.source_root, args.tests, args.raiser), sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
