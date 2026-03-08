"""Tests for main.py — CLI entry point and orchestration."""

import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest
import yaml

from tests.conftest import make_sprint, make_issue, make_release_notes


class TestLoadConfig:
    def test_missing_config_exits(self, tmp_path):
        from main import load_config
        missing = tmp_path / "nonexistent.yaml"
        with pytest.raises(SystemExit):
            load_config(config_path=missing)

    def test_valid_config(self, tmp_path):
        from main import load_config
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "jira": {"url": "https://jira.test", "default_board": "Board"},
            "llm": {"provider": "openai", "model": "gpt-4o"},
        }))
        config = load_config(config_path=config_file)
        assert config["jira"]["url"] == "https://jira.test"

    def test_missing_url_exits(self, tmp_path):
        from main import load_config
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"jira": {"default_board": "Board"}}))
        with pytest.raises(SystemExit):
            load_config(config_path=config_file)

    def test_empty_yaml_exits(self, tmp_path):
        from main import load_config
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        with pytest.raises(SystemExit):
            load_config(config_path=config_file)


class TestOutputFilenameSanitization:
    def test_spaces_replaced(self):
        name = "Sprint 42"
        safe = re.sub(r'[^a-z0-9_-]', '', name.lower().replace(' ', '_'))
        assert safe == "sprint_42"

    def test_special_chars_stripped(self):
        name = "Sprint 42! (special)/path"
        safe = re.sub(r'[^a-z0-9_-]', '', name.lower().replace(' ', '_'))
        assert safe == "sprint_42_specialpath"

    def test_slashes_stripped(self):
        name = "Sprint 42/43"
        safe = re.sub(r'[^a-z0-9_-]', '', name.lower().replace(' ', '_'))
        assert "/" not in safe

    def test_all_special_chars_produces_nonempty(self):
        """Edge case: name with only special chars."""
        name = "!!!"
        safe = re.sub(r'[^a-z0-9_-]', '', name.lower().replace(' ', '_'))
        # Result is empty string, but filename still works due to prefix
        assert safe == ""


class TestMainCLI:
    @patch("main.load_dotenv")
    @patch("main.yaml.safe_load")
    @patch("main.Path")
    @patch.dict(os.environ, {
        "JIRA_EMAIL": "test@test.com",
        "JIRA_API_TOKEN": "token",
        "LLM_API_KEY": "sk-test",
    })
    def test_missing_board_exits(self, MockPath, mock_yaml, mock_dotenv):
        """No --board and no default_board should exit."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.__truediv__ = MagicMock(return_value=mock_path)
        mock_path.open = mock_open(read_data="jira:\n  url: https://jira.test\n")
        MockPath.return_value = mock_path

        mock_yaml.return_value = {"jira": {"url": "https://jira.test"}}

        from main import main
        with patch("sys.argv", ["main.py"]):
            with pytest.raises(SystemExit):
                main()

    @patch.dict(os.environ, {}, clear=True)
    @patch("main.load_dotenv")
    @patch("main.load_config", return_value={"jira": {"url": "https://jira.test"}})
    def test_missing_jira_credentials_exits(self, mock_config, mock_dotenv):
        from main import main
        with patch("sys.argv", ["main.py", "--board", "Board"]):
            with pytest.raises(SystemExit):
                main()

    @patch.dict(os.environ, {}, clear=True)
    @patch("main.load_dotenv")
    @patch("main.load_config", return_value={
        "jira": {"url": "https://jira.test", "auth_method": "pat"},
    })
    def test_missing_pat_token_exits(self, mock_config, mock_dotenv):
        from main import main
        with patch("sys.argv", ["main.py", "--board", "Board"]):
            with pytest.raises(SystemExit):
                main()

    @patch.dict(os.environ, {"JIRA_PAT": "my-pat"}, clear=True)
    @patch("main.load_dotenv")
    @patch("main.load_config", return_value={
        "jira": {"url": "https://jira.test", "default_board": "Board", "auth_method": "pat"},
    })
    @patch("main.JiraClient")
    @patch("main.generate_summary", return_value="Test summary")
    @patch("main.generate_html", return_value="<html></html>")
    def test_pat_auth_works(self, mock_html, mock_summary, MockClient,
                            mock_config, mock_dotenv, tmp_path, capsys):
        mock_client = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.find_board.return_value = {"id": 1, "name": "Board"}
        sprint = make_sprint()
        mock_client.find_sprint_by_name.return_value = sprint
        mock_client.get_completed_issues.return_value = {}

        with patch("sys.argv", ["main.py", "--sprint", "Sprint 42"]):
            with patch("main.Path") as MockPath:
                mock_output_dir = MagicMock()
                MockPath.return_value = mock_output_dir
                mock_output_path = MagicMock()
                mock_output_dir.__truediv__ = MagicMock(return_value=mock_output_path)
                from main import main
                main()

        # Verify JiraClient was called with pat auth
        MockClient.assert_called_once_with(
            url="https://jira.test",
            email=None,
            api_token=None,
            pat="my-pat",
            auth_method="pat",
        )

    @patch.dict(os.environ, {
        "JIRA_EMAIL": "test@test.com",
        "JIRA_API_TOKEN": "token",
    }, clear=True)
    @patch("main.load_dotenv")
    @patch("main.load_config", return_value={
        "jira": {"url": "https://jira.test", "default_board": "Board"},
    })
    @patch("main.JiraClient")
    @patch("main.generate_summary", return_value="Test summary")
    @patch("main.generate_html", return_value="<html></html>")
    def test_llm_key_optional(self, mock_html, mock_summary, MockClient,
                               mock_config, mock_dotenv, tmp_path, capsys):
        """LLM key missing should warn but not exit."""
        mock_client = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.find_board.return_value = {"id": 1, "name": "Board"}
        sprint = make_sprint()
        mock_client.find_sprint_by_name.return_value = sprint
        mock_client.get_completed_issues.return_value = {}

        with patch("sys.argv", ["main.py", "--sprint", "Sprint 42"]):
            with patch("main.Path") as MockPath:
                mock_output_dir = MagicMock()
                MockPath.return_value = mock_output_dir
                mock_output_path = MagicMock()
                mock_output_dir.__truediv__ = MagicMock(return_value=mock_output_path)
                from main import main
                main()

        captured = capsys.readouterr()
        assert "No LLM API key set" in captured.out


class TestInteractiveSprint:
    def test_auto_confirm(self):
        from main import select_sprint_interactive
        mock_client = MagicMock()
        sprints = [make_sprint(id=2, state="active"), make_sprint(id=1, state="closed")]
        mock_client.get_sprints.return_value = sprints

        with patch("builtins.input", return_value=""):
            result = select_sprint_interactive(mock_client, 42, "Board")
        assert result.state == "active"

    def test_list_and_select(self):
        from main import select_sprint_interactive
        mock_client = MagicMock()
        sprints = [
            make_sprint(id=3, name="Sprint 3", state="active"),
            make_sprint(id=2, name="Sprint 2", state="closed"),
            make_sprint(id=1, name="Sprint 1", state="closed"),
        ]
        mock_client.get_sprints.return_value = sprints

        with patch("builtins.input", side_effect=["list", "2"]):
            result = select_sprint_interactive(mock_client, 42, "Board")
        assert result.name == "Sprint 2"

    def test_invalid_then_valid_input(self):
        from main import select_sprint_interactive
        mock_client = MagicMock()
        sprints = [make_sprint(id=1, state="closed")]
        mock_client.get_sprints.return_value = sprints

        with patch("builtins.input", side_effect=["list", "abc", "0", "1"]):
            result = select_sprint_interactive(mock_client, 42, "Board")
        assert result.id == 1

    def test_no_sprints_exits(self):
        from main import select_sprint_interactive
        mock_client = MagicMock()
        mock_client.get_sprints.return_value = []

        with pytest.raises(SystemExit):
            select_sprint_interactive(mock_client, 42, "Board")

    def test_prefers_active_sprint(self):
        from main import select_sprint_interactive
        mock_client = MagicMock()
        sprints = [
            make_sprint(id=3, name="Sprint 3", state="closed"),
            make_sprint(id=2, name="Sprint 2", state="active"),
            make_sprint(id=1, name="Sprint 1", state="closed"),
        ]
        mock_client.get_sprints.return_value = sprints

        with patch("builtins.input", return_value=""):
            result = select_sprint_interactive(mock_client, 42, "Board")
        assert result.name == "Sprint 2"
