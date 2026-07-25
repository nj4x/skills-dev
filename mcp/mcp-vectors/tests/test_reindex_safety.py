import asyncio
import subprocess

import pytest

from vectors.config import Config
from vectors.errors import NoGitRepository, UnsupportedBareRepository, UnsupportedLinkedWorktree
from vectors.paths import PathPolicy
from vectors.rag import RAGPipeline
from vectors.testing import InMemoryVectorStore


class _StubLMClient:
    embedding_dimension = 1

    async def initialize(self):
        return None


class _StubVectorStore:
    async def initialize(self):
        return None



def _make_initialized_pipeline():
    pipeline = RAGPipeline(Config(), lm_client=_StubLMClient(), vector_store=_StubVectorStore())
    pipeline._initialized = True
    return pipeline


def test_collect_indexable_files_skips_secret_and_reports_reason(tmp_path):
    (tmp_path / "src").mkdir()
    code = tmp_path / "src" / "app.py"
    code.write_text("print('hi')")
    secret = tmp_path / ".env.local"
    secret.write_text("TOKEN=secret")

    pipeline = RAGPipeline(Config(), lm_client=object(), vector_store=object())
    plan = pipeline.collect_indexable_files(tmp_path)

    assert code in plan.files
    skipped = {item["path"]: item for item in plan.skipped if "path" in item}
    assert str(secret.resolve()) in skipped
    assert skipped[str(secret.resolve())]["secret_risk"] is True


def test_collect_indexable_files_respects_max_files(tmp_path):
    for index in range(3):
        (tmp_path / f"file{index}.py").write_text("print('hi')")

    pipeline = RAGPipeline(Config(), lm_client=object(), vector_store=object())
    plan = pipeline.collect_indexable_files(tmp_path, max_files=2)

    assert len(plan.files) == 2
    assert plan.partial is True
    assert plan.limit_hit == "max_files"


def test_collect_indexable_files_rejects_worktree_root_without_descending(tmp_path):
    worktree = tmp_path / ".claude" / "worktrees" / "agent-1"
    worktree.mkdir(parents=True)
    (worktree / "app.py").write_text("print('hi')")

    pipeline = RAGPipeline(Config(), lm_client=object(), vector_store=object())
    plan = pipeline.collect_indexable_files(worktree)

    assert plan.files == []
    assert plan.dirs_scanned == 0
    assert plan.files_scanned == 0
    assert plan.skipped[0]["path"] == str(worktree.resolve())
    assert "excluded_directory" in plan.skipped[0]["reason_codes"]


def test_collect_indexable_files_skips_nested_worktree_subtree(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    code = src / "app.py"
    code.write_text("print('hi')")
    worktree = tmp_path / ".claude" / "worktrees" / "agent-1"
    worktree.mkdir(parents=True)
    worktree_file = worktree / "app.py"
    worktree_file.write_text("print('nope')")

    pipeline = RAGPipeline(Config(), lm_client=object(), vector_store=object())
    plan = pipeline.collect_indexable_files(tmp_path)

    assert code in plan.files
    assert worktree_file not in plan.files
    skipped_paths = {item["path"] for item in plan.skipped if "path" in item}
    assert str((tmp_path / ".claude").resolve()) in skipped_paths


def test_index_file_rejects_explicit_worktree_file(tmp_path):
    worktree = tmp_path / ".claude" / "worktrees" / "agent-1"
    worktree.mkdir(parents=True)
    worktree_file = worktree / "app.py"
    worktree_file.write_text("print('nope')")
    pipeline = _make_initialized_pipeline()

    result = asyncio.run(pipeline.index_file(worktree_file))

    assert result.success is False
    assert result.skipped is True
    assert "excluded_directory" in result.reason_codes


def _git_init_commit(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "T"], check=True)
    (path / "f.txt").write_text("hi")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)
    return path.resolve()


def test_index_file_in_non_git_dir_raises_no_git_repository(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    f = plain / "code.py"
    f.write_text("x = 1")

    with pytest.raises(NoGitRepository) as exc_info:
        asyncio.run(_make_initialized_pipeline().index_file(f))

    assert exc_info.value.error_code == "no_repository"
    assert exc_info.value.probe == f.resolve()


def test_index_file_in_linked_worktree_raises_unsupported(tmp_path):
    main = _git_init_commit(tmp_path / "main")
    wt = tmp_path / "linked"
    subprocess.run(
        ["git", "-C", str(main), "worktree", "add", "-q", str(wt), "-b", "linked"],
        check=True,
    )
    f = wt / "code.py"
    f.write_text("x = 1")

    with pytest.raises(UnsupportedLinkedWorktree) as exc_info:
        asyncio.run(_make_initialized_pipeline().index_file(f))

    assert exc_info.value.error_code == "unsupported_linked_worktree"


def test_index_file_in_bare_repo_raises_unsupported(tmp_path):
    bare = tmp_path / "repo.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    # Probe the bare repo dir itself
    with pytest.raises(UnsupportedBareRepository) as exc_info:
        asyncio.run(_make_initialized_pipeline().index_file(bare))
    assert exc_info.value.error_code == "unsupported_bare_repository"


def test_index_directory_in_non_git_dir_raises_no_git_repository(tmp_path):
    plain = tmp_path / "docs"
    plain.mkdir()
    (plain / "readme.md").write_text("hello")

    with pytest.raises(NoGitRepository):
        asyncio.run(_make_initialized_pipeline().index_directory(plain))


def test_index_directory_rejects_worktree_root(tmp_path):
    worktree = tmp_path / ".claude" / "worktrees" / "agent-1"
    worktree.mkdir(parents=True)
    (worktree / "app.py").write_text("print('nope')")
    pipeline = _make_initialized_pipeline()

    results = asyncio.run(pipeline.index_directory(worktree))

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].skipped is True
    assert "excluded_directory" in results[0].reason_codes


# ---------------------------------------------------------------------------
# Fix 1 regression: index_directory forwards canonical root, not caller dir
# ---------------------------------------------------------------------------


class _EmbedLMClient:
    """Minimal LM client that returns constant embeddings."""

    embedding_dimension = 4
    embedding_model = "stub"
    llm_model = "stub"

    async def initialize(self):
        pass

    async def get_embedding(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]

    async def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

    async def close(self):
        pass


def test_index_directory_stores_canonical_root_not_subdir(tmp_path):
    """Regression: indexing a git subdirectory must record root_id = git root, not subdir.

    Before Fix 1, `canonical_root` was never computed; `index_file` received the
    caller-supplied directory as root_path, producing a subdir-scoped root_id in
    the vector store.  The fix passes `dir_resolution.canonical_root` instead.
    """
    # Set up a real git repo with a pkg/ subdirectory.
    repo = tmp_path / "myrepo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    pkg = repo / "pkg"
    pkg.mkdir()
    src = pkg / "mod.py"
    src.write_text("x = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)

    store = InMemoryVectorStore(vector_size=4)
    pipeline = RAGPipeline(Config(), lm_client=_EmbedLMClient(), vector_store=store)
    pipeline._initialized = True
    store.update_vector_size(4)

    # Index the *subdirectory*, not the repo root.
    results = asyncio.run(pipeline.index_directory(pkg))

    assert any(r.success for r in results), f"No file indexed successfully: {results}"

    # Every stored point must carry the canonical git root, not pkg/.
    canonical_key = PathPolicy.path_key(repo.resolve())
    subdir_key = PathPolicy.path_key(pkg.resolve())
    assert store._points, "no vectors were stored"
    for point in store._points:
        root_id = point["payload"]["root_id"]
        assert root_id == canonical_key, (
            f"Expected root_id={canonical_key!r}, got {root_id!r} — "
            "index_directory is not forwarding the canonical root (Fix 1 regression)"
        )
        assert root_id != subdir_key, "root_id must not be the subdirectory path"


# ---------------------------------------------------------------------------
# Fix 2 regression: index_file ignores caller-supplied subdir root_path
# ---------------------------------------------------------------------------


def test_index_file_with_explicit_subdir_root_path_uses_canonical_root(tmp_path):
    """Regression: index_file must ignore a caller-supplied subdir root_path.

    Before this fix, the condition was `if root_path is None and canonical_root
    is not None`, so an explicit subdir passed as root_path bypassed canonical
    resolution and minted a subdir-scoped vector-store root_id.  The fix removes
    the `root_path is None` guard so canonical_root always wins.
    """
    repo = tmp_path / "myrepo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    pkg = repo / "pkg"
    pkg.mkdir()
    src = pkg / "mod.py"
    src.write_text("x = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)

    store = InMemoryVectorStore(vector_size=4)
    pipeline = RAGPipeline(Config(), lm_client=_EmbedLMClient(), vector_store=store)
    pipeline._initialized = True
    store.update_vector_size(4)

    # Caller explicitly passes the subdir as root_path — must be overridden.
    result = asyncio.run(pipeline.index_file(src, root_path=pkg))

    assert result.success, f"index_file failed: {result.error}"

    canonical_key = PathPolicy.path_key(repo.resolve())
    subdir_key = PathPolicy.path_key(pkg.resolve())
    assert store._points, "no vectors were stored"
    for point in store._points:
        root_id = point["payload"]["root_id"]
        assert root_id == canonical_key, (
            f"Expected root_id={canonical_key!r}, got {root_id!r} — "
            "index_file is not overriding caller-supplied subdir root_path (Fix 2 regression)"
        )
        assert root_id != subdir_key, "root_id must not be the subdirectory path"
