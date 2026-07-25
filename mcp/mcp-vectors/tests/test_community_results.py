"""Tests for vectors/community_results.py — Ticket 01 acceptance suite."""
from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from vectors.community_results import (
    CommunitiesReady,
    CommunitiesRebuilding,
    CommunitiesError,
    CommunitiesQueryResult,
    CommunityReportReady,
    CommunityReportRebuilding,
    CommunityReportError,
    CommunityReportResult,
)


# ---------------------------------------------------------------------------
# CommunitiesReady
# ---------------------------------------------------------------------------

class TestCommunitiesReady:
    def test_to_dict_wire_shape(self):
        items = [{"id": "c1"}, {"id": "c2"}]
        result = CommunitiesReady(communities=items).to_dict()
        assert result == {"mode": "ready", "communities": items}

    def test_mode_field_present(self):
        assert CommunitiesReady(communities=[]).to_dict()["mode"] == "ready"

    def test_no_success_key(self):
        assert "success" not in CommunitiesReady(communities=[]).to_dict()

    def test_frozen(self):
        obj = CommunitiesReady(communities=[])
        with pytest.raises(FrozenInstanceError):
            obj.communities = []  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CommunitiesRebuilding
# ---------------------------------------------------------------------------

class TestCommunitiesRebuilding:
    def test_to_dict_wire_shape(self):
        result = CommunitiesRebuilding(reason="graph dirty").to_dict()
        assert result == {"mode": "rebuilding", "warning": "graph dirty"}

    def test_mode_field_present(self):
        assert CommunitiesRebuilding(reason="x").to_dict()["mode"] == "rebuilding"

    def test_no_success_key(self):
        assert "success" not in CommunitiesRebuilding(reason="x").to_dict()

    def test_frozen(self):
        obj = CommunitiesRebuilding(reason="x")
        with pytest.raises(FrozenInstanceError):
            obj.reason = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CommunitiesError
# ---------------------------------------------------------------------------

class TestCommunitiesError:
    def test_to_dict_wire_shape(self):
        err = {"code": "NOT_FOUND", "message": "root not indexed"}
        result = CommunitiesError(error=err).to_dict()
        assert result == {"mode": "error", "error": err}

    def test_mode_field_present(self):
        assert CommunitiesError(error={}).to_dict()["mode"] == "error"

    def test_no_success_key(self):
        assert "success" not in CommunitiesError(error={}).to_dict()

    def test_frozen(self):
        obj = CommunitiesError(error={})
        with pytest.raises(FrozenInstanceError):
            obj.error = {}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CommunityReportReady
# ---------------------------------------------------------------------------

class TestCommunityReportReady:
    def test_to_dict_wire_shape(self):
        report = {"community_id": "c1", "title": "Auth"}
        result = CommunityReportReady(report=report).to_dict()
        assert result == {"mode": "ready", "community": report}

    def test_mode_field_present(self):
        assert CommunityReportReady(report={}).to_dict()["mode"] == "ready"

    def test_no_success_key(self):
        assert "success" not in CommunityReportReady(report={}).to_dict()

    def test_frozen(self):
        obj = CommunityReportReady(report={})
        with pytest.raises(FrozenInstanceError):
            obj.report = {}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CommunityReportRebuilding
# ---------------------------------------------------------------------------

class TestCommunityReportRebuilding:
    def test_to_dict_wire_shape(self):
        result = CommunityReportRebuilding(reason="stale communities").to_dict()
        assert result == {"mode": "rebuilding", "warning": "stale communities"}

    def test_mode_field_present(self):
        assert CommunityReportRebuilding(reason="x").to_dict()["mode"] == "rebuilding"

    def test_no_success_key(self):
        assert "success" not in CommunityReportRebuilding(reason="x").to_dict()

    def test_frozen(self):
        obj = CommunityReportRebuilding(reason="x")
        with pytest.raises(FrozenInstanceError):
            obj.reason = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CommunityReportError
# ---------------------------------------------------------------------------

class TestCommunityReportError:
    def test_to_dict_wire_shape(self):
        err = {"code": "UNKNOWN_ID", "message": "community not found"}
        result = CommunityReportError(error=err).to_dict()
        assert result == {"mode": "error", "error": err}

    def test_mode_field_present(self):
        assert CommunityReportError(error={}).to_dict()["mode"] == "error"

    def test_no_success_key(self):
        assert "success" not in CommunityReportError(error={}).to_dict()

    def test_frozen(self):
        obj = CommunityReportError(error={})
        with pytest.raises(FrozenInstanceError):
            obj.error = {}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Type alias sanity checks (runtime: just confirm names are importable)
# ---------------------------------------------------------------------------

class TestTypeAliases:
    def test_communities_query_result_alias_exists(self):
        # Union alias is just a type expression at runtime; confirm it's importable
        assert CommunitiesQueryResult is not None

    def test_community_report_result_alias_exists(self):
        assert CommunityReportResult is not None


# ---------------------------------------------------------------------------
# Cross-variant: mode present and no success key in all outputs
# ---------------------------------------------------------------------------

ALL_INSTANCES = [
    CommunitiesReady(communities=[]),
    CommunitiesRebuilding(reason="r"),
    CommunitiesError(error={"code": "E", "message": "m"}),
    CommunityReportReady(report={}),
    CommunityReportRebuilding(reason="r"),
    CommunityReportError(error={"code": "E", "message": "m"}),
]


@pytest.mark.parametrize("obj", ALL_INSTANCES)
def test_all_variants_have_mode(obj):
    d = obj.to_dict()
    assert "mode" in d, f"{type(obj).__name__}.to_dict() missing 'mode'"


@pytest.mark.parametrize("obj", ALL_INSTANCES)
def test_no_variant_has_success_key(obj):
    d = obj.to_dict()
    assert "success" not in d, f"{type(obj).__name__}.to_dict() must not contain 'success'"
