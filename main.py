"""
Main entry point for the Agentic AI Exit Interview System.
Orchestrates the full interview loop using a state machine.
"""

import argparse
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import OUTPUT_DIR
from agent.interviewer import Interviewer
from agent.decision_engine import DecisionEngine
from agent.state_manager import StateManager, InterviewState
from agent.summarizer import Summarizer
from agent.questions import QUESTION_BANK, FOLLOWUP_VARIANTS
from agent.tools import classify_sentiment_and_reason, detect_hr_flags
from storage.schema import SessionData, ResponseEntry, FollowUp
from storage.session import SessionStore

console = Console()


def run_interview(demo_mode: bool = False) -> None:
    """Run the complete exit interview flow.

    Args:
        demo_mode: If True, use pre-scripted employee responses.
    """
    load_dotenv()

    # Initialize components
    state_mgr = StateManager()
    decision_engine = DecisionEngine()
    interviewer = Interviewer(demo_mode=demo_mode)
    summarizer = Summarizer()
    store = SessionStore(output_dir=OUTPUT_DIR)

    # Create session
    session = SessionData(
        session_id=str(uuid.uuid4())[:8],
        timestamp=datetime.now(timezone.utc).isoformat(),
        responses=[],
        detected_topics=[],
        agent_decision_log=[],
        conversation_length=0,
        followup_count=0,
        summary=None,
    )

    # Current response entry being built
    current_entry: ResponseEntry | None = None
    current_followups: list[FollowUp] = []
    hr_flagged = False
    hr_flag_reason: str | None = None

    # --- State machine loop ---
    running = True
    while running:
        match state_mgr.current_state:
            case InterviewState.INTERVIEW_START:
                console.print(
                    Panel(
                        "[bold green]Welcome to the Exit Interview[/bold green]\n\n"
                        "Thank you for taking the time to share your feedback. "
                        "Your responses will help us improve the workplace for everyone.",
                        title="Exit Interview System",
                    )
                )
                state_mgr.transition("start")

            case InterviewState.ASK_QUESTION:
                idx = state_mgr.current_question_index
                if idx >= len(QUESTION_BANK):
                    state_mgr.transition("response_received")
                    # We need to handle this — skip to EVALUATE which will route to NEXT_QUESTION
                    continue

                question = QUESTION_BANK[idx]
                console.print(f"\n[bold cyan]Question {idx + 1}/{len(QUESTION_BANK)}:[/bold cyan]")

                response = interviewer.ask(question)
                state_mgr.increment_turn()

                if demo_mode:
                    console.print(f"[dim]Employee: {response}[/dim]")

                # Initialize response entry
                current_followups = []
                current_entry = ResponseEntry(
                    question=question,
                    answer=response,
                    reason_tags=[],
                    sentiment="neutral",
                    follow_ups=[],
                )

                state_mgr.transition("response_received")

            case InterviewState.EVALUATE_RESPONSE:
                if current_entry is None:
                    state_mgr.transition("next_question")
                    continue

                # Get the latest response to evaluate
                latest_response = current_entry.answer
                if current_followups:
                    latest_response = current_followups[-1].answer

                # Run decision engine
                conversation_history = interviewer.get_conversation_history()
                decision_data, decision_entry = decision_engine.evaluate(
                    response=latest_response,
                    question=current_entry.question,
                    conversation_history=conversation_history,
                )
                session.agent_decision_log.append(decision_entry)

                # Run classification tool
                try:
                    classification = classify_sentiment_and_reason.invoke(
                        {"response": latest_response}
                    )
                    if isinstance(classification, dict):
                        current_entry.reason_tags = list(
                            set(current_entry.reason_tags + classification.get("reason_tags", []))
                        )
                        current_entry.sentiment = classification.get("sentiment", "neutral")
                except Exception as e:
                    console.print(f"[yellow]Classification warning: {e}[/yellow]")

                # Run HR flag detection
                try:
                    hr_result = detect_hr_flags.invoke({"response": latest_response})
                    if isinstance(hr_result, dict) and hr_result.get("flag"):
                        hr_flagged = True
                        hr_flag_reason = hr_result.get("reason")
                        console.print("[bold red]⚠ HR flag detected[/bold red]")
                except Exception as e:
                    console.print(f"[yellow]HR flag detection warning: {e}[/yellow]")

                # Log decision
                decision = decision_data.get("decision", "next_question")
                reason = decision_data.get("reason", "unknown")
                console.print(
                    f"[dim]Agent decision: {decision} (reason: {reason})[/dim]"
                )

                # Decide next state
                if decision == "ask_followup" and state_mgr.can_followup():
                    state_mgr.transition("followup_needed")
                else:
                    # Finalize current entry
                    current_entry.follow_ups = current_followups
                    session.responses.append(current_entry)
                    session.conversation_length = state_mgr.total_turns
                    session.followup_count += len(current_followups)
                    current_entry = None
                    state_mgr.transition("next_question")

            case InterviewState.ASK_FOLLOWUP:
                idx = state_mgr.current_question_index
                fu_idx = state_mgr.current_followup_count

                # Get follow-up question
                variants = FOLLOWUP_VARIANTS.get(idx, [])
                if fu_idx < len(variants):
                    followup_q = variants[fu_idx]
                else:
                    followup_q = "Could you elaborate on that?"

                console.print(f"[bold yellow]Follow-up:[/bold yellow]")
                fu_response = interviewer.ask(followup_q)
                state_mgr.increment_turn()
                state_mgr.increment_followup()

                if demo_mode:
                    console.print(f"[dim]Employee: {fu_response}[/dim]")

                current_followups.append(FollowUp(question=followup_q, answer=fu_response))

                state_mgr.transition("followup_done")

            case InterviewState.NEXT_QUESTION:
                state_mgr.advance_question()

                if state_mgr.should_terminate():
                    state_mgr.transition("all_questions_done")
                else:
                    state_mgr.transition("next_question")

            case InterviewState.INTERVIEW_COMPLETE:
                console.print(
                    Panel(
                        "[bold green]Thank you for completing the exit interview.[/bold green]\n\n"
                        "Your feedback is valuable and will be used to improve our workplace. "
                        "We wish you all the best in your future endeavors.",
                        title="Interview Complete",
                    )
                )

                # Update detected topics from decision engine
                session.detected_topics = decision_engine.topic_memory
                session.conversation_length = state_mgr.total_turns

                state_mgr.transition("summary_done")

            case InterviewState.GENERATE_SUMMARY:
                console.print("\n[bold]Generating interview summary...[/bold]")

                try:
                    summary = summarizer.generate(session)

                    # Override HR flag if detected during the interview
                    if hr_flagged and not summary.flag_for_hr:
                        summary.flag_for_hr = True
                        summary.flag_reason = hr_flag_reason

                    session.summary = summary

                    # Save all outputs
                    store.save(session)
                    store.export_transcript(session)
                    store.export_summary_md(session)

                    # Print completion summary
                    _print_summary(session)

                except Exception as e:
                    console.print(f"[bold red]Summary generation failed: {e}[/bold red]")
                    # Save session even without summary
                    store.save(session)
                    store.export_transcript(session)

                running = False


def _print_summary(session: SessionData) -> None:
    """Print a brief completion summary to stdout using rich.

    Args:
        session: The completed session with summary attached.
    """
    s = session.summary
    if s is None:
        return

    table = Table(title="Interview Summary", show_header=False, border_style="green")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Session ID", session.session_id)
    table.add_row("Primary Exit Reason", s.primary_exit_reason)
    table.add_row("Sentiment", s.sentiment)
    table.add_row("Confidence Score", f"{s.confidence_score:.2f}")
    table.add_row("Questions Asked", str(len(session.responses)))
    table.add_row("Total Turns", str(session.conversation_length))
    table.add_row("Follow-ups", str(session.followup_count))
    table.add_row("Detected Topics", ", ".join(session.detected_topics) or "None")
    table.add_row(
        "HR Flag",
        f"[bold red]YES — {s.flag_reason}[/bold red]" if s.flag_for_hr else "[green]No[/green]",
    )

    console.print()
    console.print(table)
    console.print(f"\n[dim]Outputs saved to {OUTPUT_DIR}/[/dim]")


def main() -> None:
    """Parse CLI arguments and launch the interview."""
    parser = argparse.ArgumentParser(description="Agentic AI Exit Interview System")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode with pre-scripted responses",
    )
    args = parser.parse_args()
    run_interview(demo_mode=args.demo)


if __name__ == "__main__":
    main()
