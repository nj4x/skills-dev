"""Turn the human-action items of a refactor-tests run into a review queue and ticket drafts (ADR-0079).

Usage:
  python render_review_queue.py render --project-root P --ledger L (--plan SP | --rekey-only [--plan SP]) \\
      [--index IDX] [--project-name NAME] [--stopped-at PHASE] [--stage] [--evidence EV] \\
      [--tracker local|real] [--unattended] [--triage | --choice a|b|c]
  python render_review_queue.py record --project-root P --slug SLUG [--index IDX] [--ref NN-slug=REF ...]

Both `render` forms also write `.scratch/refactor-tests/run-summary.json`, the committable
summary of the run (`run_summary`). A field that cannot be computed (no plan, no evidence
file, evidence not `ok`) is null, and its `notes` say why. Every staged ticket body carries
`git_sha: <sha>` read from the evidence file, `git_sha: unknown` when there is none.

Volume gate (ADR-0080 Decision 3): `render` counts the tickets it would stage after dedupe,
hotspot tickets included, and prints `volume: { tickets, threshold, over, action, choice,
chosen_by }`. With `--tracker`, `action` is `publish` (at most 50), `ask` (interactive),
`triage` (unattended, local tracker; `render` then applies `--triage` itself), or `drafted`
(unattended, real tracker). `--choice a|b|c` passes the user's answer: the action becomes
`publish`, `triage` or `declined` at any ticket count, also in an unattended run, and
`choice` and `chosen_by: asked` record it. Without `--choice`, `render` reuses a choice
recorded in ledger `publish.volume` only when its `chosen_by` is `asked`, so a resume does
not ask again; a recorded unattended default is computed again, never reused. An unattended
default records `chosen_by: unattended-default`. `--triage` and `--choice` are mutually
exclusive.
`--triage` (option (b), the same as `--choice b`) stages fix, hotspot and add tickets unchanged and replaces
the review tickets with one triage ticket per review criterion, with no `key:` lines; the
review tickets' blocking edges move to it, and skipped tickets are not staged. The queue
file lists every ticket in either mode.

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
index and prints `{ status, tickets, unpublished, unmatched }`. A triage ticket (`keys: []`
and its `criterion` in `tickets.json`) counts as published when a published name is its file
name or a published body holds that criterion's triage text; it is listed in `tickets` with `keys: []` and adds no
index entry. `status` is `published` (every key and every triage ticket credited), `drafted`
(none), or `partial`; `unpublished` lists uncredited keys, then the file names of uncredited
triage tickets, and `unmatched` the published names with no body file. `render` also writes the index back with
ids re-keyed through the run's moves, except after a layout regression (`--stopped-at failed-layout`);
`render --rekey-only` does only that, for a run with `--no-publish-review`.

Items fall in five categories: review (dead-test, coverage-subset, cost, pinning), fix
(order-dependent, flaky), hotspot (shared cost causes from `hotspot_probe.py`, one ticket
each, numbered after fix and before review tickets), add (confirmed seams no interface test
reaches), and skipped (parametrizations the AST editor skipped, Spring clusters left
unconsolidated). A fix ticket blocks each review ticket sharing a test with it; a hotspot
ticket blocks each cost and coverage-subset ticket with a test in the directory of one of
its `tests`. Each item has the key `<category>|<criterion>|<id>`. A key already in the index is "already tracked"
and gets no ticket. Index ids are mapped through the ledger's moves first, so a test moved
since it was ticketed still matches.

A review candidate may carry `kind`. Dead-test and pinning tickets split by it, and a known
kind picks the ticket text (and `ready-for-agent` for a pinning `collaborator-double`).
Dead-test `no-raise-contract` items are never ticketed: `render` counts them under
`report_only`. Any other `kind` value, or none, passes through into the item line.
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
CATEGORY_ORDER = ("fix", "hotspot", "review", "triage", "add", "skipped")
LABELS = {"review": "ready-for-human", "skipped": "ready-for-human", "triage": "ready-for-human",
          "fix": "ready-for-agent", "hotspot": "ready-for-agent", "add": "ready-for-agent"}
VOLUME_THRESHOLD = 50  # more staged tickets than this asks the volume gate (ADR-0080 Decision 3)
NOT_DISCRIMINATING = 0.5  # a criterion flagging more than this share of evidence tests gets a warning
TOP_N = 15
HOTSPOT_BLOCKS = ("cost", "coverage-subset")  # review criteria whose `call_s` order a hotspot fix changes
KIND_GROUPED = ("dead-test", "pinning")  # criteria whose tickets split by item `kind`
KIND_LABELS = {("pinning", "collaborator-double"): "ready-for-agent"}
REPORT_ONLY = {("dead-test", "no-raise-contract")}  # counted in the Final report, never ticketed
MAX_IDS = 25
QUEUE = ".scratch/refactor-tests/review-queue.md"
INDEX = ".scratch/refactor-tests/review-index.json"
SUMMARY = ".scratch/refactor-tests/run-summary.json"
EVIDENCE = ".scratch/refactor-tests/test-evidence.json"


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
        if crit == "hotspot":
            if isinstance(c.get("function"), str) and c["function"]:  # one ticket per hotspot: its function is the module
                extra = {k: c[k] for k in ("share", "tests", "subprocess_spawns", "via") if c.get(k)}
                add("hotspot", "hotspot", c["function"], c["function"], **extra)
            continue
        if crit not in REVIEW and crit not in FIX:
            continue
        if _report_only(c):
            continue
        extra = {k: c[k] for k in ("kind", "evidence", "call_s", "time_saved_s", "note", "seed", "failing_ids")
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


def _report_only(c):
    kind = c.get("kind")
    return isinstance(kind, str) and (c.get("criterion"), kind) in REPORT_ONLY


def report_only_counts(plan):
    """`<criterion>/<kind>` -> number of review candidates that are reported, never ticketed."""
    out = {}
    for c in plan.get("review_candidates", []):
        if _report_only(c):
            name = f"{c['criterion']}/{c['kind']}"
            out[name] = out.get(name, 0) + 1
    return out


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

def _title(category, criterion, module, items, kind=None):
    n = len(items)
    if category == "review":
        return f"Review {n} {criterion} test{'s' * (n != 1)}" + (f" ({kind})" if kind else "") + f" in {module}"
    if category == "fix":
        seed = items[0].get("seed")
        return f"Fix {n} {criterion} test{'s' * (n != 1)} in {module}" + (f" (seed {seed})" if seed is not None else "")
    if category == "hotspot":
        return f"Fix cost hotspot {module} in the test tier"
    if category == "add":
        return f"Add interface tests for {n} untested seam{'s' * (n != 1)} in {module}"
    if criterion == "skipped-parametrization":
        return f"Merge {n} skipped parametrization{'s' * (n != 1)} in {module} by hand"
    return f"Consolidate skipped Spring cluster {module} by hand"


def _kind(it):
    """The item's `kind` when its criterion splits tickets by kind, else "" (any other kind only shows in the item line)."""
    kind = it.get("kind") if it["criterion"] in KIND_GROUPED else None
    return kind if isinstance(kind, str) else ""


def group_tickets(items, triage=False):
    """One ticket per (category, criterion, kind, module); a group over MAX_IDS ids splits into parts.

    `kind` splits dead-test and pinning items only; it is "" for every other criterion.
    With `triage` (volume gate option (b)), the review tickets of each criterion become one
    triage ticket, and skipped tickets are left out; fix, hotspot and add tickets stay.
    """
    groups = {}
    for it in items:
        groups.setdefault((it["category"], it["criterion"], _kind(it), it["module"]), []).append(it)
    order = sorted(groups, key=lambda g: (CATEGORY_ORDER.index(g[0]), g[1], g[2], g[3]))
    tickets = []
    for category, criterion, kind, module in order:
        members = sorted(groups[(category, criterion, kind, module)], key=lambda i: i["id"])
        parts = [members[i:i + MAX_IDS] for i in range(0, len(members), MAX_IDS)]
        label = KIND_LABELS.get((criterion, kind), LABELS[category])
        for n, part in enumerate(parts, 1):
            title = _title(category, criterion, module, part, kind)
            if len(parts) > 1:
                title += f" (part {n} of {len(parts)})"
            tickets.append({"category": category, "criterion": criterion, "kind": kind or None, "module": module,
                            "title": title, "label": label, "items": part, "blocked_by": []})
    if triage:
        tickets = _triage(tickets)
    for nn, t in enumerate(tickets, 1):
        t["nn"] = f"{nn:02d}"
        t["slug"] = slugify(t["title"])[:60].strip("-")
    _wire_blocking(tickets)
    return tickets


def _triage(tickets):
    """Option (b): one triage ticket per review criterion that has a ticket, in the review tickets' place.

    A triage ticket keeps every item of the review tickets it replaces, so the blocking edges
    move to it; it lists its items per module and never by key.
    """
    out, by_criterion = [], {}
    for t in tickets:
        if t["category"] == "skipped":
            continue
        if t["category"] != "review":
            out.append(t)
            continue
        if t["criterion"] not in by_criterion:
            by_criterion[t["criterion"]] = {"category": "triage", "criterion": t["criterion"], "kind": None,
                                            "module": None, "label": LABELS["triage"], "items": [], "blocked_by": []}
            out.append(by_criterion[t["criterion"]])
        by_criterion[t["criterion"]]["items"].extend(t["items"])
    for t in by_criterion.values():
        n = len(t["items"])
        t["title"] = TRIAGE_TITLE.format(n=n, criterion=t["criterion"], s="s" * (n != 1))
    return out


def _test_dir(test_id):
    return posixpath.dirname(split_file(test_id)[0]) or "."


def _wire_blocking(tickets):
    """A fix ticket blocks every review ticket that shares a test with it.

    A hotspot ticket blocks every cost and coverage-subset ticket with a test in the directory
    of one of the hotspot's tests: fixing the hotspot changes their `call_s` order. A triage
    ticket takes the edges of the review tickets it replaced.
    """
    reviews = [t for t in tickets if t["category"] in ("review", "triage")]
    for fix in (t for t in tickets if t["category"] == "fix"):
        fix_ids = [i["id"] for i in fix["items"]]
        for rev in reviews:
            if any(matches(fid, i["file"], i["test_name"]) for fid in fix_ids for i in rev["items"]):
                rev["blocked_by"].append(f"{fix['nn']}-{fix['slug']}")
    for hot in (t for t in tickets if t["category"] == "hotspot"):
        dirs = {_test_dir(tid) for i in hot["items"] for tid in i.get("tests") or [] if isinstance(tid, str)}
        for rev in (r for r in reviews if r["criterion"] in HOTSPOT_BLOCKS):
            if any(_test_dir(i["file"]) in dirs for i in rev["items"]):
                rev["blocked_by"].append(f"{hot['nn']}-{hot['slug']}")


# --- rendering --------------------------------------------------------------

def _item_line(it, with_key=False):
    parts = [f"`{it['id']}`"]
    if it.get("kind") is not None:
        parts.append(f"kind: {it['kind']}")
    if it.get("evidence"):
        parts.append(_excerpt(it["evidence"]))
    if it.get("call_s") is not None:
        parts.append(f"call_s {it['call_s']} s, time_saved_s {it.get('time_saved_s', it['call_s'])} s (serial time)")
    if it.get("note"):
        parts.append(it["note"])
    if it.get("failing_ids"):
        parts.append("failing_ids: " + ", ".join(f"`{f}`" for f in it["failing_ids"]))
    if it.get("share") is not None:
        parts.append(f"mean share {it['share']} of the time of the tests where it is hot")
    if it.get("tests"):
        parts.append("tests: " + ", ".join(f"`{t}`" for t in it["tests"]))
    if isinstance(it.get("subprocess_spawns"), dict):
        parts.append("subprocess_spawns: " + ", ".join(f"`{t}` {n}" for t, n in it["subprocess_spawns"].items()))
    if it.get("via"):
        parts.append("via: " + ", ".join(f"`{v}`" for v in it["via"]))
    if it.get("classes"):
        parts.append("classes: " + ", ".join(f"`{c}`" for c in it["classes"]))
    if with_key:  # `record` credits an item to a published ticket by this key
        parts.append(f"key: `{it['key']}`")
    return "- " + " — ".join(parts)


_CAVEAT = (" Coverage shows execution, not assertion strength. Remove a test only when a mutation check of its"
          " module shows no lost kill; otherwise keep or merge it. See SKILL.md → Follow-up: mutation deletion gate (optional).")
_DEAD = "The run flagged these tests for review and did not change them. None has an assertion in its body."
_PINNING_DOUBLE = (
    "The run flagged these tests for review and did not change them. Each patches a collaborator that the"
    " module imports (a test double), and that double is its strictest reference to the module's internals;"
    " the note per test names any other reference. Re-point the stub (deps injection or a checked patch); do not delete.")
# Per (criterion, kind): replaces the criterion text of _REVIEW_WHAT. Any other kind, or none, keeps that text.
_KIND_WHAT = {
    ("dead-test", "fail-soft"): _DEAD + " Each sets up an error and calls the code under test, so it passes when that"
        " code silently does nothing. Add an assertion on the log or the return value, then check it by"
        " hand-mutating the function to a silent no-op: the test must fail.",
    ("dead-test", "never-fails"): _DEAD + " Each can only pass or `pytest.skip`. Replace the skip with an assertion, or remove the test.",
    ("dead-test", "no-assertion"): _DEAD + " Add an assertion on the behaviour the test exercises, or remove the test.",
    ("pinning", "collaborator-double"): _PINNING_DOUBLE,
}
_REVIEW_WHAT = {
    "dead-test": _KIND_WHAT[("dead-test", "no-assertion")],  # an item with no kind, or another kind, reads as no-assertion
    "coverage-subset": "The run flagged these tests for review and did not change them. Every line and arc each one covers is also covered by other passing tests." + _CAVEAT,
    "cost": "The run flagged these slow tests for review and did not change them. Each is a coverage-subset test in the top decile by call time; the evidence does not say why it is slow." + _CAVEAT,
    "pinning": "The run flagged these tests for review and did not change them. Each patches internals instead of calling the interface; the note per test says whether one interface test covers its lines (assertions not compared). Decide for each one: keep, or move the assertion to the interface." + _CAVEAT,
}
TRIAGE_TITLE = "Triage {n} {criterion} test{s} from the review queue"
# Only the triage ticket of one criterion holds this text: `record` credits a renamed triage ticket by it.
TRIAGE_PHRASE = "stands for every {criterion} test it flagged"
WHAT = {
    "review": _REVIEW_WHAT,  # per criterion; review_what() swaps in the _KIND_WHAT text for a known kind
    "fix": "These tests fail when the suite runs in random order. The order gate moved every planned change that touches them to review. Make each one pass in any order.",
    "hotspot": "Profiling the slowest cost candidates found this function holding at least half the time of at least half"
               " of the profiled tests; `subprocess_spawns` counts the processes each profiled test started."
               " Fix this in the test tier (a fixture or stub), never by deleting tests. Re-run the evidence pass after"
               " the fix, because `call_s` order changes.",
    "add": "These confirmed seams have no interface test that reaches them. Add a test at each seam.",
    "skipped": "The run could not apply this change automatically and left the files unchanged. Apply it by hand or record why it stays.",
    "triage": "The run staged more review tickets than a person can work through, so this one ticket "
              + TRIAGE_PHRASE + ". Triage them by module and hotspot before any per-test review. The"
              f" per-test list is in `{QUEUE}`; the counts, the concentration and the hotspots are in `{SUMMARY}`."
              " These tests carry no key here, so the next run queues them again with fresher evidence.",
}
CHECK = {
    "review": "Each listed test is kept, rewritten, or removed, and the decision is recorded in the PR",
    "triage": "Each listed module's tests are triaged (kept, fixed in a batch, or left for a later run), and the decision is recorded",
    "fix": "Each listed test passes under the random-order run{seed}",
    "hotspot": "The listed tests no longer spend most of their time in the hotspot, no test is deleted, and the evidence pass is re-run",
    "add": "Each listed seam has an interface test that reaches its body",
    "skipped": "Each listed item is applied by hand, or the reason it stays is recorded",
}


def review_what(criterion, kind=None):
    """A review ticket's "What to build" text: the kind's disposition when it has one, else the criterion text."""
    return _KIND_WHAT.get((criterion, kind), _REVIEW_WHAT[criterion])


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
                  if t not in ("no:randomly", "-pno:randomly", "-p=no:randomly") and not (t == "-p" and tokens[i + 1:i + 2] == ["no:randomly"])]
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


def _module_lines(items):
    """A triage ticket's item list: tests per module, most first, with no key."""
    per = {}
    for it in items:
        per[it["module"]] = per.get(it["module"], 0) + 1
    return "\n".join(f"- {m}: {n} test{'s' * (n != 1)}" for m, n in sorted(per.items(), key=lambda kv: (-kv[1], kv[0])))


def ticket_body(t, slug, ledger=None, git_sha=None):
    blocked = "\n".join(" — ".join(b.split("-", 1)) for b in t["blocked_by"]) or "none"
    seed = t["items"][0].get("seed")
    check = CHECK[t["category"]].format(seed=f" with seed {seed}" if seed is not None else "")
    if t["category"] == "triage":  # no `key:` lines: these items stay out of the cross-run index
        items = _module_lines(t["items"])
        what = WHAT["triage"].format(criterion=t["criterion"])
    else:
        items = "\n".join(_item_line(i, with_key=True) for i in t["items"])
        what = review_what(t["criterion"], t.get("kind")) if t["category"] == "review" else WHAT[t["category"]]
    items += f"\n\ngit_sha: {git_sha or 'unknown'} (the commit the evidence was taken at; a later commit may make this list stale)"
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


def spec_body(started_at, project, tickets, tracked, git_sha=None):
    items = [i for t in tickets for i in t["items"]]
    lines = [f"# {run_title(started_at)}", "", f"Project: {project}", "", f"git_sha: {git_sha or 'unknown'}", "",
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


# --- run summary ------------------------------------------------------------

def evidence_ok(evidence):
    """True when any language block of the evidence file has status `ok`."""
    return any(isinstance(b, dict) and b.get("status") == "ok"
               for b in ((evidence or {}).get("languages") or {}).values())


def _top(totals, field):
    rows = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]
    return [{"module": m, field: round(v, 6) if isinstance(v, float) else v} for m, v in rows]


def run_summary(ledger, plan, evidence, stopped_at=None, volume=None):
    """The committable `run-summary.json` of one run; a field it cannot compute is null and `notes` says why.

    `plan` and `evidence` are None when their file is missing. `git_sha` and `dirty` come from
    the evidence file only, the same source the ticket bodies read. Report-only candidates
    (dead-test `no-raise-contract`) count in `counts`, `kinds` and `report_only`, never in
    `shares`, `warnings` or `concentration`: they are never ticketed.
    """
    notes = []
    gate = ledger.get("order_gate") or {}
    ok = evidence_ok(evidence)
    if evidence is None:
        notes.append("no evidence file: git_sha, dirty and excluded are null")
    elif not ok:
        reasons = "; ".join(f"{lang}: {b.get('status')} ({b.get('reason')})"
                            for lang, b in sorted((evidence.get("languages") or {}).items()) if isinstance(b, dict))
        notes.append(f"evidence is not ok ({reasons or 'no language block'}): shares and call time are null")
    if gate.get("seed") is None:
        notes.append("the random-order gate did not run: seed is null")
    summary = {
        "schema_version": 1,
        "started_at": ledger.get("started_at"),
        "stopped_at": stopped_at,
        "git_sha": (evidence or {}).get("git_sha"),
        "dirty": (evidence or {}).get("dirty"),
        "runner": ledger.get("runners"),
        "seed": gate.get("seed"),
        "evidence_status": None if evidence is None else ("ok" if ok else "not ok"),
        "counts": None, "kinds": None, "report_only": None,
        "excluded": None, "evidence_tests": None, "shares": None, "warnings": [],
        "concentration": None, "hotspots": [], "call_time": None, "volume": volume, "notes": notes,
    }
    if evidence is not None:
        excluded = {}
        for b in (evidence.get("languages") or {}).values():
            for e in (b.get("excluded") or []) if isinstance(b, dict) else []:
                excluded[e.get("outcome")] = excluded.get(e.get("outcome"), 0) + 1
        summary["excluded"] = excluded
    if ok:
        summary["evidence_tests"] = sum(len(b.get("tests") or {}) for b in evidence["languages"].values()
                                        if isinstance(b, dict) and b.get("status") == "ok")
        ct = (ledger.get("simplification") or {}).get("call_time") or {}
        summary["call_time"] = {"before_s": ct.get("before_s"), "after_s": ct.get("after_s")}
        if ct.get("before_s") is None or ct.get("after_s") is None:
            notes.append("ledger simplification.call_time has no before or after total (Step 10 did not measure it)")
    if plan is None:
        notes.append("no simplification plan (Phase B did not plan): counts, kinds and concentration are null")
        return summary
    cands = [c for c in plan.get("review_candidates", []) if isinstance(c, dict)]
    counts, kinds, ids = {}, {}, {}
    for c in cands:
        crit = c.get("criterion")
        counts[crit] = counts.get(crit, 0) + 1
        if isinstance(c.get("kind"), str):
            name = f"{crit}/{c['kind']}"
            kinds[name] = kinds.get(name, 0) + 1
        if crit in REVIEW and c.get("file") and c.get("test_name") and not _report_only(c):
            ids.setdefault(crit, set()).add(f"{c['file']}::{c['test_name']}")
    summary.update(counts=counts, kinds=kinds, report_only=report_only_counts(plan))
    summary["hotspots"] = [c for c in cands if c.get("criterion") == "hotspot"]
    if not summary["hotspots"]:
        notes.append("no hotspot entry (the probe found none or did not run): hotspots is []")
    by_count, by_call, seen = {}, {}, set()
    for c in cands:
        if c.get("criterion") not in REVIEW or not c.get("file") or not c.get("test_name") or _report_only(c):
            continue  # a report-only test is never ticketed: it adds to no share and no concentration
        module = _module(c["file"])
        by_count[module] = by_count.get(module, 0) + 1
        tid = f"{c['file']}::{c['test_name']}"
        if isinstance(c.get("call_s"), (int, float)) and tid not in seen:  # a test in coverage-subset and cost counts once
            seen.add(tid)
            by_call[module] = by_call.get(module, 0.0) + c["call_s"]
    summary["concentration"] = {"by_candidates": _top(by_count, "candidates"), "by_call_s": _top(by_call, "call_s")}
    total = summary["evidence_tests"]
    if ok and total:
        summary["shares"] = {crit: round(len(s) / total, 4) for crit, s in sorted(ids.items())}
        summary["warnings"] = [
            f"{crit} flags {share:.0%} of evidence tests: criterion is not discriminating on this suite;"
            " triage by module and hotspot before per-test review"
            for crit, share in summary["shares"].items() if share > NOT_DISCRIMINATING]
    elif ok:
        notes.append("evidence holds no test: shares are null")
    return summary


def volume_gate(count, tracker=None, unattended=False):
    """The Step 11 volume gate for `count` staged tickets (ADR-0080 Decision 3).

    `publish` at or under the threshold; above it `ask` in an interactive run, `triage`
    (option (b)) in an unattended run on the local tracker, and `drafted` in an unattended
    run on a real tracker. None when the tracker kind is not given.
    """
    if tracker is None:
        return None
    if count <= VOLUME_THRESHOLD:
        return "publish"
    if not unattended:
        return "ask"
    return "triage" if tracker == "local" else "drafted"


CHOICE_ACTIONS = {"a": "publish", "b": "triage", "c": "declined"}  # volume gate answer -> action


def gate_choice(action, choice=None, recorded=None):
    """(action, choice, chosen_by) once the volume gate's answer is applied.

    `action` is `volume_gate`'s; `choice` is the answer given now (`--choice`, or `b` for
    `--triage`); `recorded` is ledger `publish.volume` from an earlier render of this run.
    A human answer wins: the answer given now, else a recorded one with `chosen_by: asked`
    (so a resume does not ask again), sets the action from `CHOICE_ACTIONS` at any ticket
    count and in any attendance, with `chosen_by: asked`. A recorded unattended default is
    never reused: the gate is computed again, so an interactive resume still asks. With no
    human answer, `triage` and `drafted` record `chosen_by: unattended-default` (choice `b`
    for `triage`, none for `drafted`). Without a tracker (`action` None) there is no gate:
    the action stays None and an explicit `choice` is recorded with `chosen_by: asked`;
    `render` still stages option (b) for choice `b`.
    """
    recorded = recorded if isinstance(recorded, dict) else {}
    if action is None:
        return None, choice, ("asked" if choice else None)
    if choice is None and recorded.get("chosen_by") == "asked" and recorded.get("choice") in CHOICE_ACTIONS:
        choice = recorded["choice"]
    if choice is not None:
        return CHOICE_ACTIONS[choice], choice, "asked"
    if action in ("triage", "drafted"):
        return action, ("b" if action == "triage" else None), "unattended-default"
    return action, None, None


def render(root, ledger, plan, index, project, stopped_at, stage, *, triage=False, tracker=None,
           unattended=False, git_sha=None, choice=None):
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
    full = group_tickets(items)  # the queue file always lists every ticket
    action, choice, chosen_by = gate_choice(volume_gate(len(full), tracker, unattended),
                                            choice or ("b" if triage else None),
                                            (ledger.get("publish") or {}).get("volume"))
    volume = {"tickets": len(full), "threshold": VOLUME_THRESHOLD, "over": len(full) > VOLUME_THRESHOLD,
              "action": action, "choice": choice, "chosen_by": chosen_by}
    triage = bool(choice == "b" or action == "triage")
    tickets = group_tickets(items, triage=True) if triage else full
    superseded = superseded_slugs(root, slug, index)
    _write_text(root / QUEUE, queue_body(started_at, project, full, tracked, superseded, stopped_at))
    staged = bool(stage and not stopped_at and tickets)
    if staged:
        base = root / ".scratch" / slug
        drafts = base / "draft-issues"
        if drafts.is_dir():
            for old in drafts.glob("*.md"):
                old.unlink()
        _write_text(base / "spec.md", spec_body(started_at, project, tickets, tracked, git_sha))
        paths = []
        for t in tickets:
            rel = f".scratch/{slug}/draft-issues/{t['nn']}-{t['slug']}.md"
            _write_text(root / rel, ticket_body(t, slug, ledger, git_sha))
            paths.append(rel)
        _write_text(base / "manifest.md", "---\nartifact-type: tickets\n---\n" + "\n".join(paths) + "\n")
        write_atomic(base / "tickets.json", {"slug": slug, "tickets": [
            {"nn": t["nn"], "slug": t["slug"], "keys": [], "criterion": t["criterion"]} if t["category"] == "triage"
            else {"nn": t["nn"], "slug": t["slug"], "keys": [i["key"] for i in t["items"]]}
            for t in tickets]})
    return {
        "slug": slug,
        "title": run_title(started_at),
        "queue": QUEUE,
        "summary": SUMMARY,
        "staged": staged,
        "triage": triage,
        "volume": volume,
        "items": len(items),
        "tickets": [{"nn": t["nn"], "slug": t["slug"], "title": t["title"], "label": t["label"],
                     "blocked_by": t["blocked_by"], "ids": len(t["items"])} for t in tickets],
        "already_tracked": [{"key": k, "ref": ref} for k, ref in tracked],
        "superseded": superseded,
        "report_only": report_only_counts(plan),
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
    # triage tickets (option (b)) have `keys: []`: credited by name or by their criterion's
    # TRIAGE_PHRASE in the body, never indexed
    triage = {f"{t['nn']}-{t['slug']}": _triage_marker(t.get("criterion")) for t in doc["tickets"] if not t["keys"]}
    credited, unmatched = {}, []  # ref -> keys its body names; names with no body file
    triaged = {}  # triage ticket name -> ref
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
        for tname, marker in triage.items():
            if tname not in triaged and (tname == name or (marker is not None and marker in body)):
                triaged[tname] = ref
                credited.setdefault(ref, [])
    done = {k for ks in credited.values() for k in ks}
    for ref, ks in credited.items():
        for key in ks:
            index.setdefault("entries", {})[key] = {"ref": ref, "slug": slug}
    unpublished = [k for k in keys if k not in done] + [n for n in triage if n not in triaged]
    status = "published" if not unpublished else ("drafted" if not credited else "partial")
    tickets = [{"ref": ref, "keys": ks} for ref, ks in credited.items()]
    return index, {"status": status, "tickets": tickets, "unpublished": unpublished, "unmatched": unmatched}


def _triage_marker(criterion):
    """Text only the triage ticket of `criterion` holds, so a renamed one still matches its body; None without one."""
    return TRIAGE_PHRASE.format(criterion=criterion) if criterion else None


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
    r.add_argument("--evidence", help=f"evidence file (default: ledger evidence.file, else {EVIDENCE})")
    r.add_argument("--tracker", choices=["local", "real"], help="tracker kind, for the volume gate")
    r.add_argument("--unattended", action="store_true", help="the run is unattended (volume gate defaults)")
    answer = r.add_mutually_exclusive_group()  # --triage is an alias of --choice b
    answer.add_argument("--triage", action="store_true", help="volume gate option (b), the same as --choice b")
    answer.add_argument("--choice", choices=sorted(CHOICE_ACTIONS), help="the user's volume gate answer; wins over the gate's default")
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
        ledger = _load(root / a.ledger, {})
        # A missing plan is normal when Phase B never ran: it holds no items.
        plan = _load(root / a.plan, None) if a.plan else None
        evidence = _load(root / (a.evidence or (ledger.get("evidence") or {}).get("file") or EVIDENCE), None)
        git_sha = (evidence or {}).get("git_sha")
        if a.rekey_only:
            if should_rekey(a.stopped_at):
                index["entries"] = rekey_index(index, ledger)
            out = {"rekeyed": index.get("entries", {}) != before, "summary": SUMMARY}
            volume = None
        else:
            if not a.plan:
                ap.error("render needs --plan unless --rekey-only")
            out = render(root, ledger, plan or {}, index, a.project_name or root.name, a.stopped_at, a.stage,
                         triage=a.triage, tracker=a.tracker, unattended=a.unattended, git_sha=git_sha, choice=a.choice)
            volume = out["volume"]
        summary_path = root / SUMMARY  # written on every Step 11 path
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(summary_path, run_summary(ledger, plan, evidence, a.stopped_at, volume))
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
