"""Seam tests for the refactor-tests seam helper (propose, classify).

Run: uv run --with pytest pytest reference/python/tests/test_seams.py
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parent.parent  # conftest.py puts this on sys.path

from classify_seams import classify, propose  # after conftest path setup

TEXT = '''__all__ = ["slugify"]


def slugify(s):
    return "-".join(_tokenize(s))


def _tokenize(s):
    return s.lower().split()


def shout(s):
    return s.upper()
'''

CALC = '''def add(a, b):
    return a + b


def _scale(a):
    return a * 2


class Acc:
    def push(self, x):
        return x

    def _drain(self):
        return None


class _Hidden:
    def run(self):
        return 1
'''

MAIN = '''from pkg.text import shout, _tokenize


def main(s):
    return shout(s)
'''

SIBLING = '''from .text import slugify


def twice(s):
    return slugify(s) * 2
'''

TESTS = '''from unittest.mock import patch

import pkg.text
from pkg.text import slugify, _tokenize
from pkg.calc import add, Acc


def test_slugify():
    assert slugify("A b") == "a-b"


def test_tokenize_directly():
    assert _tokenize("A b") == ["a", "b"]


def test_patched_internal():
    with patch("pkg.text._tokenize", return_value=["x"]):
        assert slugify("q") == "x"


def test_attribute_internal():
    assert pkg.text._tokenize("A") == ["a"]


def test_patch_object_internal():
    with patch.object(pkg.text, "_tokenize"):
        assert slugify("q")


def test_class_public_method():
    assert Acc().push(1) == 1


def test_class_private_method():
    assert Acc._drain(Acc()) is None


def test_add_via_inner_import():
    from pkg.calc import add as plus
    assert plus(1, 2) == 3
'''


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    p = tmp_path_factory.mktemp("proj")
    for rel, text in {
        "src/pkg/__init__.py": "",
        "src/pkg/text.py": TEXT,
        "src/pkg/calc.py": CALC,
        "src/pkg/sibling.py": SIBLING,
        "src/app/__init__.py": "",
        "src/app/main.py": MAIN,
        "tests/test_all.py": TESTS,
    }.items():
        f = p / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    return p


def _names(doc, rel):
    return {s["name"]: s["signal"] for s in doc["modules"][rel]["seams"]}


def _confirmed(doc):
    return json.loads(json.dumps(doc).replace('"proposed"', '"confirmed"'))


def test_propose_uses_all_and_cross_package_imports_not_public_api_when_all_exists(proj):
    doc = propose(proj, ["src"])
    names = _names(doc, "src/pkg/text.py")
    # __all__ wins; shout is imported by package app; _tokenize is imported too but private
    assert names == {"slugify": "__all__", "shout": "cross-package-import"}
    assert all(s["status"] == "proposed" for m in doc["modules"].values() for s in m["seams"])


def test_propose_without_all_takes_public_functions_classes_and_methods(proj):
    names = _names(propose(proj, ["src"]), "src/pkg/calc.py")
    assert names == {"add": "public-api", "Acc": "public-api", "Acc.push": "public-api"}


def test_propose_never_proposes_underscore_names(proj):
    doc = propose(proj, ["src"])
    every = {s["name"] for m in doc["modules"].values() for s in m["seams"]}
    assert not any(part.startswith("_") for n in every for part in n.split("."))


def test_propose_ignores_same_package_imports(proj):
    # sibling.py imports slugify from the same package: not a cross-package signal,
    # and the module has no seams of its own beyond public-api
    doc = propose(proj, ["src"])
    assert _names(doc, "src/pkg/sibling.py") == {"twice": "public-api"}
    assert _names(doc, "src/pkg/text.py")["slugify"] == "__all__"


def _by_test(out):
    return {(r["test_name"], r["module"]): r for r in out["seams"]["pinning_candidates"]}


def test_classify_splits_interface_tests_from_pinning_candidates(proj):
    out = classify(proj, ["src"], _confirmed(propose(proj, ["src"])), ["tests/test_all.py"], evidence=None)
    interface = {(r["test_name"], r["module"]) for r in out["interface_tests"]}
    assert interface == {
        ("test_slugify", "src/pkg/text.py"),
        ("test_class_public_method", "src/pkg/calc.py"),
        ("test_add_via_inner_import", "src/pkg/calc.py"),
    }
    pins = _by_test(out)
    assert pins[("test_tokenize_directly", "src/pkg/text.py")]["internals"] == ["_tokenize"]
    assert pins[("test_patched_internal", "src/pkg/text.py")]["internals"] == ["_tokenize"]
    assert pins[("test_attribute_internal", "src/pkg/text.py")]["internals"] == ["_tokenize"]
    assert pins[("test_patch_object_internal", "src/pkg/text.py")]["internals"] == ["_tokenize"]
    assert pins[("test_class_private_method", "src/pkg/calc.py")]["internals"] == ["Acc._drain"]


def test_classify_without_evidence_omits_add_candidates_and_coverage_fields(proj):
    out = classify(proj, ["src"], _confirmed(propose(proj, ["src"])), ["tests/test_all.py"], evidence=None)
    assert "add_candidates" not in out["seams"]
    assert any("evidence status is not ok" in w for w in out["warnings"])
    for pin in out["seams"]["pinning_candidates"]:
        assert "covered_through_interface" not in pin
        assert pin["note"] == "move the assertion to the interface"


def test_classify_with_failed_evidence_behaves_like_missing(proj):
    out = classify(proj, ["src"], _confirmed(propose(proj, ["src"])), ["tests/test_all.py"],
                   evidence={"status": "failed", "tests": {}})
    assert "add_candidates" not in out["seams"]
    assert len(out["seams"]["pinning_candidates"]) == 5
    assert any("evidence status is not ok" in w for w in out["warnings"])
    assert all("covered_through_interface" not in p for p in out["seams"]["pinning_candidates"])


def _evidence():
    def cov(f, lines):
        return {"covered": {f: {"lines": lines, "arcs": []}}}

    t = "tests/test_all.py::"
    return {"status": "ok", "tests": {
        t + "test_slugify": cov("src/pkg/text.py", [5, 9]),
        t + "test_tokenize_directly": cov("src/pkg/text.py", [9]),
        t + "test_patched_internal": cov("src/pkg/text.py", [5, 9, 99]),
        t + "test_class_public_method": cov("src/pkg/calc.py", [11]),
        t + "test_add_via_inner_import[x]": cov("src/pkg/calc.py", [2]),
    }}


def test_classify_reports_add_candidates_for_seams_no_interface_test_reaches(proj):
    out = classify(proj, ["src"], _confirmed(propose(proj, ["src"])), ["tests/test_all.py"], _evidence())
    # slugify (line 5), add (line 2, via a parametrized id), Acc (push, line 11) are reached;
    # the rest have no interface test
    assert {(c["module"], c["seam"]) for c in out["seams"]["add_candidates"]} == {
        ("src/pkg/text.py", "shout"),
        ("src/pkg/sibling.py", "twice"),
        ("src/app/main.py", "main"),
    }


def test_add_candidates_ignore_pinning_tests_that_reach_the_seam(proj):
    ev = {"status": "ok", "tests": {
        # only a pinning test touches slugify: slugify is still an add candidate
        "tests/test_all.py::test_patched_internal": {"covered": {"src/pkg/text.py": {"lines": [5], "arcs": []}}},
    }}
    seams = _confirmed(propose(proj, ["src"]))
    out = classify(proj, ["src"], seams, ["tests/test_all.py"], ev)
    assert {"module": "src/pkg/text.py", "seam": "slugify"} in out["seams"]["add_candidates"]


def test_pinning_note_depends_on_interface_superset_coverage(proj):
    out = classify(proj, ["src"], _confirmed(propose(proj, ["src"])), ["tests/test_all.py"], _evidence())
    pins = _by_test(out)
    covered = pins[("test_tokenize_directly", "src/pkg/text.py")]
    assert covered["covered_through_interface"] is True
    assert covered["note"] == "covered through the interface"
    moved = pins[("test_patched_internal", "src/pkg/text.py")]
    assert moved["covered_through_interface"] is False  # line 99 not covered by the interface test
    assert moved["note"] == "move the assertion to the interface"


def test_unconfirmed_seams_classify_nothing(proj):
    out = classify(proj, ["src"], propose(proj, ["src"]), ["tests/test_all.py"], _evidence())
    assert out["seams"]["pinning_candidates"] == []
    assert out["interface_tests"] == []
    assert any("no confirmed seams" in w for w in out["warnings"])


def test_cli_propose_and_classify_round_trip(proj, tmp_path):
    run = lambda *a: subprocess.run([sys.executable, str(HELPERS / "classify_seams.py"), *a],
                                    capture_output=True, text=True, check=False)
    proposed = run("propose", "--root", str(proj), "--source-root", "src")
    assert proposed.returncode == 0, proposed.stderr
    seams_file = tmp_path / "seams.json"
    seams_file.write_text(proposed.stdout.replace('"proposed"', '"confirmed"'))
    out = run("classify", "--root", str(proj), "--source-root", "src", "--seams", str(seams_file),
              "--tests", "tests")
    assert out.returncode == 0, out.stderr
    doc = json.loads(out.stdout)
    assert len(doc["seams"]["pinning_candidates"]) == 5
    assert "add_candidates" not in doc["seams"]


def _proj_with(tmp_path, files):
    for rel, text in files.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    return tmp_path


def test_decorator_patch_of_an_internal_makes_a_pinning_candidate(tmp_path):
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "",
        "src/pkg/text.py": TEXT,
        "tests/test_dec.py": (
            "from unittest.mock import patch\nfrom pkg.text import slugify\n\n\n"
            "@patch('pkg.text._tokenize')\ndef test_dec(m):\n    assert slugify('q')\n\n\n"
            "@patch('pkg.text._tokenize')\nclass TestK:\n    def test_m(self, m):\n        assert slugify('q')\n"
        ),
    })
    out = classify(proj, ["src"], _confirmed(propose(proj, ["src"])), ["tests/test_dec.py"])
    assert {(r["test_name"], tuple(r["internals"])) for r in out["seams"]["pinning_candidates"]} == {
        ("test_dec", ("_tokenize",)),
        ("TestK::test_m", ("_tokenize",)),
    }
    assert out["interface_tests"] == []


def test_reexported_seam_is_not_an_add_candidate_and_warns(tmp_path):
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "from .text import slugify\n__all__ = ['slugify']\n",
        "src/pkg/text.py": TEXT,
        "tests/test_re.py": "from pkg import slugify\n\n\ndef test_re():\n    assert slugify('A')\n",
    })
    ev = {"status": "ok", "tests": {"tests/test_re.py::test_re": {"covered": {}}}}
    out = classify(proj, ["src"], _confirmed(propose(proj, ["src"])), ["tests/test_re.py"], ev)
    assert out["seams"]["add_candidates"] == [] or all(
        c["module"] != "src/pkg/__init__.py" for c in out["seams"]["add_candidates"]
    )
    assert any("re-export or constant" in w for w in out["warnings"])


def test_pinning_test_missing_from_evidence_is_not_covered_through_interface(proj):
    ev = {"status": "ok", "tests": {
        "tests/test_all.py::test_slugify": {"covered": {"src/pkg/text.py": {"lines": [5, 9], "arcs": []}}},
    }}
    out = classify(proj, ["src"], _confirmed(propose(proj, ["src"])), ["tests/test_all.py"], ev)
    pin = _by_test(out)[("test_tokenize_directly", "src/pkg/text.py")]
    assert pin["covered_through_interface"] is False
    assert pin["note"] == "move the assertion to the interface"
    assert any("no coverage in evidence" in w for w in out["warnings"])


def test_all_listing_an_underscore_name_never_proposes_it(tmp_path):
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "",
        "src/pkg/m.py": "__all__ = ['pub', '_priv']\n\n\ndef pub():\n    return 1\n\n\ndef _priv():\n    return 2\n",
    })
    assert _names(propose(proj, ["src"]), "src/pkg/m.py") == {"pub": "__all__"}


def test_only_confirmed_seams_count_when_statuses_mix(proj):
    doc = propose(proj, ["src"])
    for s in doc["modules"]["src/pkg/text.py"]["seams"]:
        s["status"] = "confirmed" if s["name"] == "slugify" else "proposed"
    out = classify(proj, ["src"], doc, ["tests/test_all.py"], _evidence())
    assert set(out["seams"]["modules"]) == {"src/pkg/text.py"}
    assert [s["name"] for s in out["seams"]["modules"]["src/pkg/text.py"]["seams"]] == ["slugify"]
    assert out["seams"]["add_candidates"] == []
