# mcp-wrapper

Generic MCP wrapper that proxies a configured MCP server over streamable HTTP.

## Overview

`mcp-wrapper` reads a standard MCP config JSON file, launches the selected server
as a subprocess (stdio), and exposes that server's tools/resources/prompts via
streamable HTTP. It also supports `--client` mode for CLI-based access when full
MCP integration is unavailable.

## Installation

From the repository root:

```bash
uv tool install --force --reinstall mcp/mcp-wrapper
```

## Configuration

Example config JSON:

```json
{
  "mcpServers": {
    "awslabs-dynamodb-mcp-server": {
      "command": "uvx",
      "args": ["awslabs.dynamodb-mcp-server@latest"],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

## Running the Wrapper (Server Mode)

Run a single server:

```bash
mcp-wrapper \
  --config /path/to/cline_mcp_settings.json \
  --server awslabs-dynamodb-mcp-server \
  --http
```

Default HTTP path becomes `/mcp-wrapper/<serverName>` (e.g., `/mcp-wrapper/awslabs-dynamodb-mcp-server`).

Run all servers from the config:

```bash
mcp-wrapper --config /path/to/cline_mcp_settings.json --http
```

Each server is exposed at `/mcp-wrapper/<serverName>`.

### Keep-alive behavior

By default, wrapped MCP servers stay running between client sessions to avoid
re-installing dependencies for every request.

To disable and stop each server after a session ends:

```bash
mcp-wrapper --config /path/to/cline_mcp_settings.json --http --no-keep-alive
```

### Stateless JSON mode default

The wrapper defaults to **stateless JSON streamable HTTP** (no server-side
session tracking and no SSE streaming) to avoid session teardown issues in some
MCP servers. If you need stateful SSE streaming, pass the standard streamable
HTTP flags:

```bash
mcp-wrapper --config /path/to/cline_mcp_settings.json --http --stateful-http --no-json-response
```

## Client Mode (CLI Access)

Assumes the wrapper is already running:

```bash
mcp-wrapper --client --tool list_tables --server awslabs-dynamodb-mcp-server
```

Or provide the URL explicitly:

```bash
mcp-wrapper --client --tool list_tables \
  --url http://127.0.0.1:8005/mcp-wrapper/awslabs-dynamodb-mcp-server
```

List available tools:

```bash
mcp-wrapper --client --help \
  --url http://127.0.0.1:8005/mcp-wrapper/awslabs-dynamodb-mcp-server
```

Call a tool with parameters (repeat `--param:<name> <value>` as needed):

```bash
mcp-wrapper --client --server awslabs-aws-api-mcp-server \
  --tool suggest_aws_commands \
  --param:query "list s3 buckets"
```

Parameter values are parsed as JSON when possible. For example:

```bash
mcp-wrapper --client --server example-server \
  --tool some_tool \
  --param:options '{"limit": 5, "filters": ["a", "b"]}'
```

## Notes

- Wrapper runs in streamable HTTP mode only (no stdio for the wrapper itself).
- If you want HTTPS, provide `--tls-cert` and `--tls-key` (self-signed certs are not auto-generated).
- The child server is launched as a subprocess using the command/args/env from the
  config JSON.