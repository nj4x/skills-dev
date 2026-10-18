"""pytest plugin: cProfile one test's run protocol (setup, call, teardown) for the hotspot probe.

Load with `pytest -p hotspot_profile` (this directory must be on PYTHONPATH) and select one
test id per run. The profile covers `pytest_runtest_protocol` only, so collection and
session start-up stay out of it, and is written to $HOTSPOT_PROFILE (default
`.scratch/refactor-tests/hotspot.prof` under the working directory) with
`cProfile.Profile.dump_stats`. `hotspot_probe.py analyze` reads it.
"""
import cProfile
import os

import pytest

DEFAULT = os.path.join(".scratch", "refactor-tests", "hotspot.prof")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    profile = cProfile.Profile()
    profile.enable()
    try:
        yield
    finally:
        profile.disable()
        path = os.environ.get("HOTSPOT_PROFILE", DEFAULT)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        profile.dump_stats(path)
