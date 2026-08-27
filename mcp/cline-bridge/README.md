# cline-bridge

A bridge between two agents: a capable, MCP-equipped agent asks a question; a constrained
Cline-side agent — bash only, no MCP, no API access to its model — answers it from its own
inference. They meet at a filesystem queue under `~/.mcp-bridge`.

Design: [ADR-0068](../../docs/adr/0068-cline-bridge-loop-durability-policy.md) (durability),
[ADR-0069](../../docs/adr/0069-bridge-queue-filesystem-schema.md) (queue schema),
[ADR-0070](../../docs/adr/0070-cline-bridge-mcp-tool-interface.md) (tool interface),
[ADR-0071](../../docs/adr/0071-cline-bridge-worker-loop-workflow.md) (worker loop).

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
2. Confirm it is polling: `bridge status` reports `worker=alive` once `claim-next` has run.
3. From the capable agent, call `ask_peer_model("...")`.

## Environment

- `MCP_BRIDGE_DIR` — queue root (default `~/.mcp-bridge`)
- `MCP_BRIDGE_TIMEOUT` — seconds `ask_peer_model` blocks (default `180`)

## Development

```sh
uv run --extra dev pytest
```
