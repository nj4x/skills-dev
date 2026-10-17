"""Shared test-id parsing and JSON output for the refactor-tests helpers.

Test ids are pytest node ids (`<file>::<test>`, `<file>::<Class>::<test>`), optionally
with a parameter suffix (`<id>[<params>]`). The suffix starts at the first `[`, so a
parameter holding `::`, `.` or `[` never splits the id.
"""
import json
import os


def strip_params(test_id):
    """(base, suffix): `test_id` without its `[params]` suffix, and that suffix ('' if none)."""
    base, bracket, params = test_id.partition("[")
    return base, bracket + params


def split_file(test_id):
    """(file, rest): the file path before the first `::`, and the remainder (params kept)."""
    file, _, rest = test_id.partition("::")
    return file, rest


def is_variant(test_id, base_id):
    """True when `test_id` is `base_id` or a parametrized id of it (`<base_id>[...]`).

    A bare `<file>::<test>` names a top-level test only, never `<file>::<Class>::<test>`.
    """
    return test_id == base_id or test_id.startswith(base_id + "[")


def write_atomic(path, doc):
    """Write `doc` to `path` as JSON (indent 1, sorted keys): temp file, then rename."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)
