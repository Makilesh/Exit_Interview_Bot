"""
LangChain tool functions for classification and HR flag detection.
"""

import json

from langchain_core.tools import tool

from config import MODEL_NAME, FALLBACK_MODEL_NAME


def _get_llm(temperature: float = 0):
    """Create an LLM client, trying OpenAI first and falling back to Ollama.

    Args:
        temperature: Sampling temperature for the model.

    Returns:
        A LangChain chat model instance.
    """
    import os
    from dotenv import load_dotenv

    load_dotenv()

    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=MODEL_NAME,
            temperature=temperature,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        # Test with a minimal call to verify connectivity
        return llm
    except Exception:
        from langchain_ollama import ChatOllama

        ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(
            model=FALLBACK_MODEL_NAME,
            temperature=temperature,
            base_url=ollama_base,
            format="json",
        )


def _invoke_llm_json(prompt: str, temperature: float = 0) -> dict:
    """Invoke the LLM and parse the JSON response.

    Args:
        prompt: The prompt to send.
        temperature: Sampling temperature.

    Returns:
        Parsed JSON dict from the LLM response.
    """
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # Try OpenAI first
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=MODEL_NAME,
            temperature=temperature,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        response = llm.invoke(prompt)
        return json.loads(response.content)
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
        response = llm.invoke(prompt)
        return json.loads(response.content)
    except Exception as e:
        raise RuntimeError(f"Both OpenAI and Ollama LLM calls failed: {e}")


@tool
def classify_sentiment_and_reason(response: str) -> dict:
    """Classify the sentiment and exit reason tags from an employee response.

    Given an employee response, returns the sentiment (positive/neutral/negative)
    and reason_tags from the fixed taxonomy: compensation, management, workload,
    career_growth, culture, work_life_balance.

    Args:
        response: The employee's response text.

    Returns:
        Dict with 'sentiment' and 'reason_tags' keys.
    """
    prompt = f"""You are a classification assistant. Analyze the following employee exit interview response.

Return a JSON object with exactly these fields:
- "sentiment": one of "positive", "neutral", or "negative"
- "reason_tags": a list of zero or more tags from this fixed taxonomy: ["compensation", "management", "workload", "career_growth", "culture", "work_life_balance"]

Only include tags that are clearly relevant to the response. Return valid JSON only.

Employee response: "{response}"
"""
    return _invoke_llm_json(prompt, temperature=0)


@tool
def detect_hr_flags(response: str) -> dict:
    """Detect whether an employee response contains HR-flaggable content.

    Flag triggers on mentions of: harassment, discrimination, abusive management,
    unethical practices, or hostile work environment.

    Args:
        response: The employee's response text.

    Returns:
        Dict with 'flag' (bool) and 'reason' (str or None) keys.
    """
    prompt = f"""You are an HR compliance classifier. Analyze the following employee exit interview response for serious concerns.

Flag the response if it mentions any of:
- Harassment
- Discrimination
- Abusive management
- Unethical practices
- Hostile work environment

Return a JSON object with exactly these fields:
- "flag": true or false
- "reason": a brief explanation if flagged, or null if not flagged

Return valid JSON only.

Employee response: "{response}"
"""
    return _invoke_llm_json(prompt, temperature=0)
