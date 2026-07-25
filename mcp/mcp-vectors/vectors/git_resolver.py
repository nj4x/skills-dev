"""Two-phase Git-plumbing resolver for canonical root identity (ADR-0006/0007)."""
from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_GIT_TIMEOUT = 10  # seconds

# Exact stderr git emits (LC_ALL=C) when no repository is found
_NO_REPO_STDERR = "fatal: not a git repository (or any of the parent directories): .git"


def _run_git(cmd: list[str], timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess:
    """Run a git command in a clean environment. Module-level so tests can patch it."""
    clean_env: dict[str, str] = {}
    for key in ("PATH", "HOME"):
        val = os.environ.get(key)
        if val:
            clean_env[key] = val
    clean_env["LC_ALL"] = "C"
    clean_env["LANG"] = "C"
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=clean_env,
    )


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@dataclass(frozen=True)
class GitResolution:
    """Result of a git root resolution attempt."""

    status: str  # supported_working_tree | allowlisted_non_git | unsupported_linked_worktree
                 # | unsupported_bare_repository | no_repository | unknown
    canonical_root: Optional[Path]
    git_binary_version: Optional[str]
    fingerprint: str
    error_detail: Optional[str] = None


class GitResolver:
    """Two-phase Git-plumbing resolver (ADR-0006)."""

    @staticmethod
    def git_version() -> Optional[str]:
        """Return 'git version X.Y.Z', or None if git is unavailable.

        Uses the same scrubbed environment as every other git invocation so the
        version string that feeds the resolver/epoch fingerprint is deterministic.
        """
        try:
            proc = _run_git(["git", "--version"], timeout=5)
            if proc.returncode == 0:
                return proc.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None

    @classmethod
    def resolve_root(cls, path: Path, config) -> GitResolution:
        """Resolve the canonical root for path per ADR-0006/0007."""
        git_ver = cls.git_version()
        if git_ver is None:
            return GitResolution(
                status="unknown",
                canonical_root=None,
                git_binary_version=None,
                fingerprint=_fingerprint("unknown", str(path.resolve())),
                error_detail="git binary not found or timed out",
            )

        resolved = path.resolve()
        probe_dir = resolved if resolved.is_dir() else resolved.parent

        # --- Phase 1 (no --show-toplevel: safe for bare repos) ---
        try:
            p1 = _run_git([
                "git", "-C", str(probe_dir),
                "rev-parse",
                "--is-inside-work-tree",
                "--is-bare-repository",
                "--absolute-git-dir",
                "--git-common-dir",
            ])
        except (subprocess.TimeoutExpired, OSError, PermissionError) as exc:
            return GitResolution(
                status="unknown",
                canonical_root=None,
                git_binary_version=git_ver,
                fingerprint=_fingerprint("unknown", str(resolved)),
                error_detail=str(exc),
            )

        if p1.returncode != 0:
            return cls._handle_nonzero(p1, resolved, probe_dir, config, git_ver)

        lines = p1.stdout.strip().splitlines()
        if len(lines) < 4:
            return GitResolution(
                status="unknown",
                canonical_root=None,
                git_binary_version=git_ver,
                fingerprint=_fingerprint("unknown", str(resolved)),
                error_detail=f"unexpected phase-1 output: {p1.stdout!r}",
            )

        is_inside_wt = lines[0].strip()
        is_bare = lines[1].strip()
        abs_git_dir = lines[2].strip()
        common_dir = lines[3].strip()

        if is_bare == "true":
            return GitResolution(
                status="unsupported_bare_repository",
                canonical_root=None,
                git_binary_version=git_ver,
                fingerprint=_fingerprint("unsupported_bare_repository", abs_git_dir),
            )

        if is_inside_wt != "true":
            # Inside the .git dir itself, or other non-work-tree non-bare state.
            return GitResolution(
                status="unknown",
                canonical_root=None,
                git_binary_version=git_ver,
                fingerprint=_fingerprint("unknown", str(resolved)),
                error_detail="not inside a work tree",
            )

        # Linked worktree: its per-worktree git dir (--absolute-git-dir) differs
        # from the shared repository git dir (--git-common-dir). Comparing the two
        # is the authoritative discriminator (ADR-0006) — it correctly handles
        # --separate-git-dir layouts that a `.git/worktrees/` path check misses.
        # --git-common-dir may be relative to the probe directory.
        common_path = Path(common_dir)
        if not common_path.is_absolute():
            common_path = probe_dir / common_path
        if os.path.realpath(str(common_path)) != os.path.realpath(abs_git_dir):
            return GitResolution(
                status="unsupported_linked_worktree",
                canonical_root=None,
                git_binary_version=git_ver,
                fingerprint=_fingerprint("unsupported_linked_worktree", abs_git_dir),
            )

        # --- Phase 2 (normal / submodule / separate-git-dir) ---
        return cls._phase2(probe_dir, resolved, git_ver)

    @classmethod
    def _phase2(cls, probe_dir: Path, resolved: Path, git_ver: str) -> GitResolution:
        try:
            p2 = _run_git([
                "git", "-C", str(probe_dir),
                "rev-parse",
                "--show-toplevel",
                "--absolute-git-dir",
            ])
        except (subprocess.TimeoutExpired, OSError, PermissionError) as exc:
            return GitResolution(
                status="unknown",
                canonical_root=None,
                git_binary_version=git_ver,
                fingerprint=_fingerprint("unknown", str(resolved)),
                error_detail=str(exc),
            )

        if p2.returncode != 0:
            return GitResolution(
                status="unknown",
                canonical_root=None,
                git_binary_version=git_ver,
                fingerprint=_fingerprint("unknown", str(resolved)),
                error_detail=f"phase-2 failed: {p2.stderr.strip()}",
            )

        lines = p2.stdout.strip().splitlines()
        if len(lines) < 2:
            return GitResolution(
                status="unknown",
                canonical_root=None,
                git_binary_version=git_ver,
                fingerprint=_fingerprint("unknown", str(resolved)),
                error_detail=f"unexpected phase-2 output: {p2.stdout!r}",
            )

        show_toplevel = lines[0].strip()
        abs_git_dir = lines[1].strip()

        canonical_root = Path(show_toplevel).resolve()
        return GitResolution(
            status="supported_working_tree",
            canonical_root=canonical_root,
            git_binary_version=git_ver,
            fingerprint=_fingerprint("supported_working_tree", abs_git_dir, show_toplevel),
        )

    @classmethod
    def _handle_nonzero(
        cls,
        proc: subprocess.CompletedProcess,
        resolved: Path,
        probe_dir: Path,
        config,
        git_ver: str,
    ) -> GitResolution:
        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()

        # Three-part no-repository proof (ADR-0006):
        # (a) no .git entry in any ancestor
        # (b) stderr matches the canonical "not a git repository" message exactly
        # (c) stdout is empty
        if (
            stdout == ""
            and stderr == _NO_REPO_STDERR
            and not cls._has_git_ancestor(probe_dir)
        ):
            return cls._no_repository(resolved, probe_dir, config, git_ver)

        return GitResolution(
            status="unknown",
            canonical_root=None,
            git_binary_version=git_ver,
            fingerprint=_fingerprint("unknown", str(resolved)),
            error_detail=f"exit {proc.returncode}: {stderr[:200]}",
        )

    @staticmethod
    def _has_git_ancestor(path: Path) -> bool:
        """Return True if path or any ancestor contains a .git entry."""
        current = path.resolve()
        while True:
            if (current / ".git").exists():
                return True
            parent = current.parent
            if parent == current:
                break
            current = parent
        return False

    @classmethod
    def _no_repository(
        cls,
        resolved: Path,
        probe_dir: Path,
        config,
        git_ver: str,
    ) -> GitResolution:
        """Return no_repository or allowlisted_non_git per ADR-0007."""
        allowed: list[str] = getattr(config, "allowed_non_git_roots", [])
        best_match: Optional[Path] = None
        best_len = -1
        probe_resolved = probe_dir.resolve()

        for entry in allowed:
            entry_path = Path(entry).expanduser().resolve()
            try:
                probe_resolved.relative_to(entry_path)
                key = len(entry_path.parts)
                if key > best_len:
                    best_len = key
                    best_match = entry_path
            except ValueError:
                continue

        if best_match is not None:
            return GitResolution(
                status="allowlisted_non_git",
                canonical_root=best_match,
                git_binary_version=git_ver,
                fingerprint=_fingerprint("allowlisted_non_git", str(best_match), str(probe_resolved)),
            )

        return GitResolution(
            status="no_repository",
            canonical_root=None,
            git_binary_version=git_ver,
            fingerprint=_fingerprint("no_repository", str(probe_resolved)),
        )

    @classmethod
    def validate_fingerprint(cls, probe: Path, config, fingerprint: str) -> bool:
        """Return True if resolving probe again yields the same fingerprint."""
        return cls.resolve_root(probe, config).fingerprint == fingerprint
