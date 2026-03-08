"""Sprint release notes summarization engine.

This module is LLM-provider-agnostic. All LLM interactions go through
the LLMClient protocol defined in llm_client.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from models import JiraIssue
from chunker import (
    chunk_issues,
    needs_chunking,
    issues_to_text,
    build_chunk_summary_prompt,
    build_reduce_prompt,
    DEFAULT_CHUNK_TOKEN_LIMIT,
)

if TYPE_CHECKING:
    from llm_client import LLMClient


_PLURALS = {
    "Story": "Stories",
    "Bug": "Bugs",
    "Task": "Tasks",
    "Epic": "Epics",
    "Sub-task": "Sub-tasks",
    "Improvement": "Improvements",
}


def _pluralize(issue_type: str) -> str:
    """Pluralize an issue type name."""
    if issue_type in _PLURALS:
        return _PLURALS[issue_type]
    # Fallback: naive pluralization
    if issue_type.endswith("y") and len(issue_type) > 1 and issue_type[-2] not in "aeiou":
        return issue_type[:-1] + "ies"
    return issue_type + "s"


_SYSTEM_PROMPT = (
    "You are a technical writer creating executive-friendly sprint release notes. "
    "Write 2-3 concise paragraphs summarizing the work completed. "
    "Reference specific ticket keys (e.g., PROJ-123) when highlighting important items. "
    "Focus on business value and impact. Use professional, clear language. "
    "Do not use markdown formatting — write plain text paragraphs."
)


def generate_summary(
    issues_by_type: dict[str, list[JiraIssue]],
    sprint_name: str,
    llm_client: LLMClient | None = None,
    historical_context: str = "",
    chunk_token_limit: int = DEFAULT_CHUNK_TOKEN_LIMIT,
) -> str:
    """Generate an executive summary of sprint work.

    For small sprints, generates a single summary directly.
    For large sprints, uses map-reduce: summarize each chunk, then combine.
    Historical context from the vector store enriches the final summary.

    Falls back to a count-based summary if no LLM client is provided or calls fail.
    """
    if llm_client is None:
        return _fallback_summary(issues_by_type, sprint_name)

    if not needs_chunking(issues_by_type, chunk_token_limit):
        return _summarize_direct(
            llm_client, issues_by_type, sprint_name, historical_context
        )

    return _summarize_chunked(
        llm_client, issues_by_type, sprint_name,
        historical_context, chunk_token_limit
    )


def _summarize_direct(
    llm_client: LLMClient,
    issues_by_type: dict[str, list[JiraIssue]],
    sprint_name: str,
    historical_context: str = "",
) -> str:
    """Summarize a small sprint in a single LLM call."""
    issue_text = issues_to_text(issues_by_type)

    context_section = ""
    if historical_context:
        context_section = (
            f"\n\nHistorical context from previous sprints:\n{historical_context}\n"
            "Use this context to note trends, recurring themes, or continued work."
        )

    user_prompt = (
        f"Summarize the following completed work from {sprint_name}:\n"
        f"{issue_text}{context_section}"
    )

    result = llm_client.complete(_SYSTEM_PROMPT, user_prompt)
    if result:
        return result

    print("Using fallback summary.")
    return _fallback_summary(issues_by_type, sprint_name)


def _summarize_chunked(
    llm_client: LLMClient,
    issues_by_type: dict[str, list[JiraIssue]],
    sprint_name: str,
    historical_context: str = "",
    chunk_token_limit: int = DEFAULT_CHUNK_TOKEN_LIMIT,
) -> str:
    """Map-reduce summarization for large sprints.

    Map phase: Summarize each chunk independently.
    Reduce phase: Combine chunk summaries into a final cohesive summary.
    """
    chunks = chunk_issues(issues_by_type, chunk_token_limit)
    total_chunks = len(chunks)

    print(f"Large sprint detected. Splitting into {total_chunks} chunks for summarization...")

    # Map phase: summarize each chunk
    chunk_summaries = []
    for i, chunk in enumerate(chunks):
        if not any(chunk.values()):
            continue

        print(f"  Summarizing chunk {i + 1}/{total_chunks}...")
        user_prompt = build_chunk_summary_prompt(chunk, i, total_chunks, sprint_name)

        result = llm_client.complete(_SYSTEM_PROMPT, user_prompt)
        if result:
            chunk_summaries.append(result)
        else:
            # Fallback for this chunk
            chunk_total = sum(len(v) for v in chunk.values())
            types = ", ".join(f"{len(v)} {k.lower()}(s)" for k, v in sorted(chunk.items()))
            chunk_summaries.append(f"Batch {i + 1}: {chunk_total} issues — {types}.")

    if not chunk_summaries:
        return _fallback_summary(issues_by_type, sprint_name)

    if len(chunk_summaries) == 1:
        return chunk_summaries[0]

    # Reduce phase: combine chunk summaries
    print("  Combining chunk summaries...")
    reduce_prompt = build_reduce_prompt(chunk_summaries, sprint_name, historical_context)
    reduce_system = (
        "You are a technical writer. Combine the batch summaries below into a "
        "single cohesive executive summary. Write 2-3 paragraphs. "
        "Do not use markdown formatting — write plain text paragraphs."
    )

    result = llm_client.complete(reduce_system, reduce_prompt, max_tokens=600)
    if result:
        return result

    return "\n\n".join(chunk_summaries)


def _fallback_summary(
    issues_by_type: dict[str, list[JiraIssue]], sprint_name: str
) -> str:
    """Generate a simple count-based summary when LLM is unavailable."""
    total = sum(len(issues) for issues in issues_by_type.values())
    if not issues_by_type:
        return f"{sprint_name} completed 0 issues. No work items were resolved in this sprint."
    parts = [f"{len(issues)} {itype.lower()}(s)" for itype, issues in sorted(issues_by_type.items())]
    breakdown = ", ".join(parts)
    return (
        f"{sprint_name} completed {total} issues: {breakdown}. "
        f"See the detailed breakdown below for specifics on each item."
    )
