# cline-bridge

A bridge between two agents: a capable, MCP-equipped agent asks a question; a constrained
Cline-side agent — bash only, no MCP, no API access to its model — answers it from its own
inference. They meet at a filesystem queue under `~/.cline-bridge`.

Design: [ADR-0068](../../docs/adr/0068-cline-bridge-loop-durability-policy.md) (durability),
[ADR-0069](../../docs/adr/0069-bridge-queue-filesystem-schema.md) (queue schema),
[ADR-0070](../../docs/adr/0070-cline-bridge-mcp-tool-interface.md) (tool interface),
[ADR-0071](../../docs/adr/0071-cline-bridge-worker-loop-workflow.md) (worker loop),
[ADR-0072](../../docs/adr/0072-watchdog-liveness-in-the-failure-path.md) (watchdog liveness).

## Two sides

| Side | Runs | Surface |
| --- | --- | --- |
| Capable agent | `cline-bridge` MCP server | `ask_peer_model(question)`, blocks up to 180s |
| Worker | Cline task following `worker-prompt.txt` | `bridge claim-next --wait 25`, `bridge answer <id> --file <path>` |

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

1. Start the worker: open a Cline task and paste the contents of `~/.cline-bridge/worker-prompt.txt`
   as the first message. YOLO / auto-approve must be on, or the loop stalls on approval.
2. Start the watchdog, which restarts the worker when it dies:

   ```sh
   nohup ./bridge-watchdog.sh > ~/.cline-bridge/watchdog.log 2>&1 &
   ```

   It copies `worker-prompt.txt` into the bridge root and restarts the Cline task whenever
   `worker.alive` goes stale. Starting it against an already-live worker is safe — it skips
   the startup restart rather than spawning a second worker.
3. Confirm both are up: `bridge status` reports `worker=alive` once `claim-next` has run, and
   `watchdog=alive` once the watchdog's first check has run.
4. From the capable agent, call `ask_peer_model("...")`.

The watchdog has no watchdog of its own (ADR-0068 point 3). If it dies, the system looks
healthy until the next worker death, then stalls; `ask_peer_model` surfaces this as
`watchdog: "offline"` on a `worker_offline` failure (ADR-0072), and `pgrep -f bridge-watchdog.sh`
confirms it from a shell. Restart it by hand.

## Environment

- `CLINE_BRIDGE_DIR` — queue root (default `~/.cline-bridge`)
- `CLINE_BRIDGE_TIMEOUT` — seconds `ask_peer_model` blocks (default `180`)

The MCP server reads these once at process start. Changing either requires restarting the
server's registration (e.g. reconnecting it in the capable agent's client) — a long-lived
process keeps its imported default even after the environment or source changes underneath
it, so a stale server can end up watching a different root than the worker's freshly-spawned
`bridge` CLI calls.

## Development

```sh
uv run --extra dev pytest
```
