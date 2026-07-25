"""
Tests for vectors.community_reporter.

Verifies that:
- Graph-authoritative facts (entity_names, file_paths, edge_count) are always
  sourced from the GraphSnapshot, never from the LLM.
- LLM failures yield empty prose strings without raising exceptions.
- Concurrency is bounded in generate_all_reports.
- Report provenance fields are preserved exactly from the input community.
- Output order matches input order from generate_all_reports.
"""

from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_community(
    community_id: str = "c1",
    level: int = 0,
    parent_id=None,
    entity_ids=("e1", "e2"),
    file_ids=("file_a.py", "file_b.py"),
):
    """Build a minimal CommunityCandidate-like namespace."""
    c = types.SimpleNamespace()
    c.community_id = community_id
    c.level = level
    c.parent_id = parent_id
    c.entity_ids = list(entity_ids)
    c.file_ids = list(file_ids)
    return c


def _make_snapshot(entities=None, edges=None):
    """Build a minimal GraphSnapshot-like namespace."""
    s = types.SimpleNamespace()
    s.root_id = "root"
    s.graph_version = 1
    s.entities = tuple(entities or [])
    s.edges = tuple(edges or [])
    return s


def _make_lm_client(response_json: str = '{"title":"T","summary":"S","findings":["F"]}',
                    model_name: str = "test-model"):
    """Build a mock LMStudioClient."""
    client = MagicMock()
    client._llm_model = model_name
    client.generate_response_with_history = AsyncMock(return_value=response_json)
    return client


# ---------------------------------------------------------------------------
# Test 1: graph facts are extracted correctly
# ---------------------------------------------------------------------------

def test_generate_report_extracts_graph_facts():
    """entity_names, file_paths, edge_count come from the snapshot, not the LLM."""
    from vectors.community_reporter import generate_report

    community = _make_community(
        entity_ids=["e1", "e2"],
        file_ids=["file_b.py", "file_a.py"],
    )
    snapshot = _make_snapshot(
        entities=[
            {"id": "e1", "name": "Alpha"},
            {"id": "e2", "name": "Beta"},
            {"id": "e3", "name": "Gamma"},  # not in community
        ],
        edges=[
            {"source_id": "e1", "target_id": "e2"},
            {"source_id": "e1", "target_id": "e3"},  # e3 outside community
        ],
    )
    client = _make_lm_client()

    report = asyncio.run(generate_report(community, snapshot, client))

    assert sorted(report["entity_names"]) == ["Alpha", "Beta"]
    assert report["file_paths"] == ["file_a.py", "file_b.py"]  # sorted
    assert report["edge_count"] == 1  # only e1->e2 is fully inside


# ---------------------------------------------------------------------------
# Test 2: LLM parse failure yields empty prose without raising
# ---------------------------------------------------------------------------

def test_llm_parse_failure_yields_empty_prose():
    """When LLM returns invalid JSON, title/summary/findings are empty."""
    from vectors.community_reporter import generate_report

    community = _make_community()
    snapshot = _make_snapshot(
        entities=[{"id": "e1", "name": "Alpha"}, {"id": "e2", "name": "Beta"}],
        edges=[],
    )
    client = _make_lm_client(response_json="NOT VALID JSON")

    # Must not raise
    report = asyncio.run(generate_report(community, snapshot, client))

    assert report["title"] == ""
    assert report["summary"] == ""
    assert report["findings"] == []


# ---------------------------------------------------------------------------
# Test 3: graph facts never come from LLM
# ---------------------------------------------------------------------------

def test_graph_facts_never_from_llm():
    """entity_names, file_paths, edge_count must come from snapshot only."""
    from vectors.community_reporter import generate_report

    community = _make_community(
        entity_ids=["e1"],
        file_ids=["real_file.py"],
    )
    snapshot = _make_snapshot(
        entities=[{"id": "e1", "name": "RealName"}],
        edges=[],
    )
    # LLM response pretends to inject entity/file data into prose fields
    llm_json = (
        '{"title":"LLMTitle","summary":"LLMSummary",'
        '"findings":["LLM finding"],"entity_names":["Fake"],'
        '"file_paths":["fake.py"],"edge_count":99}'
    )
    client = _make_lm_client(response_json=llm_json)

    report = asyncio.run(generate_report(community, snapshot, client))

    # Graph-authoritative fields must reflect snapshot, not LLM output
    assert report["entity_names"] == ["RealName"]
    assert report["file_paths"] == ["real_file.py"]
    assert report["edge_count"] == 0


# ---------------------------------------------------------------------------
# Test 4: generated_by and generated_at are populated
# ---------------------------------------------------------------------------

def test_generated_by_and_timestamp_populated():
    """Report must have generated_by (model name) and generated_at (ISO 8601)."""
    from vectors.community_reporter import generate_report

    community = _make_community()
    snapshot = _make_snapshot(
        entities=[{"id": "e1", "name": "Alpha"}, {"id": "e2", "name": "Beta"}],
        edges=[],
    )
    client = _make_lm_client(model_name="my-llm-v1")

    report = asyncio.run(generate_report(community, snapshot, client))

    assert report["generated_by"] == "my-llm-v1"
    assert isinstance(report["generated_at"], str)
    assert report["generated_at"].endswith("Z")
    # Quick ISO 8601 shape check: YYYY-MM-DDTHH:MM:SS...Z
    assert "T" in report["generated_at"]
    assert len(report["generated_at"]) >= 20


# ---------------------------------------------------------------------------
# Test 5: generate_all_reports bounded concurrency
# ---------------------------------------------------------------------------

def test_generate_all_reports_concurrent_limit():
    """Max concurrent LLM calls must not exceed concurrency=2 when 5 communities given."""
    from vectors.community_reporter import generate_all_reports

    # We track the peak concurrent "in-flight" count.
    peak = {"value": 0}
    active = {"value": 0}

    async def fake_generate_response_with_history(messages, max_tokens=400):
        active["value"] += 1
        if active["value"] > peak["value"]:
            peak["value"] = active["value"]
        await asyncio.sleep(0)  # yield to let other coroutines start
        active["value"] -= 1
        return '{"title":"T","summary":"S","findings":["F"]}'

    client = MagicMock()
    client._llm_model = "model"
    client.generate_response_with_history = fake_generate_response_with_history

    communities = [
        _make_community(community_id=f"c{i}", entity_ids=[f"e{i}a", f"e{i}b"], file_ids=[])
        for i in range(5)
    ]
    snapshot = _make_snapshot(
        entities=[
            entity
            for i in range(5)
            for entity in [
                {"id": f"e{i}a", "name": f"EntityA{i}"},
                {"id": f"e{i}b", "name": f"EntityB{i}"},
            ]
        ],
        edges=[],
    )

    asyncio.run(generate_all_reports(communities, snapshot, client, concurrency=2))

    assert peak["value"] <= 2, f"Peak concurrency was {peak['value']}, expected <= 2"


# ---------------------------------------------------------------------------
# Test 6: empty community edge_count is zero
# ---------------------------------------------------------------------------

def test_empty_community_edge_count_zero():
    """A community with no edges between its entities reports edge_count=0."""
    from vectors.community_reporter import generate_report

    community = _make_community(entity_ids=["e1"], file_ids=[])
    snapshot = _make_snapshot(
        entities=[{"id": "e1", "name": "Lone"}],
        edges=[],
    )
    client = _make_lm_client()

    report = asyncio.run(generate_report(community, snapshot, client))

    assert report["edge_count"] == 0


# ---------------------------------------------------------------------------
# Test 7: title/summary/key_findings truncated to limits
# ---------------------------------------------------------------------------

def test_title_summary_truncated_to_limits():
    """LLM output exceeding field limits must be truncated."""
    from vectors.community_reporter import generate_report
    import json

    long_title = "A" * 300
    long_summary = "B" * 600
    long_findings = ["C" * 300, "D" * 300, "E" * 300]

    llm_json = json.dumps({
        "title": long_title,
        "summary": long_summary,
        "findings": long_findings,
    })

    community = _make_community()
    snapshot = _make_snapshot(
        entities=[{"id": "e1", "name": "Alpha"}, {"id": "e2", "name": "Beta"}],
        edges=[],
    )
    client = _make_lm_client(response_json=llm_json)

    report = asyncio.run(generate_report(community, snapshot, client))

    assert len(report["title"]) <= 200
    assert len(report["summary"]) <= 500
    assert isinstance(report["findings"], list)
    assert len(report["findings"]) <= 5
    assert all(len(f) <= 200 for f in report["findings"])


# ---------------------------------------------------------------------------
# Test 8: community provenance fields are preserved exactly
# ---------------------------------------------------------------------------

def test_report_preserves_community_provenance():
    """community_id, level, parent_id, entity_ids, file_ids must match input exactly."""
    from vectors.community_reporter import generate_report

    community = _make_community(
        community_id="comm-xyz",
        level=2,
        parent_id="parent-abc",
        entity_ids=["e10", "e20"],
        file_ids=["foo.py", "bar.py"],
    )
    snapshot = _make_snapshot(
        entities=[
            {"id": "e10", "name": "EntityTen"},
            {"id": "e20", "name": "EntityTwenty"},
        ],
        edges=[],
    )
    client = _make_lm_client()

    report = asyncio.run(generate_report(community, snapshot, client))

    assert report["community_id"] == "comm-xyz"
    assert report["level"] == 2
    assert report["parent_id"] == "parent-abc"
    assert sorted(report["entity_ids"]) == ["e10", "e20"]
    assert sorted(report["file_ids"]) == ["bar.py", "foo.py"]
    # entity_ids and file_ids must be lists, not sets or tuples
    assert isinstance(report["entity_ids"], list)
    assert isinstance(report["file_ids"], list)


# ---------------------------------------------------------------------------
# Test 9: generate_all_reports preserves input order
# ---------------------------------------------------------------------------

def test_generate_all_reports_order_preserved():
    """Output report order must match input community order."""
    from vectors.community_reporter import generate_all_reports

    ids = [f"c{i}" for i in range(6)]
    communities = [
        _make_community(community_id=cid, entity_ids=[f"e{i}"], file_ids=[])
        for i, cid in enumerate(ids)
    ]
    snapshot = _make_snapshot(
        entities=[{"id": f"e{i}", "name": f"Entity{i}"} for i in range(6)],
        edges=[],
    )
    client = _make_lm_client()

    reports = asyncio.run(generate_all_reports(communities, snapshot, client, concurrency=3))

    assert len(reports) == len(ids)
    for report, expected_id in zip(reports, ids):
        assert report["community_id"] == expected_id


# ---------------------------------------------------------------------------
# Test 10: single-entity communities skip LLM
# ---------------------------------------------------------------------------

def test_single_entity_community_skips_llm():
    """Communities with fewer than 2 entities must not call the LLM."""
    from vectors.community_reporter import generate_report

    community = _make_community(entity_ids=["e1"], file_ids=["file_a.py"])
    snapshot = _make_snapshot(
        entities=[{"id": "e1", "name": "Lone"}],
        edges=[],
    )
    client = _make_lm_client()

    report = asyncio.run(generate_report(community, snapshot, client))

    # LLM must not be called
    client.generate_response_with_history.assert_not_called()
    # Prose fields are empty
    assert report["title"] == ""
    assert report["summary"] == ""
    assert report["findings"] == []
    # But graph-authoritative fields are still populated
    assert report["entity_names"] == ["Lone"]


# ---------------------------------------------------------------------------
# Test 11: markdown-fenced JSON is parsed correctly
# ---------------------------------------------------------------------------

def test_markdown_fenced_json_is_parsed():
    """LLM responses wrapped in ```json fences must parse correctly."""
    from vectors.community_reporter import generate_report

    fenced = '```json\n{"title":"T","summary":"S","findings":["F"]}\n```'
    community = _make_community()
    snapshot = _make_snapshot(
        entities=[{"id": "e1", "name": "Alpha"}, {"id": "e2", "name": "Beta"}],
        edges=[],
    )
    client = _make_lm_client(response_json=fenced)

    report = asyncio.run(generate_report(community, snapshot, client))

    assert report["title"] == "T"
    assert report["summary"] == "S"
    assert report["findings"] == ["F"]
