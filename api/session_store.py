"""
In-memory registry of active interview sessions.

Each live session holds the full state needed to process the next
employee response: state machine, decision engine, and the growing
SessionData object.  Sessions are keyed by session_id.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.state_manager import StateManager
from agent.decision_engine import DecisionEngine
from storage.schema import SessionData, ResponseEntry, FollowUp


@dataclass
class LiveSession:
    """All mutable state for one in-progress interview."""

    state_mgr: StateManager
    decision_engine: DecisionEngine
    session: SessionData
    pending_question: str
    current_entry: ResponseEntry | None = None
    current_followups: list[FollowUp] = field(default_factory=list)
    hr_flagged: bool = False
    hr_flag_reason: str | None = None

    def build_conversation_history(self) -> str:
        """Reconstruct a formatted conversation string for the decision engine.

        Replaces Interviewer.get_conversation_history() for the API path.
        """
        lines: list[str] = []
        for entry in self.session.responses:
            lines.append(f"Q: {entry.question}")
            lines.append(f"A: {entry.answer}")
            for fu in entry.follow_ups:
                lines.append(f"Follow-up: {fu.question}")
                lines.append(f"A: {fu.answer}")
        if self.current_entry:
            lines.append(f"Q: {self.current_entry.question}")
            lines.append(f"A: {self.current_entry.answer}")
            for fu in self.current_followups:
                lines.append(f"Follow-up: {fu.question}")
                lines.append(f"A: {fu.answer}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level session registry
# ---------------------------------------------------------------------------
_sessions: dict[str, LiveSession] = {}


def store_session(session_id: str, live: LiveSession) -> None:
    """Register a live session."""
    _sessions[session_id] = live


def get_session(session_id: str) -> LiveSession | None:
    """Retrieve a live session by ID, or None if not found."""
    return _sessions.get(session_id)


def remove_session(session_id: str) -> None:
    """Remove a completed session from the live registry."""
    _sessions.pop(session_id, None)


def list_live_sessions() -> list[str]:
    """Return all active session IDs."""
    return list(_sessions.keys())
