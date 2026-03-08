"""Tests for html_generator.py — HTML report generation."""

from unittest.mock import patch
from datetime import datetime

import pytest

from html_generator import generate_html, _format_date_range
from models import ReleaseNotes
from tests.conftest import make_issue, make_sprint, make_release_notes


class TestFormatDateRange:
    def test_valid_dates(self):
        result = _format_date_range(
            "2026-03-04T00:00:00.000+00:00",
            "2026-03-17T23:59:59.000+00:00"
        )
        assert "Wed, Mar 04" in result
        assert "Tue, Mar 17, 2026" in result
        assert "→" in result

    def test_z_suffix(self):
        result = _format_date_range(
            "2026-03-04T00:00:00Z",
            "2026-03-17T23:59:59Z"
        )
        assert "Wed, Mar 04" in result

    def test_none_start(self):
        assert _format_date_range(None, "2026-03-17T00:00:00Z") == ""

    def test_none_end(self):
        assert _format_date_range("2026-03-04T00:00:00Z", None) == ""

    def test_both_none(self):
        assert _format_date_range(None, None) == ""

    def test_invalid_format(self):
        assert _format_date_range("not-a-date", "also-not") == ""


class TestXSSEscaping:
    """P0 — Verify every user-controlled interpolation point is escaped."""

    def test_xss_in_issue_summary(self):
        rn = make_release_notes(issues_by_type={
            "Story": [make_issue(summary="<script>alert('xss')</script>")]
        })
        html = generate_html(rn)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_xss_in_sprint_name(self):
        rn = make_release_notes()
        rn.sprint.name = '"><img src=x onerror=alert(1)>'
        html = generate_html(rn)
        # The raw tag must be escaped — no unescaped angle brackets around the payload
        assert "<img src=x" not in html
        assert "&lt;img" in html
        assert "&quot;&gt;" in html

    def test_xss_in_assignee(self):
        rn = make_release_notes(issues_by_type={
            "Story": [make_issue(assignee="<b>attacker</b>")]
        })
        html = generate_html(rn)
        assert "<b>attacker</b>" not in html
        assert "&lt;b&gt;" in html

    def test_xss_in_issue_key(self):
        """Bug #3: Issue key must be escaped."""
        rn = make_release_notes(issues_by_type={
            "Story": [make_issue(key="<img src=x>")]
        })
        html = generate_html(rn)
        assert "<img src=x>" not in html
        assert "&lt;img" in html

    def test_xss_in_summary_text(self):
        rn = make_release_notes(summary="<script>steal()</script>")
        html = generate_html(rn)
        assert "<script>steal()</script>" not in html
        assert "&lt;script&gt;" in html

    def test_xss_in_issue_type(self):
        rn = make_release_notes(issues_by_type={
            "<img>": [make_issue(issue_type="<img>")]
        })
        html = generate_html(rn)
        # Check the type badge is escaped
        assert "&lt;img&gt;" in html

    def test_xss_in_priority(self):
        rn = make_release_notes(issues_by_type={
            "Story": [make_issue(priority="<b>High</b>")]
        })
        html = generate_html(rn)
        assert "<b>High</b>" not in html


class TestHTMLStructure:
    def test_valid_html5_doctype(self, sample_release_notes):
        html = generate_html(sample_release_notes)
        assert html.startswith("<!DOCTYPE html>")

    def test_contains_charset(self, sample_release_notes):
        html = generate_html(sample_release_notes)
        assert 'charset="UTF-8"' in html

    def test_inline_css(self, sample_release_notes):
        html = generate_html(sample_release_notes)
        assert "<style>" in html

    def test_no_external_dependencies(self, sample_release_notes):
        html = generate_html(sample_release_notes)
        assert "<link" not in html
        assert "<script" not in html  # no JS

    def test_footer_timestamp(self, sample_release_notes):
        html = generate_html(sample_release_notes)
        assert "Generated on" in html


class TestEmptySprint:
    def test_no_issues_message(self, empty_release_notes):
        html = generate_html(empty_release_notes)
        assert "No completed issues in this sprint." in html

    def test_no_table_when_empty(self, empty_release_notes):
        html = generate_html(empty_release_notes)
        assert "<table>" not in html

    def test_no_summary_section_when_empty(self, empty_release_notes):
        html = generate_html(empty_release_notes)
        assert "Executive Summary" not in html

    def test_zero_count_displayed(self, empty_release_notes):
        html = generate_html(empty_release_notes)
        assert "0 issues completed" in html


class TestIssueRendering:
    def test_issues_sorted_by_key(self):
        rn = make_release_notes(issues_by_type={
            "Story": [
                make_issue(key="PROJ-3"),
                make_issue(key="PROJ-1"),
                make_issue(key="PROJ-2"),
            ]
        }, total_count=3)
        html = generate_html(rn)
        pos1 = html.index("PROJ-1")
        pos2 = html.index("PROJ-2")
        pos3 = html.index("PROJ-3")
        assert pos1 < pos2 < pos3

    def test_types_sorted_alphabetically(self):
        rn = make_release_notes(issues_by_type={
            "Task": [make_issue(key="P-3", issue_type="Task")],
            "Bug": [make_issue(key="P-1", issue_type="Bug")],
            "Story": [make_issue(key="P-2", issue_type="Story")],
        }, total_count=3)
        html = generate_html(rn)
        pos_bug = html.index("Bug")
        pos_story = html.index("Story")
        pos_task = html.index("Task")
        assert pos_bug < pos_story < pos_task

    def test_singular_issue_count(self):
        rn = make_release_notes(issues_by_type={
            "Story": [make_issue()],
        }, total_count=1)
        html = generate_html(rn)
        assert "(1 issue)" in html

    def test_plural_issue_count(self):
        rn = make_release_notes(issues_by_type={
            "Story": [make_issue(key="P-1"), make_issue(key="P-2"), make_issue(key="P-3")],
        }, total_count=3)
        html = generate_html(rn)
        assert "(3 issues)" in html

    def test_unassigned_display(self):
        rn = make_release_notes(issues_by_type={
            "Story": [make_issue(assignee=None)],
        }, total_count=1)
        html = generate_html(rn)
        assert "Unassigned" in html

    def test_null_priority_display(self):
        rn = make_release_notes(issues_by_type={
            "Story": [make_issue(priority=None)],
        }, total_count=1)
        html = generate_html(rn)
        assert "None" in html

    def test_stat_badges_present(self, sample_release_notes):
        html = generate_html(sample_release_notes)
        assert "stat-badge" in html
        assert "Story:" in html
        assert "Bug:" in html

    def test_unknown_type_gets_default_color(self):
        rn = make_release_notes(issues_by_type={
            "CustomType": [make_issue(issue_type="CustomType")],
        }, total_count=1)
        html = generate_html(rn)
        assert "#6c757d" in html  # DEFAULT_TYPE_COLOR

    def test_unicode_content(self):
        rn = make_release_notes(issues_by_type={
            "Story": [make_issue(summary="修复登录问题 🚀")],
        }, total_count=1)
        html = generate_html(rn)
        assert "修复登录问题" in html

    def test_special_characters_in_summary_text(self):
        rn = make_release_notes(summary='Quotes "here" & ampersands <everywhere>')
        html = generate_html(rn)
        assert "&amp;" in html
        assert "&lt;everywhere&gt;" in html
