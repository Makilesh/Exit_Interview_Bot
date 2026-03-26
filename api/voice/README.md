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

---

## Quick Start

1. Install dependencies from main `requirements.txt` + Kokoro: `pip install "realtimetts[kokoro]"`
2. Verify setup: `python check_environment.py`
3. Clear or unset `OPENAI_API_KEY` to disable cloud LLM and use Ollama
4. Start backend: `uvicorn api.main:app --reload --port 8000`
5. Start frontend: `cd frontend && npm run dev` (opens http://localhost:5173)
6. Select a voice mode and test

---

## Testing

- **STT:** `python api/voice/test_stt.py` — test Whisper transcription on an audio file
- **TTS:** `python api/voice/test_tts.py` — test Kokoro synthesis and save WAV output
- Both scripts auto-detect CUDA; output files go to `api/voice/test_output/`

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `Connection failed` on first load | WebSocket handshake timeout | Refresh browser; check backend is running |
| Corrupted audio / ffmpeg error | Audio blob sent before encoding finished | Browser hard refresh (Ctrl+Shift+R) |
| Kokoro unavailable | RealtimeTTS not installed | `pip install "realtimetts[kokoro]"` |
| ffmpeg not found | System ffmpeg missing | Install via `choco`, `brew`, or apt |
| CUDA not detected on GPU | Device check failed | Verify NVIDIA drivers installed |

See [VOICE_TROUBLESHOOTING.md](../../VOICE_TROUBLESHOOTING.md) and [FINAL_SOLUTION.md](../../FINAL_SOLUTION.md) for detailed fixes.

---

## Known Limitations

- **STT:** Accuracy depends on audio quality and Whisper model size (tiny < small < base)
- **TTS:** Kokoro latency ~100ms per sentence; pyttsx3 fallback slower on Windows
- **WebSocket:** Single-session per connection (no multiplexing)
- **Model size:** base.en is 140 MB; Kokoro is ~200 MB — CPU inference is slower

---

## Performance

- **CPU (int8):** ~2–3 sec/10-sec audio (STT), ~200–300ms per sentence (TTS)
- **GPU (float16):** ~0.5–1 sec/10-sec audio (STT), ~50–100ms per sentence (TTS)
- **Latency breakdown:** audio upload → STT → LLM decision → TTS → audio download ≈ 5–10 sec total (CPU)
