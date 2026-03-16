# Claude Code Prompt — Exit Interview Agent: Phase 1 (FastAPI + React Frontend)
# Model: claude-sonnet-4-6
# Project: Agentic AI Exit Interview System

---

## CONTEXT

You are working inside an existing Python project called `exit-interview-agent`.
The core agent is already fully built and working. Do not modify any existing files
unless absolutely necessary. Your job is to wrap it with a web layer.

The project already has:
- `agent/` — state machine, decision engine, LangChain tools, summarizer, interviewer
- `storage/` — Pydantic v2 models (SessionData, SummaryOutput, etc.), SessionStore
- `utils/llm.py` — shared LLM utility with OpenAI → Ollama fallback + circuit breaker
- `config.py` — all tunable parameters
- `main.py` — working CLI entry point (keep this intact)

The agent was built for sequential CLI interaction. The web layer needs to make it
stateful across HTTP requests by serializing StateManager and DecisionEngine state
into the session object between requests.

---

## WHAT TO BUILD (PHASE 1)

### 1. FastAPI Backend — `api/`

Create a new `api/` directory with a FastAPI app that exposes the agent over HTTP.
The existing agent logic must remain untouched — you are only adding a thin HTTP
wrapper around it.

**File structure to create:**
```
api/
├── __init__.py
├── main.py          ← FastAPI app + all routes
├── models.py        ← Pydantic request/response schemas for the API
└── session_store.py ← In-memory registry of active sessions (keyed by session_id)
```

**Routes to implement:**

- `POST /session/start`
  - Creates a new session (uuid), initializes StateManager + DecisionEngine
  - Stores the live session state in memory
  - Returns: session_id, first question, question_number, total_questions

- `POST /session/{session_id}/respond`
  - Accepts the employee's answer for the current question
  - Runs one step of the state machine (evaluate → follow-up or next question)
  - Returns: next_question (or null if done), is_complete, follow_up (bool),
    agent_decision, detected_topics so far
  - When interview is complete, triggers summarizer and returns full SummaryOutput

- `GET /session/{session_id}`
  - Returns full SessionData (transcript, responses, summary, HR flags)

- `GET /sessions`
  - Lists all completed session IDs and their timestamps (for analytics)

- `GET /health`
  - Simple health check

**Key implementation note:**
The Interviewer class currently reads from stdin. For the API, bypass it entirely —
the answer comes in via the HTTP request body. Feed it directly into the state
machine loop that currently lives in main.py's run_interview() function.

Add `uvicorn` and `fastapi` to requirements.txt.
Add CORS middleware so the React frontend (localhost:5173) can call the API.

---

### 2. React Frontend — `frontend/`

Create a React app using Vite. Keep it clean and professional — this is a
portfolio-quality submission.

**File structure to create:**
```
frontend/
├── package.json         ← vite, react, react-dom, tailwindcss
├── vite.config.js
├── index.html
└── src/
    ├── main.jsx
    ├── App.jsx
    ├── api.js           ← all fetch calls centralised here
    └── components/
        ├── ModeSelector.jsx
        ├── ChatInterface.jsx
        ├── ProgressBar.jsx
        └── SummaryPanel.jsx
```

**User flow:**

1. Landing screen — ModeSelector presents 4 interview modes
2. User picks a mode → interview starts → ChatInterface renders
3. Questions appear one by one, employee types answers
4. ProgressBar shows Q1/6 → Q2/6 etc.
5. On completion → SummaryPanel shows the AI-generated summary

**ModeSelector — 4 modes:**

| Mode | Status | Description |
|------|--------|-------------|
| Text → Text | ACTIVE (default) | Type questions, type answers |
| Voice → Text | Coming in Phase 2 | Speak answers, read questions |
| Text → Voice | Coming in Phase 2 | Read questions, hear AI read them aloud |
| Voice → Voice | Coming in Phase 2 | Fully spoken interview |

Text-to-Text must be fully functional.
The other 3 modes should render as selectable cards with a clearly visible
"Phase 2 — Voice Engine" badge. Clicking them shows a friendly message:
"Voice modes are coming soon. The voice engine is being integrated in Phase 2."
Do not disable the cards entirely — make them feel like a real product roadmap.

**ChatInterface:**
- Clean chat bubble layout (AI questions on left, employee answers on right)
- Input box at bottom with Send button (Enter key also submits)
- Show agent decision subtly below each exchange (e.g. "follow-up requested" dim text)
- Disable input while waiting for API response, show a subtle loading indicator
- Smooth scroll to latest message

**SummaryPanel (shown after final question):**
- Primary exit reason (prominent)
- Overall sentiment with a colour indicator (green/yellow/red)
- Confidence score as a progress bar
- Top positives as a simple list
- Improvement areas as a simple list
- Detected topics as pill badges
- HR flag status — if flagged, show a clear red alert box with the reason
- Download buttons: JSON session data, Markdown summary, plain text transcript
  (these call GET /session/{id} and trigger browser download)

**Styling:**
- Use Tailwind CSS utility classes
- Clean, minimal, professional — think internal HR tool, not a consumer app
- Dark/light mode support using Tailwind's dark: prefix
- No heavy component libraries — keep dependencies minimal

---

## PHASE 2 HINTS (do not build, but design for it)

The architecture should make Phase 2 easy to add later:

- The FastAPI app should have a placeholder `api/voice/` directory with a
  `README.md` explaining: "Phase 2 will add a WebSocket endpoint here.
  The voice_engine (STT via Whisper/RealtimeSTT + TTS via Cartesia AI) will
  stream mic audio in, run the same agent core, and stream TTS audio back out.
  The 4-mode selector in the frontend will activate once this endpoint is live."

- In `api/models.py`, include a `mode` field in the SessionStartRequest schema
  with values: "text_text" | "voice_text" | "text_voice" | "voice_voice".
  Default to "text_text". The backend ignores non-text modes for now but the
  field is ready for Phase 2 routing.

- In ModeSelector.jsx, add a comment block:
  `// Phase 2: on mode select, check /health for voice endpoint availability`
  `// If voice WebSocket is live, unlock voice modes dynamically`

---

## CONSTRAINTS

- Do not modify agent/, storage/, utils/, config.py, or the root main.py
- The CLI (python main.py and python main.py --demo) must still work after your changes
- Use Python 3.11+ type hints throughout the API code
- All API error responses must use standard HTTP status codes with JSON bodies
- Session state held in memory is fine for Phase 1 (no database needed)
- The frontend should proxy API calls through Vite's dev server config
  (set proxy: { '/api': 'http://localhost:8000' } in vite.config.js)

---

## HOW TO RUN (write this into a README section)

```bash
# Backend
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

---

## DELIVERABLE CHECKLIST

- [ ] api/ directory with all 4 routes working
- [ ] CORS configured for localhost:5173
- [ ] frontend/ Vite+React app scaffolded
- [ ] ModeSelector with 4 modes (1 active, 3 with Phase 2 badge)
- [ ] ChatInterface with full text-to-text flow
- [ ] ProgressBar (Q1/6 → Q6/6)
- [ ] SummaryPanel with all fields + download buttons
- [ ] api/voice/README.md Phase 2 placeholder
- [ ] Updated root README.md with web setup instructions
- [ ] requirements.txt updated with fastapi, uvicorn

---