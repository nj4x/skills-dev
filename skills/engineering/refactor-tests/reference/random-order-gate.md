# refactor-tests reference: Random-order gate

Split from `patterns.md`, which holds the other schemas and conventions.

Step 8b of `SKILL.md`. Helper: `reference/python/order_gate.py` (`plugin`, `classify`, `demote`). The gate compares JUnit ids (`classname::name`, as in `patterns.md` → Per-runner output formats); `classify` converts node-id baselines (`path.py::Class::name`, the ledger and `baseline-ids.json` form) to that form first.

**Plugin choice.** pytest-random-order already importable in the runner's environment: use it with `--random-order-bucket=global --random-order-seed=<seed>`, plus `-p no:randomly` when pytest-randomly is importable too. Otherwise: pytest-randomly with `--randomly-seed=<seed>`, installed only for the gate run when it is not already present, and with the recorded `-p no:randomly` dropped. One shuffler per run, never two. Every other run of the skill stays in fixed order (Step 3).

**Classification**, against the gate baseline (ledger `simplification.post_layout_baseline`, or the Step 3 baseline when it is absent: `--phases=B`, or a `--dry-run` that moved nothing):

| Baseline | Gate run | Same-seed re-run | Result |
|---|---|---|---|
| not passing | any | — | excluded, listed as a baseline failure |
| passing | passed or skipped | — | no label |
| passing | failed or error | failed, error, skipped, or absent | `order-dependent` |
| passing | failed or error | passed | `flaky` |

The baseline is `simplification.post_layout_baseline`, or the Step 3 baseline when that is absent. A baseline that gives a pass count instead of passing ids (the ledger shape) counts every id not in its `failed` list as passing. A baseline that lists passing ids marks any other id `not-in-baseline` and excludes it.

**`order-gate.json`** (`classify` output, kept in `.scratch/refactor-tests/`):

```json
{
  "seed": 1234567,
  "order_dependent": ["tests.protrading.adapters.test_instruments::test_parse_cached"],
  "flaky": [],
  "excluded": [ { "id": "tests.protrading.test_slow::test_x", "baseline": "failed" } ],
  "candidates": ["tests.protrading.adapters.test_instruments::test_parse_cached"],
  "rerun_required": false
}
```

**Ledger `order_gate`**: `{ status: ok|skipped|failed, reason, plugin, seed, order_dependent: [ids], flaky: [ids] }`. `reason` is `null` with `ok`, else one line. `status: ok` is written only after `demote` exits 0. `demote` exit 2 with stderr starting `order_gate demote:` (`rerun_required` refusal) is not a helper failure; any other exit 2 is: no status is written until the same-seed re-run is classified and `demote` exits 0; a re-run that cannot complete gives `failed` with reason `rerun_required: <why>`. Any other non-zero `demote` exit gives `failed`. Resume reuses a recorded status and never runs the suite again.

**Demotion.** A planned change involves a flagged test when the test's file and base name (parameter suffix dropped on both sides) match an id; when both the id and the plan entry name a class, the class must agree. A class-less side matches any class: a plan `test_name` of `test_x` matches a flagged `Cls::test_x`, and a flagged top-level `test_x` matches a plan `Cls::test_x`. This differs on purpose from `calltime_delta.py`, where a bare id names a top-level test only. The two errors cost different things. A missed demotion lets Step 9 delete or merge an order-dependent test, while a needless demotion only adds a `review_candidates` entry, so the gate errs toward demoting. A wrong `call_s` charge misstates the reported saving, so call time errs toward charging nothing. `demote` refuses a gate result with `rerun_required: true` (exit 2, plan unchanged): its candidates carry no label until the same-seed re-run is classified. The tests a change involves: a removal's `test_name`; for an exact-duplicate removal also its kept test in `duplicate_of`; every name in a parametrization's `tests`. A change that involves an `order-dependent` or `flaky` test leaves `removals` or `parametrizations` whole. It goes to `review_candidates` as one entry per involved test and per criterion: `{ file, test_name, criterion: "order-dependent"|"flaky", evidence, seed, failing_ids }`, where `failing_ids` holds the flagged ids that this change involves.
