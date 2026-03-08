"""OpenAI GPT summarization for sprint release notes."""

import openai
from openai import OpenAI

from models import JiraIssue


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


def generate_summary(
    issues_by_type: dict[str, list[JiraIssue]],
    sprint_name: str,
    model: str = "gpt-4o",
    api_key: str | None = None,
) -> str:
    """Generate an executive summary of sprint work using OpenAI GPT.

    Falls back to a count-based summary if the API call fails or no key is provided.
    """
    if not api_key:
        return _fallback_summary(issues_by_type, sprint_name)

    # Build structured prompt
    issue_text = ""
    for itype, issues in sorted(issues_by_type.items()):
        issue_text += f"\n## {_pluralize(itype)}\n"
        for issue in issues:
            assignee = issue.assignee or "Unassigned"
            issue_text += f"- {issue.key}: {issue.summary} (Assignee: {assignee})\n"

    system_prompt = (
        "You are a technical writer creating executive-friendly sprint release notes. "
        "Write 2-3 concise paragraphs summarizing the work completed. "
        "Reference specific ticket keys (e.g., PROJ-123) when highlighting important items. "
        "Focus on business value and impact. Use professional, clear language. "
        "Do not use markdown formatting — write plain text paragraphs."
    )

    user_prompt = (
        f"Summarize the following completed work from {sprint_name}:\n{issue_text}"
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=500,
        )
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        return _fallback_summary(issues_by_type, sprint_name)
    except openai.OpenAIError as e:
        print(f"Warning: OpenAI API call failed ({e}). Using fallback summary.")
        return _fallback_summary(issues_by_type, sprint_name)


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
