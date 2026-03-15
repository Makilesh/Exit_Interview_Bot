"""
Shared LLM invocation utility.
Provides a single canonical function for all JSON-returning LLM calls,
with OpenAI as the primary provider and Ollama as the fallback.
"""

import json
import os

from dotenv import load_dotenv

from config import MODEL_NAME, FALLBACK_MODEL_NAME, TEMPERATURE

load_dotenv()


def invoke_llm_json(
    prompt: str,
    model: str = MODEL_NAME,
    temperature: float = TEMPERATURE,
) -> dict:
    """Invoke an LLM and return the parsed JSON response.

    Tries OpenAI first. If that fails for any reason, falls back to Ollama.

    Args:
        prompt: The prompt to send to the model.
        model: The OpenAI model name to use (default: MODEL_NAME from config).
        temperature: Sampling temperature (default: TEMPERATURE from config).

    Returns:
        Parsed JSON dict from the LLM response.

    Raises:
        RuntimeError: If both OpenAI and Ollama calls fail.
    """
    # Try OpenAI first
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        result = llm.invoke(prompt)
        return json.loads(result.content)
    except Exception:
        pass

    # Fallback to Ollama
    try:
        from langchain_ollama import ChatOllama

        ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        llm = ChatOllama(
            model=FALLBACK_MODEL_NAME,
            temperature=temperature,
            base_url=ollama_base,
            format="json",
        )
        result = llm.invoke(prompt)
        return json.loads(result.content)
    except Exception as e:
        raise RuntimeError(f"Both OpenAI and Ollama LLM calls failed: {e}")
