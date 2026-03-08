"""CLI entry point for Jira Sprint Release Notes Agent."""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from jira_client import JiraClient, JiraClientError
from html_generator import _format_date_range
from models import ReleaseNotes, SprintInfo
from summarizer import generate_summary
from html_generator import generate_html


def load_config(config_path: Path | None = None) -> dict:
    """Load and validate config.yaml."""
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        print("Error: config.yaml not found.")
        print("Copy config.yaml.example to config.yaml and fill in your Jira details.")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    jira = (config or {}).get("jira", {})
    if not jira.get("url"):
        print("Error: config.yaml missing required field 'jira.url'")
        sys.exit(1)

    return config


def format_sprint_date_range(sprint: SprintInfo) -> str:
    """Format sprint dates for CLI display."""
    return _format_date_range(sprint.start_date, sprint.end_date)


def select_sprint_interactive(
    client: JiraClient, board_id: int, board_name: str
) -> SprintInfo:
    """Interactive sprint selection: auto-detect or list for user to pick."""
    sprints = client.get_sprints(board_id, states="closed,active")
    if not sprints:
        print(f"No sprints found for board '{board_name}'.")
        sys.exit(1)

    # Sort by id descending (most recent first)
    sprints.sort(key=lambda s: s.id, reverse=True)

    # Auto-detect: pick the most recent active sprint, or latest closed
    auto = next((s for s in sprints if s.state == "active"), sprints[0])
    date_range = format_sprint_date_range(auto)
    date_str = f" ({date_range})" if date_range else ""

    print(f"\nAuto-detected current sprint: {auto.name}{date_str}")
    choice = input("Press Enter to confirm, or type 'list' to see all sprints: ").strip()

    if choice.lower() != "list":
        return auto

    # Show numbered list
    print(f'\nAvailable sprints for board "{board_name}":')
    display = sprints[:20]  # Show most recent 20
    for i, s in enumerate(display, 1):
        dr = format_sprint_date_range(s)
        dr_str = f"  - {dr}" if dr else ""
        print(f"  [{i}] {s.name} ({s.state}){dr_str}")

    while True:
        pick = input("\nSelect sprint number: ").strip()
        try:
            idx = int(pick) - 1
            if 0 <= idx < len(display):
                return display[idx]
        except ValueError:
            pass
        print(f"Please enter a number between 1 and {len(display)}.")


def main():
    parser = argparse.ArgumentParser(
        description="Generate sprint release notes from Jira"
    )
    parser.add_argument("--board", help="Jira board name (overrides config default)")
    parser.add_argument("--sprint", help="Sprint name (e.g., 'Sprint 42')")
    parser.add_argument(
        "--latest", action="store_true",
        help="Auto-select the latest active/closed sprint (non-interactive)"
    )
    args = parser.parse_args()

    # Load secrets first, then config
    load_dotenv()
    config = load_config()

    # Jira credentials from .env
    jira_email = os.getenv("JIRA_EMAIL")
    jira_token = os.getenv("JIRA_API_TOKEN")
    if not jira_email or not jira_token:
        print("Error: JIRA_EMAIL and JIRA_API_TOKEN must be set in .env file.")
        print("Copy .env.example to .env and add your Jira credentials.")
        sys.exit(1)

    # OpenAI key is optional — fallback summary will be used if missing
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("Warning: OPENAI_API_KEY not set. Will use fallback summary (no LLM).")

    jira_conf = config["jira"]
    board_name = args.board or jira_conf.get("default_board")
    if not board_name:
        print("Error: No board specified. Use --board or set 'jira.default_board' in config.yaml.")
        sys.exit(1)

    openai_model = config.get("openai", {}).get("model", "gpt-4o")

    # Connect to Jira
    with JiraClient(jira_conf["url"], jira_email, jira_token) as client:
        print(f"Looking up board: {board_name}...")
        try:
            board = client.find_board(board_name)
        except JiraClientError as e:
            print(f"Error: {e}")
            sys.exit(1)

        board_id = board["id"]
        print(f"Found board: {board['name']} (id={board_id})")

        # Select sprint
        if args.sprint:
            sprint = client.find_sprint_by_name(board_id, args.sprint)
            if not sprint:
                print(f"Sprint '{args.sprint}' not found on board '{board_name}'.")
                print("Available sprints:")
                for s in client.get_sprints(board_id)[-10:]:
                    print(f"  - {s.name} ({s.state})")
                sys.exit(1)
        elif args.latest:
            sprints = client.get_sprints(board_id, states="closed,active")
            if not sprints:
                print(f"No sprints found for board '{board_name}'.")
                sys.exit(1)
            sprints.sort(key=lambda s: s.id, reverse=True)
            sprint = next((s for s in sprints if s.state == "active"), sprints[0])
        else:
            sprint = select_sprint_interactive(client, board_id, board_name)

        date_range = format_sprint_date_range(sprint)
        print(f"\nGenerating release notes for: {sprint.name}")
        if date_range:
            print(f"Date range: {date_range}")

        # Fetch completed issues
        print("Fetching completed issues...")
        issues_by_type = client.get_completed_issues(sprint.id)
        total = sum(len(v) for v in issues_by_type.values())
        print(f"Found {total} completed issues.")

    # Generate LLM summary
    print("Generating executive summary...")
    summary = generate_summary(issues_by_type, sprint.name, openai_model, openai_key)

    # Build release notes
    release_notes = ReleaseNotes(
        sprint=sprint,
        issues_by_type=issues_by_type,
        total_count=total,
        summary=summary,
    )

    # Generate HTML
    html = generate_html(release_notes)

    # Write output
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[^a-z0-9_-]', '', sprint.name.lower().replace(' ', '_'))
    output_path = output_dir / f"release_notes_{safe_name}_{timestamp}.html"
    output_path.write_text(html)

    print(f"\nRelease notes saved to: {output_path}")


if __name__ == "__main__":
    main()
