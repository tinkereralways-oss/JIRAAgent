"""Shared test fixtures and factory functions."""

import sys
from pathlib import Path

import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import JiraIssue, SprintInfo, ReleaseNotes


def make_issue(**overrides) -> JiraIssue:
    """Create a JiraIssue with sensible defaults."""
    defaults = {
        "key": "PROJ-1",
        "summary": "Test issue summary",
        "issue_type": "Story",
        "status": "Done",
        "assignee": "Alice Smith",
        "priority": "Medium",
        "labels": [],
        "resolution": "Done",
        "created": "2026-03-01T10:00:00.000+0000",
        "resolved": "2026-03-10T15:00:00.000+0000",
    }
    defaults.update(overrides)
    return JiraIssue(**defaults)


def make_sprint(**overrides) -> SprintInfo:
    """Create a SprintInfo with sensible defaults."""
    defaults = {
        "id": 100,
        "name": "Sprint 42",
        "state": "closed",
        "start_date": "2026-03-04T00:00:00.000Z",
        "end_date": "2026-03-17T23:59:59.000Z",
        "complete_date": "2026-03-18T01:00:00.000Z",
    }
    defaults.update(overrides)
    return SprintInfo(**defaults)


def make_release_notes(**overrides) -> ReleaseNotes:
    """Create a ReleaseNotes with sensible defaults."""
    defaults = {
        "sprint": make_sprint(),
        "issues_by_type": {
            "Story": [make_issue(key="PROJ-1"), make_issue(key="PROJ-2", summary="Another story")],
            "Bug": [make_issue(key="PROJ-3", issue_type="Bug", summary="Fix login crash")],
        },
        "total_count": 3,
        "summary": "This sprint focused on improving login reliability and adding new features.",
    }
    defaults.update(overrides)
    return ReleaseNotes(**defaults)


@pytest.fixture
def sample_issue():
    return make_issue()


@pytest.fixture
def sample_sprint():
    return make_sprint()


@pytest.fixture
def sample_release_notes():
    return make_release_notes()


@pytest.fixture
def empty_release_notes():
    return ReleaseNotes(sprint=make_sprint(), issues_by_type={}, total_count=0, summary="")
