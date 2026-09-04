"""Gitignore-aware path matching for indexing.

Skips files and directories listed in ``.gitignore`` and ``.git/info/exclude``
during directory walks. Matching follows git's per-directory semantics: a
``.gitignore`` applies to paths under the directory that contains it, with
deeper files taking precedence within their own subtree.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pathspec
except ImportError:  # pragma: no cover - exercised via tests with monkeypatch
    pathspec = None
    logger.warning(
        "pathspec is not installed; .gitignore patterns will not be respected. "
        "Install 'pathspec>=0.12.0' to enable gitignore-aware indexing."
    )


class GitignoreMatcher:
    """Repo-root-aware, per-directory cached gitignore matcher.

    Construct via :meth:`for_path`, which locates the enclosing git repository
    and returns ``None`` when the path is not inside one. Callers treat ``None``
    as "no gitignore filtering".
    """

    def __init__(self, repo_root: Path, respect_gitignore: bool = True, respect_git_exclude: bool = True):
        self.repo_root = repo_root
        self.respect_gitignore = respect_gitignore
        self.respect_git_exclude = respect_git_exclude
        # Maps a directory -> compiled spec for that directory's .gitignore.
        # The repo root slot also folds in .git/info/exclude.
        self._specs: dict[Path, Optional["pathspec.PathSpec"]] = {}
        self._load_repo_root_spec()

    @classmethod
    def for_path(cls, path: str | Path, respect_gitignore: bool = True, respect_git_exclude: bool = True) -> Optional["GitignoreMatcher"]:
        """Return a matcher for the git repo containing ``path``, or ``None``.

        Returns ``None`` when ``path`` is not inside a git repository or when
        ``pathspec`` is unavailable.
        """
        if pathspec is None:
            return None
        candidate = Path(path).expanduser().resolve()
        # A file path's repo is found by inspecting it and its ancestors.
        for directory in (candidate, *candidate.parents):
            if (directory / ".git").exists():
                return cls(directory, respect_gitignore=respect_gitignore, respect_git_exclude=respect_git_exclude)
        return None

    def _load_repo_root_spec(self) -> None:
        lines: list[str] = []
        if self.respect_gitignore:
            lines.extend(self._read_lines(self.repo_root / ".gitignore"))
        if self.respect_git_exclude:
            lines.extend(self._read_lines(self.repo_root / ".git" / "info" / "exclude"))
        self._specs[self.repo_root] = self._compile(lines)

    def preload(self, directory: str | Path) -> None:
        """Load ``directory/.gitignore`` into the cache if not already present.

        Idempotent. Intended to be called as each directory is entered during a
        top-down walk so nested ``.gitignore`` files are picked up in order.
        """
        directory = Path(directory).resolve()
        if directory in self._specs:
            return
        self._specs[directory] = self._compile(self._read_lines(directory / ".gitignore"))

    def preload_ancestors(self, path: str | Path) -> None:
        """Preload ``.gitignore`` for every directory from the repo root to ``path``.

        Used by callers that don't walk top-down (e.g. the file watcher), so the
        relevant nested specs are cached before :meth:`is_ignored` is consulted.
        """
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.repo_root)
        except ValueError:
            return
        directory = resolved.parent if not resolved.is_dir() else resolved
        chain: list[Path] = []
        while True:
            chain.append(directory)
            if directory == self.repo_root or self.repo_root not in directory.parents:
                break
            directory = directory.parent
        for ancestor in chain:
            self.preload(ancestor)

    def is_ignored(self, path: str | Path) -> bool:
        """Return ``True`` if ``path`` is ignored by any applicable spec.

        Tests the path against the ``.gitignore`` of each ancestor directory
        from the repo root down to the path's parent, matching relative to each
        spec's own directory (git's per-directory rule).
        """
        if pathspec is None:
            return False
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.repo_root)
        except ValueError:
            return False

        is_dir = resolved.is_dir()
        # Ancestor directories that could hold an applicable .gitignore:
        # repo_root .. resolved.parent (inclusive).
        for directory, spec in self._specs.items():
            if spec is None:
                continue
            try:
                rel = resolved.relative_to(directory)
            except ValueError:
                continue
            rel_str = rel.as_posix()
            if is_dir:
                rel_str += "/"
            if spec.match_file(rel_str):
                return True
        return False

    @staticmethod
    def _read_lines(file_path: Path) -> list[str]:
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError, PermissionError):
            return []

    @staticmethod
    def _compile(lines: list[str]) -> Optional["pathspec.PathSpec"]:
        if pathspec is None or not lines:
            return None
        return pathspec.GitIgnoreSpec.from_lines(lines)
