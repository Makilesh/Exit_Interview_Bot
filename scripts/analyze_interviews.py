"""
Aggregate analysis script for multiple exit interview sessions.
Reads all sessions from the outputs directory and prints a summary report.
No new LLM calls — uses only stored session data.
"""

import sys
from collections import Counter
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from storage.session import SessionStore

console = Console()


def analyze() -> None:
    """Load all sessions and print an aggregate report."""
    store = SessionStore()
    session_ids = store.list_sessions()

    if not session_ids:
        console.print("[yellow]No sessions found in the outputs directory.[/yellow]")
        return

    console.print(Panel(f"[bold]Analyzing {len(session_ids)} interview session(s)[/bold]"))

    exit_reasons: Counter[str] = Counter()
    sentiments: Counter[str] = Counter()
    improvement_areas: Counter[str] = Counter()
    hr_flagged_count = 0
    total_sessions = 0

    for sid in session_ids:
        try:
            session = store.load(sid)
            total_sessions += 1
        except Exception as e:
            console.print(f"[red]Failed to load session {sid}: {e}[/red]")
            continue

        if session.summary:
            s = session.summary
            exit_reasons[s.primary_exit_reason] += 1
            sentiments[s.sentiment] += 1
            for area in s.improvement_areas:
                improvement_areas[area] += 1
            if s.flag_for_hr:
                hr_flagged_count += 1

    # --- Exit Reasons ---
    console.print("\n[bold underline]Most Common Exit Reasons[/bold underline]")
    reason_table = Table(show_header=True)
    reason_table.add_column("Rank", style="bold", width=6)
    reason_table.add_column("Exit Reason")
    reason_table.add_column("Count", justify="right")

    for rank, (reason, count) in enumerate(exit_reasons.most_common(), 1):
        reason_table.add_row(str(rank), reason, str(count))

    console.print(reason_table)

    # --- Sentiment Distribution ---
    console.print("\n[bold underline]Sentiment Distribution[/bold underline]")
    sentiment_table = Table(show_header=True)
    sentiment_table.add_column("Sentiment", style="bold")
    sentiment_table.add_column("Count", justify="right")

    for sentiment_label in ["positive", "neutral", "negative"]:
        sentiment_table.add_row(sentiment_label, str(sentiments.get(sentiment_label, 0)))

    console.print(sentiment_table)

    # --- Improvement Areas ---
    console.print("\n[bold underline]Most Common Improvement Areas[/bold underline]")
    improvement_table = Table(show_header=True)
    improvement_table.add_column("Rank", style="bold", width=6)
    improvement_table.add_column("Improvement Area")
    improvement_table.add_column("Count", justify="right")

    for rank, (area, count) in enumerate(improvement_areas.most_common(), 1):
        improvement_table.add_row(str(rank), area, str(count))

    console.print(improvement_table)

    # --- HR Flags ---
    console.print(
        f"\n[bold underline]HR-Flagged Sessions:[/bold underline] "
        f"[bold red]{hr_flagged_count}[/bold red] out of {total_sessions}"
    )
    console.print()


if __name__ == "__main__":
    analyze()
