"""Rotating-file logging for the bridge (ADR-0069).

Single chronological log at ~/.vscode-agent-bridge/logs/vscode-agent-bridge.log,
matching the mcp-vectors convention (10 MB / 3 backups, local-timezone
timestamps) plus a task_id= field injected from a ContextVar so lines stay
greppable per task. Logging failures are non-fatal: the server must never die
because its log file is unwritable.
"""

from __future__ import annotations

import contextvars
import logging
import sys
from pathlib import Path

LOGGER_NAME = "vscode-agent-bridge"
FMT = "%(asctime)s [%(levelname)s] [PID:%(process)d] [task_id=%(task_id)s] %(name)s: %(message)s"

task_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("task_id", default="")


def set_task_id(task_id: str | None) -> None:
    task_id_var.set(task_id or "")


class TaskIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.task_id = task_id_var.get()
        return True


class _LocalTimestampFormatter(logging.Formatter):
    """Formats asctime as local wall-clock time with numeric UTC offset (RFC 3339-ish)."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        import datetime

        dt = datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc).astimezone()
        if datefmt:
            return dt.strftime(datefmt)
        offset = dt.strftime("%z")
        offset_fmt = f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
        return dt.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3] + f" {offset_fmt}"


def setup_logging() -> logging.Logger:
    """Configure the bridge logger; never raises (non-fatal per ADR-0069)."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # sole destination is this handler; never leak to root
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()

    try:
        from logging.handlers import RotatingFileHandler

        log_dir = Path.home() / ".vscode-agent-bridge" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "vscode-agent-bridge.log"

        rotating = RotatingFileHandler(str(log_file), maxBytes=10 * 1024 * 1024, backupCount=3)
        try:
            log_file.touch(exist_ok=True)
            log_file.chmod(0o600)
        except OSError:
            pass
        rotating.setFormatter(_LocalTimestampFormatter(FMT))
        rotating.addFilter(TaskIdFilter())
        logger.addHandler(rotating)
    except (OSError, RuntimeError) as exc:
        print(f"vscode-agent-bridge: file logging disabled ({exc})", file=sys.stderr)
        logger.addHandler(logging.NullHandler())

    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
