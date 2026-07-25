from pathlib import Path

from vectors import gitignore
from vectors.gitignore import GitignoreMatcher


def _make_repo(root: Path) -> None:
    """Create a minimal fake git repo (no real git needed)."""
    (root / ".git" / "info").mkdir(parents=True)


def test_repo_root_detection(tmp_path):
    _make_repo(tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    matcher = GitignoreMatcher.for_path(nested / "file.py")
    assert matcher is not None
    assert matcher.repo_root == tmp_path.resolve()


def test_no_git_repo_returns_none(tmp_path):
    # tmp_path has no .git anywhere -> for_path returns None
    assert GitignoreMatcher.for_path(tmp_path / "file.py") is None


def test_matches_root_gitignore(tmp_path):
    _make_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("build/\n*.log\n")
    matcher = GitignoreMatcher.for_path(tmp_path)
    matcher.preload(tmp_path)

    build_dir = tmp_path / "build"
    build_dir.mkdir()
    assert matcher.is_ignored(build_dir) is True
    assert matcher.is_ignored(tmp_path / "app.log") is True
    assert matcher.is_ignored(tmp_path / "app.py") is False


def test_matches_nested_gitignore(tmp_path):
    _make_repo(tmp_path)
    sub = tmp_path / "sub"
    other = tmp_path / "other"
    sub.mkdir()
    other.mkdir()
    (sub / ".gitignore").write_text("foo\n")

    matcher = GitignoreMatcher.for_path(tmp_path)
    matcher.preload(tmp_path)
    matcher.preload(sub)
    matcher.preload(other)

    assert matcher.is_ignored(sub / "foo") is True
    # Same name under a different directory is not covered by sub/.gitignore
    assert matcher.is_ignored(other / "foo") is False


def test_git_info_exclude(tmp_path):
    _make_repo(tmp_path)
    (tmp_path / ".git" / "info" / "exclude").write_text("secret-notes/\n")
    matcher = GitignoreMatcher.for_path(tmp_path)

    notes = tmp_path / "secret-notes"
    notes.mkdir()
    assert matcher.is_ignored(notes) is True


def test_negation_within_file(tmp_path):
    _make_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("*.log\n!keep.log\n")
    matcher = GitignoreMatcher.for_path(tmp_path)
    matcher.preload(tmp_path)

    assert matcher.is_ignored(tmp_path / "debug.log") is True
    assert matcher.is_ignored(tmp_path / "keep.log") is False


def test_path_outside_repo_not_ignored(tmp_path):
    _make_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("*.log\n")
    matcher = GitignoreMatcher.for_path(tmp_path)
    # A path outside the repo root is never reported as ignored.
    assert matcher.is_ignored(Path("/elsewhere/app.log")) is False


def test_preload_ancestors_loads_nested(tmp_path):
    _make_repo(tmp_path)
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    (deep / ".gitignore").write_text("ignored.txt\n")
    matcher = GitignoreMatcher.for_path(tmp_path)

    target = deep / "ignored.txt"
    # Without preloading, the nested spec is not yet cached.
    matcher.preload_ancestors(target)
    assert matcher.is_ignored(target) is True


def test_pathspec_missing_is_graceful(tmp_path, monkeypatch):
    _make_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("build/\n")
    monkeypatch.setattr(gitignore, "pathspec", None)

    # for_path returns None when pathspec is unavailable -> callers skip gitignore.
    assert GitignoreMatcher.for_path(tmp_path) is None

    # Even a directly constructed matcher degrades to "nothing ignored".
    matcher = GitignoreMatcher(tmp_path.resolve())
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    assert matcher.is_ignored(build_dir) is False
