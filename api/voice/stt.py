"""
STT for exit interview voice input.

Engine: faster-whisper (the same Whisper backend that RealtimeSTT wraps internally).

For batch transcription of complete audio blobs sent over WebSocket, faster-whisper
is used directly.  RealtimeSTT's AudioToTextRecorder is designed for CONTINUOUS
microphone input and would block indefinitely when given a complete pre-recorded
blob — it expects an open-ended audio stream, not a single finished recording.

Model selection and VAD parameters mirror voice_engine_MVP/src/stt_handler.py:
  - model: tiny.en / small.en / base.en  (env WHISPER_MODEL, default base.en)
  - device: cuda → float16 | cpu → int8   (ctypes DLL check per MVP)
  - VAD filter: silero_vad, threshold=0.38
  - beam_size=1                            (fastest, same as MVP)

Audio pipeline: Browser WebM/Opus → 16 kHz mono WAV (pydub/ffmpeg) → temp file → transcribe.
"""

import io
import logging
import os
import wave

logger = logging.getLogger(__name__)

# ── Lazy-loaded singleton ─────────────────────────────────────────────────────
_model = None
_model_loaded = False
_load_error: str | None = None


# ── CUDA detection (ctypes approach from voice_engine_MVP/src/stt_handler.py) ─
def _cuda_available() -> bool:
    """
    Check CUDA runtime availability using ctypes DLL probing.
    This mirrors voice_engine_MVP's _cuda_runtime_available() which avoids
    importing torch (side-effects, slow) just to do a device check.
    """
    import ctypes
    for dll in ["cudart64_12.dll", "cudart64_120.dll", "cudart64_115.dll", "cublas64_12.dll"]:
        try:
            ctypes.WinDLL(dll)
            return True
        except OSError:
            continue
    # Secondary check via torch if it is already imported
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        pass
    return False


# ── Engine initialisation ─────────────────────────────────────────────────────
def _get_model():
    """Lazy-load WhisperModel; returns the model or None on failure."""
    global _model, _model_loaded, _load_error

    if _model_loaded:
        return _model

    # Model name → matches MVP's {"fast": "tiny.en", "balanced": "small.en", "accurate": "base.en"}
    model_name = os.getenv("WHISPER_MODEL", "base.en")

    cuda_ok = _cuda_available()
    device = "cuda" if cuda_ok else "cpu"
    compute_type = "float16" if cuda_ok else "int8"

    try:
        from faster_whisper import WhisperModel

        logger.info(
            f"Loading faster-whisper '{model_name}' on {device} ({compute_type})"
        )
        _model = WhisperModel(model_name, device=device, compute_type=compute_type)
        _model_loaded = True
        logger.info(f"faster-whisper '{model_name}' ready")
        return _model

    except Exception as e:
        _load_error = str(e)
        _model_loaded = True
        logger.error(f"Failed to load faster-whisper: {e}")
        return None


# ── ffmpeg availability check ─────────────────────────────────────────────────
_ffmpeg_checked = False
_ffmpeg_available = False


def _check_ffmpeg_available() -> bool:
    """
    Check if ffmpeg is available to pydub by attempting a test conversion.
    This is more reliable than checking PATH or which/where commands,
    as it tests the actual runtime environment pydub will use.
    """
    global _ffmpeg_checked, _ffmpeg_available

    if _ffmpeg_checked:
        return _ffmpeg_available

    try:
        from pydub import AudioSegment

        # Create a minimal test audio and try to export it
        test_audio = AudioSegment.silent(duration=100)  # 100ms silence
        buf = io.BytesIO()
        test_audio.export(buf, format="wav")

        _ffmpeg_available = True
        logger.info("ffmpeg availability check: PASSED")

    except Exception as e:
        _ffmpeg_available = False
        err_msg = str(e).lower()
        if any(k in err_msg for k in ("ffmpeg", "ffprobe", "couldn't find", "not installed")):
            logger.error(
                "ffmpeg availability check: FAILED - ffmpeg not found. "
                "If you just installed ffmpeg, close this terminal completely (X button), "
                "open a NEW terminal, and restart the server."
            )
        else:
            logger.error(f"ffmpeg availability check: FAILED - {e}")

    _ffmpeg_checked = True
    return _ffmpeg_available


# ── Audio conversion ──────────────────────────────────────────────────────────
def _convert_to_wav(audio_bytes: bytes) -> bytes:
    """
    Convert browser audio (WebM/Opus, OGG, MP4) to 16 kHz mono WAV.
    Requires ffmpeg on PATH (via pydub).
    """
    # Check ffmpeg availability first
    if not _check_ffmpeg_available():
        raise ValueError(
            "ffmpeg is not available. "
            "If you just installed ffmpeg, CLOSE this terminal completely (X button), "
            "open a NEW terminal, and restart the backend server. "
            "Running processes don't detect new PATH entries."
        )

    try:
        from pydub import AudioSegment

        logger.debug(f"Converting {len(audio_bytes)} bytes of audio to WAV")

        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="webm")
        except Exception as e:
            logger.debug(f"WebM parsing failed ({e}), trying auto-detect")
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes))

        audio = audio.set_channels(1).set_frame_rate(16000)
        buf = io.BytesIO()
        audio.export(buf, format="wav")
        buf.seek(0)
        wav_bytes = buf.read()
        logger.debug(f"Conversion successful: {len(wav_bytes)} bytes WAV")
        return wav_bytes

    except Exception as e:
        err = str(e).lower()
        # Only report "ffmpeg not on PATH" if it's actually a missing ffmpeg issue
        # Check for specific error patterns that indicate ffmpeg is unavailable
        if any(k in err for k in ("ffmpeg was not found", "ffmpeg: not found", "couldn't find ffmpeg",
                                   "ffprobe was not found", "ffprobe: not found", "couldn't find ffprobe",
                                   "filenotfounderror", "no such file")):
            raise ValueError(
                "ffmpeg is not on PATH. "
                "CLOSE this terminal completely (X button), "
                "open a NEW terminal, and restart the backend server."
            )
        # For other errors mentioning ffmpeg (e.g., codec issues, format problems),
        # report the actual error instead of claiming ffmpeg is missing
        raise ValueError(f"Audio conversion failed: {e}")


# ── Public API ────────────────────────────────────────────────────────────────
def stt_available() -> bool:
    """
    Return True if STT is fully available (Whisper model + ffmpeg).
    This checks both the Whisper model AND ffmpeg availability.
    """
    return _get_model() is not None and _check_ffmpeg_available()


def transcribe(audio_bytes: bytes, needs_conversion: bool = True) -> str:
    """
    Transcribe audio bytes to text.

    Args:
        audio_bytes: Raw audio from browser (WebM/Opus/OGG/MP4) or WAV.
        needs_conversion: If True, convert to 16 kHz mono WAV first.

    Returns:
        Transcribed text (empty string if nothing detected).

    Raises:
        RuntimeError: STT not available.
        ValueError:   Audio conversion or transcription failed.
    """
    model = _get_model()
    if model is None:
        raise RuntimeError(f"STT not available: {_load_error}")

    try:
        wav_bytes = _convert_to_wav(audio_bytes) if needs_conversion else audio_bytes

        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp = f.name

        try:
            # VAD parameters mirror MVP's silero_sensitivity=0.38
            segments, _info = model.transcribe(
                tmp,
                beam_size=1,                    # fastest, same as MVP
                language="en",
                vad_filter=True,
                vad_parameters={"threshold": 0.38},
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            logger.debug(f"Transcribed {len(audio_bytes)} bytes → '{text[:80]}'")
            return text
        finally:
            Path(tmp).unlink(missing_ok=True)

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise ValueError(f"Transcription failed: {e}")


class InterviewSTT:
    """Wrapper used by the WebSocket voice handler."""

    def __init__(self):
        self._available = stt_available()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def engine_type(self) -> str | None:
        return "faster_whisper" if self._available else None

    def transcribe(self, audio_bytes: bytes, needs_conversion: bool = True) -> str:
        return transcribe(audio_bytes, needs_conversion)
