# Voice Engine — Implementation

Voice mode support for the Exit Interview Agent. Uses local models (no API keys required).

## Architecture

```
Browser mic → WebSocket → STT (faster-whisper) → existing respond logic → TTS (Kokoro) → WebSocket → Browser speaker
```

## Components

### STT (`stt.py`)

- **Engine:** faster-whisper
- **Model:** configurable via `WHISPER_MODEL` env var (default: `base.en`)
- **Input format:** WebM/Opus (browser-native MediaRecorder)
- **Conversion:** pydub + ffmpeg for WebM → PCM
- **Device:** auto-detects CUDA, falls back to CPU with int8 quantization

### TTS (`tts.py`)

- **Engine:** Kokoro-82M via RealtimeTTS
- **Voice:** configurable via `KOKORO_VOICE` env var (default: `af_heart`)
- **Output:** WAV bytes sent to browser via WebSocket
- **Fallback:** pyttsx3 if Kokoro unavailable
- **Device:** auto-detects CUDA

### WebSocket (`__init__.py`)

**Endpoint:** `/api/voice/ws/{session_id}?mode={mode}`

**Modes:**
- `voice_text` — STT only (speak answers, read questions)
- `text_voice` — TTS only (type answers, hear questions)
- `voice_voice` — full STT + TTS

**Message Protocol:**

| Direction | Type | Payload |
|-----------|------|---------|
| Client → Server | audio | Binary WebM blob or `{type: "audio", data: "<base64>"}` |
| Client → Server | text | `{type: "text", data: "typed answer"}` |
| Server → Client | question | `{type: "question", text: "...", audio?: "<base64>", question_number, total}` |
| Server → Client | complete | `{type: "complete", summary: {...}}` |
| Server → Client | crisis | `{type: "crisis"}` |
| Server → Client | error | `{type: "error", message: "..."}` |

## Configuration

```bash
# In .env
WHISPER_MODEL=base.en        # tiny.en | base.en | small.en
KOKORO_VOICE=af_heart        # af_heart | af_bella | af_sarah | am_adam | bm_george | bf_emma
```

## Dependencies

```
faster-whisper>=1.0.0
pyttsx3>=2.90
pydub>=0.25.0
```

Plus system ffmpeg for audio conversion.
