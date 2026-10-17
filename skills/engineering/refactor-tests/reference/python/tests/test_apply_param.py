"""Tests for apply_param.py: the Step 9 single-write parametrize edit and its resume checks.

Run: uv run --with pytest pytest reference/python/tests/test_apply_param.py
"""
import ast
import json
import subprocess
import sys
import textwrap
from pathlib import Path

from scan_static import scan  # conftest.py puts HELPERS on sys.path

HELPERS = Path(__file__).resolve().parent.parent

TEST_FILE = '''"""Clamp tests."""
from pkg.calc import clamp


def test_keep():
    assert clamp(0, 0, 1) >= 0


def test_clamp_low():
    assert clamp(-5, 0, 3) == 0


def test_clamp_high():
    assert clamp(9, 0, 3) == 3


def test_clamp_mid():
    assert clamp(2, 0, 3) == 2


def test_after():
    assert clamp(1, 0, 1) <= 1
'''

CLASS_FILE = '''import pytest
from pkg.calc import clamp


class TestClamp:
    def test_one(self):
        assert clamp(1, 0, 3) == 1

    def test_two(self):
        assert clamp(2, 0, 3) == 2

    def test_three(self):
        assert clamp(3, 0, 3) == 3

    def test_other(self):
        assert clamp(9, 0, 3) <= 3
'''


def project(tmp_path, files):
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "calc.py").write_text("def clamp(x, lo, hi):\n    return max(lo, min(x, hi))\n")
    (tmp_path / "tests").mkdir()
    for name, text in files.items():
        (tmp_path / "tests" / name).write_text(text)
    scratch = tmp_path / ".scratch" / "refactor-tests"
    scratch.mkdir(parents=True)
    out = scan(tmp_path, ["src"], ["tests"])
    plan = {"schema_version": 2, "removals": out["removals"], "review_candidates": out["review_candidates"],
            "parametrizations": out["parametrizations"]}
    (scratch / "simplification-plan.json").write_text(json.dumps(plan))
    (scratch / "ledger.json").write_text(json.dumps({"phase": "executing", "simplification": {}}))
    return tmp_path


def apply(root, *extra):
    res = subprocess.run([sys.executable, str(HELPERS / "apply_param.py"), "--root", str(root), *extra],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def ledger(root):
    return json.loads((root / ".scratch" / "refactor-tests" / "ledger.json").read_text())


def plan(root):
    return json.loads((root / ".scratch" / "refactor-tests" / "simplification-plan.json").read_text())


def pytest_run(root, path):
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", path],
                          cwd=root, capture_output=True, text=True,
                          env={"PYTHONPATH": str(root / "src"), "PATH": "/usr/bin:/bin"})


def functions(text, cls=None):
    tree = ast.parse(text)
    body = tree.body
    if cls:
        body = next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    return [n.name for n in body if isinstance(n, ast.FunctionDef)]


def test_apply_replaces_originals_in_one_write_and_records_ledger(tmp_path):
    root = project(tmp_path, {"test_cl.py": TEST_FILE})
    [result] = apply(root)
    assert result["status"] == "applied"
    text = (root / "tests" / "test_cl.py").read_text()
    assert functions(text) == ["test_keep", "test_clamp", "test_after"]
    assert "import pytest\n" in text
    # the import goes after the module docstring and the existing imports
    assert text.index("import pytest") > text.index("from pkg.calc import clamp")
    assert not list((root / "tests").glob("*.rt-tmp"))
    [entry] = ledger(root)["simplification"]["parametrizations"]
    assert entry == {"file": "tests/test_cl.py", "consolidated_name": "test_clamp",
                     "replaced": ["test_clamp_low", "test_clamp_high", "test_clamp_mid"]}
    res = pytest_run(root, "tests/test_cl.py")
    assert "5 passed" in res.stdout, res.stdout + res.stderr


def test_apply_in_class_reindents_and_keeps_siblings(tmp_path):
    root = project(tmp_path, {"test_cls.py": CLASS_FILE})
    [result] = apply(root)
    assert result["status"] == "applied"
    text = (root / "tests" / "test_cls.py").read_text()
    assert functions(text, "TestClamp") == ["test_clamp", "test_other"]
    assert text.count("import pytest") == 1
    assert ledger(root)["simplification"]["parametrizations"][0]["consolidated_name"] == "TestClamp::test_clamp"
    res = pytest_run(root, "tests/test_cls.py")
    assert "4 passed" in res.stdout, res.stdout + res.stderr


def test_apply_accepts_an_indented_consolidated_body(tmp_path):
    root = project(tmp_path, {"test_cls.py": CLASS_FILE})
    p = plan(root)
    p["parametrizations"][0]["consolidated_body"] = textwrap.indent(p["parametrizations"][0]["consolidated_body"], "    ")
    (root / ".scratch" / "refactor-tests" / "simplification-plan.json").write_text(json.dumps(p))
    [result] = apply(root)
    assert result["status"] == "applied"
    assert "4 passed" in pytest_run(root, "tests/test_cls.py").stdout


def test_resume_entry_in_ledger_is_recorded_and_not_edited(tmp_path):
    root = project(tmp_path, {"test_cl.py": TEST_FILE})
    apply(root)
    before = (root / "tests" / "test_cl.py").read_text()
    [result] = apply(root)
    assert result["status"] == "recorded"
    assert (root / "tests" / "test_cl.py").read_text() == before
    assert len(ledger(root)["simplification"]["parametrizations"]) == 1


def test_resume_already_applied_write_is_recorded_without_edit(tmp_path):
    root = project(tmp_path, {"test_cl.py": TEST_FILE})
    apply(root)
    # the run stopped after the file write, before the ledger write
    (root / ".scratch" / "refactor-tests" / "ledger.json").write_text(json.dumps({"simplification": {}}))
    before = (root / "tests" / "test_cl.py").read_text()
    [result] = apply(root)
    assert result["status"] == "already-applied"
    assert (root / "tests" / "test_cl.py").read_text() == before
    [entry] = ledger(root)["simplification"]["parametrizations"]
    assert entry["replaced"] == ["test_clamp_low", "test_clamp_high", "test_clamp_mid"]
    assert "skipped" not in entry


def test_ast_failure_is_skipped_and_file_left_unchanged(tmp_path):
    root = project(tmp_path, {"test_cl.py": TEST_FILE})
    p = plan(root)
    p["parametrizations"][0]["consolidated_body"] = "def test_clamp(:\n    pass\n"
    (root / ".scratch" / "refactor-tests" / "simplification-plan.json").write_text(json.dumps(p))
    [result] = apply(root)
    assert result["status"] == "skipped"
    assert (root / "tests" / "test_cl.py").read_text() == TEST_FILE
    [entry] = ledger(root)["simplification"]["parametrizations"]
    assert entry["tests"] == ["test_clamp_low", "test_clamp_high", "test_clamp_mid"]
    assert entry["consolidated_name"] == "test_clamp"
    assert "does not parse" in entry["skipped"]
    # a skipped entry is done: a resumed run does not retry it
    assert apply(root)[0]["status"] == "recorded"


def test_missing_original_is_skipped(tmp_path):
    root = project(tmp_path, {"test_cl.py": TEST_FILE})
    p = plan(root)
    p["parametrizations"][0]["tests"].append("test_gone")
    (root / ".scratch" / "refactor-tests" / "simplification-plan.json").write_text(json.dumps(p))
    [result] = apply(root)
    assert result["status"] == "skipped"
    assert "test_gone not found" in result["reason"]
    assert (root / "tests" / "test_cl.py").read_text() == TEST_FILE


def test_unparsable_file_is_skipped(tmp_path):
    root = project(tmp_path, {"test_cl.py": TEST_FILE})
    (root / "tests" / "test_cl.py").write_text(TEST_FILE + "\ndef broken(:\n")
    [result] = apply(root)
    assert result["status"] == "skipped"
    assert "file does not parse" in result["reason"]


def test_index_flag_applies_only_named_entries(tmp_path):
    root = project(tmp_path, {"test_cl.py": TEST_FILE, "test_cls.py": CLASS_FILE})
    assert len(plan(root)["parametrizations"]) == 2
    results = apply(root, "--index", "1")
    assert [r["index"] for r in results] == [1]
    assert len(ledger(root)["simplification"]["parametrizations"]) == 1


def test_aliased_pytest_import_does_not_satisfy_required_import(tmp_path):
    root = project(tmp_path, {"test_cls.py": CLASS_FILE.replace("import pytest", "import pytest as pt")})
    [result] = apply(root)
    assert result["status"] == "applied"
    assert "\nimport pytest\n" in (root / "tests" / "test_cls.py").read_text()
    assert "4 passed" in pytest_run(root, "tests/test_cls.py").stdout
