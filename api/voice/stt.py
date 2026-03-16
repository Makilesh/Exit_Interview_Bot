"""
Simplified Whisper STT for turn-based exit interviews.

Uses faster-whisper for efficient transcription. No real-time streaming,
VAD complexity, or barge-in detection — interview is turn-based.
"""

import io
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy-loaded globals
_model = None
_model_loaded = False
_load_error = None


def _get_model():
    """Lazy-load the Whisper model on first use."""
    global _model, _model_loaded, _load_error

    if _model_loaded:
        return _model

    model_name = os.getenv("WHISPER_MODEL", "base.en")

    try:
        from faster_whisper import WhisperModel

        # Auto-detect CUDA, fallback to CPU with int8
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
                logger.info(f"Loading Whisper model '{model_name}' on CUDA")
            else:
                device = "cpu"
                compute_type = "int8"
                logger.info(f"Loading Whisper model '{model_name}' on CPU (int8)")
        except ImportError:
            device = "cpu"
            compute_type = "int8"
            logger.info(f"Loading Whisper model '{model_name}' on CPU (int8, torch not available)")

        _model = WhisperModel(model_name, device=device, compute_type=compute_type)
        _model_loaded = True
        logger.info(f"Whisper model '{model_name}' loaded successfully")
        return _model

    except Exception as e:
        _load_error = str(e)
        _model_loaded = True  # Mark as attempted
        logger.error(f"Failed to load Whisper model: {e}")
        return None


def stt_available() -> bool:
    """Check if STT is available (model loaded successfully)."""
    _get_model()
    return _model is not None


def _convert_to_wav(audio_bytes: bytes) -> bytes:
    """
    Convert browser audio (WebM/Opus, OGG, MP4) to 16 kHz mono WAV.

    Tries WebM format first (Chrome/Edge MediaRecorder default), then lets
    pydub auto-detect so Safari (MP4/AAC) and Firefox (OGG) also work.
    ffmpeg must be on PATH.
    """
    try:
        from pydub import AudioSegment

        # Try WebM explicitly first, then auto-detect
        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="webm")
        except Exception:
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes))

        audio = audio.set_channels(1).set_frame_rate(16000)
        wav_buffer = io.BytesIO()
        audio.export(wav_buffer, format="wav")
        wav_buffer.seek(0)
        return wav_buffer.read()

    except Exception as e:
        err = str(e).lower()
        if any(k in err for k in ("ffmpeg", "ffprobe", "couldn't find", "not installed")):
            raise ValueError(
                "ffmpeg is not on PATH. Install ffmpeg and add it to PATH, "
                "then restart the server."
            )
        raise ValueError(f"Failed to convert audio: {e}")


def transcribe(audio_bytes: bytes, needs_conversion: bool = True) -> str:
    """
    Transcribe audio bytes to text.

    Args:
        audio_bytes: Raw audio bytes from browser (WebM/Opus/OGG/MP4) or WAV.
        needs_conversion: If True, convert to WAV first via pydub (requires ffmpeg).

    Returns:
        Transcribed text string (empty string if nothing detected).

    Raises:
        RuntimeError: If STT is not available.
        ValueError: If audio conversion or transcription fails.
    """
    model = _get_model()
    if model is None:
        raise RuntimeError(f"STT not available: {_load_error}")

    try:
        wav_bytes = _convert_to_wav(audio_bytes) if needs_conversion else audio_bytes

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            temp_path = f.name

        try:
            segments, _info = model.transcribe(
                temp_path,
                beam_size=1,
                language="en",
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments)
            logger.debug(f"Transcribed {len(audio_bytes)} bytes -> '{text[:60]}'")
            return text.strip()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise ValueError(f"Transcription failed: {e}")


class InterviewSTT:
    """
    Wrapper class for STT operations in the interview context.

    Provides a simple interface for the WebSocket handler.
    """

    def __init__(self):
        """Initialize STT (triggers lazy model loading)."""
        self._available = stt_available()

    @property
    def available(self) -> bool:
        """Check if STT is ready."""
        return self._available

    def transcribe(self, audio_bytes: bytes, needs_conversion: bool = True) -> str:
        """Transcribe audio to text. See module-level transcribe() for details."""
        return transcribe(audio_bytes, needs_conversion)
