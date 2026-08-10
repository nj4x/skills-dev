# Research: Handoff Skill — "Error writing file" Root-Cause Analysis

**Date:** 2026-08-07  
**Scope:** File output section of `session/handoff/SKILL.md` — mktemp template and Write precondition bugs

## Summary

The `handoff` skill (`session/handoff/SKILL.md`) fails to save its output on macOS because its "## File Output" section suggests a temp-file recipe (`$TMPDIR/handoff-<random-8-chars>.md`) that a following agent naturally implements as `mktemp /tmp/handoff-XXXXXXXX.md`. Two independent, compounding defects then guarantee failure. First, **BSD `mktemp` (macOS) only substitutes *trailing* `X`s**; because `.md` follows the `X`s, the template is treated literally, so `mktemp` creates a file literally named `handoff-XXXXXXXX.md` and prints that literal path (verified on this machine). Second — and this is the central bug — the skill's whole strategy of **pre-creating a temp file and *then* using the `Write` tool to fill it** is incompatible with the Claude Code `Write` tool contract, which requires any **already-existing** path to be `Read` in-session before it can be written. Every path the agent tried (mktemp literal file, then `tempfile.NamedTemporaryFile(delete=False)`) existed on disk at `Write` time and had never been read, so `Write` refused with "Error writing file." The fix is to stop pre-creating: compute a not-yet-existing path with a pure shell expression that never touches the filesystem, then `Write` directly to it (a new-file write needs no prior `Read`).

## Severity-ranked defect inventory

| # | Severity | Defect | Where | Fix |
|---|----------|--------|-------|-----|
| D1 | **Major** | Pre-create-then-`Write` anti-pattern. The skill implies materializing a temp file first, then filling it with `Write`. This violates the `Write` read-before-overwrite rule for *any* pre-creation method (mktemp or tempfile). Root cause of the terminal failures in transcript steps 2 and 5. | SKILL.md "## File Output" | Choose a non-existent path via a pure-string expression; `Write` directly (new file needs no pre-read). |
| D2 | **Major** | `Write` read-before-overwrite precondition unaddressed. Skill gives no guidance that writing to an existing path requires a prior `Read`, or that a new-file write does not. | SKILL.md "## File Output" | State explicitly: target a fresh path so `Write` creates it; if reusing/overwriting an existing handoff file, `Read` it first. |
| D3 | **Major** | Non-portable / broken `mktemp` template. The `<random-8-chars>` + `.md` phrasing pushes agents to `mktemp /tmp/handoff-XXXXXXXX.md`, where the `.md` suffix follows the `X`s. On BSD/macOS the `X`s are not substituted (literal filename + collision on re-run). | SKILL.md "## File Output" | Do not use `mktemp` for a suffixed name at all (see D1 recipe). If `mktemp` is ever needed, put `X`s trailing: `mktemp /tmp/handoff.XXXXXXXX`, or use `mktemp -t handoff`. |
| D4 | Minor | `<random-8-chars>` wording implies "random block then a fixed suffix," which is exactly the shape BSD `mktemp` mishandles. Even the intent is a trap. | SKILL.md line 95 | Reword to a timestamp/PID-based unique stem with the extension baked into a literal string, not "random chars + suffix." |
| D5 | Minor | Hardcoded `/tmp` in the implemented command vs. the documented `$TMPDIR`. macOS `$TMPDIR` is a per-user `/var/folders/...` path, not `/tmp`; drifting to `/tmp` loses the per-user isolation the doc intends. | transcript steps 1&3 vs. SKILL.md | Use `${TMPDIR:-/tmp}` so it honors `$TMPDIR` when set and falls back to `/tmp`. |
| D6 | Minor | No fallback ordering / error guidance. When the temp write failed the agent flailed (mktemp → retry → python tempfile → retry) instead of following a deterministic recipe. | SKILL.md "## File Output" | Give one canonical recipe plus a single documented fallback (`HANDOFF.md` in repo root), removing improvisation. |

---

## Root cause A — BSD vs GNU `mktemp` template semantics

**Primary source: `man mktemp` on this machine (macOS 14.8, dated August 4, 2022).** Quoted verbatim:

> The template may be any file name with some number of 'Xs' **appended** to it, for example `/tmp/temp.XXXX`. The **trailing** 'Xs' are replaced with the current process number and/or a unique letter combination.

The operative words are **"appended"** and **"trailing."** BSD `mktemp` substitutes only a run of `X`s that sits at the *end* of the template. If any non-`X` character (such as a `.md` extension) follows the `X`s, there are no trailing `X`s, so nothing is substituted and the template is used **literally** — and, because `mktemp` still creates the file, you get a real on-disk file with a literal `X`-filled name.

**Reproduced on this machine** (fresh names, so no stale state):

```
$ out=$(mktemp /tmp/hotest-XXXXXXXX.md); echo "$out"
/tmp/hotest-XXXXXXXX.md            # LITERAL — Xs not substituted, exit 0
$ ls /tmp/hotest-*
-rw-------  /tmp/hotest-XXXXXXXX.md # a real file with the literal name
$ mktemp /tmp/hotest-XXXXXXXX.md    # run again
mktemp: mkstemp failed on /tmp/hotest-XXXXXXXX.md: File exists   # exit 1
```

Compare a template with **trailing** `X`s (correct BSD usage):

```
$ mktemp /tmp/hotest.XXXXXXXX
/tmp/hotest.6aSWaN7Q               # real random substitution
$ mktemp -t handoff
/var/folders/g9/.../T/handoff.DV6j1CyzbA   # -t uses $TMPDIR + adds random tail
```

This **exactly explains transcript steps 1 and 3**: step 1's `mktemp /tmp/handoff-XXXXXXXX.md` printed the literal `/tmp/handoff-XXXXXXXX.md` and created that 0-byte file; step 3's retry then hit `mkstemp failed ... File exists` because the literal file from step 1 was already there. (Confirmed independently: after re-creating and re-running, I observed the identical `mkstemp failed on ...: File exists` message.)

**GNU divergence (portability trap).** The man page on this machine is the OpenBSD/FreeBSD implementation; note its history line: *"A mmktemp utility appeared in OpenBSD 2.1 ... first appeared in FreeBSD 2.2.7. This man page is taken from OpenBSD."* GNU coreutils `mktemp` (typical Linux) is a *different* implementation that, since coreutils 8.1, permits a fixed suffix *after* the trailing `X`s (e.g. `mktemp /tmp/handoff-XXXXXXXX.md` yields `/tmp/handoff-a1b2c3d4.md`). That divergence is precisely why the skill's recipe is dangerous: **it silently works on Linux and silently breaks on macOS.** (BSD confirms it rejects the GNU knob: `mktemp --suffix=.md ...` → `mktemp: unrecognized option '--suffix=.md'`.)

**Correct portable `mktemp` invocations** (if one insists on `mktemp`):
- Trailing `X`s, no suffix: `mktemp /tmp/handoff.XXXXXXXX` (works on both; but yields no `.md` extension).
- `-t` form: `mktemp -t handoff` (honors `$TMPDIR`; no `.md`).
- There is **no** single `mktemp` invocation that portably produces a random name *with* a `.md` suffix across BSD and GNU. This is the deeper reason to abandon `mktemp` here (see root cause C).

## Root cause B — `Write` "Error writing file" after the file already exists

**This is the central bug.** The Claude Code `Write` tool contract in this environment states (verbatim from the tool description):

> If this is an existing file, you MUST use the Read tool first to read the file's contents. This tool will fail if you did not read the file first.

(The sibling `Edit` tool carries the same precondition: *"You must use your Read tool at least once in the conversation before editing. This tool will error if you attempt an edit without reading the file."*) So the rule is: **writing to a path that already exists on disk requires that the path was `Read` earlier in the same session; writing to a genuinely new (non-existent) path needs no prior read** — `Write` creates it.

Applying this to the transcript:
- **Step 2:** `mktemp` had already materialized `/tmp/handoff-XXXXXXXX.md` (a real 0-byte file, per root cause A). `Write` to it → the path exists, was never `Read` → **refused: "Error writing file."**
- **Step 5:** Step 4 ran `tempfile.NamedTemporaryFile(prefix='handoff-', suffix='.md', dir='/tmp', delete=False)`, which **creates the file and leaves it on disk** (`delete=False`), printing `/tmp/handoff-s4nkjfu2.md`. `Write` to it → again the path exists, was never `Read` → **still "Error writing file."**

The transcript itself isolates the variable: between a hypothetical success and step 5 the *only* thing that changed is "the file now physically exists (because `tempfile` created it)." The random-name generation was fixed in step 4, yet `Write` still failed — proving the failure is the read-before-overwrite precondition, not the filename. (No document under `docs/` restates this precondition; the authoritative statement is the `Write`/`Edit` tool contract quoted above. `docs/adr/0038` and `0027` reference *analogous* read-before-write staging discipline for other subsystems, but not the Claude Code `Write` tool rule.)

## Root cause C — the design flaw that makes A and B inevitable

The skill's implied workflow is **(1) create a temp file, then (2) `Write` into it.** Both defects fall out of step (1):

- Pre-creating with `mktemp` walks straight into root cause A (BSD literal-`X` behavior).
- Pre-creating with *anything* (`mktemp`, `python tempfile` with `delete=False`, `touch`, `> file`) walks straight into root cause B, because the pre-created path now exists and `Write` demands a prior `Read` it never did.

`mktemp` and `tempfile` exist to *avoid TOCTOU races by atomically creating* the file — but the `Write` tool does its own file creation, so pre-creating is not only unnecessary, it is actively harmful here. The two tools fight over who creates the file.

**The correct pattern:** compute a not-yet-existing path with a **pure string expression that never touches the filesystem**, then `Write` directly to that path. A new-file write needs no pre-create and no pre-read, so both A and B disappear.

**Recommended portable recipe** (no filesystem touch until `Write` runs; works on macOS and Linux):

```
${TMPDIR:-/tmp}/handoff-$(date +%Y%m%d-%H%M%S)-$$.md
```

- `${TMPDIR:-/tmp}` honors the per-user macOS `$TMPDIR` (`/var/folders/...`) and falls back to `/tmp` on systems that don't set it — fixing D5. (On macOS `$TMPDIR` has a trailing `/`; the resulting `//` is harmless, but `"${TMPDIR:-/tmp}"` with the literal `/tmp` fallback keeps it clean.)
- `date +%Y%m%d-%H%M%S` + `$$` (shell PID) yields a unique, human-readable stem with **no `X` placeholders**, so no `mktemp` semantics apply — sidestepping root cause A entirely. (`$RANDOM` is an acceptable alternative in `bash`/`zsh`.)
- The `.md` extension is a plain literal in the string, not a suffix `mktemp` must preserve.
- Crucially: **run the expression only to obtain the string** (e.g. `echo` it, or inline it into the `Write` call). Do **not** `touch`/`>` it. Then call `Write` with that path — it does not yet exist, so `Write` creates it with no prior `Read`.

