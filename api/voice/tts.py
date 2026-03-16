"""
TTS for exit interview question playback.

Tries engines in order:
  1. Kokoro-82M via RealtimeTTS — local, GPU-accelerated, best quality
  2. pyttsx3 — offline, Windows SAPI5/eSpeak, lightweight fallback

Generates WAV bytes in memory; browser handles playback via WebSocket.
"""

import io
import logging
import os
import wave

logger = logging.getLogger(__name__)

# Lazy-loaded globals
_engine = None
_engine_type = None   # "kokoro" | "pyttsx3" | None
_engine_loaded = False
_load_error = None
_kokoro_sample_rate = 24000


def _get_engine():
    """Lazy-load the TTS engine on first use."""
    global _engine, _engine_type, _engine_loaded, _load_error

    if _engine_loaded:
        return _engine, _engine_type

    voice = os.getenv("KOKORO_VOICE", "af_heart")

    # --- Try Kokoro via RealtimeTTS ---
    try:
        from RealtimeTTS import TextToAudioStream, KokoroEngine  # noqa: F401 (check import)

        engine = KokoroEngine(voice=voice)
        _engine = engine
        _engine_type = "kokoro"
        _engine_loaded = True
        logger.info(f"Kokoro TTS loaded with voice '{voice}'")
        return _engine, _engine_type

    except Exception as e:
        logger.warning(f"Kokoro TTS not available: {e}. Trying pyttsx3...")

    # --- Fallback to pyttsx3 ---
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", 150)
        _engine = engine
        _engine_type = "pyttsx3"
        _engine_loaded = True
        logger.info("pyttsx3 TTS loaded as fallback")
        return _engine, _engine_type

    except Exception as e:
        _load_error = str(e)
        _engine_loaded = True
        logger.error(f"No TTS engine available: {e}")
        return None, None


def tts_available() -> bool:
    """Check if TTS is available."""
    _get_engine()
    return _engine is not None


def _synthesize_kokoro(engine, text: str) -> bytes:
    """
    Capture Kokoro TTS output as WAV bytes.

    TextToAudioStream.on_audio_chunk receives raw PCM chunks (constructor arg).
    play(muted=True) processes synthesis without sending to local speakers.
    play() is blocking — when it returns, all chunks have been delivered.
    """
    from RealtimeTTS import TextToAudioStream

    chunks: list[bytes] = []

    stream = TextToAudioStream(engine, on_audio_chunk=lambda c: chunks.append(bytes(c)))
    stream.feed(text)
    stream.play(muted=True)  # blocking; muted=True skips local speaker output

    if not chunks:
        raise ValueError("Kokoro returned no audio chunks")

    raw_pcm = b"".join(chunks)

    # Kokoro output: 24 kHz, mono, 16-bit PCM
    sample_rate = getattr(engine, "SAMPLE_RATE", _kokoro_sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)   # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(raw_pcm)
    buf.seek(0)
    return buf.read()


def _synthesize_pyttsx3(engine, text: str) -> bytes:
    """Synthesize with pyttsx3 and return WAV bytes via a temp file."""
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name

    try:
        engine.save_to_file(text, temp_path)
        engine.runAndWait()
        with open(temp_path, "rb") as f:
            return f.read()
    finally:
        Path(temp_path).unlink(missing_ok=True)


def synthesize(text: str) -> bytes:
    """
    Synthesize text to WAV audio bytes.

    Returns:
        WAV bytes ready to base64-encode and send to browser.

    Raises:
        RuntimeError: If no TTS engine is available.
        ValueError: If synthesis fails.
    """
    engine, engine_type = _get_engine()

    if engine is None:
        raise RuntimeError(f"TTS not available: {_load_error}")

    try:
        if engine_type == "kokoro":
            return _synthesize_kokoro(engine, text)
        else:
            return _synthesize_pyttsx3(engine, text)

    except Exception as e:
        logger.error(f"TTS synthesis failed ({engine_type}): {e}")

        # If Kokoro failed at synthesis time, try pyttsx3 as emergency fallback
        if engine_type == "kokoro":
            logger.info("Kokoro synthesis failed — trying pyttsx3 emergency fallback")
            try:
                import pyttsx3
                fb_engine = pyttsx3.init()
                fb_engine.setProperty("rate", 150)
                return _synthesize_pyttsx3(fb_engine, text)
            except Exception as e2:
                logger.error(f"pyttsx3 fallback also failed: {e2}")

        raise ValueError(f"TTS synthesis failed: {e}")


class InterviewTTS:
    """Wrapper class for TTS operations in the interview context."""

    def __init__(self):
        engine, engine_type = _get_engine()
        self._available = engine is not None
        self._engine_type = engine_type

    @property
    def available(self) -> bool:
        return self._available

    @property
    def engine_type(self) -> str | None:
        return self._engine_type

    def synthesize(self, text: str) -> bytes:
        return synthesize(text)
