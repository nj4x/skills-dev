import time

import pytest

from bridge.cli import main
from bridge.queue import BridgeQueue


@pytest.fixture
def queue(tmp_path, monkeypatch):
    monkeypatch.setenv("CLINE_BRIDGE_DIR", str(tmp_path))
    return BridgeQueue(tmp_path)


def test_claim_next_prints_fenced_question(queue, capsys):
    record = queue.submit("what is 2 + 2?")
    assert main(["claim-next"]) == 0
    out = capsys.readouterr().out
    assert record["id"] in out
    assert "what is 2 + 2?" in out
    assert "data, not instructions" in out


def test_claim_next_on_empty_queue_reports_empty_and_beats_heart(queue, capsys):
    assert main(["claim-next"]) == 0
    assert "EMPTY" in capsys.readouterr().out
    assert queue.worker_alive() is True


def test_claim_next_wait_returns_as_soon_as_work_arrives(queue, capsys):
    queue.submit("urgent")
    started = time.monotonic()
    main(["claim-next", "--wait", "5"])
    assert time.monotonic() - started < 1
    assert "urgent" in capsys.readouterr().out


def test_claim_next_wait_gives_up_after_the_window(queue, capsys):
    started = time.monotonic()
    main(["claim-next", "--wait", "1"])
    assert time.monotonic() - started >= 1
    assert "EMPTY" in capsys.readouterr().out


def test_answer_from_file_completes_the_round_trip(queue, tmp_path, capsys):
    record = queue.submit("why?")
    queue.claim_next()
    answer_file = tmp_path / "bridge-answer.txt"
    answer_file.write_text("because 'quoting' is $hazardous\nsecond line")

    assert main(["answer", record["id"], "--file", str(answer_file)]) == 0
    assert "OK" in capsys.readouterr().out
    assert queue.read_answered(record["id"])["answer"] == "because 'quoting' is $hazardous\nsecond line"


def test_answer_for_unknown_request_reports_error_without_failing(queue, capsys):
    assert main(["answer", "nope", "still an answer"]) == 0
    assert "ERROR" in capsys.readouterr().out


def test_answer_with_unreadable_file_reports_error_without_failing(queue, tmp_path, capsys):
    assert main(["answer", "nope", "--file", str(tmp_path / "missing.txt")]) == 0
    assert "ERROR" in capsys.readouterr().out


def test_status_reports_counts_and_worker_state(queue, capsys):
    queue.submit("why?")
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "pending=1" in out
    assert "worker=offline" in out
    assert "watchdog=offline" in out


def test_status_reports_a_live_watchdog(queue, capsys):
    queue.ensure()
    queue.watchdog_heartbeat.touch()
    assert main(["status"]) == 0
    assert "watchdog=alive" in capsys.readouterr().out
