# Agentic AI Exit Interview System

An intelligent exit interview system powered by LangChain and OpenAI (with Ollama fallback). The system conducts structured exit interviews with employees, using an agentic decision engine to dynamically adapt follow-up questions based on response quality and content. It produces structured session data, human-readable transcripts, and Markdown summary reports.

## Architecture

### State Machine
The interview follows a strict state machine flow: `INTERVIEW_START` -> `ASK_QUESTION` -> `EVALUATE_RESPONSE` -> (optionally `ASK_FOLLOWUP`) -> `NEXT_QUESTION` -> ... -> `INTERVIEW_COMPLETE` -> `GENERATE_SUMMARY`. The `StateManager` enforces valid transitions, tracks question progress, and manages termination conditions (all questions asked, max turns reached, or max follow-ups per question).

### Decision Engine
The `DecisionEngine` is the core of the agentic behavior. After each employee response, it makes an LLM call to classify the response and decide whether to ask a follow-up (for vague, emotionally charged, or incomplete answers) or move to the next question. It maintains a running topic memory of all discussed themes.

### Tools
Two LangChain `@tool` functions handle specialized classification:
- **`classify_sentiment_and_reason`** — Extracts sentiment (positive/neutral/negative) and reason tags from a fixed taxonomy (compensation, management, workload, career_growth, culture, work_life_balance).
- **`detect_hr_flags`** — Flags responses mentioning harassment, discrimination, abusive management, unethical practices, or hostile work environments.

### Storage
The `SessionStore` handles all persistence: JSON session data (validated through Pydantic models), plain-text transcripts, and Markdown summary reports. All output files are written to the `outputs/` directory.

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API keys:**
   Create a `.env` file in the project root:
   ```env
   OPENAI_API_KEY=your-openai-api-key-here
   ```

3. **Ollama fallback (optional):**
   If you want fallback support when OpenAI is unavailable:
   - Install and run [Ollama](https://ollama.ai/) locally
   - Pull the fallback model: `ollama pull gpt-oss:20b`
   - Optionally set `OLLAMA_BASE_URL` in `.env` (defaults to `http://localhost:11434`)

## How to Run

### Live mode (interactive stdin input)
```bash
python main.py
```

### Demo mode (pre-scripted responses)
```bash
python main.py --demo
```

### Multi-interview analysis
After running one or more interviews:
```bash
python scripts/analyze_interviews.py
```

This reads all saved sessions and prints an aggregate report with exit reason rankings, sentiment distribution, common improvement areas, and HR flag counts.

## Sample Output

Below is a truncated example of a generated `session_<id>_summary.md`:

```markdown
# Exit Interview Summary — Session a1b2c3d4

**Date:** 2025-01-15T10:30:00+00:00

---

## Primary Exit Reason

Below-market compensation combined with poor management practices.

## Overall Sentiment

negative

## Confidence Score

0.85

## Top Positives

- Supportive team culture and camaraderie
- Strong learning opportunities in the first year
- Interesting and challenging work

## Improvement Areas

- Compensation alignment with market rates
- Management training and accountability
- Work-life balance policies

## HR Flag Status

**Flagged:** Yes
**Reason:** Employee reported publicly abusive behavior by manager in team meetings.

---

## Detected Topics

- compensation
- management
- work_life_balance
- culture
```

## Project Structure

```
exit-interview-agent/
├── config.py                  # All tunable parameters
├── main.py                    # Entry point and orchestration
├── agent/
│   ├── __init__.py
│   ├── interviewer.py         # Conversation management with LLM
│   ├── questions.py           # Question bank and follow-up variants
│   ├── decision_engine.py     # Agentic decision-making
│   ├── state_manager.py       # Interview state machine
│   ├── summarizer.py          # Final summary generation
│   └── tools.py               # LangChain classification tools
├── storage/
│   ├── __init__.py
│   ├── session.py             # Session persistence and export
│   └── schema.py              # Pydantic v2 data models
├── outputs/                   # Generated interview data
├── scripts/
│   └── analyze_interviews.py  # Aggregate analysis script
├── requirements.txt
└── README.md
```
