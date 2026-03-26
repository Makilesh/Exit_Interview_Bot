"""
Comprehensive TTS tests for the exit interview voice pipeline.

Mirrors the structure of voice_engine_MVP/src/test_kokoro_local.py.

Tests:
  1. Engine availability & type detection
  2. Synthesize single phrase → valid WAV bytes
  3. WAV format validation (sample rate, channels, bit depth)
  4. Multiple interview-style phrases
  5. Edge cases (empty string, very long text)
  6. Latency benchmark (5 consecutive calls)

Run from repo root:
    python api/voice/test_tts.py
"""

import io
import sys
import time
import wave
from pathlib import Path

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Allow running from repo root without installing the package ───────────────
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import api.voice.tts as _tts_module
from api.voice.tts import (
    InterviewTTS,
    tts_available,
    synthesize,
    _get_engine,
    _KOKORO_SAMPLE_RATE,
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


def _parse_wav_info(wav_bytes: bytes) -> dict:
    """Extract WAV header info."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        return {
            "channels": wf.getnchannels(),
            "sample_width_bytes": wf.getsampwidth(),
            "sample_width_bits": wf.getsampwidth() * 8,
            "frame_rate": wf.getframerate(),
            "n_frames": wf.getnframes(),
            "duration_s": wf.getnframes() / wf.getframerate(),
        }


# ── Tests ─────────────────────────────────────────────────────────────────────
def test_1_engine_availability():
    """Test 1 — Engine availability & type detection."""
    _banner("Test 1 — Engine availability & type detection")

    engine, engine_type = _get_engine()
    if engine is None:
        _fail(f"No TTS engine loaded (error: {_tts_module._load_error})")
        return False

    _pass(f"Engine type     : {engine_type}")
    _info(f"tts_available() : {tts_available()}")

    tts = InterviewTTS()
    _info(f"InterviewTTS.available   : {tts.available}")
    _info(f"InterviewTTS.engine_type : {tts.engine_type}")

    assert tts.available, "InterviewTTS.available should be True"
    _pass("InterviewTTS wrapper is healthy")

    # Log Kokoro-specific info
    if engine_type == "kokoro":
        _info(f"Kokoro SAMPLE_RATE : {getattr(engine, 'SAMPLE_RATE', _KOKORO_SAMPLE_RATE)} Hz")
        import os
        _info(f"KOKORO_VOICE       : {os.getenv('KOKORO_VOICE', 'af_heart')}")
        _info(f"KOKORO_SPEED       : {os.getenv('KOKORO_SPEED', '1.0')}")

    return True


def test_2_synthesize_and_verify():
    """Test 2 — Synthesize a phrase and verify output is valid WAV."""
    _banner("Test 2 — Synthesize → valid WAV bytes")

    phrase = "Hello! This is the exit interview assistant. How are you feeling today?"
    _info(f"Input : {phrase!r}")

    t0 = time.monotonic()
    try:
        wav_bytes = synthesize(phrase)
        elapsed_ms = (time.monotonic() - t0) * 1000
    except Exception as e:
        _fail(f"synthesize() raised: {e}")
        return False

    if not wav_bytes:
        _fail("synthesize() returned empty bytes")
        return False

    _info(f"Output size     : {len(wav_bytes):,} bytes")
    _info(f"First synthesis : {elapsed_ms:.0f} ms")

    # Verify WAV header is parseable
    try:
        info = _parse_wav_info(wav_bytes)
    except Exception as e:
        _fail(f"Output is not a valid WAV file: {e}")
        return False

    _pass(f"Valid WAV — {info['duration_s']:.2f}s audio")
    return True


def test_3_wav_format():
    """Test 3 — WAV format validation (sample rate, channels, bit depth)."""
    _banner("Test 3 — WAV format validation")

    phrase = "Thank you for participating in today's exit interview."
    try:
        wav_bytes = synthesize(phrase)
        info = _parse_wav_info(wav_bytes)
    except Exception as e:
        _fail(f"Could not synthesize for format test: {e}")
        return False

    _, engine_type = _get_engine()

    _info(f"Channels      : {info['channels']}")
    _info(f"Bit depth     : {info['sample_width_bits']} bit")
    _info(f"Sample rate   : {info['frame_rate']} Hz")
    _info(f"Duration      : {info['duration_s']:.2f} s")
    _info(f"Total frames  : {info['n_frames']:,}")

    ok = True

    # Channels must be mono
    if info["channels"] == 1:
        _pass("Mono channel (1 channel)")
    else:
        _fail(f"Expected mono, got {info['channels']} channels")
        ok = False

    # Bit depth
    if info["sample_width_bits"] == 16:
        _pass("16-bit PCM")
    else:
        _fail(f"Expected 16-bit, got {info['sample_width_bits']}-bit")
        ok = False

    # Sample rate depends on engine
    if engine_type == "kokoro":
        expected_rate = _KOKORO_SAMPLE_RATE   # 24 000 Hz
    else:
        expected_rate = None  # pyttsx3 varies by platform

    if expected_rate and info["frame_rate"] != expected_rate:
        _fail(f"Expected {expected_rate} Hz for {engine_type}, got {info['frame_rate']} Hz")
        ok = False
    else:
        _pass(f"Sample rate {info['frame_rate']} Hz ({engine_type})")

    # Duration must be > 0
    if info["duration_s"] > 0:
        _pass(f"Non-zero audio duration ({info['duration_s']:.2f} s)")
    else:
        _fail("Audio has zero duration")
        ok = False

    return ok


def test_4_multiple_phrases():
    """Test 4 — Synthesize all typical interview question phrases."""
    _banner("Test 4 — Multiple interview phrases")

    phrases = [
        "What was your primary reason for leaving?",
        "How would you describe your relationship with your direct manager?",
        "Could you elaborate on that?",
        "Did you feel recognized for your contributions?",
        "What could we have done differently to retain you?",
        "Thank you. Your feedback has been recorded.",
    ]

    results = []
    for i, phrase in enumerate(phrases, 1):
        try:
            t0 = time.monotonic()
            wav = synthesize(phrase)
            ms = (time.monotonic() - t0) * 1000
            info = _parse_wav_info(wav)
            _pass(
                f"Phrase {i}: {info['duration_s']:.2f}s WAV, {len(wav):,} bytes, {ms:.0f} ms"
            )
            results.append(True)
        except Exception as e:
            _fail(f"Phrase {i} failed: {e}")
            results.append(False)

    passed = sum(results)
    _info(f"\n  {passed}/{len(results)} phrases passed")
    return passed == len(results)


def test_5_edge_cases():
    """Test 5 — Edge cases: empty string, very long text."""
    _banner("Test 5 — Edge cases")

    ok = True

    # ── Empty string ──────────────────────────────────────────────────────────
    _info("Testing empty string input...")
    try:
        result = synthesize("")
        _info(f"  Empty string → {len(result)} bytes")
        # Either returns minimal WAV or raises — both acceptable behaviours
        _pass("Empty string handled without crash")
    except (ValueError, RuntimeError) as e:
        # Acceptable if engine raises a descriptive error
        _pass(f"Empty string raised expected error: {type(e).__name__}")
    except Exception as e:
        _fail(f"Empty string caused unexpected exception: {e}")
        ok = False

    # ── Very long text ────────────────────────────────────────────────────────
    _info("\nTesting long text (300+ words)...")
    long_text = (
        "I have been with this company for several years and during that time "
        "I have had the opportunity to work on many interesting projects. "
        "The culture here has always been collaborative and supportive. "
        "However, I believe that it is time for me to take the next step in "
        "my career and explore new opportunities that align with my long-term "
        "professional goals. I have truly valued the relationships I have built "
        "with my colleagues and I will carry those lessons forward. "
    ) * 3

    _info(f"  Text length: {len(long_text)} chars")
    try:
        t0 = time.monotonic()
        wav = synthesize(long_text)
        ms = (time.monotonic() - t0) * 1000
        info = _parse_wav_info(wav)
        _pass(f"Long text synthesised: {info['duration_s']:.1f}s WAV in {ms:.0f} ms")
    except Exception as e:
        _fail(f"Long text synthesis failed: {e}")
        ok = False

    return ok


def test_6_latency_benchmark():
    """Test 6 — Latency benchmark (5 consecutive calls)."""
    _banner("Test 6 — Latency benchmark")

    phrase = "Could you tell me more about why you decided to leave the organisation?"
    runs = 5
    latencies = []

    for i in range(runs):
        t0 = time.monotonic()
        try:
            wav = synthesize(phrase)
            elapsed_ms = (time.monotonic() - t0) * 1000
            info = _parse_wav_info(wav)
            latencies.append(elapsed_ms)
            _info(
                f"  Run {i+1}: {elapsed_ms:.0f} ms → "
                f"{info['duration_s']:.2f}s audio, {len(wav):,} bytes"
            )
        except Exception as e:
            _fail(f"  Run {i+1} failed: {e}")

    if not latencies:
        _fail("All benchmark runs failed")
        return False

    avg = sum(latencies) / len(latencies)
    fastest = min(latencies)
    slowest = max(latencies)

    _info(f"\n  Avg     : {avg:.0f} ms")
    _info(f"  Fastest : {fastest:.0f} ms")
    _info(f"  Slowest : {slowest:.0f} ms")

    _, engine_type = _get_engine()

    # Thresholds from voice_engine_MVP README:
    #   Kokoro ~100 ms, Cartesia 40-90 ms, System TTS varies
    if engine_type == "kokoro" and avg < 2_000:
        _pass(f"Kokoro latency acceptable (avg {avg:.0f} ms)")
    elif engine_type == "pyttsx3":
        _pass(f"pyttsx3 latency (avg {avg:.0f} ms) — varies by system")
    else:
        _info(f"Engine='{engine_type}', avg={avg:.0f} ms")

    _pass(f"Benchmark complete — {len(latencies)}/{runs} runs succeeded")
    return True


# ── Runner ────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("  Exit Interview Bot — TTS Test Suite")
    print("  (follows voice_engine_MVP kokoro_tts_engine.py patterns)")
    print("=" * 60)

    results = {}
    tests = [
        ("1_engine_availability", test_1_engine_availability),
        ("2_synthesize_and_verify", test_2_synthesize_and_verify),
        ("3_wav_format", test_3_wav_format),
        ("4_multiple_phrases", test_4_multiple_phrases),
        ("5_edge_cases", test_5_edge_cases),
        ("6_latency_benchmark", test_6_latency_benchmark),
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
            print(f"  [SKIP]  {name}")
            skipped += 1
        else:
            print(f"  [FAIL]  {name}")
            failed += 1

    total = passed + failed
    print(f"\n  {passed}/{total} passed, {skipped} skipped\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
