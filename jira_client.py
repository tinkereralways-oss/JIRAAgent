"""Jira REST API wrapper for fetching sprint and issue data."""

import time
from typing import Optional

import requests

from models import JiraIssue, SprintInfo


class JiraClientError(Exception):
    pass


class JiraClient:
    def __init__(self, url: str, email: str, api_token: str):
        self.base_url = url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update({"Accept": "application/json"})

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _request(self, method: str, url: str, **kwargs) -> dict:
        for attempt in range(3):
            try:
                resp = self.session.request(method, url, timeout=(10, 30), **kwargs)
            except requests.exceptions.ConnectionError as e:
                raise JiraClientError(f"Connection failed: {e}") from e
            except requests.exceptions.Timeout as e:
                raise JiraClientError(f"Request timed out: {e}") from e
            if resp.status_code == 429:
                try:
                    retry_after = int(resp.headers.get("Retry-After", 5))
                except (ValueError, TypeError):
                    retry_after = 5
                print(f"Rate limited, retrying in {retry_after}s...")
                time.sleep(retry_after)
                continue
            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                raise JiraClientError(
                    f"Jira API error {resp.status_code}: {resp.text[:200]}"
                ) from e
            try:
                return resp.json()
            except requests.exceptions.JSONDecodeError as e:
                raise JiraClientError(
                    f"Invalid JSON response from Jira: {resp.text[:200]}"
                ) from e
        raise JiraClientError("Rate limit exceeded after retries")

    def find_board(self, board_name: str) -> dict:
        """Find a board by name. Returns board dict with 'id' and 'name'."""
        url = f"{self.base_url}/rest/agile/1.0/board"
        data = self._request("GET", url, params={"name": board_name})
        boards = data.get("values", [])
        if not boards:
            # List available boards to help the user
            all_data = self._request("GET", url, params={"maxResults": 50})
            available = [b["name"] for b in all_data.get("values", [])]
            raise JiraClientError(
                f"Board '{board_name}' not found. Available boards: {available}"
            )
        return boards[0]

    def get_sprints(
        self, board_id: int, states: str = "closed,active"
    ) -> list[SprintInfo]:
        """Get sprints for a board, filtered by state."""
        url = f"{self.base_url}/rest/agile/1.0/board/{board_id}/sprint"
        sprints = []
        start_at = 0
        while True:
            data = self._request(
                "GET",
                url,
                params={"state": states, "startAt": start_at, "maxResults": 50},
            )
            for s in data.get("values", []):
                sprints.append(
                    SprintInfo(
                        id=s["id"],
                        name=s["name"],
                        state=s["state"],
                        start_date=s.get("startDate"),
                        end_date=s.get("endDate"),
                        complete_date=s.get("completeDate"),
                    )
                )
            if data.get("isLast", True):
                break
            start_at += len(data.get("values", []))
        return sprints

    def find_sprint_by_name(
        self, board_id: int, sprint_name: str
    ) -> Optional[SprintInfo]:
        """Find a specific sprint by name."""
        sprints = self.get_sprints(board_id, states="closed,active,future")
        for s in sprints:
            if s.name.lower() == sprint_name.lower():
                return s
        return None

    def get_completed_issues(
        self, sprint_id: int
    ) -> dict[str, list[JiraIssue]]:
        """Fetch all Done issues for a sprint, grouped by issue type."""
        url = f"{self.base_url}/rest/api/2/search"
        jql = f"sprint={sprint_id} AND statusCategory=Done"
        fields = (
            "summary,issuetype,status,assignee,priority,labels,"
            "resolution,created,resolutiondate"
        )

        issues_by_type: dict[str, list[JiraIssue]] = {}
        start_at = 0

        while True:
            data = self._request(
                "GET",
                url,
                params={
                    "jql": jql,
                    "fields": fields,
                    "startAt": start_at,
                    "maxResults": 100,
                },
            )

            for raw in data.get("issues", []):
                f = raw["fields"]
                issue = JiraIssue(
                    key=raw["key"],
                    summary=f.get("summary", ""),
                    issue_type=f.get("issuetype", {}).get("name", "Unknown"),
                    status=f.get("status", {}).get("name", ""),
                    assignee=(f.get("assignee") or {}).get("displayName"),
                    priority=(f.get("priority") or {}).get("name"),
                    labels=f.get("labels", []),
                    resolution=(f.get("resolution") or {}).get("name"),
                    created=f.get("created"),
                    resolved=f.get("resolutiondate"),
                )
                issues_by_type.setdefault(issue.issue_type, []).append(issue)

            total = data.get("total", 0)
            start_at += len(data.get("issues", []))
            if start_at >= total:
                break

        return issues_by_type
