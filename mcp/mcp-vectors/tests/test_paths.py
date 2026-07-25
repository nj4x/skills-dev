import hashlib

import pytest

from vectors.config import Config
from vectors.paths import OperationScope, PathPolicy


def test_component_safe_containment_avoids_prefix_pitfall():
    assert PathPolicy.is_within("/tmp/root/file.py", "/tmp/root")
    assert not PathPolicy.is_within("/tmp/root2/file.py", "/tmp/root")


def test_overlap_parent_child_and_unrelated():
    assert PathPolicy.overlaps("/tmp/root", "/tmp/root/child/file.py")
    assert PathPolicy.overlaps("/tmp/root/child/file.py", "/tmp/root")
    assert not PathPolicy.overlaps("/tmp/root-a", "/tmp/root-b")


def test_relative_to_best_root():
    root = "/tmp/project"
    path = "/tmp/project/src/app.py"
    assert PathPolicy.relative_to_root(path, root) == "src/app.py"
    assert PathPolicy.best_root(path, ["/tmp", root]).as_posix().endswith(root)


def test_root_id_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        PathPolicy.root_id("/tmp/project")


def test_operation_scope_fields():
    scope = OperationScope(canonical_root_id="/repo", requested_path=__import__("pathlib").Path("/repo/src"))
    assert scope.canonical_root_id == "/repo"
    assert scope.requested_path.name == "src"


def test_config_fingerprint_is_deterministic():
    c1 = Config(allowed_non_git_roots=["/a", "/b"])
    c2 = Config(allowed_non_git_roots=["/b", "/a"])
    assert c1.config_fingerprint == c2.config_fingerprint


def test_config_fingerprint_changes_with_allowlist():
    c1 = Config(allowed_non_git_roots=[])
    c2 = Config(allowed_non_git_roots=["/docs"])
    assert c1.config_fingerprint != c2.config_fingerprint


def test_config_fingerprint_is_sha256():
    c = Config(allowed_non_git_roots=[])
    assert len(c.config_fingerprint) == 64
    assert all(ch in "0123456789abcdef" for ch in c.config_fingerprint)
