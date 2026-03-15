# Phase 2 — Voice Engine

Phase 2 will add a WebSocket endpoint here for real-time voice interviews.

## Planned Architecture

The voice engine will use:
- **STT (Speech-to-Text):** Whisper / RealtimeSTT — streams mic audio in, returns transcribed text
- **TTS (Text-to-Speech):** Cartesia AI — converts AI-generated questions to natural speech

## How It Connects

The voice WebSocket will:
1. Accept a streaming audio connection from the frontend
2. Run STT on incoming audio chunks to get the employee's answer as text
3. Feed that text into the **same agent core** (DecisionEngine, tools, Summarizer)
4. Stream TTS audio of the next question back to the frontend

The 4-mode selector in the frontend will activate voice modes once this endpoint
is live. The frontend already checks `/api/health` and will dynamically unlock
voice modes when the voice WebSocket is detected.

## Modes Unlocked

| Mode | WebSocket Path |
|------|---------------|
| Voice → Text | `/api/voice/ws` (STT only, text display) |
| Text → Voice | `/api/voice/ws` (text input, TTS output) |
| Voice → Voice | `/api/voice/ws` (full STT + TTS) |
