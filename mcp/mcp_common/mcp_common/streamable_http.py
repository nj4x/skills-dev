"""Shared CLI helper for running MCP servers with optional Streamable HTTP transport.

Supports stdio (default) and streamable HTTP with optional TLS.
"""

from __future__ import annotations

import argparse
import asyncio
import httpx
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class SupportsStreamableHTTP(Protocol):
    """Protocol for FastMCP-like servers used by the helper."""

    settings: Any

    def run(self, transport: str = "stdio", mount_path: str | None = None) -> None:
        ...

    def streamable_http_app(self):
        ...


@dataclass
class StreamableHttpArgs:
    """Parsed CLI args for streamable HTTP transport."""

    transport: str
    host: str
    port: int
    path: str
    tls_cert: str | None
    tls_key: str | None
    json_response: bool
    stateless_http: bool
    macro_http: bool
    macro_https: bool
    client_mode: bool
    client_url: str | None
    client_tool: str | None
    client_params: dict[str, Any]
    client_help: bool
    show_help: bool


def build_streamable_http_parser(default_path: str) -> argparse.ArgumentParser:
    """Create an argparse parser with shared streamable HTTP options."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-h",
        "--help",
        action="store_true",
        help="Show this help message and exit.",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Shortcut for streamable HTTP with default host/port/path.",
    )
    parser.add_argument(
        "--https",
        action="store_true",
        help="Shortcut for streamable HTTPS with default host/port/path and a self-signed cert.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport to use (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind for streamable HTTP (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8005,
        help="Port to bind for streamable HTTP (default: 8005).",
    )
    parser.add_argument(
        "--path",
        default=default_path,
        help=f"Streamable HTTP path (default: {default_path}).",
    )
    parser.add_argument(
        "--tls-cert",
        default=None,
        help="Path to TLS certificate PEM file (optional; enables HTTPS).",
    )
    parser.add_argument(
        "--tls-key",
        default=None,
        help="Path to TLS private key PEM file (required if --tls-cert is set).",
    )
    parser.add_argument(
        "--json-response",
        action="store_true",
        help="Enable JSON response mode for streamable HTTP.",
    )
    parser.add_argument(
        "--stateless-http",
        action="store_true",
        help="Enable stateless streamable HTTP mode.",
    )
    parser.add_argument(
        "--client",
        action="store_true",
        help="Run in client mode against a running MCP server.",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Client mode only: server URL (defaults to http://{host}:{port}{path}).",
    )
    parser.add_argument(
        "--tool",
        default=None,
        help="Client mode only: tool name to invoke.",
    )
    return parser


def parse_streamable_http_args(
    parser: argparse.ArgumentParser,
    default_path: str,
) -> StreamableHttpArgs:
    """Parse args and return a typed StreamableHttpArgs instance."""
    args, unknown = parser.parse_known_args()
    if args.help and not args.client:
        parser.print_help()
        raise SystemExit(0)
    client_params = _parse_client_params(unknown)
    return StreamableHttpArgs(
        transport=args.transport,
        host=args.host,
        port=args.port,
        path=args.path,
        tls_cert=args.tls_cert,
        tls_key=args.tls_key,
        json_response=args.json_response,
        stateless_http=args.stateless_http,
        macro_http=args.http,
        macro_https=args.https,
        client_mode=args.client,
        client_url=args.url,
        client_tool=args.tool,
        client_params=client_params,
        client_help=args.client and args.help,
        show_help=args.help,
    )


def _parse_client_params(unknown_args: list[str]) -> dict[str, Any]:
    """Parse --param:<name> value pairs from unknown args."""
    params: dict[str, Any] = {}
    idx = 0
    while idx < len(unknown_args):
        token = unknown_args[idx]
        if token.startswith("--param:"):
            name = token.split(":", 1)[1]
            if not name:
                raise ValueError("Invalid --param: syntax; expected --param:<name> <value>")
            if idx + 1 >= len(unknown_args):
                raise ValueError(f"Missing value for --param:{name}")
            raw_value = unknown_args[idx + 1]
            params[name] = _parse_param_value(raw_value)
            idx += 2
            continue
        idx += 1
    return params


def _parse_param_value(raw_value: str) -> Any:
    """Parse a parameter value, attempting JSON first."""
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


async def run_client_mode(args: StreamableHttpArgs, default_http_port: int = 8005, default_https_port: int = 4430) -> None:
    """Run client mode against a running MCP streamable HTTP server."""
    _configure_client_logging()
    
    # Check if this is help request without server (list all available servers)
    if args.client_help and not args.client_tool and not args.client_url:
        # Try to get server list from the wrapper's servers-info endpoint
        servers_info_url = f"http://{args.host}:{args.port}/mcp-wrapper/servers-info"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(servers_info_url, timeout=10.0)
                if response.status_code == 200:
                    servers_data = response.json()
                    _print_servers_info(servers_data)
                    return
                elif response.status_code == 400:
                    # Check if this is a configuration/auth error that suggests no servers are configured
                    error_text = response.text.lower()
                    if any(keyword in error_text for keyword in ['authentication', 'access key', 'aws', 'x.509', 'certificate']):
                        print("NO wrapped MCP servers are configured yet", file=sys.stderr)
                    else:
                        print(f"Failed to get servers info: {response.status_code} {response.text}", file=sys.stderr)
                        print("Make sure the mcp-wrapper server is running and properly configured.", file=sys.stderr)
                else:
                    print(f"Failed to get servers info: {response.status_code} {response.text}", file=sys.stderr)
                    print("Make sure the mcp-wrapper server is running.", file=sys.stderr)
        except httpx.ConnectError as e:
            if "name or service not known" in str(e).lower() or "nodename nor servname provided" in str(e).lower():
                print("NO wrapped MCP servers are configured yet", file=sys.stderr)
            else:
                print("Failed to connect to mcp-wrapper server.", file=sys.stderr)
                print("Make sure the mcp-wrapper server is running.", file=sys.stderr)
        except httpx.TimeoutException:
            print("Timeout connecting to mcp-wrapper server.", file=sys.stderr)
            print("Make sure the mcp-wrapper server is running and responding.", file=sys.stderr)
        except Exception as e:
            # Check if this looks like an AWS authentication error
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ['authentication', 'access key', 'aws', 'x.509', 'certificate']):
                print("NO wrapped MCP servers are configured yet", file=sys.stderr)
            else:
                print(f"Failed to connect to mcp-wrapper server: {e}", file=sys.stderr)
                print("Make sure the mcp-wrapper server is running.", file=sys.stderr)
        raise SystemExit(1)
    
    if not args.client_help and not args.client_tool:
        print("Client mode requires --tool unless --help is provided", file=sys.stderr)
        raise SystemExit(2)
    
    # Construct URL with server-specific default ports when no custom URL or port is provided
    if args.client_url:
        url = args.client_url
    else:
        # Use server-specific default port if user didn't specify a custom port (default argparse value is 8005)
        port = args.port
        if port == 8005 and default_http_port != 8005:  # Only override if server has custom default
            port = default_http_port
        url = f"http://{args.host}:{port}{args.path}"
    exit_code = 0
    async with streamable_http_client(url) as streams:
        read_stream, write_stream, _get_session_id = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            if args.client_help:
                tools = await session.list_tools()
                for tool in tools.tools:
                    _print_tool_help(tool)
                return
            if not args.client_tool:
                raise ValueError("Client mode requires --tool unless --help is provided")
            result = await session.call_tool(args.client_tool, args.client_params)
            exit_code = _print_tool_result(args.client_tool, result)
            if exit_code:
                await _print_tool_parameters(session, args.client_tool)
    if exit_code:
        raise SystemExit(exit_code)


def _configure_client_logging() -> None:
    """Ensure client logs do not pollute stdout."""
    logging.getLogger().setLevel(logging.WARNING)
    for logger_name in (
        "httpx",
        "httpcore",
        "mcp.client.streamable_http",
        "mcp.client",
        "mcp.server",
        "mcp-wiki",
        "mcp-vectors",
    ):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _print_tool_help(tool: Any) -> None:
    """Render tool help with clear separation and parameter metadata."""
    print(f"\n=== {tool.name} ===")
    description = tool.description or ""
    if description:
        print(description)
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
    if not schema:
        return
    _print_tool_parameters_block(schema)


def _print_tool_parameters_block(schema: dict[str, Any], *, stderr: bool = False) -> None:
    """Print a tool schema's parameters block."""
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    output = sys.stderr if stderr else sys.stdout
    if properties:
        print("Parameters:", file=output)
    else:
        print("Parameters: none", file=output)
    for prop, prop_schema in properties.items():
        prop_schema = prop_schema if isinstance(prop_schema, dict) else {}
        param_type = _format_schema_type(prop_schema)
        optionality = "required" if prop in required else "optional"
        desc = prop_schema.get("description", "")
        suffix = f" - {desc}" if desc else ""
        print(f"  - {prop} ({param_type}, {optionality}){suffix}", file=output)


async def _print_tool_parameters(session: ClientSession, tool_name: str) -> None:
    """Print tool parameters for a failed tool call."""
    try:
        tools = await session.list_tools()
    except Exception:
        return
    tool = next((tool for tool in tools.tools if tool.name == tool_name), None)
    if not tool:
        return
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
    if not schema:
        return
    print("", file=sys.stderr)
    _print_tool_parameters_block(schema, stderr=True)


def _format_schema_type(schema: dict[str, Any]) -> str:
    """Format a JSON schema type for display."""
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " | ".join(str(t) for t in schema_type)
    if schema_type == "array":
        items = schema.get("items", {})
        item_type = _format_schema_type(items) if isinstance(items, dict) else "any"
        return f"array<{item_type}>"
    if schema_type:
        return str(schema_type)
    any_of = schema.get("anyOf") or schema.get("oneOf")
    if any_of and isinstance(any_of, list):
        return " | ".join(_format_schema_type(opt) for opt in any_of if isinstance(opt, dict))
    return "any"


def _print_tool_result(tool_name: str, result: Any) -> int:
    """Pretty-print tool call results for client mode."""
    is_error = getattr(result, "is_error", None)
    if is_error is None:
        is_error = getattr(result, "isError", False)
    if is_error:
        print(f"Error executing tool {tool_name}:", file=sys.stderr)
        structured = getattr(result, "structured_content", None)
        if structured is None:
            structured = getattr(result, "structuredContent", None)
        if structured is not None:
            print(json.dumps(structured, indent=2, ensure_ascii=False), file=sys.stderr)
        else:
            content_blocks = getattr(result, "content", None)
            if content_blocks is None:
                content_blocks = getattr(result, "content", [])
            for block in content_blocks:
                text = getattr(block, "text", None)
                if text:
                    _print_error_text(text, tool_name)
        return 1

    structured = getattr(result, "structured_content", None)
    if structured is None:
        structured = getattr(result, "structuredContent", None)
    if structured is not None:
        print(json.dumps(structured, indent=2, ensure_ascii=False))
        return 0

    content_blocks = getattr(result, "content", None)
    if content_blocks is None:
        content_blocks = getattr(result, "content", [])
    printed = False
    for block in content_blocks:
        text = getattr(block, "text", None)
        if text:
            print(text)
            printed = True
    if not printed:
        print(result)
    return 0


def _print_error_text(text: str, tool_name: str | None = None) -> None:
    """Normalize Pydantic error text for readability."""
    normalized = text.replace("\r", "")
    normalized = normalized.replace("\n  Field ", " <- Field ")
    lines = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("For further information"):
            continue
        if tool_name and line.startswith(f"Error executing tool {tool_name}:"):
            continue
        lines.append(line)
    if lines:
        print("\n".join(lines), file=sys.stderr)


def _generate_self_signed_cert(cert_path: Path, key_path: Path) -> None:
    """Generate a self-signed certificate if it doesn't already exist."""
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    if cert_path.exists() and key_path.exists():
        return
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )


def _print_servers_info(servers_data: dict) -> None:
    """Print server information in a user-friendly format."""
    print("Available MCP servers:")
    servers = servers_data.get("servers", [])
    if not servers:
        print("  No servers configured or available.")
        return
    
    for server in servers:
        server_name = server.get("name", "Unknown")
        print(f"\n  {server_name}:")
        tools = server.get("tools", [])
        if not tools:
            print("    No tools available.")
        else:
            for tool in tools:
                tool_name = tool.get("name", "Unknown")
                description = tool.get("description", "")
                if description:
                    print(f"    - {tool_name}: {description}")
                else:
                    print(f"    - {tool_name}")


def run_with_streamable_http(mcp: SupportsStreamableHTTP, args: StreamableHttpArgs, default_http_port: int = 8005, default_https_port: int = 4430) -> None:
    """Run MCP server with stdio or streamable HTTP transport."""
    if args.client_mode:
        asyncio.run(run_client_mode(args, default_http_port, default_https_port))
        return
    if args.macro_http and args.macro_https:
        raise ValueError("--http and --https cannot be used together")

    # Handle --http and --https shortcuts with server-specific default ports
    if args.macro_http:
        args.transport = "streamable-http"
        # Only override port if user didn't specify a custom port
        if args.port == 8005:  # Default argparse value
            args.port = default_http_port

    if args.macro_https:
        args.transport = "streamable-http"
        # Only override port if user didn't specify a custom port
        if args.port == 8005:  # Default argparse value
            args.port = default_https_port
        if not args.tls_cert and not args.tls_key:
            cert_dir = Path(os.getenv("MCP_TLS_DIR", "/tmp/mcp-tls"))
            cert_path = cert_dir / "cert.pem"
            key_path = cert_dir / "key.pem"
            _generate_self_signed_cert(cert_path, key_path)
            args.tls_cert = str(cert_path)
            args.tls_key = str(key_path)
    if args.transport == "stdio":
        mcp.run()
        return

    os.environ.setdefault("MCP_ENABLE_SIGNAL_HANDLERS", "false")

    if args.tls_cert and not args.tls_key:
        raise ValueError("--tls-key is required when --tls-cert is provided")

    # Configure FastMCP settings before building the app
    if hasattr(mcp, "settings"):
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.settings.streamable_http_path = args.path
        mcp.settings.json_response = args.json_response
        mcp.settings.stateless_http = args.stateless_http

    app = mcp.streamable_http_app()

    config_kwargs: dict[str, Any] = {
        "host": args.host,
        "port": args.port,
        "log_level": getattr(mcp.settings, "log_level", "info").lower() if hasattr(mcp, "settings") else "info",
    }

    if args.tls_cert:
        config_kwargs["ssl_certfile"] = args.tls_cert
        config_kwargs["ssl_keyfile"] = args.tls_key

    config = uvicorn.Config(app, **config_kwargs)
    server = uvicorn.Server(config)
    server.run()