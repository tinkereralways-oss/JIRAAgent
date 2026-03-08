"""Tests for summarizer.py — LLM-agnostic summarization engine."""

from unittest.mock import MagicMock

import pytest

from summarizer import generate_summary, _fallback_summary, _pluralize
from tests.conftest import make_issue


def _mock_llm(response_text: str | None = "Summary text.") -> MagicMock:
    """Create a mock LLMClient that returns the given text."""
    mock = MagicMock()
    mock.complete.return_value = response_text
    return mock


class TestPluralize:
    def test_story(self):
        assert _pluralize("Story") == "Stories"

    def test_bug(self):
        assert _pluralize("Bug") == "Bugs"

    def test_task(self):
        assert _pluralize("Task") == "Tasks"

    def test_epic(self):
        assert _pluralize("Epic") == "Epics"

    def test_subtask(self):
        assert _pluralize("Sub-task") == "Sub-tasks"

    def test_unknown_ending_in_y(self):
        assert _pluralize("Category") == "Categories"

    def test_unknown_ending_in_ey(self):
        # 'ey' has vowel before y, so just add 's'
        assert _pluralize("Key") == "Keys"

    def test_unknown_regular(self):
        assert _pluralize("Widget") == "Widgets"


class TestFallbackSummary:
    def test_with_issues(self):
        issues = {
            "Story": [make_issue(key="P-1"), make_issue(key="P-2")],
            "Bug": [make_issue(key="P-3", issue_type="Bug")],
        }
        result = _fallback_summary(issues, "Sprint 42")
        assert "Sprint 42 completed 3 issues" in result
        assert "2 story(s)" in result
        assert "1 bug(s)" in result

    def test_empty_issues_no_dangling_colon(self):
        """Bug #5: Empty issues should not produce 'completed 0 issues: .'"""
        result = _fallback_summary({}, "Sprint 42")
        assert ": ." not in result
        assert "0 issues" in result

    def test_types_sorted_alphabetically(self):
        issues = {
            "Task": [make_issue(issue_type="Task")],
            "Bug": [make_issue(issue_type="Bug")],
        }
        result = _fallback_summary(issues, "Sprint 1")
        bug_pos = result.index("bug")
        task_pos = result.index("task")
        assert bug_pos < task_pos


class TestGenerateSummary:
    def test_no_llm_client_returns_fallback(self):
        issues = {"Story": [make_issue()]}
        result = generate_summary(issues, "Sprint 42", llm_client=None)
        assert "Sprint 42 completed" in result

    def test_successful_llm_call(self):
        llm = _mock_llm("  Great sprint with solid delivery.  ")
        issues = {"Story": [make_issue()]}
        result = generate_summary(issues, "Sprint 42", llm_client=llm)
        assert result == "  Great sprint with solid delivery.  "
        llm.complete.assert_called_once()

    def test_llm_failure_returns_fallback(self):
        llm = _mock_llm(None)
        issues = {"Story": [make_issue()]}
        result = generate_summary(issues, "Sprint 42", llm_client=llm)
        assert "Sprint 42 completed" in result

    def test_prompt_includes_issue_keys(self):
        llm = _mock_llm("Summary")
        issues = {"Story": [make_issue(key="PROJ-99"), make_issue(key="PROJ-100")]}
        generate_summary(issues, "Sprint 42", llm_client=llm)

        call_args = llm.complete.call_args
        user_prompt = call_args[0][1]  # second positional arg
        assert "PROJ-99" in user_prompt
        assert "PROJ-100" in user_prompt

    def test_prompt_uses_correct_pluralization(self):
        """Bug #6: Prompt should say 'Stories' not 'Storys'."""
        llm = _mock_llm("Summary")
        issues = {"Story": [make_issue()]}
        generate_summary(issues, "Sprint 42", llm_client=llm)

        call_args = llm.complete.call_args
        user_prompt = call_args[0][1]
        assert "Stories" in user_prompt
        assert "Storys" not in user_prompt

    def test_historical_context_included_in_prompt(self):
        llm = _mock_llm("Summary with context")
        issues = {"Story": [make_issue()]}
        generate_summary(
            issues, "Sprint 42", llm_client=llm,
            historical_context="Past work on auth system."
        )

        call_args = llm.complete.call_args
        user_prompt = call_args[0][1]
        assert "Past work on auth system." in user_prompt

    def test_chunked_summarization_for_large_sprints(self):
        llm = _mock_llm("Chunk summary.")
        # Create enough issues to trigger chunking with a tiny limit
        issues = {
            "Story": [
                make_issue(key=f"P-{i}", summary=f"Feature {i} " * 20)
                for i in range(50)
            ]
        }
        result = generate_summary(
            issues, "Sprint 42", llm_client=llm, chunk_token_limit=500
        )
        # LLM should be called multiple times (map + reduce)
        assert llm.complete.call_count > 1
        assert result == "Chunk summary."

    def test_chunked_with_all_failures_returns_batch_fallbacks(self):
        llm = _mock_llm(None)  # All calls fail
        issues = {
            "Story": [
                make_issue(key=f"P-{i}", summary=f"Feature {i} " * 20)
                for i in range(50)
            ]
        }
        result = generate_summary(
            issues, "Sprint 42", llm_client=llm, chunk_token_limit=500
        )
        # When all LLM calls fail, map phase produces per-chunk fallbacks,
        # reduce also fails, so we get concatenated batch summaries
        assert "Batch 1" in result
        assert "story(s)" in result
