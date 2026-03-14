"""
Interviewer — manages the conversation with the employee using LangChain memory.
"""

import os

from dotenv import load_dotenv
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from config import MODEL_NAME, FALLBACK_MODEL_NAME, TEMPERATURE


# Pre-scripted demo responses covering varied sentiments and topics
DEMO_RESPONSES: list[str] = [
    "I'm leaving mainly because of compensation. I received a much better offer elsewhere "
    "that values my skills more appropriately. The pay gap had been bothering me for a while.",

    "Overall, it has been a mixed experience. The first couple of years were great, but things "
    "started going downhill when management changed. There was a lot of uncertainty and "
    "communication broke down.",

    "I really enjoyed the team culture and the people I worked with directly. My colleagues "
    "were supportive and we had great camaraderie. The learning opportunities in the first "
    "year were excellent.",

    "The company could definitely improve its management practices. My manager was often "
    "dismissive and sometimes borderline abusive in meetings. There were instances where "
    "concerns were raised but nothing was done. Work-life balance was also poor — we were "
    "expected to be available around the clock.",

    "My relationship with my direct team was wonderful, but management was a different story. "
    "My manager would take credit for our work and rarely provided constructive feedback. "
    "There was little transparency in promotion decisions.",

    "I would hesitate to recommend this company right now. While the work itself is interesting, "
    "the management issues and below-market compensation make it hard to suggest to friends. "
    "If those areas improved, it could be a great place again.",

    "It was a gradual realization. After my request for a raise was denied for the second time "
    "despite positive performance reviews, I started looking elsewhere.",

    "The environment became quite hostile after the reorg. People were afraid to speak up.",

    "Yes, there was a specific incident where my manager publicly berated a team member during "
    "a meeting. That was a turning point for many of us on the team.",

    "Honestly, I think people who are early in their career and don't mind the long hours "
    "could benefit from the learning opportunities. But for experienced professionals "
    "looking for fair compensation and respect, I'd say look elsewhere.",
]


class Interviewer:
    """Manages the conversation flow with the employee."""

    def __init__(self, demo_mode: bool = False) -> None:
        """Initialize the interviewer.

        Args:
            demo_mode: If True, use pre-scripted responses instead of live input.
        """
        load_dotenv()
        self.demo_mode = demo_mode
        self.memory = ConversationBufferMemory(return_messages=True)
        self._demo_index = 0
        self._llm = self._create_llm()

        # Set the system prompt
        self._system_prompt = (
            "You are a professional, empathetic HR interviewer conducting an exit interview. "
            "Ask one question at a time and never volunteer opinions. Listen carefully to the "
            "employee's responses and maintain a supportive, non-judgmental tone. Your goal is "
            "to understand the employee's genuine reasons for leaving and their experience."
        )

    def _create_llm(self):
        """Create an LLM client, trying OpenAI first and falling back to Ollama.

        Returns:
            A LangChain chat model instance.
        """
        try:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=MODEL_NAME,
                temperature=TEMPERATURE,
            )
        except Exception:
            from langchain_ollama import ChatOllama

            ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            return ChatOllama(
                model=FALLBACK_MODEL_NAME,
                temperature=TEMPERATURE,
                base_url=ollama_base,
            )

    def ask(self, question: str) -> str:
        """Send a question to the employee and get their response.

        In demo mode, returns a pre-scripted response.
        In live mode, reads from stdin.

        Args:
            question: The interview question to ask.

        Returns:
            The employee's response string.
        """
        # Store the question in memory as an AI message
        self.memory.chat_memory.add_ai_message(question)

        if self.demo_mode:
            response = DEMO_RESPONSES[self._demo_index % len(DEMO_RESPONSES)]
            self._demo_index += 1
        else:
            response = input(f"\n{question}\nYour response: ").strip()

        # Store the response in memory as a human message
        self.memory.chat_memory.add_user_message(response)
        return response

    def get_response(self, employee_input: str) -> str:
        """Process employee input through the LLM chain.

        Uses the conversation memory and system prompt to generate an
        appropriate interviewer response.

        Args:
            employee_input: The employee's latest input.

        Returns:
            The LLM-generated interviewer response.
        """
        messages = [SystemMessage(content=self._system_prompt)]
        messages.extend(self.memory.chat_memory.messages)
        messages.append(HumanMessage(content=employee_input))

        try:
            result = self._llm.invoke(messages)
            return result.content
        except Exception as e:
            return f"Thank you for sharing that. Let's continue. (Error: {e})"

    def get_conversation_history(self) -> str:
        """Get the full conversation history as a formatted string.

        Returns:
            A string representation of the conversation.
        """
        lines: list[str] = []
        for msg in self.memory.chat_memory.messages:
            if isinstance(msg, AIMessage):
                lines.append(f"Interviewer: {msg.content}")
            elif isinstance(msg, HumanMessage):
                lines.append(f"Employee: {msg.content}")
        return "\n".join(lines)
