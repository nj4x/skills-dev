"""Turn the human-action items of a refactor-tests run into a review queue and ticket drafts (ADR-0079).

Usage:
  python render_review_queue.py render --project-root P --ledger L (--plan SP | --rekey-only) \\
      [--index IDX] [--project-name NAME] [--stopped-at PHASE] [--stage]
  python render_review_queue.py record --project-root P --slug SLUG [--index IDX] [--ref NN-slug=REF ...]

`render` reads the ledger and `simplification-plan.json`, re-keys the cross-run index through
the ledger's moves (not after `--stopped-at failed-layout`), and always writes
`.scratch/refactor-tests/review-queue.md`. With `--rekey-only` it does only the re-key. With `--stage` (and no `--stopped-at`) it also
writes `.scratch/<slug>/spec.md`, `draft-issues/<NN>-<slug>.md`, and `manifest.md` in the
shape `to-tickets` expects, plus `tickets.json` for `record`. It prints a JSON summary.
Relative `--ledger`, `--plan`, and `--index` paths resolve against `--project-root`.

`record` runs after `to-tickets`. It finds the published tickets (manifest lines
`<tracker-ID> <name>`, promoted `issues/<name>.md` files, or `--ref` overrides) and credits
each staged item to the published ticket whose body holds the item's full key in backticks, so a ticket
`to-tickets` renamed, merged, or split still counts. It adds those keys to the cross-run
index and prints `{ status, tickets, unpublished, unmatched }`. `status` is `published` (every
key credited), `drafted` (none), or `partial`; `unpublished` lists uncredited keys and
`unmatched` the published names with no body file. `render` also writes the index back with
ids re-keyed through the run's moves, except after a layout regression (`--stopped-at failed-layout`);
`render --rekey-only` does only that, for a run with `--no-publish-review`.

Items fall in four categories: review (dead-test, coverage-subset, cost, pinning), fix
(order-dependent, flaky), add (confirmed seams no interface test reaches), and skipped
(parametrizations the AST editor skipped, Spring clusters left unconsolidated). Each item
has the key `<category>|<criterion>|<id>`. A key already in the index is "already tracked"
and gets no ticket. Index ids are mapped through the ledger's moves first, so a test moved
since it was ticketed still matches.
"""
import argparse
import json
import os
import posixpath
import re
import shlex
import sys
from pathlib import Path

from order_gate import matches
from refactor_tests_shared import split_file, strip_params, write_atomic

REVIEW = ("dead-test", "coverage-subset", "cost", "pinning")
FIX = ("order-dependent", "flaky")
CATEGORY_ORDER = ("fix", "review", "add", "skipped")
LABELS = {"review": "ready-for-human", "skipped": "ready-for-human",
          "fix": "ready-for-agent", "add": "ready-for-agent"}
MAX_IDS = 25
QUEUE = ".scratch/refactor-tests/review-queue.md"
INDEX = ".scratch/refactor-tests/review-index.json"


def slugify(text):
    """The `to-tickets` feature-slug rule: lowercase, non-alphanumeric to `-`, trimmed."""
    return re.sub(r"[^a-z0-9]", "-", text.lower()).strip("-")


def run_title(started_at):
    return f"refactor-tests review {started_at}"


def _module(path):
    return posixpath.dirname(path) or "."


def _excerpt(text):
    return " / ".join((text or "").splitlines()[:2])


# --- items ------------------------------------------------------------------

def collect_items(ledger, plan):
    """Every human-action item of the run, as dicts with `category`, `criterion`, `id`, `key`."""
    items, seen = [], set()

    def add(category, criterion, item_id, module, **extra):
        key = f"{category}|{criterion}|{item_id}"
        if key in seen:  # e.g. two demoted removals that share one kept duplicate
            return
        seen.add(key)
        items.append({"category": category, "criterion": criterion, "id": item_id,
                      "module": module, "key": key, **extra})

    for c in plan.get("review_candidates", []):
        crit = c.get("criterion")
        if crit not in REVIEW and crit not in FIX:
            continue
        extra = {k: c[k] for k in ("evidence", "call_s", "time_saved_s", "note", "seed", "failing_ids")
                 if c.get(k) is not None}
        add("review" if crit in REVIEW else "fix", crit, f"{c['file']}::{c['test_name']}",
            _module(c["file"]), file=c["file"], test_name=c["test_name"], **extra)

    for a in (plan.get("seams") or {}).get("add_candidates", []):
        add("add", "untested-seam", f"{a['module']}::{a['seam']}", a["module"])

    for p in (ledger.get("simplification") or {}).get("parametrizations", []):
        if not p.get("skipped"):
            continue
        add("skipped", "skipped-parametrization", f"{p['file']}::{p['consolidated_name']}",
            _module(p["file"]), evidence=str(p["skipped"]), tests=p.get("tests") or p.get("replaced") or [])

    for s in (ledger.get("spring") or {}).get("skipped_clusters", []):
        add("skipped", "skipped-spring-cluster", s["cluster"], s["cluster"],
            evidence=s.get("reason", ""), classes=s.get("classes", []))
    return items


def _move_map(ledger):
    files = {m["from"]: m["to"] for m in ledger.get("moves", [])}
    ids = ledger.get("id_map", {})

    def translate(item_id):
        base, suffix = strip_params(item_id)
        if base in ids:
            return ids[base] + suffix
        file, rest = split_file(item_id)
        return f"{files[file]}::{rest}" if file in files and rest else item_id
    return translate


def rekey_index(index, ledger):
    """Index entries re-keyed with each test id mapped through this run's moves.

    `main` writes them back, so a test moved in this run still matches its entry in later
    runs, whose ledgers no longer hold the move.
    """
    translate = _move_map(ledger)
    out = {}
    for key, entry in index.get("entries", {}).items():
        if key.count("|") < 2 or not isinstance(entry, dict):  # a hand-edited index must not abort the run
            out.setdefault(key, entry)
            continue
        category, criterion, item_id = key.split("|", 2)
        out.setdefault(f"{category}|{criterion}|{translate(item_id)}", entry)
    return out


def should_rekey(stopped_at):
    """Phase A moves stay in the working tree after a later gate regresses; only a layout regression may be reverted."""
    return stopped_at != "failed-layout"


# --- grouping ---------------------------------------------------------------

def _title(category, criterion, module, items):
    n = len(items)
    if category == "review":
        return f"Review {n} {criterion} test{'s' * (n != 1)} in {module}"
    if category == "fix":
        seed = items[0].get("seed")
        return f"Fix {n} {criterion} test{'s' * (n != 1)} in {module}" + (f" (seed {seed})" if seed is not None else "")
    if category == "add":
        return f"Add interface tests for {n} untested seam{'s' * (n != 1)} in {module}"
    if criterion == "skipped-parametrization":
        return f"Merge {n} skipped parametrization{'s' * (n != 1)} in {module} by hand"
    return f"Consolidate skipped Spring cluster {module} by hand"


def group_tickets(items):
    """One ticket per (category, criterion, module); a group over MAX_IDS ids splits into parts."""
    groups = {}
    for it in items:
        groups.setdefault((it["category"], it["criterion"], it["module"]), []).append(it)
    order = sorted(groups, key=lambda g: (CATEGORY_ORDER.index(g[0]), g[1], g[2]))
    tickets = []
    for category, criterion, module in order:
        members = sorted(groups[(category, criterion, module)], key=lambda i: i["id"])
        parts = [members[i:i + MAX_IDS] for i in range(0, len(members), MAX_IDS)]
        for n, part in enumerate(parts, 1):
            title = _title(category, criterion, module, part)
            if len(parts) > 1:
                title += f" (part {n} of {len(parts)})"
            tickets.append({"category": category, "criterion": criterion, "module": module,
                            "title": title, "label": LABELS[category], "items": part, "blocked_by": []})
    for nn, t in enumerate(tickets, 1):
        t["nn"] = f"{nn:02d}"
        t["slug"] = slugify(t["title"])[:60].strip("-")
    _wire_blocking(tickets)
    return tickets


def _wire_blocking(tickets):
    """A fix ticket blocks every review ticket that shares a test with it."""
    for fix in (t for t in tickets if t["category"] == "fix"):
        fix_ids = [i["id"] for i in fix["items"]]
        for rev in (t for t in tickets if t["category"] == "review"):
            if any(matches(fid, i["file"], i["test_name"]) for fid in fix_ids for i in rev["items"]):
                rev["blocked_by"].append(f"{fix['nn']}-{fix['slug']}")


# --- rendering --------------------------------------------------------------

def _item_line(it, with_key=False):
    parts = [f"`{it['id']}`"]
    if it.get("evidence"):
        parts.append(_excerpt(it["evidence"]))
    if it.get("call_s") is not None:
        parts.append(f"call_s {it['call_s']} s, time_saved_s {it.get('time_saved_s', it['call_s'])} s (serial time)")
    if it.get("note"):
        parts.append(it["note"])
    if it.get("failing_ids"):
        parts.append("failing_ids: " + ", ".join(f"`{f}`" for f in it["failing_ids"]))
    if it.get("tests"):
        parts.append("tests: " + ", ".join(f"`{t}`" for t in it["tests"]))
    if it.get("classes"):
        parts.append("classes: " + ", ".join(f"`{c}`" for c in it["classes"]))
    if with_key:  # `record` credits an item to a published ticket by this key
        parts.append(f"key: `{it['key']}`")
    return "- " + " — ".join(parts)


_CAVEAT = (" Coverage shows execution, not assertion strength. Remove a test only when a mutation check of its"
          " module shows no lost kill; otherwise keep or merge it. See SKILL.md → Follow-up: mutation deletion gate (optional).")
_REVIEW_WHAT = {
    "dead-test": "The run flagged these tests for review and did not change them. Decide for each one: keep, rewrite at the interface, or remove.",
    "coverage-subset": "The run flagged these tests for review and did not change them. Every line and arc each one covers is also covered by other passing tests." + _CAVEAT,
    "cost": "The run flagged these slow tests for review and did not change them. Each is a coverage-subset test in the top decile by call time; the evidence does not say why it is slow." + _CAVEAT,
    "pinning": "The run flagged these tests for review and did not change them. Each patches internals instead of calling the interface; the note per test says whether one interface test covers its lines (assertions not compared). Decide for each one: keep, or move the assertion to the interface." + _CAVEAT,
}
WHAT = {
    "review": _REVIEW_WHAT,  # per criterion; the dead-test text stays neutral
    "fix": "These tests fail when the suite runs in random order. The order gate moved every planned change that touches them to review. Make each one pass in any order.",
    "add": "These confirmed seams have no interface test that reaches them. Add a test at each seam.",
    "skipped": "The run could not apply this change automatically and left the files unchanged. Apply it by hand or record why it stays.",
}
CHECK = {
    "review": "Each listed test is kept, rewritten, or removed, and the decision is recorded in the PR",
    "fix": "Each listed test passes under the random-order run{seed}",
    "add": "Each listed seam has an interface test that reaches its body",
    "skipped": "Each listed item is applied by hand, or the reason it stays is recorded",
}


def reproduce_line(ledger, item):
    """The command that re-runs one fix-ticket file with the recorded runner, plugin and seed, or None."""
    gate = ledger.get("order_gate") or {}
    seed = item.get("seed", gate.get("seed"))
    if seed is None:
        return None
    tokens = shlex.split((ledger.get("runners") or {}).get("python") or "pytest")
    prefix = ""
    if gate.get("plugin") == "pytest-random-order":
        args = ["--random-order-bucket=global", f"--random-order-seed={seed}"]
    else:
        # the recorded `-p no:randomly` would block the plugin; the gate installed it for its run
        tokens = [t for i, t in enumerate(tokens)
                  if t != "no:randomly" and not (t == "-p" and tokens[i + 1:i + 2] == ["no:randomly"])]
        args = ["-p", "randomly", f"--randomly-seed={seed}"]
        if tokens[:2] == ["uv", "run"]:
            tokens[2:2] = ["--with", "pytest-randomly"]
        elif tokens[:1] == ["pytest"]:
            tokens = ["uv", "run", "--with", "pytest-randomly", *tokens]
        else:  # another launcher: install into the scratch dir, as Step 7 does
            target = ".scratch/refactor-tests/pytest-randomly"
            prefix = (f"python3 -m pip install --target {target} pytest-randomly && "
                      f"PYTHONPATH={target}${{PYTHONPATH:+:$PYTHONPATH}} ")
    return prefix + shlex.join([*tokens, *args, item.get("file", "")])


def ticket_body(t, slug, ledger=None):
    blocked = "\n".join(" — ".join(b.split("-", 1)) for b in t["blocked_by"]) or "none"
    seed = t["items"][0].get("seed")
    check = CHECK[t["category"]].format(seed=f" with seed {seed}" if seed is not None else "")
    items = "\n".join(_item_line(i, with_key=True) for i in t["items"])
    what = WHAT["review"][t["criterion"]] if t["category"] == "review" else WHAT[t["category"]]
    if t["category"] == "fix":
        lines = dict.fromkeys(filter(None, (reproduce_line(ledger or {}, i) for i in t["items"])))
        if lines:
            what += "\n\nReproduce:\n" + "\n".join(f"    {ln}" for ln in lines)
    return (
        "---\n"
        "artifact-type: ticket\n"
        f"label: {t['label']}\n"
        "lineage-rules:\n"
        '  - "Ticket must reference its source spec"\n'
        '  - "Ticket may additionally reference source ADRs for cross-cutting concerns"\n'
        "---\n\n"
        f"# {t['nn']} — {t['title']}\n\n"
        f"**Spec**: {slug}\n\n"
        f"## What to build\n{what}\n\n{items}\n\n"
        f"## Blocked by\n{blocked}\n\n"
        f"## Status\n{t['label']}\n\n"
        f"## Checklist\n- [ ] {check}\n"
    )


def _counts(items):
    out = {}
    for it in items:
        out[it["criterion"]] = out.get(it["criterion"], 0) + 1
    return out


def spec_body(started_at, project, tickets, tracked):
    items = [i for t in tickets for i in t["items"]]
    lines = [f"# {run_title(started_at)}", "", f"Project: {project}", "",
             ("Human-action items from a refactor-tests run (ADR-0079). The ledger under "
              "`.scratch/refactor-tests/` holds the full evidence."), "", "## Items", ""]
    lines += [f"- {crit}: {n}" for crit, n in sorted(_counts(items).items())]
    if tracked:
        lines += ["", "## Already tracked", ""]
        lines += [f"- `{k}` — {ref}" for k, ref in tracked]
    lines += ["", "## Proposed tickets", "", "| NN | Title | Label | Blocked by |", "|---|---|---|---|"]
    lines += [f"| {t['nn']} | {t['title']} | {t['label']} | {', '.join(b.split('-', 1)[0] for b in t['blocked_by']) or 'none'} |"
              for t in tickets]
    return "\n".join(lines) + "\n"


def queue_body(started_at, project, tickets, tracked, superseded, stopped_at):
    lines = [f"# {run_title(started_at)}: review queue", "", f"Project: {project}", ""]
    if stopped_at:
        lines += [f"> Run stopped at {stopped_at}; candidates may be stale.", ""]
    if not tickets:
        lines += ["No human-action items" + (" left after dedupe." if tracked else "."), ""]
    for t in tickets:
        lines += [f"## {t['title']} ({t['label']})", ""]
        if t["blocked_by"]:
            lines += ["Blocked by: " + ", ".join(t["blocked_by"]), ""]
        lines += [_item_line(i).replace("- ", "- [ ] ", 1) for i in t["items"]] + [""]
    if tracked:
        lines += ["## Already tracked", ""] + [f"- `{k}` — {ref}" for k, ref in tracked] + [""]
    if superseded:
        lines += ["## Superseded drafts", ""] + [f"- `.scratch/{s}/`: never published; superseded by this run" for s in superseded] + [""]
    return "\n".join(lines)


def _write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _load(path, default):
    if path and Path(path).exists():
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"render_review_queue: {path} is not valid JSON ({e})") from e
    return default


NAME_LINE = re.compile(r"(\S+) (\d+-\S+?)(?:\.md)?\s*")  # `<tracker-ID> <NN>-<slug>` after a publish


def _manifest_refs(base):
    """Ticket file name -> tracker ref, from manifest lines a real-tracker publish rewrote."""
    manifest = base / "manifest.md"
    refs = {}
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            m = NAME_LINE.fullmatch(line)
            if m and not m.group(1).startswith(".scratch/"):
                refs.setdefault(m.group(2), m.group(1))
    return refs


def superseded_slugs(root, slug, index):
    """Earlier run slugs with drafts that no tracker and no index entry shows as published."""
    published = {e.get("slug") for e in index.get("entries", {}).values()}
    out = []
    for d in sorted((root / ".scratch").glob("refactor-tests-review-*")):
        if d.name != slug and (d / "draft-issues").is_dir() and not (d / "issues").exists() \
                and not _manifest_refs(d) and d.name not in published:
            out.append(d.name)
    return out


def render(root, ledger, plan, index, project, stopped_at, stage):
    started_at = ledger.get("started_at")
    if not started_at:
        raise SystemExit("render_review_queue: ledger has no started_at (Step 1 records it, also on resume)")
    slug = slugify(run_title(started_at))
    known = rekey_index(index, ledger)
    if should_rekey(stopped_at):
        index["entries"] = known
    items, tracked = [], []
    for it in collect_items(ledger, plan):
        if it["key"] in known:
            tracked.append((it["key"], known[it["key"]].get("ref", "?")))
        else:
            items.append(it)
    tickets = group_tickets(items)
    superseded = superseded_slugs(root, slug, index)
    _write_text(root / QUEUE, queue_body(started_at, project, tickets, tracked, superseded, stopped_at))
    staged = bool(stage and not stopped_at and tickets)
    if staged:
        base = root / ".scratch" / slug
        drafts = base / "draft-issues"
        if drafts.is_dir():
            for old in drafts.glob("*.md"):
                old.unlink()
        _write_text(base / "spec.md", spec_body(started_at, project, tickets, tracked))
        paths = []
        for t in tickets:
            rel = f".scratch/{slug}/draft-issues/{t['nn']}-{t['slug']}.md"
            _write_text(root / rel, ticket_body(t, slug, ledger))
            paths.append(rel)
        _write_text(base / "manifest.md", "---\nartifact-type: tickets\n---\n" + "\n".join(paths) + "\n")
        write_atomic(base / "tickets.json", {"slug": slug, "tickets": [
            {"nn": t["nn"], "slug": t["slug"], "keys": [i["key"] for i in t["items"]]} for t in tickets]})
    return {
        "slug": slug,
        "title": run_title(started_at),
        "queue": QUEUE,
        "staged": staged,
        "items": len(items),
        "tickets": [{"nn": t["nn"], "slug": t["slug"], "title": t["title"], "label": t["label"],
                     "blocked_by": t["blocked_by"], "ids": len(t["items"])} for t in tickets],
        "already_tracked": [{"key": k, "ref": ref} for k, ref in tracked],
        "superseded": superseded,
    }


# --- record -----------------------------------------------------------------

def record(root, slug, index, refs):
    base = root / ".scratch" / slug
    doc = _load(base / "tickets.json", None)
    if doc is None:
        raise SystemExit(f"render_review_queue: no tickets.json under .scratch/{slug}")
    found = {name.removesuffix(".md"): ref for name, ref in refs.items()}  # ticket file name -> ref
    for name, ref in _manifest_refs(base).items():
        found.setdefault(name, ref)
    if (base / "issues").is_dir():
        for f in sorted((base / "issues").glob("*.md")):
            found.setdefault(f.stem, f".scratch/{slug}/issues/{f.name}")
    keys = [k for t in doc["tickets"] for k in t["keys"]]
    credited, unmatched = {}, []  # ref -> keys its body names; names with no body file
    for name, ref in found.items():
        body_file = next((p for p in (base / "issues" / f"{name}.md", base / "draft-issues" / f"{name}.md")
                          if p.exists()), None)
        if body_file is None:
            unmatched.append(name)
            continue
        body = body_file.read_text(encoding="utf-8")
        mine = [k for k in keys if f"`{k}`" in body]
        if mine:
            credited[ref] = list(dict.fromkeys(credited.get(ref, []) + mine))
    done = {k for ks in credited.values() for k in ks}
    for ref, ks in credited.items():
        for key in ks:
            index.setdefault("entries", {})[key] = {"ref": ref, "slug": slug}
    unpublished = [k for k in keys if k not in done]
    status = "published" if not unpublished else ("drafted" if not done else "partial")
    tickets = [{"ref": ref, "keys": ks} for ref, ks in credited.items()]
    return index, {"status": status, "tickets": tickets, "unpublished": unpublished, "unmatched": unmatched}


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--project-root", required=True)
    r.add_argument("--ledger", required=True)
    r.add_argument("--plan")
    r.add_argument("--rekey-only", action="store_true", help="only re-key the index (Step 11 with --no-publish-review)")
    r.add_argument("--index")
    r.add_argument("--project-name")
    r.add_argument("--stopped-at")
    r.add_argument("--stage", action="store_true")
    c = sub.add_parser("record")
    c.add_argument("--project-root", required=True)
    c.add_argument("--slug", required=True)
    c.add_argument("--index")
    c.add_argument("--ref", action="append", default=[], help="<ticket file name>=REF for a ticket the manifest does not show")
    a = ap.parse_args(argv)
    root = Path(a.project_root).resolve()
    index_path = root / (a.index or INDEX)  # an absolute --index replaces root
    index = _load(index_path, {"schema_version": 1, "entries": {}})
    if a.cmd == "render":
        if not (root / a.ledger).exists():
            raise SystemExit(f"render_review_queue: no ledger at {root / a.ledger}")
        before = dict(index.get("entries", {}))
        if a.rekey_only:
            if should_rekey(a.stopped_at):
                index["entries"] = rekey_index(index, _load(root / a.ledger, {}))
            out = {"rekeyed": index.get("entries", {}) != before}
        else:
            if not a.plan:
                ap.error("render needs --plan unless --rekey-only")
            # A missing plan is normal when Phase B never ran: it holds no items.
            out = render(root, _load(root / a.ledger, {}), _load(root / a.plan, {}), index,
                         a.project_name or root.name, a.stopped_at, a.stage)
        if index.get("entries", {}) != before:
            write_atomic(index_path, index)
    else:
        if any("=" not in r for r in a.ref):
            ap.error("--ref needs <ticket file name>=REF")
        refs = dict(ref.split("=", 1) for ref in a.ref)
        index, out = record(root, a.slug, index, refs)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(index_path, index)
    json.dump(out, sys.stdout, indent=1)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
