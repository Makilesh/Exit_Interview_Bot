"""
Session persistence layer.
Handles saving, loading, and exporting interview sessions.
"""

import json
import os
from pathlib import Path

from storage.schema import SessionData
from config import OUTPUT_DIR


class SessionStore:
    """Handles persistence of interview session data."""

    def __init__(self, output_dir: str = OUTPUT_DIR):
        """Initialize the session store.

        Args:
            output_dir: Directory path for storing session files.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, session: SessionData) -> None:
        """Write session data to a JSON file.

        Args:
            session: Validated SessionData to persist.
        """
        path = self.output_dir / f"session_{session.session_id}.json"
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    def load(self, session_id: str) -> SessionData:
        """Read and parse a session from JSON.

        Args:
            session_id: The unique session identifier.

        Returns:
            Parsed SessionData object.
        """
        path = self.output_dir / f"session_{session_id}.json"
        raw = path.read_text(encoding="utf-8")
        return SessionData.model_validate_json(raw)

    def export_transcript(self, session: SessionData) -> None:
        """Write a clean human-readable Q&A transcript.

        Args:
            session: The session to export.
        """
        path = self.output_dir / f"session_{session.session_id}_transcript.txt"
        lines: list[str] = []
        lines.append(f"Exit Interview Transcript — Session {session.session_id}")
        lines.append(f"Date: {session.timestamp}")
        lines.append("=" * 60)
        lines.append("")

        for i, entry in enumerate(session.responses, 1):
            lines.append(f"Q{i}: {entry.question}")
            lines.append(f"A{i}: {entry.answer}")
            lines.append(f"    Sentiment: {entry.sentiment}")
            lines.append(f"    Tags: {', '.join(entry.reason_tags)}")
            for j, fu in enumerate(entry.follow_ups, 1):
                lines.append(f"  Follow-up {j}: {fu.question}")
                lines.append(f"  Response {j}: {fu.answer}")
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")

    def export_summary_md(self, session: SessionData) -> None:
        """Write a formatted Markdown summary report.

        Args:
            session: The session to export (must have a summary attached).
        """
        if session.summary is None:
            return

        s = session.summary
        path = self.output_dir / f"session_{session.session_id}_summary.md"
        lines: list[str] = []
        lines.append(f"# Exit Interview Summary — Session {session.session_id}")
        lines.append("")
        lines.append(f"**Date:** {session.timestamp}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Primary Exit Reason")
        lines.append("")
        lines.append(s.primary_exit_reason)
        lines.append("")
        lines.append("## Overall Sentiment")
        lines.append("")
        lines.append(s.sentiment)
        lines.append("")
        lines.append("## Confidence Score")
        lines.append("")
        lines.append(f"{s.confidence_score:.2f}")
        lines.append("")
        lines.append("## Top Positives")
        lines.append("")
        for item in s.top_positives:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## Improvement Areas")
        lines.append("")
        for item in s.improvement_areas:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## HR Flag Status")
        lines.append("")
        lines.append(f"**Flagged:** {'Yes' if s.flag_for_hr else 'No'}")
        if s.flag_reason:
            lines.append(f"**Reason:** {s.flag_reason}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Detected Topics")
        lines.append("")
        for topic in session.detected_topics:
            lines.append(f"- {topic}")
        lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")

    def list_sessions(self) -> list[str]:
        """Return all session IDs found in the outputs directory.

        Returns:
            List of session ID strings.
        """
        ids: list[str] = []
        for f in self.output_dir.glob("session_*.json"):
            name = f.stem  # e.g. "session_abc123"
            session_id = name.replace("session_", "", 1)
            ids.append(session_id)
        return ids
