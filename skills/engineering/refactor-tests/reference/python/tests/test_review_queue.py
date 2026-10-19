"""Seam tests for render_review_queue.py (ADR-0079): the review queue, ticket drafts, and cross-run index.

Run: uv run --with pytest pytest reference/python/tests
"""
import json

import pytest

from render_review_queue import main, slugify  # conftest.py puts HELPERS on sys.path

STARTED = "2026-10-16T19-26-00"
SLUG = "refactor-tests-review-2026-10-16t19-26-00"
A = "tests/pkg/adapters/test_instruments.py"


def _plan(review=(), adds=()):
    return {"schema_version": 2, "review_candidates": list(review),
            "seams": {"add_candidates": list(adds)}}


def _cand(test_name, criterion, file=A, **extra):
    return {"file": file, "test_name": test_name, "criterion": criterion, "evidence": "line one\nline two\nline three", **extra}


def _setup(tmp_path, plan, ledger=None):
    ledger = {"started_at": STARTED, "moves": [], "id_map": {}, **(ledger or {})}
    (tmp_path / "ledger.json").write_text(json.dumps(ledger))
    (tmp_path / "plan.json").write_text(json.dumps(plan))


def _render(tmp_path, capsys, *extra):
    main(["render", "--project-root", str(tmp_path), "--ledger", str(tmp_path / "ledger.json"),
          "--plan", str(tmp_path / "plan.json"), "--project-name", "demo", *extra])
    return json.loads(capsys.readouterr().out)


def _record(tmp_path, capsys, *extra):
    main(["record", "--project-root", str(tmp_path), "--slug", SLUG, *extra])
    return json.loads(capsys.readouterr().out)


def test_slug_matches_the_to_tickets_rule_for_the_run_title(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]))
    out = _render(tmp_path, capsys)
    assert out["slug"] == SLUG == slugify(out["title"])


def test_one_ticket_per_criterion_and_module_with_labels(tmp_path, capsys):
    plan = _plan(
        [_cand("test_a", "dead-test"), _cand("test_b", "dead-test"),
         _cand("test_c", "coverage-subset", call_s=1.2, time_saved_s=1.2),
         _cand("test_d", "dead-test", file="tests/pkg/core/test_core.py")],
        [{"module": "src/pkg/core.py", "seam": "run"}],
    )
    _setup(tmp_path, plan)
    tickets = _render(tmp_path, capsys)["tickets"]
    assert [(t["title"], t["label"]) for t in tickets] == [
        ("Review 1 coverage-subset test in tests/pkg/adapters", "ready-for-human"),
        ("Review 2 dead-test tests in tests/pkg/adapters", "ready-for-human"),
        ("Review 1 dead-test test in tests/pkg/core", "ready-for-human"),
        ("Add interface tests for 1 untested seam in src/pkg/core.py", "ready-for-agent"),
    ]


def test_group_over_25_ids_splits_into_numbered_parts(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand(f"test_{i:02d}", "pinning") for i in range(30)]))
    tickets = _render(tmp_path, capsys)["tickets"]
    assert [t["ids"] for t in tickets] == [25, 5]
    assert tickets[0]["title"].endswith("(part 1 of 2)")


def test_fix_ticket_comes_first_and_blocks_only_overlapping_review_tickets(tmp_path, capsys):
    plan = _plan([
        _cand("Cls::test_a", "order-dependent", seed=7, failing_ids=["tests.pkg.adapters.test_instruments.Cls::test_a"]),
        _cand("Cls::test_a", "pinning"),
        _cand("test_other", "pinning", file="tests/pkg/core/test_core.py"),
    ])
    _setup(tmp_path, plan)
    tickets = _render(tmp_path, capsys)["tickets"]
    fix, overlapping, other = tickets
    assert fix["label"] == "ready-for-agent" and fix["title"].startswith("Fix 1 order-dependent test")
    assert "(seed 7)" in fix["title"]
    assert overlapping["blocked_by"] == [f"01-{fix['slug']}"]
    assert other["blocked_by"] == []


def test_skipped_parametrizations_per_module_and_spring_clusters_per_cluster(tmp_path, capsys):
    ledger = {
        "simplification": {"parametrizations": [
            {"file": A, "consolidated_name": "test_p", "tests": ["test_p1", "test_p2"], "skipped": "AST edit failed"},
            {"file": A, "consolidated_name": "test_q", "replaced": ["test_q1"]},
        ]},
        "spring": {"skipped_clusters": [
            {"cluster": "WebMvcTest+PaymentClient", "classes": ["ATest", "BTest"], "reason": "differing types"}]},
    }
    _setup(tmp_path, _plan(), ledger)
    tickets = _render(tmp_path, capsys)["tickets"]
    assert [(t["title"], t["label"]) for t in tickets] == [
        ("Merge 1 skipped parametrization in tests/pkg/adapters by hand", "ready-for-human"),
        ("Consolidate skipped Spring cluster WebMvcTest+PaymentClient by hand", "ready-for-human"),
    ]


def test_stage_writes_to_tickets_shaped_artifacts(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]))
    out = _render(tmp_path, capsys, "--stage")
    base = tmp_path / ".scratch" / SLUG
    manifest = (base / "manifest.md").read_text()
    assert manifest.startswith("---\nartifact-type: tickets\n---\n")
    rel = manifest.splitlines()[3]
    ticket = (tmp_path / rel).read_text()
    assert "label: ready-for-human" in ticket and f"**Spec**: {SLUG}" in ticket
    assert "## Status\nready-for-human" in ticket and "- [ ] " in ticket
    assert "line three" not in ticket  # evidence excerpt keeps at most two lines
    spec = (base / "spec.md").read_text()
    assert spec.startswith(f"# refactor-tests review {STARTED}\n\nProject: demo\n")
    assert "## Proposed tickets" in spec
    assert out["staged"] is True


def test_queue_always_written_and_stopped_run_never_stages(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]))
    out = _render(tmp_path, capsys, "--stage", "--stopped-at", "failed-simplify")
    queue = (tmp_path / ".scratch/refactor-tests/review-queue.md").read_text()
    assert "Run stopped at failed-simplify; candidates may be stale." in queue
    assert out["staged"] is False and not (tmp_path / ".scratch" / SLUG).exists()


def test_zero_items_stages_nothing(tmp_path, capsys):
    _setup(tmp_path, _plan())
    out = _render(tmp_path, capsys, "--stage")
    assert out["tickets"] == [] and out["staged"] is False
    assert "No human-action items." in (tmp_path / ".scratch/refactor-tests/review-queue.md").read_text()


def test_record_indexes_published_tickets_and_next_run_skips_them_after_a_move(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test"), _cand("test_b", "pinning")]))
    tickets = _render(tmp_path, capsys, "--stage")["tickets"]
    first = f"{tickets[0]['nn']}-{tickets[0]['slug']}"
    out = _record(tmp_path, capsys, "--ref", f"{first}=#41")
    assert out["status"] == "partial" and out["unpublished"] == [f"review|pinning|{A}::test_b"]
    index = json.loads((tmp_path / ".scratch/refactor-tests/review-index.json").read_text())
    assert list(index["entries"].values()) == [{"ref": "#41", "slug": SLUG}]

    moved = "tests/pkg/adapters/sub/test_instruments.py"
    _setup(tmp_path, _plan([_cand("test_a", "dead-test", file=moved), _cand("test_b", "pinning", file=moved)]),
           {"started_at": "2026-10-17T08-00-00", "moves": [{"from": A, "to": moved}]})
    out = _render(tmp_path, capsys)
    assert out["already_tracked"] == [{"key": f"review|dead-test|{moved}::test_a", "ref": "#41"}]
    assert [t["title"] for t in out["tickets"]] == ["Review 1 pinning test in tests/pkg/adapters/sub"]
    assert out["superseded"] == []


def test_record_reads_rewritten_manifest_and_promoted_local_issues(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test"), _cand("test_b", "pinning")]))
    t1, t2 = _render(tmp_path, capsys, "--stage")["tickets"]
    base = tmp_path / ".scratch" / SLUG
    (base / "manifest.md").write_text(f"---\nartifact-type: tickets\n---\n#90 {t1['nn']}-{t1['slug']}\n")
    (base / "issues").mkdir()
    name2 = f"{t2['nn']}-{t2['slug']}.md"
    (base / "draft-issues" / name2).rename(base / "issues" / name2)
    out = _record(tmp_path, capsys)
    assert out["status"] == "published"
    assert [t["ref"] for t in out["tickets"]] == ["#90", f".scratch/{SLUG}/issues/{t2['nn']}-{t2['slug']}.md"]


def test_unpublished_earlier_slug_is_reported_as_superseded(tmp_path, capsys):
    old = tmp_path / ".scratch" / "refactor-tests-review-2026-10-15t10-00-00" / "draft-issues"
    old.mkdir(parents=True)
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]))
    out = _render(tmp_path, capsys)
    assert out["superseded"] == ["refactor-tests-review-2026-10-15t10-00-00"]


def test_index_ids_map_through_the_ledger_id_map(tmp_path, capsys):
    index = {"schema_version": 1, "entries": {f"review|dead-test|{A}::test_old": {"ref": "#5", "slug": "x"}}}
    (tmp_path / ".scratch/refactor-tests").mkdir(parents=True)
    (tmp_path / ".scratch/refactor-tests/review-index.json").write_text(json.dumps(index))
    _setup(tmp_path, _plan([_cand("test_new", "dead-test")]), {"id_map": {f"{A}::test_old": f"{A}::test_new"}})
    out = _render(tmp_path, capsys)
    assert out["already_tracked"] == [{"key": f"review|dead-test|{A}::test_new", "ref": "#5"}]
    assert out["tickets"] == []


def test_record_credits_items_by_body_after_to_tickets_renames_and_merges(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test"), _cand("test_b", "pinning")]))
    _render(tmp_path, capsys, "--stage")
    base = tmp_path / ".scratch" / SLUG
    merged = "".join(p.read_text() for p in sorted((base / "draft-issues").glob("*.md")))
    for p in (base / "draft-issues").glob("*.md"):
        p.unlink()
    (base / "draft-issues" / "01-review-flagged-tests.md").write_text(merged)
    (base / "manifest.md").write_text("---\nartifact-type: tickets\n---\n#77 01-review-flagged-tests\n")
    out = _record(tmp_path, capsys)
    assert out["status"] == "published" and out["unpublished"] == []
    assert out["tickets"] == [{"ref": "#77", "keys": [f"review|dead-test|{A}::test_a", f"review|pinning|{A}::test_b"]}]


def test_record_with_nothing_published_is_drafted_and_writes_no_entries(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]))
    _render(tmp_path, capsys, "--stage")
    out = _record(tmp_path, capsys)
    assert out["status"] == "drafted" and out["tickets"] == []
    index = json.loads((tmp_path / ".scratch/refactor-tests/review-index.json").read_text())
    assert index["entries"] == {}


def test_duplicate_items_collapse_and_missing_seed_is_omitted(tmp_path, capsys):
    plan = _plan([_cand("test_kept", "flaky", failing_ids=["x"]), _cand("test_kept", "flaky", failing_ids=["x"])])
    _setup(tmp_path, plan)
    (ticket,) = _render(tmp_path, capsys)["tickets"]
    assert ticket["ids"] == 1 and ticket["title"] == "Fix 1 flaky test in tests/pkg/adapters"


def test_record_credits_by_full_key_when_one_test_has_two_criteria(tmp_path, capsys):
    plan = _plan([_cand("Cls::test_a", "order-dependent", seed=7), _cand("Cls::test_a", "pinning")])
    _setup(tmp_path, plan)
    fix, _review = _render(tmp_path, capsys, "--stage")["tickets"]
    base = tmp_path / ".scratch" / SLUG
    (base / "manifest.md").write_text(f"---\nartifact-type: tickets\n---\n#10 {fix['nn']}-{fix['slug']}\n")
    out = _record(tmp_path, capsys)
    assert out["status"] == "partial"
    assert out["tickets"] == [{"ref": "#10", "keys": [f"fix|order-dependent|{A}::Cls::test_a"]}]
    assert out["unpublished"] == [f"review|pinning|{A}::Cls::test_a"]


def test_moved_test_stays_tracked_on_the_run_after_the_move(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]))
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    _record(tmp_path, capsys, "--ref", f"{ticket['nn']}-{ticket['slug']}.md=#41")
    moved = "tests/pkg/adapters/sub/test_instruments.py"
    _setup(tmp_path, _plan([_cand("test_a", "dead-test", file=moved)]),
           {"started_at": "2026-10-17T08-00-00", "moves": [{"from": A, "to": moved}]})
    assert _render(tmp_path, capsys)["tickets"] == []
    _setup(tmp_path, _plan([_cand("test_a", "dead-test", file=moved)]), {"started_at": "2026-10-18T08-00-00"})
    out = _render(tmp_path, capsys)
    assert out["tickets"] == [] and out["already_tracked"][0]["ref"] == "#41"


def test_layout_regression_does_not_rekey_the_index(tmp_path, capsys):
    index = {"schema_version": 1, "entries": {f"review|dead-test|{A}::test_a": {"ref": "#5", "slug": "x"}}}
    (tmp_path / ".scratch/refactor-tests").mkdir(parents=True)
    (tmp_path / ".scratch/refactor-tests/review-index.json").write_text(json.dumps(index))
    _setup(tmp_path, _plan(), {"moves": [{"from": A, "to": "tests/other.py"}]})
    _render(tmp_path, capsys, "--stopped-at", "failed-layout")
    assert json.loads((tmp_path / ".scratch/refactor-tests/review-index.json").read_text()) == index


def test_relative_paths_resolve_against_project_root(tmp_path, capsys, monkeypatch):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]))
    monkeypatch.chdir("/")
    main(["render", "--project-root", str(tmp_path), "--ledger", "ledger.json", "--plan", "plan.json"])
    assert json.loads(capsys.readouterr().out)["items"] == 1


def test_record_reads_three_digit_names_and_reports_unmatched(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]))
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    base = tmp_path / ".scratch" / SLUG
    draft = base / "draft-issues" / f"{ticket['nn']}-{ticket['slug']}.md"
    draft.rename(base / "draft-issues" / f"100-{ticket['slug']}.md")
    (base / "manifest.md").write_text(f"---\nartifact-type: tickets\n---\n#9 100-{ticket['slug']}.md\n#8 07-gone\n")
    out = _record(tmp_path, capsys)
    assert out["status"] == "published" and out["tickets"][0]["ref"] == "#9"
    assert out["unmatched"] == ["07-gone"]


def _index(tmp_path, entries):
    (tmp_path / ".scratch/refactor-tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".scratch/refactor-tests/review-index.json").write_text(
        json.dumps({"schema_version": 1, "entries": entries}))


def _read_index(tmp_path):
    return json.loads((tmp_path / ".scratch/refactor-tests/review-index.json").read_text())["entries"]


def test_rekey_only_rekeys_without_writing_the_queue(tmp_path, capsys):
    _index(tmp_path, {f"review|dead-test|{A}::test_a": {"ref": "#5", "slug": "x"}})
    _setup(tmp_path, _plan(), {"moves": [{"from": A, "to": "tests/new.py"}]})
    main(["render", "--project-root", str(tmp_path), "--ledger", "ledger.json", "--rekey-only"])
    assert json.loads(capsys.readouterr().out) == {"rekeyed": True, "summary": ".scratch/refactor-tests/run-summary.json"}
    assert list(_read_index(tmp_path)) == ["review|dead-test|tests/new.py::test_a"]
    assert not (tmp_path / ".scratch/refactor-tests/review-queue.md").exists()


def test_later_gate_regression_still_rekeys_phase_a_moves(tmp_path, capsys):
    _index(tmp_path, {f"review|dead-test|{A}::test_a": {"ref": "#5", "slug": "x"}})
    _setup(tmp_path, _plan(), {"moves": [{"from": A, "to": "tests/new.py"}]})
    _render(tmp_path, capsys, "--stopped-at", "failed-simplify")
    assert list(_read_index(tmp_path)) == ["review|dead-test|tests/new.py::test_a"]


def test_queue_spec_and_fix_body_carry_tracked_items_seed_and_failing_ids(tmp_path, capsys):
    _index(tmp_path, {f"review|pinning|{A}::test_p": {"ref": "#3", "slug": "x"}})
    old = tmp_path / ".scratch" / "refactor-tests-review-2026-10-15t10-00-00" / "draft-issues"
    old.mkdir(parents=True)
    fid = "tests.pkg.adapters.test_instruments::test_f"
    _setup(tmp_path, _plan([_cand("test_p", "pinning"), _cand("test_f", "flaky", seed=99, failing_ids=[fid])]))
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    queue = (tmp_path / ".scratch/refactor-tests/review-queue.md").read_text()
    assert f"## Already tracked\n\n- `review|pinning|{A}::test_p` — #3" in queue
    assert "## Superseded drafts" in queue and "refactor-tests-review-2026-10-15t10-00-00" in queue
    base = tmp_path / ".scratch" / SLUG
    assert "## Already tracked" in (base / "spec.md").read_text()
    body = (base / "draft-issues" / f"{ticket['nn']}-{ticket['slug']}.md").read_text()
    assert f"failing_ids: `{fid}`" in body and "with seed 99" in body


def test_rekey_only_after_a_layout_regression_leaves_the_index_alone(tmp_path, capsys):
    entries = {f"review|dead-test|{A}::test_a": {"ref": "#5", "slug": "x"}}
    _index(tmp_path, entries)
    _setup(tmp_path, _plan(), {"moves": [{"from": A, "to": "tests/new.py"}]})
    main(["render", "--project-root", str(tmp_path), "--ledger", "ledger.json", "--rekey-only",
          "--stopped-at", "failed-layout"])
    assert json.loads(capsys.readouterr().out) == {"rekeyed": False, "summary": ".scratch/refactor-tests/run-summary.json"}
    assert _read_index(tmp_path) == entries


def test_hand_edited_index_entries_do_not_abort_the_run(tmp_path, capsys):
    _index(tmp_path, {"junk": {"ref": "#1"}, f"review|dead-test|{A}::test_a": {"slug": "x"}})
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]))
    out = _render(tmp_path, capsys)
    assert out["already_tracked"] == [{"key": f"review|dead-test|{A}::test_a", "ref": "?"}]


def test_review_text_is_criterion_specific_and_coverage_criteria_do_not_offer_bare_remove():
    from render_review_queue import WHAT
    for crit in ("coverage-subset", "cost", "pinning"):
        text = WHAT["review"][crit]
        assert "keep, rewrite at the interface, or remove" not in text
        assert "Follow-up: mutation deletion gate (optional)" in text
        assert "Coverage shows execution, not assertion strength" in text
    assert "Follow-up: mutation deletion gate" not in WHAT["review"]["dead-test"]


def _draft(tmp_path, ticket):
    return (tmp_path / ".scratch" / SLUG / "draft-issues" / f"{ticket['nn']}-{ticket['slug']}.md").read_text()


def test_staged_review_ticket_uses_its_criterion_text(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_s", "coverage-subset")]))
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    assert "Follow-up: mutation deletion gate (optional)" in _draft(tmp_path, ticket)


def test_fix_ticket_carries_reproduce_line_with_seed_and_plugin(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_f", "flaky", seed=99)]),
           {"runners": {"python": "pytest"}, "order_gate": {"plugin": "pytest-randomly", "seed": 99}})
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    assert f"uv run --with pytest-randomly pytest -p randomly --randomly-seed=99 {A}" in _draft(tmp_path, ticket)


def test_fix_ticket_reproduce_line_for_random_order_plugin_needs_no_install(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_f", "order-dependent", seed=7)]),
           {"order_gate": {"plugin": "pytest-random-order", "seed": 7}})
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    assert f"pytest --random-order-bucket=global --random-order-seed=7 {A}" in _draft(tmp_path, ticket)


def test_reproduce_line_replaces_recorded_no_randomly_flag_and_does_not_nest_uv(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_f", "flaky", seed=99)]),
           {"runners": {"python": "uv run pytest -p no:randomly"}, "order_gate": {"plugin": "pytest-randomly", "seed": 99}})
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    assert f"uv run --with pytest-randomly pytest -p randomly --randomly-seed=99 {A}" in _draft(tmp_path, ticket)
    assert "no:randomly" not in _draft(tmp_path, ticket)


@pytest.mark.parametrize("flag", ["-pno:randomly", "-p=no:randomly"])
def test_reproduce_line_drops_joined_no_randomly_forms(tmp_path, capsys, flag):
    _setup(tmp_path, _plan([_cand("test_f", "flaky", seed=99)]),
           {"runners": {"python": f"uv run pytest {flag}"}, "order_gate": {"plugin": "pytest-randomly", "seed": 99}})
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    assert f"uv run --with pytest-randomly pytest -p randomly --randomly-seed=99 {A}" in _draft(tmp_path, ticket)
    assert "no:randomly" not in _draft(tmp_path, ticket)


def test_reproduce_line_installs_for_a_venv_launcher_and_omits_line_without_seed(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_f", "flaky", seed=5), _cand("test_g", "order-dependent")]),
           {"runners": {"python": ".venv/bin/python -m pytest"}, "order_gate": {"plugin": "pytest-randomly"}})
    tickets = _render(tmp_path, capsys, "--stage")["tickets"]
    bodies = [_draft(tmp_path, t) for t in tickets]
    with_seed = [b for b in bodies if "--randomly-seed=5" in b]
    assert len(with_seed) == 1
    assert (".scratch/refactor-tests/pytest-randomly pytest-randomly && PYTHONPATH=.scratch/refactor-tests/pytest-randomly"
            f"${{PYTHONPATH:+:$PYTHONPATH}} .venv/bin/python -m pytest -p randomly --randomly-seed=5 {A}") in with_seed[0]
    assert "uv run" not in with_seed[0]
    assert all("Reproduce:" not in b for b in bodies if b is not with_seed[0])


def test_no_raise_contract_is_counted_never_ticketed_and_kind_shows_in_the_item_line(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_valid", "dead-test", kind="no-raise-contract"),
                            _cand("test_soft", "dead-test", kind="fail-soft")]))
    out = _render(tmp_path, capsys, "--stage")
    assert out["items"] == 1
    assert out["report_only"] == {"dead-test/no-raise-contract": 1}
    (ticket,) = out["tickets"]
    body = _draft(tmp_path, ticket)
    assert "test_valid" not in body
    assert f"`{A}::test_soft` — kind: fail-soft — " in body
    assert "test_valid" not in (tmp_path / ".scratch/refactor-tests/review-queue.md").read_text()


def test_dead_test_and_pinning_group_by_kind_and_collaborator_double_is_for_an_agent(tmp_path, capsys):
    _setup(tmp_path, _plan([
        _cand("test_a", "dead-test", kind="fail-soft"), _cand("test_b", "dead-test", kind="never-fails"),
        _cand("test_c", "dead-test", kind="fail-soft"),
        _cand("test_d", "pinning", kind="collaborator-double"), _cand("test_e", "pinning", kind="private"),
        _cand("test_f", "pinning"),
    ]))
    tickets = _render(tmp_path, capsys)["tickets"]
    assert [(t["title"], t["label"], t["ids"]) for t in tickets] == [
        ("Review 2 dead-test tests (fail-soft) in tests/pkg/adapters", "ready-for-human", 2),
        ("Review 1 dead-test test (never-fails) in tests/pkg/adapters", "ready-for-human", 1),
        ("Review 1 pinning test in tests/pkg/adapters", "ready-for-human", 1),
        ("Review 1 pinning test (collaborator-double) in tests/pkg/adapters", "ready-for-agent", 1),
        ("Review 1 pinning test (private) in tests/pkg/adapters", "ready-for-human", 1),
    ]


def test_review_text_follows_the_kind():
    from render_review_queue import WHAT, review_what
    double = review_what("pinning", "collaborator-double")
    assert "Re-point the stub (deps injection or a checked patch); do not delete." in double
    assert "Remove a test only when a mutation check" not in double
    for kind in ("private", "constant", "public-non-seam", "other", None):
        assert review_what("pinning", kind) == WHAT["review"]["pinning"]
    assert "Add an assertion on the log or the return value" in review_what("dead-test", "fail-soft")
    assert "Replace the skip with an assertion, or remove the test." in review_what("dead-test", "never-fails")
    assert review_what("dead-test", None) == review_what("dead-test", "no-assertion") == WHAT["review"]["dead-test"]
    assert "keep, rewrite at the interface, or remove" not in WHAT["review"]["dead-test"]


def test_staged_collaborator_double_ticket_says_do_not_delete(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_d", "pinning", kind="collaborator-double")]))
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    body = _draft(tmp_path, ticket)
    assert "do not delete" in body
    assert "Remove a test only when a mutation check of its module shows no lost kill" not in body
    assert "label: ready-for-agent" in body and "## Status\nready-for-agent" in body


def test_items_with_any_kind_or_none_pass_through(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_a", "cost", kind="hotspot-blocked", call_s=1.0),
                            _cand("test_b", "dead-test", kind=["odd"]),
                            _cand("test_c", "pinning", kind=7),
                            _cand("test_d", "coverage-subset")]))
    out = _render(tmp_path, capsys, "--stage")
    assert out["items"] == 4 and out["report_only"] == {}
    titles = [t["title"] for t in out["tickets"]]
    assert "Review 1 cost test in tests/pkg/adapters" in titles  # kind does not split other criteria
    assert "Review 1 dead-test test in tests/pkg/adapters" in titles  # a non-string kind does not split
    queue = (tmp_path / ".scratch/refactor-tests/review-queue.md").read_text()
    assert "kind: hotspot-blocked" in queue and "kind: ['odd']" in queue and "kind: 7" in queue


def test_unknown_string_kind_splits_dead_test_and_keeps_the_criterion_text(tmp_path, capsys):
    from render_review_queue import WHAT
    _setup(tmp_path, _plan([_cand("test_a", "dead-test", kind="weird"), _cand("test_b", "dead-test")]))
    tickets = _render(tmp_path, capsys, "--stage")["tickets"]
    assert [t["title"] for t in tickets] == ["Review 1 dead-test test in tests/pkg/adapters",
                                             "Review 1 dead-test test (weird) in tests/pkg/adapters"]
    assert WHAT["review"]["dead-test"] in _draft(tmp_path, tickets[1])


def _hotspot(function="src/pkg/db.py:connect", tests=(f"{A}::test_slow",), **extra):
    spawns = {t: 3 for t in tests}
    return {"criterion": "hotspot", "function": function, "share": 0.84, "tests": list(tests),
            "subprocess_spawns": spawns, "via": ["subprocess.py:run"], **extra}


def test_hotspot_is_for_an_agent_and_numbered_after_fix_and_before_review_tickets(tmp_path, capsys):
    from render_review_queue import LABELS, WHAT
    assert LABELS["hotspot"] == "ready-for-agent"
    assert "Fix this in the test tier (a fixture or stub), never by deleting tests." in WHAT["hotspot"]
    assert "Re-run the evidence pass after the fix, because `call_s` order changes." in WHAT["hotspot"]
    _setup(tmp_path, _plan([_cand("test_c", "cost", call_s=2.0), _cand("Cls::test_f", "flaky", seed=3),
                            _hotspot(), _cand("test_s", "coverage-subset", call_s=2.0)],
                           [{"module": "src/pkg/core.py", "seam": "run"}]))
    tickets = _render(tmp_path, capsys)["tickets"]
    assert [(t["nn"], t["title"].split(" ")[:2], t["label"]) for t in tickets] == [
        ("01", ["Fix", "1"], "ready-for-agent"),
        ("02", ["Fix", "cost"], "ready-for-agent"),
        ("03", ["Review", "1"], "ready-for-human"),
        ("04", ["Review", "1"], "ready-for-human"),
        ("05", ["Add", "interface"], "ready-for-agent"),
    ]
    assert tickets[1]["title"] == "Fix cost hotspot src/pkg/db.py:connect in the test tier"


def test_hotspot_blocks_only_cost_and_coverage_subset_tickets_in_its_test_directories(tmp_path, capsys):
    core = "tests/pkg/core/test_core.py"
    _setup(tmp_path, _plan([
        _hotspot(tests=(f"{A}::test_slow[1]", f"{A}::Cls::test_slower")),
        _cand("test_c", "cost", call_s=2.0), _cand("test_s", "coverage-subset", call_s=1.0),
        _cand("test_d", "dead-test"), _cand("test_p", "pinning"),
        _cand("test_c", "cost", file=core, call_s=2.0), _cand("test_s", "coverage-subset", file=core),
    ]))
    tickets = _render(tmp_path, capsys)["tickets"]
    hot = next(t for t in tickets if t["title"].startswith("Fix cost hotspot"))
    edge = f"{hot['nn']}-{hot['slug']}"
    blocked = {t["title"] for t in tickets if edge in t["blocked_by"]}
    assert blocked == {"Review 1 cost test in tests/pkg/adapters", "Review 1 coverage-subset test in tests/pkg/adapters"}


def test_hotspot_ticket_body_lists_share_tests_and_subprocess_spawns(tmp_path, capsys):
    from render_review_queue import WHAT
    tests = (f"{A}::test_a", "tests/pkg/core/test_core.py::test_b")
    _setup(tmp_path, _plan([_hotspot(tests=tests)]))
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    body = _draft(tmp_path, ticket)
    assert "label: ready-for-agent" in body and WHAT["hotspot"] in body
    assert f"subprocess_spawns: `{tests[0]}` 3, `{tests[1]}` 3" in body
    assert "share 0.84" in body and "via: `subprocess.py:run`" in body
    assert "key: `hotspot|hotspot|src/pkg/db.py:connect`" in body


def test_hotspot_entry_without_a_function_is_ignored(tmp_path, capsys):
    _setup(tmp_path, _plan([{"criterion": "hotspot", "share": 0.9}, _hotspot(function=7)]))
    assert _render(tmp_path, capsys)["tickets"] == []


# --- run summary, provenance and volume gate (G7, G8; ADR-0080) ---------------

SHA = "0123456789abcdef0123456789abcdef01234567"
EVIDENCE = ".scratch/refactor-tests/test-evidence.json"


def _evidence(tmp_path, status="ok", git_sha=SHA, tests=4):
    block = {"status": status, "tools": {}, "commands": {}, "excluded": [
        {"id": f"{A}::test_x", "outcome": "failed"}, {"id": f"{A}::test_y", "outcome": "no-timing"},
        {"id": f"{A}::test_z", "outcome": "failed"}],
        "tests": {f"{A}::t{i}": {"outcome": "passed", "call_s": 0.1, "covered": {}} for i in range(tests)}}
    if status != "ok":
        block.update(reason="pytest exit 3", tests={}, excluded=[])
    path = tmp_path / EVIDENCE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "id_basis": "post-layout", "git_sha": git_sha,
                                "dirty": False if git_sha else None, "languages": {"python": block}}))


def _summary(tmp_path):
    return json.loads((tmp_path / ".scratch/refactor-tests/run-summary.json").read_text())


HEALTHY_LEDGER = {
    "runners": {"python": "uv run pytest"},
    "order_gate": {"status": "ok", "plugin": "pytest-randomly", "seed": 1234},
    "simplification": {"call_time": {"before_s": 41.2, "after_s": 37.9}},
}


def test_run_summary_of_a_healthy_run(tmp_path, capsys):
    core = "tests/pkg/core/test_core.py"
    _setup(tmp_path, _plan([
        _cand("test_c", "coverage-subset", call_s=2.0), _cand("test_c", "cost", call_s=2.0),
        _cand("test_d", "coverage-subset", call_s=0.5), _cand("test_e", "coverage-subset", file=core, call_s=0.25),
        _cand("test_n", "dead-test", kind="no-raise-contract"), _cand("test_f", "dead-test", kind="fail-soft"),
        _hotspot(),
    ]), HEALTHY_LEDGER)
    _evidence(tmp_path)
    _render(tmp_path, capsys, "--stage")
    s = _summary(tmp_path)
    assert (s["started_at"], s["git_sha"], s["dirty"], s["seed"]) == (STARTED, SHA, False, 1234)
    assert s["runner"] == {"python": "uv run pytest"} and s["stopped_at"] is None
    assert s["counts"] == {"coverage-subset": 3, "cost": 1, "dead-test": 2, "hotspot": 1}
    assert s["kinds"] == {"dead-test/no-raise-contract": 1, "dead-test/fail-soft": 1}
    assert s["report_only"] == {"dead-test/no-raise-contract": 1}
    assert s["excluded"] == {"failed": 2, "no-timing": 1}
    assert s["concentration"]["by_candidates"][0] == {"module": "tests/pkg/adapters", "candidates": 4}  # no test_n
    assert s["concentration"]["by_call_s"] == [{"module": "tests/pkg/adapters", "call_s": 2.5},
                                               {"module": "tests/pkg/core", "call_s": 0.25}]  # test_c counted once
    assert [h["function"] for h in s["hotspots"]] == ["src/pkg/db.py:connect"]
    assert s["call_time"] == {"before_s": 41.2, "after_s": 37.9}
    assert s["evidence_tests"] == 4 and s["shares"]["coverage-subset"] == 0.75
    assert len(s["warnings"]) == 1 and s["warnings"][0].startswith("coverage-subset flags 75% of evidence tests")
    assert s["volume"]["tickets"] == 5 and s["volume"]["over"] is False


def test_run_summary_leaves_no_raise_contract_tests_out_of_shares_and_warnings(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand(f"test_n{i}", "dead-test", kind="no-raise-contract", call_s=1.0)
                            for i in range(3)]), HEALTHY_LEDGER)
    _evidence(tmp_path)  # 3 of 4 evidence tests flagged, all report-only
    _render(tmp_path, capsys, "--stage")
    s = _summary(tmp_path)
    assert s["counts"] == {"dead-test": 3} and s["kinds"] == {"dead-test/no-raise-contract": 3}
    assert s["report_only"] == {"dead-test/no-raise-contract": 3}
    assert s["shares"] == {} and s["warnings"] == []
    assert s["concentration"] == {"by_candidates": [], "by_call_s": []}


def test_run_summary_of_a_failed_layout_run_has_nulls_and_notes(tmp_path, capsys):
    _setup(tmp_path, _plan(), {"runners": {"python": "pytest"}})
    (tmp_path / "plan.json").unlink()  # Phase B never ran
    out = _render(tmp_path, capsys, "--stage", "--stopped-at", "failed-layout")
    assert out["staged"] is False
    s = _summary(tmp_path)
    assert s["stopped_at"] == "failed-layout" and s["started_at"] == STARTED
    for field in ("git_sha", "dirty", "seed", "counts", "kinds", "excluded", "shares", "concentration", "call_time"):
        assert s[field] is None, field
    assert s["hotspots"] == [] and s["warnings"] == []
    notes = " | ".join(s["notes"])
    assert "no evidence file" in notes and "no simplification plan" in notes and "seed is null" in notes


def test_run_summary_is_written_with_no_publish_review(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]), HEALTHY_LEDGER)
    _evidence(tmp_path, status="failed")
    main(["render", "--project-root", str(tmp_path), "--ledger", "ledger.json", "--rekey-only", "--plan", "plan.json"])
    assert json.loads(capsys.readouterr().out)["summary"] == ".scratch/refactor-tests/run-summary.json"
    assert not (tmp_path / ".scratch/refactor-tests/review-queue.md").exists()
    s = _summary(tmp_path)
    assert s["counts"] == {"dead-test": 1} and s["volume"] is None
    assert s["call_time"] is None and s["shares"] is None and s["warnings"] == []
    assert any("evidence is not ok (python: failed (pytest exit 3))" in n for n in s["notes"])


def test_ticket_body_carries_the_evidence_git_sha_and_matches_the_summary(tmp_path, capsys):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]))
    _evidence(tmp_path)
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    assert f"git_sha: {SHA} " in _draft(tmp_path, ticket)
    assert _summary(tmp_path)["git_sha"] == SHA
    assert f"git_sha: {SHA}" in (tmp_path / ".scratch" / SLUG / "spec.md").read_text()


@pytest.mark.parametrize("evidence", ["missing", "null"])
def test_ticket_body_says_git_sha_unknown_without_a_recorded_sha(tmp_path, capsys, evidence):
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]))
    if evidence == "null":
        _evidence(tmp_path, git_sha=None)
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    assert "git_sha: unknown " in _draft(tmp_path, ticket)
    assert _summary(tmp_path)["git_sha"] is None


def _many(n, criterion="dead-test"):
    """n review tickets of one criterion: one test in each of n test directories."""
    return [_cand("test_a", criterion, file=f"tests/m{i:03d}/test_x.py", call_s=1.0) for i in range(n)]


def test_volume_gate_counts_staged_tickets_including_hotspots(tmp_path, capsys):
    _setup(tmp_path, _plan(_many(50)))
    assert _render(tmp_path, capsys, "--tracker", "real")["volume"] == {
        "tickets": 50, "threshold": 50, "over": False, "action": "publish", "choice": None, "chosen_by": None}
    _setup(tmp_path, _plan([*_many(50), _hotspot()]))
    volume = _render(tmp_path, capsys, "--tracker", "real")["volume"]
    assert volume["tickets"] == 51 and volume["over"] is True and volume["action"] == "ask"


def test_volume_gate_counts_after_dedupe(tmp_path, capsys):
    _setup(tmp_path, _plan(_many(51)))
    _index(tmp_path, {"review|dead-test|tests/m000/test_x.py::test_a": {"ref": "#1", "slug": "s"}})
    assert _render(tmp_path, capsys, "--tracker", "local")["volume"]["tickets"] == 50


@pytest.mark.parametrize("tracker,action,triage", [("local", "triage", True), ("real", "drafted", False)])
def test_volume_gate_unattended_defaults(tmp_path, capsys, tracker, action, triage):
    _setup(tmp_path, _plan(_many(51)))
    out = _render(tmp_path, capsys, "--tracker", tracker, "--unattended", "--stage")
    assert out["volume"]["action"] == action and out["triage"] is triage
    assert len(out["tickets"]) == (1 if triage else 51)
    assert (out["volume"]["choice"], out["volume"]["chosen_by"]) == ("b" if triage else None, "unattended-default")
    assert _summary(tmp_path)["volume"] == out["volume"]


@pytest.mark.parametrize("choice,action,tickets", [("a", "publish", 51), ("b", "triage", 1), ("c", "declined", 51)])
def test_volume_gate_records_the_asked_choice(tmp_path, capsys, choice, action, tickets):
    _setup(tmp_path, _plan(_many(51)))
    assert _render(tmp_path, capsys, "--tracker", "real", "--stage")["volume"]["action"] == "ask"
    out = _render(tmp_path, capsys, "--tracker", "real", "--stage", "--choice", choice)
    assert out["volume"] == {"tickets": 51, "threshold": 50, "over": True,
                             "action": action, "choice": choice, "chosen_by": "asked"}
    assert out["triage"] is (choice == "b") and len(out["tickets"]) == tickets
    assert _summary(tmp_path)["volume"] == out["volume"]


@pytest.mark.parametrize("choice,action", [("a", "publish"), ("b", "triage"), ("c", "declined")])
def test_volume_gate_resume_with_a_recorded_choice_does_not_ask(tmp_path, capsys, choice, action):
    recorded = {"tickets": 51, "threshold": 50, "over": True, "action": action, "choice": choice, "chosen_by": "asked"}
    _setup(tmp_path, _plan(_many(51)), {"publish": {"status": "queued", "volume": recorded}})
    out = _render(tmp_path, capsys, "--tracker", "real", "--stage")
    assert out["volume"] == recorded and out["triage"] is (choice == "b")


def test_option_a_output_is_unchanged_by_the_gate(tmp_path, capsys):
    _setup(tmp_path, _plan([*_many(51), _hotspot()]))
    plain = _render(tmp_path, capsys, "--stage")
    drafts = {p.name: p.read_text() for p in (tmp_path / ".scratch" / SLUG / "draft-issues").iterdir()}
    gated = _render(tmp_path, capsys, "--stage", "--tracker", "real")
    assert plain["tickets"] == gated["tickets"] and plain["triage"] is gated["triage"] is False
    assert drafts == {p.name: p.read_text() for p in (tmp_path / ".scratch" / SLUG / "draft-issues").iterdir()}
    assert all("Triage" not in t["title"] for t in gated["tickets"])


def test_option_b_keeps_fix_hotspot_add_and_moves_edges_to_triage_tickets(tmp_path, capsys):
    ledger = {"simplification": {"parametrizations": [
        {"file": A, "consolidated_name": "test_p", "tests": ["test_p1"], "skipped": "AST edit failed"}]},
        "spring": {"skipped_clusters": [{"cluster": "WebMvcTest+X", "classes": ["ATest"], "reason": "r"}]}}
    plan = _plan([
        *_many(30, "cost"), *_many(30, "dead-test"),
        _hotspot(tests=("tests/m001/test_x.py::test_slow",)),
        _cand("test_a", "flaky", seed=3, file="tests/m002/test_x.py"),
    ], [{"module": "src/pkg/core.py", "seam": "run"}])
    _setup(tmp_path, plan, ledger)
    out = _render(tmp_path, capsys, "--stage", "--triage")
    titles = [t["title"] for t in out["tickets"]]
    assert titles == [
        "Fix 1 flaky test in tests/m002 (seed 3)",
        "Fix cost hotspot src/pkg/db.py:connect in the test tier",
        "Triage 30 cost tests from the review queue",
        "Triage 30 dead-test tests from the review queue",
        "Add interface tests for 1 untested seam in src/pkg/core.py",
    ]
    fix, hot, cost, dead, add = out["tickets"]
    assert add["blocked_by"] == [] and add["label"] == "ready-for-agent"
    assert cost["blocked_by"] == [f"{fix['nn']}-{fix['slug']}", f"{hot['nn']}-{hot['slug']}"]
    assert dead["blocked_by"] == [f"{fix['nn']}-{fix['slug']}"]  # a hotspot blocks only cost and coverage-subset
    assert cost["label"] == dead["label"] == "ready-for-human" and hot["label"] == "ready-for-agent"
    body = _draft(tmp_path, cost)
    assert "key:" not in body and "review-queue.md" in body and "run-summary.json" in body
    assert "- tests/m000: 1 test" in body
    assert "key: `hotspot|hotspot|src/pkg/db.py:connect`" in _draft(tmp_path, hot)
    keys = {t["nn"]: t["keys"] for t in json.loads((tmp_path / ".scratch" / SLUG / "tickets.json").read_text())["tickets"]}
    assert keys[cost["nn"]] == [] and keys[hot["nn"]] == ["hotspot|hotspot|src/pkg/db.py:connect"]
    queue = (tmp_path / ".scratch/refactor-tests/review-queue.md").read_text()
    assert "Merge 1 skipped parametrization" in queue and "Consolidate skipped Spring cluster" in queue
    assert "Review 1 cost test in tests/m000" in queue  # the queue file keeps every per-test ticket


def test_option_b_has_no_triage_ticket_for_a_criterion_without_tickets(tmp_path, capsys):
    _setup(tmp_path, _plan([*_many(51, "dead-test"), _hotspot(tests=("tests/m001/test_x.py::test_slow",))]))
    out = _render(tmp_path, capsys, "--stage", "--triage")
    assert [t["title"] for t in out["tickets"]] == [
        "Fix cost hotspot src/pkg/db.py:connect in the test tier", "Triage 51 dead-test tests from the review queue"]
    assert all(t["blocked_by"] == [] for t in out["tickets"])  # no cost/coverage-subset triage ticket: edge dropped


def test_option_c_publishes_nothing_and_still_writes_the_summary(tmp_path, capsys):
    _setup(tmp_path, _plan(_many(51)), HEALTHY_LEDGER)
    _evidence(tmp_path)
    assert _render(tmp_path, capsys, "--stage", "--tracker", "real")["volume"]["action"] == "ask"
    out = _render(tmp_path, capsys, "--stage", "--tracker", "real", "--choice", "c")
    assert (out["volume"]["action"], out["volume"]["choice"], out["volume"]["chosen_by"]) == ("declined", "c", "asked")
    assert out["triage"] is False
    assert (tmp_path / ".scratch/refactor-tests/review-queue.md").exists()
    assert _summary(tmp_path)["volume"] == out["volume"] and _summary(tmp_path)["volume"]["over"] is True
    # Step 11 records `declined` and calls neither to-tickets nor record: the drafts stay, nothing is published
    base = tmp_path / ".scratch" / SLUG
    assert (base / "manifest.md").read_text() == "---\nartifact-type: tickets\n---\n" + "".join(
        f".scratch/{SLUG}/draft-issues/{t['nn']}-{t['slug']}.md\n" for t in out["tickets"])  # no tracker ids
    assert not (tmp_path / ".scratch/refactor-tests/review-index.json").exists()
    assert not (base / "issues").exists()


# --- volume gate answers: who chose, explicit flags, resume (ADR-0080) ---------

def _volume(out):
    return out["volume"]["action"], out["volume"]["choice"], out["volume"]["chosen_by"]


def test_unattended_default_record_does_not_suppress_the_interactive_ask(tmp_path, capsys):
    recorded = {"tickets": 51, "threshold": 50, "over": True, "action": "triage", "choice": "b",
                "chosen_by": "unattended-default"}
    _setup(tmp_path, _plan(_many(51)), {"publish": {"status": "queued", "volume": recorded}})
    out = _render(tmp_path, capsys, "--tracker", "local", "--stage")
    assert _volume(out) == ("ask", None, None) and out["triage"] is False


def test_asked_record_is_not_overridden_by_the_unattended_default(tmp_path, capsys):
    recorded = {"tickets": 51, "threshold": 50, "over": True, "action": "publish", "choice": "a", "chosen_by": "asked"}
    _setup(tmp_path, _plan(_many(51)), {"publish": {"status": "queued", "volume": recorded}})
    out = _render(tmp_path, capsys, "--tracker", "local", "--unattended", "--stage")
    assert _volume(out) == ("publish", "a", "asked") and out["triage"] is False and len(out["tickets"]) == 51


@pytest.mark.parametrize("flag", [("--choice", "b"), ("--triage",)])
def test_explicit_answer_wins_over_the_unattended_real_tracker_default(tmp_path, capsys, flag):
    _setup(tmp_path, _plan(_many(51)))
    out = _render(tmp_path, capsys, "--tracker", "real", "--unattended", "--stage", *flag)
    assert _volume(out) == ("triage", "b", "asked") and out["triage"] is True and len(out["tickets"]) == 1


def test_triage_and_choice_are_mutually_exclusive(tmp_path, capsys):
    _setup(tmp_path, _plan(_many(3)))
    with pytest.raises(SystemExit):
        _render(tmp_path, capsys, "--tracker", "real", "--triage", "--choice", "a")
    assert "not allowed with argument" in capsys.readouterr().err


@pytest.mark.parametrize("choice,action,titles", [
    ("a", "publish", ["Review 1 dead-test test in tests/m000", "Review 1 dead-test test in tests/m001"]),
    ("b", "triage", ["Triage 2 dead-test tests from the review queue"]),
    ("c", "declined", ["Review 1 dead-test test in tests/m000", "Review 1 dead-test test in tests/m001"]),
])
def test_explicit_choice_at_50_tickets_or_fewer_applies_and_staging_matches(tmp_path, capsys, choice, action, titles):
    _setup(tmp_path, _plan(_many(2)))
    out = _render(tmp_path, capsys, "--tracker", "real", "--stage", "--choice", choice)
    assert _volume(out) == (action, choice, "asked") and out["volume"]["over"] is False
    assert out["triage"] is (action == "triage") and [t["title"] for t in out["tickets"]] == titles


# --- record: triage tickets have no keys (option (b)) -------------------------

def _publish(tmp_path, *lines):
    (tmp_path / ".scratch" / SLUG / "manifest.md").write_text("---\nartifact-type: tickets\n---\n" + "".join(f"{ln}\n" for ln in lines))


def test_triage_only_staging_with_the_triage_ticket_published_is_published(tmp_path, capsys):
    _setup(tmp_path, _plan(_many(3)))
    (t,) = _render(tmp_path, capsys, "--stage", "--triage")["tickets"]
    _publish(tmp_path, f"#9 {t['nn']}-{t['slug']}")
    out = _record(tmp_path, capsys)
    assert out == {"status": "published", "tickets": [{"ref": "#9", "keys": []}], "unpublished": [], "unmatched": []}
    assert _read_index(tmp_path) == {}  # triage items stay out of the cross-run index


def test_triage_only_staging_with_nothing_published_is_not_published(tmp_path, capsys):
    _setup(tmp_path, _plan(_many(3)))
    (t,) = _render(tmp_path, capsys, "--stage", "--triage")["tickets"]
    out = _record(tmp_path, capsys)
    assert out["status"] == "drafted" and out["tickets"] == []
    assert out["unpublished"] == [f"{t['nn']}-{t['slug']}"]


def test_mixed_fix_and_triage_staging_credits_both_and_indexes_only_keys(tmp_path, capsys):
    _setup(tmp_path, _plan([*_many(3), _cand("test_f", "flaky", seed=3, file="tests/m009/test_x.py")]))
    fix, tri = _render(tmp_path, capsys, "--stage", "--triage")["tickets"]
    fix_key = "fix|flaky|tests/m009/test_x.py::test_f"
    _publish(tmp_path, f"#1 {fix['nn']}-{fix['slug']}")
    out = _record(tmp_path, capsys)
    assert out["status"] == "partial" and out["unpublished"] == [f"{tri['nn']}-{tri['slug']}"]
    # to-tickets renamed the triage ticket: its body still holds the criterion's triage text
    base = tmp_path / ".scratch" / SLUG / "draft-issues"
    (base / f"{tri['nn']}-{tri['slug']}.md").rename(base / f"{tri['nn']}-triage-dead-tests.md")
    _publish(tmp_path, f"#1 {fix['nn']}-{fix['slug']}", f"#2 {tri['nn']}-triage-dead-tests")
    out = _record(tmp_path, capsys)
    assert out["status"] == "published" and out["unpublished"] == []
    assert out["tickets"] == [{"ref": "#1", "keys": [fix_key]}, {"ref": "#2", "keys": []}]
    assert _read_index(tmp_path) == {fix_key: {"ref": "#1", "slug": SLUG}}


def _rename_and_publish(tmp_path, ticket, new_name, ref="#7"):
    base = tmp_path / ".scratch" / SLUG / "draft-issues"
    (base / f"{ticket['nn']}-{ticket['slug']}.md").rename(base / f"{new_name}.md")
    _publish(tmp_path, f"{ref} {new_name}")


@pytest.mark.parametrize("n,title", [
    (1, "Triage 1 dead-test test from the review queue"),  # singular title: its slug has no `-tests`
    (3, "Triage 3 dead-test tests from the review queue"),
])
def test_renamed_triage_ticket_is_credited_by_its_criterion_text(tmp_path, capsys, n, title):
    _setup(tmp_path, _plan(_many(n)))
    (t,) = _render(tmp_path, capsys, "--stage", "--triage")["tickets"]
    assert t["title"] == title
    doc = json.loads((tmp_path / ".scratch" / SLUG / "tickets.json").read_text())
    assert doc["tickets"] == [{"nn": t["nn"], "slug": t["slug"], "keys": [], "criterion": "dead-test"}]
    _rename_and_publish(tmp_path, t, f"{t['nn']}-sort-out-dead-tests")
    out = _record(tmp_path, capsys)
    assert out == {"status": "published", "tickets": [{"ref": "#7", "keys": []}], "unpublished": [], "unmatched": []}


def test_renamed_triage_ticket_of_another_criterion_is_not_credited(tmp_path, capsys):
    _setup(tmp_path, _plan([*_many(2), *_many(2, "cost")]))
    cost, dead = _render(tmp_path, capsys, "--stage", "--triage")["tickets"]
    assert "cost" in cost["title"] and "dead-test" in dead["title"]
    _rename_and_publish(tmp_path, cost, f"{cost['nn']}-sort-out-slow-tests")
    out = _record(tmp_path, capsys)
    assert out["status"] == "partial" and out["unpublished"] == [f"{dead['nn']}-{dead['slug']}"]
    assert out["tickets"] == [{"ref": "#7", "keys": []}]


def test_triage_entry_without_a_criterion_is_credited_only_by_name(tmp_path, capsys):
    _setup(tmp_path, _plan(_many(1)))
    (t,) = _render(tmp_path, capsys, "--stage", "--triage")["tickets"]
    path = tmp_path / ".scratch" / SLUG / "tickets.json"
    doc = json.loads(path.read_text())
    del doc["tickets"][0]["criterion"]  # a tickets.json from before the field
    path.write_text(json.dumps(doc))
    _rename_and_publish(tmp_path, t, f"{t['nn']}-sort-out-dead-tests")
    out = _record(tmp_path, capsys)
    assert out["status"] == "drafted" and out["unpublished"] == [f"{t['nn']}-{t['slug']}"]
    _publish(tmp_path, f"#8 {t['nn']}-{t['slug']}")
    (tmp_path / ".scratch" / SLUG / "draft-issues" / f"{t['nn']}-sort-out-dead-tests.md").rename(
        tmp_path / ".scratch" / SLUG / "draft-issues" / f"{t['nn']}-{t['slug']}.md")
    assert _record(tmp_path, capsys)["status"] == "published"


def test_boundary_double_text_asks_for_no_deletion_and_is_for_a_human(tmp_path, capsys):
    from render_review_queue import WHAT, review_what
    text = review_what("pinning", "boundary-double")
    assert "do not delete the test" in text and "Remove a test only when a mutation check" not in text
    assert text != review_what("pinning", "collaborator-double")
    assert text != WHAT["review"]["pinning"]
    _setup(tmp_path, _plan([_cand("test_b", "pinning", kind="boundary-double")]))
    (ticket,) = _render(tmp_path, capsys, "--stage")["tickets"]
    assert ticket["title"] == "Review 1 pinning test (boundary-double) in tests/pkg/adapters"
    assert ticket["label"] == "ready-for-human"
    assert "do not delete the test" in _draft(tmp_path, ticket)
