"""
LangChain tool functions for classification and HR flag detection.
"""

from langchain_core.tools import tool

from config import MODEL_NAME
from utils.llm import invoke_llm_json


@tool
def classify_sentiment_and_reason(response: str, question: str = "") -> dict:
    """Classify the sentiment and exit reason tags from an employee response.

    Given an employee response and the question that prompted it, returns the
    sentiment (positive/neutral/negative) and reason_tags from the fixed taxonomy:
    compensation, management, workload, career_growth, culture, work_life_balance.

    Args:
        response: The employee's response text.
        question: The interview question that was asked (used for sentiment context).

    Returns:
        Dict with 'sentiment' and 'reason_tags' keys.
    """
    question_context = f'Interview question: "{question}"\n' if question else ""
    prompt = f"""You are a classification assistant. Analyze the following employee exit interview response.

{question_context}Return a JSON object with exactly these fields:
- "sentiment": one of "positive", "neutral", or "negative"
  Important: determine sentiment relative to the question being asked. If the question asks
  what the employee LIKED or what was POSITIVE, and the response names things positively,
  that is "positive" sentiment even if the words are neutral nouns.
  Example: question = "What did you like most?" + response = "the people, the environment" → sentiment: "positive"
  A list of nouns that are positive things (when asked about positives) is POSITIVE, not neutral.
- "reason_tags": a list of zero or more tags from this fixed taxonomy: ["compensation", "management", "workload", "career_growth", "culture", "work_life_balance"]

Only include tags that are clearly relevant to the response. Return valid JSON only.

Employee response: "{response}"
"""
    return invoke_llm_json(prompt, model=MODEL_NAME, temperature=0)


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
    prompt = f"""You are an HR compliance classifier. Your job is to detect responses that describe serious misconduct — not general dissatisfaction.

Flag the response ONLY if the employee explicitly describes one or more of:
- Harassment (personal, sexual, or targeted)
- Discrimination (race, gender, age, religion, disability, etc.)
- Abusive or threatening behaviour by management
- Unethical or illegal business practices
- A hostile work environment driven by the above

Do NOT flag based solely on:
- Compensation complaints or pay dissatisfaction (even "pay gap" or "underpaid")
- General frustration with management style or communication
- Disagreements about promotion or career growth
- Workload or work-life balance complaints
- Vague feelings of being undervalued
- General descriptions of "toxic culture" or "toxic people" without specific incidents of targeted harm
- Feeling demotivated, disengaged, or undervalued
- Vague references to a "bad environment" with no named misconduct

Return a JSON object with exactly these fields:
- "flag": true or false
- "reason": a one-sentence explanation if flagged, or null if not flagged

Return valid JSON only.

Employee response: "{response}"
"""
    return invoke_llm_json(prompt, model=MODEL_NAME, temperature=0)
