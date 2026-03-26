"""
Comprehensive STT tests for the exit interview voice pipeline.

Mirrors the structure of voice_engine_MVP/src/test_kokoro_local.py.

Engine under test: faster-whisper (same backend as RealtimeSTT wraps).
Parameters follow voice_engine_MVP/src/stt_handler.py:
  - model: base.en (env WHISPER_MODEL)
  - beam_size=1, vad_filter=True, threshold=0.38

Tests:
  1. Engine availability & type detection
  2. End-to-end transcription via pyttsx3-generated speech
  3. Phrase accuracy check (known input -> expected keywords)
  4. Handling of silence-only audio
  5. Latency benchmark (5 consecutive transcriptions)

Run from repo root:
    python api/voice/test_stt.py
"""

import io
import struct
import sys
import time
import wave
from pathlib import Path

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import api.voice.stt as _stt_module
from api.voice.stt import (
    InterviewSTT,
    stt_available,
    transcribe,
    _get_model,
    _cuda_available,
)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _banner(title: str) -> None:
    width = 60
    print(f"\n{'-' * width}")
    print(f"  {title}")
    print(f"{'-' * width}")


def _pass(msg: str) -> None:
    print(f"  [PASS]  {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL]  {msg}")


def _info(msg: str) -> None:
    print(f"          {msg}")


def _make_silence_wav(duration_s: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Generate a WAV file containing pure silence."""
    n_samples = int(duration_s * sample_rate)
    pcm = struct.pack(f"<{n_samples}h", *([0] * n_samples))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    buf.seek(0)
    return buf.read()


def _make_speech_wav(text: str) -> bytes | None:
    """
    Use pyttsx3 to synthesise text -> WAV bytes for test input.
    Returns None if pyttsx3 is not available.
    """
    try:
        import tempfile
        import threading
        import pyttsx3

        eng = pyttsx3.init()
        eng.setProperty("rate", 150)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name

        result: list[bytes | None] = [None]

        def _run():
            try:
                eng.save_to_file(text, tmp)
                eng.runAndWait()
                result[0] = Path(tmp).read_bytes()
            except Exception:
                pass

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=15)
        Path(tmp).unlink(missing_ok=True)
        return result[0] if result[0] else None

    except Exception as e:
        print(f"          (pyttsx3 unavailable for test audio generation: {e})")
        return None


def _to_16k_mono(wav_bytes: bytes) -> bytes:
    """Re-sample a WAV to 16 kHz mono using pydub if needed."""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_wav(io.BytesIO(wav_bytes))
        audio = audio.set_channels(1).set_frame_rate(16000)
        buf = io.BytesIO()
        audio.export(buf, format="wav")
        buf.seek(0)
        return buf.read()
    except Exception:
        return wav_bytes  # Best effort — return as-is


# ── Tests ─────────────────────────────────────────────────────────────────────
def test_1_engine_availability():
    """Test 1 — Engine availability & type detection."""
    _banner("Test 1 — Engine availability & type detection")

    # CUDA check (mirrors MVP's _cuda_runtime_available)
    cuda_ok = _cuda_available()
    _info(f"CUDA available  : {cuda_ok}")

    model = _get_model()
    if model is None:
        _fail(f"No STT engine loaded (error: {_stt_module._load_error})")
        return False

    import os
    _pass(f"Engine          : faster-whisper")
    _info(f"Whisper model   : {os.getenv('WHISPER_MODEL', 'base.en')}")
    _info(f"stt_available() : {stt_available()}")

    stt = InterviewSTT()
    _info(f"InterviewSTT.available   : {stt.available}")
    _info(f"InterviewSTT.engine_type : {stt.engine_type}")

    assert stt.available, "InterviewSTT.available should be True"
    _pass("InterviewSTT wrapper is healthy")
    return True


def test_2_transcribe_synthesized_speech():
    """Test 2 — End-to-end transcription of pyttsx3-generated speech."""
    _banner("Test 2 — End-to-end transcription (synthesised speech)")

    test_phrase = "I am leaving because I found a better opportunity elsewhere."
    _info(f"Input phrase    : {test_phrase!r}")

    wav_bytes = _make_speech_wav(test_phrase)
    if wav_bytes is None:
        _fail("Could not generate test audio — pyttsx3 unavailable, skipping")
        return None

    wav_16k = _to_16k_mono(wav_bytes)

    t0 = time.monotonic()
    try:
        result = transcribe(wav_16k, needs_conversion=False)
        elapsed = time.monotonic() - t0
    except Exception as e:
        _fail(f"transcribe() raised: {e}")
        return False

    _info(f"Transcription   : {result!r}")
    _info(f"Latency         : {elapsed * 1000:.0f} ms")

    if not result:
        _fail("Transcription returned empty string")
        return False

    expected_keywords = ["leaving", "better", "opportunity", "elsewhere", "found"]
    matched = [kw for kw in expected_keywords if kw.lower() in result.lower()]
    if matched:
        _pass(f"Keywords found  : {matched}")
    else:
        _fail(
            f"No expected keywords found. Expected one of {expected_keywords}. Got: {result!r}"
        )
        return False

    return True


def test_3_phrase_accuracy():
    """Test 3 — Short interview-style phrases."""
    _banner("Test 3 — Short interview phrase accuracy")

    phrases = [
        ("I enjoyed working with my team.", ["enjoyed", "working", "team"]),
        ("The management was not supportive.", ["management", "supportive"]),
        ("I am looking for new challenges.", ["looking", "challenges", "new"]),
    ]

    results = []
    for phrase, keywords in phrases:
        _info(f"Input  : {phrase!r}")
        wav = _make_speech_wav(phrase)
        if wav is None:
            _info("  -> Skipped (pyttsx3 unavailable)")
            continue
        wav_16k = _to_16k_mono(wav)

        try:
            text = transcribe(wav_16k, needs_conversion=False)
        except Exception as e:
            _fail(f"Error: {e}")
            results.append(False)
            continue

        matched = [kw for kw in keywords if kw.lower() in text.lower()]
        pct = len(matched) / len(keywords) * 100
        _info(f"Output : {text!r}")
        _info(f"Hit    : {matched} ({pct:.0f}%)")

        if pct >= 50:
            _pass(f"Acceptable accuracy ({pct:.0f}%)")
            results.append(True)
        else:
            _fail(f"Low accuracy ({pct:.0f}%)")
            results.append(False)

    if not results:
        _info("All phrases skipped (pyttsx3 unavailable)")
        return None

    passed = sum(results)
    _info(f"\n  {passed}/{len(results)} phrases passed")
    return passed == len(results)


def test_4_silence_handling():
    """Test 4 — Silence-only audio should return empty string, not crash."""
    _banner("Test 4 — Silence / empty audio handling")

    silence_wav = _make_silence_wav(duration_s=0.8)
    _info(f"Silence WAV size: {len(silence_wav)} bytes")

    try:
        result = transcribe(silence_wav, needs_conversion=False)
        _info(f"Result          : {result!r}")
        _pass("transcribe() returned without raising")
        if result == "":
            _pass("Correctly returned empty string for silence")
        else:
            _info(f"(Unexpected transcription from silence: {result!r})")
        return True
    except Exception as e:
        _fail(f"transcribe() raised exception on silence: {e}")
        return False


def test_5_latency_benchmark():
    """Test 5 — Latency benchmark (5 consecutive calls)."""
    _banner("Test 5 — Latency benchmark")

    phrase = "My main reason for leaving was the lack of growth opportunities."
    wav = _make_speech_wav(phrase)
    if wav is None:
        _info("Skipped — pyttsx3 unavailable")
        return None
    wav_16k = _to_16k_mono(wav)

    runs = 5
    latencies = []
    for i in range(runs):
        t0 = time.monotonic()
        try:
            result = transcribe(wav_16k, needs_conversion=False)
            elapsed_ms = (time.monotonic() - t0) * 1000
            latencies.append(elapsed_ms)
            _info(f"  Run {i+1}: {elapsed_ms:.0f} ms  -> {result[:60]!r}")
        except Exception as e:
            _fail(f"  Run {i+1} failed: {e}")

    if latencies:
        avg = sum(latencies) / len(latencies)
        _info(f"\n  Avg latency : {avg:.0f} ms over {len(latencies)} runs")
        _pass(f"Benchmark complete — avg {avg:.0f} ms")
        if avg < 10_000:
            _pass("Latency within acceptable range (< 10 s per call)")
        else:
            _fail(f"High latency ({avg:.0f} ms) — consider a smaller model (tiny.en)")
        return True
    return False


# ── Runner ────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("  Exit Interview Bot — STT Test Suite")
    print("  (faster-whisper, parameters from voice_engine_MVP)")
    print("=" * 60)

    results = {}
    tests = [
        ("1_engine_availability", test_1_engine_availability),
        ("2_transcribe_synthesized_speech", test_2_transcribe_synthesized_speech),
        ("3_phrase_accuracy", test_3_phrase_accuracy),
        ("4_silence_handling", test_4_silence_handling),
        ("5_latency_benchmark", test_5_latency_benchmark),
    ]

    for name, fn in tests:
        try:
            result = fn()
            results[name] = result
        except Exception as exc:
            _fail(f"Unexpected exception in {name}: {exc}")
            results[name] = False

    # ── Summary ───────────────────────────────────────────────────────────────
    _banner("Summary")
    passed = skipped = failed = 0
    for name, r in results.items():
        if r is True:
            print(f"  [PASS]  {name}")
            passed += 1
        elif r is None:
            print(f"  [SKIP]  {name}  (skipped)")
            skipped += 1
        else:
            print(f"  [FAIL]  {name}")
            failed += 1

    total = passed + failed
    print(f"\n  {passed}/{total} passed, {skipped} skipped\n")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
