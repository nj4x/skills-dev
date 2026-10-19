"""Seam tests for the refactor-tests seam helper (propose, classify).

Run: uv run --with pytest pytest reference/python/tests/test_seams.py
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from classify_seams import classify, propose  # conftest.py puts HELPERS on sys.path

HELPERS = Path(__file__).resolve().parent.parent

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
    assert covered["note"] == "lines covered by one interface test (assertions not compared)"
    moved = pins[("test_patched_internal", "src/pkg/text.py")]
    assert moved["covered_through_interface"] is False  # line 99 not covered by the interface test
    assert moved["note"] == "move the assertion to the interface"


def test_unconfirmed_seams_classify_nothing(proj):
    out = classify(proj, ["src"], propose(proj, ["src"]), ["tests/test_all.py"], _evidence())
    assert out["seams"]["pinning_candidates"] == []
    assert out["interface_tests"] == []
    assert any("no confirmed seams" in w for w in out["warnings"])


def test_cli_propose_and_classify_round_trip(proj, tmp_path):
    def run(*a):
        return subprocess.run([sys.executable, str(HELPERS / "classify_seams.py"), *a],
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
    assert ("src/pkg/__init__.py", "slugify") not in {
        (c["module"], c["seam"]) for c in out["seams"]["add_candidates"]
    }
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


def test_relative_import_beyond_the_top_package_resolves_to_nothing(tmp_path):
    proj = _proj_with(tmp_path, {
        "src/a/__init__.py": "",
        "src/a/b.py": "from ..x import y\n",
        "src/x.py": "def y():\n    return 1\n",
    })
    assert _names(propose(proj, ["src"]), "src/x.py") == {"y": "public-api"}


def test_object_form_monkeypatch_setattr_of_an_internal_makes_a_pinning_candidate(tmp_path):
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "",
        "src/pkg/text.py": TEXT,
        "tests/test_mp.py": (
            "import pkg.text\nfrom pkg.text import slugify\n\n\n"
            "def test_mp(monkeypatch):\n"
            "    monkeypatch.setattr(pkg.text, '_tokenize', lambda s: ['x'])\n"
            "    assert slugify('q') == 'x'\n"
        ),
    })
    out = classify(proj, ["src"], _confirmed(propose(proj, ["src"])), ["tests/test_mp.py"])
    assert [(r["test_name"], r["internals"]) for r in out["seams"]["pinning_candidates"]] == [("test_mp", ["_tokenize"])]
    assert out["interface_tests"] == []


def test_add_candidate_reexported_by_an_imported_package_init_warns(tmp_path):
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "from .text import slugify\n",
        "src/pkg/text.py": TEXT,
        "tests/test_re.py": "from pkg import slugify\n\n\ndef test_re():\n    assert slugify('A')\n",
    })
    ev = {"status": "ok", "tests": {"tests/test_re.py::test_re": {"covered": {"src/pkg/text.py": {"lines": [5]}}}}}
    out = classify(proj, ["src"], _confirmed(propose(proj, ["src"])), ["tests/test_re.py"], ev)
    assert {"module": "src/pkg/text.py", "seam": "slugify"} in out["seams"]["add_candidates"]
    assert any("slugify" in w and "re-exported by src/pkg/__init__.py" in w for w in out["warnings"])


@pytest.mark.parametrize("src", [
    "import other\n__all__ = ['pub'] + other.__all__\n",
    "__all__ = ['pub']\n__all__ += _extra()\n",
])
def test_computed_all_is_not_read_as_no_all(tmp_path, src):
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "",
        "src/pkg/m.py": src + "\n\ndef pub():\n    return 1\n\n\ndef other_pub():\n    return 2\n",
    })
    doc = propose(proj, ["src"])
    assert _names(doc, "src/pkg/m.py") == {"pub": "__all__"}
    assert any("src/pkg/m.py" in w and "__all__" in w for w in doc["warnings"])


def test_all_built_from_literal_concatenation_and_augmented_assignment_is_evaluated(tmp_path):
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "",
        "src/pkg/m.py": "__all__ = ['a'] + ['b']\n__all__ += ('c',)\n\n\ndef a():\n    return 1\n\n\ndef d():\n    return 2\n",
    })
    doc = propose(proj, ["src"])
    assert _names(doc, "src/pkg/m.py") == {"a": "__all__", "b": "__all__", "c": "__all__"}
    assert doc["warnings"] == []


@pytest.mark.parametrize("src", [
    "__all__ = ['pub', 'other_pub']\n__all__.remove('other_pub')\n",
    "__all__ = ['pub', 'other_pub']\ndel __all__[1]\n",
    "__all__ = ['pub']\n__all__[:] = ['other_pub']\n",
    "__all__ = ['pub']\n__all__.insert(0, 'other_pub')\n",
    "__all__ = ['pub']\nif True:\n    __all__.append('other_pub')\n",
    "__all__ = ['pub']\ntry:\n    __all__ += ['other_pub']\nexcept Exception:\n    pass\n",
    "try:\n    __all__ = ['pub']\nexcept Exception:\n    __all__ = []\n",
], ids=["remove", "del-item", "slice-assign", "insert", "nested-if", "nested-try", "assign-in-try"])
def test_mutated_or_nested_all_is_incomplete_and_never_falls_back_to_public_api(tmp_path, src):
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "",
        "src/pkg/m.py": src + "\n\ndef pub():\n    return 1\n\n\ndef other_pub():\n    return 2\n",
    })
    doc = propose(proj, ["src"])
    seams = doc["modules"].get("src/pkg/m.py", {"seams": []})["seams"]
    assert "public-api" not in {s["signal"] for s in seams}
    assert any("src/pkg/m.py" in w and "__all__" in w for w in doc["warnings"])


def test_reading_all_does_not_make_it_incomplete(tmp_path):
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "",
        "src/pkg/m.py": "__all__ = ['a']\nNAMES = list(__all__)\nfor _n in __all__:\n    pass\n\n\ndef a():\n    return 1\n",
    })
    doc = propose(proj, ["src"])
    assert _names(doc, "src/pkg/m.py") == {"a": "__all__"}
    assert doc["warnings"] == []


@pytest.mark.parametrize("src", [
    "def helper():\n    __all__ = ['x']\n    __all__.append('y')\n    return __all__\n",
    "class Box:\n    __all__ = ['x']\n",
    "__all__: list[str]\n",
], ids=["function-local", "class-level", "bare-annotation"])
def test_all_outside_module_scope_or_without_value_keeps_public_api(tmp_path, src):
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "",
        "src/pkg/m.py": src + "\n\ndef pub():\n    return 1\n",
    })
    doc = propose(proj, ["src"])
    assert _names(doc, "src/pkg/m.py")["pub"] == "public-api"
    assert doc["warnings"] == []


def test_add_candidate_reexported_through_two_package_levels_warns(tmp_path):
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "from .sub import slugify\n",
        "src/pkg/sub/__init__.py": "from .text import slugify\n",
        "src/pkg/sub/text.py": TEXT,
        "tests/test_re.py": "from pkg import slugify\n\n\ndef test_re():\n    assert slugify('A')\n",
    })
    ev = {"status": "ok", "tests": {"tests/test_re.py::test_re": {"covered": {"src/pkg/sub/text.py": {"lines": [5]}}}}}
    out = classify(proj, ["src"], _confirmed(propose(proj, ["src"])), ["tests/test_re.py"], ev)
    assert {"module": "src/pkg/sub/text.py", "seam": "slugify"} in out["seams"]["add_candidates"]
    assert any("slugify" in w and "re-exported by src/pkg/__init__.py" in w for w in out["warnings"])


# --- pinning kinds and test doubles (G5) -------------------------------------

SVC = '''__all__ = ["run", "report"]

import json
from pkg.cfg import load_config

TIMEOUT = 5


def run():
    return _helper(load_config(), json.dumps({}))


def _helper(c, s):
    return c


def report():
    return 1


def extra():
    return 2
'''

CFG = '''_cache = {}


def load_config():
    return _cache


def _reset():
    _cache.clear()
'''

KIND_TESTS = '''from unittest.mock import patch

import pkg.svc as svc
from pkg.svc import run


@patch("pkg.svc.load_config")
def test_double(m):
    assert run() is m.return_value


def test_patched_defined():
    with patch("pkg.svc._helper", return_value=1):
        assert run() == 1


def test_constant(monkeypatch):
    monkeypatch.setattr("pkg.svc.TIMEOUT", 0)
    assert run() is not None


def test_mixed(monkeypatch):
    monkeypatch.setattr(svc, "load_config", dict)
    with patch.object(svc, "TIMEOUT", 1):
        assert svc.extra() == 2


def test_double_and_constant():
    with patch("pkg.svc.load_config"), patch("pkg.svc.TIMEOUT", 0):
        assert run()


def test_imported_not_patched():
    assert svc.json.dumps({}) == "{}"


def test_two_modules():
    with patch("pkg.svc.load_config"), patch("pkg.cfg._cache", {}):
        assert run() is not None


def test_double_here_private_there():
    with patch("pkg.svc.load_config"), patch("pkg.cfg._reset"):
        assert run() is not None
'''


@pytest.fixture
def kinds_proj(tmp_path):
    return _proj_with(tmp_path, {
        "src/pkg/__init__.py": "",
        "src/pkg/svc.py": SVC,
        "src/pkg/cfg.py": CFG,
        "tests/test_kinds.py": KIND_TESTS,
    })


def test_module_table_tells_imported_names_from_defined_ones():
    import ast

    from classify_seams import module_table
    table = module_table(ast.parse(SVC + "try:\n    import yaml\nexcept ImportError:\n    yaml = None\n"
                                   "from os import path as run\n_f = lambda: 1\n"))
    assert table["json"] == table["load_config"] == "import"
    assert table["TIMEOUT"] == table["__all__"] == "constant"
    assert table["run"] == table["_helper"] == table["_f"] == "callable"  # defined beats a later import
    assert table["yaml"] == "constant"  # rebound in the module: not only an import


def test_patched_imported_collaborator_is_a_double_not_an_internal(kinds_proj):
    from classify_seams import NOTE_DOUBLE
    out = classify(kinds_proj, ["src"], _confirmed(propose(kinds_proj, ["src"])), ["tests/test_kinds.py"])
    rec = _by_test(out)[("test_double", "src/pkg/svc.py")]
    assert (rec["internals"], rec["doubles"], rec["kind"]) == ([], ["load_config"], "collaborator-double")
    assert rec["note"] == NOTE_DOUBLE


def test_pinning_kind_per_reference_and_strictest_wins(kinds_proj):
    out = classify(kinds_proj, ["src"], _confirmed(propose(kinds_proj, ["src"])), ["tests/test_kinds.py"])
    pins = _by_test(out)
    got = {name: (r["kind"], r["internals"], r["doubles"]) for (name, mod), r in pins.items() if mod == "src/pkg/svc.py"}
    assert got["test_patched_defined"] == ("private", ["_helper"], [])
    assert got["test_constant"] == ("constant", ["TIMEOUT"], [])
    assert got["test_mixed"] == ("public-non-seam", ["TIMEOUT", "extra"], ["load_config"])
    assert got["test_double_and_constant"] == ("collaborator-double", ["TIMEOUT"], ["load_config"])
    assert got["test_imported_not_patched"] == ("other", ["json.dumps"], [])
    assert all(r["note"] != "re-point the stub (deps injection or a checked patch); do not delete"
               for r in pins.values() if r["internals"])


def test_one_test_takes_its_strictest_kind_in_every_module(kinds_proj):
    out = classify(kinds_proj, ["src"], _confirmed(propose(kinds_proj, ["src"])), ["tests/test_kinds.py"])
    pins = _by_test(out)
    svc_rec, cfg_rec = pins[("test_two_modules", "src/pkg/svc.py")], pins[("test_two_modules", "src/pkg/cfg.py")]
    assert svc_rec["doubles"] == ["load_config"] and cfg_rec["internals"] == ["_cache"]
    assert svc_rec["kind"] == cfg_rec["kind"] == "collaborator-double"  # double is stricter than constant


def test_widened_double_record_does_not_say_do_not_delete(kinds_proj):
    from classify_seams import NOTE_DOUBLE
    out = classify(kinds_proj, ["src"], _confirmed(propose(kinds_proj, ["src"])), ["tests/test_kinds.py"])
    pins = _by_test(out)
    svc_rec = pins[("test_double_here_private_there", "src/pkg/svc.py")]
    cfg_rec = pins[("test_double_here_private_there", "src/pkg/cfg.py")]
    assert (svc_rec["internals"], svc_rec["doubles"]) == ([], ["load_config"])
    assert svc_rec["kind"] == cfg_rec["kind"] == "private"
    assert svc_rec["note"] != NOTE_DOUBLE  # a private ticket ends in delete


# --- seams-confirmed.json reuse (G6) -----------------------------------------

def _write_confirmed(proj, doc):
    path = proj / ".scratch/refactor-tests/seams-confirmed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc if isinstance(doc, str) else json.dumps(doc))
    return path


def test_reuse_drops_stale_names_and_modules_and_proposes_only_the_difference(kinds_proj):
    from classify_seams import reuse
    path = _write_confirmed(kinds_proj, {"modules": {
        "src/pkg/svc.py": {"seams": [
            {"name": "run", "signal": "__all__", "status": "confirmed"},
            {"name": "gone_fn", "signal": "__all__", "status": "confirmed"},
            {"name": "report", "signal": "__all__", "status": "rejected"},
            {"name": "TIMEOUT", "signal": "user", "status": "confirmed"},
            {"name": "extra", "signal": "public-api", "status": "confirmed"},
        ]},
        "src/pkg/old.py": {"seams": [{"name": "x", "signal": "__all__", "status": "confirmed"}]},
    }})
    out = reuse(kinds_proj, propose(kinds_proj, ["src"]), path)
    assert out["status"] == "ok"
    assert {s["name"]: s["status"] for s in out["modules"]["src/pkg/svc.py"]["seams"]} == {
        "run": "confirmed", "report": "rejected", "TIMEOUT": "confirmed", "extra": "confirmed"}
    assert "src/pkg/old.py" not in out["modules"]
    # `extra` was proposed once and is no longer; the user-added TIMEOUT never was, so it is no change
    assert out["diff"] == {"new_modules": ["src/pkg/cfg.py"], "added": {}, "removed": {"src/pkg/svc.py": ["extra"]}}
    assert out["review_modules"] == ["src/pkg/cfg.py", "src/pkg/svc.py"]
    assert out["public_api_modules"] == ["src/pkg/cfg.py"]
    assert any("gone_fn" in w and "dropped" in w for w in out["warnings"])
    assert any("src/pkg/old.py" in w and "dropped" in w for w in out["warnings"])


def test_reuse_adds_newly_proposed_names_as_proposed(kinds_proj):
    from classify_seams import reuse
    path = _write_confirmed(kinds_proj, {"modules": {
        "src/pkg/svc.py": {"seams": [{"name": "run", "signal": "__all__", "status": "confirmed"}]},
        "src/pkg/cfg.py": {"seams": [{"name": "load_config", "signal": "public-api", "status": "confirmed"}]},
    }})
    out = reuse(kinds_proj, propose(kinds_proj, ["src"]), path)
    assert out["diff"] == {"new_modules": [], "added": {"src/pkg/svc.py": ["report"]}, "removed": {}}
    assert out["review_modules"] == ["src/pkg/svc.py"] and out["public_api_modules"] == []
    assert out["warnings"] == []


def test_reuse_twice_with_no_source_change_reports_no_difference(kinds_proj):
    from classify_seams import reuse
    proposed = propose(kinds_proj, ["src"])
    path = _write_confirmed(kinds_proj, {"modules": {
        "src/pkg/svc.py": {"seams": [{"name": "run", "signal": "__all__", "status": "confirmed"},
                                     {"name": "report", "signal": "__all__", "status": "rejected"},
                                     {"name": "Acc", "signal": "user", "status": "confirmed"}]},
        "src/pkg/cfg.py": {"seams": [{"name": "load_config", "signal": "public-api", "status": "confirmed"}]},
    }})
    (kinds_proj / "src/pkg/svc.py").write_text(SVC + "\n\nclass Acc:\n    def push(self):\n        return 1\n")
    first = reuse(kinds_proj, proposed, path)
    _write_confirmed(kinds_proj, {"schema_version": 1, "modules": first["modules"]})
    second = reuse(kinds_proj, proposed, path)
    assert second["diff"] == {"new_modules": [], "added": {}, "removed": {}}
    assert second["review_modules"] == [] and second["warnings"] == []


def test_reuse_keeps_seams_of_a_star_import_module_and_counts_all_names_as_bound(tmp_path):
    from classify_seams import reuse
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "from .core import *\n",
        "src/pkg/core.py": "def run():\n    return 1\n",
        "src/pkg/api.py": '__all__ = ["late"]\n\n\ndef __dir__():\n    return __all__\n',
    })
    path = _write_confirmed(proj, {"modules": {
        "src/pkg/__init__.py": {"seams": [{"name": "run", "signal": "user", "status": "confirmed"}]},
        "src/pkg/api.py": {"seams": [{"name": "late", "signal": "__all__", "status": "confirmed"}]},
    }})
    out = reuse(proj, propose(proj, ["src"]), path)
    assert out["modules"]["src/pkg/__init__.py"]["seams"][0]["name"] == "run"
    assert out["modules"]["src/pkg/api.py"]["seams"][0]["name"] == "late"
    assert not any("dropped" in w for w in out["warnings"])
    assert any("src/pkg/__init__.py" in w and "kept unchecked" in w for w in out["warnings"])


@pytest.mark.parametrize("text", ["not json{", '{"modules": {"src/pkg/svc.py": '])
def test_reuse_ignores_a_corrupt_file_with_a_warning(kinds_proj, text):
    from classify_seams import reuse
    path = _write_confirmed(kinds_proj, text)
    proposed = propose(kinds_proj, ["src"])
    out = reuse(kinds_proj, proposed, path)
    assert out["status"] == "ignored"
    assert out["modules"] == proposed["modules"]
    assert out["diff"]["new_modules"] == sorted(proposed["modules"])
    assert len(out["warnings"]) == 1 and "ignored" in out["warnings"][0]


@pytest.mark.parametrize("doc", [
    [], {"mods": {}}, {"modules": []}, {"modules": {"src/pkg/svc.py": {"seams": "run"}}},
    {"modules": {"src/pkg/svc.py": {"seams": [{"name": 1, "status": "confirmed"}]}}},
    {"modules": {"src/pkg/svc.py": {"seams": [{"name": "run"}]}}},
])
def test_reuse_ignores_valid_json_with_the_wrong_schema(kinds_proj, doc):
    from classify_seams import reuse
    out = reuse(kinds_proj, propose(kinds_proj, ["src"]), _write_confirmed(kinds_proj, doc))
    assert out["status"] == "ignored"
    assert out["diff"]["new_modules"] == ["src/pkg/cfg.py", "src/pkg/svc.py"]
    assert len(out["warnings"]) == 1 and "ignored" in out["warnings"][0]


def test_reuse_without_a_file_proposes_everything(kinds_proj):
    from classify_seams import reuse
    out = reuse(kinds_proj, propose(kinds_proj, ["src"]), kinds_proj / ".scratch/refactor-tests/seams-confirmed.json")
    assert (out["status"], out["warnings"]) == ("absent", [])
    assert out["review_modules"] == ["src/pkg/cfg.py", "src/pkg/svc.py"]


def test_cli_reuse_reads_the_default_confirmed_path(kinds_proj, capsys):
    from classify_seams import main
    _write_confirmed(kinds_proj, {"modules": {"src/pkg/svc.py": {"seams": [
        {"name": "run", "signal": "__all__", "status": "confirmed"}]}}})
    (kinds_proj / "proposed.json").write_text(json.dumps(propose(kinds_proj, ["src"])))
    main(["reuse", "--root", str(kinds_proj), "--proposed", "proposed.json"])
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok" and out["diff"]["added"] == {"src/pkg/svc.py": ["report"]}


def test_double_of_a_boundary_import_is_boundary_double_and_of_project_logic_is_not(tmp_path):
    from classify_seams import NOTE_BOUNDARY, NOTE_DOUBLE
    proj = _proj_with(tmp_path, {
        "src/pkg/__init__.py": "",
        "src/pkg/svc.py": SVC,
        "src/pkg/cfg.py": CFG,
        "tests/test_bd.py": '''from unittest.mock import patch

from pkg.svc import run


def test_boundary():
    with patch("pkg.svc.json"):
        assert run() is not None


def test_own_logic():
    with patch("pkg.svc.load_config"):
        assert run() is not None


def test_boundary_and_own_logic():
    with patch("pkg.svc.json"), patch("pkg.svc.load_config"):
        assert run() is not None
''',
    })
    out = classify(proj, ["src"], _confirmed(propose(proj, ["src"])), ["tests/test_bd.py"])
    pins = _by_test(out)
    b = pins[("test_boundary", "src/pkg/svc.py")]
    assert (b["internals"], b["doubles"], b["kind"], b["note"]) == ([], ["json"], "boundary-double", NOTE_BOUNDARY)
    o = pins[("test_own_logic", "src/pkg/svc.py")]
    assert (o["doubles"], o["kind"], o["note"]) == (["load_config"], "collaborator-double", NOTE_DOUBLE)
    both = pins[("test_boundary_and_own_logic", "src/pkg/svc.py")]
    assert both["kind"] == "collaborator-double"  # own-logic double is stricter


def test_ref_kind_keeps_a_patched_constant_and_an_unpatched_import_out_of_boundary_double():
    from classify_seams import ref_kind
    assert ref_kind("TIMEOUT", {"TIMEOUT": "constant"}, True, {"json"}) == "constant"
    assert ref_kind("json", {"json": "import"}, False, {"json"}) == "other"


def test_boundary_names_treat_namespace_packages_and_rebinds_as_project(tmp_path):
    import ast

    from classify_seams import boundary_names, source_files
    proj = _proj_with(tmp_path, {"src/pkg/svc.py": "", "src/pkg/cfg.py": ""})  # pkg has no __init__.py
    files = source_files(proj, ["src"])
    tree = ast.parse(
        "import json\nimport pkg.cfg\nfrom pkg import cfg as c1\nfrom . import cfg as c2\n"
        "try:\n    import ujson as fast\nexcept ImportError:\n    from pkg.cfg import fast\n"
    )
    assert boundary_names(tree, "pkg.svc", False, files) == {"json"}


def test_project_subpackage_named_like_a_skipped_dir_is_not_a_boundary(tmp_path):
    import ast

    from classify_seams import boundary_names, source_files
    proj = _proj_with(tmp_path, {"src/pkg/__init__.py": "", "src/pkg/svc.py": "", "src/pkg/build/steps.py": ""})
    files = source_files(proj, ["src"])
    assert "pkg.build.steps" not in files  # `build` is a skipped directory name
    tree = ast.parse("import json\nfrom pkg.build import steps\nfrom pkg.build.steps import run\nimport pkg.build.steps as s\n")
    assert boundary_names(tree, "pkg.svc", False, files, proj, ["src"]) == {"json"}
