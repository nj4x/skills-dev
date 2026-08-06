"""Generic MCP wrapper server that proxies another MCP server over stdio.

Usage:
    mcp-wrapper --config /path/to/cline_mcp_settings.json --server my-server

This wrapper launches the configured MCP server subprocess, connects via stdio,
and exposes the child's tools/resources/prompts via streamable HTTP.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, List, Dict, Optional, TextIO

import anyio
import uvicorn
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, JSONResponse
from starlette.routing import Mount, Route
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server import Server
from mcp.server.connection import Connection
from mcp.server.runner import serve_connection
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.shared.jsonrpc_dispatcher import JSONRPCDispatcher
from mcp.shared.transport_context import TransportContext
from mcp_types import DEFAULT_NEGOTIATED_VERSION
from mcp_common.streamable_http import (
    build_streamable_http_parser,
    parse_streamable_http_args,
    run_client_mode,
)

logger = logging.getLogger("mcp-wrapper")


class MCPLogHandler:
    """Custom stderr handler that captures output and writes to log file."""
    
    def __init__(self, server_name: str, log_file_path: str = "/tmp/mcp-wrapper.log"):
        self.server_name = server_name
        self.log_file_path = log_file_path
        self.original_stderr = sys.stderr
        # Create a pipe for capturing stderr
        self.read_fd, self.write_fd = os.pipe()
        self._start_capture_task()
        
    def _start_capture_task(self) -> None:
        """Start a background task to capture and log stderr output."""
        import threading
        def capture_stderr():
            try:
                with os.fdopen(self.read_fd, 'r', encoding='utf-8', errors='replace') as read_file:
                    while True:
                        line = read_file.readline()
                        if not line:  # EOF
                            break
                        self._log_line(line)
            except Exception as e:
                self.original_stderr.write(f"[LOG ERROR] Failed to capture stderr: {e}\n")
                self.original_stderr.flush()
        
        thread = threading.Thread(target=capture_stderr, daemon=True)
        thread.start()
        
    def _log_line(self, line: str) -> None:
        """Log a single line to both file and stderr."""
        if line.strip():  # Only log non-empty lines
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            log_entry = f"[{timestamp}] [{self.server_name}] {line.strip()}\n"
            
            # Write to log file
            try:
                with open(self.log_file_path, "a", encoding="utf-8") as f:
                    f.write(log_entry)
            except Exception as e:
                # If we can't write to log file, at least write to original stderr
                self.original_stderr.write(f"[{timestamp}] [LOG ERROR] Failed to write to {self.log_file_path}: {e}\n")
        
        # Also write to original stderr for immediate visibility
        self.original_stderr.write(line)
        self.original_stderr.flush()
        
    def fileno(self) -> int:
        """Return the file descriptor for writing."""
        return self.write_fd
        
    def write(self, data: str) -> None:
        """Write data to the pipe (this won't be called by subprocess but kept for compatibility)."""
        # This method exists for compatibility but won't be used by subprocess
        # The subprocess will write directly to the file descriptor
        pass
        
    def flush(self) -> None:
        """Flush is not needed for pipe-based approach."""
        pass


@dataclass
class ChildServerConfig:
    name: str
    command: str
    args: list[str]
    env: dict[str, str]
    disabled: bool


def _load_config(config_path: str | Path, server_name: str) -> ChildServerConfig:
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    raw = json.loads(config_file.read_text(encoding="utf-8"))
    servers = raw.get("mcpServers", {})
    if server_name not in servers:
        available = ", ".join(sorted(servers.keys())) or "<none>"
        raise KeyError(f"Server '{server_name}' not found in config. Available: {available}")
    entry = servers[server_name]
    if entry.get("disabled"):
        raise ValueError(f"Server '{server_name}' is disabled in config")
    command = entry.get("command")
    if not command:
        raise ValueError(f"Server '{server_name}' missing 'command' in config")
    args = entry.get("args", [])
    if not isinstance(args, list):
        raise ValueError(f"Server '{server_name}' args must be a list")
    env = entry.get("env", {})
    if env is None:
        env = {}
    if not isinstance(env, dict):
        raise ValueError(f"Server '{server_name}' env must be an object")
    return ChildServerConfig(
        name=server_name,
        command=command,
        args=[str(a) for a in args],
        env={str(k): str(v) for k, v in env.items()},
        disabled=bool(entry.get("disabled", False)),
    )


def _load_all_configs(config_path: str | Path) -> list[ChildServerConfig]:
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    raw = json.loads(config_file.read_text(encoding="utf-8"))
    servers = raw.get("mcpServers", {})
    configs: list[ChildServerConfig] = []
    for server_name in sorted(servers.keys()):
        entry = servers[server_name]
        if entry.get("disabled"):
            continue
        command = entry.get("command")
        if not command:
            raise ValueError(f"Server '{server_name}' missing 'command' in config")
        args = entry.get("args", [])
        if not isinstance(args, list):
            raise ValueError(f"Server '{server_name}' args must be a list")
        env = entry.get("env", {})
        if env is None:
            env = {}
        if not isinstance(env, dict):
            raise ValueError(f"Server '{server_name}' env must be an object")
        configs.append(
            ChildServerConfig(
                name=server_name,
                command=command,
                args=[str(a) for a in args],
                env={str(k): str(v) for k, v in env.items()},
                disabled=False,
            )
        )
    if not configs:
        raise ValueError("No enabled MCP servers found in config")
    return configs


class ProxyState:
    """Shared state for the wrapper server."""

    def __init__(
        self,
        child_config: ChildServerConfig,
        *,
        keep_alive: bool,
        app_exit_stack: AsyncExitStack,
    ):
        self.child_config = child_config
        self.session: ClientSession | None = None
        self._app_exit_stack = app_exit_stack
        self._active_sessions = 0
        self._lock = anyio.Lock()
        self._keep_alive = keep_alive

    async def acquire(self) -> None:
        async with self._lock:
            if self._active_sessions == 0:
                await self._start_locked()
            self._active_sessions += 1

    async def release(self) -> None:
        async with self._lock:
            if self._active_sessions == 0:
                return
            self._active_sessions -= 1
            if self._active_sessions == 0 and not self._keep_alive:
                await self._stop_locked()

    async def shutdown(self) -> None:
        async with self._lock:
            self._active_sessions = 0
            await self._stop_locked()

    async def _start_locked(self) -> None:
        if self.session is not None:
            return

        # Create custom log handler for this server
        log_handler = MCPLogHandler(self.child_config.name, "/tmp/mcp-wrapper.log")
        
        params = StdioServerParameters(
            command=self.child_config.command,
            args=self.child_config.args,
            env=self.child_config.env,
        )
        read_stream, write_stream = await self._app_exit_stack.enter_async_context(
            stdio_client(params, errlog=log_handler)
        )
        session = await self._app_exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        self.session = session

    async def _stop_locked(self) -> None:
        self.session = None


@asynccontextmanager
async def _proxy_lifespan(state: ProxyState) -> AsyncIterator[ProxyState]:
    yield state


def _build_proxy_server(
    child_config: ChildServerConfig,
    *,
    keep_alive: bool,
    app_exit_stack: AsyncExitStack,
) -> tuple[Server, ProxyState]:
    state = ProxyState(child_config, keep_alive=keep_alive, app_exit_stack=app_exit_stack)

    async def on_list_tools(ctx, params=None):
        return await ctx.lifespan_context.session.list_tools(params=params)

    async def on_call_tool(ctx, params):
        return await ctx.lifespan_context.session.call_tool(params.name, params.arguments)

    async def on_list_resources(ctx, params=None):
        return await ctx.lifespan_context.session.list_resources(params=params)

    async def on_list_resource_templates(ctx, params=None):
        return await ctx.lifespan_context.session.list_resource_templates(params=params)

    async def on_read_resource(ctx, params):
        return await ctx.lifespan_context.session.read_resource(params.uri)

    async def on_subscribe_resource(ctx, params):
        return await ctx.lifespan_context.session.subscribe_resource(params.uri)

    async def on_unsubscribe_resource(ctx, params):
        return await ctx.lifespan_context.session.unsubscribe_resource(params.uri)

    async def on_list_prompts(ctx, params=None):
        return await ctx.lifespan_context.session.list_prompts(params=params)

    async def on_get_prompt(ctx, params):
        return await ctx.lifespan_context.session.get_prompt(params.name, params.arguments)

    async def on_completion(ctx, params):
        argument_payload = {"name": params.argument.name, "value": params.argument.value}
        context_args = params.context.arguments if params.context else None
        return await ctx.lifespan_context.session.complete(
            params.ref, argument_payload, context_arguments=context_args
        )

    server = Server(
        name=f"mcp-wrapper:{child_config.name}",
        instructions=f"Proxy server for '{child_config.name}'.",
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
        on_list_resources=on_list_resources,
        on_list_resource_templates=on_list_resource_templates,
        on_read_resource=on_read_resource,
        on_subscribe_resource=on_subscribe_resource,
        on_unsubscribe_resource=on_unsubscribe_resource,
        on_list_prompts=on_list_prompts,
        on_get_prompt=on_get_prompt,
        on_completion=on_completion,
    )

    return server, state


@dataclass
class WrapperSettings:
    host: str = "127.0.0.1"
    port: int = 8005
    json_response: bool = False
    stateless_http: bool = False
    log_level: str = "info"


def _build_streamable_http_app(
    routes: list[Mount],
    proxy_states: list[ProxyState],
    app_exit_stack: AsyncExitStack,
) -> Starlette:
    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        await app_exit_stack.__aenter__()
        try:
            for state in proxy_states:
                await state.acquire()
            yield
        finally:
            for state in proxy_states:
                await state.shutdown()
            await app_exit_stack.aclose()

    return Starlette(routes=routes, lifespan=lifespan)



def _build_stateless_json_app(proxy_server: Server, proxy_state: "ProxyState") -> callable:
    async def app(scope, receive, send):
        transport = StreamableHTTPServerTransport(
            mcp_session_id=None,
            is_json_response_enabled=True,
        )

        async def run_stateless_server(*, task_status=anyio.TASK_STATUS_IGNORED):
            async with transport.connect() as streams:
                read_stream, write_stream = streams
                task_status.started()
                dispatcher: JSONRPCDispatcher[TransportContext] = JSONRPCDispatcher(
                    read_stream,
                    write_stream,
                    inline_methods=frozenset({"initialize"}),
                    transport_builder=lambda _md: TransportContext(kind="streamable-http", can_send_request=False),
                )
                connection = Connection.from_envelope(DEFAULT_NEGOTIATED_VERSION, None, None)
                try:
                    await serve_connection(
                        proxy_server, dispatcher, connection=connection, lifespan_state=proxy_state
                    )
                except Exception:
                    logger.exception("Stateless session crashed")

        async with anyio.create_task_group() as tg:
            await tg.start(run_stateless_server)
            await transport.handle_request(scope, receive, send)
            tg.cancel_scope.cancel()
        await transport.terminate()

    return app


def _extract_first_sentence(text: str) -> str:
    """Extract the first sentence from a text description."""
    if not text:
        return ""
    
    # Split on sentence-ending punctuation
    sentences = re.split(r'[.!?]+', text.strip())
    if sentences:
        first_sentence = sentences[0].strip()
        if first_sentence:
            return first_sentence + "."
    return text.strip()


async def _query_server_tools(child_config: ChildServerConfig, app_exit_stack: AsyncExitStack) -> List[Dict[str, str]]:
    """Query a wrapped server for its available tools and extract first sentences of descriptions."""
    try:
        # Create a temporary session to query the server
        params = StdioServerParameters(
            command=child_config.command,
            args=child_config.args,
            env=child_config.env,
        )
        # Create custom log handler for this server
        log_handler = MCPLogHandler(child_config.name, "/tmp/mcp-wrapper.log")
        read_stream, write_stream = await app_exit_stack.enter_async_context(
            stdio_client(params, errlog=log_handler)
        )
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            
            tools_info = []
            for tool in tools_result.tools:
                tool_info = {
                    "name": tool.name,
                    "description": _extract_first_sentence(tool.description or "")
                }
                tools_info.append(tool_info)
            
            return tools_info
    except Exception as e:
        logger.warning(f"Failed to query tools for server {child_config.name}: {e}")
        return []


async def _get_servers_info(child_configs: List[ChildServerConfig], app_exit_stack: AsyncExitStack) -> Dict:
    """Get information about all configured servers including their available tools."""
    servers_info = []
    
    for child_config in child_configs:
        tools_info = await _query_server_tools(child_config, app_exit_stack)
        server_info = {
            "name": child_config.name,
            "tools": tools_info
        }
        servers_info.append(server_info)
    
    return {"servers": servers_info}


def main() -> None:
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument("--config", help="Path to MCP config JSON file")
    base_parser.add_argument("--server", help="Server name from config JSON")
    base_parser.add_argument(
        "--keep-alive",
        dest="keep_alive",
        action="store_true",
        default=True,
        help="Keep wrapped MCP servers running between client sessions (default).",
    )
    base_parser.add_argument(
        "--no-keep-alive",
        dest="keep_alive",
        action="store_false",
        help="Stop wrapped MCP servers when each session ends.",
    )
    base_args, _ = base_parser.parse_known_args()

    default_path = f"/mcp-wrapper/{base_args.server}" if base_args.server else "/mcp-wrapper"
    streamable_parser = build_streamable_http_parser(default_path=default_path)
    parser = argparse.ArgumentParser(parents=[base_parser, streamable_parser], add_help=False)
    args, _ = parser.parse_known_args()
    streamable_args = parse_streamable_http_args(parser, default_path=default_path)
    if not streamable_args.stateless_http:
        streamable_args.stateless_http = True
    if not streamable_args.json_response:
        streamable_args.json_response = True

    if streamable_args.client_mode:
        if args.server and not streamable_args.client_url:
            streamable_args.client_url = (
                f"http://{streamable_args.host}:{streamable_args.port}"
                f"/mcp-wrapper/{args.server}"
            )
        asyncio.run(run_client_mode(streamable_args))
        return

    if not args.config:
        parser.error("--config is required unless running in --client mode")

    if args.server:
        child_configs = [_load_config(args.config, args.server)]
    else:
        child_configs = _load_all_configs(args.config)

    if not streamable_args.stateless_http or not streamable_args.json_response:
        raise ValueError(
            "mcp-wrapper currently supports stateless JSON streamable HTTP only. "
            "Remove --stateful-http/--no-json-response to proceed."
        )

    wrapper = WrapperSettings()
    routes: list[Mount] = []
    proxy_states: list[ProxyState] = []
    app_exit_stack = AsyncExitStack()
    for child_config in child_configs:
        proxy_server, proxy_state = _build_proxy_server(
            child_config,
            keep_alive=base_args.keep_alive,
            app_exit_stack=app_exit_stack,
        )
        server_path = f"/mcp-wrapper/{child_config.name}"
        proxy_states.append(proxy_state)
        async def healthcheck(_request):
            return PlainTextResponse("ok")

        server_app = Starlette(
            routes=[
                Route("/health", healthcheck),
                Mount("/", app=_build_stateless_json_app(proxy_server, proxy_state)),
            ],
        )
        routes.append(Mount(server_path, app=server_app))

    if streamable_args.transport == "stdio":
        streamable_args.transport = "streamable-http"

    if streamable_args.transport == "stdio":
        raise ValueError("mcp-wrapper only supports streamable-http transport")

    if streamable_args.macro_http and streamable_args.macro_https:
        raise ValueError("--http and --https cannot be used together")

    if streamable_args.macro_http:
        streamable_args.transport = "streamable-http"

    if streamable_args.macro_https:
        streamable_args.transport = "streamable-http"
        if not streamable_args.tls_cert and not streamable_args.tls_key:
            raise ValueError("--https requires --tls-cert/--tls-key when using mcp-wrapper")

    if not routes:
        raise RuntimeError("No MCP servers configured")

    # Add the servers info endpoint
    async def servers_info_endpoint(_request):
        # Load all configs to get server information
        if not args.config:
            return JSONResponse({"error": "No config file specified"}, status_code=400)
        
        try:
            child_configs = _load_all_configs(args.config)
            servers_info = await _get_servers_info(child_configs, app_exit_stack)
            return JSONResponse(servers_info)
        except Exception as e:
            logger.error(f"Failed to get servers info: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    # Add the servers info route directly to avoid trailing slash redirects
    routes.append(Route("/mcp-wrapper/servers-info", servers_info_endpoint, methods=["GET"]))

    app = _build_streamable_http_app(routes, proxy_states, app_exit_stack)
    config_kwargs = {
        "host": streamable_args.host,
        "port": streamable_args.port,
        "log_level": wrapper.log_level,
    }
    if streamable_args.tls_cert:
        config_kwargs["ssl_certfile"] = streamable_args.tls_cert
        config_kwargs["ssl_keyfile"] = streamable_args.tls_key
    uvicorn.Server(uvicorn.Config(app, **config_kwargs)).run()


if __name__ == "__main__":
    main()