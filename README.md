# Agentic AI Exit Interview System

An intelligent, LLM-driven exit interview agent built with Python, LangChain, and OpenAI (with local Ollama fallback). The system conducts structured exit interviews, uses an agentic decision engine to dynamically adapt follow-up questions based on response quality, classifies sentiment and topics in real time, flags HR concerns, and produces a structured session record, a human-readable transcript, and a Markdown summary report.

Available as a **CLI application** (text-only) or **full-stack web interface** with 4 interview modes: text-only, voice-to-text (STT), text-to-voice (TTS), or fully voice-driven (end-to-end).

---

## Architecture

The system is composed of five layers that interact in a tight loop: the state machine orchestrates flow, the decision engine drives agentic behaviour, the LangChain tools classify each response, the LLM utility handles provider routing, and the storage layer persists everything.

### 1. State Machine (`agent/state_manager.py`)

The entire interview is governed by a seven-state machine:

```
INTERVIEW_START
      │  "start"
      ▼
  ASK_QUESTION  ◄───────────────────────────────┐
      │  "response_received"                    │
      ▼                                         │
EVALUATE_RESPONSE                               │
      │                                         │
      ├─ "followup_needed" ──► ASK_FOLLOWUP ───►┤  "followup_done"
      │                                         │
      └─ "next_question" ────► NEXT_QUESTION ───┘
                                    │  "all_questions_done"
                                    ▼
                          INTERVIEW_COMPLETE
                                    │  "generate_summary"
                                    ▼
                           GENERATE_SUMMARY
```

`StateManager` tracks the current state, the active question index, the per-question follow-up count, and the total turn count. `should_terminate()` returns `True` when any termination condition is met (all 6 questions asked, `MAX_TURNS` reached, or `MAX_FOLLOWUPS_PER_QUESTION` reached for the current question). `can_followup()` is a guard used by the decision engine to prevent over-probing.

### 2. Decision Engine (`agent/decision_engine.py`)

The `DecisionEngine` is the core of the agentic behaviour. After every employee response, it makes a focused LLM call whose only job is classification and decision-making — not conversation. It returns a structured JSON object:

```json
{
  "decision": "ask_followup" | "next_question",
  "reason": "vague_answer" | "emotionally_charged" | "potential_management_issue" | "sufficient_answer" | ...,
  "reason_tags": ["management", "compensation", ...],
  "sentiment": "positive" | "neutral" | "negative",
  "dominant_topics": ["management", "career_growth", ...]
}
```

Key decision rules baked into the prompt:

- **Move on** when the answer contains a concrete specific detail, even briefly, or directly answers a yes/no question.
- **Follow up** when the answer is generic ("it was fine", "I don't know"), emotionally charged without specifics, or hints at a serious concern without naming it.
- **Emotion-word rule:** Strong adjectives (`hated`, `horrible`, `terrible`, `awful`, `worst`) paired with a person or role still require a specific incident or action — otherwise the response is treated as vague and triggers a follow-up.

The engine accumulates `dominant_topics` across all turns into `topic_memory`, which maps directly to `detected_topics` in the session record.

### 3. LangChain Tools (`agent/tools.py`)

Two `@tool`-decorated functions run in parallel with the decision engine on every turn, providing independent signal:

**`classify_sentiment_and_reason(response, question)`**
Returns `sentiment` (positive / neutral / negative) and `reason_tags` from a fixed six-item taxonomy: `compensation`, `management`, `workload`, `career_growth`, `culture`, `work_life_balance`. Sentiment is evaluated relative to the question context (e.g. naming things you liked counts as positive). `"mixed"` is explicitly disallowed — dual-sentiment responses are resolved to the dominant tone. A post-processing guard in `main.py` enforces valid values.

**`detect_hr_flags(response)`**
Returns `{"flag": bool, "severity": "critical" | "standard" | null, "reason": str | None}`. Flags only explicit misconduct: harassment, discrimination, abusive management, unethical or illegal practices, or a hostile work environment driven by the above. General dissatisfaction, toxic-culture descriptions without specific incidents, and pay complaints are explicitly excluded.

`severity` is set to `"critical"` for sexual harassment, sexual assault, rape, physical violence, or unwanted sexual contact — triggering immediate interview termination with a crisis escalation response. `"standard"` covers other flagged content (non-sexual discrimination, verbal abuse, unethical practices) — the interview continues to the next question but follow-ups are suppressed to avoid probing a sensitive topic.

### 4. Per-Turn Execution Flow (`main.py` — `EVALUATE_RESPONSE`)

On every employee response, all three classification calls run concurrently in a single `ThreadPoolExecutor(max_workers=3)`:

```
Employee Response
        │
        ├──────────────────────────────────────┐──────────────────┐
        ▼                                      ▼                  ▼
DecisionEngine.evaluate()      classify_sentiment_and_reason()   detect_hr_flags()
  → decision + reason tags       → sentiment + reason_tags         → flag + severity + reason
        │                                      │                  │
        └──────────────────────────────────────┘──────────────────┘
                                        │
                             severity == "critical"?
                             YES → stop interview → CrisisPanel
                             NO  ↓
                             Resolve actual decision
                             (guard: can_followup? HR flagged?)
                                        │
                           Log to agent_decision_log
                                        │
                        Transition state machine
```

The decision engine's result drives the state transition; the tools' results enrich the `ResponseEntry`. Because all three calls are independent, wall-clock time per turn equals `max(T_decision, T_classify, T_hr)` rather than their sum.

### 5. LLM Utility Layer (`utils/llm.py`)

All LLM calls across the entire system go through one function: `invoke_llm_json(prompt, model, temperature)`. It provides three pillars:

**Provider fallback** — tries `ChatOpenAI` first; on any failure, falls back to the local `ChatOllama` instance. The Ollama base URL defaults to `http://localhost:11434` and is overridable via `OLLAMA_BASE_URL` in `.env`.

**Circuit breaker** — after 2 consecutive OpenAI failures, OpenAI is skipped entirely for 60 seconds. This eliminates repeated timeout or authentication overhead on every call when the primary provider is unavailable (e.g. when running fully locally). The breaker resets automatically after the cooldown or on the next successful call.

**Client cache** — `ChatOpenAI` and `ChatOllama` instances are cached by `(model, temperature)` key. A session of ~25 LLM calls reuses 2-3 client instances instead of constructing fresh ones each time. Both mechanisms are thread-safe via `threading.Lock`.

### 6. Conversation Memory (`agent/interviewer.py`)

The `Interviewer` class manages per-session conversation history using `InMemoryChatMessageHistory` from `langchain_core`. It stores the full Q&A exchange as a sequence of human/AI messages. `get_conversation_history()` returns this as a formatted string passed to the decision engine for context-aware decisions.

In **demo mode** (`--demo`), `ask()` returns pre-scripted responses covering varied sentiments including management concerns and compensation mentions. In **live mode**, it reads from stdin.

### 7. Summarizer (`agent/summarizer.py`)

After all questions are answered, the `Summarizer` formats the full Q&A transcript, the detected topics, and the agent decision log into a single prompt and makes one LLM call. The result is parsed into a `SummaryOutput` Pydantic model with these fields:

| Field | Type | Description |
|---|---|---|
| `primary_exit_reason` | str | The main reason the employee is leaving |
| `sentiment` | str | Overall interview sentiment (positive / neutral / negative) |
| `confidence_score` | float | 0.0–1.0, how clearly exit reasons emerged |
| `top_positives` | list[str] | 1–3 things the employee valued |
| `improvement_areas` | list[str] | 1–3 areas the company should address |
| `flag_for_hr` | bool | Whether HR escalation is warranted |
| `flag_reason` | str \| None | Explanation if flagged |

### 8. Session Storage (`storage/session.py`)

`SessionStore` writes files per session to the `outputs/` directory with timestamped, chronologically sortable names. Normal sessions produce three files; crisis-escalated sessions produce two (no LLM summary is generated):

```
outputs/
  session_20260315_075457_c02fd9e0.json          ← full session data (Pydantic-validated)
  session_20260315_075457_c02fd9e0_transcript.txt ← clean Q&A formatted text
  session_20260315_075457_c02fd9e0_summary.md     ← structured Markdown report (normal sessions only)
```

`load()` and `list_sessions()` work by globbing for the session ID (the last segment before the extension), so they are resilient to the timestamp prefix.

### 9. Aggregate Analysis (`scripts/analyze_interviews.py`)

A standalone script that reads all saved sessions via `SessionStore` and prints a cross-session report — no LLM calls:

- Most common exit reasons (ranked)
- Sentiment distribution (positive / neutral / negative counts)
- Most common improvement areas
- Count of HR-flagged sessions

---

## Data Models (`storage/schema.py`)

All data structures are Pydantic v2 models and serve as the single source of truth.

```
SessionData
├── session_id: str
├── timestamp: str
├── conversation_length: int
├── followup_count: int
├── detected_topics: list[str]
├── responses: list[ResponseEntry]
│   ├── question: str
│   ├── answer: str
│   ├── sentiment: str
│   ├── reason_tags: list[str]
│   └── follow_ups: list[FollowUp]
│       ├── question: str
│       └── answer: str
├── agent_decision_log: list[AgentDecisionEntry]
│   ├── response: str
│   ├── decision: str
│   └── reason: str
└── summary: SummaryOutput | None
```

---

## Project Structure

```
exit-interview-agent/
├── config.py                    # All tunable parameters (single source of truth)
├── main.py                      # Entry point — state machine loop and orchestration
├── agent/
│   ├── __init__.py
│   ├── decision_engine.py       # Agentic follow-up / next-question decision
│   ├── interviewer.py           # Conversation memory, demo/live mode
│   ├── questions.py             # Question bank (6 primary + follow-up variants)
│   ├── state_manager.py         # 7-state interview state machine
│   ├── summarizer.py            # End-of-session summary LLM call
│   └── tools.py                 # @tool: classify_sentiment_and_reason, detect_hr_flags
├── storage/
│   ├── __init__.py
│   ├── schema.py                # Pydantic v2 models — SessionData, SummaryOutput, etc.
│   └── session.py               # JSON / transcript / Markdown export
├── utils/
│   └── llm.py                   # Shared invoke_llm_json + circuit breaker + client cache
├── outputs/                     # Generated session files (gitignored)
├── scripts/
│   └── analyze_interviews.py    # Cross-session aggregate report
├── requirements.txt
└── README.md
```

---

## Configuration (`config.py`)

| Parameter | Default | Description |
|---|---|---|
| `MODEL_NAME` | `"gpt-4.1"` | Primary OpenAI model for all calls |
| `SUMMARY_MODEL` | `"gpt-4.1"` | Model used for the final summary |
| `FALLBACK_MODEL_NAME` | `"gpt-oss:20b"` | Ollama model used when OpenAI is unavailable |
| `TEMPERATURE` | `0.3` | Sampling temperature (tools use `0` for determinism) |
| `MAX_TURNS` | `15` | Hard cap on total conversation turns |
| `MAX_FOLLOWUPS_PER_QUESTION` | `2` | Maximum follow-ups per primary question |
| `OUTPUT_DIR` | `"outputs"` | Directory for all generated files |

---

## Setup

**1. Install dependencies:**
```bash
pip install -r requirements.txt
```

**2. Configure the OpenAI API key (optional — local Ollama fallback available):**

Create a `.env` file in the project root:
```env
OPENAI_API_KEY=sk-your-key-here
```

**3. Ollama fallback (recommended for offline use):**

Install and run [Ollama](https://ollama.ai/) locally, then pull the fallback model:
```bash
ollama pull gpt-oss:20b
```

Optionally override the Ollama endpoint in `.env`:
```env
OLLAMA_BASE_URL=http://localhost:11434
```

Local fallback verification in this workspace succeeded against `gpt-oss:20b`. If you want to exercise the local path explicitly, you can leave `OPENAI_API_KEY` unset or temporarily clear it before running the app; the shared LLM utility will fall back to Ollama.

When OpenAI is unavailable, the circuit breaker in `utils/llm.py` automatically routes all calls to Ollama after the first two failures.

**4. Voice dependencies (required for web interface voice modes):**

- **STT (Speech-to-Text):** `faster-whisper` is already in `requirements.txt` and tested ✅
- **TTS (Text-to-Speech):** Kokoro requires `realtimetts[kokoro]`:
  ```bash
  pip install "realtimetts[kokoro]"
  ```
  Fallback to `pyttsx3` (SAPI5 on Windows) is automatic if Kokoro unavailable.

- **Audio processing:** System `ffmpeg` is required for WebM/Opus → PCM conversion:
  - **Windows:** `choco install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html)
  - **macOS:** `brew install ffmpeg`
  - **Linux:** `sudo apt install ffmpeg`

Run `python check_environment.py` to verify all dependencies are ready.

---

## How to Run

**Live mode** — employee types responses interactively:
```bash
python main.py
```

**Demo mode** — pre-scripted responses, useful for testing:
```bash
python main.py --demo
```

**Aggregate analysis** — cross-session report from all saved outputs:
```bash
python scripts/analyze_interviews.py
```

---

## Sample Output

### Terminal (rich summary table)

```
┌─────────────────────────────────────────────────────────┐
│                    Interview Summary                     │
├──────────────────────────┬──────────────────────────────┤
│ Session ID               │ 0d50d177                     │
│ Primary Exit Reason      │ Lack of learning and growth  │
│ Sentiment                │ negative                     │
│ Confidence Score         │ 0.85                         │
│ Questions Asked          │ 6                            │
│ Total Turns              │ 8                            │
│ HR Flagged               │ No                           │
└──────────────────────────┴──────────────────────────────┘
```

### `session_20260315_075457_0d50d177_summary.md`

```markdown
# Exit Interview Summary — Session 0d50d177

**Date:** 2026-03-15T08:15:01.936273+00:00

---

## Primary Exit Reason

Lack of learning and growth opportunities

## Overall Sentiment

negative

## Confidence Score

0.85

## Top Positives

- Teammates and team culture

## Improvement Areas

- Management behaviour and accountability
- Employee treatment and respect
- Compensation alignment

## HR Flag Status

**Flagged:** No

---

## Detected Topics

- career_growth
- management
- culture
- compensation
```

---

## Web Interface (Phase 1)

The agent is also available as a full-stack web application — FastAPI backend + React frontend.

### Project structure (web layer)

```
api/
├── __init__.py
├── main.py           ← FastAPI app + all routes (includes voice WebSocket router)
├── models.py         ← Pydantic request/response schemas
├── session_store.py  ← In-memory live session registry
└── voice/
    ├── __init__.py   ← WebSocket router for all voice modes
    ├── stt.py        ← Speech-to-text (faster-whisper)
    ├── tts.py        ← Text-to-speech (Kokoro / pyttsx3 fallback)
    ├── test_stt.py   ← STT testing utilities
    ├── test_tts.py   ← TTS testing utilities
    └── Voice_README.md     ← Voice engine detailed documentation

frontend/
├── package.json      ← Vite + React + Tailwind
├── vite.config.js    ← /api proxy → localhost:8000
└── src/
    ├── App.jsx        ← 4-mode router (select → interview → summary | crisis)
    ├── api.js         ← All fetch calls centralised (including WebSocket auth)
    └── components/
        ├── ModeSelector.jsx   ← 4-mode landing screen
        ├── ChatInterface.jsx  ← Chat bubble interface (text mode)
        ├── VoiceInterface.jsx ← Voice mode handler (handles STT/TTS over WebSocket)
        ├── ProgressBar.jsx    ← Q1/6 → Q6/6 progress indicator
        ├── SummaryPanel.jsx   ← Full summary + downloads
        └── CrisisPanel.jsx    ← Emergency escalation screen
```

### API routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/session/start` | Create session, return first question |
| POST | `/api/session/{id}/respond` | Submit answer, get next question or summary |
| GET | `/api/session/{id}` | Full session data (JSON) |
| GET | `/api/sessions` | List all completed sessions |
| GET | `/api/session/{id}/download/json` | Download session JSON |
| GET | `/api/session/{id}/download/transcript` | Download transcript |
| GET | `/api/session/{id}/download/summary` | Download Markdown summary |

### Running the web interface

**1. Install Python dependencies (if not already done):**
```bash
pip install -r requirements.txt
```

**2. Start the backend:**
```bash
uvicorn api.main:app --reload --port 8000
```

**3. Start the frontend (separate terminal):**
```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### Interview modes

| Mode | Status | Engine | Description |
|------|--------|--------|-------------|
| Text → Text | **Active** | — | Type questions, type answers |
| Voice → Text | **Active** | faster-whisper STT | Speak answers, read questions (STT only) |
| Text → Voice | **Active** | Kokoro TTS | Type answers, hear questions spoken (TTS only) |
| Voice → Voice | **Active** | faster-whisper + Kokoro | Fully spoken interview (STT + TTS via WebSocket) |

**Voice Architecture:**

All voice modes operate over WebSocket (`/api/voice/ws/{session_id}?mode={mode}`):

- **STT Engine:** `faster-whisper` (local, no API key)
  - Model: configurable via `WHISPER_MODEL` env var (default: `base.en`)
  - Input: browser audio (WebM/Opus) → converted to PCM via ffmpeg
  - Device: auto-detects CUDA (float16), falls back to CPU (int8)
  - VAD (Voice Activity Detection): silero-vad with threshold 0.38

- **TTS Engine:** `Kokoro-82M` via RealtimeTTS (local, no API key)
  - Voice: configurable via `KOKORO_VOICE` env var (default: `af_heart`)
  - Output: WAV bytes streamed to browser via WebSocket → plays in AudioContext
  - Fallback: `pyttsx3` (Windows SAPI5) if Kokoro unavailable
  - Device: auto-detects CUDA

**Configuration (.env):**
```env
WHISPER_MODEL=base.en        # tiny.en | small.en | base.en
KOKORO_VOICE=af_heart        # af_heart | af_bella | af_sarah | am_adam | bm_george | bf_emma
KOKORO_SPEED=1.0             # 0.5–2.0
```

**Status Notes:**
- STT tested and working ✅
- TTS tested and working ✅
- WebSocket message protocol stable ✅
- Browser MediaRecorder → PCM conversion fixed (ffmpeg required) ✅

See `api/voice/Voice_README.md` for detailed message protocol and troubleshooting.