"""Typed error classes for root resolution failures (ADR-0006/0007)."""
from __future__ import annotations

from pathlib import Path


class RootResolutionError(Exception):
    """Base class for all git root resolution failures."""

    def __init__(self, probe: Path, status: str, message: str) -> None:
        super().__init__(message)
        self.probe = probe
        self.status = status
        self.message = message

    @property
    def error_code(self) -> str:
        return self.status


class UnsupportedLinkedWorktree(RootResolutionError):
    def __init__(self, probe: Path) -> None:
        super().__init__(
            probe,
            "unsupported_linked_worktree",
            f"Cannot index a linked git worktree: {probe}. Index the main worktree instead.",
        )


class UnsupportedBareRepository(RootResolutionError):
    def __init__(self, probe: Path) -> None:
        super().__init__(
            probe,
            "unsupported_bare_repository",
            f"Cannot index a bare git repository: {probe}",
        )


class NoGitRepository(RootResolutionError):
    def __init__(self, probe: Path) -> None:
        super().__init__(
            probe,
            "no_repository",
            f"Path is not inside a git repository: {probe}. "
            "Initialise a git repo or add to allowed_non_git_roots.",
        )


class UnknownResolution(RootResolutionError):
    def __init__(self, probe: Path, detail: str | None = None) -> None:
        msg = f"Could not determine git root for: {probe}"
        if detail:
            msg += f" ({detail})"
        super().__init__(probe, "unknown_resolution", msg)
