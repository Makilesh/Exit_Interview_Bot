"""
Voice WebSocket endpoint for exit interviews.

Provides real-time voice interaction using STT and TTS while reusing
the existing session state and agent logic from api/main.py.
"""

import asyncio
import base64
import json
import logging
from typing import Callable, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from agent.questions import QUESTION_BANK, FOLLOWUP_VARIANTS
from agent.state_manager import InterviewState
from agent.summarizer import Summarizer
from storage.schema import ResponseEntry, FollowUp

from api.session_store import get_session, remove_session
from api.voice.stt import InterviewSTT, stt_available
from api.voice.tts import InterviewTTS, tts_available

logger = logging.getLogger(__name__)

voice_router = APIRouter(prefix="/api/voice", tags=["voice"])

# Lazy-loaded engines
_stt: InterviewSTT | None = None
_tts: InterviewTTS | None = None


def _get_stt() -> InterviewSTT:
    """Get or create the STT engine."""
    global _stt
    if _stt is None:
        _stt = InterviewSTT()
    return _stt


def _get_tts() -> InterviewTTS:
    """Get or create the TTS engine."""
    global _tts
    if _tts is None:
        _tts = InterviewTTS()
    return _tts


def voice_available() -> dict:
    """Check if voice engines are available."""
    return {
        "stt": stt_available(),
        "tts": tts_available(),
    }


async def _send_json(websocket: WebSocket, data: dict) -> None:
    """Send JSON message to client."""
    await websocket.send_text(json.dumps(data))


async def _send_error(websocket: WebSocket, message: str) -> None:
    """Send error message to client."""
    await _send_json(websocket, {"type": "error", "message": message})


async def _send_question(
    websocket: WebSocket,
    text: str,
    question_number: int,
    total: int,
    tts_engine: InterviewTTS | None,
    use_tts: bool,
) -> None:
    """Send question to client, optionally with TTS audio."""
    msg = {
        "type": "question",
        "text": text,
        "question_number": question_number,
        "total": total,
    }

    # Generate TTS audio if needed
    if use_tts and tts_engine and tts_engine.available:
        try:
            audio_bytes = await asyncio.get_running_loop().run_in_executor(
                None, tts_engine.synthesize, text
            )
            msg["audio"] = base64.b64encode(audio_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            # Continue without audio

    await _send_json(websocket, msg)


@voice_router.websocket("/ws/{session_id}")
async def voice_interview(
    websocket: WebSocket,
    session_id: str,
    mode: str = Query(default="voice_voice"),
):
    """
    WebSocket endpoint for voice interview sessions.

    Protocol:
    - Client sends: {"type": "audio", "data": "<base64>"} or raw binary
    - Client sends: {"type": "text", "data": "typed answer"} (text_voice mode)
    - Server sends: {"type": "question", "text": "...", "audio?": "<base64>", ...}
    - Server sends: {"type": "complete", "summary": {...}}
    - Server sends: {"type": "crisis"}
    - Server sends: {"type": "error", "message": "..."}
    """
    await websocket.accept()

    # Validate mode
    if mode not in ("voice_text", "text_voice", "voice_voice"):
        await _send_error(websocket, f"Invalid mode: {mode}")
        await websocket.close(code=1008)
        return

    use_stt = mode in ("voice_text", "voice_voice")
    use_tts = mode in ("text_voice", "voice_voice")

    # Get session
    live = get_session(session_id)
    if live is None:
        await _send_error(websocket, "Session not found")
        await websocket.close(code=1008)
        return

    # Initialize engines
    stt_engine = _get_stt() if use_stt else None
    tts_engine = _get_tts() if use_tts else None

    if use_stt and (stt_engine is None or not stt_engine.available):
        await _send_error(
            websocket,
            "Speech-to-text is not available. "
            "Run: pip install faster-whisper  (requires ffmpeg on PATH). "
            "Try 'Text → Voice' mode instead.",
        )
        await websocket.close(code=1008)
        return

    # Import helpers from main (they're in the same package)
    from api.main import _evaluate_response, _store

    logger.info(f"Voice WebSocket connected: session={session_id}, mode={mode}")

    try:
        # Send initial question
        await _send_question(
            websocket,
            live.pending_question,
            live.state_mgr.current_question_index + 1,
            len(QUESTION_BANK),
            tts_engine,
            use_tts,
        )

        # Main message loop
        while True:
            # Receive message (can be text JSON or binary audio)
            message = await websocket.receive()

            if "text" in message:
                # JSON message
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type", "")

                    # Handle heartbeat ping
                    if msg_type == "ping":
                        await _send_json(websocket, {"type": "pong"})
                        continue

                    if msg_type == "audio":
                        # Base64-encoded audio
                        audio_bytes = base64.b64decode(data.get("data", ""))
                        answer = await asyncio.get_running_loop().run_in_executor(
                            None, stt_engine.transcribe, audio_bytes, True
                        )
                    elif msg_type == "text":
                        # Direct text input (for text_voice mode)
                        answer = data.get("data", "").strip()
                    else:
                        await _send_error(websocket, f"Unknown message type: {msg_type}")
                        continue

                except json.JSONDecodeError:
                    await _send_error(websocket, "Invalid JSON")
                    continue

            elif "bytes" in message:
                # Raw binary audio
                if not use_stt:
                    await _send_error(websocket, "Audio not expected in this mode")
                    continue

                audio_bytes = message["bytes"]
                answer = await asyncio.get_running_loop().run_in_executor(
                    None, stt_engine.transcribe, audio_bytes, True
                )

            else:
                continue  # Skip unexpected message types

            if not answer:
                await _send_error(websocket, "Could not transcribe audio")
                continue

            # Echo transcription to client immediately so UI can display it
            await _send_json(websocket, {"type": "transcript", "text": answer})

            # Process the answer through the same logic as HTTP endpoint
            state_mgr = live.state_mgr

            # Record the answer
            if state_mgr.current_state == InterviewState.ASK_QUESTION:
                live.current_followups = []
                live.current_entry = ResponseEntry(
                    question=live.pending_question,
                    answer=answer,
                    reason_tags=[],
                    sentiment="neutral",
                    follow_ups=[],
                )
                state_mgr.increment_turn()
                state_mgr.transition("response_received")

            elif state_mgr.current_state == InterviewState.ASK_FOLLOWUP:
                live.current_followups.append(
                    FollowUp(question=live.pending_question, answer=answer)
                )
                state_mgr.increment_turn()
                state_mgr.increment_followup()
                state_mgr.transition("followup_done")

            else:
                await _send_error(
                    websocket,
                    f"Session not expecting a response (state: {state_mgr.current_state.value})"
                )
                continue

            # Evaluate response (3 parallel LLM calls)
            result = await asyncio.get_running_loop().run_in_executor(
                None, _evaluate_response, live, answer
            )

            decision_data = result["decision_data"]
            decision_entry = result["decision_entry"]
            classification = result["classification"]
            hr_result = result["hr_result"]

            # Apply classification
            if live.current_entry and isinstance(classification, dict):
                live.current_entry.reason_tags = list(
                    set(live.current_entry.reason_tags + classification.get("reason_tags", []))
                )
                if not live.current_followups or len(live.current_followups) <= 1:
                    raw_sentiment = classification.get("sentiment", "neutral")
                    if raw_sentiment not in ("positive", "neutral", "negative"):
                        raw_sentiment = "negative"
                    if not live.current_followups:
                        live.current_entry.sentiment = raw_sentiment

            # Apply HR flags
            if isinstance(hr_result, dict) and hr_result.get("flag"):
                live.hr_flagged = True
                live.hr_flag_reason = hr_result.get("reason")

            # Check for critical HR flag
            if isinstance(hr_result, dict) and hr_result.get("severity") == "critical":
                if live.current_entry:
                    live.current_entry.follow_ups = live.current_followups
                    live.session.responses.append(live.current_entry)
                live.session.detected_topics = live.decision_engine.topic_memory
                live.session.conversation_length = state_mgr.total_turns
                _store.save(live.session)
                _store.export_transcript(live.session)
                remove_session(session_id)

                await _send_json(websocket, {"type": "crisis"})
                await websocket.close(code=1000)
                return

            # Determine actual decision
            hr_flagged_this_turn = isinstance(hr_result, dict) and hr_result.get("flag")
            decision = decision_data.get("decision", "next_question")

            if decision == "ask_followup" and state_mgr.can_followup() and not hr_flagged_this_turn:
                actual_decision = "ask_followup"
            else:
                actual_decision = "next_question"

            decision_entry.decision = actual_decision
            live.session.agent_decision_log.append(decision_entry)

            # Route based on decision
            if actual_decision == "ask_followup":
                state_mgr.transition("followup_needed")

                idx = state_mgr.current_question_index
                fu_idx = state_mgr.current_followup_count
                variants = FOLLOWUP_VARIANTS.get(idx, [])
                followup_q = variants[fu_idx] if fu_idx < len(variants) else "Could you elaborate on that?"

                live.pending_question = followup_q

                await _send_question(
                    websocket,
                    followup_q,
                    state_mgr.current_question_index + 1,
                    len(QUESTION_BANK),
                    tts_engine,
                    use_tts,
                )
                continue

            # Next question path
            state_mgr.transition("next_question")

            # Finalize current entry
            if live.current_entry:
                live.current_entry.follow_ups = live.current_followups
                live.session.responses.append(live.current_entry)
                live.session.conversation_length = state_mgr.total_turns
                live.session.followup_count += len(live.current_followups)
                live.current_entry = None

            # Advance question
            state_mgr.advance_question()

            if state_mgr.should_terminate():
                # Interview complete
                state_mgr.transition("all_questions_done")
                live.session.detected_topics = live.decision_engine.topic_memory
                live.session.conversation_length = state_mgr.total_turns

                state_mgr.transition("generate_summary")

                # Run summarizer
                summarizer = Summarizer()
                summary_dict = None
                try:
                    summary = await asyncio.get_running_loop().run_in_executor(
                        None, summarizer.generate, live.session
                    )
                    if live.hr_flagged and not summary.flag_for_hr:
                        summary.flag_for_hr = True
                        summary.flag_reason = live.hr_flag_reason
                    live.session.summary = summary
                    summary_dict = summary.model_dump()
                except Exception as e:
                    logger.error(f"Summarizer failed: {e}")

                # Persist
                _store.save(live.session)
                _store.export_transcript(live.session)
                _store.export_summary_md(live.session)

                # Clean up
                remove_session(session_id)

                await _send_json(websocket, {
                    "type": "complete",
                    "summary": summary_dict,
                    "detected_topics": live.session.detected_topics,
                })
                await websocket.close(code=1000)
                return

            # More questions remain
            state_mgr.transition("next_question")
            next_q = QUESTION_BANK[state_mgr.current_question_index]
            live.pending_question = next_q

            await _send_question(
                websocket,
                next_q,
                state_mgr.current_question_index + 1,
                len(QUESTION_BANK),
                tts_engine,
                use_tts,
            )

    except WebSocketDisconnect:
        logger.info(f"Voice WebSocket disconnected: session={session_id}")
    except Exception as e:
        logger.error(f"Voice WebSocket error: {e}")
        try:
            await _send_error(websocket, str(e))
        except:
            pass
    finally:
        # Don't remove session on disconnect — allow reconnection
        pass
