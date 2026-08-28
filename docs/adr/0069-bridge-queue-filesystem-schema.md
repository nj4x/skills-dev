---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0069: Cline Bridge Queue Filesystem Schema and Layout

> Lineage exempt: this repository is the skills-dev tooling workspace itself and carries no
> `.data/requirements/` FS/SRS corpus. This ADR records a decision about the workspace's own
> internal tooling, not a product capability traceable to a requirement.

**Status**: Approved

**Context**

The Cline bridge (map issue #37) needs an on-disk queue so a capable MCP-equipped agent can submit questions and a constrained Cline-side worker can claim and answer them asynchronously. Issue #39 designed the queue's format, filesystem layout, and locking discipline to satisfy requirements from ADR-0068 (loop durability), with coordination points for #40 (MCP interface), #41 (loop workflow), and #46 (trust boundary).

The key constraint: this repository runs on macOS, which lacks GNU `flock(1)` (requires Homebrew `util-linux`). Bash and Python must share locking primitives; Python has `fcntl.flock`, bash has only `mkdir`-atomicity or BSD `/usr/bin/shlock`. A Python-only writer (MCP server, `bridge` CLI) sidesteps this by moving locking entirely into Python, leaving bash to read only.

**Decision**

## Layout and Directory Structure

```
~/.cline-bridge/
├── queue/
│   ├── pending/          # waiting to be claimed
│   ├── claimed/          # claimed by a worker, awaiting answer
│   ├── answered/         # answered, awaiting pickup by submit_request
│   └── failed/           # timeout expired without answer (terminal)
├── tmp/                  # staging area for atomic writes
└── worker.alive          # heartbeat file, 0 bytes, mtime-driven (ADR-0068 point 2)
```

The root path is `os.path.expanduser(os.getenv("CLINE_BRIDGE_DIR", "~/.cline-bridge"))`. Directories are created lazily with `os.makedirs(..., exist_ok=True)` on first access. This follows the established `~/.mcp-vectors/<subsystem>` precedent in this repository's existing MCP servers.

## File Naming and Ordering

Request files are named `<unix-millis>-<short-uuid>.json`, e.g. `1756205412345-a3f9c2d1.json`. Lexical sort of filenames gives FIFO order by submission time with no index file needed. The UUID segment (8 hex chars) provides uniqueness when multiple requests arrive within the same millisecond.

**Example**: `~/.cline-bridge/queue/pending/1756205412345-a3f9c2d1.json`

## Record Schema

A request record carries only immutable data and timestamps; status is encoded in its containing directory, not in the record itself. This eliminates torn-state windows where directory and field disagree after a partial write.

```json
{
  "id": "1756205412345-a3f9c2d1",
  "question": "What does this code do?",
  "submitted_at": "2026-08-26T14:30:12.345Z",
  "claimed_at": null,
  "answered_at": null,
  "answer": null
}
```

**Fields**:
- `id` (string): Matches the filename stem. Immutable. Makes the record self-describing if ever copied out of its directory.
- `question` (string): Arbitrary text from the capable agent. Immutable.
- `submitted_at` (ISO 8601 timestamp): Set when the record is created. Immutable.
- `claimed_at` (ISO 8601 timestamp or null): Set to the current timestamp when the record moves from `pending/` to `claimed/`. Null until claimed. Used for diagnostics and staleness detection.
- `answered_at` (ISO 8601 timestamp or null): Set when the worker writes the answer. Null until answered.
- `answer` (string or null): The worker's response. Null until answered. May contain multiple paragraphs or structured text; it is treated as opaque payload on both ends.

**State machine**:
1. Created in `pending/` with `claimed_at` and `answered_at` both null, `answer` null.
2. On claim, moved to `claimed/` and `claimed_at` is set.
3. On answer, record in `claimed/` is updated in place with `answered_at` and `answer` set, then moved to `answered/`.
4. On timeout (180s after submission per ADR-0068 point 5), record in `claimed/` is moved to `failed/` *without* writing an answer. `answered_at` and `answer` remain null.

**No claimant identity is stored** — ADR-0068 point 4 requires a restarted worker carry no state, so a stable claimant id has no meaning.

## Write Safety

All writes to queue records happen in two stages to prevent torn writes:

1. Write to `~/.cline-bridge/tmp/<id>.tmp`
2. Atomic `os.rename(<tmp-path>, <final-path>)` to move into the queue

The `tmp/` directory is a sibling of `queue/` on the same filesystem, guaranteeing the rename is atomic. `tmp/` is cleaned opportunistically (see below) and is never part of the queue itself.

## Claim Primitive

Claiming a request is an atomic operation to prevent two workers from claiming the same request (see Q5 in ticket #39):

1. Acquire exclusive lock on `~/.cline-bridge/queue.lock` using `fcntl.flock(LOCK_EX)`.
2. Scan `pending/` for the oldest file (lexically smallest filename).
3. If found, `os.rename(pending/<oldest>, claimed/<oldest>)` and set the file's `claimed_at` field in a fresh write.
4. Release the lock.
5. Return the claimed record, or None if `pending/` is empty.

The lock is released immediately after the rename, and the kernel automatically releases it on process death, so there is no stale-lock problem. The rename is a single atomic syscall with no intermediate state, so there is no window for a torn claim.

## Heartbeat File

The worker's liveness is a single file at `~/.cline-bridge/worker.alive`, zero bytes, with mtime as the signal (per ADR-0068 point 2). The CLI touches this file on *every* invocation of `claim-next`, including empty-queue polls. This is the only file updated on every poll; queue records are left unchanged when no work is claimed.

The heartbeat is a sibling of `queue/`, not a record within it, so the queue directory remains free of non-records and a sweep can never trip over it.

## Retention and Garbage Collection

Terminal records (`answered/` and `failed/`) are kept for 7 days, then deleted opportunistically. The garbage collection sweep runs at the top of every `submit_request` call (before the 180s wait begins):

```python
now = time.time()
for terminal_dir in [answered_dir, failed_dir]:
    for filename in os.listdir(terminal_dir):
        path = os.path.join(terminal_dir, filename)
        mtime = os.stat(path).st_mtime
        if now - mtime > 7 * 24 * 3600:  # 7 days
            os.remove(path)
```

This ensures old records do not accumulate unbounded. Terminal records are never deleted on read, so the post-mortem trail remains available for debugging if a question fails.

## Worked Example

**Initial state**: `pending/` contains one submitted request.

```
~/.cline-bridge/queue/pending/1756205412345-a3f9c2d1.json

{
  "id": "1756205412345-a3f9c2d1",
  "question": "Explain the claim primitive in ADR-0069.",
  "submitted_at": "2026-08-26T14:30:12.345Z",
  "claimed_at": null,
  "answered_at": null,
  "answer": null
}
```

**Worker calls `bridge claim-next`**: The CLI acquires the lock, finds the oldest pending file, moves it to `claimed/`, and sets `claimed_at`.

```
~/.cline-bridge/queue/claimed/1756205412345-a3f9c2d1.json

{
  "id": "1756205412345-a3f9c2d1",
  "question": "Explain the claim primitive in ADR-0069.",
  "submitted_at": "2026-08-26T14:30:12.345Z",
  "claimed_at": "2026-08-26T14:30:13.200Z",
  "answered_at": null,
  "answer": null
}
```

`pending/` is now empty. The worker processes the question.

**Worker calls `bridge answer <id> <answer-text>`**: The CLI writes the answer into the record and moves it to `answered/`.

```
~/.cline-bridge/queue/answered/1756205412345-a3f9c2d1.json

{
  "id": "1756205412345-a3f9c2d1",
  "question": "Explain the claim primitive in ADR-0069.",
  "submitted_at": "2026-08-26T14:30:12.345Z",
  "claimed_at": "2026-08-26T14:30:13.200Z",
  "answered_at": "2026-08-26T14:30:45.890Z",
  "answer": "The claim primitive is an atomic claim operation..."
}
```

**Meanwhile, `submit_request` polls for the answer**: Every 250 ms, it checks for the file at `answered/1756205412345-a3f9c2d1.json`. When found, it reads the record, extracts the answer, and returns it to the caller. The record remains in `answered/` for 7 days, then is deleted by a later garbage collection sweep.

**Timeout scenario** (if the worker dies while the request is in `claimed/`): After 180 seconds without progress, `submit_request` moves the request to `failed/` and marks its status terminal. The record remains readable for debugging.

```
~/.cline-bridge/queue/failed/1756205412345-a3f9c2d1.json

{
  "id": "1756205412345-a3f9c2d1",
  "question": "...",
  "submitted_at": "2026-08-26T14:30:12.345Z",
  "claimed_at": "2026-08-26T14:30:13.200Z",
  "answered_at": null,
  "answer": null
}
```

(Terminal timestamp fields could be added for completeness, but the directory move and file mtime are sufficient for auditing.)

## CLI Surface

The `bridge` CLI exposes these subcommands (detailed in #40):
- `claim-next [--wait N]`: atomically claim the oldest pending request and return its id + question. Without `--wait`, returns immediately if the queue is empty. With `--wait N`, blocks the server-side lock-and-scan loop for up to N seconds, returning as soon as work arrives or an empty result if N seconds elapse (see #41).
- `answer <id> [--file <path>]`: write the answer and move the request to `answered/`. Answer text either from the `<text>` argument (inline, deprecated) or read from `<path>` (safer, see #41).
- `status`: list pending/claimed/answered/failed counts (for diagnostics)

## Consequences

- **Single Python process owns the lock.** Bash and other languages cannot claim; they must shell out to the Python CLI. This is acceptable because Cline already shells out to the CLI for every operation, so there is no new overhead.
- **No state recovery after a hard crash.** If the MCP server process dies mid-write to `tmp/`, the `.tmp` file remains and is garbage-collected by the next process to run. No metadata file tracks half-finished operations — the queue is self-consistent by construction.
- **GC is opportunistic, not scheduled.** If `submit_request` never runs again after a question times out, its record will remain indefinitely. A cron job or daemon could run GC more aggressively, but is not required for v1.
- **Record payload is opaque text.** Both ends treat question and answer as literal prompt/answer content, never evaluated as shell commands (trust boundary decisions belong to #46).

