"""Dedicated VS Code instance lifecycle (design/70, ADR-pending).

One persistent window at ``~/.vscode-agent-bridge/data``, spawned by this
process. Liveness is not the `code` CLI's exit status — that process hands
off to the real Electron main process and exits immediately regardless of
outcome — it is the companion extension's WebSocket connection, tracked via
``mark_connected``/``mark_disconnected`` from the hook server.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

DATA_DIR = Path(os.path.expanduser("~/.vscode-agent-bridge/data"))
SPAWN_TIMEOUT = 30.0

# Suppress every first-run interactive prompt so a fresh dedicated window
# needs no human click before cline-sr can run (task/77).
SEED_SETTINGS = {
    "security.workspace.trust.enabled": False,
    "workbench.startupEditor": "none",
    "workbench.tips.enabled": False,
    "workbench.welcomePage.walkthroughs.openOnInstall": False,
    "extensions.ignoreRecommendations": True,
    "update.mode": "none",
    "telemetry.telemetryLevel": "off",
    "settingsSync.enabled": False,
    "github.gitAuthentication": False,
}


def _seed_settings() -> None:
    settings_path = DATA_DIR / "User" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            return  # unreadable user file — leave it untouched
    merged = {**SEED_SETTINGS, **existing}
    if merged != existing:
        settings_path.write_text(json.dumps(merged, indent=2) + "\n")


class InstanceUnreachable(RuntimeError):
    """The dedicated window did not come up (or reconnect) in time."""


class InstanceManager:
    def __init__(self, code_bin: str = "code") -> None:
        self._code_bin = code_bin
        self.workspace: str | None = None
        self._alive = False
        self._connected = asyncio.Event()

    @property
    def alive(self) -> bool:
        return self._alive

    def mark_connected(self) -> None:
        self._alive = True
        self._connected.set()

    def mark_disconnected(self) -> None:
        self._alive = False
        self._connected.clear()

    async def ensure_ready(self, workspace: str, port: int) -> None:
        """Spawn or reuse the dedicated window so `workspace` is open in it."""
        if self._alive and self.workspace == workspace:
            return

        self._connected.clear()
        args = [self._code_bin, "--user-data-dir", str(DATA_DIR)]
        if self._alive:
            args.append("--reuse-window")
        args.append(workspace)

        _seed_settings()
        env = {**os.environ, "BRIDGE_PORT": str(port)}
        proc = await asyncio.create_subprocess_exec(*args, env=env)
        await proc.wait()  # the `code` CLI hands off and exits at once (design/70)

        try:
            await asyncio.wait_for(self._connected.wait(), timeout=SPAWN_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise InstanceUnreachable(f"extension did not connect within {SPAWN_TIMEOUT}s") from exc
        self.workspace = workspace
