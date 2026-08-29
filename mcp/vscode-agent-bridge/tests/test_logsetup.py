import logging

from bridge.logsetup import TaskIdFilter, set_task_id, setup_logging, task_id_var


def _make_record() -> logging.LogRecord:
    return logging.LogRecord("vscode-agent-bridge", logging.INFO, "x.py", 1, "msg", None, None)


def test_filter_injects_empty_task_id_when_unset():
    token = task_id_var.set("")
    try:
        record = _make_record()
        assert TaskIdFilter().filter(record) is True
        assert record.task_id == ""
    finally:
        task_id_var.reset(token)


def test_filter_injects_task_id_from_contextvar():
    token = task_id_var.set("abc123")
    try:
        record = _make_record()
        TaskIdFilter().filter(record)
        assert record.task_id == "abc123"
    finally:
        task_id_var.reset(token)


def test_set_task_id_updates_contextvar():
    set_task_id("deadbeef")
    assert task_id_var.get() == "deadbeef"
    set_task_id(None)
    assert task_id_var.get() == ""


def test_setup_logging_writes_to_file_with_task_id(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    logger = setup_logging()
    set_task_id("t1")
    logger.info("hello world")
    for handler in logger.handlers:
        handler.flush()
    log_file = tmp_path / ".vscode-agent-bridge" / "logs" / "vscode-agent-bridge.log"
    assert log_file.exists()
    content = log_file.read_text()
    assert "[task_id=t1]" in content
    assert "hello world" in content
    set_task_id(None)


def test_setup_logging_nonfatal_when_dir_uncreatable(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "blocked"
    blocker.write_text("")  # file where a directory is needed
    monkeypatch.setenv("HOME", str(blocker))
    logger = setup_logging()  # must not raise
    logger.info("still works")  # must not raise either
    assert "vscode-agent-bridge: file logging disabled" in capsys.readouterr().err


def test_setup_logging_nonfatal_when_home_unresolvable(monkeypatch, capsys):
    import bridge.logsetup as logsetup

    def _raise():
        raise RuntimeError("could not determine home directory")

    monkeypatch.setattr(logsetup.Path, "home", staticmethod(_raise))
    logger = setup_logging()  # must not raise
    logger.info("still works")  # must not raise either
    assert "vscode-agent-bridge: file logging disabled" in capsys.readouterr().err


def test_setup_logging_idempotent_no_duplicate_handlers(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    setup_logging()
    logger = setup_logging()
    assert len(logger.handlers) == 1
