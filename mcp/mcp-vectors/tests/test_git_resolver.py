"""Tests for the GitResolver two-phase Git-plumbing resolver (ADR-0006)."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from vectors.config import Config
from vectors.git_resolver import GitResolution, GitResolver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(path: Path) -> Path:
    """Initialize a git repo at path; return the resolved root."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "T"], check=True)
    (path / "f.txt").write_text("hi")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)
    return path.resolve()


def _make_bare_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", "-q", str(path)], check=True)
    return path.resolve()


def _make_linked_worktree(main: Path, wt: Path) -> Path:
    """Add a linked worktree at wt from repo at main."""
    wt.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(main), "worktree", "add", "-q", str(wt), "-b", "linked"],
        check=True,
    )
    return wt.resolve()


def _make_submodule(super_path: Path, sub_name: str, inner_path: Path) -> Path:
    """Manually simulate a submodule checkout (file-transport not allowed here)."""
    inner_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(inner_path)], check=True)
    subprocess.run(["git", "-C", str(inner_path), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(inner_path), "config", "user.name", "T"], check=True)
    (inner_path / "g.txt").write_text("sub")
    subprocess.run(["git", "-C", str(inner_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(inner_path), "commit", "-qm", "inner"], check=True)

    # Create modules dir and copy git db
    modules_dir = super_path / ".git" / "modules" / sub_name
    modules_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-r", str(inner_path / ".git") + "/.", str(modules_dir)], check=True)
    subprocess.run(
        ["git", "-C", str(modules_dir), "config", "core.worktree", str(super_path / sub_name)],
        check=True,
    )

    # Create submodule working directory
    sub_wt = super_path / sub_name
    sub_wt.mkdir(parents=True, exist_ok=True)
    (sub_wt / ".git").write_text(f"gitdir: ../.git/modules/{sub_name}\n")
    (sub_wt / "g.txt").write_text("sub")
    return sub_wt.resolve()


def _make_separate_git_dir(wt_path: Path, git_path: Path) -> Path:
    wt_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", f"--separate-git-dir={git_path}", str(wt_path)],
        check=True,
    )
    subprocess.run(["git", "-C", str(wt_path), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(wt_path), "config", "user.name", "T"], check=True)
    (wt_path / "h.txt").write_text("sep")
    subprocess.run(["git", "-C", str(wt_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(wt_path), "commit", "-qm", "init"], check=True)
    return wt_path.resolve()


# ---------------------------------------------------------------------------
# Normal working tree
# ---------------------------------------------------------------------------

def test_normal_repo_root(tmp_path: Path):
    root = _make_repo(tmp_path / "repo")
    res = GitResolver.resolve_root(root, Config())
    assert res.status == "supported_working_tree"
    assert res.canonical_root == root


def test_subdirectory_maps_to_repo_root(tmp_path: Path):
    root = _make_repo(tmp_path / "repo")
    sub = root / "src" / "pkg"
    sub.mkdir(parents=True)
    res = GitResolver.resolve_root(sub, Config())
    assert res.status == "supported_working_tree"
    assert res.canonical_root == root


def test_file_inside_repo_maps_to_repo_root(tmp_path: Path):
    root = _make_repo(tmp_path / "repo")
    f = root / "main.py"
    f.write_text("x = 1")
    res = GitResolver.resolve_root(f, Config())
    assert res.status == "supported_working_tree"
    assert res.canonical_root == root


# ---------------------------------------------------------------------------
# Separate-git-dir
# ---------------------------------------------------------------------------

def test_separate_git_dir_maps_to_working_tree_root(tmp_path: Path):
    wt = _make_separate_git_dir(tmp_path / "wt", tmp_path / "git_store")
    res = GitResolver.resolve_root(wt, Config())
    assert res.status == "supported_working_tree"
    assert res.canonical_root == wt


# ---------------------------------------------------------------------------
# Submodule
# ---------------------------------------------------------------------------

def test_submodule_has_own_canonical_root(tmp_path: Path):
    super_root = _make_repo(tmp_path / "super")
    sub_wt = _make_submodule(super_root, "inner", tmp_path / "inner_src")
    res = GitResolver.resolve_root(sub_wt, Config())
    assert res.status == "supported_working_tree"
    assert res.canonical_root == sub_wt


def test_submodule_root_differs_from_superproject(tmp_path: Path):
    super_root = _make_repo(tmp_path / "super")
    sub_wt = _make_submodule(super_root, "inner", tmp_path / "inner_src")
    res_super = GitResolver.resolve_root(super_root, Config())
    res_sub = GitResolver.resolve_root(sub_wt, Config())
    assert res_super.canonical_root != res_sub.canonical_root


# ---------------------------------------------------------------------------
# Linked worktree
# ---------------------------------------------------------------------------

def test_linked_worktree_rejected(tmp_path: Path):
    main = _make_repo(tmp_path / "main")
    wt = _make_linked_worktree(main, tmp_path / "linked")
    res = GitResolver.resolve_root(wt, Config())
    assert res.status == "unsupported_linked_worktree"
    assert res.canonical_root is None


def test_path_inside_linked_worktree_also_rejected(tmp_path: Path):
    main = _make_repo(tmp_path / "main")
    wt = _make_linked_worktree(main, tmp_path / "linked")
    sub = wt / "src"
    sub.mkdir()
    res = GitResolver.resolve_root(sub, Config())
    assert res.status == "unsupported_linked_worktree"


def test_linked_worktree_of_separate_git_dir_repo_rejected(tmp_path: Path):
    """Regression: a linked worktree of a --separate-git-dir repo has its git dir
    under <external>/worktrees/<name> — no literal '.git/worktrees/' — so the old
    substring heuristic misclassified it as a normal work tree. The --git-common-dir
    vs --absolute-git-dir comparison (ADR-0006) must still reject it."""
    work = tmp_path / "work"
    git_dir = tmp_path / "external.git"
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", f"--separate-git-dir={git_dir}", str(work)], check=True
    )
    subprocess.run(["git", "-C", str(work), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.name", "T"], check=True)
    (work / "f.txt").write_text("hi")
    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-qm", "init"], check=True)

    wt = tmp_path / "linked"
    subprocess.run(
        ["git", "-C", str(work), "worktree", "add", "-q", str(wt), "-b", "linked"],
        check=True,
    )
    # The worktree's git dir lives under the external store, not under '.git/worktrees/'.
    assert "/.git/worktrees/" not in str((git_dir / "worktrees").resolve())

    res = GitResolver.resolve_root(wt.resolve(), Config())
    assert res.status == "unsupported_linked_worktree"
    assert res.canonical_root is None


def test_separate_git_dir_main_worktree_supported(tmp_path: Path):
    """The main work tree of a --separate-git-dir repo is NOT a linked worktree:
    its --absolute-git-dir equals --git-common-dir, so it resolves normally."""
    work = tmp_path / "work"
    git_dir = tmp_path / "external.git"
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", f"--separate-git-dir={git_dir}", str(work)], check=True
    )
    subprocess.run(["git", "-C", str(work), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.name", "T"], check=True)
    (work / "f.txt").write_text("hi")
    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-qm", "init"], check=True)

    res = GitResolver.resolve_root(work.resolve(), Config())
    assert res.status == "supported_working_tree"
    assert res.canonical_root == work.resolve()


# ---------------------------------------------------------------------------
# Bare repository
# ---------------------------------------------------------------------------

def test_bare_repo_rejected(tmp_path: Path):
    bare = _make_bare_repo(tmp_path / "repo.git")
    res = GitResolver.resolve_root(bare, Config())
    assert res.status == "unsupported_bare_repository"
    assert res.canonical_root is None


# ---------------------------------------------------------------------------
# Plain directory (no repository)
# ---------------------------------------------------------------------------

def test_plain_dir_no_repo(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    res = GitResolver.resolve_root(plain, Config())
    assert res.status == "no_repository"
    assert res.canonical_root is None


def test_plain_dir_with_allowlist_entry_returns_allowlisted(tmp_path: Path):
    plain = tmp_path / "docs"
    plain.mkdir()
    config = Config(allowed_non_git_roots=[str(plain)])
    res = GitResolver.resolve_root(plain, config)
    assert res.status == "allowlisted_non_git"
    assert res.canonical_root == plain.resolve()


def test_no_repo_without_matching_allowlist(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    other = tmp_path / "other"
    config = Config(allowed_non_git_roots=[str(other)])
    res = GitResolver.resolve_root(plain, config)
    assert res.status == "no_repository"
    assert res.canonical_root is None


# ---------------------------------------------------------------------------
# Nested allowlist: longest prefix wins
# ---------------------------------------------------------------------------

def test_nested_allowlist_innermost_wins(tmp_path: Path):
    outer = tmp_path / "a"
    inner = tmp_path / "a" / "b"
    target = tmp_path / "a" / "b" / "doc.pdf"
    inner.mkdir(parents=True)
    target.write_text("pdf content")
    config = Config(allowed_non_git_roots=[str(outer), str(inner)])
    res = GitResolver.resolve_root(target, config)
    assert res.status == "allowlisted_non_git"
    assert res.canonical_root == inner.resolve()


# ---------------------------------------------------------------------------
# Git-over-allowlist precedence
# ---------------------------------------------------------------------------

def test_git_repo_inside_allowlisted_dir_uses_git_root(tmp_path: Path):
    outer = tmp_path / "docs"
    repo = outer / "project"
    root = _make_repo(repo)
    config = Config(allowed_non_git_roots=[str(outer)])
    res = GitResolver.resolve_root(root / "src", config)
    # Git wins: canonical root is the git working tree, not the allowlist boundary
    assert res.status == "supported_working_tree"
    assert res.canonical_root == root


# ---------------------------------------------------------------------------
# --git-common-dir relative path normalization
# ---------------------------------------------------------------------------

def test_main_checkout_common_dir_normalized_correctly(tmp_path: Path):
    """Main checkout --git-common-dir is '.git' (relative); must normalize against probe cwd."""
    root = _make_repo(tmp_path / "repo")
    # A sub-sub-dir to ensure normalization works at depth
    deep = root / "a" / "b" / "c"
    deep.mkdir(parents=True)
    res = GitResolver.resolve_root(deep, Config())
    assert res.status == "supported_working_tree"
    assert res.canonical_root == root


# ---------------------------------------------------------------------------
# Inherited GIT_* environment variable isolation
# ---------------------------------------------------------------------------

def test_inherited_ceiling_dirs_does_not_affect_classification(tmp_path: Path):
    """GIT_CEILING_DIRECTORIES set to tmp_path parent should not prevent detection."""
    root = _make_repo(tmp_path / "repo")
    with patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(tmp_path.parent)}):
        res = GitResolver.resolve_root(root, Config())
    assert res.status == "supported_working_tree"
    assert res.canonical_root == root


def test_inherited_git_dir_env_var_does_not_override_resolution(tmp_path: Path):
    """GIT_DIR pointing elsewhere should not affect the clean-env resolver."""
    root = _make_repo(tmp_path / "repo")
    other = tmp_path / "other"
    other.mkdir()
    with patch.dict(os.environ, {"GIT_DIR": str(other)}):
        res = GitResolver.resolve_root(root, Config())
    assert res.status == "supported_working_tree"
    assert res.canonical_root == root


# ---------------------------------------------------------------------------
# Fault-injection: missing git binary
# ---------------------------------------------------------------------------

def test_missing_git_binary_returns_unknown(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with patch("vectors.git_resolver.GitResolver.git_version", return_value=None):
        res = GitResolver.resolve_root(plain, Config())
    assert res.status == "unknown"
    assert res.canonical_root is None


# ---------------------------------------------------------------------------
# Fault-injection: timeout
# ---------------------------------------------------------------------------

def test_timeout_returns_unknown(tmp_path: Path):
    root = _make_repo(tmp_path / "repo")
    import subprocess as sp

    def _raise(*a, **kw):
        raise sp.TimeoutExpired(cmd="git", timeout=10)

    with patch("vectors.git_resolver._run_git", side_effect=_raise):
        res = GitResolver.resolve_root(root, Config())
    assert res.status == "unknown"


# ---------------------------------------------------------------------------
# Fault-injection: permission error on .git
# ---------------------------------------------------------------------------

def test_permission_error_returns_unknown_not_no_repository(tmp_path: Path):
    root = _make_repo(tmp_path / "repo")
    git_dir = root / ".git"
    original_mode = git_dir.stat().st_mode

    try:
        git_dir.chmod(0o000)
        res = GitResolver.resolve_root(root / "src", Config())
        # Should be unknown, not no_repository, because .git exists (even unreadable)
        assert res.status in ("unknown", "unsupported_linked_worktree", "supported_working_tree")
        # Critical: must NOT be no_repository (which would allow purge)
        assert res.status != "no_repository"
    finally:
        git_dir.chmod(original_mode)


# ---------------------------------------------------------------------------
# Fault-injection: probe inside .git dir (is-inside-work-tree=false, is-bare=false)
# ---------------------------------------------------------------------------

def test_probe_inside_git_dir_returns_unknown(tmp_path: Path):
    root = _make_repo(tmp_path / "repo")
    inside_git = root / ".git" / "refs"
    res = GitResolver.resolve_root(inside_git, Config())
    # Probing inside .git itself should be unknown (not a work tree, not bare)
    assert res.status == "unknown"


# ---------------------------------------------------------------------------
# Fingerprint and pre-mutation revalidation
# ---------------------------------------------------------------------------

def test_resolution_carries_fingerprint(tmp_path: Path):
    root = _make_repo(tmp_path / "repo")
    res = GitResolver.resolve_root(root, Config())
    assert isinstance(res.fingerprint, str)
    assert len(res.fingerprint) > 0


def test_same_path_same_fingerprint(tmp_path: Path):
    root = _make_repo(tmp_path / "repo")
    res1 = GitResolver.resolve_root(root, Config())
    res2 = GitResolver.resolve_root(root, Config())
    assert res1.fingerprint == res2.fingerprint


def test_git_init_after_resolution_changes_fingerprint(tmp_path: Path):
    plain = tmp_path / "soon_repo"
    plain.mkdir()
    res_before = GitResolver.resolve_root(plain, Config())
    assert res_before.status == "no_repository"

    _make_repo(plain)
    res_after = GitResolver.resolve_root(plain, Config())
    assert res_after.status == "supported_working_tree"
    assert res_after.fingerprint != res_before.fingerprint


def test_validate_fingerprint_detects_stale_resolution(tmp_path: Path):
    plain = tmp_path / "soon_repo"
    plain.mkdir()
    res_stale = GitResolver.resolve_root(plain, Config())

    _make_repo(plain)
    res_fresh = GitResolver.resolve_root(plain, Config())

    is_valid = GitResolver.validate_fingerprint(plain, Config(), res_stale.fingerprint)
    assert not is_valid

    is_valid_fresh = GitResolver.validate_fingerprint(plain, Config(), res_fresh.fingerprint)
    assert is_valid_fresh


# ---------------------------------------------------------------------------
# git_binary_version is recorded
# ---------------------------------------------------------------------------

def test_resolution_records_git_version(tmp_path: Path):
    root = _make_repo(tmp_path / "repo")
    res = GitResolver.resolve_root(root, Config())
    assert res.git_binary_version is not None
    assert "git" in res.git_binary_version.lower()
