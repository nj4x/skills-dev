from vectors.safety import ExclusionPolicy


def test_secret_filenames_and_patterns_are_skipped():
    policy = ExclusionPolicy()
    for path in ["/tmp/app/.env.local", "/tmp/app/key.pem", "/tmp/app/.ssh/id_rsa", "/tmp/app/credentials.json"]:
        decision = policy.should_index_path(path)
        assert decision.action == "skip"
        assert decision.secret_risk is True
        assert decision.safe_to_auto_delete_if_stale is False


def test_content_scan_returns_rule_ids_not_values():
    policy = ExclusionPolicy()
    secret_value = "secret = 'super-sensitive-token-value'"
    reasons = policy.scan_content_signals(secret_value)
    assert "generic_secret_assignment" in reasons
    assert all("super-sensitive" not in reason for reason in reasons)


def test_non_secret_source_file_indexes():
    policy = ExclusionPolicy()
    decision = policy.should_index_path("/tmp/app/src/main.py")
    assert decision.action == "index"
    assert decision.reason_codes == []


def test_worktree_paths_are_skipped_for_files_and_directories():
    policy = ExclusionPolicy()

    file_decision = policy.should_index_path("/tmp/app/.claude/worktrees/agent-1/src/main.py")
    assert file_decision.action == "skip"
    assert "excluded_directory" in file_decision.reason_codes

    directory_decision = policy.should_traverse_path("/tmp/app/.claude/worktrees/agent-1")
    assert directory_decision.action == "skip"
    assert "excluded_directory" in directory_decision.reason_codes


def test_non_excluded_directories_can_be_traversed():
    policy = ExclusionPolicy()
    decision = policy.should_traverse_path("/tmp/app/src")
    assert decision.action == "index"
    assert decision.reason_codes == []


def test_multi_segment_excluded_directories_match_descendants():
    policy = ExclusionPolicy(excluded_directories=[".claude/worktrees"])

    assert policy.should_traverse_path("/tmp/app/.claude/worktrees").action == "skip"
    assert policy.should_traverse_path("/tmp/app/.claude/worktrees/agent-1/src").action == "skip"
    assert policy.should_traverse_path("/tmp/app/.claude/other").action == "index"
