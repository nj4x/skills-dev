"""Path normalization and containment helpers for mcp-vectors."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class OperationScope:
    """Separates the canonical root identity (namespace) from the requested path (selector)."""

    canonical_root_id: str
    requested_path: Path


@dataclass(frozen=True)
class PathInfo:
    """Normalized path details used in payloads and locks."""

    path: Path
    path_key: str
    display_path: str
    relative_path: Optional[str] = None
    root_path: Optional[str] = None
    root_id: Optional[str] = None


class PathPolicy:
    """Component-safe path normalization, containment, and overlap checks."""

    @staticmethod
    def resolve(path: str | Path, base_dir: str | Path | None = None) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute() and base_dir is not None:
            candidate = Path(base_dir).expanduser() / candidate
        return candidate.resolve(strict=False)

    @staticmethod
    def path_key(path: str | Path) -> str:
        return PathPolicy.resolve(path).as_posix()

    @staticmethod
    def root_id(root_path: str | Path) -> str:  # noqa: ARG004
        raise NotImplementedError("use GitResolver.resolve_root instead")

    @staticmethod
    def is_within(path: str | Path, root: str | Path) -> bool:
        path_resolved = PathPolicy.resolve(path)
        root_resolved = PathPolicy.resolve(root)
        try:
            path_resolved.relative_to(root_resolved)
            return True
        except ValueError:
            return False

    @staticmethod
    def overlaps(left: str | Path, right: str | Path) -> bool:
        left_resolved = PathPolicy.resolve(left)
        right_resolved = PathPolicy.resolve(right)
        return PathPolicy.is_within(left_resolved, right_resolved) or PathPolicy.is_within(right_resolved, left_resolved)

    @staticmethod
    def any_overlap(path: str | Path, roots: Iterable[str | Path]) -> bool:
        return any(PathPolicy.overlaps(path, root) for root in roots)

    @staticmethod
    def relative_to_root(path: str | Path, root: str | Path | None) -> Optional[str]:
        if root is None:
            return None
        try:
            return PathPolicy.resolve(path).relative_to(PathPolicy.resolve(root)).as_posix()
        except ValueError:
            return None

    @staticmethod
    def best_root(path: str | Path, roots: Iterable[str | Path] | None) -> Optional[Path]:
        if not roots:
            return None
        path_resolved = PathPolicy.resolve(path)
        matches = []
        for root in roots:
            root_resolved = PathPolicy.resolve(root)
            if PathPolicy.is_within(path_resolved, root_resolved):
                matches.append(root_resolved)
        if not matches:
            return None
        return max(matches, key=lambda p: len(p.parts))

    @staticmethod
    def info(path: str | Path, root: str | Path | None = None) -> PathInfo:
        resolved = PathPolicy.resolve(path)
        root_resolved = PathPolicy.resolve(root) if root is not None else None
        relative = PathPolicy.relative_to_root(resolved, root_resolved) if root_resolved else None
        return PathInfo(
            path=resolved,
            path_key=resolved.as_posix(),
            display_path=relative or resolved.as_posix(),
            relative_path=relative,
            root_path=root_resolved.as_posix() if root_resolved else None,
            root_id=PathPolicy.path_key(root_resolved) if root_resolved else None,
        )

    @staticmethod
    def validate_base_dirs(base_dirs: Iterable[str] | None) -> list[str] | None:
        if base_dirs is None:
            return None
        return [PathPolicy.path_key(path) for path in base_dirs if str(path).strip()]

    @staticmethod
    def commonpath_contains(path: str | Path, root: str | Path) -> bool:
        """Compatibility helper for tests and older Python path semantics."""
        path_key = PathPolicy.path_key(path)
        root_key = PathPolicy.path_key(root)
        try:
            return os.path.commonpath([path_key, root_key]) == root_key
        except ValueError:
            return False
