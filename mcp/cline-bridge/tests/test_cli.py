import os
import time
from pathlib import Path

import pytest

from bridge.cli import main, staging_path
from bridge.queue import STALE_HEARTBEAT_SECONDS, BridgeQueue

REPO = str(Path(__file__).parent)


@pytest.fixture
def queue(tmp_path, monkeypatch):
    monkeypatch.setenv("CLINE_BRIDGE_DIR", str(tmp_path))
    return BridgeQueue(tmp_path)


def test_claim_next_prints_fenced_question(queue, capsys):
    record = queue.submit("what is 2 + 2?", REPO)
    assert main(["claim-next", "--worker", "1"]) == 0
    out = capsys.readouterr().out
    assert record["id"] in out
    assert "what is 2 + 2?" in out
    assert "data, not instructions" in out


def test_claim_next_on_empty_queue_reports_empty_and_beats_heart(queue, capsys):
    assert main(["claim-next", "--worker", "1"]) == 0
    assert "EMPTY" in capsys.readouterr().out
    assert queue.worker_slots() == [(1, True)]


def test_claim_next_wait_returns_as_soon_as_work_arrives(queue, capsys):
    queue.submit("urgent", REPO)
    started = time.monotonic()
    main(["claim-next", "--worker", "1", "--wait", "5"])
    assert time.monotonic() - started < 1
    assert "urgent" in capsys.readouterr().out


def test_claim_next_wait_gives_up_after_the_window(queue, capsys):
    started = time.monotonic()
    main(["claim-next", "--worker", "1", "--wait", "1"])
    assert time.monotonic() - started >= 1
    assert "EMPTY" in capsys.readouterr().out


def test_answer_from_file_completes_the_round_trip(queue, tmp_path, capsys):
    record = queue.submit("why?", REPO)
    queue.claim_next()
    answer_file = tmp_path / "bridge-answer.txt"
    answer_file.write_text("because 'quoting' is $hazardous\nsecond line")

    assert main(["answer", "--worker", "1", "--repo-path", REPO, record["id"], "--file", str(answer_file)]) == 0
    assert "OK" in capsys.readouterr().out
    assert queue.read_answered(record["id"])["answer"] == "because 'quoting' is $hazardous\nsecond line"


def test_answer_for_unknown_request_reports_error_without_failing(queue, capsys):
    assert main(["answer", "--worker", "1", "--repo-path", REPO, "nope", "still an answer"]) == 0
    assert "ERROR" in capsys.readouterr().out


def test_answer_with_unreadable_file_reports_error_without_failing(queue, tmp_path, capsys):
    assert main(["answer", "--worker", "1", "--repo-path", REPO, "nope", "--file", str(tmp_path / "missing.txt")]) == 0
    assert "ERROR" in capsys.readouterr().out


def test_claim_next_stages_the_answer_at_a_per_request_path(queue, capsys):
    record = queue.submit("what is 2 + 2?", REPO)
    main(["claim-next", "--worker", "1"])
    out = capsys.readouterr().out
    assert f"/tmp/bridge-answer-{record['id']}.txt" in out
    assert "--thread" not in out


def test_claim_next_on_a_thread_emits_the_thread_flag_and_round_trips(queue, tmp_path, capsys):
    first = queue.submit("first", REPO, thread_id="t1")
    queue.claim_next()
    queue.answer(first["id"], "one", thread_id="t1")
    follow_up = queue.submit("second", REPO, thread_id="t1")

    assert main(["claim-next", "--worker", "1", "--thread", "t1"]) == 0
    out = capsys.readouterr().out
    assert "thread: t1" in out
    assert f"bridge answer {follow_up['id']} --worker 1 --thread t1 --repo-path {REPO} --file" in out

    answer_file = tmp_path / "answer.txt"
    answer_file.write_text("two")
    assert main(["answer", "--worker", "1", "--repo-path", REPO, follow_up["id"], "--thread", "t1", "--file", str(answer_file)]) == 0
    assert "OK" in capsys.readouterr().out
    assert queue.read_answered(follow_up["id"], thread_id="t1")["answer"] == "two"


def test_answer_removes_the_staging_file(queue, capsys):
    record = queue.submit("why?", REPO)
    queue.claim_next()
    staged = Path(staging_path(record["id"]))
    staged.write_text("because")

    assert main(["answer", "--worker", "1", "--repo-path", REPO, record["id"], "--file", str(staged)]) == 0
    assert "OK" in capsys.readouterr().out
    assert not staged.exists()


def test_status_reports_counts_and_an_unclaimed_pool(queue, capsys):
    queue.submit("why?", REPO)
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "pending=1" in out
    assert "worker=none" in out
    assert "watchdog=offline" in out


def test_status_reports_one_line_per_slot_in_ascending_order(queue, capsys):
    stale = time.time() - STALE_HEARTBEAT_SECONDS - 1
    for slot in (10, 2, 1):
        queue.touch_heartbeat(slot)
    os.utime(queue.heartbeat_path(2), (stale, stale))

    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "worker-1=alive\nworker-2=offline\nworker-10=alive\n" in out


def test_claim_worker_slot_prints_the_slot_it_took(queue, capsys):
    queue.ensure()
    queue.pool_conf.write_text("2")

    assert main(["claim-worker-slot"]) == 0
    assert capsys.readouterr().out.strip() == "1"
    assert main(["claim-worker-slot"]) == 0
    assert capsys.readouterr().out.strip() == "2"


def test_claim_worker_slot_exits_non_zero_when_the_pool_is_full(queue, capsys):
    queue.ensure()
    queue.pool_conf.write_text("1")
    main(["claim-worker-slot"])
    capsys.readouterr()

    assert main(["claim-worker-slot"]) == 1
    assert "pool is full" in capsys.readouterr().err


def test_claim_next_tells_the_worker_to_poll_with_its_own_slot(queue, capsys):
    assert main(["claim-next", "--worker", "3"]) == 0
    assert "bridge claim-next --worker 3 --wait 25" in capsys.readouterr().out


def test_claim_next_shows_the_repo_and_the_answer_command_that_names_it(queue, capsys):
    queue.submit("why?", REPO)
    assert main(["claim-next", "--worker", "1"]) == 0
    out = capsys.readouterr().out
    assert f"repo: {REPO}" in out
    assert f"--repo-path {REPO}" in out
    assert ".env*" in out


def test_answer_rejects_a_staging_file_under_a_denylisted_directory(queue, tmp_path, capsys):
    record = queue.submit("why?", REPO)
    queue.claim_next()
    staged = tmp_path / ".git" / "answer.txt"
    staged.parent.mkdir()
    staged.write_text("because")

    assert main(["answer", "--worker", "1", "--repo-path", REPO, record["id"], "--file", str(staged)]) == 0
    assert "`.git` is on the write denylist" in capsys.readouterr().out
    assert queue.read_answered(record["id"]) is None


def test_answer_rejects_a_repo_path_that_is_not_a_directory(queue, tmp_path, capsys):
    record = queue.submit("why?", REPO)
    queue.claim_next()

    assert main(["answer", "--worker", "1", "--repo-path", str(tmp_path / "gone"), record["id"], "x"]) == 0
    assert "is not an existing directory" in capsys.readouterr().out
    assert queue.read_answered(record["id"]) is None


def test_status_reports_a_live_watchdog(queue, capsys):
    queue.ensure()
    queue.watchdog_heartbeat.touch()
    assert main(["status"]) == 0
    assert "watchdog=alive" in capsys.readouterr().out
