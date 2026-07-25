from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CommunitiesReady:
    communities: list

    def to_dict(self) -> dict:
        return {"mode": "ready", "communities": self.communities}


@dataclass(frozen=True)
class CommunitiesRebuilding:
    reason: str

    def to_dict(self) -> dict:
        return {"mode": "rebuilding", "warning": self.reason}


@dataclass(frozen=True)
class CommunitiesError:
    error: dict  # {"code": str, "message": str}

    def to_dict(self) -> dict:
        return {"mode": "error", "error": self.error}


CommunitiesQueryResult = CommunitiesReady | CommunitiesRebuilding | CommunitiesError


@dataclass(frozen=True)
class CommunityReportReady:
    report: dict

    def to_dict(self) -> dict:
        return {"mode": "ready", "community": self.report}


@dataclass(frozen=True)
class CommunityReportRebuilding:
    reason: str

    def to_dict(self) -> dict:
        return {"mode": "rebuilding", "warning": self.reason}


@dataclass(frozen=True)
class CommunityReportError:
    error: dict  # {"code": str, "message": str}

    def to_dict(self) -> dict:
        return {"mode": "error", "error": self.error}


CommunityReportResult = CommunityReportReady | CommunityReportRebuilding | CommunityReportError
