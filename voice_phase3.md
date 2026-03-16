 Voice Mode Integration for Exit Interview Agent

# Phase 2: Wire voice engine into the existing FastAPI + React stack

---

## CONTEXT

You are working inside an existing full-stack project: `exit-interview-agent`.

The project already has:
- A working FastAPI backend (`api/`) with session state, decision engine, summarizer
- A working React frontend (`frontend/`) with 4 mode cards (only Text→Text active)
- A working CLI agent (`main.py`, `agent/`, `storage/`)
- A Phase 2 placeholder at `api/voice/README.md`

You also have access to a separate reference repo: `voice_engine_MVP` (github.com/Makilesh/voice_engine_MVP).
Study its implementation for STT and TTS patterns. Do NOT copy it wholesale — adapt
the relevant parts cleanly into this project's architecture.

---

## WHAT TO BUILD

Add voice mode support so that the existing 4-mode selector in the frontend actually works.
The three voice modes to implement:

| Mode | STT | TTS |
|------|-----|-----|
| Voice → Text | Yes (mic input) | No (text display) |
| Text → Voice | No (typed input) | Yes (TTS playback) |
| Voice → Voice | Yes (mic input) | Yes (TTS playback) |

Text → Text already works. Do not break it.

---

## ARCHITECTURE: HOW IT CONNECTS

The voice layer sits between the browser and the existing agent core.
The agent core (DecisionEngine, StateManager, tools, Summarizer) does NOT change.

```
Browser mic → WebSocket → STT → existing /respond logic → TTS → WebSocket → Browser speaker
```

Create a new WebSocket endpoint: `POST /api/voice/ws/{session_id}`

This endpoint:
1. Accepts binary audio frames from the browser (PCM or WebM/Opus)
2. Runs STT to get the employee's answer as text
3. Feeds that text into the SAME session state that the text API uses
   (reuse the existing LiveSession from api/session_store.py)
4. Gets the next question (or summary) back
5. Runs TTS on that question text
6. Streams audio back to the browser

The session state is SHARED between text and voice paths. A session started
via POST /api/session/start can then be continued via either the text
POST /api/session/{id}/respond OR the voice WebSocket. Same session_id.

---

## STT IMPLEMENTATION

Reference: `voice_engine_MVP/src/stt_handler.py`

For the interview bot context, simplify significantly:

- Use `faster-whisper` directly (no RealtimeSTT dependency needed)
- Model: `base.en` — good accuracy, reasonable speed
- NO real-time streaming transcription needed (interview = turn-based, not free-form chat)
- NO barge-in detection needed (the interviewer speaks, then waits — clean turns)
- NO VAD complexity — use simple silence detection or fixed chunking
- Process audio in complete utterance chunks, not frame-by-frame

The flow is simple:
1. Browser sends audio (triggered by user releasing a button OR silence detection client-side)
2. Backend receives the audio blob
3. Transcribe with Whisper → get text
4. Pass text to existing respond logic
5. Done

Add to `api/voice/stt.py`:
```python
class InterviewSTT:
    """Simplified Whisper STT for interview turn-taking."""
    # Load faster-whisper model once at startup
    # transcribe(audio_bytes) → str
```

---

## TTS IMPLEMENTATION

Reference: `voice_engine_MVP/src/kokoro_tts_engine.py`

For the interview bot context, use Kokoro-82M local GPU TTS. Simplify it
significantly from the voice_engine_MVP version:

- Engine: Kokoro-82M via `RealtimeTTS[kokoro]`
- Voice: `af_heart` (warm American female — same as voice_engine_MVP default)
- NO barge-in detection needed (interviewer speaks, employee listens, clean turns)
- NO real-time streaming queue — synthesize the full question to audio bytes, then send
- NO PyAudio playback on the server — generate audio bytes and stream to browser
- CUDA auto-detected (uses GPU if available, falls back to CPU silently)
- Fallback: pyttsx3 if Kokoro fails to load (e.g. missing torch)

The key difference from voice_engine_MVP's Kokoro usage: that system plays audio
locally via PyAudio. Here, you generate audio bytes in memory and send them over
WebSocket to the browser. The browser handles playback via AudioContext.

Add to `api/voice/tts.py`:
```python
class InterviewTTS:
    """Kokoro-82M TTS for interview question playback.
    Generates audio bytes in memory — browser handles playback.
    """
    # initialize() → loads Kokoro model (call once at startup)
    # synthesize(text) → bytes (WAV/PCM)
    # Falls back to pyttsx3 if Kokoro unavailable
```

No API key required — Kokoro runs entirely locally. First run downloads ~170MB model.

---

## WEBSOCKET ENDPOINT

Add to `api/voice/__init__.py` and wire into `api/main.py`:

```python
@app.websocket("/api/voice/ws/{session_id}")
async def voice_interview(websocket: WebSocket, session_id: str, mode: str = "voice_voice"):
    """
    WebSocket for voice interview sessions.
    mode: "voice_text" | "text_voice" | "voice_voice"

    Message protocol (JSON control + binary audio):
    - Client sends: {"type": "audio", "data": <base64 audio>} OR binary blob
    - Client sends: {"type": "text", "data": "typed answer"} (text_voice mode)
    - Server sends: {"type": "question", "text": "...", "question_number": N, "total": 6}
    - Server sends: {"type": "audio", "data": <base64 audio>} (when TTS active)
    - Server sends: {"type": "complete", "summary": {...}}
    - Server sends: {"type": "crisis"}
    - Server sends: {"type": "error", "message": "..."}
    """
```

The endpoint reuses the existing `_get_live()` and `_evaluate_response()` helpers
from `api/main.py`. The session must already exist (started via POST /api/session/start).

---

## FRONTEND CHANGES

Activate the 3 voice mode cards in `frontend/src/components/ModeSelector.jsx`.
Remove the "Soon" badge and the toast. Instead, when a voice mode is selected:
1. Start a session via POST /api/session/start (same as text mode)
2. Navigate to a new `VoiceInterface` component instead of `ChatInterface`

Create `frontend/src/components/VoiceInterface.jsx`:

- Shows the current question as large readable text (always visible regardless of mode)
- Shows a mic button for voice input modes (Voice→Text, Voice→Voice)
  - Press and hold to record, release to submit
  - OR use VAD: auto-detect when user stops speaking (configurable)
- Shows a text input for Text→Voice mode (same as ChatInterface but also plays TTS)
- For TTS modes: auto-plays the question audio when it arrives via WebSocket
- Shows a waveform or simple animated indicator while recording / while AI is speaking
- Shows conversation history as text (all modes show text transcript)
- ProgressBar stays the same

Keep it simple. No fancy waveform library needed — a CSS animation is fine.

Browser audio capture: use the standard Web Audio API (`MediaRecorder`) to capture
mic audio as WebM/Opus or PCM. Send as binary over the WebSocket.

Browser audio playback: use `AudioContext` to play the received PCM/MP3 bytes.

Add to `frontend/src/api.js`:
```javascript
export function createVoiceSocket(sessionId, mode, handlers) {
  // handlers: { onQuestion, onAudio, onComplete, onCrisis, onError }
  // Returns: { send(audioBlob), sendText(text), close() }
}
```

---

## FILE STRUCTURE TO CREATE

```
api/voice/
├── __init__.py          ← WebSocket endpoint + router
├── stt.py               ← InterviewSTT (faster-whisper)
└── tts.py               ← InterviewTTS (Cartesia + fallback)

frontend/src/components/
└── VoiceInterface.jsx   ← Voice interview UI
```

Modify:
- `api/main.py` — include voice router
- `frontend/src/components/ModeSelector.jsx` — activate voice cards
- `frontend/src/App.jsx` — route to VoiceInterface for voice modes
- `frontend/src/api.js` — add createVoiceSocket
- `requirements.txt` — add faster-whisper, pyttsx3

---

## WHAT NOT TO DO

Do not replicate the full voice_engine_MVP complexity. That system is built for a
free-flowing real-time voice assistant with:
- Continuous listening + VAD + barge-in
- Full-duplex speaker+mic simultaneously
- Echo suppression
- Multi-provider LLM fallback chain

None of that is needed here. This is a turn-based interview:
- Employee speaks → presses button (or brief silence) → sends audio
- System transcribes → processes → responds
- System plays question audio → employee listens
- Repeat

The simplest correct implementation beats the most sophisticated broken one.

Do not add: barge-in, real-time streaming transcription, echo cancellation,
PyAudio server-side playback, RealtimeSTT, the full Kokoro queue/consumer
architecture from voice_engine_MVP (that plays locally — here you generate
bytes and send to browser instead).

---

## CONSTRAINTS

- Do not modify agent/, storage/, utils/, config.py, or main.py (CLI)
- Do not break the existing Text→Text flow
- The voice WebSocket must reuse existing LiveSession state (not create a parallel state)
- CARTESIA_API_KEY is optional — fall back gracefully if not set
- OPENAI_API_KEY is required for the existing agent (unchanged)
- Add `faster-whisper`, `pyttsx3`, and `RealtimeTTS[kokoro]` to requirements.txt
- The WebSocket endpoint must handle disconnections cleanly (no orphaned sessions)
- Health check at GET /api/health should indicate voice capability:
  `{"status": "ok", "voice": true/false}` based on whether Whisper and Kokoro loaded
- Kokoro requires `torch` — check if available, fall back to pyttsx3 if not
- CARTESIA_API_KEY is NOT needed — Kokoro is fully local

---

## ENVIRONMENT

Add to `.env.example`:
```
# Voice Engine (Phase 2)
# Kokoro TTS runs fully locally — no API key needed.
# First run downloads ~170MB model automatically.

# Whisper model size: tiny.en | base.en | small.en (default: base.en)
WHISPER_MODEL=base.en

# Kokoro voice (default: af_heart)
# Options: af_heart, af_bella, af_sarah, am_adam, bm_george, bf_emma
KOKORO_VOICE=af_heart
```

---

## HOW TO RUN (add to README)

Voice modes require no additional setup — Kokoro runs fully locally with no API key.
Whisper also runs locally. Both models are downloaded automatically on first run.

GPU (CUDA) is auto-detected for Kokoro. If unavailable, CPU is used (slower but works).

```bash
# Backend (same command, voice WebSocket included automatically)
uvicorn api.main:app --reload --port 8000

# Frontend (same command)
cd frontend && npm run dev
```

---

## DELIVERABLE CHECKLIST

- [ ] api/voice/stt.py — InterviewSTT with faster-whisper
- [ ] api/voice/tts.py — InterviewTTS with Cartesia + pyttsx3 fallback
- [ ] api/voice/__init__.py — WebSocket endpoint
- [ ] api/main.py updated — voice router included
- [ ] GET /api/health returns voice capability flag
- [ ] frontend/src/components/VoiceInterface.jsx — voice interview UI
- [ ] ModeSelector.jsx — all 4 modes active (voice modes connect to VoiceInterface)
- [ ] App.jsx — routes voice modes to VoiceInterface
- [ ] api.js — createVoiceSocket helper
- [ ] requirements.txt — faster-whisper, RealtimeTTS[kokoro], pyttsx3 added
- [ ] .env.example — WHISPER_MODEL and KOKORO_VOICE documented
- [ ] Text→Text mode still works unchanged

---