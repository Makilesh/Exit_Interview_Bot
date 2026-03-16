"""
FastAPI application — thin HTTP wrapper around the existing agent core.

All interview logic is delegated to the existing agent/ modules.
This file only handles HTTP routing, session lifecycle, and response formatting.
"""

import concurrent.futures
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from agent.decision_engine import DecisionEngine
from agent.questions import QUESTION_BANK, FOLLOWUP_VARIANTS
from agent.state_manager import StateManager, InterviewState
from agent.summarizer import Summarizer
from agent.tools import classify_sentiment_and_reason, detect_hr_flags
from config import OUTPUT_DIR
from storage.schema import (
    SessionData,
    ResponseEntry,
    FollowUp,
    AgentDecisionEntry,
)
from storage.session import SessionStore

from api.models import (
    SessionStartRequest,
    SessionStartResponse,
    RespondRequest,
    RespondResponse,
    SessionListItem,
)
from api.session_store import (
    LiveSession,
    store_session,
    get_session,
    remove_session,
)
from api.voice import voice_router, voice_available

load_dotenv()

app = FastAPI(
    title="Exit Interview Agent API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include voice WebSocket router
app.include_router(voice_router)

_store = SessionStore(output_dir=OUTPUT_DIR)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_live(session_id: str) -> LiveSession:
    """Fetch a live session or raise 404."""
    live = get_session(session_id)
    if live is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return live


def _evaluate_response(live: LiveSession, latest_response: str) -> dict:
    """Run the 3 parallel LLM calls and return the merged result.

    Returns a dict with keys: decision_data, decision_entry,
    classification, hr_result.
    """
    conversation_history = live.build_conversation_history()
    question = live.current_entry.question if live.current_entry else ""

    classification = None
    hr_result = None
    decision_data = None
    decision_entry = None

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f_decision = executor.submit(
            live.decision_engine.evaluate,
            response=latest_response,
            question=question,
            conversation_history=conversation_history,
        )
        f_classify = executor.submit(
            classify_sentiment_and_reason.invoke,
            {"response": latest_response, "question": question},
        )
        f_hr = executor.submit(
            detect_hr_flags.invoke,
            {"response": latest_response},
        )

        try:
            decision_data, decision_entry = f_decision.result()
        except Exception:
            decision_data = {
                "decision": "next_question",
                "reason": "llm_error",
                "reason_tags": [],
                "sentiment": "neutral",
                "dominant_topics": [],
            }
            decision_entry = AgentDecisionEntry(
                response=latest_response,
                decision="next_question",
                reason="llm_error",
            )
        try:
            classification = f_classify.result()
        except Exception:
            pass
        try:
            hr_result = f_hr.result()
        except Exception:
            pass

    return {
        "decision_data": decision_data,
        "decision_entry": decision_entry,
        "classification": classification,
        "hr_result": hr_result,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    """Health check with voice capability status."""
    return {"status": "ok", "voice": voice_available()}


@app.post("/api/session/start", response_model=SessionStartResponse)
def start_session(req: SessionStartRequest):
    """Create a new interview session and return the first question."""
    valid_modes = ("text_text", "voice_text", "text_voice", "voice_voice")
    if req.mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode. Must be one of: {', '.join(valid_modes)}",
        )

    session_id = str(uuid.uuid4())[:8]
    state_mgr = StateManager()
    decision_engine = DecisionEngine()

    session = SessionData(
        session_id=session_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        responses=[],
        detected_topics=[],
        agent_decision_log=[],
        conversation_length=0,
        followup_count=0,
        summary=None,
    )

    state_mgr.transition("start")  # INTERVIEW_START → ASK_QUESTION
    first_question = QUESTION_BANK[0]

    live = LiveSession(
        state_mgr=state_mgr,
        decision_engine=decision_engine,
        session=session,
        pending_question=first_question,
    )
    store_session(session_id, live)

    return SessionStartResponse(
        session_id=session_id,
        first_question=first_question,
        question_number=1,
        total_questions=len(QUESTION_BANK),
    )


@app.post("/api/session/{session_id}/respond", response_model=RespondResponse)
def respond(session_id: str, req: RespondRequest):
    """Process an employee answer and return the next question or summary."""
    live = _get_live(session_id)
    state_mgr = live.state_mgr
    answer = req.answer.strip()

    if not answer:
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")

    # ---------------------------------------------------------------
    # 1. Record the answer based on the current state
    # ---------------------------------------------------------------
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
        raise HTTPException(
            status_code=409,
            detail=f"Session not expecting a response (state: {state_mgr.current_state.value}).",
        )

    # ---------------------------------------------------------------
    # 2. EVALUATE_RESPONSE — 3 parallel LLM calls
    # ---------------------------------------------------------------
    latest_response = answer
    result = _evaluate_response(live, latest_response)

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

    # Critical severity — stop interview immediately, do not ask another question
    if isinstance(hr_result, dict) and hr_result.get("severity") == "critical":
        if live.current_entry:
            live.current_entry.follow_ups = live.current_followups
            live.session.responses.append(live.current_entry)
        live.session.detected_topics = live.decision_engine.topic_memory
        live.session.conversation_length = state_mgr.total_turns
        _store.save(live.session)
        _store.export_transcript(live.session)  # preserve record for HR review
        remove_session(session_id)
        return RespondResponse(
            next_question=None,
            is_complete=True,
            follow_up=False,
            question_number=state_mgr.current_question_index + 1,
            total_questions=len(QUESTION_BANK),
            agent_decision={"decision": "crisis_escalation", "reason": "critical_hr_flag"},
            detected_topics=[],
            crisis_escalation=True,
        )

    # Determine actual decision after guard
    # Never follow up on HR-flagged responses — do not probe sensitive disclosures
    hr_flagged_this_turn = isinstance(hr_result, dict) and hr_result.get("flag")
    decision = decision_data.get("decision", "next_question")
    reason = decision_data.get("reason", "unknown")

    if decision == "ask_followup" and state_mgr.can_followup() and not hr_flagged_this_turn:
        actual_decision = "ask_followup"
    else:
        actual_decision = "next_question"

    decision_entry.decision = actual_decision
    live.session.agent_decision_log.append(decision_entry)

    # ---------------------------------------------------------------
    # 3. Route based on actual decision
    # ---------------------------------------------------------------
    if actual_decision == "ask_followup":
        state_mgr.transition("followup_needed")

        idx = state_mgr.current_question_index
        fu_idx = state_mgr.current_followup_count
        variants = FOLLOWUP_VARIANTS.get(idx, [])
        followup_q = variants[fu_idx] if fu_idx < len(variants) else "Could you elaborate on that?"

        live.pending_question = followup_q

        return RespondResponse(
            next_question=followup_q,
            is_complete=False,
            follow_up=True,
            question_number=state_mgr.current_question_index + 1,
            total_questions=len(QUESTION_BANK),
            agent_decision={"decision": actual_decision, "reason": reason},
            detected_topics=live.decision_engine.topic_memory,
        )

    # --- next_question path ---
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
        # --- Interview complete ---
        state_mgr.transition("all_questions_done")
        live.session.detected_topics = live.decision_engine.topic_memory
        live.session.conversation_length = state_mgr.total_turns

        state_mgr.transition("generate_summary")

        # Run summarizer
        summarizer = Summarizer()
        try:
            summary = summarizer.generate(live.session)
            if live.hr_flagged and not summary.flag_for_hr:
                summary.flag_for_hr = True
                summary.flag_reason = live.hr_flag_reason
            live.session.summary = summary
        except Exception:
            pass

        # Persist
        _store.save(live.session)
        _store.export_transcript(live.session)
        _store.export_summary_md(live.session)

        # Clean up live session
        remove_session(session_id)

        return RespondResponse(
            next_question=None,
            is_complete=True,
            follow_up=False,
            question_number=len(QUESTION_BANK),
            total_questions=len(QUESTION_BANK),
            agent_decision={"decision": actual_decision, "reason": reason},
            detected_topics=live.session.detected_topics,
            summary=live.session.summary,
        )

    # --- More questions remain ---
    state_mgr.transition("next_question")
    next_q = QUESTION_BANK[state_mgr.current_question_index]
    live.pending_question = next_q

    return RespondResponse(
        next_question=next_q,
        is_complete=False,
        follow_up=False,
        question_number=state_mgr.current_question_index + 1,
        total_questions=len(QUESTION_BANK),
        agent_decision={"decision": actual_decision, "reason": reason},
        detected_topics=live.decision_engine.topic_memory,
    )


@app.get("/api/session/{session_id}")
def get_session_data(session_id: str):
    """Return full SessionData for a completed or active session."""
    # Check live sessions first
    live = get_session(session_id)
    if live:
        return live.session.model_dump()

    # Check persisted sessions
    try:
        loaded = _store.load(session_id)
        return loaded.model_dump()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")


@app.get("/api/sessions", response_model=list[SessionListItem])
def list_sessions():
    """List all completed sessions with their IDs and timestamps."""
    items: list[SessionListItem] = []
    for sid in _store.list_sessions():
        try:
            s = _store.load(sid)
            items.append(SessionListItem(session_id=s.session_id, timestamp=s.timestamp))
        except Exception:
            continue
    return items


# ---------------------------------------------------------------------------
# Download routes
# ---------------------------------------------------------------------------

@app.get("/api/session/{session_id}/download/json")
def download_json(session_id: str):
    """Download the session JSON file."""
    try:
        s = _store.load(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    path = _store._filename(s, ".json")
    return FileResponse(path, filename=path.name, media_type="application/json")


@app.get("/api/session/{session_id}/download/transcript")
def download_transcript(session_id: str):
    """Download the session transcript."""
    try:
        s = _store.load(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    path = _store._filename(s, "_transcript.txt")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    return FileResponse(path, filename=path.name, media_type="text/plain")


@app.get("/api/session/{session_id}/download/summary")
def download_summary(session_id: str):
    """Download the session summary Markdown."""
    try:
        s = _store.load(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    path = _store._filename(s, "_summary.md")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Summary not found")
    return FileResponse(path, filename=path.name, media_type="text/markdown")
