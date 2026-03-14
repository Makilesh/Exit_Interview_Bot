"""
State machine for the exit interview flow.
"""

from enum import Enum

from config import MAX_TURNS, MAX_FOLLOWUPS_PER_QUESTION
from agent.questions import QUESTION_BANK


class InterviewState(Enum):
    """States the interview can be in."""

    INTERVIEW_START = "INTERVIEW_START"
    ASK_QUESTION = "ASK_QUESTION"
    EVALUATE_RESPONSE = "EVALUATE_RESPONSE"
    ASK_FOLLOWUP = "ASK_FOLLOWUP"
    NEXT_QUESTION = "NEXT_QUESTION"
    INTERVIEW_COMPLETE = "INTERVIEW_COMPLETE"
    GENERATE_SUMMARY = "GENERATE_SUMMARY"


# Valid state transitions keyed by (current_state, event)
_TRANSITIONS: dict[tuple[InterviewState, str], InterviewState] = {
    (InterviewState.INTERVIEW_START, "start"): InterviewState.ASK_QUESTION,
    (InterviewState.ASK_QUESTION, "response_received"): InterviewState.EVALUATE_RESPONSE,
    (InterviewState.EVALUATE_RESPONSE, "followup_needed"): InterviewState.ASK_FOLLOWUP,
    (InterviewState.EVALUATE_RESPONSE, "next_question"): InterviewState.NEXT_QUESTION,
    (InterviewState.ASK_FOLLOWUP, "followup_done"): InterviewState.EVALUATE_RESPONSE,
    (InterviewState.NEXT_QUESTION, "next_question"): InterviewState.ASK_QUESTION,
    (InterviewState.NEXT_QUESTION, "all_questions_done"): InterviewState.INTERVIEW_COMPLETE,
    (InterviewState.INTERVIEW_COMPLETE, "generate_summary"): InterviewState.GENERATE_SUMMARY,
}


class StateManager:
    """Manages interview state transitions and termination conditions."""

    def __init__(self) -> None:
        """Initialize the state manager at INTERVIEW_START."""
        self.current_state: InterviewState = InterviewState.INTERVIEW_START
        self.current_question_index: int = 0
        self.current_followup_count: int = 0
        self.total_turns: int = 0

    def transition(self, event: str) -> None:
        """Move to the next state based on the given event.

        Args:
            event: One of 'start', 'response_received', 'followup_needed',
                   'followup_done', 'next_question', 'all_questions_done',
                   'summary_done'.

        Raises:
            ValueError: If the transition is invalid from the current state.
        """
        key = (self.current_state, event)
        if key not in _TRANSITIONS:
            raise ValueError(
                f"Invalid transition: event '{event}' from state '{self.current_state.value}'"
            )
        self.current_state = _TRANSITIONS[key]

    def should_terminate(self) -> bool:
        """Check if the interview should end.

        Returns:
            True if any termination condition is met.
        """
        all_questions_asked = self.current_question_index >= len(QUESTION_BANK)
        max_turns_reached = self.total_turns >= MAX_TURNS
        return all_questions_asked or max_turns_reached

    def advance_question(self) -> None:
        """Move to the next primary question and reset follow-up counter."""
        self.current_question_index += 1
        self.current_followup_count = 0

    def increment_followup(self) -> None:
        """Increment the follow-up count for the current question."""
        self.current_followup_count += 1

    def increment_turn(self) -> None:
        """Increment the total turn counter."""
        self.total_turns += 1

    def can_followup(self) -> bool:
        """Check whether another follow-up is allowed for the current question.

        Returns:
            True if the follow-up limit has not been reached.
        """
        return self.current_followup_count < MAX_FOLLOWUPS_PER_QUESTION
