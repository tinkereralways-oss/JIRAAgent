"""Tests for models.py — Data classes."""

from models import JiraIssue, SprintInfo, ReleaseNotes
from tests.conftest import make_issue, make_sprint


class TestJiraIssue:
    def test_all_fields_populated(self):
        issue = make_issue()
        assert issue.key == "PROJ-1"
        assert issue.summary == "Test issue summary"
        assert issue.issue_type == "Story"
        assert issue.status == "Done"
        assert issue.assignee == "Alice Smith"
        assert issue.priority == "Medium"
        assert issue.labels == []
        assert issue.resolution == "Done"

    def test_defaults_for_optional_fields(self):
        issue = JiraIssue(key="X-1", summary="s", issue_type="Bug", status="Done")
        assert issue.assignee is None
        assert issue.priority is None
        assert issue.labels == []
        assert issue.resolution is None
        assert issue.created is None
        assert issue.resolved is None

    def test_labels_mutable_default_isolation(self):
        a = JiraIssue(key="A-1", summary="a", issue_type="Task", status="Done")
        b = JiraIssue(key="B-1", summary="b", issue_type="Task", status="Done")
        a.labels.append("urgent")
        assert b.labels == []

    def test_issues_by_type_mutable_default_isolation(self):
        a = ReleaseNotes(sprint=make_sprint())
        b = ReleaseNotes(sprint=make_sprint())
        a.issues_by_type["Story"] = [make_issue()]
        assert b.issues_by_type == {}


class TestSprintInfo:
    def test_optional_dates_none(self):
        s = SprintInfo(id=1, name="Sprint 1", state="future")
        assert s.start_date is None
        assert s.end_date is None
        assert s.complete_date is None

    def test_all_fields(self):
        s = make_sprint()
        assert s.id == 100
        assert s.name == "Sprint 42"
        assert s.state == "closed"


class TestReleaseNotes:
    def test_defaults(self):
        rn = ReleaseNotes(sprint=make_sprint())
        assert rn.issues_by_type == {}
        assert rn.total_count == 0
        assert rn.summary == ""
