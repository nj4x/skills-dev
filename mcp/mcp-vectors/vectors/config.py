"""Configuration management for MCP Vectors."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ====================
# Log Sanitization
# ====================

# Words that trigger false positives in log parsers (like Cline)
# These are masked when they appear in file/directory names in logs
_TRIGGER_WORDS = re.compile(r'\b(error|fail|exception|critical)\b', re.IGNORECASE)


def sanitize_for_log(text: str) -> str:
    """Sanitize file/directory names for logging to avoid false positive error detection."""
    def mask_word(match: re.Match) -> str:
        word = match.group(1)
        if len(word) <= 2:
            return word
        return word[0] + '*' + word[2:]

    return _TRIGGER_WORDS.sub(mask_word, str(text))


# Extensions to exclude from indexing (binary, media, etc.)
DEFAULT_EXCLUDED_EXTENSIONS = [
    # Binary images
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp", ".tiff", ".tif",
    # Binary executables and compiled files
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".pyc", ".pyo", ".class", ".pyd",
    # Archives
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".rar", ".7z", ".jar", ".war", ".ear",
    # Media
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv", ".flac", ".ogg", ".webm", ".m4a", ".m4v",
    # Fonts
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    # Documents (binary formats - can't be parsed as text)
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    # Database files
    ".sqlite", ".db", ".sqlite3", ".mdb",
    # Lock files
    ".lock",
    # Source maps and minified files (usually not useful for semantic search)
    ".map",
    # Other binary/non-text
    ".pdf",  # PDF parsing is opt-in; keep excluded by default for safety/performance
]

# Filenames to exclude (for files without extensions like .DS_Store)
DEFAULT_EXCLUDED_FILENAMES = [
    ".DS_Store",
    "Thumbs.db",
    ".gitkeep",
    ".npmrc",
    ".yarnrc",
    ".pypirc",
    ".netrc",
    "credentials.json",
]

# Secret-like filenames and path patterns skipped by default for future indexing.
# These exclusions are prospective; existing indexed payloads require audit/purge.
DEFAULT_SECRET_FILENAMES = [
    ".env",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "http-client.private.env.json",
]

DEFAULT_SECRET_PATH_PATTERNS = [
    ".env.*",
    "*.pem",
    "*.key",
    "*.crt",
    "*.p12",
    "*.pfx",
    "service-account*.json",
    ".aws",
    ".aws/*",
    ".ssh",
    ".ssh/*",
    ".kube",
    ".kube/*",
]

# Directories to exclude from indexing
DEFAULT_EXCLUDED_DIRECTORIES = [
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    "env",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".next",
    ".nuxt",
    "target",
    "bin",
    "obj",
    "coverage",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "eggs",
    "*.egg-info",
    ".eggs",
    "vendor",
    "Pods",
    ".gradle",
    ".mvn",
    "out",
    ".output",
    ".parcel-cache",
    ".turbo",
    ".aws",
    ".ssh",
    ".kube",
    ".claude",
    ".claude/worktrees",
    ".cline",
    ".clinerules",
    ".workspace_rag",
    "graphify-out",
]


@dataclass
class Config:
    """Configuration for the MCP Vectors server."""

    # LM Studio settings
    lm_studio_url: str = "http://localhost:1234/v1"
    embedding_model: str = "auto"
    llm_model: str = "auto"
    lm_studio_ttl: int = -1  # seconds to keep model loaded (-1 = indefinite)

    # Qdrant settings
    qdrant_url: Optional[str] = None
    qdrant_collection: str = "mcp_vectors"

    # Indexing settings
    watch_dirs: list[str] = field(default_factory=list)
    chunk_size: int = 512
    chunk_overlap: int = 128
    respect_gitignore: bool = True
    respect_git_exclude: bool = True
    embedding_batch_size: int = 100

    # Auto-maintain: on startup, reconcile an already-indexed project against disk
    # and keep watching it. On by default; set AUTO_SYNC=false to opt out.
    auto_sync: bool = True

    # Exclusion filters (deny-list approach - index everything except these)
    excluded_extensions: list[str] = field(default_factory=lambda: DEFAULT_EXCLUDED_EXTENSIONS.copy())
    excluded_directories: list[str] = field(default_factory=lambda: DEFAULT_EXCLUDED_DIRECTORIES.copy())
    excluded_filenames: list[str] = field(default_factory=lambda: DEFAULT_EXCLUDED_FILENAMES.copy())
    secret_filenames: list[str] = field(default_factory=lambda: DEFAULT_SECRET_FILENAMES.copy())
    secret_path_patterns: list[str] = field(default_factory=lambda: DEFAULT_SECRET_PATH_PATTERNS.copy())

    # Processing limits
    max_file_size_mb: float = 50.0
    max_chunk_tokens: int = 512
    max_search_limit: int = 100
    max_scroll_points: int = 50_000
    scroll_page_size: int = 1_000
    max_files_per_scan: int = 10_000
    max_dirs_per_scan: int = 2_000

    # Graceful shutdown
    graceful_shutdown_timeout: int = 60

    # Community report-generation retry / TTL recovery (lazy reports phase).
    # After reports_max_attempts consecutive hard failures a root's report slot is
    # parked "failed-permanently"; reports_retry_base_ttl_seconds later it resets to
    # pending. Each consecutive parking doubles the TTL, capped at
    # reports_retry_max_ttl_seconds (24h -> 48h -> 96h ... <= 30d).
    reports_retry_base_ttl_seconds: int = 86_400     # 24h; REPORTS_RETRY_BASE_TTL_SECONDS
    reports_retry_max_ttl_seconds: int = 2_592_000   # 30d cap; REPORTS_RETRY_MAX_TTL_SECONDS
    reports_max_attempts: int = 5                     # REPORTS_MAX_ATTEMPTS
    reports_claim_lease_seconds: int = 3_600         # REPORTS_CLAIM_LEASE_SECONDS

    # Git root enforcement (ADR-0006, ADR-0007, ADR-0008)
    allowed_non_git_roots: list[str] = field(default_factory=list)
    auto_purge_non_git_roots: bool = True      # AUTO_PURGE_NON_GIT_ROOTS
    reconcile_on_startup: bool = True          # RECONCILE_ON_STARTUP

    # Entity-targeted community summarization (ADR-0009–0021)
    entity_search_limit: int = 20              # ENTITY_SEARCH_LIMIT
    community_cap_ratio: float = 0.3           # COMMUNITY_CAP_RATIO
    entity_extraction_concurrency: int = 4     # ENTITY_EXTRACTION_CONCURRENCY
    targeting_log_full_query: bool = False     # TARGETING_LOG_FULL_QUERY
    query_log_max_chars: int = 64              # QUERY_LOG_MAX_CHARS

    @property
    def config_fingerprint(self) -> str:
        """Deterministic SHA-256 of enforcement-relevant config fields."""
        canonical = sorted(self.allowed_non_git_roots)
        joined = "|".join(canonical)
        payload = f"v2|git-root-enforcement|auto-purge={self.auto_purge_non_git_roots}|{joined}"
        return hashlib.sha256(payload.encode()).hexdigest()

    # search_root channel timeout (seconds); validated > 0 at startup, defaults to 60
    search_root_timeout_seconds: int = 60      # SEARCH_ROOT_TIMEOUT_SECONDS

    # LLM provider selection
    llm_provider: str = "lm_studio"           # LLM_PROVIDER: "lm_studio" | "anthproxy"
    anthproxy_url: str = "http://127.0.0.1:8082"  # ANTHPROXY_URL
    anthproxy_model: str = "haiku"             # ANTHPROXY_MODEL
    anthproxy_llm_batch_size: int = 50         # ANTHPROXY_LLM_BATCH_SIZE
    anthproxy_llm_max_prompt_chars: int = 80000  # ANTHPROXY_LLM_MAX_PROMPT_CHARS


def get_config() -> Config:
    """Load configuration from environment variables."""
    return Config(
        lm_studio_url=os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "auto"),
        llm_model=os.getenv("LLM_MODEL", "auto"),
        lm_studio_ttl=int(os.getenv("LM_STUDIO_TTL", "-1")),
        qdrant_url=os.getenv("QDRANT_URL"),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "mcp_vectors"),
        watch_dirs=_parse_watch_dirs(os.getenv("WATCH_DIR", "")),
        chunk_size=int(os.getenv("CHUNK_SIZE", "512")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "128")),
        respect_gitignore=_parse_bool(os.getenv("RESPECT_GITIGNORE"), default=True),
        respect_git_exclude=_parse_bool(os.getenv("RESPECT_GIT_EXCLUDE"), default=True),
        embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "100")),
        max_file_size_mb=float(os.getenv("MAX_FILE_SIZE_MB", "50.0")),
        max_chunk_tokens=int(os.getenv("MAX_CHUNK_TOKENS", "512")),
        max_search_limit=int(os.getenv("MAX_SEARCH_LIMIT", "100")),
        max_scroll_points=int(os.getenv("MAX_SCROLL_POINTS", "50000")),
        scroll_page_size=int(os.getenv("SCROLL_PAGE_SIZE", "1000")),
        max_files_per_scan=int(os.getenv("MAX_FILES_PER_SCAN", "10000")),
        max_dirs_per_scan=int(os.getenv("MAX_DIRS_PER_SCAN", "2000")),
        graceful_shutdown_timeout=int(os.getenv("GRACEFUL_SHUTDOWN_TIMEOUT", "60")),
        auto_sync=_parse_bool(os.getenv("AUTO_SYNC"), default=True),
        reports_retry_base_ttl_seconds=int(os.getenv("REPORTS_RETRY_BASE_TTL_SECONDS", "86400")),
        reports_retry_max_ttl_seconds=int(os.getenv("REPORTS_RETRY_MAX_TTL_SECONDS", "2592000")),
        reports_max_attempts=int(os.getenv("REPORTS_MAX_ATTEMPTS", "5")),
        reports_claim_lease_seconds=int(os.getenv("REPORTS_CLAIM_LEASE_SECONDS", "3600")),
        llm_provider=os.getenv("LLM_PROVIDER", "lm_studio"),
        anthproxy_url=os.getenv("ANTHPROXY_URL", "http://127.0.0.1:8082"),
        anthproxy_model=os.getenv("ANTHPROXY_MODEL", "haiku"),
        anthproxy_llm_batch_size=int(os.getenv("ANTHPROXY_LLM_BATCH_SIZE", "50")),
        anthproxy_llm_max_prompt_chars=int(os.getenv("ANTHPROXY_LLM_MAX_PROMPT_CHARS", "80000")),
        allowed_non_git_roots=_parse_path_list(os.getenv("ALLOWED_NON_GIT_ROOTS", "")),
        auto_purge_non_git_roots=_parse_bool(os.getenv("AUTO_PURGE_NON_GIT_ROOTS"), default=True),
        reconcile_on_startup=_parse_bool(os.getenv("RECONCILE_ON_STARTUP"), default=True),
        entity_search_limit=int(os.getenv("ENTITY_SEARCH_LIMIT", "20")),
        community_cap_ratio=float(os.getenv("COMMUNITY_CAP_RATIO", "0.3")),
        entity_extraction_concurrency=int(os.getenv("ENTITY_EXTRACTION_CONCURRENCY", "4")),
        targeting_log_full_query=_parse_bool(os.getenv("TARGETING_LOG_FULL_QUERY"), default=False),
        query_log_max_chars=int(os.getenv("QUERY_LOG_MAX_CHARS", "64")),
        search_root_timeout_seconds=int(os.getenv("SEARCH_ROOT_TIMEOUT_SECONDS") or "60") or 60,
    )


def resolve_project_root(watch_dirs: list[str]) -> Optional[Path]:
    """Resolve the project root this server instance should auto-maintain.

    Prefers an explicit WATCH_DIR; otherwise falls back to the PWD env var, which
    Claude Code sets to the directory it was launched in. Note os.getcwd() is NOT a
    safe fallback: ``uv run --directory`` rewrites the cwd to the server package dir
    while leaving PWD pointed at the launching project. Returns None when no reliable
    project root can be determined (auto-maintain is then skipped).
    """
    if watch_dirs:
        return Path(watch_dirs[0]).expanduser().resolve(strict=False)

    pwd = os.environ.get("PWD")
    if pwd:
        candidate = Path(pwd).expanduser()
        if candidate.is_dir():
            return candidate.resolve(strict=False)

    return None


def _parse_bool(value: Optional[str], default: bool) -> bool:
    """Parse a boolean environment variable, falling back to default when unset."""
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_watch_dirs(watch_dir_env: str) -> list[str]:
    """Parse comma-separated WATCH_DIR environment variable."""
    if not watch_dir_env or not watch_dir_env.strip():
        return []
    dirs = [d.strip() for d in watch_dir_env.split(",")]
    return [d for d in dirs if d]


def _parse_path_list(value: str) -> list[str]:
    """Parse a comma-separated list of paths into resolved posix strings."""
    if not value or not value.strip():
        return []
    return [
        Path(p.strip()).expanduser().resolve(strict=False).as_posix()
        for p in value.split(",")
        if p.strip()
    ]


def resolve_path(path: str, base_dir: Optional[str] = None) -> Path:
    """Resolve a path, making it absolute if relative."""
    path_obj = Path(path).expanduser()

    if path_obj.is_absolute():
        return path_obj.resolve(strict=False)

    if base_dir:
        return (Path(base_dir).expanduser() / path_obj).resolve(strict=False)

    watch_dirs = _parse_watch_dirs(os.getenv("WATCH_DIR", ""))
    if watch_dirs:
        return (Path(watch_dirs[0]).expanduser() / path_obj).resolve(strict=False)

    return path_obj.resolve(strict=False)
