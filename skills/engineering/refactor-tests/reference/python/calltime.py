"""pytest plugin: record the call-phase duration and final outcome of every test.

Load with `pytest -p calltime` (this directory must be on PYTHONPATH).
Rows are keyed by nodeid and written to $CALLTIME_FILE (default `calltime.json`).
A test with a call-phase report gets the call duration. A test whose setup
skipped or failed gets a row with `duration: null` (it never reached the call
phase). A failed teardown turns the row's outcome to `failed`, keeping the call
duration.
"""
import json
import os

_rows: dict[str, dict] = {}


def pytest_runtest_logreport(report):
    if report.when == "call":
        _rows[report.nodeid] = {"duration": report.duration, "outcome": report.outcome}
    elif report.outcome != "passed":
        prev = _rows.get(report.nodeid, {})
        _rows[report.nodeid] = {
            "duration": prev.get("duration"),
            "outcome": report.outcome,
        }


def pytest_sessionfinish(session):
    # Under xdist the controller replays worker reports; only it writes the file.
    if hasattr(session.config, "workerinput"):
        return
    with open(os.environ.get("CALLTIME_FILE", "calltime.json"), "w") as f:
        json.dump(_rows, f, indent=1, sort_keys=True)
