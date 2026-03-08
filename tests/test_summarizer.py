"""Tests for summarizer.py — OpenAI GPT summarization."""

from unittest.mock import MagicMock, patch

import pytest
import openai

from summarizer import generate_summary, _fallback_summary, _pluralize
from tests.conftest import make_issue


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
    def test_no_api_key_returns_fallback(self):
        issues = {"Story": [make_issue()]}
        result = generate_summary(issues, "Sprint 42", api_key=None)
        assert "Sprint 42 completed" in result

    def test_empty_api_key_returns_fallback(self):
        issues = {"Story": [make_issue()]}
        result = generate_summary(issues, "Sprint 42", api_key="")
        assert "Sprint 42 completed" in result

    @patch("summarizer.OpenAI")
    def test_successful_openai_call(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = "  Great sprint with solid delivery.  "
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        issues = {"Story": [make_issue()]}
        result = generate_summary(issues, "Sprint 42", api_key="sk-test")
        assert result == "Great sprint with solid delivery."

    @patch("summarizer.OpenAI")
    def test_openai_error_returns_fallback(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.side_effect = openai.OpenAIError("fail")

        issues = {"Story": [make_issue()]}
        result = generate_summary(issues, "Sprint 42", api_key="sk-test")
        assert "Sprint 42 completed" in result

    @patch("summarizer.OpenAI")
    def test_empty_choices_returns_fallback(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(choices=[])

        issues = {"Story": [make_issue()]}
        result = generate_summary(issues, "Sprint 42", api_key="sk-test")
        assert "Sprint 42 completed" in result

    @patch("summarizer.OpenAI")
    def test_null_content_returns_fallback(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        issues = {"Story": [make_issue()]}
        result = generate_summary(issues, "Sprint 42", api_key="sk-test")
        assert "Sprint 42 completed" in result

    @patch("summarizer.OpenAI")
    def test_model_parameter_passed(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = "Summary"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        generate_summary({"Story": [make_issue()]}, "S1", model="gpt-3.5-turbo", api_key="sk-test")
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-3.5-turbo"

    @patch("summarizer.OpenAI")
    def test_prompt_includes_issue_keys(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = "Summary"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        issues = {"Story": [make_issue(key="PROJ-99"), make_issue(key="PROJ-100")]}
        generate_summary(issues, "Sprint 42", api_key="sk-test")

        call_args = mock_client.chat.completions.create.call_args[1]
        user_msg = call_args["messages"][1]["content"]
        assert "PROJ-99" in user_msg
        assert "PROJ-100" in user_msg

    @patch("summarizer.OpenAI")
    def test_prompt_uses_correct_pluralization(self, MockOpenAI):
        """Bug #6: Prompt should say 'Stories' not 'Storys'."""
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = "Summary"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        issues = {"Story": [make_issue()]}
        generate_summary(issues, "Sprint 42", api_key="sk-test")

        call_args = mock_client.chat.completions.create.call_args[1]
        user_msg = call_args["messages"][1]["content"]
        assert "Stories" in user_msg
        assert "Storys" not in user_msg
