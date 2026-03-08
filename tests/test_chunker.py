"""Tests for chunker.py — text chunking for context management."""

import pytest

from chunker import (
    estimate_tokens,
    issue_to_text,
    issues_to_text,
    chunk_issues,
    needs_chunking,
    build_chunk_summary_prompt,
    build_reduce_prompt,
)
from tests.conftest import make_issue


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 1  # minimum 1

    def test_short_string(self):
        tokens = estimate_tokens("Hello world")
        assert tokens >= 1
        assert tokens <= 10

    def test_longer_string(self):
        text = "a" * 400
        assert estimate_tokens(text) == 100


class TestIssueToText:
    def test_basic_issue(self):
        issue = make_issue(key="PROJ-1", summary="Fix login", assignee="Alice")
        text = issue_to_text(issue)
        assert "PROJ-1" in text
        assert "Fix login" in text
        assert "Alice" in text

    def test_unassigned(self):
        issue = make_issue(assignee=None)
        text = issue_to_text(issue)
        assert "Unassigned" in text

    def test_priority_included(self):
        issue = make_issue(priority="High")
        text = issue_to_text(issue)
        assert "High" in text

    def test_labels_included(self):
        issue = make_issue(labels=["frontend", "urgent"])
        text = issue_to_text(issue)
        assert "frontend" in text
        assert "urgent" in text


class TestIssuesToText:
    def test_grouped_by_type(self):
        issues = {
            "Bug": [make_issue(key="P-1", issue_type="Bug")],
            "Story": [make_issue(key="P-2", issue_type="Story")],
        }
        text = issues_to_text(issues)
        assert "Bugs" in text  # pluralized
        assert "Stories" in text
        assert "P-1" in text
        assert "P-2" in text

    def test_sorted_alphabetically(self):
        issues = {
            "Task": [make_issue(issue_type="Task")],
            "Bug": [make_issue(issue_type="Bug")],
        }
        text = issues_to_text(issues)
        bug_pos = text.index("Bug")
        task_pos = text.index("Task")
        assert bug_pos < task_pos


class TestChunkIssues:
    def test_small_set_single_chunk(self):
        issues = {"Story": [make_issue(key=f"P-{i}") for i in range(3)]}
        chunks = chunk_issues(issues, token_limit=5000)
        assert len(chunks) == 1
        assert "Story" in chunks[0]
        assert len(chunks[0]["Story"]) == 3

    def test_large_set_multiple_chunks(self):
        # Create enough issues to exceed a tiny token limit
        issues = {
            "Story": [
                make_issue(key=f"P-{i}", summary=f"A detailed story about feature {i} " * 5)
                for i in range(50)
            ]
        }
        chunks = chunk_issues(issues, token_limit=500)
        assert len(chunks) > 1
        # All issues should be present across chunks
        total = sum(len(c.get("Story", [])) for c in chunks)
        assert total == 50

    def test_multiple_types_preserved(self):
        issues = {
            "Story": [make_issue(key="P-1", issue_type="Story")],
            "Bug": [make_issue(key="P-2", issue_type="Bug")],
        }
        chunks = chunk_issues(issues, token_limit=5000)
        assert len(chunks) == 1
        assert "Story" in chunks[0]
        assert "Bug" in chunks[0]

    def test_empty_input(self):
        chunks = chunk_issues({})
        assert len(chunks) == 1
        assert chunks[0] == {}

    def test_split_preserves_type_keys(self):
        # Each chunk should have valid type keys
        issues = {
            "Story": [
                make_issue(key=f"P-{i}", summary="x" * 200)
                for i in range(20)
            ]
        }
        chunks = chunk_issues(issues, token_limit=300)
        for chunk in chunks:
            for key in chunk:
                assert key == "Story"


class TestNeedsChunking:
    def test_small_set_no_chunking(self):
        issues = {"Story": [make_issue()]}
        assert not needs_chunking(issues, token_limit=5000)

    def test_large_set_needs_chunking(self):
        issues = {
            "Story": [
                make_issue(key=f"P-{i}", summary="x" * 200)
                for i in range(100)
            ]
        }
        assert needs_chunking(issues, token_limit=500)


class TestBuildChunkSummaryPrompt:
    def test_includes_chunk_info(self):
        chunk = {"Story": [make_issue(key="P-1")]}
        prompt = build_chunk_summary_prompt(chunk, 0, 3, "Sprint 42")
        assert "part 1 of 3" in prompt
        assert "Sprint 42" in prompt
        assert "P-1" in prompt

    def test_includes_issue_count(self):
        chunk = {
            "Story": [make_issue(key="P-1"), make_issue(key="P-2")],
            "Bug": [make_issue(key="P-3", issue_type="Bug")],
        }
        prompt = build_chunk_summary_prompt(chunk, 1, 5, "Sprint 1")
        assert "3 issues" in prompt


class TestBuildReducePrompt:
    def test_combines_summaries(self):
        summaries = ["Summary A about features.", "Summary B about bugs."]
        prompt = build_reduce_prompt(summaries, "Sprint 42")
        assert "Batch 1 summary" in prompt
        assert "Batch 2 summary" in prompt
        assert "Summary A" in prompt
        assert "Summary B" in prompt
        assert "Sprint 42" in prompt

    def test_includes_historical_context(self):
        summaries = ["Summary A."]
        prompt = build_reduce_prompt(summaries, "Sprint 42", historical_context="Past work on auth.")
        assert "Past work on auth." in prompt
        assert "previous sprints" in prompt.lower() or "Historical" in prompt

    def test_no_historical_context(self):
        summaries = ["Summary A."]
        prompt = build_reduce_prompt(summaries, "Sprint 42", historical_context="")
        assert "Historical" not in prompt
