"""
TTS for exit interview question playback.

Engine priority (mirrors voice_engine_MVP/src/tts_handler_optimized.py):
  1. Kokoro-82M via RealtimeTTS   — local GPU/CPU, best quality, ~100 ms latency
  2. pyttsx3 SAPI5               — offline Windows fallback, always available

Server-side usage: audio is captured as WAV bytes (muted=True, on_audio_chunk
callback) so the WebSocket handler can base64-encode and stream to the browser.
The browser's AudioContext handles playback — no local speakers involved.
"""

import io
import logging
import os
import wave

logger = logging.getLogger(__name__)

# ── Lazy-loaded singleton ─────────────────────────────────────────────────────
_engine       = None
_engine_type: str | None = None   # "kokoro" | "pyttsx3" | None
_engine_loaded = False
_load_error: str | None = None

_KOKORO_SAMPLE_RATE = 24000   # Hz — Kokoro-82M native output rate


# ── Engine initialisation ─────────────────────────────────────────────────────
def _get_engine():
    """Lazy-load TTS engine.  Returns (engine, engine_type)."""
    global _engine, _engine_type, _engine_loaded, _load_error

    if _engine_loaded:
        return _engine, _engine_type

    # Read configuration from environment (matching voice_engine_MVP config.py)
    voice = os.getenv("KOKORO_VOICE", "af_heart")
    speed = float(os.getenv("KOKORO_SPEED", "1.0"))

    # ── Primary: KokoroEngine via RealtimeTTS ─────────────────────────────────
    # Constructor mirrors voice_engine_MVP/src/kokoro_tts_engine.py:
    #   self._engine = KokoroEngine(voice=self.voice_config.voice,
    #                               default_speed=self.voice_config.speed)
    try:
        from RealtimeTTS import KokoroEngine

        engine = KokoroEngine(voice=voice, default_speed=speed)
        _engine = engine
        _engine_type = "kokoro"
        _engine_loaded = True
        logger.info(f"Kokoro TTS ready — voice='{voice}', speed={speed}")
        return _engine, _engine_type

    except Exception as e:
        logger.warning(f"Kokoro TTS unavailable: {e}. Trying pyttsx3...")

    # ── Fallback: pyttsx3 SAPI5 ───────────────────────────────────────────────
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", 150)
        _engine = engine
        _engine_type = "pyttsx3"
        _engine_loaded = True
        logger.info("pyttsx3 TTS ready (SAPI5 fallback)")
        return _engine, _engine_type

    except Exception as e:
        _load_error = str(e)
        _engine_loaded = True
        logger.error(f"No TTS engine available: {e}")
        return None, None


# ── Synthesis implementations ─────────────────────────────────────────────────
def _synthesize_kokoro(engine, text: str) -> bytes:
    """
    Synthesize text to int16 PCM bytes at 24 kHz using KokoroEngine directly.

    Calls engine.synthesize() which is BLOCKING and places audio chunks
    (int16 PCM bytes) into engine.queue.  We drain the queue and pack the
    result into a WAV.

    This bypasses TextToAudioStream and AudioPlayer entirely — no audio
    output device is required, which is important in a server context.

    Pattern derived from voice_engine_MVP/src/kokoro_tts_engine.py and
    the KokoroEngine.synthesize() source (audio_int16 put onto engine.queue).
    """
    from queue import Queue

    if not text.strip():
        raise ValueError("Cannot synthesize empty text")

    # Give the engine a fresh queue so previous residual chunks don't bleed in
    engine.queue = Queue()

    ok = engine.synthesize(text)  # blocking — fills engine.queue
    if not ok:
        raise ValueError("KokoroEngine.synthesize() returned False")

    # Drain all audio chunks from the queue
    chunks: list[bytes] = []
    while not engine.queue.empty():
        chunks.append(engine.queue.get_nowait())

    if not chunks:
        raise ValueError("Kokoro returned no audio chunks")

    raw_pcm = b"".join(chunks)  # int16 PCM, 24 kHz, mono

    # get_stream_info() → (paInt16=8, channels=1, sample_rate=24000)
    try:
        _, _, sample_rate = engine.get_stream_info()
    except Exception:
        sample_rate = _KOKORO_SAMPLE_RATE

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)             # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(raw_pcm)
    buf.seek(0)
    return buf.read()


def _synthesize_pyttsx3(engine, text: str) -> bytes:
    """
    Synthesize with pyttsx3 via a threaded call with timeout.

    pyttsx3's runAndWait() drives a Windows SAPI5 COM message loop which can
    deadlock in scripts without a GUI event loop.  Running it in a daemon
    thread with join(timeout=30) prevents permanent hangs.
    """
    import tempfile
    import threading
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name

    result: list[bytes | None] = [None]
    exc:    list[Exception | None] = [None]

    def _run():
        try:
            engine.save_to_file(text, tmp)
            engine.runAndWait()
            data = Path(tmp).read_bytes()
            result[0] = data
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=30)

    Path(tmp).unlink(missing_ok=True)

    if t.is_alive():
        raise TimeoutError(
            "pyttsx3 synthesis timed out after 30 s — "
            "SAPI5 may be unavailable in this environment"
        )
    if exc[0]:
        raise exc[0]
    if not result[0]:
        raise ValueError("pyttsx3 returned empty audio")
    return result[0]


# ── Public API ────────────────────────────────────────────────────────────────
def tts_available() -> bool:
    """Return True if at least one TTS engine loaded successfully."""
    _, engine_type = _get_engine()
    return engine_type is not None


def synthesize(text: str) -> bytes:
    """
    Synthesize text → WAV bytes (ready to base64-encode for the browser).

    Raises:
        RuntimeError: No TTS engine available.
        ValueError:   Synthesis failed.
    """
    engine, engine_type = _get_engine()
    if engine is None:
        raise RuntimeError(f"TTS not available: {_load_error}")

    try:
        if engine_type == "kokoro":
            return _synthesize_kokoro(engine, text)
        return _synthesize_pyttsx3(engine, text)

    except Exception as e:
        logger.error(f"TTS synthesis failed ({engine_type}): {e}")

        # If Kokoro failed at synthesis time try pyttsx3 as emergency fallback
        if engine_type == "kokoro":
            logger.info("Kokoro synthesis failed — falling back to pyttsx3")
            try:
                import pyttsx3
                fb = pyttsx3.init()
                fb.setProperty("rate", 150)
                return _synthesize_pyttsx3(fb, text)
            except Exception as e2:
                logger.error(f"pyttsx3 emergency fallback also failed: {e2}")

        raise ValueError(f"TTS synthesis failed: {e}")


class InterviewTTS:
    """Wrapper used by the WebSocket voice handler."""

    def __init__(self):
        _, self._engine_type = _get_engine()

    @property
    def available(self) -> bool:
        return self._engine_type is not None

    @property
    def engine_type(self) -> str | None:
        return self._engine_type

    def synthesize(self, text: str) -> bytes:
        return synthesize(text)
