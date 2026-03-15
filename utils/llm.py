"""
Shared LLM invocation utility.
Provides a single canonical function for all JSON-returning LLM calls,
with OpenAI as the primary provider and Ollama as the fallback.

Includes a circuit breaker that skips OpenAI after consecutive failures
and a client cache that reuses LLM instances across calls.
"""

import json
import os
import threading
import time

from dotenv import load_dotenv

from config import MODEL_NAME, FALLBACK_MODEL_NAME, TEMPERATURE

load_dotenv()

# ---------------------------------------------------------------------------
# Circuit breaker — skip OpenAI after consecutive failures
# ---------------------------------------------------------------------------
_CB_LOCK = threading.Lock()
_cb_failure_count: int = 0
_cb_open_until: float = 0.0
_CB_FAILURE_THRESHOLD: int = 2
_CB_COOLDOWN_SECONDS: float = 60.0


def _cb_is_open() -> bool:
    """Return True if the breaker is open and OpenAI should be skipped."""
    with _CB_LOCK:
        if _cb_failure_count < _CB_FAILURE_THRESHOLD:
            return False
        if time.monotonic() >= _cb_open_until:
            return False  # cooldown expired — half-open, allow one attempt
        return True


def _cb_record_failure() -> None:
    """Record an OpenAI failure; open the breaker if threshold reached."""
    global _cb_failure_count, _cb_open_until
    with _CB_LOCK:
        _cb_failure_count += 1
        if _cb_failure_count >= _CB_FAILURE_THRESHOLD:
            _cb_open_until = time.monotonic() + _CB_COOLDOWN_SECONDS


def _cb_record_success() -> None:
    """Record an OpenAI success; reset the breaker."""
    global _cb_failure_count, _cb_open_until
    with _CB_LOCK:
        _cb_failure_count = 0
        _cb_open_until = 0.0


# ---------------------------------------------------------------------------
# Client cache — reuse LLM instances across calls
# ---------------------------------------------------------------------------
_CLIENT_LOCK = threading.Lock()
_openai_clients: dict[tuple[str, float], object] = {}
_ollama_clients: dict[tuple[str, float], object] = {}


def _get_openai_client(model: str, temperature: float):
    """Return a cached ChatOpenAI instance, creating one if needed."""
    key = (model, temperature)
    with _CLIENT_LOCK:
        if key not in _openai_clients:
            from langchain_openai import ChatOpenAI

            _openai_clients[key] = ChatOpenAI(
                model=model,
                temperature=temperature,
                model_kwargs={"response_format": {"type": "json_object"}},
            )
        return _openai_clients[key]


def _get_ollama_client(model: str, temperature: float):
    """Return a cached ChatOllama instance, creating one if needed."""
    key = (model, temperature)
    with _CLIENT_LOCK:
        if key not in _ollama_clients:
            from langchain_ollama import ChatOllama

            ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            _ollama_clients[key] = ChatOllama(
                model=model,
                temperature=temperature,
                base_url=ollama_base,
                format="json",
            )
        return _ollama_clients[key]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def invoke_llm_json(
    prompt: str,
    model: str = MODEL_NAME,
    temperature: float = TEMPERATURE,
) -> dict:
    """Invoke an LLM and return the parsed JSON response.

    Tries OpenAI first (unless the circuit breaker is open).
    Falls back to Ollama on any failure.

    Args:
        prompt: The prompt to send to the model.
        model: The OpenAI model name to use (default: MODEL_NAME from config).
        temperature: Sampling temperature (default: TEMPERATURE from config).

    Returns:
        Parsed JSON dict from the LLM response.

    Raises:
        RuntimeError: If both OpenAI and Ollama calls fail.
    """
    # Try OpenAI first — unless the circuit breaker is open
    if not _cb_is_open():
        try:
            llm = _get_openai_client(model, temperature)
            result = llm.invoke(prompt)
            _cb_record_success()
            return json.loads(result.content)
        except Exception:
            _cb_record_failure()

    # Fallback to Ollama
    try:
        llm = _get_ollama_client(FALLBACK_MODEL_NAME, temperature)
        result = llm.invoke(prompt)
        return json.loads(result.content)
    except Exception as e:
        raise RuntimeError(f"Both OpenAI and Ollama LLM calls failed: {e}")
