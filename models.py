"""Data classes for Jira sprint release notes."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class JiraIssue:
    key: str
    summary: str
    issue_type: str
    status: str
    assignee: Optional[str] = None
    priority: Optional[str] = None
    labels: list[str] = field(default_factory=list)
    resolution: Optional[str] = None
    created: Optional[str] = None
    resolved: Optional[str] = None


@dataclass
class SprintInfo:
    id: int
    name: str
    state: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    complete_date: Optional[str] = None


@dataclass
class ReleaseNotes:
    sprint: SprintInfo
    issues_by_type: dict[str, list[JiraIssue]] = field(default_factory=dict)
    total_count: int = 0
    summary: str = ""
