"""Text chunking for context management when interacting with LLMs.

Splits large sets of Jira issues into token-bounded chunks, enabling
map-reduce summarization for sprints that exceed model context limits.
"""

from models import JiraIssue


# Average tokens per character (conservative estimate for English text)
_CHARS_PER_TOKEN = 4

# Default token budget per chunk (leaves room for system prompt + response)
DEFAULT_CHUNK_TOKEN_LIMIT = 3000

# Max tokens for the combined reduce step
DEFAULT_REDUCE_TOKEN_LIMIT = 4000


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length.

    Uses a conservative character-to-token ratio. For more precise counting,
    tiktoken can be used, but this avoids the dependency for most use cases.
    """
    return max(1, len(text) // _CHARS_PER_TOKEN)


def issue_to_text(issue: JiraIssue) -> str:
    """Convert a single JiraIssue to a text line for the LLM prompt."""
    assignee = issue.assignee or "Unassigned"
    parts = [f"- {issue.key}: {issue.summary} (Assignee: {assignee})"]
    if issue.priority:
        parts[0] += f" [Priority: {issue.priority}]"
    if issue.labels:
        parts[0] += f" [Labels: {', '.join(issue.labels)}]"
    return parts[0]


def issues_to_text(issues_by_type: dict[str, list[JiraIssue]]) -> str:
    """Convert all issues into structured text for the LLM prompt."""
    from summarizer import _pluralize

    text = ""
    for itype in sorted(issues_by_type.keys()):
        issues = issues_by_type[itype]
        text += f"\n## {_pluralize(itype)}\n"
        for issue in issues:
            text += issue_to_text(issue) + "\n"
    return text


def chunk_issues(
    issues_by_type: dict[str, list[JiraIssue]],
    token_limit: int = DEFAULT_CHUNK_TOKEN_LIMIT,
) -> list[dict[str, list[JiraIssue]]]:
    """Split issues into chunks that fit within a token budget.

    Each chunk is a dict[str, list[JiraIssue]] (same format as issues_by_type),
    making it directly usable with existing prompt-building functions.

    Chunking strategy:
    1. First tries to keep issue types together (natural grouping).
    2. If a single type exceeds the limit, splits that type across chunks.
    """
    chunks: list[dict[str, list[JiraIssue]]] = []
    current_chunk: dict[str, list[JiraIssue]] = {}
    current_tokens = 0

    for itype in sorted(issues_by_type.keys()):
        issues = issues_by_type[itype]

        # Estimate tokens for this entire type group
        type_text = f"\n## {itype}\n"
        type_header_tokens = estimate_tokens(type_text)

        for issue in issues:
            issue_text = issue_to_text(issue) + "\n"
            issue_tokens = estimate_tokens(issue_text)

            # Check if adding this issue would exceed the limit
            needed = issue_tokens
            if itype not in current_chunk:
                needed += type_header_tokens

            if current_tokens + needed > token_limit and current_chunk:
                # Flush current chunk and start a new one
                chunks.append(current_chunk)
                current_chunk = {}
                current_tokens = 0

            # Add issue to current chunk
            if itype not in current_chunk:
                current_chunk[itype] = []
                current_tokens += type_header_tokens

            current_chunk[itype].append(issue)
            current_tokens += issue_tokens

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)

    return chunks if chunks else [{}]


def needs_chunking(
    issues_by_type: dict[str, list[JiraIssue]],
    token_limit: int = DEFAULT_CHUNK_TOKEN_LIMIT,
) -> bool:
    """Check if the issue set needs chunking to fit within token limits."""
    text = issues_to_text(issues_by_type)
    return estimate_tokens(text) > token_limit


def build_chunk_summary_prompt(
    chunk: dict[str, list[JiraIssue]],
    chunk_index: int,
    total_chunks: int,
    sprint_name: str,
) -> str:
    """Build a prompt for summarizing a single chunk of issues."""
    chunk_text = issues_to_text(chunk)
    total_in_chunk = sum(len(v) for v in chunk.values())
    return (
        f"This is part {chunk_index + 1} of {total_chunks} from {sprint_name}. "
        f"This batch contains {total_in_chunk} issues.\n"
        f"Summarize the key work completed in this batch in 1-2 concise paragraphs. "
        f"Reference specific ticket keys when highlighting important items.\n"
        f"{chunk_text}"
    )


def build_reduce_prompt(
    chunk_summaries: list[str],
    sprint_name: str,
    historical_context: str = "",
) -> str:
    """Build a prompt to combine chunk summaries into a final summary.

    This is the 'reduce' step of map-reduce summarization.
    """
    combined = "\n\n---\n\n".join(
        f"Batch {i + 1} summary:\n{s}" for i, s in enumerate(chunk_summaries)
    )

    context_section = ""
    if historical_context:
        context_section = (
            f"\n\nHistorical context from previous sprints:\n{historical_context}\n"
        )

    return (
        f"Below are summaries of different batches of work completed in {sprint_name}. "
        f"Combine them into a single cohesive executive summary of 2-3 paragraphs. "
        f"Focus on business value and impact. Use professional, clear language. "
        f"Reference specific ticket keys (e.g., PROJ-123) when highlighting important items. "
        f"Do not use markdown formatting — write plain text paragraphs."
        f"{context_section}\n\n{combined}"
    )
