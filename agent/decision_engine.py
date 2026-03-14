"""
Decision engine — the core of agentic behavior.
Evaluates employee responses and decides whether to follow up or move on.
"""

import json
import os

from dotenv import load_dotenv

from config import MODEL_NAME, FALLBACK_MODEL_NAME, TEMPERATURE
from storage.schema import AgentDecisionEntry


class DecisionEngine:
    """Evaluates employee responses and makes structured decisions about interview flow."""

    def __init__(self) -> None:
        """Initialize the decision engine with an empty topic memory."""
        load_dotenv()
        self.topic_memory: list[str] = []

    def _get_llm(self):
        """Create an LLM client, trying OpenAI first and falling back to Ollama.

        Returns:
            A LangChain chat model instance.
        """
        try:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=MODEL_NAME,
                temperature=TEMPERATURE,
                model_kwargs={"response_format": {"type": "json_object"}},
            )
        except Exception:
            from langchain_ollama import ChatOllama

            ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            return ChatOllama(
                model=FALLBACK_MODEL_NAME,
                temperature=TEMPERATURE,
                base_url=ollama_base,
                format="json",
            )

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
- "dominant_topics": a list from the same taxonomy as reason_tags — the main topics discussed in this response

Rules:
- Choose "ask_followup" if the answer is vague, shallow, emotionally charged, or hints at a deeper issue worth exploring.
- Choose "next_question" if the answer is clear, detailed, and sufficient.
- Return valid JSON only.
"""
        llm = self._get_llm()
        try:
            result = llm.invoke(prompt)
            decision_data = json.loads(result.content)
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
