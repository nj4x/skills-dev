"""Indexing safety and secret-audit helpers."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

from .config import (
    DEFAULT_EXCLUDED_DIRECTORIES,
    DEFAULT_EXCLUDED_EXTENSIONS,
    DEFAULT_EXCLUDED_FILENAMES,
    DEFAULT_SECRET_FILENAMES,
    DEFAULT_SECRET_PATH_PATTERNS,
)
from .paths import PathPolicy


_SECRET_CONTENT_PATTERNS = {
    "private_key_marker": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "aws_access_key_id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "generic_secret_assignment": re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd|credential)\b\s*[:=]\s*['\"]?[^\s'\"]{8,}"
    ),
}


@dataclass(frozen=True)
class IndexDecision:
    """Decision describing whether a path should be indexed."""

    path: str
    path_key: str
    action: str
    reason_codes: list[str]
    secret_risk: bool = False
    safe_to_auto_delete_if_stale: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


class ExclusionPolicy:
    """Shared exclusion policy for parser, watcher, scanner, and audits."""

    def __init__(
        self,
        excluded_extensions: Optional[Iterable[str]] = None,
        excluded_directories: Optional[Iterable[str]] = None,
        excluded_filenames: Optional[Iterable[str]] = None,
        secret_filenames: Optional[Iterable[str]] = None,
        secret_path_patterns: Optional[Iterable[str]] = None,
    ):
        self.excluded_extensions = {ext.lower() for ext in (excluded_extensions or DEFAULT_EXCLUDED_EXTENSIONS)}
        self.excluded_directories = set(excluded_directories or DEFAULT_EXCLUDED_DIRECTORIES)
        self.excluded_filenames = set(excluded_filenames or DEFAULT_EXCLUDED_FILENAMES)
        self.secret_filenames = set(secret_filenames or DEFAULT_SECRET_FILENAMES)
        self.secret_path_patterns = set(secret_path_patterns or DEFAULT_SECRET_PATH_PATTERNS)

    def is_excluded_directory(self, dir_path: str | Path) -> bool:
        return self.should_traverse_path(dir_path).action == "skip"

    def should_traverse_path(self, path: str | Path) -> IndexDecision:
        resolved = PathPolicy.resolve(path)
        reason_codes: list[str] = []

        secret_risk, secret_reasons = self.is_secret_path(resolved)
        reason_codes.extend(secret_reasons)

        if resolved.name in self.excluded_filenames:
            reason_codes.append("excluded_filename")

        if self._matches_excluded_path(resolved):
            reason_codes.append("excluded_directory")

        action = "skip" if reason_codes else "index"
        return IndexDecision(
            path=resolved.as_posix(),
            path_key=resolved.as_posix(),
            action=action,
            reason_codes=list(dict.fromkeys(reason_codes)),
            secret_risk=secret_risk,
            safe_to_auto_delete_if_stale=not secret_risk,
        )

    def is_secret_path(self, path: str | Path) -> tuple[bool, list[str]]:
        path_obj = Path(path)
        name = path_obj.name
        normalized = path_obj.as_posix()
        reason_codes: list[str] = []

        if name in self.secret_filenames:
            reason_codes.append("secret_filename")

        for pattern in self.secret_path_patterns:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(normalized, pattern) or any(
                fnmatch.fnmatch(part, pattern) for part in path_obj.parts
            ):
                reason_codes.append(f"secret_path_pattern:{pattern}")

        if any(part in {".ssh", ".aws", ".kube"} for part in path_obj.parts):
            reason_codes.append("secret_directory")

        # Preserve order while deduplicating.
        deduped = list(dict.fromkeys(reason_codes))
        return bool(deduped), deduped

    def should_index_path(self, path: str | Path) -> IndexDecision:
        resolved = PathPolicy.resolve(path)
        reason_codes: list[str] = []

        secret_risk, secret_reasons = self.is_secret_path(resolved)
        reason_codes.extend(secret_reasons)

        if resolved.name in self.excluded_filenames:
            reason_codes.append("excluded_filename")

        suffix = resolved.suffix.lower()
        if suffix in self.excluded_extensions:
            reason_codes.append("excluded_extension")

        if self._matches_excluded_path(resolved):
            reason_codes.append("excluded_directory")

        action = "skip" if reason_codes else "index"
        return IndexDecision(
            path=resolved.as_posix(),
            path_key=resolved.as_posix(),
            action=action,
            reason_codes=list(dict.fromkeys(reason_codes)),
            secret_risk=secret_risk,
            safe_to_auto_delete_if_stale=not secret_risk,
        )

    def scan_content_signals(self, text: str, max_chars: int = 200_000) -> list[str]:
        """Return rule IDs for secret-like content without returning matched values."""
        sample = text[:max_chars]
        return [name for name, pattern in _SECRET_CONTENT_PATTERNS.items() if pattern.search(sample)]

    def payload_secret_reasons(self, payload: dict) -> list[str]:
        reasons: list[str] = []
        file_path = payload.get("file_path") or payload.get("path_key") or ""
        if file_path:
            _, path_reasons = self.is_secret_path(file_path)
            reasons.extend(path_reasons)
        chunk_text = payload.get("chunk_text")
        if isinstance(chunk_text, str):
            reasons.extend(f"content_signal:{rule_id}" for rule_id in self.scan_content_signals(chunk_text))
        return list(dict.fromkeys(reasons))

    def _matches_excluded_path(self, path: Path) -> bool:
        normalized = path.as_posix().strip("/")
        parts = tuple(path.parts)
        for pattern in self.excluded_directories:
            normalized_pattern = pattern.replace("\\", "/").strip("/")
            if "/" in normalized_pattern:
                if (
                    fnmatch.fnmatch(normalized, normalized_pattern)
                    or fnmatch.fnmatch(normalized, f"*/{normalized_pattern}")
                    or fnmatch.fnmatch(normalized, f"{normalized_pattern}/*")
                    or fnmatch.fnmatch(normalized, f"*/{normalized_pattern}/*")
                ):
                    return True
            elif any(self._matches_any(part, [pattern]) for part in parts):
                return True
        return False

    @staticmethod
    def _matches_any(value: str, patterns: Iterable[str]) -> bool:
        for pattern in patterns:
            if value == pattern or fnmatch.fnmatch(value, pattern):
                return True
        return False
