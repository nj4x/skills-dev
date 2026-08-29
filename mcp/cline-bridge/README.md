# ⚠️ DEPRECATED — cline-bridge

**Deprecated as of 2026-08-28.** Use [`vscode-agent-bridge`](../vscode-agent-bridge) (main branch) instead — production-ready and proven via [live end-to-end round-trip](https://github.com/nj4x/skills-dev/issues/76). See [wayfinder map #67](https://github.com/nj4x/skills-dev/issues/67) for context and [retirement decision #73](https://github.com/nj4x/skills-dev/issues/73).

---

A bridge between two agents: a capable, MCP-equipped agent asks a question; a constrained
Cline-side agent — bash only, no MCP, no API access to its model — answers it from its own
inference. They meet at a filesystem queue under `~/.cline-bridge`.

Design: [ADR-0068](../../docs/adr/0068-cline-bridge-loop-durability-policy.md) (durability),
[ADR-0069](../../docs/adr/0069-bridge-queue-filesystem-schema.md) (queue schema),
[ADR-0070](../../docs/adr/0070-cline-bridge-mcp-tool-interface.md) (tool interface),
[ADR-0071](../../docs/adr/0071-cline-bridge-worker-loop-workflow.md) (worker loop),
[ADR-0072](../../docs/adr/0072-watchdog-liveness-in-the-failure-path.md) (watchdog liveness),
[ADR-0073](../../docs/adr/0073-thread-scoped-queue-directories.md) (threads),
[ADR-0074](../../docs/adr/0074-worker-pool-identity-and-lifecycle.md) (worker pool),
[ADR-0075](../../docs/adr/0075-worker-repo-access-and-delegation-model.md) (repo access),
[ADR-0076](../../docs/adr/0076-async-submit-and-poll-surface.md) (async surface),
[ADR-0077](../../docs/adr/0077-thread-bound-worker-loop.md) (thread-bound loop),
[ADR-0079](../../docs/adr/0079-watchdog-optional-assume-live-pool.md) (optional watchdog).

## Two sides

| Side | Runs | Surface |
| --- | --- | --- |
| Capable agent | `cline-bridge` MCP server | `ask_peer_model(question, repo_path)`, blocks up to 180s; `submit_to_peer_model(question, repo_path, thread_id)` + `poll_peer_model(handle, thread_id)`, non-blocking |
| Worker | Cline task following `worker-prompt.txt` | `bridge claim-worker-slot`, `bridge claim-next --worker N --wait 25`, `bridge answer <id> --worker N --repo-path <path> --file <path>` |

A worker is one VS Code window. `POOL_SIZE` of them run side by side, each holding a slot it
takes at startup and heartbeats to as `worker-N.alive`.

## Install

```sh
cd mcp/cline-bridge
uv sync --extra dev
```

Register the MCP server with the capable agent:

```sh
claude mcp add cline-bridge -- uv --directory /absolute/path/to/mcp/cline-bridge run cline-bridge
```

Install the worker prompt and rules where the Cline instance can reach them:

```sh
mkdir -p ~/.cline-bridge
cp worker-prompt.txt ~/.cline-bridge/worker-prompt.txt
cp .clinerules/bridge-trust-boundary.md <cline-workspace>/.clinerules/
```

The `bridge` CLI must be on the worker's `PATH`. Either `uv tool install .` from this
directory, or point the prompt at `uv --directory <path> run bridge`.

## Run a round trip

The watchdog is off by default (ADR-0079). Start workers on their own:

1. Start each worker: open a VS Code window, start a Cline task, and paste the contents of
   `~/.cline-bridge/worker-prompt.txt` as the first message. YOLO / auto-approve must be on, or
   the loop stalls on approval. One window per worker. Each task calls `bridge
   claim-worker-slot` itself and stops if the pool is already full.
2. Confirm everything is up: `bridge status` reports `worker-N=alive` per slot that has run
   `claim-next`.
3. From the capable agent, call `ask_peer_model("...", repo_path="/abs/path/to/repo")`. The
   worker reads and edits that live tree (ADR-0075) — it is a delegate, not a sandbox, so do
   not point it at a tree holding production credentials.

With no watchdog running, nothing writes `pool.conf`, so the slot ceiling falls back to 10
(ADR-0074). Close a window to shrink the pool; its `worker-N.alive` goes stale on its own and
the slot is reused by the next worker to claim one.

## Optional: the watchdog

`bridge-watchdog.sh` restarts a worker whose `worker-N.alive` goes stale. Run it when you want
worker deaths to self-heal unattended, and accept that it can also restart a worker that is
merely busy — the heartbeat is touched only by `bridge` calls, so a long answer is
indistinguishable from a death (ADR-0079). Two Cline tasks then share one slot.

**Start it before any worker.** It writes `pool.conf`, which is what caps the number of slots;
a worker that starts first can take a slot above `POOL_SIZE` (ADR-0074).

```sh
POOL_SIZE=2 nohup ./bridge-watchdog.sh > ~/.cline-bridge/watchdog.log 2>&1 &
```

It also re-copies `worker-prompt.txt` into the bridge root. It never starts workers on its own:
a slot with no heartbeat file was never claimed, so there is nothing to restart.

While it runs, `bridge status` reports `watchdog=alive`, and `ask_peer_model` fails fast with
`worker_offline` when the whole pool is stale — meaning a restart is already due. It has no
watchdog of its own (ADR-0068 point 3); `pgrep -f bridge-watchdog.sh` confirms it from a shell,
and you restart it by hand. To shrink the pool, stop it before closing a window: a stale
heartbeat with no owner reads as a dead worker, and the restart it triggers can land in another
window and kill a live claim (ADR-0074).

Upgrading from the single-worker layout: `mv ~/.cline-bridge/worker.alive ~/.cline-bridge/worker-1.alive`
first. Also drain `~/.cline-bridge/queue/` — records enqueued before ADR-0075 carry no
`repo_path`, and `claim-next` will not render them.

## Environment

- `CLINE_BRIDGE_DIR` — queue root (default `~/.cline-bridge`)
- `CLINE_BRIDGE_TIMEOUT` — seconds `ask_peer_model` blocks (default `180`)
- `CLINE_BRIDGE_ASYNC_TIMEOUT` — seconds before an unanswered request is swept to `failed/` (default `1800`)
- `POOL_SIZE` — slot ceiling, 1–10, read by the watchdog only (default `1`; with no watchdog
  running nothing writes `pool.conf` and the ceiling falls back to 10)

The MCP server reads these once at process start. Changing either requires restarting the
server's registration (e.g. reconnecting it in the capable agent's client) — a long-lived
process keeps its imported default even after the environment or source changes underneath
it, so a stale server can end up watching a different root than the worker's freshly-spawned
`bridge` CLI calls.

## Development

```sh
uv run --extra dev pytest
```
