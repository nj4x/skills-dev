"""Auto-start Qdrant in Docker when it is not reachable at a localhost URL.

Activated when QDRANT_URL points to localhost/127.0.0.1 and Qdrant is not
responding. Controlled by QDRANT_DOCKER_AUTOSTART (default: true).
No-op when QDRANT_URL is unset (in-memory mode) or points to a remote host.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

_QDRANT_IMAGE = "qdrant/qdrant"
_QDRANT_STORAGE_DIR = os.path.expanduser("~/.mcp-vectors/qdrant")
_STARTUP_TIMEOUT = 30  # seconds to wait for Qdrant to become healthy
_HEALTH_TIMEOUT = 2    # seconds per health-check request


def _is_localhost(url: str) -> bool:
    return "localhost" in url or "127.0.0.1" in url


def _is_healthy(url: str) -> bool:
    try:
        req = urllib.request.urlopen(
            f"{url.rstrip('/')}/readyz", timeout=_HEALTH_TIMEOUT
        )
        return req.status == 200
    except Exception:
        return False


def _docker_available() -> bool:
    try:
        return subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5
        ).returncode == 0
    except Exception:
        return False


def _container_already_running(port: int = 6333) -> bool:
    """True if any Docker container is already publishing the Qdrant port."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"publish={port}", "--format", "{{.ID}}"],
            capture_output=True, text=True, timeout=5,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _start_container() -> bool:
    """Run the Qdrant container. Returns True on success."""
    os.makedirs(_QDRANT_STORAGE_DIR, exist_ok=True)
    cmd = [
        "docker", "run", "-d",
        "-p", "6333:6333",
        "-p", "6334:6334",
        "-v", f"{_QDRANT_STORAGE_DIR}:/qdrant/storage:z",
        "--restart", "unless-stopped",
        _QDRANT_IMAGE,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        logger.error("Failed to start Qdrant container: %s", result.stderr.strip())
        return False
    logger.info("Started Qdrant container: %s", result.stdout.strip()[:12])
    return True


def _wait_for_healthy(url: str, timeout: int = _STARTUP_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_healthy(url):
            return True
        time.sleep(1)
    return False


def ensure_qdrant_running(url: str | None) -> None:
    """Check Qdrant health and start it via Docker if needed.

    Safe to call from asyncio via asyncio.to_thread — all I/O is synchronous.
    """
    if not url:
        return  # in-memory mode; nothing to start

    autostart = os.getenv("QDRANT_DOCKER_AUTOSTART", "true").strip().lower()
    if autostart not in ("1", "true", "yes", "on"):
        return

    if not _is_localhost(url):
        return  # remote Qdrant; don't touch it

    if _is_healthy(url):
        logger.debug("Qdrant already healthy at %s", url)
        return

    if not _docker_available():
        logger.warning(
            "Qdrant not reachable at %s and Docker is not available — "
            "start Qdrant manually or set QDRANT_DOCKER_AUTOSTART=false",
            url,
        )
        return

    if _container_already_running():
        logger.info("Qdrant container is starting up, waiting for health check…")
    else:
        logger.info("Qdrant not reachable at %s — starting Docker container…", url)
        if not _start_container():
            return

    if _wait_for_healthy(url):
        logger.info("Qdrant ready at %s", url)
    else:
        logger.warning(
            "Qdrant did not become healthy within %ds at %s",
            _STARTUP_TIMEOUT, url,
        )
