"""Find shared cost causes (hotspots) behind the slowest cost candidates (Step 8, ADR-0080).

Usage:
  python hotspot_probe.py select --candidates FILE
  python hotspot_probe.py analyze --root P [--profile ID=FILE ...] [--failed ID=REASON ...]

`select` reads a JSON list of `review_candidates` entries (the `select_candidates.py`
output) or a plan holding `review_candidates`, and prints `{ profile, cost_candidates, warnings }`:
the ids of the top 5 `cost` entries by `call_s` (all of them when there are fewer than 5).
With fewer than 2 cost candidates no profile can make a hotspot: `profile` is empty and
`warnings` says the probe is skipped.

`analyze` reads one cProfile file per profiled test, written by the `hotspot_profile`
pytest plugin, which profiles the test's run protocol (setup, call, teardown) and nothing
else. It prints `{ hotspots, profiled, failed, n, warnings }`. A test's time is the total
time of its profile; a function's share is its cumulative time divided by that total.
pytest and pluggy frames, `builtins` dispatchers such as `next` (which drives a yield
fixture), the test function, and every caller of the test function (decorators, async
runners) are wrappers, never hotspots. Functions are told apart by path, line and name;
the printed name is `<path>:<name>`, or `<path>:<name>:<line>` when two would print the same.

Hotspot rule: with n usable profiles, a function whose share is at least 0.5 in at least
max(2, ceil(n / 2)) of them is a hotspot. One hit is never a hotspot. A profile that is
missing, unreadable, or empty is failed: it is excluded from n and listed under `failed`
with the `--failed` ones. With fewer than 2 usable profiles no hotspot is emitted and
`warnings` says so. A hotspot that another hotspot calls is folded into the hotspot at the
top of that call chain and listed under its `via`, so one shared cause makes one entry. Each entry is
`{ criterion: "hotspot", function, share, tests, subprocess_spawns, via }`: `share` is the
mean share over the profiles the function itself hit, `tests` are the tests it or a `via`
function hit, and `subprocess_spawns` maps every usable
profiled test id to the process spawns its profile counts.
"""
import argparse
import json
import math
import pstats
import re
import sys
from pathlib import Path

from refactor_tests_shared import split_file, strip_params

TOP_N = 5
MIN_SHARE = 0.5
MIN_USABLE = 2
WRAPPER_DIRS = ("/_pytest/", "/pluggy/")
SPAWN = re.compile(r"<built-in method (_posixsubprocess\.fork_exec|_winapi\.CreateProcess"
                   r"|posix\.posix_spawnp?|posix\.system|nt\.system)>")
STDLIB = re.compile(r"/lib/python\d+(\.\d+)?/")


def needed_hits(n):
    """Profiles a function must hold at least MIN_SHARE of to be a hotspot, for n usable profiles."""
    return max(MIN_USABLE, math.ceil(n / 2))


def select(candidates):
    """The top TOP_N `cost` entries by `call_s` descending (ties by id), as test ids."""
    if isinstance(candidates, dict):
        candidates = candidates.get("review_candidates", [])
    cost = [c for c in candidates if isinstance(c, dict) and c.get("criterion") == "cost"
            and isinstance(c.get("call_s"), (int, float))]
    ranked = sorted(cost, key=lambda c: (-c["call_s"], f"{c['file']}::{c['test_name']}"))
    warnings = [] if len(cost) >= MIN_USABLE else [
        f"fewer than {MIN_USABLE} cost candidates ({len(cost)}); hotspot probe skipped, no hotspot emitted"]
    return {"profile": [f"{c['file']}::{c['test_name']}" for c in ranked[:TOP_N]] if not warnings else [],
            "cost_candidates": len(cost), "warnings": warnings}


# --- one profile ------------------------------------------------------------

def _path(filename):
    return filename.replace("\\", "/")


def function_key(func, root):
    """`(path, line, name)` for a pstats key, the path relative to site-packages, stdlib, or root."""
    filename, line, name = func
    if filename == "~":
        return ("~", 0, name)
    path = _path(filename)
    if "/site-packages/" in path:
        path = path.split("/site-packages/", 1)[1]
    elif STDLIB.search(path):
        path = STDLIB.split(path, 1)[-1]
    elif root:
        prefix = _path(str(root)).rstrip("/") + "/"
        path = path.removeprefix(prefix)
    return (path, line, name)


def _short(key):
    path, _line, name = key
    return name if path == "~" else f"{path}:{name}"


def function_names(keys):
    """key -> printed name: `<path>:<name>`, or `<path>:<name>:<line>` when two keys would print the same."""
    keys = set(keys)
    counts = {}
    for k in keys:
        counts[_short(k)] = counts.get(_short(k), 0) + 1
    return {k: _short(k) if counts[_short(k)] == 1 else f"{_short(k)}:{k[1]}" for k in keys}


def _wrapper(func):
    """pytest and pluggy frames, and the `builtins` dispatchers (`next` drives a yield fixture, `exec` runs a module)."""
    filename, _line, name = func
    return (any(d in "/" + _path(filename) for d in WRAPPER_DIRS)
            or (filename == "~" and name.startswith("<built-in method builtins.")))


def _test_frames(stats, test_id):
    file, rest = split_file(strip_params(test_id)[0])
    name = (rest or "").rsplit("::", 1)[-1]
    return [f for f in stats if f[2] == name and (_path(f[0]) == file or _path(f[0]).endswith("/" + file))]


def _ancestors(stats, frames):
    seen, todo = set(frames), list(frames)
    while todo:
        for c in stats.get(todo.pop(), (0, 0, 0, 0, {}))[4]:
            if c not in seen:
                seen.add(c)
                todo.append(c)
    return seen


def read_profile(path, test_id, root):
    """`{ shares: {key: share}, callers: {key: set}, spawns }` for one profile, keyed by `function_key`; raises ValueError when unusable."""
    if not Path(path).is_file():
        raise ValueError("no profile file")
    try:
        loaded = pstats.Stats(str(path))
    except Exception as e:  # pstats raises whatever marshal or its own checks raise on a bad file
        raise ValueError(f"unreadable profile ({type(e).__name__})") from e
    stats, total = loaded.stats, loaded.total_tt
    if total <= 0:
        raise ValueError("empty profile")
    skip = _ancestors(stats, _test_frames(stats, test_id))
    shares, callers, spawns = {}, {}, 0
    for f, (_cc, nc, _tt, ct, f_callers) in stats.items():
        if SPAWN.fullmatch(f[2]):
            spawns += nc
        if f in skip or _wrapper(f):
            continue
        share = min(1.0, ct / total)
        if share > 0:
            key = function_key(f, root)
            shares[key] = max(shares.get(key, 0.0), share)
            callers.setdefault(key, set()).update(function_key(c, root) for c in f_callers if not _wrapper(c))
    return {"shares": shares, "callers": callers, "spawns": spawns}


# --- across profiles --------------------------------------------------------

def find_hotspots(profiles):
    """Hotspot entries from `{ test_id: { shares, callers, spawns } }` (usable profiles only)."""
    n = len(profiles)
    if n < MIN_USABLE:
        return []
    need = needed_hits(n)
    hits = {}
    for test_id in sorted(profiles):
        for name, share in profiles[test_id]["shares"].items():
            if share >= MIN_SHARE:
                hits.setdefault(name, []).append((test_id, share))
    hot = {name for name, h in hits.items() if len(h) >= need}
    callers = {name: set().union(*(p["callers"].get(name, set()) for p in profiles.values())) for name in hot}
    callees = {name: {c for c in hot if name in callers[c] and c != name} for name in hot}
    tops = [name for name in sorted(hot) if not (callers[name] & hot) - {name}]
    vias, covered = {}, set(tops)
    for name in sorted(hot, key=lambda h: (h not in tops, h)):  # a hot cycle no top reaches gets its own entry
        if name in covered and name not in tops:
            continue
        if name not in tops:
            tops.append(name)
            covered.add(name)
        via, todo = set(), list(callees[name])
        while todo:
            c = todo.pop()
            if c not in via and c not in tops:
                via.add(c)
                todo.extend(callees[c])
        vias[name] = via
        covered |= via
    spawns = {t: profiles[t]["spawns"] for t in sorted(profiles)}
    label = function_names(k for p in profiles.values() for k in p["shares"])
    out = []
    for name in tops:
        via = vias[name]
        folded = sorted({t for h in (name, *via) for t, _ in hits[h]})  # a folded hotspot keeps its tests with the top
        out.append({"criterion": "hotspot", "function": label[name],
                    "share": round(sum(s for _, s in hits[name]) / len(hits[name]), 3),
                    "tests": folded, "subprocess_spawns": spawns,
                    "via": sorted(label[v] for v in via)})
    return sorted(out, key=lambda e: e["function"])


def analyze(root, profiles, failed):
    """`{ hotspots, profiled, failed, n, warnings }` for `profiles` (test id -> file) and `failed` (test id -> reason)."""
    usable, failures = {}, [{"id": t, "reason": r} for t, r in failed.items()]
    for test_id, path in profiles.items():
        if test_id in failed:  # named failed by the caller: never also usable
            continue
        try:
            usable[test_id] = read_profile(path, test_id, root)
        except ValueError as e:
            failures.append({"id": test_id, "reason": str(e)})
    warnings = [f"profile of {f['id']} failed ({f['reason']}); left out of n" for f in failures]
    if len(usable) < MIN_USABLE:
        warnings.append(f"fewer than {MIN_USABLE} usable profiles ({len(usable)}); no hotspot emitted")
    return {"hotspots": find_hotspots(usable), "profiled": sorted(usable), "failed": failures,
            "n": len(usable), "warnings": warnings}


def _split_pair(value):
    """(id, value) of `ID=VALUE`: the first `=`, or the first `]=` when that `=` sits in the id's `[params]` suffix."""
    base, _suffix = strip_params(value)
    cut = value.find("=")
    if cut >= len(base):
        cut = value.find("]=", len(base)) + 1
    return (value[:cut], value[cut + 1:]) if cut > 0 else None


def _pairs(values, flag, ap):
    out = {}
    for v in values:
        pair = _split_pair(v)
        if pair is None:
            ap.error(f"{flag} needs ID=VALUE")
        out[pair[0]] = pair[1]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--candidates", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--root", required=True)
    a.add_argument("--profile", action="append", default=[], help="ID=FILE of one cProfile output")
    a.add_argument("--failed", action="append", default=[], help="ID=REASON of a test whose profile run failed")
    args = ap.parse_args(argv)
    if args.cmd == "select":
        out = select(json.loads(Path(args.candidates).read_text(encoding="utf-8")))
    else:
        out = analyze(Path(args.root).resolve(), _pairs(args.profile, "--profile", ap), _pairs(args.failed, "--failed", ap))
    json.dump(out, sys.stdout, indent=1)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
