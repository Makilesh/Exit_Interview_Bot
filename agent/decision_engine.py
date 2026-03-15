"""
Decision engine — the core of agentic behavior.
Evaluates employee responses and decides whether to follow up or move on.
"""

from config import MODEL_NAME, TEMPERATURE
from storage.schema import AgentDecisionEntry
from utils.llm import invoke_llm_json


class DecisionEngine:
    """Evaluates employee responses and makes structured decisions about interview flow."""

    def __init__(self) -> None:
        """Initialize the decision engine with an empty topic memory."""
        self.topic_memory: list[str] = []

    def evaluate(self, response: str, question: str, conversation_history: str) -> tuple[dict, AgentDecisionEntry]:
        """Evaluate an employee response and return a structured decision.

        Args:
            response: The employee's latest answer.
            question: The question that was asked.
            conversation_history: The full conversation context so far.

        Returns:
            A tuple of (decision_dict, AgentDecisionEntry).
        """
        prompt = f"""You are a decision engine for an exit interview system. Your only job is classification and decision-making.

Analyze the employee's response to the interview question below, in the context of the full conversation.

Conversation so far:
{conversation_history}

Current question: "{question}"
Employee response: "{response}"

Return a JSON object with exactly these fields:
- "decision": either "ask_followup" or "next_question"
- "reason": one of "vague_answer", "potential_management_issue", "emotionally_charged", "sufficient_answer", "detailed_response", "off_topic"
- "reason_tags": a list from this taxonomy: ["compensation", "management", "workload", "career_growth", "culture", "work_life_balance"]
- "sentiment": one of "positive", "neutral", "negative"
- "dominant_topics": a list from the same taxonomy as reason_tags — topics the employee **explicitly mentioned or directly described** in this response. Do NOT infer or guess topics that were not mentioned.
  Counter-examples to avoid hallucinated tags:
  - "I got a better offer" → ["compensation"], NOT ["career_growth"]
  - "management was bad" → ["management"], NOT ["work_life_balance"]
  - "the hours were long" → ["workload"], NOT ["work_life_balance"] unless balance was explicitly described

Rules for choosing "next_question" (move on):
- The employee clearly states a reason, even briefly (e.g. "compensation", "better opportunity", "management issues")
- The answer is a direct yes or no to a yes/no question
- The conversation already includes one or more follow-up exchanges on this topic — do not probe indefinitely
- The answer is short but contains at least one concrete, specific detail

Rules for choosing "ask_followup" (probe deeper):
- The question is open-ended ("describe", "explain", "how would you", "what did you like", "why") AND the answer is a single word or generic phrase with no specifics (e.g. "good", "fine", "it was okay", "bad")
- The answer is completely generic with no specifics (e.g. "it was fine", "I don't know")
- The answer hints at a serious concern (management abuse, discrimination) but gives no detail
- The answer is emotionally charged and unexplored
- Emotion words alone (bad, good, fine, terrible, amazing, awful, great) without any noun,
  person, event, or action described are NOT sufficient answers — treat them as vague.
  Example: "bad and very bad" → ask_followup (no specifics given)
  Example: "bad — my manager ignored all feedback" → next_question (specific detail present)

Default toward "next_question" when in doubt. Only choose "ask_followup" if there is a clear, specific reason to dig deeper.
Return valid JSON only.
"""
        try:
            decision_data = invoke_llm_json(prompt, model=MODEL_NAME, temperature=TEMPERATURE)
        except Exception as e:
            # Fallback: if both LLM providers fail, default to next_question
            decision_data = {
                "decision": "next_question",
                "reason": "llm_error",
                "reason_tags": [],
                "sentiment": "neutral",
                "dominant_topics": [],
            }

        # Update topic memory with deduplication
        for topic in decision_data.get("dominant_topics", []):
            if topic not in self.topic_memory:
                self.topic_memory.append(topic)

        # Create the decision log entry
        entry = AgentDecisionEntry(
            response=response,
            decision=decision_data.get("decision", "next_question"),
            reason=decision_data.get("reason", "unknown"),
        )

        return decision_data, entry
