"""
Pydantic request/response schemas for the API layer.
"""

from pydantic import BaseModel

from storage.schema import SummaryOutput


class SessionStartRequest(BaseModel):
    """Request body for starting a new interview session."""

    # Phase 2: "voice_text" | "text_voice" | "voice_voice"
    mode: str = "text_text"


class SessionStartResponse(BaseModel):
    """Response after creating a new session."""

    session_id: str
    first_question: str
    question_number: int
    total_questions: int


class RespondRequest(BaseModel):
    """Request body for submitting an employee answer."""

    answer: str


class RespondResponse(BaseModel):
    """Response after processing an employee answer."""

    next_question: str | None
    is_complete: bool
    follow_up: bool
    question_number: int
    total_questions: int
    agent_decision: dict
    detected_topics: list[str]
    summary: SummaryOutput | None = None


class SessionListItem(BaseModel):
    """Summary of a completed session for the session list."""

    session_id: str
    timestamp: str
