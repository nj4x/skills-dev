# refactor-tests reference: Seam classification (Python)

Split from `patterns.md`, which holds the other schemas and conventions.

Step 7b of `SKILL.md`. Helper: `reference/python/classify_seams.py` (`propose`, `reuse`, `classify`). The seam definition quoted in `SKILL.md` comes from `skills/engineering/tdd/SKILL.md` `## Seams — where tests go`; module, interface, seam, adapter come from `codebase-design`.

**Seam signals**, per source module, strongest first. A name takes the first signal that proposes it, and the proposal records that signal.

| Signal | Value | Proposes |
|---|---|---|
| (a) `__all__` | `__all__` | each public name listed in the module's `__all__` |
| (b) cross-package import | `cross-package-import` | a public function or class that a source file in another package of the project imports from this module (`from <module> import <name>`, relative imports resolved) |
| (c) public surface | `public-api` | only when the module has no `__all__`: public top-level functions and classes, and the public methods of those classes as `Class.method` |

Names with a leading underscore are never proposed. Test files and `conftest.py` are not source modules. `__all__` built from literal lists with `+`, `+=`, `.extend`, or `.append` is evaluated. A computed part (`[...] + other.__all__`) still means the module has an `__all__`: its literal names are proposed, signal (c) does not apply, and `propose` adds a `warnings` entry for the module. Any other change to `__all__` counts as computed the same way: `__all__.remove(...)`, `.insert(...)`, `.pop(...)` and the other list mutators, `del __all__[...]`, `__all__[:] = ...`, `-=`, and any assignment or mutation of `__all__` nested in a module-level `if`, `try`, `for`, `while`, or `with`. Only module scope is read: an `__all__` assigned or changed inside a function, lambda, or class body, and a value-less annotation `__all__: list[str]`, are ignored, so signal (c) still applies when the module has no other `__all__`. The ledger keeps these `propose` warnings in `seams.propose_warnings`. `seams.warnings` holds them followed by the `classify` warnings of the latest `classify` run: each run, a resume included, rebuilds it from `propose_warnings`, so `classify` warnings are never appended twice. The Final report lists `seams.warnings` whether or not a confirm round ran.

**Static classification**, per test and per source module, from the test's AST only. The test's references to that module are the names it imports and uses, attribute access on imported modules and classes, and `patch("pkg.mod.name")` (as a call or as a decorator on the test or its class), `patch.object(mod, "name")`, `monkeypatch.setattr("pkg.mod.name", ...)`, and `monkeypatch.setattr(mod, "name", ...)` targets. A reference is a seam when its name is a confirmed seam, or its first segment is a seam class and the remaining segments are public. A method call on an instance is not resolved.

- **Interface test**: at least one reference, and every reference is a seam.
- **Pinning candidate**: at least one reference is not a seam (`internals` lists them, e.g. `_tokenize`, or a mock patched at an internal path).
- One test can be an interface test for one module and a pinning candidate for another.

**Test doubles.** `classify` reads, per source module, which top-level names the module binds by an import and which it defines (`def`, `class`, or an assignment, also inside a module-level `if` or `try`; a name both imported and defined counts as defined). A `patch(...)`, `patch.object(...)`, or `monkeypatch.setattr(...)` target that names an imported name is a **test double**: the test replaces a collaborator, not the module's own code. It is listed under `doubles`, not `internals`. A test whose only non-seam references in a module are doubles is an interface test with doubles: it stays a pinning candidate with `kind: collaborator-double` and the note "re-point the stub (deps injection or a checked patch); do not delete". When the double's name is imported from outside the project's source files (third-party or stdlib, a system boundary), the kind is `boundary-double` instead, with the note "double of a system boundary: keep, no deletion"; project ports that wrap a boundary count as project modules and stay `collaborator-double`. A module counts as outside the project when a dotted segment is `vendor`, `vendored`, `_vendor`, or `_vendored` (matched whole), including a vendored package with an `__init__.py` and every module under it; a first-party `vendor.py` or `vendored.py` file stays project. A subpackage named `build` below the first segment, absent from the source files, is project; a top-level `build`, `vendor`, `node_modules`, and `.venv` are not. No static signal marks a port, so a patched port keeps the ticket; inject the port instead of patching it (`tdd/mocking.md`: inject first). When the same test takes a stricter kind in another module, every record of it carries that kind and the move or covered note instead. (`codebase-design` has no term for this; it names an in-memory fake or a mock adapter, which a test double may be.)

**Pinning kinds.** Each non-seam reference has a kind, and each pinning candidate carries `kind`:

| `kind` | Reference | Workflow |
|---|---|---|
| `public-non-seam` | A public name defined in the module that is not a confirmed seam. | A human seam decision: confirm it as a seam, or move the test to one. |
| `private` | A `def`, `class`, or lambda name with a leading-underscore part (`_tokenize`, `Acc._drain`). | Merge the assertion into the closest existing interface test as parametrized cases, keep the original, run the mutation check (`SKILL.md` → Follow-up: mutation deletion gate (optional)), then delete. |
| `collaborator-double` | A patch target bound by an import (a test double). | Re-point the stub: deps injection or a checked patch. Do not delete. |
| `boundary-double` | A patch target bound by an import from outside the project's source files (third-party or stdlib: a system boundary). | Keep the double; do not delete. Check the patch is injected or checked. |
| `constant` | A module-level name bound by an assignment, not a `def`, `class`, or lambda, with or without a leading underscore (`TIMEOUT`, `_cache`). | Re-point the stub. |
| `other` | Anything else, for example an imported name the test uses without patching it. | Look by hand. |

When a test has several kinds, it follows the strictest: `public-non-seam` > `private` > `collaborator-double` > `constant` > `boundary-double` > `other`. `kind` is the strictest over every non-seam reference of the test, in every module, so all entries of one test carry the same kind and the test is grouped under it. Writing one new interface test per pinning test is not the goal.

**Coverage against the interface** (needs evidence status `ok`). A seam's body lines are the lines of its body statements (decorators and the `def`/`class` header excluded: the header runs at import, outside any `|run` context). A seam is **reached** when an interface test's `covered` lines for the module intersect its body lines; parametrized ids merge by their base id. A confirmed seam no interface test reaches is an **add candidate**; pinning tests never count. A seam whose name has no function or class body in its module (a re-export or a constant in `__all__`) is never an add candidate; the report warns. A test that imports a name through a package `__init__` re-export (`from pkg import run`, where `pkg/__init__.py` has `from .mod import run`) is linked to the `__init__`, not to `mod.py`, so it is not an interface test of `mod.py` and its coverage does not count toward reaching `mod.py`'s seam. When such a seam is an add candidate, the helper adds a warning that the candidate needs a check by hand. Re-exports are followed through every package level: when `pkg/sub/__init__.py` re-exports `run` from `.mod` and `pkg/__init__.py` re-exports it from `.sub`, a test importing `from pkg import run` is linked to `pkg/__init__.py` the same way: it does not reach the seam in `pkg/sub/mod.py`, and that add candidate gets the warning. A pinning candidate has `covered_through_interface: true` when some interface test of the same module covers a superset of its lines in that module (a pinning test with no coverage in the evidence gets `false`, with a warning); the note is then "lines covered by one interface test (assertions not compared)", otherwise "move the assertion to the interface". With evidence status other than `ok`, `add_candidates` and `covered_through_interface` are omitted (keys absent) and the note is "move the assertion to the interface".

**`seams` object** in `simplification-plan.json` (only confirmed seams are listed; under `--dry-run` or unattended runs with no readable `seams-confirmed.json`, seams stay `proposed` in the ledger and the plan carries no `pinning_candidates`):

```json
"seams": {
  "modules": {
    "src/protrading/adapters/instruments.py": {
      "seams": [ { "name": "parse_instrument", "signal": "__all__", "status": "confirmed" } ]
    }
  },
  "add_candidates": [ { "module": "src/protrading/adapters/instruments.py", "seam": "parse_instrument" } ],
  "pinning_candidates": [
    {
      "file": "tests/protrading/adapters/test_instruments.py",
      "test_name": "test_tokenize_directly",
      "module": "src/protrading/adapters/instruments.py",
      "internals": ["_tokenize"],
      "doubles": ["load_config"],
      "kind": "private",
      "covered_through_interface": true,
      "note": "lines covered by one interface test (assertions not compared)"
    }
  ]
}
```

Each pinning candidate also goes to `review_candidates` as `{ file, test_name, criterion: "pinning", kind, evidence, note }`.

**Seam sidecars**, all under `.scratch/refactor-tests/`:

| File | Written by | Holds |
|---|---|---|
| `seams-proposed.json` | Step 7b item 1 | the `propose` output of this run |
| `seams-classified.json` | Step 7b item 3 | the `classify` output of this run |
| `seams-confirmed.json` | Step 7b item 2, when a round confirms | `{ schema_version: 1, modules }` in the `propose` shape; each seam has `status: confirmed`, or `rejected` for a name the user removed |

Step 1 never archives `seams-confirmed.json`: it carries the confirmed seams from run to run. A `--dry-run` never writes it.

**Reuse across runs.** `classify_seams.py reuse --root P --proposed .scratch/refactor-tests/seams-proposed.json` reads `seams-confirmed.json` (`--confirmed` overrides the path) and prints `{ status, modules, diff: { new_modules, added, removed }, review_modules, public_api_modules, warnings }`:

- `status` is `ok`, `absent` (no file), or `ignored`. A file that cannot be read, is not JSON, or has the wrong shape (no `modules` key, `modules` not an object, or a module without a `seams` list of entries with string `name` and `status`) is `ignored` with a warning; the run then behaves as with no file.
- `modules` keeps each earlier seam with its status and adds this run's new proposals as `proposed`. A rejected name is not proposed again.
- A confirmed module whose file no longer exists, or a seam name its module no longer binds (top-level name or `Class.method`), is dropped with a warning naming it. A module that cannot be parsed, or that has a star import or a module `__getattr__`, keeps its seams unchecked, with a warning. Literal `__all__` names count as bound.
- `diff`: `new_modules` (not in the file), `added` (newly proposed names per module), `removed` (confirmed names this run no longer proposes, except `signal: user` names, which were never proposed; they stay confirmed until the user removes them).
- `review_modules` are the new or changed modules: the only ones the confirm round shows. `public_api_modules` are those of them with a `public-api` proposal, the weakest signal.
