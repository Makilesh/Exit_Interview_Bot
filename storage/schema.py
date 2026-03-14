"""
All Pydantic v2 models.
This is the single source of truth for data structure.
"""

from pydantic import BaseModel


class FollowUp(BaseModel):
    """A follow-up question and answer pair."""

    question: str
    answer: str


class ResponseEntry(BaseModel):
    """A single interview question-answer exchange with analysis metadata."""

    question: str
    answer: str
    reason_tags: list[str]
    sentiment: str
    follow_ups: list[FollowUp]


class AgentDecisionEntry(BaseModel):
    """A logged decision made by the decision engine."""

    response: str
    decision: str
    reason: str


class SummaryOutput(BaseModel):
    """Final summary generated after the interview is complete."""

    primary_exit_reason: str
    sentiment: str
    confidence_score: float
    top_positives: list[str]
    improvement_areas: list[str]
    flag_for_hr: bool
    flag_reason: str | None


class SessionData(BaseModel):
    """Complete session data for an exit interview."""

    session_id: str
    timestamp: str
    responses: list[ResponseEntry]
    detected_topics: list[str]
    agent_decision_log: list[AgentDecisionEntry]
    conversation_length: int
    followup_count: int
    summary: SummaryOutput | None
