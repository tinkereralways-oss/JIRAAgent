"""Integration tests — end-to-end pipeline verification."""

from html_generator import generate_html
from summarizer import _fallback_summary
from models import ReleaseNotes
from tests.conftest import make_issue, make_sprint


class TestJiraToHTMLPipeline:
    def test_full_pipeline_with_fallback_summary(self):
        """Simulate: Jira data -> fallback summary -> HTML output."""
        issues_by_type = {
            "Story": [
                make_issue(key="PROJ-1", summary="Add user dashboard"),
                make_issue(key="PROJ-2", summary="Implement search"),
            ],
            "Bug": [
                make_issue(key="PROJ-3", issue_type="Bug", summary="Fix login crash",
                           priority="High"),
            ],
            "Task": [
                make_issue(key="PROJ-4", issue_type="Task", summary="Update CI config",
                           assignee=None),
            ],
        }

        summary = _fallback_summary(issues_by_type, "Sprint 42")
        rn = ReleaseNotes(
            sprint=make_sprint(),
            issues_by_type=issues_by_type,
            total_count=4,
            summary=summary,
        )

        html = generate_html(rn)

        # Verify structure
        assert "<!DOCTYPE html>" in html
        assert "Sprint 42" in html
        assert "4 issues completed" in html

        # Verify all issue keys present
        for key in ["PROJ-1", "PROJ-2", "PROJ-3", "PROJ-4"]:
            assert key in html

        # Verify grouping (Bug before Story before Task alphabetically)
        bug_pos = html.index("Bug")
        story_pos = html.index("Story")
        task_pos = html.index("Task")
        assert bug_pos < story_pos < task_pos

        # Verify summary is present and escaped
        assert "Executive Summary" in html
        assert "Sprint 42 completed 4 issues" in html

        # Verify unassigned display
        assert "Unassigned" in html

    def test_empty_sprint_pipeline(self):
        """Empty sprint should produce valid HTML with no-issues message."""
        summary = _fallback_summary({}, "Sprint 99")
        rn = ReleaseNotes(
            sprint=make_sprint(name="Sprint 99"),
            issues_by_type={},
            total_count=0,
            summary=summary,
        )

        html = generate_html(rn)
        assert "No completed issues in this sprint." in html
        assert "0 issues completed" in html
        assert "Sprint 99" in html

    def test_large_sprint(self):
        """500 issues should render without error."""
        issues = [
            make_issue(key=f"PROJ-{i}", summary=f"Issue number {i}")
            for i in range(500)
        ]
        rn = ReleaseNotes(
            sprint=make_sprint(),
            issues_by_type={"Story": issues},
            total_count=500,
            summary="A very productive sprint.",
        )

        html = generate_html(rn)
        assert "500 issues completed" in html
        assert "PROJ-0" in html
        assert "PROJ-499" in html

    def test_special_characters_throughout(self):
        """Unicode, HTML entities, and special chars should all render safely."""
        issues_by_type = {
            "Story": [
                make_issue(key="PROJ-1", summary='Fix "quotes" & <tags>',
                           assignee="Ñoño O'Brien"),
            ],
        }
        rn = ReleaseNotes(
            sprint=make_sprint(name='Sprint <42> & "friends"'),
            issues_by_type=issues_by_type,
            total_count=1,
            summary='Summary with <html> & "quotes"',
        )

        html = generate_html(rn)
        # No raw HTML injection
        assert "<42>" not in html
        assert "&lt;42&gt;" in html
        assert "&amp;" in html
        # Original content preserved (escaped)
        assert "PROJ-1" in html
