"""Tests for vector_store.py — ChromaDB vector memory management."""

import tempfile
import shutil

import pytest

from vector_store import VectorStore
from tests.conftest import make_issue, make_sprint


@pytest.fixture
def tmp_store(tmp_path):
    """Create a VectorStore with a temporary directory."""
    store = VectorStore(persist_dir=str(tmp_path / "testdb"))
    yield store


class TestVectorStoreBasics:
    def test_empty_store(self, tmp_store):
        assert tmp_store.count() == 0

    def test_store_sprint_issues(self, tmp_store):
        sprint = make_sprint(id=100, name="Sprint 42")
        issues = {
            "Story": [
                make_issue(key="PROJ-1", summary="Add user dashboard"),
                make_issue(key="PROJ-2", summary="Implement search"),
            ],
            "Bug": [
                make_issue(key="PROJ-3", issue_type="Bug", summary="Fix login crash"),
            ],
        }
        stored = tmp_store.store_sprint_issues(sprint, issues)
        assert stored == 3
        assert tmp_store.count() == 3

    def test_store_empty_sprint(self, tmp_store):
        sprint = make_sprint()
        stored = tmp_store.store_sprint_issues(sprint, {})
        assert stored == 0
        assert tmp_store.count() == 0

    def test_upsert_idempotent(self, tmp_store):
        sprint = make_sprint(id=100)
        issues = {"Story": [make_issue(key="PROJ-1")]}
        tmp_store.store_sprint_issues(sprint, issues)
        tmp_store.store_sprint_issues(sprint, issues)
        assert tmp_store.count() == 1  # upsert, not duplicate

    def test_clear(self, tmp_store):
        sprint = make_sprint()
        issues = {"Story": [make_issue(key="PROJ-1")]}
        tmp_store.store_sprint_issues(sprint, issues)
        assert tmp_store.count() == 1
        tmp_store.clear()
        assert tmp_store.count() == 0


class TestQuerySimilar:
    def test_query_returns_results(self, tmp_store):
        sprint = make_sprint(id=100, name="Sprint 42")
        issues = {
            "Story": [
                make_issue(key="PROJ-1", summary="Add user authentication"),
                make_issue(key="PROJ-2", summary="Build admin dashboard"),
            ],
            "Bug": [
                make_issue(key="PROJ-3", issue_type="Bug", summary="Fix login page crash"),
            ],
        }
        tmp_store.store_sprint_issues(sprint, issues)

        results = tmp_store.query_similar("authentication login", n_results=5)
        assert len(results) > 0
        assert "document" in results[0]
        assert "metadata" in results[0]
        assert "distance" in results[0]

    def test_query_empty_store(self, tmp_store):
        results = tmp_store.query_similar("test query")
        assert results == []

    def test_exclude_sprint_id(self, tmp_store):
        sprint1 = make_sprint(id=100, name="Sprint 42")
        sprint2 = make_sprint(id=200, name="Sprint 43")

        tmp_store.store_sprint_issues(sprint1, {
            "Story": [make_issue(key="PROJ-1", summary="User auth feature")],
        })
        tmp_store.store_sprint_issues(sprint2, {
            "Story": [make_issue(key="PROJ-10", summary="Auth improvements")],
        })

        # Exclude sprint 200
        results = tmp_store.query_similar(
            "authentication", n_results=10, exclude_sprint_id=200
        )
        # Should only return sprint 100 results
        for r in results:
            assert r["metadata"]["sprint_id"] != 200


class TestSprintHistory:
    def test_empty_history(self, tmp_store):
        history = tmp_store.get_sprint_history()
        assert history == []

    def test_history_with_data(self, tmp_store):
        sprint1 = make_sprint(id=100, name="Sprint 42")
        sprint2 = make_sprint(id=200, name="Sprint 43")

        tmp_store.store_sprint_issues(sprint1, {
            "Story": [make_issue(key="P-1"), make_issue(key="P-2")],
            "Bug": [make_issue(key="P-3", issue_type="Bug")],
        })
        tmp_store.store_sprint_issues(sprint2, {
            "Task": [make_issue(key="P-4", issue_type="Task")],
        })

        history = tmp_store.get_sprint_history()
        assert len(history) == 2
        # Most recent first
        assert history[0]["sprint_id"] == 200
        assert history[0]["sprint_name"] == "Sprint 43"
        assert history[0]["issue_count"] == 1
        assert history[1]["sprint_id"] == 100
        assert history[1]["issue_count"] == 3

    def test_history_limit(self, tmp_store):
        for i in range(10):
            sprint = make_sprint(id=i, name=f"Sprint {i}")
            tmp_store.store_sprint_issues(sprint, {
                "Story": [make_issue(key=f"P-{i}")],
            })
        history = tmp_store.get_sprint_history(limit=3)
        assert len(history) == 3


class TestRelatedContext:
    def test_no_context_for_first_sprint(self, tmp_store):
        issues = {"Story": [make_issue(key="P-1", summary="New feature")]}
        context = tmp_store.get_related_context(issues, current_sprint_id=100)
        assert context == ""

    def test_context_from_past_sprints(self, tmp_store):
        # Store past sprint
        past_sprint = make_sprint(id=50, name="Sprint 40")
        tmp_store.store_sprint_issues(past_sprint, {
            "Story": [make_issue(key="OLD-1", summary="Initial auth implementation")],
        })

        # Query with current sprint issues
        current_issues = {
            "Story": [make_issue(key="NEW-1", summary="Auth improvements")],
        }
        context = tmp_store.get_related_context(current_issues, current_sprint_id=100)
        assert "previous sprints" in context.lower() or "Sprint 40" in context

    def test_empty_issues_no_context(self, tmp_store):
        context = tmp_store.get_related_context({}, current_sprint_id=100)
        assert context == ""


class TestIssueDocument:
    def test_document_format(self, tmp_store):
        sprint = make_sprint(id=100)
        issue = make_issue(
            key="PROJ-1",
            summary="Fix login",
            issue_type="Bug",
            priority="High",
            assignee="Alice",
            labels=["frontend"],
        )
        tmp_store.store_sprint_issues(sprint, {"Bug": [issue]})

        results = tmp_store.query_similar("login", n_results=1)
        assert len(results) == 1
        doc = results[0]["document"]
        assert "PROJ-1" in doc
        assert "Fix login" in doc
        assert "Bug" in doc

    def test_metadata_stored(self, tmp_store):
        sprint = make_sprint(id=100, name="Sprint 42")
        issue = make_issue(key="PROJ-1", priority="High", labels=["api"])
        tmp_store.store_sprint_issues(sprint, {"Story": [issue]})

        results = tmp_store.query_similar("test", n_results=1)
        meta = results[0]["metadata"]
        assert meta["issue_key"] == "PROJ-1"
        assert meta["sprint_name"] == "Sprint 42"
        assert meta["priority"] == "High"
        assert meta["labels"] == "api"
