"""HTML report generator for sprint release notes."""

from datetime import datetime
from html import escape as _escape

from models import ReleaseNotes


def _format_date_range(start: str | None, end: str | None) -> str:
    """Format sprint dates as 'Wed, Mar 04 → Tue, Mar 17, 2026'."""
    try:
        if start and end:
            s = datetime.fromisoformat(start.replace("Z", "+00:00"))
            e = datetime.fromisoformat(end.replace("Z", "+00:00"))
            return f"{s.strftime('%a, %b %d')} → {e.strftime('%a, %b %d, %Y')}"
    except (ValueError, TypeError):
        pass
    return ""


# Color mapping for issue types
TYPE_COLORS = {
    "Story": "#28a745",
    "Bug": "#dc3545",
    "Task": "#007bff",
    "Epic": "#6f42c1",
    "Sub-task": "#17a2b8",
    "Improvement": "#fd7e14",
}

PRIORITY_COLORS = {
    "Highest": "#dc3545",
    "High": "#fd7e14",
    "Medium": "#ffc107",
    "Low": "#28a745",
    "Lowest": "#6c757d",
}

DEFAULT_TYPE_COLOR = "#6c757d"


def _badge_color(issue_type: str) -> str:
    return TYPE_COLORS.get(issue_type, DEFAULT_TYPE_COLOR)


def _priority_color(priority: str | None) -> str:
    if not priority:
        return "#6c757d"
    return PRIORITY_COLORS.get(priority, "#6c757d")


def generate_html(release_notes: ReleaseNotes) -> str:
    """Generate a self-contained HTML report."""
    sprint = release_notes.sprint
    date_range = _format_date_range(sprint.start_date, sprint.end_date)

    # Build stats bar
    type_stats = ""
    for itype, issues in sorted(release_notes.issues_by_type.items()):
        color = _badge_color(itype)
        type_stats += (
            f'<span class="stat-badge" style="background:{color}">'
            f"{itype}: {len(issues)}</span>\n"
        )

    # Build issue tables grouped by type
    issue_sections = ""
    if not release_notes.issues_by_type:
        issue_sections = '<p class="no-issues">No completed issues in this sprint.</p>'
    else:
        for itype in sorted(release_notes.issues_by_type.keys()):
            issues = release_notes.issues_by_type[itype]
            color = _badge_color(itype)
            rows = ""
            for issue in sorted(issues, key=lambda i: i.key):
                p_color = _priority_color(issue.priority)
                assignee = issue.assignee or "Unassigned"
                priority = issue.priority or "None"
                rows += f"""                    <tr>
                        <td><code>{_escape(issue.key)}</code></td>
                        <td>{_escape(issue.summary)}</td>
                        <td>{_escape(assignee)}</td>
                        <td><span class="priority-dot" style="background:{p_color}"></span>{_escape(priority)}</td>
                    </tr>
"""
            issue_sections += f"""
        <div class="type-section">
            <h3><span class="type-badge" style="background:{color}">{_escape(itype)}</span> ({len(issues)} issue{"s" if len(issues) != 1 else ""})</h3>
            <table>
                <thead>
                    <tr><th>Key</th><th>Summary</th><th>Assignee</th><th>Priority</th></tr>
                </thead>
                <tbody>
{rows}                </tbody>
            </table>
        </div>
"""

    summary_section = ""
    if release_notes.summary:
        summary_section = f"""
        <div class="summary-section">
            <h2>Executive Summary</h2>
            <div class="summary-text">{_escape(release_notes.summary)}</div>
        </div>
"""

    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Release Notes — {_escape(sprint.name)}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                         "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 2rem 1rem;
        }}
        .container {{
            max-width: 960px;
            margin: 0 auto;
            background: #fff;
            border-radius: 8px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            padding: 2.5rem;
        }}
        header {{
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
        }}
        header h1 {{
            font-size: 1.75rem;
            color: #1a1a2e;
            margin-bottom: 0.25rem;
        }}
        header .date-range {{
            color: #6c757d;
            font-size: 1rem;
        }}
        .stats-bar {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-bottom: 2rem;
            align-items: center;
        }}
        .stats-bar .total {{
            font-weight: 600;
            font-size: 1.1rem;
            margin-right: 1rem;
            color: #1a1a2e;
        }}
        .stat-badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            color: #fff;
            font-size: 0.85rem;
            font-weight: 500;
        }}
        .summary-section {{
            background: #f8f9fa;
            border-left: 4px solid #007bff;
            padding: 1.5rem;
            border-radius: 0 6px 6px 0;
            margin-bottom: 2rem;
        }}
        .summary-section h2 {{
            font-size: 1.2rem;
            margin-bottom: 0.75rem;
            color: #1a1a2e;
        }}
        .summary-text {{
            color: #495057;
            line-height: 1.8;
        }}
        .type-section {{
            margin-bottom: 2rem;
        }}
        .type-section h3 {{
            font-size: 1.1rem;
            margin-bottom: 0.75rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .type-badge {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 4px;
            color: #fff;
            font-size: 0.85rem;
            font-weight: 500;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th {{
            text-align: left;
            padding: 0.6rem 0.75rem;
            background: #f8f9fa;
            border-bottom: 2px solid #dee2e6;
            font-size: 0.85rem;
            text-transform: uppercase;
            color: #6c757d;
            letter-spacing: 0.5px;
        }}
        td {{
            padding: 0.6rem 0.75rem;
            border-bottom: 1px solid #e9ecef;
            font-size: 0.9rem;
        }}
        tbody tr:nth-child(even) {{
            background: #f8f9fa;
        }}
        tbody tr:hover {{
            background: #e9ecef;
        }}
        td code {{
            background: #e9ecef;
            padding: 0.15rem 0.4rem;
            border-radius: 3px;
            font-size: 0.85rem;
            color: #1a1a2e;
        }}
        .priority-dot {{
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 0.4rem;
            vertical-align: middle;
        }}
        .no-issues {{
            color: #6c757d;
            font-style: italic;
            padding: 2rem;
            text-align: center;
        }}
        footer {{
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #e9ecef;
            color: #adb5bd;
            font-size: 0.8rem;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Release Notes — {_escape(sprint.name)}</h1>
            <div class="date-range">{date_range}</div>
        </header>

        <div class="stats-bar">
            <span class="total">{release_notes.total_count} issues completed</span>
            {type_stats}
        </div>
{summary_section}
{issue_sections}
        <footer>
            Generated on {now}
        </footer>
    </div>
</body>
</html>"""

    return html
