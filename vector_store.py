"""Vector database for Jira issue memory management using ChromaDB."""

import hashlib
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

from models import JiraIssue, SprintInfo


DEFAULT_DB_PATH = str(Path(__file__).parent / "data" / "vectordb")


class VectorStore:
    """Persistent vector store for Jira issues using ChromaDB.

    Stores issue embeddings to enable:
    - Cross-sprint memory (recall similar past issues)
    - Historical context enrichment for summaries
    - Deduplication detection across sprints
    """

    def __init__(self, persist_dir: str = DEFAULT_DB_PATH):
        self.persist_dir = persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name="jira_issues",
            metadata={"hnsw:space": "cosine"},
        )

    def _issue_id(self, issue: JiraIssue, sprint_id: int) -> str:
        """Deterministic ID for an issue within a sprint."""
        return f"{sprint_id}_{issue.key}"

    def _issue_to_document(self, issue: JiraIssue) -> str:
        """Convert a JiraIssue to a text document for embedding."""
        parts = [
            f"[{issue.issue_type}] {issue.key}: {issue.summary}",
            f"Status: {issue.status}",
        ]
        if issue.assignee:
            parts.append(f"Assignee: {issue.assignee}")
        if issue.priority:
            parts.append(f"Priority: {issue.priority}")
        if issue.labels:
            parts.append(f"Labels: {', '.join(issue.labels)}")
        if issue.resolution:
            parts.append(f"Resolution: {issue.resolution}")
        return " | ".join(parts)

    def _issue_metadata(self, issue: JiraIssue, sprint: SprintInfo) -> dict:
        """Build metadata dict for ChromaDB storage."""
        return {
            "issue_key": issue.key,
            "issue_type": issue.issue_type,
            "status": issue.status,
            "assignee": issue.assignee or "",
            "priority": issue.priority or "",
            "sprint_id": sprint.id,
            "sprint_name": sprint.name,
            "sprint_state": sprint.state,
            "labels": ",".join(issue.labels) if issue.labels else "",
            "resolution": issue.resolution or "",
            "created": issue.created or "",
            "resolved": issue.resolved or "",
        }

    def store_sprint_issues(
        self,
        sprint: SprintInfo,
        issues_by_type: dict[str, list[JiraIssue]],
    ) -> int:
        """Store all issues from a sprint into the vector database.

        Returns the number of issues stored.
        """
        documents = []
        metadatas = []
        ids = []

        for issues in issues_by_type.values():
            for issue in issues:
                doc_id = self._issue_id(issue, sprint.id)
                documents.append(self._issue_to_document(issue))
                metadatas.append(self._issue_metadata(issue, sprint))
                ids.append(doc_id)

        if not documents:
            return 0

        self.collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        return len(documents)

    def query_similar(
        self,
        query_text: str,
        n_results: int = 10,
        exclude_sprint_id: Optional[int] = None,
    ) -> list[dict]:
        """Find similar issues from the vector store.

        Args:
            query_text: Text to search for similar issues.
            n_results: Maximum number of results.
            exclude_sprint_id: Sprint ID to exclude (e.g., the current sprint).

        Returns:
            List of dicts with 'document', 'metadata', and 'distance' keys.
        """
        where_filter = None
        if exclude_sprint_id is not None:
            where_filter = {"sprint_id": {"$ne": exclude_sprint_id}}

        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where_filter,
            )
        except Exception:
            # If filtering fails (e.g., no documents match), query without filter
            try:
                results = self.collection.query(
                    query_texts=[query_text],
                    n_results=n_results,
                )
            except Exception:
                return []

        items = []
        if results and results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                items.append({
                    "document": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 1.0,
                })
        return items

    def get_sprint_history(self, limit: int = 5) -> list[dict]:
        """Get a summary of stored sprints for historical context.

        Returns a list of sprint summaries with issue counts, sorted by
        most recent first.
        """
        try:
            all_items = self.collection.get(include=["metadatas"])
        except Exception:
            return []

        if not all_items or not all_items["metadatas"]:
            return []

        # Aggregate by sprint
        sprints: dict[int, dict] = {}
        for meta in all_items["metadatas"]:
            sid = meta.get("sprint_id")
            if sid is None:
                continue
            if sid not in sprints:
                sprints[sid] = {
                    "sprint_id": sid,
                    "sprint_name": meta.get("sprint_name", ""),
                    "issue_count": 0,
                    "types": {},
                }
            sprints[sid]["issue_count"] += 1
            itype = meta.get("issue_type", "Unknown")
            sprints[sid]["types"][itype] = sprints[sid]["types"].get(itype, 0) + 1

        # Sort by sprint_id descending (most recent first)
        history = sorted(sprints.values(), key=lambda s: s["sprint_id"], reverse=True)
        return history[:limit]

    def get_related_context(
        self,
        issues_by_type: dict[str, list[JiraIssue]],
        current_sprint_id: int,
        max_results: int = 10,
    ) -> str:
        """Build a historical context string from similar past issues.

        Queries the vector store for issues similar to the current sprint's
        work, excluding the current sprint itself.
        """
        # Build a combined query from current sprint issue summaries
        summaries = []
        for issues in issues_by_type.values():
            for issue in issues[:5]:  # Sample up to 5 per type
                summaries.append(f"{issue.issue_type}: {issue.summary}")

        if not summaries:
            return ""

        query = " | ".join(summaries)
        similar = self.query_similar(
            query, n_results=max_results, exclude_sprint_id=current_sprint_id
        )

        if not similar:
            return ""

        # Build context string
        lines = ["Related work from previous sprints:"]
        seen_sprints = set()
        for item in similar:
            meta = item["metadata"]
            sprint_name = meta.get("sprint_name", "Unknown Sprint")
            seen_sprints.add(sprint_name)
            lines.append(
                f"- [{meta.get('issue_key', '?')}] {item['document']} "
                f"(from {sprint_name})"
            )

        return "\n".join(lines)

    def count(self) -> int:
        """Return the total number of stored issues."""
        return self.collection.count()

    def clear(self) -> None:
        """Delete all stored issues."""
        self.client.delete_collection("jira_issues")
        self.collection = self.client.get_or_create_collection(
            name="jira_issues",
            metadata={"hnsw:space": "cosine"},
        )
