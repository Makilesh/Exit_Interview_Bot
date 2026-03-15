"""
Summarizer — generates a final summary of the exit interview.
"""

from config import SUMMARY_MODEL, TEMPERATURE
from storage.schema import SessionData, SummaryOutput
from utils.llm import invoke_llm_json


class Summarizer:
    """Generates a structured summary from complete interview session data."""

    def __init__(self) -> None:
        """Initialize the summarizer."""
        pass

    def _format_transcript(self, session: SessionData) -> str:
        """Format the session responses as a readable Q&A transcript.

        Args:
            session: The complete session data.

        Returns:
            A formatted string of the conversation.
        """
        lines: list[str] = []
        for i, entry in enumerate(session.responses, 1):
            lines.append(f"Q{i}: {entry.question}")
            lines.append(f"A{i}: {entry.answer}")
            for j, fu in enumerate(entry.follow_ups, 1):
                lines.append(f"  Follow-up {j}: {fu.question}")
                lines.append(f"  Response {j}: {fu.answer}")
            lines.append("")
        return "\n".join(lines)

    def _format_decision_log(self, session: SessionData) -> str:
        """Format the agent decision log for the summary prompt.

        Args:
            session: The complete session data.

        Returns:
            A formatted string of agent decisions.
        """
        lines: list[str] = []
        for entry in session.agent_decision_log:
            lines.append(f"- Decision: {entry.decision} | Reason: {entry.reason}")
        return "\n".join(lines)

    def generate(self, session: SessionData) -> SummaryOutput:
        """Generate a summary from the complete session data.

        Args:
            session: The full SessionData with responses and decision logs.

        Returns:
            A validated SummaryOutput object.
        """
        transcript = self._format_transcript(session)
        decision_log = self._format_decision_log(session)
        topics = ", ".join(session.detected_topics) if session.detected_topics else "None detected"

        prompt = f"""You are an HR analytics expert. Analyze the following exit interview transcript and produce a structured summary.

TRANSCRIPT:
{transcript}

DETECTED TOPICS: {topics}

AGENT DECISION LOG:
{decision_log}

Return a JSON object with exactly these fields:
- "primary_exit_reason": a concise statement of the main reason the employee is leaving
- "sentiment": the overall sentiment of the interview — one of "positive", "neutral", "negative"
  Weight sentiment across the full conversation, not individual strongly-worded responses.
  If most answers are neutral with only 1–2 negative responses, the overall sentiment should be "neutral".
  Only use "negative" if the majority of responses express negativity.
  Only use "positive" if most responses are clearly positive or encouraging.
- "confidence_score": a float between 0.0 and 1.0 reflecting how clearly the exit reasons emerged from the conversation
- "top_positives": a list of 1–3 things the employee viewed positively about the company
- "improvement_areas": a list of 1–3 areas the company should improve based on this interview
- "flag_for_hr": true if the interview revealed harassment, discrimination, abuse, unethical practices, or hostile work environment concerns; false otherwise
- "flag_reason": a brief explanation if flag_for_hr is true, or null if false

Return valid JSON only.
"""
        try:
            data = invoke_llm_json(prompt, model=SUMMARY_MODEL, temperature=TEMPERATURE)
        except Exception as e:
            raise RuntimeError(f"Summary generation failed: {e}")

        return SummaryOutput.model_validate(data)
