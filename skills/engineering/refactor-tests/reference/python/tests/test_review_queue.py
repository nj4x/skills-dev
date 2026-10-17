"""Seam tests for render_review_queue.py (ADR-0079): the review queue, ticket drafts, and cross-run index.

Run: uv run --with pytest pytest reference/python/tests
"""
import json

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
    assert json.loads(capsys.readouterr().out) == {"rekeyed": True}
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
    assert json.loads(capsys.readouterr().out) == {"rekeyed": False}
    assert _read_index(tmp_path) == entries


def test_hand_edited_index_entries_do_not_abort_the_run(tmp_path, capsys):
    _index(tmp_path, {"junk": {"ref": "#1"}, f"review|dead-test|{A}::test_a": {"slug": "x"}})
    _setup(tmp_path, _plan([_cand("test_a", "dead-test")]))
    out = _render(tmp_path, capsys)
    assert out["already_tracked"] == [{"key": f"review|dead-test|{A}::test_a", "ref": "?"}]
