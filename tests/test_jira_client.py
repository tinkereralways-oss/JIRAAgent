"""Tests for jira_client.py — Jira REST API wrapper."""

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import requests

from jira_client import JiraClient, JiraClientError


def _mock_response(status_code=200, json_data=None, text="", headers=None):
    """Create a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = text or json.dumps(json_data or {})
    resp.headers = headers or {}
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = requests.exceptions.JSONDecodeError("", "", 0)
    resp.raise_for_status = MagicMock()
    if status_code >= 400 and status_code != 429:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp
        )
    return resp


class TestRequest:
    def test_successful_request(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        mock_resp = _mock_response(200, {"key": "value"})
        client.session.request = MagicMock(return_value=mock_resp)

        result = client._request("GET", "https://jira.test/api")
        assert result == {"key": "value"}

    def test_timeout_is_set(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        mock_resp = _mock_response(200, {"ok": True})
        client.session.request = MagicMock(return_value=mock_resp)

        client._request("GET", "https://jira.test/api")
        _, kwargs = client.session.request.call_args
        assert kwargs["timeout"] == (10, 30)

    @patch("jira_client.time.sleep")
    def test_rate_limit_retry_succeeds(self, mock_sleep):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        r429 = _mock_response(429, headers={"Retry-After": "2"})
        r200 = _mock_response(200, {"ok": True})
        client.session.request = MagicMock(side_effect=[r429, r429, r200])

        result = client._request("GET", "https://jira.test/api")
        assert result == {"ok": True}
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(2)

    @patch("jira_client.time.sleep")
    def test_rate_limit_exhausted(self, mock_sleep):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        r429 = _mock_response(429, headers={"Retry-After": "1"})
        client.session.request = MagicMock(return_value=r429)

        with pytest.raises(JiraClientError, match="Rate limit exceeded"):
            client._request("GET", "https://jira.test/api")

    @patch("jira_client.time.sleep")
    def test_rate_limit_non_numeric_retry_after(self, mock_sleep):
        """Bug #2: Non-numeric Retry-After should not crash."""
        client = JiraClient("https://jira.test", "a@b.com", "token")
        r429 = _mock_response(429, headers={"Retry-After": "Thu, 01 Jan 2026 00:00:00 GMT"})
        r200 = _mock_response(200, {"ok": True})
        client.session.request = MagicMock(side_effect=[r429, r200])

        result = client._request("GET", "https://jira.test/api")
        assert result == {"ok": True}
        mock_sleep.assert_called_with(5)  # Falls back to default

    def test_http_error_wrapped_in_jira_client_error(self):
        """Bug #1: HTTPError must be wrapped in JiraClientError."""
        client = JiraClient("https://jira.test", "a@b.com", "token")
        r500 = _mock_response(500, text="Internal Server Error")
        client.session.request = MagicMock(return_value=r500)

        with pytest.raises(JiraClientError, match="Jira API error 500"):
            client._request("GET", "https://jira.test/api")

    def test_http_401_wrapped(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        r401 = _mock_response(401, text="Unauthorized")
        client.session.request = MagicMock(return_value=r401)

        with pytest.raises(JiraClientError, match="Jira API error 401"):
            client._request("GET", "https://jira.test/api")

    def test_malformed_json_wrapped(self):
        """Bug #4: Non-JSON response must not crash with raw JSONDecodeError."""
        client = JiraClient("https://jira.test", "a@b.com", "token")
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.text = "<html>Login page</html>"
        resp.headers = {}
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = requests.exceptions.JSONDecodeError("", "", 0)
        client.session.request = MagicMock(return_value=resp)

        with pytest.raises(JiraClientError, match="Invalid JSON response"):
            client._request("GET", "https://jira.test/api")

    def test_connection_error_wrapped(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client.session.request = MagicMock(
            side_effect=requests.exceptions.ConnectionError("DNS failed")
        )

        with pytest.raises(JiraClientError, match="Connection failed"):
            client._request("GET", "https://jira.test/api")

    def test_timeout_error_wrapped(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client.session.request = MagicMock(
            side_effect=requests.exceptions.Timeout("Timed out")
        )

        with pytest.raises(JiraClientError, match="Request timed out"):
            client._request("GET", "https://jira.test/api")


class TestFindBoard:
    def test_board_found(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client._request = MagicMock(
            return_value={"values": [{"id": 42, "name": "My Board"}]}
        )
        board = client.find_board("My Board")
        assert board["id"] == 42

    def test_board_not_found_lists_available(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client._request = MagicMock(
            side_effect=[
                {"values": []},  # search returns nothing
                {"values": [{"name": "Board A"}, {"name": "Board B"}]},  # list all
            ]
        )
        with pytest.raises(JiraClientError, match="Board A"):
            client.find_board("Missing Board")


class TestGetSprints:
    def test_single_page(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client._request = MagicMock(return_value={
            "values": [
                {"id": 1, "name": "Sprint 1", "state": "closed",
                 "startDate": "2026-01-01T00:00:00Z", "endDate": "2026-01-14T00:00:00Z"},
            ],
            "isLast": True,
        })
        sprints = client.get_sprints(42)
        assert len(sprints) == 1
        assert sprints[0].name == "Sprint 1"

    def test_pagination(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client._request = MagicMock(side_effect=[
            {
                "values": [{"id": 1, "name": "Sprint 1", "state": "closed"}],
                "isLast": False,
            },
            {
                "values": [{"id": 2, "name": "Sprint 2", "state": "active"}],
                "isLast": True,
            },
        ])
        sprints = client.get_sprints(42)
        assert len(sprints) == 2

    def test_empty_board(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client._request = MagicMock(return_value={"values": [], "isLast": True})
        assert client.get_sprints(42) == []


class TestFindSprintByName:
    def test_found_case_insensitive(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client._request = MagicMock(return_value={
            "values": [{"id": 10, "name": "Sprint 42", "state": "closed"}],
            "isLast": True,
        })
        result = client.find_sprint_by_name(42, "sprint 42")
        assert result is not None
        assert result.id == 10

    def test_not_found(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client._request = MagicMock(return_value={"values": [], "isLast": True})
        assert client.find_sprint_by_name(42, "Sprint 99") is None


class TestGetCompletedIssues:
    def test_issues_grouped_by_type(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client._request = MagicMock(return_value={
            "issues": [
                {"key": "P-1", "fields": {
                    "summary": "Story one", "issuetype": {"name": "Story"},
                    "status": {"name": "Done"}, "assignee": {"displayName": "Alice"},
                    "priority": {"name": "High"}, "labels": [], "resolution": {"name": "Done"},
                    "created": "2026-01-01", "resolutiondate": "2026-01-10",
                }},
                {"key": "P-2", "fields": {
                    "summary": "Bug fix", "issuetype": {"name": "Bug"},
                    "status": {"name": "Done"}, "assignee": None,
                    "priority": None, "labels": ["backend"], "resolution": None,
                    "created": "2026-01-02", "resolutiondate": None,
                }},
            ],
            "total": 2,
        })
        result = client.get_completed_issues(100)
        assert "Story" in result
        assert "Bug" in result
        assert len(result["Story"]) == 1
        assert result["Bug"][0].assignee is None
        assert result["Bug"][0].labels == ["backend"]

    def test_pagination_collects_all(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        page1 = {
            "issues": [{"key": f"P-{i}", "fields": {
                "summary": f"Issue {i}", "issuetype": {"name": "Task"},
                "status": {"name": "Done"}, "assignee": None,
                "priority": None, "labels": [], "resolution": None,
                "created": "2026-01-01", "resolutiondate": None,
            }} for i in range(100)],
            "total": 150,
        }
        page2 = {
            "issues": [{"key": f"P-{i}", "fields": {
                "summary": f"Issue {i}", "issuetype": {"name": "Task"},
                "status": {"name": "Done"}, "assignee": None,
                "priority": None, "labels": [], "resolution": None,
                "created": "2026-01-01", "resolutiondate": None,
            }} for i in range(100, 150)],
            "total": 150,
        }
        client._request = MagicMock(side_effect=[page1, page2])
        result = client.get_completed_issues(100)
        assert len(result["Task"]) == 150

    def test_empty_sprint(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client._request = MagicMock(return_value={"issues": [], "total": 0})
        assert client.get_completed_issues(100) == {}

    def test_null_nested_fields(self):
        """Verify assignee=null, priority=null don't crash."""
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client._request = MagicMock(return_value={
            "issues": [{"key": "P-1", "fields": {
                "summary": "s", "issuetype": {"name": "Task"},
                "status": {"name": "Done"}, "assignee": None,
                "priority": None, "labels": [], "resolution": None,
                "created": None, "resolutiondate": None,
            }}],
            "total": 1,
        })
        result = client.get_completed_issues(100)
        issue = result["Task"][0]
        assert issue.assignee is None
        assert issue.priority is None


class TestContextManager:
    def test_session_closed_on_exit(self):
        client = JiraClient("https://jira.test", "a@b.com", "token")
        client.session.close = MagicMock()
        with client:
            pass
        client.session.close.assert_called_once()

    def test_url_trailing_slash_stripped(self):
        client = JiraClient("https://jira.test/", "a@b.com", "token")
        assert client.base_url == "https://jira.test"


class TestAuthentication:
    def test_basic_auth_sets_session_auth(self):
        client = JiraClient("https://jira.test", email="a@b.com", api_token="token")
        assert client.session.auth == ("a@b.com", "token")
        assert "Authorization" not in client.session.headers

    def test_pat_auth_sets_bearer_header(self):
        client = JiraClient(
            "https://jira.test", pat="my-pat-token", auth_method="pat"
        )
        assert client.session.headers["Authorization"] == "Bearer my-pat-token"
        assert client.session.auth is None

    def test_pat_auth_missing_token_raises(self):
        with pytest.raises(JiraClientError, match="Personal Access Token"):
            JiraClient("https://jira.test", auth_method="pat")

    def test_basic_auth_missing_email_raises(self):
        with pytest.raises(JiraClientError, match="JIRA_EMAIL and JIRA_API_TOKEN"):
            JiraClient("https://jira.test", api_token="token", auth_method="basic")

    def test_basic_auth_missing_token_raises(self):
        with pytest.raises(JiraClientError, match="JIRA_EMAIL and JIRA_API_TOKEN"):
            JiraClient("https://jira.test", email="a@b.com", auth_method="basic")

    def test_pat_auth_request_succeeds(self):
        client = JiraClient(
            "https://jira.test", pat="my-pat-token", auth_method="pat"
        )
        mock_resp = _mock_response(200, {"key": "value"})
        client.session.request = MagicMock(return_value=mock_resp)

        result = client._request("GET", "https://jira.test/api")
        assert result == {"key": "value"}

    def test_default_auth_method_is_basic(self):
        client = JiraClient("https://jira.test", email="a@b.com", api_token="tok")
        assert client.session.auth == ("a@b.com", "tok")
