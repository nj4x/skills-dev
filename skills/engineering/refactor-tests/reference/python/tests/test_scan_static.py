"""Tests for scan_static.py: the evidence-free criteria of SKILL.md Step 8.

Run: uv run --with pytest pytest reference/python/tests/test_scan_static.py
"""
import ast
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scan_static import scan  # conftest.py puts HELPERS on sys.path

HELPERS = Path(__file__).resolve().parent.parent

SOURCE = '''def clamp(x, lo, hi):
    return max(lo, min(x, hi))


def load(path):
    return path
'''


def project(tmp_path, tests, conftest=None, source=SOURCE):
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "calc.py").write_text(source)
    (tmp_path / "tests").mkdir()
    for name, text in tests.items():
        path = tmp_path / "tests" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text))
    if conftest is not None:
        (tmp_path / "tests" / "conftest.py").write_text(textwrap.dedent(conftest))
    return tmp_path


def run(tmp_path, tests, conftest=None, raisers=()):
    root = project(tmp_path, tests, conftest)
    return scan(root, ["src"], ["tests"], raisers)


def names(entries, criterion):
    return sorted(e["test_name"] for e in entries if e["criterion"] == criterion)


def by_name(entries, name):
    return next(e for e in entries if e["test_name"] == name)


# --- exact duplicate --------------------------------------------------------

def test_exact_duplicate_ignores_name_and_docstring_and_keeps_the_first(tmp_path):
    out = run(tmp_path, {"test_dup.py": '''
        from pkg.calc import clamp

        def test_a():
            assert clamp(5, 0, 3) == 3

        def test_b():
            """Same body, other docstring."""
            assert clamp(5, 0, 3) == 3
    '''})
    [entry] = out["removals"]
    assert entry["criterion"] == "exact-duplicate"
    assert entry["test_name"] == "test_b"
    assert entry["duplicate_of"] == "test_a"
    assert "duplicate_of_file" not in entry


def test_exact_duplicate_in_a_class_uses_class_names(tmp_path):
    out = run(tmp_path, {"test_dup.py": '''
        class TestC:
            def test_a(self):
                assert 1 + 1 == 2

            def test_b(self):
                assert 1 + 1 == 2
    '''})
    [entry] = out["removals"]
    assert (entry["test_name"], entry["duplicate_of"]) == ("TestC::test_b", "TestC::test_a")


PLAIN = "def test_a():\n    m = Mock(return_value=1)\n    assert clamp(5, 0, 3) == 3\n\n"


@pytest.mark.parametrize("second", [
    "def test_b(tmp_path):\n    m = Mock(return_value=1)\n    assert clamp(5, 0, 3) == 3\n",
    "@pytest.mark.slow\ndef test_b():\n    m = Mock(return_value=1)\n    assert clamp(5, 0, 3) == 3\n",
    "def test_b():\n    m = Mock(return_value=2)\n    assert clamp(5, 0, 3) == 3\n",
], ids=["fixture", "decorator", "mock-return"])
def test_exact_duplicate_not_flagged_when_setup_differs(tmp_path, second):
    text = "import pytest\nfrom unittest.mock import Mock\nfrom pkg.calc import clamp\n\n" + PLAIN + second
    out = run(tmp_path, {"test_dup.py": text})
    assert names(out["removals"], "exact-duplicate") == []


def test_exact_duplicate_never_compared_across_files_or_classes(tmp_path):
    body = '''
        def test_a():
            assert 1 + 1 == 2
    '''
    out = run(tmp_path, {"test_one.py": body, "test_two.py": body, "test_cls.py": '''
        class TestA:
            def test_a(self):
                assert 1 + 1 == 2

        class TestB:
            def test_a(self):
                assert 1 + 1 == 2
    '''})
    assert out["removals"] == []


# --- trivially true ---------------------------------------------------------

def test_trivially_true_forms_are_removals(tmp_path):
    out = run(tmp_path, {"test_triv.py": '''
        import unittest

        def test_const():
            assert True

        def test_same(x=1):
            assert x == x

        class TestU(unittest.TestCase):
            def test_eq(self):
                self.assertEqual(1, 1)

            def test_true(self):
                self.assertTrue(True)
    '''})
    assert names(out["removals"], "trivially-true") == [
        "TestU::test_eq", "TestU::test_true", "test_const", "test_same"]


def test_trivially_true_not_flagged_for_calls_or_mixed_bodies(tmp_path):
    out = run(tmp_path, {"test_triv.py": '''
        from pkg.calc import load

        def test_determinism():
            assert load(1) == load(1)

        def test_mixed():
            x = load(1)
            assert True
    '''})
    assert names(out["removals"], "trivially-true") == []


def test_two_identical_trivially_true_tests_are_not_also_duplicates(tmp_path):
    out = run(tmp_path, {"test_triv.py": '''
        def test_a():
            assert True

        def test_b():
            assert True
    '''})
    assert [e["criterion"] for e in out["removals"]] == ["trivially-true", "trivially-true"]


# --- dead test --------------------------------------------------------------

def test_dead_test_is_review_only_with_kind(tmp_path):
    out = run(tmp_path, {"test_dead.py": '''
        from pkg.calc import load

        def test_runs():
            load(1)
    '''})
    assert out["removals"] == []
    [entry] = out["review_candidates"]
    assert entry["criterion"] == "dead-test"
    assert entry["kind"] == "no-assertion"
    assert entry["test_name"] == "test_runs"
    assert entry["evidence"].startswith("no assertion statement in body")


@pytest.mark.parametrize("body", [
    "    with pytest.raises(ValueError):\n        load(1)\n",
    "    with pytest.warns(UserWarning):\n        load(1)\n",
    "    if load(1):\n        pytest.fail('x')\n",
    "    if load(1):\n        raise AssertionError\n",
    "    m = load(1)\n    m.assert_called_once()\n",
    "    check_shape(load(1))\n",
    "    self_verify = load(1)\n    _expect_ok(self_verify)\n",
], ids=["raises", "warns", "fail", "raise", "mock-assert", "check-prefix", "expect-prefix"])
def test_assertion_vocabulary_is_not_dead(tmp_path, body):
    text = "import pytest\nfrom pkg.calc import load\n\ndef test_x():\n" + body
    out = run(tmp_path, {"test_vocab.py": text})
    assert names(out["review_candidates"], "dead-test") == []


def test_asserting_helper_in_file_or_conftest_and_fixture_count(tmp_path):
    out = run(tmp_path, {"sub/test_helpers.py": '''
        from pkg.calc import load

        def shape_ok(x):
            assert x

        def test_local_helper():
            shape_ok(load(1))

        def test_conftest_helper():
            conf_ok(load(1))

        def test_fixture(asserting_fixture):
            load(1)

        def test_plain_fixture(plain_fixture):
            load(1)

        class TestM:
            def _ok(self, x):
                assert x

            def test_method_helper(self):
                self._ok(load(1))
    '''}, conftest='''
        import pytest

        def conf_ok(x):
            assert x

        @pytest.fixture
        def asserting_fixture():
            yield
            assert True

        @pytest.fixture
        def plain_fixture():
            return 1
    ''')
    assert names(out["review_candidates"], "dead-test") == ["test_plain_fixture"]


@pytest.mark.parametrize("text, kind", [
    ("def test_ok():\n    schema.validate({})\n", "no-raise-contract"),
    ("def test_x():\n    with ctx():\n        schema.validate({})\n", "no-raise-contract"),
    ("def test_ok():\n    parse_strict({})\n", "no-raise-contract"),
    ("def test_load_does_not_raise():\n    load(1)\n", "no-raise-contract"),
    ('def test_x():\n    """Must not raise on empty input."""\n    load(1)\n', "no-raise-contract"),
    ("def test_x():\n    with patch('pkg.calc.load', side_effect=OSError('x')):\n        run()\n", "fail-soft"),
    ("def test_x():\n    m = Mock(side_effect=ValueError)\n    run(m)\n", "fail-soft"),
    ("def test_x():\n    m = Mock()\n    m.side_effect = KeyError('k')\n    run(m)\n", "fail-soft"),
    ("@patch('pkg.calc.load', side_effect=RuntimeError)\ndef test_x(m):\n    run()\n", "fail-soft"),
    ("def test_x():\n    if not load(1):\n        pytest.skip('no data')\n", "never-fails"),
    ("def test_x():\n    pytest.importorskip('numpy')\n    load(1)\n", "never-fails"),
    ("def test_x():\n    load(1)\n", "no-assertion"),
    ("def test_x():\n    m = Mock(side_effect=ValueError)\n", "no-assertion"),
], ids=["validate", "validate-in-with", "raiser-flag", "name", "docstring", "fail-soft-with",
        "fail-soft-mock", "fail-soft-attr", "fail-soft-decorator", "never-fails", "importorskip", "no-assertion",
        "error-setup-without-call"])
def test_dead_test_kinds(tmp_path, text, kind):
    out = run(tmp_path, {"test_kinds.py": text}, raisers=["config.parse_strict"])
    [entry] = out["review_candidates"]
    assert entry["kind"] == kind


@pytest.mark.parametrize("text, kind", [
    # matches no-raise-contract (validate last), fail-soft and never-fails
    ("def test_x():\n    m = Mock(side_effect=ValueError)\n    run(m)\n"
     "    if m:\n        pytest.skip('x')\n    schema.validate({})\n", "no-raise-contract"),
    # matches fail-soft and never-fails
    ("def test_x():\n    m = Mock(side_effect=ValueError)\n    run(m)\n    pytest.skip('x')\n", "fail-soft"),
], ids=["no-raise-over-rest", "fail-soft-over-never-fails"])
def test_dead_test_kind_precedence_first_match_wins(tmp_path, text, kind):
    out = run(tmp_path, {"test_kinds.py": text})
    assert out["review_candidates"][0]["kind"] == kind


# --- parametrize cluster and pair -----------------------------------------

CLUSTER = '''
    from pkg.calc import clamp

    def test_clamp_low():
        assert clamp(-5, 0, 3) == 0

    def test_clamp_high():
        assert clamp(9, 0, 3) == 3

    def test_clamp_mid():
        assert clamp(2, 0, 3) == 2
'''


def test_parametrize_cluster_emits_concrete_body(tmp_path):
    out = run(tmp_path, {"test_cl.py": CLUSTER})
    [entry] = out["parametrizations"]
    assert entry["criterion"] == "parametrize-cluster"
    assert entry["tests"] == ["test_clamp_low", "test_clamp_high", "test_clamp_mid"]
    assert entry["consolidated_name"] == "test_clamp"
    assert entry["required_imports"] == ["pytest"]
    assert entry["class"] is None
    assert "clamp(…)" in entry["evidence"]
    body = entry["consolidated_body"]
    tree = ast.parse(body)
    fn = tree.body[0]
    assert fn.name == "test_clamp"
    assert [a.arg for a in fn.args.args] == ["arg", "expected"]
    assert "(-5, 0)," in body and "(9, 3)," in body and "(2, 2)," in body
    assert "ids=['low', 'high', 'mid']" in body
    assert ast.unparse(fn.body[0]) == "assert clamp(arg, 0, 3) == expected"


def test_parametrize_cluster_body_runs_under_pytest(tmp_path):
    root = project(tmp_path, {"test_cl.py": CLUSTER})
    [entry] = scan(root, ["src"], ["tests"])["parametrizations"]
    (root / "tests" / "test_new.py").write_text(
        "import pytest\nfrom pkg.calc import clamp\n\n\n" + entry["consolidated_body"])
    res = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          "tests/test_new.py"], cwd=root, capture_output=True, text=True,
                         env={"PYTHONPATH": str(root / "src"), "PATH": "/usr/bin:/bin"})
    assert "3 passed" in res.stdout, res.stdout + res.stderr


def test_parametrize_cluster_in_class_uses_class_names(tmp_path):
    out = run(tmp_path, {"test_cl.py": '''
        from pkg.calc import clamp

        class TestClamp:
            def test_one(self):
                assert clamp(1, 0, 3) == 1

            def test_two(self):
                assert clamp(2, 0, 3) == 2

            def test_three(self):
                assert clamp(3, 0, 3) == 3
    '''})
    [entry] = out["parametrizations"]
    assert entry["class"] == "TestClamp"
    assert entry["tests"] == ["TestClamp::test_one", "TestClamp::test_two", "TestClamp::test_three"]
    # no shared name prefix beyond `test`: named after the source function
    assert entry["consolidated_name"] == "TestClamp::test_clamp"
    fn = ast.parse(entry["consolidated_body"]).body[0]
    assert [a.arg for a in fn.args.args] == ["self", "arg", "expected"]


@pytest.mark.parametrize("pair, expected", [
    (("test_parse_1", "test_parse_2"), True),
    (("test_parse_a", "test_parse_b"), True),
    (("test_parse_equity", "test_parse_future"), False),
], ids=["digits", "letters", "words"])
def test_parametrize_pair_needs_suffix_names(tmp_path, pair, expected):
    a, b = pair
    out = run(tmp_path, {"test_pair.py": f'''
        from pkg.calc import clamp

        def {a}():
            assert clamp(1, 0, 3) == 1

        def {b}():
            assert clamp(2, 0, 3) == 2
    '''})
    got = [e["criterion"] for e in out["parametrizations"]]
    assert got == (["parametrize-pair"] if expected else [])
    if expected:
        assert out["parametrizations"][0]["consolidated_name"] == "test_parse"


@pytest.mark.parametrize("tests, reason", [
    # mixed types at one position
    (["assert clamp(1, 0, 3) == 1", "assert clamp(2.0, 0, 3) == 2", "assert clamp(3, 0, 3) == 3"],
     "differing constants of mixed types"),
    # differing mock configuration
    (["m = Mock(return_value=1)\n    assert clamp(m(), 0, 3) == 1",
      "m = Mock(return_value=2)\n    assert clamp(m(), 0, 3) == 1",
      "m = Mock(return_value=3)\n    assert clamp(m(), 0, 3) == 1"],
     "differing mock configuration"),
    # comments in body
    (["assert clamp(1, 0, 3) == 1  # one", "assert clamp(2, 0, 3) == 2", "assert clamp(3, 0, 3) == 3"],
     "comments in body would be lost by AST regeneration"),
], ids=["mixed-types", "mock-config", "comments"])
def test_parametrize_cluster_unanalyzable(tmp_path, tests, reason):
    text = "from unittest.mock import Mock\nfrom pkg.calc import clamp\n\n"
    for i, t in enumerate(tests):
        text += f"def test_c_{i}x():\n    {t}\n\n"
    out = run(tmp_path, {"test_un.py": text})
    assert out["parametrizations"] == []
    [entry] = out["unanalyzable"]
    assert entry["reason"] == reason
    assert entry["file"] == "tests/test_un.py"


def test_parametrize_cluster_skips_docstring_and_parametrized_and_fixture_differences(tmp_path):
    out = run(tmp_path, {"test_doc.py": '''
        import pytest
        from pkg.calc import clamp

        def test_a_1():
            """One."""
            assert clamp(1, 0, 3) == 1

        def test_a_2():
            """Two."""
            assert clamp(2, 0, 3) == 2

        @pytest.mark.parametrize("z", [1])
        def test_b_1(z):
            assert clamp(1, 0, 3) == 1

        @pytest.mark.parametrize("z", [1])
        def test_b_2(z):
            assert clamp(2, 0, 3) == 2

        def test_c_1(tmp_path):
            assert clamp(1, 0, 3) == 1

        def test_c_2():
            assert clamp(2, 0, 3) == 2
    '''})
    assert out["parametrizations"] == []
    reasons = sorted(e["reason"] for e in out["unanalyzable"])
    assert reasons == ["already parametrized", "docstrings differ; consolidation would drop them"]


def test_dead_and_duplicate_tests_never_join_a_cluster(tmp_path):
    out = run(tmp_path, {"test_mix.py": '''
        from pkg.calc import clamp

        def test_c_1():
            clamp(1, 0, 3)

        def test_c_2():
            clamp(2, 0, 3)

        def test_c_3():
            clamp(3, 0, 3)
    '''})
    assert out["parametrizations"] == []
    assert len(names(out["review_candidates"], "dead-test")) == 3


def test_unparsable_file_is_unanalyzable(tmp_path):
    out = run(tmp_path, {"test_bad.py": "def test_x(:\n    pass\n"})
    [entry] = out["unanalyzable"]
    assert entry["file"] == "tests/test_bad.py"
    assert entry["reason"].startswith("SyntaxError")


# --- plan-v2 shapes and CLI -----------------------------------------------

REMOVAL_KEYS = {"file", "test_name", "criterion", "evidence"}
REVIEW_KEYS = {"file", "test_name", "criterion", "evidence"}
PARAM_KEYS = {"file", "tests", "consolidated_name", "consolidated_body", "required_imports",
              "criterion", "evidence"}


def test_output_matches_plan_v2_shapes(tmp_path):
    out = run(tmp_path, {"test_all.py": CLUSTER + '''
    def test_dead():
        clamp(1, 2, 3)

    def test_true():
        assert True

    def test_clamp_low_copy():
        assert clamp(-5, 0, 3) == 0
    '''})
    assert set(out) == {"removals", "review_candidates", "parametrizations", "unanalyzable"}
    for e in out["removals"]:
        assert REMOVAL_KEYS <= set(e)
        assert e["criterion"] in ("exact-duplicate", "trivially-true")
        if e["criterion"] == "exact-duplicate":
            assert e["duplicate_of"] == "test_clamp_low"
    for e in out["review_candidates"]:
        assert REVIEW_KEYS | {"kind"} <= set(e)
    for e in out["parametrizations"]:
        assert PARAM_KEYS <= set(e)
        assert isinstance(e["consolidated_body"], str) and ast.parse(e["consolidated_body"])
    json.dumps(out)


def test_cli_repeatable_source_root_and_tests_flags(tmp_path):
    root = project(tmp_path, {"test_one.py": CLUSTER})
    (root / "lib").mkdir()
    (root / "lib" / "other.py").write_text("def pick(x):\n    return x\n")
    (root / "more").mkdir()
    (root / "more" / "test_two.py").write_text(textwrap.dedent('''
        from other import pick

        def test_a():
            pick(1)
    '''))
    res = subprocess.run([sys.executable, str(HELPERS / "scan_static.py"), "--root", str(root),
                          "--source-root", "src", "--source-root", "lib",
                          "--tests", "tests", "--tests", "more/test_two.py"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert [e["file"] for e in out["parametrizations"]] == ["tests/test_one.py"]
    assert [e["file"] for e in out["review_candidates"]] == ["more/test_two.py"]


def test_cli_tests_flag_does_not_take_two_values(tmp_path):
    root = project(tmp_path, {"test_one.py": CLUSTER})
    res = subprocess.run([sys.executable, str(HELPERS / "scan_static.py"), "--root", str(root),
                          "--source-root", "src", "--tests", "tests", "more"],
                         capture_output=True, text=True)
    assert res.returncode == 2
    assert "unrecognized arguments" in res.stderr


def test_parametrize_cluster_skips_default_argument_signatures(tmp_path):
    out = run(tmp_path, {"test_def.py": '''
        from pkg.calc import clamp

        def test_a1(x=0):
            assert clamp(1, 0, 3) == 1

        def test_a2(x=0):
            assert clamp(2, 0, 3) == 2
    '''})
    assert out["parametrizations"] == []
    assert [e["reason"] for e in out["unanalyzable"]] == [
        "signature has *args, **kwargs, keyword-only arguments or default values"]
